import shlex
import subprocess
import langchain
import itertools
import shutil
import experiment


def do_run(
        workload_name: str,
        tracer_name: str,
) -> None:
    workload = experiment.workloads[workload_name]
    tracer = experiment.tracers[tracer_name]()
    experiment.podman_build(workload.context, workload_name)
    if workload.setup:
        cmd = experiment.podman(workload_name, workload.mounts) + workload.setup
        print(f"Running {tracer_name} {workload_name} setup")
        print(shlex.join(map(str, cmd)))
        subprocess.run(
            cmd,
            check=True,
        )
    cmd = experiment.podman(workload_name, workload.mounts) + experiment.join_cmds(*workload.steps)
    print(f"Running {tracer_name} {workload_name}")
    print(shlex.join(map(str, cmd)))
    subprocess.run(
        cmd,
        check=True,
    )

    if tracer.make_artifact:
        cmd = experiment.podman(workload_name, workload.mounts) + tracer.make_artifact
        print(f"Running {tracer_name} {workload_name} artifact")
        print(shlex.join(map(str, cmd)))
        subprocess.run(
            cmd,
            check=True,
        )
        assert tracer.artifact
        artifact_path = experiment.results_dir / "artifacts" / tracer_name / workload_name
        artifact_path.parent.mkdir(exist_ok=True, parents=True)
        if artifact_path.exists():
            artifact_path.unlink()
        shutil.move(experiment.scratch_dir / tracer.artifact, artifact_path)


if __name__ == "__main__":
    for workload_name, tracer_name in itertools.product(experiment.workloads.keys(), experiment.tracers.keys()):
        artifact_path = experiment.results_dir / "artifacts" / tracer_name / workload_name
        if experiment.tracers[tracer].make_artifact and not artifact_path.exists():
            do_run(workload, tracer)
