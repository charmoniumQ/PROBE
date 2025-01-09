import datetime
import dataclasses
import typing
import util
import command


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
make = command.NixPath(".#gnumake", "/bin/make")
mkdir = command.NixPath(".#coreutils", "/bin/mkdir")
work_dir = command.Placeholder("work_dir")
blast_dir = command.NixPath(".#blast-benchmark")
blast_output = command.Placeholder("work_dir", prefix="OUTPUT=")
test_file = command.Placeholder("work_dir", postfix="/test")
def create_file_cmd(size: int, file: command.Placeholder) -> command.Command:
    return command.Command((
        command.NixPath(".#coreutils", "/bin/dd"),
        "if=/dev/zero",
        dataclasses.replace(file, prefix="of="),
        f"bs={size}",
        "count=1",
    ))


def kaggle_workload(notebook_name: str) -> Workload:
    return Workload(
            (("app", "kaggle", notebook_name), ("data science", "")),
            command.Command((
                command.NixPath(".#kaggle-notebook-env", "/bin/jupyter"),
                "nbconvert",
                "--execute",
                "--to=notebook",
                command.NixPath(f".#kaggle-notebook-{notebook_name}"),
                command.Placeholder("work_dir", postfix="/notebook.ipynb"),
            )),
        )


workloads = [
    Workload(
        (("app", "blast", "tblastx"), ("cse", "multiomics")),
        command.Command((make, "-C", blast_dir, "tblastx", blast_output)),
    ),
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
    Workload(
        (("microbench", "lmbench", "getppid"), ("sys", "syscall")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_syscall"),
            "-N",
            "300",
            "null",
        )),
    ),
    Workload(
        (("microbench", "lmbench", "read"), ("sys", "file io")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_syscall"),
            "-N",
            "300",
            "read",
        )),
    ),
    Workload(
        (("microbench", "lmbench", "write"), ("sys", "file io")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_syscall"),
            "-N",
            "300",
            "write",
        )),
    ),
    Workload(
        (("microbench", "lmbench", "stat"), ("sys", "file io")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_syscall"),
            "-N",
            "300",
            "stat",
            test_file,
        )),
        create_file_cmd(1024, test_file),
    ),
    Workload(
        (("microbench", "lmbench", "fstat"), ("sys", "file io")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_syscall"),
            "-N",
            "300",
            "fstat",
            test_file,
        )),
        create_file_cmd(1024, test_file),
    ),
    Workload(
        (("microbench", "lmbench", "open/close"), ("sys", "file io")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_syscall"),
            "-N",
            "300",
            "open",
            test_file,
        )),
        create_file_cmd(1024, test_file),
    ),
    Workload(
        (("microbench", "lmbench", "fork"), ("sys", "proc")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_proc"),
            "-N",
            "300",
            "fork",
        )),
        create_file_cmd(1024, test_file),
    ),
    Workload(
        (("microbench", "lmbench", "exec"), ("sys", "proc")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_proc"),
            "-N",
            "300",
            "exec",
        )),
        create_file_cmd(1024, test_file),
    ),
    Workload(
        (("microbench", "lmbench", "shell"), ("sys", "proc")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_proc"),
            "-N",
            "300",
            "shell",
        )),
        create_file_cmd(1024, test_file),
    ),
    Workload(
        (("microbench", "lmbench", "install-signal"), ("sys", "proc")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_sig"),
            "-N",
            "300",
            "install",
        )),
    ),
    Workload(
        (("microbench", "lmbench", "catch-signal"), ("sys", "proc")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_sig"),
            "-N",
            "100",
            "catch",
        )),
    ),
    Workload(
        (("microbench", "lmbench", "protection-fault"), ("sys", "proc")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_sig"),
            "-N",
            "100",
            "prot",
            test_file,
        )),
        create_file_cmd(8 * 1024 * 1024, test_file),
    ),
    Workload(
        (("microbench", "lmbench", "select-file"), ("sys", "file io")),
        command.Command((
            env,
            "--chdir",
            work_dir,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_select"),
            "-n",
            "100",
            "-N"
            "300",
            "file",
        )),
    ),
    Workload(
        (("microbench", "lmbench", "select-tcp"), ("sys", "net io")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_select"),
            "-n",
            "100",
            "-N"
            "300",
            "tcp",
        )),
        create_file_cmd(1024, test_file),
    ),
    Workload(
        (("microbench", "lmbench", "read_bandwidth"), ("sys", "file io")),
        command.Command((
            env,
            command.NixPath(".#lmbench", "/bin/bw_file_rd"),
            "-N",
            "10",
            "1M",
            "io_only",
            test_file,
        )),
        create_file_cmd(1024, test_file),
    ),
    Workload(
        (("microbench", "lmbench", "unix_bandwidth"), ("sys", "file io")),
        command.Command((
            command.NixPath(".#lmbench", "/bin/bw_unix"),
            "-N",
            "1",
            test_file,
        )),
        create_file_cmd(1024, test_file),
    ),
    Workload(
        (("microbench", "lmbench", "pipe_bandwidth"), ("sys", "file io")),
        command.Command((
            command.NixPath(".#lmbench", "/bin/bw_unix"),
            "-N",
            "1",
            test_file,
        )),
        create_file_cmd(1024, test_file),
    ),
    Workload(
        (("microbench", "lmbench", "fs latency"), ("sys", "file io")),
        command.Command((
            env,
            "ENOUGH=10000",
            command.NixPath(".#lmbench", "/bin/lat_fs"),
            "-N",
            "10",
            test_file,
        )),
        create_file_cmd(1024, test_file),
    ),
    kaggle_workload("titanic-0"),
    kaggle_workload("titanic-1"),
    kaggle_workload("house-prices-0"),
    kaggle_workload("house-prices-1"),
]


WORKLOAD_GROUPS = {
    **util.groupby_dict(workloads, lambda workload: workload.labels[0][0], util.identity),
    **util.groupby_dict(workloads, lambda workload: workload.labels[0][1], util.identity),
    **util.groupby_dict(workloads, lambda workload: workload.labels[0][2], util.identity),
    **util.groupby_dict(workloads, lambda workload: workload.labels[1][0], util.identity),
    **util.groupby_dict(workloads, lambda workload: workload.labels[1][1], util.identity),
    "all": workloads,
    "fast": [workload for workload in workloads if workload.labels[0][1] == "sanity"],
}
