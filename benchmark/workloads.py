import pathlib
import datetime
import dataclasses
import typing
import util
import command
import pwd
import grp
import os


@dataclasses.dataclass(frozen=True)
class Workload:

    labels: typing.Any

    cmd: command.Command

    setup_cmd: command.Command = command.Command(())

    # timeout for the NO provenance case.
    # Provenance collectors will already adjust their own timeout
    timeout: datetime.timedelta | None = datetime.timedelta(minutes=15)


env = command.NixPath(".#coreutils", "/bin/env")
cp = command.NixPath(".#coreutils", "/bin/cp")
rsync = command.NixPath(".#rsync", "/bin/rsync")
make = command.NixPath(".#gnumake", "/bin/make")
bash = (command.NixPath(".#bash", "/bin/bash"), "--noprofile", "--norc", "-e", "-x")
git = command.NixPath(".#git", "/bin/git")
mkdir = command.NixPath(".#coreutils", "/bin/mkdir")
work_dir = command.Placeholder("work_dir")
blast_dir = command.NixPath(".#blast-benchmark")
blast_output = command.Placeholder("work_dir", prefix="OUTPUT=")
test_file = command.Placeholder("work_dir", postfix="/test")
user = pwd.getpwuid(os.getuid()).pw_name
group = grp.getgrgid(os.getgid()).gr_name
this_directory = pathlib.Path(__file__).resolve().parent


def kaggle_workload(
        notebook_name: str,
        timeout: datetime.timedelta = datetime.timedelta(minutes=15),
) -> Workload:
    return Workload(
            (("app", "kaggle", notebook_name), ("data science", "")),
            command.Command((
                env,
                blast_output,
                command.NixPath(".#kaggle-notebook-env", "/bin/jupyter"),
                "nbconvert",
                "--execute",
                "--to=notebook",
                command.NixPath(f".#kaggle-notebook-{notebook_name}"),
                "--output",
                command.Placeholder("work_dir", postfix="/notebook.ipynb"),
            )),
            timeout=timeout,
        )


def lmbench_workload(
        type: str,
        workload_name: str,
        bin_name: str,
        args: tuple[str | command.Placeholder, ...],
        create_file_size: int | None = None,
) -> Workload:
    return Workload(
        (("microbench", "lmbench", workload_name), ("sys", type)),
        command.Command((
            env,
            "ENOUGH=1000000",
            "TIMING_O=0",
            "LOOP_O=0.000013",
            command.NixPath(".#lmbench", f"/bin/{bin_name}"),
            *args,
            *((test_file,) if create_file_size else ())
        )),
        command.Command(
            (
                command.NixPath(".#coreutils", "/bin/dd"),
                "if=/dev/zero",
                dataclasses.replace(test_file, prefix="of="),
                f"bs={create_file_size}",
                "count=1",
            )
            if create_file_size else ()
        ),
    )


http_port = 49284


http_n_requests = 200000


http_size = 4096


apache_http_conf = '''
ServerRoot $HTTPD_ROOT
PidFile $HTTPD_ROOT/httpd.pid
ErrorLog $HTTPD_ROOT/errors.log
ServerName localhost
Listen $PORT
LoadModule mpm_event_module $APACHE_MODULES_PATH/mod_mpm_event.so
LoadModule unixd_module $APACHE_MODULES_PATH/mod_unixd.so
LoadModule authz_core_module $APACHE_MODULES_PATH/mod_authz_core.so
DocumentRoot $SRV_ROOT
'''

workloads = [
    # Workload(
    #     (("app", "blast", "tblastx"), ("cse", "multiomics")),
    #     command.Command((make, "-C", blast_dir, "tblastx", blast_output)),
    # ),
    Workload(
        (("app", "blast", "tblastn"), ("cse", "multiomics")),
        command.Command((make, "-C", blast_dir, "tblastn", blast_output)),
    ),
    Workload(
        (("app", "blast", "blastx"), ("cse", "multiomics")),
        command.Command((make, "-C", blast_dir, "blastx", blast_output)),
    ),
    Workload(
        (("app", "blast", "blastn"), ("cse", "multiomics")),
        command.Command((make, "-C", blast_dir, "blastn", blast_output)),
    ),
    Workload(
        (("app", "blast", "blastp"), ("cse", "multiomics")),
        command.Command((make, "-C", blast_dir, "blastp", blast_output)),
    ),
    Workload(
        (("app", "blast", "megablast"), ("cse", "multiomics")),
        command.Command((make, "-C", blast_dir, "megablast", blast_output)),
    ),
    # TODO: fix
    # Workload(
    #     (("app", "blast", "idx_megablast"), ("cse", "multiomics")),
    #     command.Command((make, "-C", blast_dir, "idx_megablast", blast_output)),
    # ),
    lmbench_workload("syscall", "syscall", "lat_syscall", ("-N", "3", "null")),
    lmbench_workload("file io", "read", "lat_syscall", ("-N", "3", "read")),
    lmbench_workload("file io", "write", "lat_syscall", ("-N", "3", "write")),
    lmbench_workload("file io", "stat", "lat_syscall", ("-N", "3", "stat"), 1024),
    lmbench_workload("file io", "fstat", "lat_syscall", ("-N", "3", "fstat"), 1024),
    lmbench_workload("file io", "open/close", "lat_syscall", ("-N", "3", "open"), 1024),
    lmbench_workload("proc"   , "fork", "lat_proc", ("-N", "3", "fork")),
    lmbench_workload("proc"   , "exec", "lat_proc", ("-N", "3", "exec")),
    lmbench_workload("proc"   , "shell", "lat_proc", ("-N", "3", "shell")),
    lmbench_workload("proc"   , "shell", "lat_proc", ("-N", "3", "procedure")),
    lmbench_workload("proc"   , "install-signal", "lat_sig", ("-N", "3", "install")),
    lmbench_workload("proc"   , "catch-signal", "lat_sig", ("-N", "1", "catch")),
    lmbench_workload("proc"   , "protection-fault", "lat_sig", ("-N", "1", "prot"), 1024 * 1024 * 8),
    lmbench_workload("file io", "select-file", "lat_select", ("-n", "100", "-N", "3", "file")),
    lmbench_workload("net io" , "select-tcp", "lat_select", ("-n", "100", "-N", "3", "tcp")),
    lmbench_workload("file io", "read-bandwidth", "bw_file_rd", ("-N", "1", "1M", "io_only"), 1024),
    # Note that `bw_file_rd open2close` should be a linear combination of `bw_file_rd io_only` + `lat_syscall open`
    lmbench_workload("file io", "pipe-read/write", "bw_pipe", ("-N", "1")),
    # Note that bw_unix is substantially similar to bw_pipe, except both ends to read and write.
    lmbench_workload("file io", "create/delete", "lat_fs", ("-s", "1", "-N", "1", work_dir)),
    kaggle_workload("titanic-0"),
    kaggle_workload("titanic-1"),
    kaggle_workload("house-prices-0"),
    # kaggle_workload("house-prices-1", datetime.timedelta(minutes=60)),
    Workload(
        (("microbench", "postmark", "postmark"), ("sys", "file io")),
        command.Command((
            *bash,
            "-c",
            command.NixPath(".#postmark", postfix="/bin/postmark", prefix="echo -e 'set transactions 100000\nrun\nquit\n' | "),
        )),
    ),
    Workload(
        (("app", "compile", "huggingface/transformers"), ("ml", "")),
        command.Command((command.NixPath(".#transformers-python", "/bin/python"), "setup.py", "bdist_wheel")),
        command.Command((rsync, "--archive", "--chmod", "700", "--chown", f"{user}:{group}", command.NixPath(".#transformers-src", postfix="/"), work_dir)),
    ),
    # Workload(
    #     (("app", "compile", "tesseract-ocr"), ("ml", "")),
    #     command.Command((
    #         env,
    #         command.NixPath(".#tesseract-env", postfix="/bin", prefix="PATH="),
    #         command.NixPath(".#pkg-config", postfix="/share/aclocal", prefix="ACLOCAL_PATH="),
    #         command.NixPath(".#tesseract-env", "/bin/bash"),
    #         "-c",
    #         "\n".join([
    #             # ./autogen.sh doesn't work, because pkg-config is in a non-default path
    #             "env_path=$(dirname $(dirname $(which bash)))",
    #             "export LIBLEPT_HEADERSDIR=$env_path/include",
    #             "export LIBLEPT_LIBDIR=$env_path/lib",
    #             "export PKG_CONFIG_PATH=$env_path/lib/pkgconfig",
    #             "mkdir -p config",
    #             "aclocal -I config",
    #             "libtoolize -f -c",
    #             "libtoolize --automake",
    #             "aclocal -I config",
    #             "autoconf -I$ACLOCAL_PATH",
    #             "autoheader -f",
    #             "automake --add-missing --copy --warnings=all",
    #             "./configure --with-extra-libraries=$LIBLEPT_LIBDIR",
    #             "make CPPFLAGS=\"-I$env_path/include/ -I$env_path/include/leptonica\"",
    #         ]),
    #     )),
    #     command.Command((rsync, "--archive", "--chmod", "700", "--chown", f"{user}:{group}", command.NixPath(".#tesseract-src", postfix="/"), work_dir)),
    #     timeout=datetime.timedelta(minutes=60),
    # ),
    Workload(
        (("app", "compile", "sextractor"), ("cse", "astro")),
        command.Command((
            env,
            command.NixPath(".#sextractor-env", postfix="/bin", prefix="PATH="),
            command.NixPath(".#sextractor-env", "/bin/bash"),
            "-c",
            "\n".join([
                # ./autogen.sh doesn't work, because pkg-config is in a non-default path
                "env_path=$(dirname $(dirname $(which bash)))",
                "export PKG_CONFIG_PATH=$env_path/lib/pkgconfig",
                "sh autogen.sh",
                'export CPPFLAGS="-I$env_path/include -L$env_path/lib"',
                'export LDFLAGS="-L$env_path/lib"',
                # Nix's FFTW doesn't have fftwf_execute
                "./configure --disable-model-fitting",
                "make",
            ]),
        )),
        command.Command((rsync, "--archive", "--chmod", "700", "--chown", f"{user}:{group}", command.NixPath(".#sextractor-src", postfix="/"), work_dir)),
        timeout=datetime.timedelta(minutes=60),
    ),
    Workload(
        (("app", "http", "apache"), ("sys", "server")),
        command.Command((
            command.NixPath(".#http-load-test", "/bin/http-load-test"),
            str(http_n_requests),
            f"http://localhost:{http_port}/test",
            command.NixPath(".#apacheHttpd", "/bin/httpd"),
            "-k",
            "start",
            "-f",
            test_file,
            "-X",
        )),
        command.Command((
            env,
            command.NixPath(".#coreutils", postfix="/bin", prefix="PATH="),
            command.Placeholder("work_dir", postfix="", prefix="HTTPD_ROOT="),
            command.Placeholder("work_dir", postfix="/srv", prefix="SRV_ROOT="),
            command.NixPath(".#apacheHttpd", postfix="/modules", prefix="APACHE_MODULES_PATH="),
            f"PORT={http_port}",
            *bash,
            "-c",
            "\n".join([
                f"echo \"{apache_http_conf}\" > $HTTPD_ROOT/test",
                "mkdir $SRV_ROOT",
                f"dd if=/dev/zero of=$SRV_ROOT/test.txt bs=1k count={http_size} > $SRV_ROOT/test",
            ]),
        )),
    ),
    Workload(
        (("app", "quantum-espresso", "ph-01"), ("cse", "comp-chem")),
        command.Command((
            env,
            command.NixPath(".#quantum-espresso-env", prefix="PATH=", postfix="/bin"),
            command.Placeholder("work_dir", prefix="HOME="),
            *bash,
            str(this_directory / "quantum-espresso/ph-01/main.sh"),
        ))
    ),
    Workload(
        (("app", "quantum-espresso", "pw-01"), ("cse", "comp-chem")),
        command.Command((
            env,
            command.NixPath(".#quantum-espresso-env", prefix="PATH=", postfix="/bin"),
            command.Placeholder("work_dir", prefix="HOME="),
            *bash,
            str(this_directory / "quantum-espresso/pw-01/main.sh"),
        ))
    ),
    Workload(
        (("app", "quantum-espresso", "pp-01"), ("cse", "comp-chem")),
        command.Command((
            env,
            command.NixPath(".#quantum-espresso-env", prefix="PATH=", postfix="/bin"),
            command.NixPath(".#gnuplot", prefix="gnuplot=", postfix="/bin/gnuplot"),
            command.Placeholder("work_dir", prefix="HOME="),
            *bash,
            str(this_directory / "quantum-espresso/pp-01/main.sh"),
        ))
    ),
    Workload(
        (("app", "umap", "umap"), ("cse", "ml")),
        command.Command((
            command.NixPath(".#kaggle-notebook-env", "/bin/python"),
            str(this_directory / "umap/plot_algorithms.py"),
        )),
    ),
    Workload(
        (("app", "hdbscan", "hdbscan"), ("cse", "ml")),
        command.Command((
            command.NixPath(".#kaggle-notebook-env", "/bin/python"),
            str(this_directory / "hdbscan/plot_cluster_comparison.py"),
        )),
    ),
]


WORKLOAD_GROUPS = {
    **util.groupby_dict(workloads, lambda workload: workload.labels[0][0], util.identity),
    **util.groupby_dict(workloads, lambda workload: workload.labels[0][1], util.identity),
    **util.groupby_dict(workloads, lambda workload: workload.labels[0][2], util.identity),
    **util.groupby_dict(workloads, lambda workload: workload.labels[1][0], util.identity),
    **util.groupby_dict(workloads, lambda workload: workload.labels[1][1], util.identity),
    "all": workloads,
    "all-but-ph": [
        workload
        for workload in workloads
        if workload.labels[0][1] not in {"quantum-espresso", "http"} and workload.labels[0][2] != "huggingface/transformers"
    ],
    "fast": [
        workload
        for workload in workloads
        if workload.labels[0][1] not in {"blast"} and workload.labels[0][2] not in {"house-prices-1"}
    ],
    "working-app": [
        workload
        for workload in workloads
        if workload.labels[0][0] in {"app"} and workload.labels[0][2] not in {"house-prices-1"}
    ],
}
