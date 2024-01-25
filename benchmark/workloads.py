import charmonium.time_block as ch_tb
import shutil
import hashlib
import subprocess
import re
import urllib.parse
from collections.abc import Sequence, Mapping
from pathlib import Path
from util import run_all, CmdArg, check_returncode, merge_env_vars, download
import yaml
import tarfile
import shlex
from typing import cast

# ruff: noqa: E501

cwd = Path(__file__).resolve()
result_bin = (cwd.parent / "result").resolve() / "bin"
result_lib = result_bin.parent / "lib"


class Workload:
    kind: str
    name: str

    def setup(self, workdir: Path) -> None:
        pass

    def run(self, workdir: Path) -> tuple[Sequence[CmdArg], Mapping[CmdArg, CmdArg]]:
        return ["true"], {"PATH": str(result_bin)}

    def __str__(self) -> str:
        return self.name


class SpackInstall(Workload):
    """Benchmark installing user-provided Spack package

    Spack is a package manager; it knows how to install software. We want to
    benchmark "installing spack packages".

    However, installing one spack package will necessitate downloading lots of
    source code and installing hundreds of dependent packages.
    - We definitely don't want to benchmark downloading the source code.
    - Installing dependent packages, where the dependencies are very common, is
      less interesting because it makes the data less statistically independent,
      slower, and hides interesting differences between top-level packages.

    Therefore the setup() downloads all code, builds top-level package and
    the dependencies, and then removes just the top-level package. This will get
    built during run().

    """

    kind = "compilation"

    def __init__(self, specs: list[str], version: str = "v0.20.1") -> None:
        self.name = "compile " + "+".join(specs)
        self._version = version
        self._specs = specs
        self._env_vars: Mapping[str, str] = {}

    @property
    def env_name(self) -> str:
        env_name = urllib.parse.quote("-".join(self._specs), safe="")
        if len(env_name) > 64:
            return hashlib.sha256(env_name.encode()).hexdigest()[:16]
        else:
            return env_name

    def setup(self, workdir: Path) -> None:
        self._env_vars = {
            "PATH": str(result_bin),
            "SPACK_USER_CACHE_PATH": str(workdir),
            "SPACK_USER_CONFIG_PATH": str(workdir),
            "LD_LIBRARY_PATH": str(result_lib),
            "LIBRARY_PATH": str(result_lib),
            "SPACK_PYTHON": f"{result_bin}/python",
        }

        # Install spack
        spack_dir = workdir / "spack"
        if not spack_dir.exists():
            check_returncode(subprocess.run(
                run_all(
                    (
                        f"{result_bin}/git", "clone", "-c", "feature.manyFiles=true",
                        "https://github.com/spack/spack.git", str(spack_dir),
                    ),
                    (
                        f"{result_bin}/git", "-C", str(spack_dir), "checkout",
                        self._version, "--force",
                    ),
                ),
                env=self._env_vars,
                check=False,
                capture_output=True,
            ), env=self._env_vars)
        spack = spack_dir / "bin" / "spack"
        assert spack.exists()

        # Use our built $PWD/result/bin/sh, not system /bin/sh
        spack.write_text(spack.read_text().replace("#!/bin/sh", f"#!{result_bin}/sh"))

        # Concretize env with desired specs
        env_dir = workdir / "spack_envs" / self.env_name
        if not env_dir.exists():
            env_dir.mkdir(parents=True)
            check_returncode(subprocess.run(
                [spack, "env", "create", "--dir", env_dir],
                env=self._env_vars,
                check=False,
                capture_output=True,
            ), env=self._env_vars)
        exports = check_returncode(subprocess.run(
            [spack, "env", "activate", "--sh", "--dir", env_dir],
            env=self._env_vars,
            check=False,
            text=True,
            capture_output=True,
        ), env=self._env_vars).stdout
        pattern = re.compile('^export ([a-zA-Z0-9_]+)="?(.*?)"?;?$', flags=re.MULTILINE)
        self._env_vars = cast(Mapping[str, str], merge_env_vars(
            self._env_vars,
            {
                match.group(1): match.group(2)
                for match in pattern.finditer(exports)
            },
        ))

        # I'm not sure why this is necessary
        view_path = env_dir / ".spack-env" / "view"
        if view_path.exists():
            if view_path.is_symlink():
                view_path.unlink()
            else:
                shutil.rmtree(view_path)

        view_path2 = env_dir / ".spack-env" / "._view"
        if view_path2.exists():
            if view_path2.is_symlink():
                view_path2.unlink()
            else:
                shutil.rmtree(view_path2)

        subprocess.run(
            [spack, "repo", "add", "spack-repo"],
            env=self._env_vars,
            check=False,
            capture_output=True,
        )

        check_returncode(subprocess.run(
            [spack, "compiler", "find"],
            env=self._env_vars,
            check=False,
            capture_output=True,
        ), env=self._env_vars)

        conf_obj = yaml.safe_load((env_dir / "spack.yaml").read_text())
        compilers = conf_obj["spack"]["compilers"]
        assert len(compilers) == 1, "Multiple compilers detected; I'm not sure how to choose and configure those."
        compiler = compilers[0]["compiler"]
        compiler.setdefault("environment", {}).setdefault("prepend_path", {})["LIBRARY_PATH"] = str(result_lib)
        (env_dir / "spack.yaml").write_text(yaml.dump(conf_obj))

        check_returncode(subprocess.run(
            [spack, "add", *self._specs],
            env=self._env_vars,
            check=False,
            capture_output=True,
        ), env=self._env_vars)
        spec_shorthand = ", ".join(spec.partition("@")[0] for spec in self._specs)
        if not (env_dir / "spack.lock").exists():
            with ch_tb.ctx(f"concretize {spec_shorthand}"):
                check_returncode(subprocess.run(
                    [spack, "concretize"],
                    env=self._env_vars,
                    check=False,
                    capture_output=True,
                ), env=self._env_vars)
        with \
             (env_dir / "spack_install_stdout").open("wb") as stdout, \
             (env_dir / "spack_install_stderr").open("wb") as stderr, \
             ch_tb.ctx(f"install {spec_shorthand}"):
            print(f"`tail --follow {env_dir}/spack_install_stdout` to check progress. Same applies to stderr")
            check_returncode(subprocess.run(
                [spack, "install"],
                env=self._env_vars,
                check=False,
                stdout=stdout,
                stderr=stderr,
            ), env=self._env_vars)

        # Find deps of that env and take out specs we asked for
        generalized_specs = [
            spec.partition("@")[0]
            for spec in self._specs
        ]

        # Ensure target specs are uninstalled
        with ch_tb.ctx("Uninstalling specs"):
            for spec in generalized_specs:
                has_spec = subprocess.run(
                    [
                        spack, "find", spec,
                    ],
                    env=self._env_vars,
                    check=False,
                    capture_output=True,
                ).returncode == 0
                if has_spec:
                    check_returncode(subprocess.run(
                        [
                            spack, "uninstall", "--all", "--yes", "--force", *spec.split(" "),
                        ],
                        check=False,
                        capture_output=True,
                        env=self._env_vars,
                    ), env=self._env_vars)


    def run(self, workdir: Path) -> tuple[Sequence[CmdArg], Mapping[CmdArg, CmdArg]]:
        spack = workdir / "spack/bin/spack"
        assert "LD_PRELOAD" not in self._env_vars
        # assert "LD_LIBRARY_PATH" not in self._env_vars
        assert "HOME" not in self._env_vars
        # env=patchelf%400.13.1%3A0.13%20%25gcc%20target%3Dx86_64-openblas
        # env - PATH=$PWD/result/bin HOME=$HOME $(jq  --join-output --raw-output 'to_entries[] | .key + "=" + .value + " "' .workdir/work/spack_envs/$env/env_vars.json) .workdir/work/spack/bin/spack --debug bootstrap status 2>~/Downloads/stderr_good.txt >~/Downloads/stdout_good.txt
        # sed -i $'s/\033\[[0-9;]*m//g' ~/Downloads/stderr*.txt
        # sed -i 's/==> \[[0-9:. -]*\] //g' ~/Downloads/stderr*.txt
        return (
            (spack, "install"),
            {k: v for k, v in self._env_vars.items()},
        )


class KaggleNotebook(Workload):
    kind = "data science"

    def __init__(
            self,
            kernel: str,
            competition: str,
            replace: Sequence[tuple[str, str]],
    ) -> None:
        # kaggle kernels pull pmarcelino/comprehensive-data-exploration-with-python
        # kaggle competitions download -c house-prices-advanced-regression-techniques
        self._kernel = kernel
        self._competition = competition
        self._replace = replace
        self._notebook: None | Path = None
        self._data_zip: None | Path = None
        author, name = self._kernel.split("/")
        self.name = author + "-" + name[:4]

    def setup(self, workdir: Path) -> None:
        self._notebook = workdir / "kernel" / (self._kernel.split("/")[1] + ".ipynb")
        self._data_zip = workdir / (self._competition.split("/")[1] + ".zip")
        if not self._notebook.exists():
            check_returncode(subprocess.run(
                [
                    result_bin / "kaggle", "kernels", "pull", "--path",
                    workdir / "kernel", self._kernel
                ],
                env={"PATH": str(result_bin)},
                check=False,
                capture_output=True,
            ))
            notebook_text = self._notebook.read_text()
            for bad, good in self._replace:
                notebook_text = notebook_text.replace(bad, good)
            self._notebook.write_text(notebook_text)
        if not self._data_zip.exists():
            check_returncode(subprocess.run(
                [
                    result_bin / "kaggle", "competitions", "download", "--path",
                    workdir, self._competition.split("/")[1]
                ],
                check=False,
                capture_output=True,
            ))
        if (workdir / "input").exists():
            shutil.rmtree(workdir / "input")
        check_returncode(subprocess.run(
            [result_bin / "unzip", "-o", "-d", workdir / "input", self._data_zip],
            env={"PATH": str(result_bin)},
            check=False,
            capture_output=True,
        ))

    def run(self, workdir: Path) -> tuple[Sequence[CmdArg], Mapping[CmdArg, CmdArg]]:
        assert self._notebook
        return (
            (
                (result_bin / "python").resolve(), "-m", "jupyter", "nbconvert", "--execute",
                "--to=markdown", self._notebook,
            ),
            {
                "PATH": str(result_bin),
            },
        )


# See https://superuser.com/a/1079037
APACHE_CONF = '''
ServerRoot $HTTPD_ROOT
PidFile $HTTPD_ROOT/httpd.pid
ErrorLog $HTTPD_ROOT/errors.log
ServerName localhost
Listen $PORT
LoadModule mpm_event_module $MODULES_ROOT/mod_mpm_event.so
LoadModule unixd_module $MODULES_ROOT/mod_unixd.so
LoadModule authz_core_module $MODULES_ROOT/mod_authz_core.so
DocumentRoot $SRV_ROOT
'''


HTTP_PORT = 54123
HTTP_N_REQUESTS = 500000
HTTP_REQUEST_SIZE = 16 * 1024

HTTP_LOAD_CMD = shlex.join([
    str(result_bin / "hey"), "-n", str(HTTP_N_REQUESTS), f"http://localhost:{HTTP_PORT}/test"
])


class HttpBench(Workload):
    kind = "http_bench"

    def __init__(self, port: int, n_requests: int, request_size: int):
        self.port = port
        self.n_requests = n_requests,
        self.request_size = request_size

    def write_request_payload(self, path: Path) -> None:
        path.write_text("A" * self.request_size)

    def run_server(self, workdir: Path) -> str:
        raise NotImplementedError

    def run(self, workdir: Path) -> tuple[Sequence[CmdArg], Mapping[CmdArg, CmdArg]]:
        return (
            (
                result_bin / "python",
                "run_server_and_client.py",
                self.run_server(workdir),
                HTTP_LOAD_CMD,
            ),
            {},
        )

class ApacheBench(HttpBench):
    name = "apache with apachebench"

    def run_server(self, workdir: Path) -> str:
        httpd_root = (workdir / "apache").resolve()
        if httpd_root.exists():
            shutil.rmtree(httpd_root)
        httpd_root.mkdir()
        srv_root = httpd_root / "srv"
        srv_root.mkdir()
        self.write_request_payload(srv_root / "test")
        conf_file = httpd_root / "httpd.conf"
        modules_root = result_lib.parent / "modules"
        conf_file.write_text(
            APACHE_CONF
            .replace("$HTTPD_ROOT", str(httpd_root))
            .replace("$MODULES_ROOT", str(modules_root))
            .replace("$SRV_ROOT", str(srv_root))
            .replace("$PORT", str(HTTP_PORT))
        )
        return shlex.join([
            str(result_bin / "apacheHttpd"), "-k", "start", "-f", str(conf_file)
        ])


class SimpleHttpBench(HttpBench):
    name = "python http.server with apachebench"

    def run_server(self, workdir: Path) -> str:
        httpd_root = workdir / "simple"
        if httpd_root.exists():
            shutil.rmtree(httpd_root)
        httpd_root.mkdir()
        self.write_request_payload(httpd_root / "test")
        return shlex.join([
            str(result_bin / "python"), "-m", "http.server", str(HTTP_PORT), "--directory", str(httpd_root)
        ]) + f" > {httpd_root}/stdout 2> {httpd_root}/stderr"


class MiniHttpBench(HttpBench):
    name = "minihttp with apachebench"

    def run_server(self, workdir: Path) -> str:
        httpd_root = (workdir / "minihttpd").resolve()
        if httpd_root.exists():
            shutil.rmtree(httpd_root)
        httpd_root.mkdir()
        (httpd_root / "logs").mkdir()
        (httpd_root / "localhost").mkdir()
        self.write_request_payload(httpd_root / "localhost/test")
        return shlex.join([
            str(result_bin / "miniHttpd"), "--logfile", str(httpd_root / "logs"), "--port",
            str(HTTP_PORT), "--change-root", "", "--document-root", str(httpd_root)
        ])


LIGHTTPD_CONF = '''
server.document-root = "$SRV_ROOT"
server.port = $PORT
server.upload-dirs = ( "$SRV_ROOT" )
'''


class LighttpdBench(HttpBench):
    name = "lighttpd with apachebench"

    def run_server(self, workdir: Path) -> str:
        httpd_root = workdir / "lighttpd"
        if httpd_root.exists():
            shutil.rmtree(httpd_root)
        httpd_root.mkdir()
        srv_root = httpd_root / "files"
        srv_root.mkdir()
        self.write_request_payload(httpd_root / "test")
        conf_path = httpd_root / "test.conf"
        conf_path.write_text(
            LIGHTTPD_CONF
            .replace("$PORT", str(HTTP_PORT))
            .replace("$SRV_ROOT", str(srv_root))
        )
        return shlex.join([
            str(result_bin / "lighttpd"), "-D", "-f", str(conf_path),
        ])


NGINX_CONF = '''
# https://stackoverflow.com/a/73297125/1078199
daemon off;  # run in foreground
events {}
pid $NGINX_ROOT/nginx.pid;
http {
    access_log $NGINX_ROOT/access.log;
    client_body_temp_path $NGINX_ROOT;
    proxy_temp_path $NGINX_ROOT;
    fastcgi_temp_path $NGINX_ROOT;
    uwsgi_temp_path $NGINX_ROOT;
    scgi_temp_path $NGINX_ROOT;
    server {
        server_name localhost;
        listen $PORT default_server;
        root $SRV_ROOT;
    }
}
'''


class NginxBench(HttpBench):
    name = "nginx with apachebench"

    def run_server(self, workdir: Path) -> str:
        nginx_root = (workdir / "nginx").resolve()
        if nginx_root.exists():
            shutil.rmtree(nginx_root)
        nginx_root.mkdir()
        srv_root = nginx_root / "files"
        srv_root.mkdir()
        self.write_request_payload(srv_root / "test")
        conf_path = nginx_root / "test.conf"
        conf_path.write_text(
            NGINX_CONF
            .replace("$PORT", str(HTTP_PORT))
            .replace("$NGINX_ROOT", str(nginx_root))
            .replace("$SRV_ROOT", str(srv_root))
        )
        return shlex.join([
            str(result_bin / "nginx"), "-p", str(nginx_root), "-c", "test.conf", "-e", "stderr",
        ])


PROFTPD_CONF = '''
DefaultAddress   0.0.0.0
Port             $PORT
User             $USER
Group            $GROUP
DelayTable       "$FTPDIR/delay"
ScoreboardFile   "$FTPDIR/scoreboard"
PidFile          "$FTPDIR/proftpd.pid"
TransferLog      "$FTPDIR/xferlog"
DefaultRoot      "$FTPDIR/srv"
VRootEngine       on
WtmpLog           off
RequireValidShell off

<Anonymous $FTPDIR/srv/>
    User $USER
    Group $GROUP
    UserAlias anonymous $USER
    <Directory *>
        AllowAll
    </Directory>
</Anonymous>
'''

'''
RequireValidShell off
AuthUserFile     "/home/sam/box/prov/benchmark/.workdir/work/proftpd/authuserfile"
'''

'''
username:$6$3FjBjHLcRPwcOK8h$DpG7OtbJXsQJ0g/TTAQjYiw47ZApeNdo6k9tRlcHQzfALKsoDxecBShN1KohFrB4iYsNRz40Wyq9Y/FK1ddaJ0:1000:100::/home/sam/box/prov/benchmark/.workdir/work/proftpd/srv:/bin/bash
'''


class ProftpdBench(Workload):
    kind = "ftp_bench"

    name = "proftpd with ftpbench"

    def __init__(self, ftp_port: int, n_requests: int) -> None:
        self.ftp_port = ftp_port
        self.n_requests = n_requests

    def setup(self, workdir: Path) -> None:
        ftpdir = (workdir / "proftpd").resolve()
        if ftpdir.exists():
            shutil.rmtree(ftpdir)
        ftpdir.mkdir()
        (ftpdir / "srv").mkdir()
        # user = getpass.getuser()
        # uid = pwd.getpwnam(user).pw_uid
        # gid = pwd.getpwnam(user).pw_gid
        # group = grp.getgrgid(gid).gr_name
        (ftpdir / "conf").write_text(
            PROFTPD_CONF
            .replace("$PORT", str(self.ftp_port))
            .replace("$USER", "benchexec")
            .replace("$GROUP", "benchexec")
            .replace("$FTPDIR", str(ftpdir))
        )
        tmpdir = ftpdir / "tmp"
        tmpdir.mkdir()

    def run(self, workdir: Path) -> tuple[Sequence[CmdArg], Mapping[CmdArg, CmdArg]]:
        ftpdir = (workdir / "proftpd").resolve()
        tmpdir = ftpdir / "tmp"
        ftpbench_args = [str(result_bin / "ftpbench"), "--host", f"127.0.0.1:{self.ftp_port}", "--user", "anonymous", "--password", ""]
        return (
            (
                result_bin / "python",
                "run_server_and_client.py",
                shlex.join([
                    str(result_bin / "proftpd"), "--nodaemon", "--config", str(ftpdir / "conf")
                ]),
                " && ".join([
                    shlex.join([*ftpbench_args, "--maxiter", str(self.n_requsets), "upload", str(tmpdir)]),
                    # shlex.join([*ftpbench_args, "--maxiter", "500", "download", str(tmpdir)]),
                ])
            ),
            {},
        )


class Postmark(Workload):
    kind = "postmark"
    name = "postmark"

    def __init__(self, n_transactions: int) -> None:
        self.n_transactions = n_transactions

    def setup(self, workdir: Path) -> None:
        postmark_dir = workdir / "postmark"
        if postmark_dir.exists():
            shutil.rmtree(postmark_dir)
        postmark_dir.mkdir()
        postmark_input = postmark_dir / "postmark.input"
        postmark_input.write_text("\n".join([f"set transactions {self.n_transactions}", "run", ""]))

    def run(self, workdir: Path) -> tuple[tuple[CmdArg, ...], Mapping[CmdArg, CmdArg]]:
        postmark_dir = workdir / "postmark"
        postmark_input = postmark_dir / "postmark.input"
        return (
            (result_bin / "sh", "-c", f"{result_bin}/env --chdir {postmark_dir} {result_bin}/postmark < {postmark_input}"),
            {},
        )


LINUX_TARBALL_URL = "https://github.com/torvalds/linux/archive/refs/tags/v6.8-rc1.tar.gz"
SMALLER_TARBALL_URL = "https://files.pythonhosted.org/packages/60/7c/04f0706b153c63e94b01fdb1f3ccfca19c80fa7c42ac34c182f4b1a12c75/BenchExec-3.20.tar.gz"


class Archive(Workload):
    kind = "archive"
    def __init__(self, algorithm: str, url: str) -> None:
        self.algorithm = algorithm
        self.name = f"archive tar {self.algorithm}"
        self.url = url

    def setup(self, workdir: Path) -> None:
        resource_dir = workdir / "archive"
        archive_tgz = resource_dir / "archive.tar.gz"
        newarchive = resource_dir / ("newarchive.tar.compressed" if self.algorithm else "newarchive.tar")
        source_dir = resource_dir / "source"
        if not archive_tgz.exists():
            download(archive_tgz, self.url)
        if not source_dir.exists():
            tarfile.TarFile.open(archive_tgz).extractall(path=source_dir)
        if newarchive.exists():
            newarchive.unlink()

    def run(self, workdir: Path) -> tuple[tuple[CmdArg, ...], Mapping[CmdArg, CmdArg]]:
        resource_dir = workdir / "archive"
        newarchive = resource_dir / ("newarchive.tar.compressed" if self.algorithm else "newarchive.tar")
        source_dir = resource_dir / "source"
        use_compress_prog = ("--use-compress-prog", str(result_bin / self.algorithm)) if self.algorithm else ()
        return (
            (result_bin / "tar", "--create", "--file", newarchive, *use_compress_prog, "--directory", source_dir, "."),
            {},
        )


class Unarchive(Workload):
    kind = "unarchive"
    def __init__(self, algorithm: str, url: str) -> None:
        self.algorithm = algorithm
        self.name = f"unarchive {algorithm}"
        self.url = url
        self.target_archive: None | Path = None

    def setup(self, workdir: Path) -> None:
        resource_dir = workdir / "unarchive"
        archive_targz = resource_dir / "archive.tar.gz"
        source_dir = resource_dir / "source"
        if source_dir.exists():
            shutil.rmtree(source_dir)
        source_dir.mkdir()
        if not archive_targz.exists():
            download(archive_targz, self.url)
        if self.algorithm in {"gzip", "pigz"}:
            self.target_archive = archive_targz
        else:
            archive_tar = resource_dir / "archive.tar"
            if not archive_tar.exists():
                subprocess.run([result_bin / "pigz", "--decompress", archive_targz], check=True)
            if self.algorithm == "":
                self.target_archive = archive_tar
            elif self.algorithm in {"pbzip2", "bzip2"}:
                archive_tarbz = resource_dir / "archive.tar.bz2"
                if not archive_tarbz.exists():
                    subprocess.run([result_bin / "pbzip2", "--compress", archive_tar], check=True)
                self.target_archive = archive_tarbz
            else:
                raise NotImplementedError(f"No compression handler for algorithm {self.algorithm}")

    def run(self, workdir: Path) -> tuple[tuple[CmdArg, ...], Mapping[CmdArg, CmdArg]]:
        resource_dir = workdir / "unarchive"
        source_dir = resource_dir / "source"
        if self.target_archive is None:
            raise RuntimeError("self.target_archive should have been set during setup()")
        use_compress_prog = ("--use-compress-prog", str(result_bin / self.algorithm)) if self.algorithm else ()
        return (
            (result_bin / "tar", "--extract", "--file", self.target_archive, *use_compress_prog, "--directory", source_dir, "--strip-components", "1"),
            {},
        )


class Cmds(Workload):
    def __init__(self, kind: str, name: str, setup: tuple[CmdArg, ...], run: tuple[CmdArg, ...]) -> None:
        self.kind = kind
        self.name = name
        self._setup = setup
        self._run = run

    def _replace_args(self, args: tuple[CmdArg, ...], workdir: Path) -> tuple[CmdArg, ...]:
        return tuple(
            (
                arg.replace("$WORKDIR", str(workdir))
                if isinstance(arg, str) else
                arg.replace(b"$WORKDIR", str(workdir).encode())
                if isinstance(arg, bytes) else
                arg
            )
            for arg in args
        )

    def setup(self, workdir: Path) -> None:
        check_returncode(subprocess.run(
            self._replace_args(self._setup, workdir),
            env={"PATH": str(result_bin)},
            check=False,
            capture_output=True,
        ))

    def run(self, workdir: Path) -> tuple[tuple[CmdArg, ...], Mapping[CmdArg, CmdArg]]:
        return tuple(self._replace_args(self._run, workdir)), {}


class VCSTraffic(Workload):
    kind = "vcs"
    def __init__(
            self,
            url: str,
            clone_cmd: tuple[CmdArg, ...],
            checkout_cmd: tuple[CmdArg, ...],
            list_commits_cmd: tuple[CmdArg, ...],
            first_n_commits: None | int = None,
    ) -> None:
        self.name = str(clone_cmd[0]).split("/")[-1] + " " + url.split("/")[-1]
        self.url = url
        self.clone_cmd = clone_cmd
        self.checkout_cmd = checkout_cmd
        self.list_commits_cmd = list_commits_cmd
        self.repo_dir: None | Path = None
        self.commits: None | list[str] = None
        self.first_n_commits = first_n_commits

    def setup(self, workdir: Path) -> None:
        self.repo_dir = workdir / "vcs" / hashlib.sha256(self.url.encode()).hexdigest()[:10]
        if self.repo_dir.exists():
            shutil.rmtree(self.repo_dir)
        subprocess.run([*self.clone_cmd, self.url, self.repo_dir], check=True, capture_output=True)
        self.commits = subprocess.run(
            [*self.list_commits_cmd],
            check=True,
            capture_output=True,
            text=True,
            cwd=self.repo_dir,
        ).stdout.strip().split("\n")[:self.first_n_commits]
        (self.repo_dir / "script").write_text(
            f"cd {self.repo_dir}\n" + "\n".join([
                shlex.join([*map(str, self.checkout_cmd), commit]) + " >/dev/null"
                for commit in self.commits
            ])
        )

    def run(self, workdir: Path) -> tuple[tuple[CmdArg, ...], Mapping[CmdArg, CmdArg]]:
        assert self.repo_dir is not None
        assert self.commits is not None
        return (
            (result_bin / "sh", self.repo_dir / "script"),
            {},
        )

def genomics_workload(name: str, which_targets: tuple[str, ...]) -> Cmds:
    return Cmds(
        "genomics",
        name,
        (
            result_bin / "sh",
            "-c",
            f"""
                if [ ! -d $WORKDIR/blast-benchmark ]; then
                    {result_bin}/curl --output-dir $WORKDIR --remote-name https://ftp.ncbi.nih.gov/blast/demo/benchmark/benchmark2013.tar.gz
                    mkdir --parents $WORKDIR/blast-benchmark
                    {result_bin}/tar --extract --file $WORKDIR/benchmark2013.tar.gz --directory $WORKDIR/blast-benchmark --strip-components 1
                fi
                {result_bin}/rm --recursive --force $WORKDIR/blast-benchmark/output
                {result_bin}/mkdir $WORKDIR/blast-benchmark/output
                {result_bin}/env --chdir=$WORKDIR/blast-benchmark/output {result_bin}/mkdir blastn blastp blastx tblastn tblastx megablast idx_megablast
            """,
        ),
        (
            result_bin / "make",
            "--directory=$WORKDIR/blast-benchmark",
            f"BLASTN={result_bin}/blastn",
            f"BLASTP={result_bin}/blastp",
            f"BLASTX={result_bin}/blastx",
            f"TBLASTN={result_bin}/tblastn",
            f"TBLASTP={result_bin}/tblastp",
            f"MEGABLAST={result_bin}/blastn -task megablast -use_index false",
            f"IDX_MEGABLAST={result_bin}/blastn -task megablast -use_index true",
            f"IDX_MEGABLAST={result_bin}/blastn -task megablast -use_index true",
            f"MAKEMBINDEX={result_bin}/makembindex -iformat blastdb -old_style_index false",
            "TIME=",
            *which_targets,
        ),
    )


noop_cmd = (result_bin / "true",)
create_file_cmd = (result_bin / "sh", "-c", "mkdir -p $WORKDIR/lmbench && echo seq 1000 > $WORKDIR/lmbench/test")

WORKLOADS: Sequence[Workload] = (
    # Cmds("simple", "python", noop_cmd, (result_bin / "python", "-c", "print(4)")),  # noqa: E501
    Cmds("simple", "python-imports", noop_cmd, (result_bin / "python", "-c", "import pandas, pymc, matplotlib")),
    # Cmds("simple", "gcc", noop_cmd, (result_bin / "gcc", "-Wall", "-Og", "test.c", "-o", "$WORKDIR/test.exe")),
    Cmds("simple", "gcc-math-pthread", noop_cmd, (result_bin / "gcc", "-DFULL", "-Wall", "-Og", "-pthread", "test.c", "-o", "$WORKDIR/test.exe", "-lpthread", "-lm")),
    # SpackInstall(["trilinos", "spack-repo.libtool"]), # Broke: openblas
    Cmds("lmbench", "getppid", noop_cmd, (result_bin / "lat_syscall", "-P", "1", "-N", "3000", "null")),
    Cmds("lmbench", "read", noop_cmd, (result_bin / "lat_syscall", "-P", "1", "-N", "3000", "read")),
    Cmds("lmbench", "write", noop_cmd, (result_bin / "lat_syscall", "-P", "1", "-N", "3000", "write")),
    Cmds("lmbench", "stat", create_file_cmd, (result_bin / "lat_syscall", "-P", "1", "-N", "3000", "stat", "$WORKDIR/lmbench/test")),
    Cmds("lmbench", "fstat", create_file_cmd, (result_bin / "lat_syscall", "-P", "1", "-N", "3000", "fstat", "$WORKDIR/lmbench/test")),
    Cmds("lmbench", "open/close", create_file_cmd, (result_bin / "lat_syscall", "-P", "1", "-N", "3000", "open", "$WORKDIR/lmbench/test")),
    Cmds("lmbench", "fork", noop_cmd, (result_bin / "lat_proc", "-P", "1", "-N", "1000", "fork")),
    Cmds("lmbench", "exec", noop_cmd, (result_bin / "lat_proc", "-P", "1", "-N", "1000", "exec")),
    # Cmds("lmbench", "shell", noop_cmd, (result_bin / "lat_proc", "-P", "1", "-N", "100", "shell")),
    Cmds("lmbench", "install-signal", noop_cmd, (result_bin / "lat_sig", "-P", "1", "-N", "3000", "install")),
    Cmds("lmbench", "catch-signal", noop_cmd, (result_bin / "lat_sig", "-P", "1", "-N", "1000" "catch")),
    Cmds("lmbench", "protection-fault", create_file_cmd, (result_bin / "lat_sig", "-P", "1", "-N", "1000", "prot", "$WORKDIR/lmbench/test")),
    Cmds(
        "lmbench",
        "page-fault",
        (result_bin / "sh", "-c", "mkdir -p $WORKDIR/lmbench && seq 3000000 > $WORKDIR/lmbench/big_test"),
        (result_bin / "lat_pagefault", "-P", "1", "-N", "1000", "$WORKDIR/lmbench/big_test"),
    ),
    Cmds("lmbench", "select-file", create_file_cmd, (result_bin / "env", "--chdir", "$WORKDIR", result_bin / "lat_select", "-n", "100", "-P", "1", "-N", "3000", "file")),
    Cmds("lmbench", "select-tcp", create_file_cmd, (result_bin / "lat_select", "-n", "3000", "-P", "1", "tcp")),
    Cmds("lmbench", "mmap", create_file_cmd, (result_bin / "lat_mmap", "-P", "1", "-N", "100", "1M", "$WORKDIR/lmbench/test")),
    Cmds("lmbench", "bw_file-rd", create_file_cmd, (result_bin / "bw_file_rd", "-P", "1", "-N", "3000", "1M", "io_only", "$WORKDIR/lmbench/test")),
    Cmds("lmbench", "bw_unix", noop_cmd, (result_bin / "bw_unix", "-P", "1", "-N", "10")),
    Cmds("lmbench", "bw_pipe", noop_cmd, (result_bin / "bw_pipe", "-P", "1", "-N", "3")),
    Cmds("lmbench", "fs", create_file_cmd, (result_bin / "lat_fs", "-P", "1", "-N", "100", "$WORKDIR/lmbench")),
    SpackInstall(["python"]),
    SpackInstall(["openmpi", "spack-repo.libtool"]),
    SpackInstall(["cmake"]),
    # SpackInstall(["qt"]), # Broke
    SpackInstall(["dealii"]), # Broke
    # SpackInstall(["gcc"]), # takes a long time
    # SpackInstall(["llvm"]), # takes a long time
    SpackInstall(["glibc"]),
    # SpackInstall(["petsc ^spack-repo.libtool"]), # Broke: openblas
    # SpackInstall(["llvm-doe"]), # takes a long time
    SpackInstall(["boost"]),
    SpackInstall(["hdf", "spack-repo.krb5"]),
    # SpackInstall(["openblas"]), # Broke
    SpackInstall(["spack-repo.mpich"]),
    SpackInstall(["openssl"]),
    # SpackInstall(["py-matplotlib"]), # Broke
    # SpackInstall(["gromacs"]), # Broke
    SpackInstall(["apacheHttpd", "spack-repo.openldap"]),
    genomics_workload("blastx-10", ("NM_001004160", "NM_004838")),
    genomics_workload("megablast-10", (
        "NM_001000841", "NM_001008511", "NM_007622", "NM_020327", "NM_032130",
        "NM_064997", "NM_071881", "NM_078614", "NM_105954", "NM_118167",
        "NM_127277", "NM_134656", "NM_146415", "NM_167127", "NM_180448"
    )),
    genomics_workload("tblastn-10", ("NP_072902",)),
    ApacheBench(HTTP_PORT, HTTP_N_REQUESTS, HTTP_REQUEST_SIZE),
    SimpleHttpBench(HTTP_PORT, HTTP_N_REQUESTS, HTTP_REQUEST_SIZE),
    MiniHttpBench(HTTP_PORT, HTTP_N_REQUESTS, HTTP_REQUEST_SIZE),
    LighttpdBench(HTTP_PORT, HTTP_N_REQUESTS, HTTP_REQUEST_SIZE),
    NginxBench(HTTP_PORT, HTTP_N_REQUESTS, HTTP_REQUEST_SIZE),
    ProftpdBench(HTTP_PORT, 500),
    Postmark(1_000_000),
    Archive("", SMALLER_TARBALL_URL),
    Archive("gzip", SMALLER_TARBALL_URL),
    Archive("pigz", SMALLER_TARBALL_URL),
    Archive("bzip2", SMALLER_TARBALL_URL),
    Archive("pbzip2", SMALLER_TARBALL_URL),
    Unarchive("", SMALLER_TARBALL_URL),
    Unarchive("gzip", SMALLER_TARBALL_URL),
    Unarchive("pigz", SMALLER_TARBALL_URL),
    Unarchive("bzip2", SMALLER_TARBALL_URL),
    Unarchive("pbzip2", SMALLER_TARBALL_URL),
    VCSTraffic(
        "https://github.com/pypa/setuptools_scm",
        (result_bin / "git", "clone"),
        (result_bin / "git", "checkout"),
        (result_bin / "git", "log", "--format=%H"),
    ),
    VCSTraffic(
        "https://hg.mozilla.org/schema-validation",
        (result_bin / "hg", "clone"),
        (result_bin / "hg", "checkout"),
        (result_bin / "hg", "log", "--template={node}\n"),
    ),
    KaggleNotebook(
        "pmarcelino/comprehensive-data-exploration-with-python",
        "competitions/house-prices-advanced-regression-techniques",
        replace=(
            (".corr()", ".corr(numeric_only=True)"),
            (
                "df_train['SalePrice'][:,np.newaxis]",
                "df_train['SalePrice'].values[:,np.newaxis]",
            ),
            (
                "df_train.drop((missing_data[missing_data['Total'] > 1]).index,1)",
                "df_train.drop((missing_data[missing_data['Total'] > 1]).index, axis=1)",
            ),
        ),
    ),
    KaggleNotebook(
        "startupsci/titanic-data-science-solutions",
        "competitions/titanic",
        replace=(
            (
                "sns.FacetGrid(train_df, col='Survived', row='Pclass', size=",
                "sns.FacetGrid(train_df, col='Survived', row='Pclass', height=",
            ),
            (
                "sns.FacetGrid(train_df, row='Embarked', size=",
                "sns.FacetGrid(train_df, row='Embarked', height=",
            ),
            (
                "sns.FacetGrid(train_df, row='Embarked', col='Survived', size=",
                "sns.FacetGrid(train_df, row='Embarked', col='Survived', height=",
            ),
            (
                "sns.FacetGrid(train_df, row='Pclass', col='Sex', size=",
                "sns.FacetGrid(train_df, row='Pclass', col='Sex', height=",
            )
        ),
    ),
    KaggleNotebook(
        "ldfreeman3/a-data-science-framework-to-achieve-99-accuracy",
        "competitions/titanic",
        replace=(
            (
                "from sklearn.preprocessing import Imputer , Normalizer",
                (
                    "from sklearn.impute import SimpleImputer as Imputer; "
                    "from sklearn.preprocessing import Normalizer"
                ),
            ),
            (
                "from pandas.tools.plotting import scatter_matrix",
                "from pandas.plotting import scatter_matrix",
            ),
            ("sns.factorplot(", "sns.catplot("),
            (".corr()", ".corr(numeric_only=True)"),
            (
                "data2.set_value(index, 'Random_Predict', 0)",
                "data2.loc[index, 'Random_Predict'] = 0",
            ),
            (
                "data2.set_value(index, 'Random_Predict', 1)",
                "data2.loc[index, 'Random_Predict'] = 1",
            ),
        ),
    ),
    KaggleNotebook(
        "yassineghouzam/titanic-top-4-with-ensemble-modeling",
        "competitions/titanic",
        replace=(
            ("sns.factorplot(", "sns.catplot("),
            (
                r'sns.kdeplot(train[\"Age\"][(train[\"Survived\"] == 0) & (train[\"Age\"].notnull())], color=\"Red\", shade',
                r'sns.kdeplot(train[\"Age\"][(train[\"Survived\"] == 0) & (train[\"Age\"].notnull())], color=\"Red\", fill',
            ),
            (
                r'sns.kdeplot(train[\"Age\"][(train[\"Survived\"] == 1) & (train[\"Age\"].notnull())], ax =g, color=\"Blue\", shade',
                r'sns.kdeplot(train[\"Age\"][(train[\"Survived\"] == 1) & (train[\"Age\"].notnull())], ax =g, color=\"Blue\", fill'
            ),
            ("dataset['Age'].iloc[i]", "dataset.loc[i, 'Age']"),
            ("sns.distplot", "sns.histplot"),
            (
                r'sns.catplot(x=\"SibSp\",y=\"Survived\",data=train,kind=\"bar\", size',
                r'sns.catplot(x=\"SibSp\",y=\"Survived\",data=train,kind=\"bar\", height',
            ),
            (
                r'sns.catplot(x=\"Parch\",y=\"Survived\",data=train,kind=\"bar\", size',
                r'sns.catplot(x=\"Parch\",y=\"Survived\",data=train,kind=\"bar\", height',
            ),
            (
                r'sns.catplot(x=\"Pclass\",y=\"Survived\",data=train,kind=\"bar\", size',
                r'sns.catplot(x=\"Pclass\",y=\"Survived\",data=train,kind=\"bar\", height',
            ),
            (
                r'sns.catplot(x=\"Pclass\", y=\"Survived\", hue=\"Sex\", data=train,\n                   size',
                r'sns.catplot(x=\"Pclass\", y=\"Survived\", hue=\"Sex\", data=train,\n                   height'),
            (
                r'sns.catplot(x=\"Embarked\", y=\"Survived\",  data=train,\n                   size',
                r'sns.catplot(x=\"Embarked\", y=\"Survived\",  data=train,\n                   height',
            ),
            (
                r'sns.catplot(\"Pclass\", col=\"Embarked\",  data=train,\n                   size',
                r'sns.catplot(x=\"Pclass\", col=\"Embarked\",  data=train,\n                   height',
            ),
            (
                r'set_xticklabels([\"Master\",\"Miss/Ms/Mme/Mlle/Mrs\",\"Mr\",\"Rare\"])',
                r'set_xticks(range(4), labels=[\"Master\",\"Miss/Ms/Mme/Mlle/Mrs\",\"Mr\",\"Rare\"])',
            ),
            (
                "sns.countplot(dataset[\\\"Cabin\\\"],order=['A','B','C','D','E','F','G','T','X'])",
                "sns.countplot(dataset, x='Cabin', order=['A','B','C','D','E','F','G','T','X'])",
            ),
            (
                "sns.barplot(\\\"CrossValMeans\\\",\\\"Algorithm\\\",data = cv_res, palette=\\\"Set3\\\",orient = \\\"h\\\",**{'xerr':cv_std})",
                "sns.barplot(x=\\\"CrossValMeans\\\",y=\\\"Algorithm\\\",data = cv_res, palette=\\\"Set3\\\",orient = \\\"h\\\",**{'xerr':cv_std})",
            ),
            (
                "train = dataset[:train_len]\ntest = dataset[train_len:]\n",
                "train = dataset[:train_len].copy()\ntest = dataset[train_len:].copy()\n",
            ),
            # (r'g.set_xlabel(\"Mean Accuracy\")', ""),
            # (r'g = g.set_title(\\"Cross validation scores\\")', ""),
            ('\'loss\' : [\\"deviance\\"]', '\'loss\' : [\\"log_loss\\"]'),
            ("n_jobs=4", "n_jobs=1"),
            ("n_jobs= 4", "n_jobs=1"),
            # Skip boring CPU-heavy computation
            (
                r'\"learning_rate\":  [0.0001, 0.001, 0.01, 0.1, 0.2, 0.3,1.5]',
                r'\"learning_rate\":  [0.3]',
            ),
            (
                r'\"min_samples_split\": [2, 3, 10]',
                r'\"min_samples_split\": [3]',
            ),
            (
                r'\"min_samples_leaf\": [1, 3, 10]',
                r'\"min_samples_leaf\": [3]',
            ),
            (
                r"'n_estimators' : [100,200,300]",
                r"'n_estimators' : [200]",
            ),
            (
                r"'C': [1, 10, 50, 100,200,300, 1000]",
                r"'C': [10]",
            ),
            (
                "kfold = StratifiedKFold(n_splits=10)",
                "kfold = StratifiedKFold(n_splits=3)",
            )
        ),
    ),
)
