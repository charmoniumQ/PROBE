import subprocess
import datetime
import csv
import time
import os
import shutil
import resource
from dataclasses import dataclass
import psutil
import errno
from pathlib import Path

@dataclass
class Result:
    returncode: int
    stdout: str
    stderr: str
    duration: float
    rusage: resource.struct_rusage

LOG_FILE = Path("probe_log")
RECORD_DIR = Path("probe_record")

class ResourcePopen(subprocess.Popen):
    def _try_wait(self, wait_flags):
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

def resource_call(*popenargs, timeout=None, **kwargs) -> Result:
    with ResourcePopen(*popenargs, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs) as p:
        start = datetime.datetime.now()
        try:
            stdout, stderr = p.communicate(timeout=timeout)
        except:
            p.kill()
            stdout, stderr = p.communicate()
            raise
        stop = datetime.datetime.now()
        return Result(p.returncode, stdout.decode(), stderr.decode(), (stop - start).total_seconds(), p.rusage)

def cleanup():
    if LOG_FILE.exists():
        print("Removing log file.")
        LOG_FILE.unlink()
    if RECORD_DIR.exists():
        print("Removing record directory.")
        shutil.rmtree(RECORD_DIR)
    time.sleep(3)

def benchmark_command(command: list[str], warmup_iterations: int, benchmark_iterations: int, transcribe_flag: bool) -> list[Result]:
    results = []

    for _ in range(warmup_iterations):
        print(f"Running warmup command: {' '.join(command)}")
        if LOG_FILE.exists():
            LOG_FILE.unlink()
        subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    for _ in range(benchmark_iterations):
        cleanup()
        print(f"Starting process with command: {' '.join(command)}")
        result = resource_call(command)
        results.append(result)
        time.sleep(3)

        if transcribe_flag:
            print(f"Running probe transcribe -i {RECORD_DIR} -o {LOG_FILE}")
            transcribe_result = resource_call(["probe", "transcribe", "-i", str(RECORD_DIR), "-o", str(LOG_FILE)])
            results.append(transcribe_result)
            time.sleep(3)

    return results

def write_results_to_csv(writer, command_to_run, phase, results):
    for idx, result in enumerate(results, start=1):
        rusage = result.rusage
        writer.writerow({
            'Command': command_to_run,
            'Phase': phase,
            'Return Code': result.returncode,
            'Duration': result.duration,
            'ru_utime': f"{rusage.ru_utime:.6f}",
            'ru_stime': f"{rusage.ru_stime:.6f}",
            'ru_maxrss': rusage.ru_maxrss,
            'ru_ixrss': rusage.ru_ixrss,
            'ru_idrss': rusage.ru_idrss,
            'ru_isrss': rusage.ru_isrss,
            'ru_minflt': rusage.ru_minflt,
            'ru_majflt': rusage.ru_majflt,
            'ru_nswap': rusage.ru_nswap,
            'ru_inblock': rusage.ru_inblock,
            'ru_oublock': rusage.ru_oublock,
            'ru_msgsnd': rusage.ru_msgsnd,
            'ru_msgrcv': rusage.ru_msgrcv,
            'ru_nsignals': rusage.ru_nsignals,
            'ru_nvcsw': rusage.ru_nvcsw,
            'ru_nivcsw': rusage.ru_nivcsw
        })

def benchmark_with_transcription(commands_to_run: list[str], warmup_count: int, benchmark_count: int):
    with open('benchmark_results.csv', mode='w', newline='') as csv_file:
        fieldnames = [
            'Command', 'Phase', 'Return Code', 'Duration',
            'ru_utime', 'ru_stime', 'ru_maxrss', 'ru_ixrss', 'ru_idrss', 'ru_isrss',
            'ru_minflt', 'ru_majflt', 'ru_nswap', 'ru_inblock', 'ru_oublock',
            'ru_msgsnd', 'ru_msgrcv', 'ru_nsignals', 'ru_nvcsw', 'ru_nivcsw'
        ]
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for command_to_run in commands_to_run:
            command_args = command_to_run.split()

            print(f"Running benchmark for command (No PROBE): {command_to_run}")
            transcribe_flag = False
            no_probe_results = benchmark_command(command_args, warmup_count, benchmark_count, transcribe_flag)
            write_results_to_csv(writer, command_to_run, 'No PROBE', no_probe_results)

            cleanup()

            record_command_args = ["probe", "record"] + command_args
            print(f"Running benchmark for command (Record): {' '.join(record_command_args)}")
            record_results = benchmark_command(record_command_args, warmup_count, benchmark_count, transcribe_flag)
            write_results_to_csv(writer, command_to_run, 'Record', record_results)

            cleanup()

            transcribe_flag = True
            print(f"Running benchmark for command probe no-transcribe: {command_to_run}")
            no_transcribe_args= ["probe", "record", "--no-transcribe"] + command_args
            probe_results = benchmark_command(no_transcribe_args, warmup_count, benchmark_count, transcribe_flag)
            write_results_to_csv(writer, command_to_run, 'no-transcribe', probe_results)

            cleanup()

if __name__ == "__main__":
    commands = [
        "ls -l", 
        "echo Hello World", 
        "pwd",
        "gcc hello_world.c -o hello_world && ./hello_world",   
        "gcc pthreads_example.c -o pthreads_example -lpthread && ./pthreads_example",  
        "python3 hello_world.py",
        "date", 
        "uptime"
    ]

    benchmark_with_transcription(commands, warmup_count=1, benchmark_count=2)
