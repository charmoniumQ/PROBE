import subprocess
import datetime
import csv
import time
import os
import shutil
import resource
from dataclasses import dataclass
import psutil 

@dataclass
class Result:
    returncode: int
    cpu_times: tuple
    memory_usage: int
    io_counters: dict
    stdout: str
    stderr: str
    start_time: datetime.datetime
    end_time: datetime.datetime
    cpu_usage_percent: float

LOG_FILE = "probe_log"
RECORD_DIR = "probe_record"

def cleanup():
    if os.path.exists(LOG_FILE):
        print("Removing log file.")
        subprocess.run("rm probe_log", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if os.path.exists(RECORD_DIR):
        print("Removing record directory.")
        shutil.rmtree(RECORD_DIR)
    time.sleep(3)

def get_process_stats(proc):
    try:
        rusage = resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu_times = (rusage.ru_utime, rusage.ru_stime)  
        memory_usage = rusage.ru_maxrss  
    except Exception as e:
        print(f"Failed to get process stats: {e}")
        cpu_times = memory_usage = None

    io_counters = None
    try:
        process = psutil.Process(proc.pid)
        io_counters_raw = process.io_counters()
        io_counters = {
            'read_count': io_counters_raw.read_count,
            'write_count': io_counters_raw.write_count,
            'read_bytes': io_counters_raw.read_bytes,
            'write_bytes': io_counters_raw.write_bytes
        }
    except Exception as e:
        print(f"Failed to get I/O counters: {e}")

    return cpu_times, memory_usage, io_counters

def benchmark_command(command: str, warmup_iterations: int, benchmark_iterations: int, flag: bool) -> list[Result]:
    results = []

    for _ in range(warmup_iterations):
        print(f"Running warmup command: {command}")
        subprocess.run("rm probe_log", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if not flag:
        for _ in range(benchmark_iterations):
            cleanup()
            start_time_psutil = datetime.datetime.now()
            print(f"Starting process with command: {command}")
            proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            print(f"Command STDOUT:\n{stdout.decode('utf-8')}")
            print(f"Command STDERR:\n{stderr.decode('utf-8')}")
            returncode = proc.wait()
            end_time_wait = datetime.datetime.now()
            cpu_times, memory_usage, io_counters = get_process_stats(proc)
            total_cpu_time = cpu_times[0] + cpu_times[1]
            elapsed_time = (end_time_wait - start_time_psutil).total_seconds()
            cpu_usage_percent = (total_cpu_time / elapsed_time) * 100 if elapsed_time > 0 else 0
            result = Result(
                returncode=returncode,
                cpu_times=cpu_times,
                memory_usage=memory_usage,
                io_counters=io_counters,
                stdout=stdout.decode('utf-8'),
                stderr=stderr.decode('utf-8'),
                start_time=start_time_psutil,
                end_time=end_time_wait,
                cpu_usage_percent=cpu_usage_percent
            )
            results.append(result)
            time.sleep(3)
    else:
        for _ in range(benchmark_iterations):
            cleanup()
            start_time_psutil = datetime.datetime.now()
            print(f"Starting process with command: {command}")
            proc = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            print(f"Command STDOUT:\n{stdout.decode('utf-8')}")
            print(f"Command STDERR:\n{stderr.decode('utf-8')}")
            returncode = proc.wait()
            end_time_wait = datetime.datetime.now()
            cpu_times, memory_usage, io_counters = get_process_stats(proc)
            total_cpu_time = cpu_times[0] + cpu_times[1]
            elapsed_time = (end_time_wait - start_time_psutil).total_seconds()
            cpu_usage_percent = (total_cpu_time / elapsed_time) * 100 if elapsed_time > 0 else 0
            result = Result(
                returncode=returncode,
                cpu_times=cpu_times,
                memory_usage=memory_usage,
                io_counters=io_counters,
                stdout=stdout.decode('utf-8'),
                stderr=stderr.decode('utf-8'),
                start_time=start_time_psutil,
                end_time=end_time_wait,
                cpu_usage_percent=cpu_usage_percent
            )
            results.append(result)
            time.sleep(4)

            start_time_psutil = datetime.datetime.now()
            print(f"Starting process with command: ./probe transcribe -i {RECORD_DIR} -o {LOG_FILE}")
            proc = subprocess.Popen("./probe transcribe -i probe_record -o probe_log", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = proc.communicate()
            print(f"Command STDOUT:\n{stdout.decode('utf-8')}")
            print(f"Command STDERR:\n{stderr.decode('utf-8')}")
            returncode = proc.wait()
            end_time_wait = datetime.datetime.now()
            cpu_times, memory_usage, io_counters = get_process_stats(proc)
            total_cpu_time = cpu_times[0] + cpu_times[1]
            elapsed_time = (end_time_wait - start_time_psutil).total_seconds()
            cpu_usage_percent = (total_cpu_time / elapsed_time) * 100 if elapsed_time > 0 else 0
            result = Result(
                returncode=returncode,
                cpu_times=cpu_times,
                memory_usage=memory_usage,
                io_counters=io_counters,
                stdout=stdout.decode('utf-8'),
                stderr=stderr.decode('utf-8'),
                start_time=start_time_psutil,
                end_time=end_time_wait,
                cpu_usage_percent=cpu_usage_percent
            )
            results.append(result)
            time.sleep(3)

    return results

def benchmark_with_transcription(commands_to_run, warmup_count, benchmark_count):
    with open('benchmark_results.csv', mode='w', newline='') as csv_file:
        fieldnames = ['Command', 'Phase', 'Return Code', 'CPU Times', 'Memory Usage', 'IO Counters',
                      'Start Time', 'End Time', 'Duration (s)', 'CPU Usage (%)']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for command_to_run in commands_to_run:
            print(f"Running benchmark for command (No PROBE): {command_to_run}")
            flag = False
            no_probe_results = benchmark_command(command_to_run, warmup_count, benchmark_count, flag)

            for idx, result in enumerate(no_probe_results, start=1):
                writer.writerow({
                    'Command': command_to_run,
                    'Phase': 'No PROBE',
                    'Return Code': result.returncode,
                    'CPU Times': result.cpu_times,
                    'Memory Usage': result.memory_usage,
                    'IO Counters': result.io_counters,
                    'Start Time': result.start_time,
                    'End Time': result.end_time,
                    'Duration (s)': (result.end_time - result.start_time).total_seconds(),
                    'CPU Usage (%)': result.cpu_usage_percent
                })

<<<<<<< HEAD
            # Run ./PROBE record for both execution and transcription
            record_command = f"probe record {command_to_run}"
=======
            cleanup()

            record_command = f"./probe record {command_to_run}"
>>>>>>> 76a5b4b (feat: performance tests for rust)
            print(f"Running benchmark for command (Record): {record_command}")
            record_results = benchmark_command(record_command, warmup_count, benchmark_count, flag)

            for idx, result in enumerate(record_results, start=1):
                writer.writerow({
                    'Command': command_to_run,
                    'Phase': 'Record',
                    'Return Code': result.returncode,
                    'CPU Times': result.cpu_times,
                    'Memory Usage': result.memory_usage,
                    'IO Counters': result.io_counters,
                    'Start Time': result.start_time,
                    'End Time': result.end_time,
                    'Duration (s)': (result.end_time - result.start_time).total_seconds(),
                    'CPU Usage (%)': result.cpu_usage_percent
                })

<<<<<<< HEAD
            # Run ./PROBE record --no-transcribe for execution only
            no_transcribe_command = f"probe record --no-transcribe {command_to_run}"
=======
            cleanup()

            no_transcribe_command = f"./probe record --no-transcribe {command_to_run}"
>>>>>>> 76a5b4b (feat: performance tests for rust)
            print(f"Running benchmark for command (No Transcribe): {no_transcribe_command}")
            flag = True
            no_transcribe_results = benchmark_command(no_transcribe_command, warmup_count, benchmark_count, flag)

            for idx, result in enumerate(no_transcribe_results, start=1):
                writer.writerow({
                    'Command': command_to_run,
                    'Phase': 'No Transcribe',
                    'Return Code': result.returncode,
                    'CPU Times': result.cpu_times,
                    'Memory Usage': result.memory_usage,
                    'IO Counters': result.io_counters,
                    'Start Time': result.start_time,
                    'End Time': result.end_time,
                    'Duration (s)': (result.end_time - result.start_time).total_seconds(),
                    'CPU Usage (%)': result.cpu_usage_percent
                })

<<<<<<< HEAD
                # Run ./PROBE transcribe-only using the temporary probe directory
                if result.returncode == 0:
                    probe_log_dir = result.stdout.strip().split(': ')[-1]  # Extracting the probe log directory
                    transcribe_command = f"probe transcribe-only {probe_log_dir} --output probe_log"
                    print(f"Running transcription for command: {command_to_run}")
                    transcribe_proc = subprocess.run(transcribe_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

                    transcribe_err = transcribe_proc.stderr
                    if transcribe_proc.returncode == 0:
                        transcribe_duration_seconds = (datetime.datetime.now() - result.end_time).total_seconds()

                        writer.writerow({
                            'Command': command_to_run,
                            'Phase': 'Transcription',
                            'Return Code': transcribe_proc.returncode,
                            'CPU Times': '',
                            'Memory Info': '',
                            'IO Counters': '',
                            'Start Time': result.end_time,
                            'End Time': datetime.datetime.now(),
                            'Duration (s)': transcribe_duration_seconds
                        })

                        print(f"Transcription completed for command: {command_to_run}")
                    else:
                        print(f"Error in transcription for command: {command_to_run}")
                        print(f"Error message:\n{transcribe_err.decode('utf-8')}")
                else:
                    print(f"Skipping transcription for command due to previous error: {command_to_run}")

if __name__ == "__main__":
=======
            cleanup()
         
if __name__ == "__main__":   
>>>>>>> 76a5b4b (feat: performance tests for rust)
    commands_to_run = [
        "echo 'Hello, World!'",
        "ls -l",
        "pwd",
        "head ../flake.nix",
        "python3 -c 'print(2 + 2)'",
        "cat tasks.md"
    ]
    warmup_count = 1
    benchmark_count = 2

    benchmark_with_transcription(commands_to_run, warmup_count, benchmark_count)
