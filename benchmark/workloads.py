import charmonium.time_block as ch_tb
import shutil
import hashlib
import subprocess
import collections
import re
import urllib.parse
from collections.abc import Sequence, Mapping
from pathlib import Path
from util import run_all, CmdArg, check_returncode, merge_env_vars, download, groupby_dict, cmd_arg
import yaml
import tarfile
import shlex
from typing import cast, Any

# ruff: noqa: E501

cwd = Path(__file__).resolve()
result_bin = (cwd.parent / "result").resolve() / "bin"
result_lib = result_bin.parent / "lib"
result = result_lib.parent


class Workload:
    kind: str
    name: str
    network_access = False

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

    kind = "spack"

    def __init__(
            self,
            specs: list[str],
            name: str | None = None,
            version: str = "02a6ec7b3c2d487010a192eb6ecb201c4d1a6d2e",
            # some of my PR's landed in develop, but haven't been part of an official spack release yet.
            # https://github.com/spack/spack/pull/42199
            # https://github.com/spack/spack/pull/42199
    ) -> None:
        self.name = name if name is not None else "spack " + specs[0]
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
            cast(Mapping[CmdArg, str], self._env_vars),
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
        env_obj = compiler.setdefault("environment", {})
        prepend_path = env_obj.setdefault("prepend_path", {})
        prepend_path["LIBRARY_PATH"] = str(result_lib)
        prepend_path["CPATH"] = str(result_lib.parent / "include")
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
    kind = "notebook"

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
        self.name = name[:10]

    def setup(self, workdir: Path) -> None:
        self._kaggle_dir = workdir / "kaggle"
        self._kernel_dir = self._kaggle_dir / "kernel"
        self._input_dir = self._kaggle_dir / "input"
        self._notebook = self._kernel_dir / (self._kernel.split("/")[1] + ".ipynb")
        self._data_zip = self._kaggle_dir / (self._competition.split("/")[1] + ".zip")
        if not self._notebook.exists():
            check_returncode(subprocess.run(
                [
                    result_bin / "kaggle", "kernels", "pull", "--path",
                    self._kernel_dir, self._kernel
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
                    self._kaggle_dir, self._competition.split("/")[1]
                ],
                check=False,
                capture_output=True,
            ))
        if self._input_dir.exists():
            shutil.rmtree(self._input_dir)
        check_returncode(subprocess.run(
            [result_bin / "unzip", "-o", "-d", self._input_dir, self._data_zip],
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


class HttpBench(Workload):
    kind = "http_server"
    network_access = True

    def __init__(self, port: int, n_requests: int, request_size: int):
        self.port = port
        self.n_requests = n_requests
        self.request_size = request_size

    def write_request_payload(self, path: Path) -> None:
        path.write_text("A" * self.request_size)

    def run_server(self, workdir: Path) -> str:
        raise NotImplementedError

    def get_load(self) -> tuple[CmdArg, ...]:
        return str(result_bin / "hey"), "-n", str(self.n_requests), f"http://localhost:{self.port}/test"

    def stop_server(self) -> tuple[CmdArg, ...] | None:
        return None

    def run(self, workdir: Path) -> tuple[Sequence[CmdArg], Mapping[CmdArg, CmdArg]]:
        stop_server = self.stop_server()
        return (
            (
                result_bin / "python",
                "run_server_and_client.py",
                self.run_server(workdir),
                " && ".join([
                    shlex.join(map(str, self.get_load())),
                    *((shlex.join(map(bytes.decode, map(cmd_arg, stop_server))),) if stop_server is not None else ()),
                ]),
                shlex.join([
                    str(result_bin / "curl"), "--silent", "--fail", "--output", "/dev/null", f"http://localhost:{HTTP_PORT}/test",
                ]),
            ),
            {},
        )


class Apache(HttpBench):
    name = "apache"

    # def stop_server(self) -> tuple[CmdArg, ...] | None:
    #     return (result_bin / "apacheHttpd", "-k", "graceful-stop")

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
            str(result_bin / "apacheHttpd"), "-k", "start", "-f", str(conf_file), "-X",
        ])


class SimpleHttp(HttpBench):
    name = "python http.server"

    def run_server(self, workdir: Path) -> str:
        httpd_root = workdir / "simple"
        if httpd_root.exists():
            shutil.rmtree(httpd_root)
        httpd_root.mkdir()
        self.write_request_payload(httpd_root / "test")
        return shlex.join([
            str(result_bin / "python"), "-m", "http.server", str(HTTP_PORT), "--directory", str(httpd_root)
        ]) + f" > {httpd_root}/stdout 2> {httpd_root}/stderr"


class MiniHttp(HttpBench):
    name = "minihttp"

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
server.errorlog = "$HTTPD_ROOT/error.log"
'''


class Lighttpd(HttpBench):
    name = "lighttpd"

    def run_server(self, workdir: Path) -> str:
        httpd_root = (workdir / "lighttpd").resolve()
        if httpd_root.exists():
            shutil.rmtree(httpd_root)
        httpd_root.mkdir()
        srv_root = httpd_root / "files"
        srv_root.mkdir()
        self.write_request_payload(srv_root / "test")
        conf_path = httpd_root / "test.conf"
        conf_path.write_text(
            LIGHTTPD_CONF
            .replace("$PORT", str(HTTP_PORT))
            .replace("$SRV_ROOT", str(srv_root))
            .replace("$HTTPD_ROOT", str(httpd_root))
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


class Nginx(HttpBench):
    name = "nginx"

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


class HttpClient(SimpleHttp):
    def __init__(self, name: str, http_client: tuple[CmdArg, ...], *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.kind = "http_client"
        self.http_client = http_client

    def get_load(self) -> tuple[CmdArg, ...]:
        http_client_cmd = tuple(
            cmd_arg(arg)
            .decode()
            .replace("$outfile", ".workdir/work/downloaded_file")
            .replace("$url", f"http://localhost:{HTTP_PORT}/test")
            for arg in self.http_client
        )
        return repeat(self.n_requests, http_client_cmd)


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


class Proftpd(Workload):
    kind = "ftp_server"
    name = "proftpd with ftpbench"
    network_access = True

    def __init__(self, ftp_port: int, n_requests: int) -> None:
        self.ftp_port = ftp_port
        self.n_requests = n_requests

    def setup(self, workdir: Path) -> None:
        ftpdir = (workdir / "proftpd").resolve()
        if ftpdir.exists():
            shutil.rmtree(ftpdir)
        ftpdir.mkdir()
        (ftpdir / "srv").mkdir()
        (ftpdir / "srv/test").write_text("A" * 1024 * 1024)
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

    def get_load(self, tmpdir: Path) -> tuple[CmdArg, ...]:
        return (
            str(result_bin / "ftpbench"),
            "--host",
            f"127.0.0.1:{self.ftp_port}",
            "--user",
            "anonymous",
            "--password",
            "",
            "--maxiter",
            str(self.n_requests),
            "upload",
            str(tmpdir),
        )

    def run(self, workdir: Path) -> tuple[Sequence[CmdArg], Mapping[CmdArg, CmdArg]]:
        ftpdir = (workdir / "proftpd").resolve()
        tmpdir = ftpdir / "tmp"
        return (
            (
                result_bin / "python",
                "run_server_and_client.py",
                shlex.join([
                    str(result_bin / "proftpd"), "--nodaemon", "--config", str(ftpdir / "conf")
                ]),
                shlex.join(cmd_arg(arg).decode() for arg in self.get_load(tmpdir)),
                shlex.join([
                    str(result_bin / "curl"), "--silent", "--output", f"{tmpdir}/test", f"ftp://anonymous:@127.0.0.1:{self.ftp_port}/test"
                ])
            ),
            {},
        )


class FtpClient(Proftpd):
    def __init__(self, name: str, ftp_client: tuple[CmdArg, ...], *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.kind = "ftp_client"
        self.name = name
        self.ftp_client = ftp_client

    def get_load(self, tmpdir: Path) -> tuple[CmdArg, ...]:
        tmpdir.mkdir(exist_ok=True)
        return repeat(self.n_requests, tuple(
            cmd_arg(arg)
            .decode()
            .replace("$url", f"ftp://anonymous:@127.0.0.1:{self.ftp_port}/test")
            .replace("$host", "127.0.0.1")
            .replace("$username", "anonymous")
            .replace("$password", "")
            .replace("$port", str(self.ftp_port))
            .replace("$remote_file", "test")
            .replace("$dst", str(tmpdir / "local_test"))
            for arg in self.ftp_client
        ))


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
    def __init__(self, algorithm: str, url: str, repetitions: int) -> None:
        self.algorithm = algorithm
        self.name = f"archive {self.algorithm}".strip()
        self.url = url
        self.repetitions = repetitions

    def setup(self, workdir: Path) -> None:
        resource_dir = workdir / "archive"
        resource_dir.mkdir(exist_ok=True)
        archive_tgz = resource_dir / "archive.tar.gz"
        newarchive = resource_dir / ("newarchive.tar.compressed" if self.algorithm else "newarchive.tar")
        source_dir = resource_dir / "source"
        if not archive_tgz.exists():
            download(archive_tgz, self.url)
        if not source_dir.exists():
            with tarfile.TarFile.open(archive_tgz) as archive_tgz_obj:
                archive_tgz_obj.extractall(path=source_dir)
        if newarchive.exists():
            newarchive.unlink()

    def run(self, workdir: Path) -> tuple[tuple[CmdArg, ...], Mapping[CmdArg, CmdArg]]:
        resource_dir = workdir / "archive"
        newarchive = resource_dir / ("newarchive.tar.compressed" if self.algorithm else "newarchive.tar")
        source_dir = resource_dir / "source"
        use_compress_prog = ("--use-compress-prog", str(result_bin / self.algorithm)) if self.algorithm else ()
        return (
            repeat(self.repetitions, (result_bin / "tar", "--create", "--file", newarchive, *use_compress_prog, "--directory", source_dir, ".")),
            {},
        )


class Unarchive(Workload):
    kind = "unarchive"
    def __init__(self, algorithm: str, url: str, repetitions: int) -> None:
        self.algorithm = algorithm
        self.name = f"unarchive {algorithm}".strip()
        self.url = url
        self.target_archive: None | Path = None
        self.repetitions = repetitions

    def setup(self, workdir: Path) -> None:
        resource_dir = workdir / "unarchive"
        resource_dir.mkdir(exist_ok=True)
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
            repeat(self.repetitions, (
                result_bin / "tar", "--extract", "--file", self.target_archive,
                *use_compress_prog, "--directory", source_dir, "--strip-components", "1", "--overwrite",
            )),
            {},
        )


class Cmds(Workload):
    def __init__(self, kind: str, name: str, setup: tuple[CmdArg, ...], run: tuple[CmdArg, ...], run_env: Mapping[CmdArg, CmdArg] = {}) -> None:
        self.kind = kind
        self.name = name
        self._setup = setup
        self._run = run
        self.run_env = run_env

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
        return tuple(self._replace_args(self._run, workdir)), self.run_env


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


class Blast(Workload):
    kind = "blast"

    @staticmethod
    def get_all() -> list["Blast"]:
        workdir = Path(".workdir/0/work")
        Blast.static_setup(workdir)
        blastdir = workdir / "blast-benchmark/"
        blasts = []
        targets = ["blastn", "megablast", "tblastn", "tblastx", "blastp", "blastx"]
        for line in (blastdir / "Makefile").read_text().split("\n"):
            if line.count(":") == 1:
                target, objects_str = line.split(":")
                objects = objects_str.strip().split(" ")
                if target in targets:
                    # count = int(input(f"How many {target} (of {len(objects)})? "))
                    # sampled_objects = objects
                    # print(",\n".join(f'Blast("{target}-{object}", ("{object}",))' for object in sampled_objects) + ",")
                    for object in objects:
                        blasts.append(Blast(f"{target}-{object}", (object,)))
        return blasts

    def __init__(self, name: str, which_targets: tuple[str, ...]) -> None:
        self.name = name
        self.which_targets = which_targets

    @staticmethod
    def static_setup(workdir: Path) -> None:
        blastdir = workdir / "blast-benchmark"
        if not blastdir.exists():
            blastdir.mkdir(parents=True)
            blast_targz = blastdir / "blast.tar.gz"
            download(blast_targz, "https://ftp.ncbi.nih.gov/blast/demo/benchmark/benchmark2013.tar.gz")
            with tarfile.TarFile.open(blast_targz) as blast_targz_obj:
                blast_targz_obj.extractall(
                    blastdir,
                    filter=lambda member, dest_path: member.replace(name="/".join(member.name.split("/")[1:])),
                )
        (blastdir / "Makefile").write_text("\n".join([
            line.partition("2>")[0]
            for line in (blastdir / "Makefile").read_text().split("\n")
        ]))
        output_dir = blastdir / "output"
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir()
        for subdir in ["blastn", "blastp", "blastx", "tblastn", "tblastx", "megablast", "idx_megablast"]:
            (output_dir / subdir).mkdir()


    def setup(self, workdir: Path) -> None:
        Blast.static_setup(workdir)

    def run(self, workdir: Path) -> tuple[tuple[CmdArg, ...], Mapping[CmdArg, CmdArg]]:
        blastdir = workdir / "blast-benchmark"
        return (
            (
                result_bin / "make",
                f"--directory={blastdir}",
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
                *self.which_targets,
            ),
            {},
        )


class Copy(Workload):
    kind = "copy"

    def __init__(self, name: str, url: str) -> None:
        self.name = name
        self.url = url
        self.name_hash = hashlib.sha256(self.url.encode()).hexdigest()[:10]

    def setup(self, workdir: Path) -> None:
        main_dir = (workdir / "copy")
        if not main_dir.exists():
            main_dir.mkdir()
        archive = main_dir / (self.name_hash + ".tar.gz")
        if not archive.exists():
            download(archive, self.url)
        src_dir = workdir / self.name_hash
        if not src_dir.exists():
            src_dir.mkdir()
            with tarfile.TarFile.open(archive) as archive_obj:
                archive_obj.extractall(
                    src_dir,
                    filter=lambda member, dest_path: member.replace(name="/".join(member.name.split("/")[1:])),
                )
        dst_dir = workdir / "dst"
        if dst_dir.exists():
            shutil.rmtree(dst_dir)

    def run(self, workdir: Path) -> tuple[tuple[CmdArg, ...], Mapping[CmdArg, CmdArg]]:
        src_dir = workdir / self.name_hash
        dst_dir = workdir / "dst"
        return (
            (result_bin / "cp", "--recursive", str(src_dir), str(dst_dir)),
            {},
        )

noop_cmd = (result_bin / "true",)
def create_file_cmd(size: int) -> tuple[CmdArg, ...]:
    return (
        result_bin / "python",
        "-c",
        "\n".join([
            "import pathlib",
            "dir = pathlib.Path('$WORKDIR/lmbench')",
            "dir.mkdir(exist_ok=True)",
            f"(dir / 'file').write_text({size} * 'A')",
        ]),
    )


def repeat(n: int, cmd: tuple[CmdArg, ...]) -> tuple[CmdArg, ...]:
    return (
        result_bin / "sh",
        "-c",
        f"for i in $({result_bin}/seq {n}); do {shlex.join(cmd_arg(cmd_part).decode() for cmd_part in cmd)}; done",
    )


HTTP_PORT = 54123
HTTP_N_REQUESTS = 50000
HTTP_REQUEST_SIZE = 16 * 1024


# NOTE: where there are repetitions, I've balanced these as best as I can to make them take between 10 and 30 seconds.
# 10 seconds is enough time that I am sure the cost of initial file loading is not a factor.
# Obviously, the Spack compile and Kaggle notebooks take much longer than this, and nothing can be done about that.
WORKLOADS: list[Workload] = [
    Cmds("simple", "hello", noop_cmd, repeat(1000, (result_bin / "hello",))),
    Cmds("simple", "ps", noop_cmd, repeat(1000, (result_bin / "ps", "aux"))),
    Cmds("simple", "true", noop_cmd, repeat(1000, (result_bin / "true",))),
    Cmds("simple", "echo", noop_cmd, repeat(1000, (result_bin / "echo", "hello", "world"))),
    Cmds("simple", "ls", create_file_cmd(100), repeat(1000, (result_bin / "ls", "$WORKDIR/lmbench"))),
    Cmds("python", "python-hello-world", noop_cmd, repeat(100, (result_bin / "python", "-c", "print('hello world')"))),
    Cmds("python", "python-import", noop_cmd, repeat(10, (result_bin / "python", "-c", "import pandas, matplotlib; print('hi')"))),
    Cmds("gcc", "gcc-hello-world", noop_cmd, repeat(100, (result_bin / "gcc", "-Wall", "-Og", "test.c", "-o", "$WORKDIR/test.exe"))),
    Cmds("gcc", "gcc-hello-world threads", noop_cmd, repeat(100, (result_bin / "gcc", "-DUSE_THREADS", "-Wall", "-O3", "-pthread", "test.c", "-o", "$WORKDIR/test.exe", "-lpthread"))),
    # TOD: Fix shell workloads
    Cmds("shell", "shell-incr", noop_cmd, (result_bin / "bash", "-c", "i=0; for i in seq 10000; do i=$((i+1)); done")),
    Cmds("shell", "cd", noop_cmd, (result_bin / "bash", "-c", "dir0={result_bin}/realpath $PWD; dir1={result_bin}/realpath $WORKDIR; for i in seq 10000; do cd $dir0; cd $dir1; done")),
    Cmds("shell", "shell-echo", noop_cmd, (result_bin / "bash", "-c", "for i in seq 10000; do echo hi > /dev/null; done")),
    Cmds(
        "pdflatex",
        "latex-test",
        (result_bin / "sh", "-c", f"{result_bin}/mkdir --parents $WORKDIR/latex && {result_bin}/cp test.tex $WORKDIR/latex/test.tex"),
        (result_bin / "env", "--chdir", "$WORKDIR/latex", "pdflatex", "test.tex"),
    ),
    Cmds(
        "pdflatex",
        "latex-test2",
        (result_bin / "sh", "-c", f"{result_bin}/mkdir --parents $WORKDIR/latex && {result_bin}/cp test2.tex $WORKDIR/latex/test2.tex"),
        (result_bin / "env", "--chdir", "$WORKDIR/latex", "pdflatex", "test2.tex"),
    ),
    Cmds("lmbench", "lm-getppid", noop_cmd, (result_bin / "lat_syscall", "-N", "1000", "null"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-read", noop_cmd, (result_bin / "lat_syscall", "-N", "1000", "read"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-write", noop_cmd, (result_bin / "lat_syscall", "-N", "1000", "write"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-stat", create_file_cmd(1024), (result_bin / "lat_syscall", "-N", "1000", "stat", "$WORKDIR/lmbench/file"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-fstat", create_file_cmd(1024), (result_bin / "lat_syscall", "-N", "1000", "fstat", "$WORKDIR/lmbench/file"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-open/close", create_file_cmd(1024), (result_bin / "lat_syscall", "-N", "1000", "open", "$WORKDIR/lmbench/file"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-fork", noop_cmd, (result_bin / "lat_proc", "-N", "1000", "fork"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-exec", noop_cmd, (result_bin / "lat_proc", "-N", "1000", "exec"), {"ENOUGH": "10000"}),
    # Cmds("lmbench", "lm-shell", noop_cmd, (result_bin / "lat_proc", "-N", "100", "shell")), # broke
    Cmds("lmbench", "lm-install-signal", noop_cmd, (result_bin / "lat_sig", "-N", "1000", "install"), {"ENOUGH": "10000"}), # noisy
    Cmds("lmbench", "lm-catch-signal", noop_cmd, (result_bin / "lat_sig", "-N", "1000", "catch"), {"ENOUGH": "10000"}), # noisy
    Cmds("lmbench", "lm-protection-fault", create_file_cmd(1024), (result_bin / "lat_sig", "-N", "300", "prot", "$WORKDIR/lmbench/file"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-page-fault", create_file_cmd(8 * 1024 * 1024), (result_bin / "lat_pagefault", "-N", "1000", "$WORKDIR/lmbench/file"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-select-file", create_file_cmd(1024), (result_bin / "env", "--chdir", "$WORKDIR", result_bin / "lat_select", "-n", "100", "-N", "1000", "file"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-select-tcp", create_file_cmd(1024), (result_bin / "lat_select", "-n", "100", "-N", "1000", "tcp"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-mmap", create_file_cmd(8 * 1024 * 1024), (result_bin / "lat_mmap", "-N", "1000", "1M", "$WORKDIR/lmbench/file"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-bw_file_rd", create_file_cmd(1024), (result_bin / "bw_file_rd", "-N", "1000", "1M", "io_only", "$WORKDIR/lmbench/file"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-bw_unix", noop_cmd, (result_bin / "bw_unix", "-N", "10"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-bw_pipe", noop_cmd, (result_bin / "bw_pipe", "-N", "10"), {"ENOUGH": "10000"}),
    Cmds("lmbench", "lm-fs", create_file_cmd(1024), (result_bin / "lat_fs", "-N", "100", "$WORKDIR/lmbench"), {"ENOUGH": "10000"}),
    # Cmds("splash-3", "splash-barnes", noop_cmd, (result_bin / "sh", "-c", f"{result_bin}/BARNES < {result}/inputs/barnes/n16384-p1")),
    Cmds("splash-3", "splash-fmm", (result_bin / "mkdir", "--parents", "$WORKDIR/splash"), repeat(1000, (result_bin / "sh", "-c", f"{result_bin}/FMM -o $WORKDIR/splash/fmm-out < {result}/inputs/fmm/input.4.16384"))),
    Cmds("splash-3", "splash-ocean", noop_cmd, (result_bin / "OCEAN", "-p1", "-n", "1026")),
    Cmds("splash-3", "splash-radiosity", noop_cmd, repeat(100, (result_bin / "RADIOSITY", "-p", "1", "-ae", "50000", "-bf", "0.1", "-en", "0.05", "-room", "-batch"))),
    Cmds("splash-3", "splash-raytrace", (result_bin / "mkdir", "--parents", "$WORKDIR/splash"), (result_bin / "sh", "-c", f"cd $WORKDIR/splash; {result_bin}/RAYTRACE -p1 -m512 {result}/inputs/raytrace/car.env")),
    Cmds("splash-3", "splash-volrend", noop_cmd, (result_bin / "VOLREND", "1", f"{result}/inputs/volrend/head", "256")),
    Cmds("splash-3", "splash-water-nsquared", noop_cmd, repeat(300, (result_bin / "sh", "-c", f"{result_bin}/WATER-NSQUARED < {result}/inputs/water-nsquared/n512-p1"))),
    Cmds("splash-3", "splash-water-spatial", noop_cmd, repeat(300, (result_bin / "sh", "-c", f"{result_bin}/WATER-SPATIAL < {result}/inputs/water-spatial/n512-p1"))),
    Cmds("splash-3", "splash-cholesky", noop_cmd, repeat(300, (result_bin / "sh", "-c", f"{result_bin}/CHOLESKY -p1 < {result}/inputs/cholesky/tk15.O"))),
    Cmds("splash-3", "splash-fft", noop_cmd, (result_bin / "FFT", "-p1", "-m256")),
    Cmds("splash-3", "splash-lu", noop_cmd, repeat(10, (result_bin / "LU", "-p1", "-n4096"))),
    Cmds("splash-3", "splash-radix", noop_cmd, (result_bin / "RADIX", "-p1", "-n134217728")),
    # SpackInstall(["trilinos"]), # Broke: openblas
    SpackInstall(["python"]),
    # SpackInstall(["openmpi", "spack-repo.krb5"]),
    # SpackInstall(["cmake"]),  # too long (barely)
    # SpackInstall(["qt"]), # Broke
    # SpackInstall(["dealii"]), # Broke
    # SpackInstall(["gcc"]), # takes a long time
    # SpackInstall(["llvm"]), # takes a long time
    # SpackInstall(["petsc"]), # Broke: openblas
    # SpackInstall(["llvm-doe"]), # takes a long time
    SpackInstall(["boost"]),
    SpackInstall(["hdf5~mpi", "spack-repo.krb5"]),
    # SpackInstall(["openblas"]), # Broke
    SpackInstall(["spack-repo.mpich"]),
    # SpackInstall(["openssl"]),  # too long (barely)
    # SpackInstall(["py-matplotlib"]), # Broke
    # SpackInstall(["gromacs"]), # Broke
    SpackInstall(["glibc"]),
    SpackInstall(["spack-repo.apacheHttpd", "spack-repo.openldap", "spack-repo.apr-util"]),
    SpackInstall(["perl"]),
    # SpackInstall(["r"]),
    SpackInstall(["git"]),
    # SpackInstall(["py-numpy"]),
    # SpackInstall(["py-scipy"]),
    # SpackInstall(["py-h5py"]),
    *Blast.get_all(),
    Copy("cp linux", LINUX_TARBALL_URL),
    Copy("cp smaller", SMALLER_TARBALL_URL),
    Apache(HTTP_PORT, HTTP_N_REQUESTS, HTTP_REQUEST_SIZE // 10),
    SimpleHttp(HTTP_PORT, HTTP_N_REQUESTS, HTTP_REQUEST_SIZE),
    MiniHttp(HTTP_PORT, HTTP_N_REQUESTS, HTTP_REQUEST_SIZE),
    Lighttpd(HTTP_PORT, HTTP_N_REQUESTS, HTTP_REQUEST_SIZE),
    Nginx(HTTP_PORT, HTTP_N_REQUESTS, HTTP_REQUEST_SIZE),
    # For some reason in wget/curl in ltrace is reallly slow, so we need to run fewer requests.
    HttpClient(
        "curl",
        (result_bin / "curl", "--silent", "--output", "$outfile", "$url"),
        HTTP_PORT,
        HTTP_N_REQUESTS // 10_000,
        HTTP_REQUEST_SIZE,
    ),
    HttpClient(
        "wget",
        (result_bin / "wget", "--quiet", "--output-document", "$outfile", "$url"),
        HTTP_PORT,
        HTTP_N_REQUESTS // 10_000,
        HTTP_REQUEST_SIZE,
    ),
    # HttpClient(
    #     "axel",
    #     (result_bin / "axel", "--output", "$outfile", "$url"),
    #     HTTP_PORT,
    #     HTTP_N_REQUESTS // 100,
    #     HTTP_REQUEST_SIZE,
    # ),
    # Proftpd(HTTP_PORT, 500), # unfortunately, this crashes in ltrace if this number is too big.
    # ltrace will alsosc crash if this number is too big: FtpClient(..., number)
    Proftpd(HTTP_PORT, 500),
    FtpClient(
        "lftp",
        (result_bin / "lftp", "-p", "$port", "-u", "$username,$password", "$host:$port", "-e", "get -c $remote_file -o $dst"),
        HTTP_PORT,
        10,
    ),
    FtpClient("ftp-curl", (result_bin / "curl", "--silent", "--output", "$dst", "$url"), HTTP_PORT, 10),
    FtpClient("ftp-wget", (result_bin / "wget", "--quiet", "--output-document", "$dst", "$url"), HTTP_PORT, 10),
    Postmark(100_000),
    Archive("", SMALLER_TARBALL_URL, 100),
    Archive("gzip", SMALLER_TARBALL_URL, 100),
    Archive("pigz", SMALLER_TARBALL_URL, 100),
    Archive("bzip2", SMALLER_TARBALL_URL, 30),
    Archive("pbzip2", SMALLER_TARBALL_URL, 30),
    Unarchive("", SMALLER_TARBALL_URL, 100),
    Unarchive("gzip", SMALLER_TARBALL_URL, 100),
    Unarchive("pigz", SMALLER_TARBALL_URL, 100),
    Unarchive("bzip2", SMALLER_TARBALL_URL, 100),
    Unarchive("pbzip2", SMALLER_TARBALL_URL, 100),
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
                "sns.barplot(x=\\\"CrossValMeans\\\",y=\\\"Algorithm\\\",data = cv_res, palette=\\\"Set3\\\",orient = \\\"h\\\")",
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
]


all_names = [
    workload.name
    for workload in WORKLOADS
]
for name, count in collections.Counter(all_names).most_common():
    if count > 1:
        raise ValueError(f"{name} is duplicated {count} times")


WORKLOAD_GROUPS: Mapping[str, list[Workload]] = {
    # Singleton groups
    **{
        workload.name: [workload]
        for workload in WORKLOADS
    },

    # Main groups
    **{
        group_name: list(group)
        for group_name, group in groupby_dict(
                WORKLOADS,
                lambda workload: workload.kind,
                lambda workload: workload,
        ).items()
    },

    # Second order groups
    # TODO: try spack boost, other spacks
    "file_servers": [
        workload
        for workload in WORKLOADS
        if workload.kind in {"ftp_server", "http_server"}
    ],
    "all": WORKLOADS,
    "working": [
        workload
        for workload in WORKLOADS
        if workload.name not in {"titanic-to", "select-tcp", "spack spack-repo.mpich", "spack glibc", "spack boost"} and workload.kind not in {"spack"}
    ],
    "working-ltrace": [
        workload
        for workload in WORKLOADS
        if workload.name not in {"titanic-to", "select-tcp", "spack spack-repo.mpich", "spack glibc", "spack boost"} and workload.kind not in {"spack", "ftp_client", "splash-3"}
    ],
    "fast": [
        workload
        for workload in WORKLOADS
        if workload.name not in {"postmark", "titanic-to", "select-tcp", "spack spack-repo.mpich"} and workload.kind not in {"spack", "http_server", "splash-3"}
    ],
    "superfast": [
        workload
        for workload in WORKLOADS
        if workload.kind in {"simple", "python", "gcc"}
    ]
}
