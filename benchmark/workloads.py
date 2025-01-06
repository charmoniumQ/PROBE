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


make = command.NixPath(".#gnumake", "/bin/make")
mkdir = command.NixPath(".#coreutils", "/bin/mkdir")
tmpdir = command.Placeholder("tmpdir")
blast_dir = command.NixPath(".#blast-benchmark")
blast_output = command.Placeholder("work_dir", prefix="OUTPUT=")


workloads = [
    Workload(
        (("app", "blast", "tblastx"), ("cse", "multiomics")),
        command.Command((make, "-C", blast_dir, "tblastx", blast_output)),
    ),
    Workload(
        (("app", "blast", "tblastn"), ("cse", "multiomics")),
        command.Command((make, "-C", blast_dir, "tblastn", blast_output)),
    ),
    # Workload(
    #     (("app", "blast", "blastx"), ("cse", "multiomics")),
    #     command.Command((make, "-C", blast_dir, "blastx", blast_output)),
    # ),
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
    # Workload(
    #     (("app", "blast", "idx_megablast"), ("cse", "multiomics")),
    #     command.Command((make, "-C", blast_dir, "idx_megablast", blast_output)),
    # ),
    Workload(
        (("microbench", "sanity", "ls"), ("", "")),
        command.Command((command.NixPath(".#coreutils", postfix="/bin/ls"),)),
    ),
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
