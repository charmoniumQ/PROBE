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


def cmd(
    *args: str | command.NixAttr | command.Variable | command.Combo,
) -> command.Command:
    return command.Command(args)

def nix(attr: str) -> command.NixAttr:
    return command.NixAttr(attr)

def var(name: str) -> command.Variable:
    return command.Variable(name)

def combine(
    *args: str | command.Variable | command.NixAttr | pathlib.Path,
) -> command.Combo:
    return command.Combo(args)

def nix_path(attr: str, path: str) -> command.Combo:
    return command.Combo((command.NixAttr(attr), path))

def nix_env_path(attrs: typing.Sequence[str]) -> command.Combo:
    return command.Combo((
        "PATH=",
        *util.flatten1([  # type: ignore
            (
                nix(attr),
                "/bin:",
            )
            for attr in attrs
        ]),
    ))


env = nix_path(".#coreutils", "/bin/env")
output_equals_output = combine("OUTPUT=", var("work_dir"))
test_file = combine(var("work_dir"), "/test")
bash = (nix_path(".#bash", "/bin/bash"), "--noprofile", "--norc", "-e", "-x")
cp = nix_path(".#coreutils", "/bin/cp")
rsync = nix_path(".#rsync", "/bin/rsync")
make = nix_path(".#gnumake", "/bin/make")
mkdir = nix_path(".#coreutils", "/bin/mkdir")
work_dir = var("work_dir")
blast_dir = nix(".#blast-benchmark")
repeat = nix_path(".#repeat", "/bin/repeat")
user = pwd.getpwuid(os.getuid()).pw_name
group = grp.getgrgid(os.getgid()).gr_name
bin_repetitions = 1000
calibration_ratio = 10000


def kaggle_workload(
        notebook_name: str,
        timeout: datetime.timedelta = datetime.timedelta(minutes=15),
) -> Workload:
    return Workload(
        (("app", "kaggle", notebook_name), ("data science", "")),
        cmd(
            env,
            output_equals_output,
            nix_path(".#kaggle-notebook-env", "/bin/jupyter"),
            "nbconvert",
            "--execute",
            "--to=notebook",
            nix(f".#kaggle-notebook-{notebook_name}"),
            "--output",
            combine(var("work_dir"), "/notebook.ipynb"),
        ),
        timeout=timeout,
    )


def lmbench_workload(
        type: str,
        workload_name: str,
        bin_name: str,
        args: tuple[str | command.Combo | command.Variable | command.NixAttr, ...],
        create_file_size: int | None = None,
        enough: int = 3000000,
) -> Workload:
    return Workload(
        (("microbench", "lmbench", workload_name), ("sys", type)),
        cmd(
            env,
            f"ENOUGH={enough}",
            "TIMING_O=0",
            "LOOP_O=0.000013",
            nix_path(".#lmbench", f"/bin/{bin_name}"),
            *args,
            *((test_file,) if create_file_size else ())
        ),
        cmd(
            nix_path(".#coreutils", "/bin/dd"),
            "if=/dev/zero",
            combine("of=", var("work_dir"), "/test"),
            f"bs={create_file_size}",
            "count=1",
        ) if create_file_size else cmd(),
    )


http_port = 49284


http_n_requests = 2000000


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

WORKLOADS = [
    Workload(
        (("app", "blast", "tblastx"), ("cse", "multiomics")),
        cmd(make, "-C", blast_dir, "tblastx", output_equals_output),
    ),
    Workload(
        (("app", "blast", "tblastn"), ("cse", "multiomics")),
        cmd(make, "-C", blast_dir, "tblastn", output_equals_output),
    ),
    Workload(
        (("app", "blast", "blastx"), ("cse", "multiomics")),
        cmd(make, "-C", blast_dir, "blastx", output_equals_output),
    ),
    Workload(
        (("app", "blast", "blastn"), ("cse", "multiomics")),
        cmd(make, "-C", blast_dir, "blastn", output_equals_output),
    ),
    Workload(
        (("app", "blast", "blastp"), ("cse", "multiomics")),
        cmd(make, "-C", blast_dir, "blastp", output_equals_output),
    ),
    Workload(
        (("app", "blast", "megablast"), ("cse", "multiomics")),
        cmd(make, "-C", blast_dir, "megablast", output_equals_output),
    ),
    # TODO: fix
    # Workload(
    #     (("app", "blast", "idx_megablast"), ("cse", "multiomics")),
    #     command.Command((make, "-C", blast_dir, "idx_megablast", output_equals_output)),
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
    # This was hanging for some reason
    #lmbench_workload("proc"   , "hello", "lat_cmd", ("-N", "1", nix_path(".#coreutils", "/bin/hello")), enough=2000),
    Workload(
        (("bench", "utils", "hello"), ("sys", "proc")),
        cmd(
            repeat,
            str(bin_repetitions * 30),
            nix_path(".#hello", "/bin/hello"),
        ),
    ),
    Workload(
        (("bench", "utils", "ls"), ("sys", "proc")),
        cmd(
            repeat,
            str(bin_repetitions * 20),
            nix_path(".#coreutils", "/bin/ls"),
        ),
    ),
    Workload(
        (("bench", "utils", "true"), ("sys", "proc")),
        cmd(
            repeat,
            str(bin_repetitions * 20),
            nix_path(".#coreutils", "/bin/true")
        ),
    ),
    Workload(
        (("bench", "utils", "python noop"), ("sys", "proc")),
        cmd(
            repeat,
            str(bin_repetitions // 2),
            nix_path(".#kaggle-notebook-env", "/bin/python"),
            "-c",
            "",
        ),
    ),
    Workload(
        (("bench", "utils", "bash noop"), ("sys", "proc")),
        cmd(
            repeat,
            str(bin_repetitions * 20),
            nix_path(".#bash", "/bin/bash"),
            "-c",
            "",
        ),
    ),
    Workload(
        (("bench", "big-calib", "small-hello"), ("sys", "proc")),
        cmd(
            repeat,
            str(calibration_ratio),
            nix_path(".#small-hello", "/bin/small-hello"),
        ),
    ),
    # The point of hello & cp is to measure
    # I don't think we actually need cp to be in big calib, since we already have hello
    # Workload(
    #     (("bench", "big-calib", "cp"), ("sys", "proc")),
    #     cmd(
    #         repeat,
    #         str(calibration_ratio),
    #         nix_path(".#coreutils", "/bin/cp"),
    #         combine(var("work_dir"), "/test0"),
    #         combine(var("work_dir"), "/test1"),
    #     ),
    #     cmd(
    #         nix_path(".#write-file", "/bin/write-file"),
    #         "hello world",
    #         combine(var("work_dir"), "/test0"),
    #     ),
    # ),
    Workload(
        (("bench", "small-calib", "1-small-hello"), ("sys", "proc")),
        cmd(nix_path(".#small-hello", "/bin/small-hello")),
    ),
    Workload(
        (("bench", "small-calib", "1-cp"), ("sys", "proc")),
        cmd(
            nix_path(".#coreutils", "/bin/cp"),
            combine(var("work_dir"), "/test0"),
            combine(var("work_dir"), "/test1"),
        ),
        cmd(
            nix_path(".#write-file", "/bin/write-file"),
            "hello world",
            combine(var("work_dir"), "/test0"),
        ),
    ),

    # lmbench_workload("proc"   , "shell", "lat_proc", ("-N", "3", "procedure")),
    # lmbench_workload("proc"   , "install-signal", "lat_sig", ("-N", "3", "install")),
    # lmbench_workload("proc"   , "catch-signal", "lat_sig", ("-N", "1", "catch")),
    # lmbench_workload("proc"   , "protection-fault", "lat_sig", ("-N", "1", "prot"), 1024 * 1024 * 8),
    # lmbench_workload("file io", "select-file", "lat_select", ("-n", "100", "-N", "3", "file")),
    # lmbench_workload("net io" , "select-tcp", "lat_select", ("-n", "100", "-N", "3", "tcp")),
    # lmbench_workload("file io", "read-bandwidth", "bw_file_rd", ("-N", "1", "1M", "io_only"), 1024),
    # Note that `bw_file_rd open2close` should be a linear combination of `bw_file_rd io_only` + `lat_syscall open`
    # lmbench_workload("file io", "pipe-read/write", "bw_pipe", ("-N", "1")),
    # Note that bw_unix is substantially similar to bw_pipe, except both ends to read and write.
    lmbench_workload("file io", "create/delete", "lat_fs", ("-s", "1", "-N", "1", work_dir)),
    kaggle_workload("titanic-0"),
    kaggle_workload("titanic-1"),
    kaggle_workload("house-prices-0"),
    kaggle_workload("house-prices-1", datetime.timedelta(minutes=60)),
    Workload(
        (("microbench", "postmark", "postmark2"), ("sys", "file io")),
        cmd(
            nix_path(".#echo-pipe", "/bin/echo-pipe"),
            "set transactions 100000\nrun\nquit\n",
            nix_path(".#postmark", "/bin/postmark"),
        ),
    ),
    Workload(
        (("app", "compile", "huggingface/transformers"), ("ml", "")),
        cmd(nix_path(".#transformers-python", "/bin/python"), "setup.py", "bdist_wheel"),
        cmd(rsync, "--archive", "--chmod", "700", "--chown", f"{user}:{group}", nix_path(".#transformers-src", "/"), work_dir),
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
        cmd(
            env,
            nix_env_path([".#sextractor-env"]),
            combine("env_path=", nix(".#sextractor-env")),
            nix_path(".#sextractor-env", "/bin/bash"),
            "-c",
            "\n".join([
                # ./autogen.sh doesn't work, because pkg-config is in a non-default path
                "export PKG_CONFIG_PATH=$env_path/lib/pkgconfig",
                "sh autogen.sh",
                'export CPPFLAGS="-I$env_path/include -L$env_path/lib"',
                'export LDFLAGS="-L$env_path/lib"',
                # Nix's FFTW doesn't have fftwf_execute
                "./configure --disable-model-fitting",
                "make",
            ]),
        ),
        cmd(rsync, "--archive", "--chmod=700", f"--chown={user}:{group}", combine(nix(".#sextractor-src"), "/"), work_dir),
        timeout=datetime.timedelta(minutes=60),
    ),
    Workload(
        (("app", "http", "apache"), ("sys", "server")),
        cmd(
            nix_path(".#http-load-test", "/bin/http-load-test"),
            str(http_n_requests),
            f"http://localhost:{http_port}/test",
            nix_path(".#apacheHttpd", "/bin/httpd"),
            *("-k", "start", "-f", test_file, "-X"),
        ),
        cmd(
            env,
            combine("COREUTILS=", nix(".#coreutils")),
            combine("HTTPD_ROOT=", var("work_dir")),
            combine("SRV_ROOT=", var("work_dir"), "/srv"),
            combine("APACHE_MODULES_PATH=", nix(".#apacheHttpd"), "/modules"),
            f"PORT={http_port}",
            *bash,
            "-c",
            "\n".join([
                f"echo \"{apache_http_conf}\" > $HTTPD_ROOT/test",
                "$COREUTILS/bin/mkdir $SRV_ROOT",
                f"$COREUTILS/bin/dd if=/dev/zero of=$SRV_ROOT/test.txt bs=1k count={http_size} > $SRV_ROOT/test",
            ]),
        ),
    ),
    Workload(
        (("app", "quantum-espresso1", "ph-01"), ("cse", "comp-chem")),
        cmd(
            env,
            nix_env_path([".#quantum-espresso-env", ".#coreutils"]),
            combine("HOME=", var("work_dir")),
            output_equals_output,
            *bash,
            nix_path(".#quantum-espresso-scripts", "/ph-01/main.sh"),
        ),
    ),
    Workload(
        (("app", "quantum-espresso1", "pw-01"), ("cse", "comp-chem")),
        cmd(
            env,
            nix_env_path([".#quantum-espresso-env", ".#coreutils"]),
            combine("HOME=", var("work_dir")),
            output_equals_output,
            *bash,
            nix_path(".#quantum-espresso-scripts", "/pw-01/main.sh"),
        ),
    ),
    Workload(
        (("app", "quantum-espresso1", "pp-01"), ("cse", "comp-chem")),
        cmd(
            env,
            nix_env_path([".#quantum-espresso-env", ".#coreutils"]),
            combine("HOME=", var("work_dir")),
            output_equals_output,
            *bash,
            nix_path(".#quantum-espresso-scripts", "/pw-01/main.sh"),
        ),
    ),
    Workload(
        (("app", "data-sci", "umap"), ("cse", "ml")),
        cmd(
            nix_path(".#kaggle-notebook-env", "/bin/python"),
            nix_path(".#data-science", "/umap_plot_algorithms.py"),
        ),
    ),
    Workload(
        (("app", "data-sci", "hdbscan"), ("cse", "ml")),
        cmd(
            env,
            combine("HOME=", work_dir),
            nix_path(".#kaggle-notebook-env", "/bin/python"),
            nix_path(".#data-science", "/hdbscan_plot_cluster_comparison.py"),
        ),
    ),
    Workload(
        (("app", "data-sci", "plot-simple"), ("cse", "ml")),
        cmd(
            nix_path(".#kaggle-notebook-env", "/bin/python"),
            nix_path(".#data-science", "/plot_simple.py"),
        ),
    ),
    Workload(
        (("app", "data-sci", "imports"), ("cse", "ml")),
        cmd(
            env,
            combine("HOME=", work_dir),
            nix_path(".#kaggle-notebook-env", "/bin/python"),
            "-c",
            "\n".join([
                "import pandas",
                "import tqdm",
                "import notebook",
                "import seaborn",
                "import scipy",
                "import sklearn",
                "import xgboost",
                "import lightgbm",
                "import numpy",
                "import umap",
                "import hdbscan",
            ]),
        ),
    ),
    Workload(
        (("app", "astropy", "astro-pvd"), ("cse", "astro")),
        cmd(
            env,
            output_equals_output,
            nix_path(".#astropy-env", "/bin/jupyter"),
            "nbconvert",
            "--execute",
            "--to=notebook",
            nix(".#astropy-pvd"),
            "--output",
            combine(var("work_dir"), "/notebook.ipynb"),
        ),
    ),
    Workload(
        (("bench", "splash3", "barnes"), ("bench", "cpu")),
        cmd(
            nix_path(".#uncat", "/bin/uncat"),
            nix_path(".#splash3", "/inputs/barnes/n16384-p1"),
            nix_path(".#splash3", "/bin/BARNES"),
        )
    ),
    Workload(
        (("bench", "splash3", "fmm"), ("bench", "cpu")),
        cmd(
            nix_path(".#echo-pipe", "/bin/echo-pipe"),
            "two cluster\nplummer\n262144\n1e-6\n1\n5\n.025\n0.0\ncost zones",
            nix_path(".#splash3", "/bin/FMM"),
        ),
    ),
    Workload(
        (("bench", "splash3", "ocean"), ("bench", "cpu")),
        cmd(
            nix_path(".#splash3", "/bin/OCEAN"),
            *("-n2050", "-p1"),
        ),
    ),
    Workload(
        (("bench", "splash3", "radiosity"), ("bench", "cpu")),
        cmd(
            nix_path(".#splash3", "/bin/RADIOSITY"),
            *("-p", "1", "-room", "-batch", "-ae", "50000"),
        ),
    ),
    Workload(
        (("bench", "splash3", "raytrace"), ("bench", "cpu")),
        cmd(
            nix_path(".#splash3", "/bin/RAYTRACE"),
            *("-a100", "-p1", "-m512", nix_path(".#splash3", "/inputs/raytrace/car.env")),
        ),
    ),
    Workload(
        (("bench", "splash3", "volrend"), ("bench", "cpu")),
        cmd(
            nix_path(".#splash3", "/bin/VOLREND"),
            "1",
            combine(var("work_dir"), "/head"),
            "128",
        ),
        cmd(
            cp,
            nix_path(".#splash3", "/inputs/volrend/head.den"),
            work_dir
        ),
    ),
    Workload(
        (("bench", "splash3", "water-nsquared"), ("bench", "cpu")),
        cmd(
            nix_path(".#echo-pipe", "/bin/echo-pipe"),
            "  1.5e-16   512  100   6\n 1      3000     3  0\n1 6.212752",
            nix_path(".#splash3", "/bin/WATER-NSQUARED")
        ),
    ),
    Workload(
        (("bench", "splash3", "water-spatial"), ("bench", "cpu")),
        cmd(
            nix_path(".#echo-pipe", "/bin/echo-pipe"),
            "  1.5e-16   512  7   6\n 1      3000     3  0\n1 6.212752",
            nix_path(".#splash3", "/bin/WATER-SPATIAL")
        ),
    ),
    Workload(
        (("bench", "splash3", "cholesky"), ("bench", "cpu")),
        cmd(
            repeat,
            "300",
            nix_path(".#uncat", "/bin/uncat"),
            nix_path(".#splash3", "/inputs/cholesky/tk15.O"),
            nix_path(".#splash3", "/bin/CHOLESKY"),
        ),
    ),
    Workload(
        (("bench", "splash3", "fft"), ("bench", "cpu")),
        cmd(
            nix_path(".#splash3", "/bin/FFT"),
            *("-m26", "-p1", "-n65536", "-l4"),
        ),
    ),
    Workload(
        (("bench", "splash3", "lu"), ("bench", "cpu")),
        cmd(
            nix_path(".#splash3", "/bin/LU"),
            *("-p1", "-n2048"),
        ),
    ),
    Workload(
        (("bench", "splash3", "radix"), ("bench", "cpu")),
        cmd(
            nix_path(".#splash3", "/bin/RADIX"),
            *("-p1", "-n134217728"),
        ),
    ),
    Workload(
        (("bench", "rsync", "rsync-linux"), ("bench", "io")),
        cmd(
            rsync,
            "--archive",
            "--chmod=700",
            f"--chown={user}:{group}",
            nix(".#linux-src"),
            work_dir,
        ),
    ),
    Workload(
        (("bench", "shell", "shell-cd"), ("bench", "io")),
        cmd(
            env,
            output_equals_output,
            nix_env_path([".#coreutils"]),
            *bash,
            "-c",
            "for i in $(seq 100000); do cd $OUTPUT/test0; true; cd $OUTPUT/test1; done",
        ),
        cmd(
            mkdir,
            combine(var("work_dir"), "/test0"),
            combine(var("work_dir"), "/test1"),
        ),
    ),
    Workload(
        (("bench", "tar", "tar-linux"), ("bench", "io")),
        cmd(
            nix_path(".#un-archive-env", "/bin/tar"),
            "--create",
            combine("--file=", var("work_dir"), "/test.tar"),
            combine("--directory=", nix(".#linux-src")),
            ".",
        ),
    ),
    Workload(
        (("bench", "tar", "untar-linux"), ("bench", "io")),
        cmd(
            repeat,
            "1000",
            nix_path(".#un-archive-env", "/bin/tar"),
            combine("--directory=", var("work_dir")),
            "--extract",
            combine("--file=", nix(".#linux-src-tar")),
        ),
    ),
    Workload(
        (("test", "test", "failing",), ("a", "b")),
        cmd(
            *bash,
            "-c",
            "false",
        ),
    )
]


WORKLOAD_GROUPS = {
    **util.groupby_dict(WORKLOADS, lambda workload: workload.labels[0][0], util.identity),
    **util.groupby_dict(WORKLOADS, lambda workload: workload.labels[0][1], util.identity),
    **util.groupby_dict(WORKLOADS, lambda workload: workload.labels[0][2], util.identity),
    **util.groupby_dict(WORKLOADS, lambda workload: workload.labels[1][0], util.identity),
    **util.groupby_dict(WORKLOADS, lambda workload: workload.labels[1][1], util.identity),
    "all": WORKLOADS,
    "run-for-usenix2": [
        workload
        for workload in WORKLOADS
        if workload.labels[0][-1] not in {"megablast", "tblastn", "blastx", "pp-01", "blastn", "pw-01", "house-prices-1", "umap", "apache"}
    ],
    "run-for-usenix": [
        workload
        for workload in WORKLOADS
        if workload.labels[0][-1] not in {"megablast", "tblastn", "blastx", "pp-01", "blastn", "pw-01", "house-prices-1", "umap"}
    ],
    "fast": [
        workload
        for workload in WORKLOADS
        if workload.labels[0][2] not in {
                "house-prices-1",  # too long
                "water-spatial", # too long or short (not easy to callibrate)
                "sextractor", # Stalls out for some reason
                "ph-01", # too long
                "barnes", # never worked
                "tblastx", # too long
                "rsync-linux", # somehow this is really slow and fails in Bubblewrap
                "megablast", # not super long, but still longer than I'd like
                "blastx", # ditto
                "blastp",
                "blastn",
                "tblastn",
                "untar-linux", # broken
        }
    ],
}
