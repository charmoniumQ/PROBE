import subprocess
import shlex
import datetime
import csv
import time
import os
import shutil
import resource
import dataclasses
import typing
import errno
import pathlib


@dataclasses.dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str
    duration: float
    rusage: resource.struct_rusage


PROBE_LOG = pathlib.Path("probe_log")
PROBE_RECORD_DIR = pathlib.Path("probe_record")


class ResourcePopen(subprocess.Popen[bytes]):
    def _try_wait(self, wait_flags: int) -> tuple[int, int]:
        try:
            (pid, sts, res) = os.wait4(self.pid, wait_flags)
        except OSError as e:
            if e.errno != errno.ECHILD:
                raise
            pid = self.pid
            sts = 0
        else:
            self.rusage = res
        return (pid, sts)


def resource_call(
    popenargs: typing.Sequence[str],
    timeout: float | None = None,
) -> Result:
    with ResourcePopen(popenargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as p:
        start = datetime.datetime.now()
        try:
            stdout, stderr = p.communicate(timeout=timeout)
        except:
            p.kill()
            stdout, stderr = p.communicate()
            raise
        stop = datetime.datetime.now()
        return Result(
            p.returncode,
            stdout.decode(),
            stderr.decode(),
            (stop - start).total_seconds(),
            p.rusage,
        )


DELAY = 0.0


def cleanup() -> None:
    if PROBE_LOG.exists():
        PROBE_LOG.unlink()
    if PROBE_RECORD_DIR.exists():
        shutil.rmtree(PROBE_RECORD_DIR)
    time.sleep(DELAY)


def benchmark_command(
    command: list[str],
    warmup_iterations: int,
    benchmark_iterations: int,
    transcribe_flag: bool,
) -> list[Result]:
    results = []

    for _ in range(warmup_iterations):
        print(f"    Running warmup command: {shlex.join(command)}")
        cleanup()
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            print("      Returned non-zero")
            print(proc.stdout.decode())
            print(proc.stderr.decode())

    for _ in range(benchmark_iterations):
        cleanup()
        print(f"    Running process with command: {shlex.join(command)}")
        result = resource_call(command)
        if result.returncode != 0:
            print("      Returned non-zero")

        results.append(result)
        time.sleep(DELAY)

        if transcribe_flag:
            print(f"    Running probe transcribe -i {PROBE_RECORD_DIR} -o {PROBE_LOG}")
            transcribe_result = resource_call(
                [
                    "probe",
                    "transcribe",
                    "-i",
                    str(PROBE_RECORD_DIR),
                    "-o",
                    str(PROBE_LOG),
                ]
            )
            if result.returncode != 0:
                print("      Transcribe returned non-zero")
            results.append(transcribe_result)
            time.sleep(DELAY)

    return results


def write_results_to_csv(
    writer: csv.DictWriter[str],
    command_to_run: str,
    phase: str,
    results: list[Result],
) -> None:
    for idx, result in enumerate(results, start=1):
        rusage = result.rusage
        writer.writerow(
            {
                "Command": command_to_run,
                "Phase": phase,
                "Return Code": result.returncode,
                "Duration": result.duration,
                "ru_utime": f"{rusage.ru_utime:.6f}",
                "ru_stime": f"{rusage.ru_stime:.6f}",
                "ru_maxrss": rusage.ru_maxrss,
                "ru_ixrss": rusage.ru_ixrss,
                "ru_idrss": rusage.ru_idrss,
                "ru_isrss": rusage.ru_isrss,
                "ru_minflt": rusage.ru_minflt,
                "ru_majflt": rusage.ru_majflt,
                "ru_nswap": rusage.ru_nswap,
                "ru_inblock": rusage.ru_inblock,
                "ru_oublock": rusage.ru_oublock,
                "ru_msgsnd": rusage.ru_msgsnd,
                "ru_msgrcv": rusage.ru_msgrcv,
                "ru_nsignals": rusage.ru_nsignals,
                "ru_nvcsw": rusage.ru_nvcsw,
                "ru_nivcsw": rusage.ru_nivcsw,
            }
        )


def benchmark_with_transcription(
    commands_to_run: list[list[str]], warmup_count: int, benchmark_count: int
) -> None:
    with open("benchmark_results.csv", mode="w", newline="") as csv_file:
        fieldnames = [
            "Command",
            "Phase",
            "Return Code",
            "Duration",
            "ru_utime",
            "ru_stime",
            "ru_maxrss",
            "ru_ixrss",
            "ru_idrss",
            "ru_isrss",
            "ru_minflt",
            "ru_majflt",
            "ru_nswap",
            "ru_inblock",
            "ru_oublock",
            "ru_msgsnd",
            "ru_msgrcv",
            "ru_nsignals",
            "ru_nvcsw",
            "ru_nivcsw",
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for command_args in commands_to_run:
            print(f"Benchmarking: {shlex.join(command_args)}")

            print(
                f"  Running benchmark for command (No PROBE): {shlex.join(command_args)}"
            )
            transcribe_flag = False
            no_probe_results = benchmark_command(
                command_args, warmup_count, benchmark_count, transcribe_flag
            )
            write_results_to_csv(
                writer, shlex.join(command_args), "No PROBE", no_probe_results
            )

            cleanup()

            record_command_args = ["probe", "record"] + command_args
            print(
                f"  Running benchmark for command (Record): {shlex.join(record_command_args)}"
            )
            record_results = benchmark_command(
                record_command_args, warmup_count, benchmark_count, transcribe_flag
            )
            write_results_to_csv(
                writer, shlex.join(command_args), "Record", record_results
            )

            cleanup()

            transcribe_flag = True
            no_transcribe_args = ["probe", "record", "--no-transcribe"] + command_args
            print(
                f"  Running benchmark for command probe no-transcribe: {shlex.join(no_transcribe_args)}"
            )
            probe_results = benchmark_command(
                no_transcribe_args, warmup_count, benchmark_count, transcribe_flag
            )
            write_results_to_csv(
                writer, shlex.join(command_args), "no-transcribe", probe_results
            )

            cleanup()


if __name__ == "__main__":
    commands = [
        ["ls", "-l"],
        ["echo", "Hello World"],
        ["pwd"],
        [
            "sh",
            "-c",
            "cd probe_src/tests/c && gcc hello_world.c -o hello_world.exe && ./hello_world.exe",
        ],
        [
            "sh",
            "-c",
            "cd probe_src/tests/c && gcc createFile.c -o createFile.exe -lpthread && ./createFile.exe",
        ],
        ["python3", "-c", "import sys; sys.stdout.write('hello world')"],
        ["date"],
        ["uptime"],
    ]

    os.chdir(pathlib.Path(__file__).resolve().parent.parent)
    benchmark_with_transcription(commands, warmup_count=1, benchmark_count=4)
