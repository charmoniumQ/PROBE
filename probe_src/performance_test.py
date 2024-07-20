import subprocess
import datetime
import csv
import psutil
import time
from dataclasses import dataclass

@dataclass
class Result:
    returncode: int
    cpu_times: tuple
    memory_info: tuple
    io_counters: tuple
    stdout: str
    stderr: str
    start_time: datetime.datetime
    end_time: datetime.datetime

def benchmark_command(command: str, warmup_iterations: int, benchmark_iterations: int) -> list[Result]:
    results = []

    for _ in range(warmup_iterations):
        subprocess.run(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    for _ in range(benchmark_iterations):
        start_time_psutil = datetime.datetime.now()

        proc = psutil.Popen(command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        cpu_times = memory_info = io_counters = None

        if proc.is_running():
            try:
                cpu_times = proc.cpu_times()
                memory_info = proc.memory_info()
                io_counters = proc.io_counters()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        stdout, stderr = proc.communicate()

        datetime.datetime.now()

        datetime.datetime.now()
        returncode = proc.wait()
        end_time_wait = datetime.datetime.now()

        result = Result(
            returncode=returncode,
            cpu_times=cpu_times,
            memory_info=memory_info,
            io_counters=io_counters,
            stdout=stdout.decode('utf-8'),
            stderr=stderr.decode('utf-8'),
            start_time=start_time_psutil,
            end_time=end_time_wait
        )
        results.append(result)
        time.sleep(4)  # Pause for 4 seconds after each command

    return results

def benchmark_with_transcription(commands_to_run, warmup_count, benchmark_count):
    with open('benchmark_results.csv', mode='w', newline='') as csv_file:
        fieldnames = ['Command', 'Phase', 'Return Code', 'CPU Times', 'Memory Info', 'IO Counters',
                      'Start Time', 'End Time', 'Duration (s)']
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()

        for command_to_run in commands_to_run:
            # Run the command without PROBE
            print(f"Running benchmark for command (No PROBE): {command_to_run}")
            no_probe_results = benchmark_command(command_to_run, warmup_count, benchmark_count)

            for idx, result in enumerate(no_probe_results, start=1):
                print(f"Result {idx} (No PROBE):")
                print(f"Return Code: {result.returncode}")
                print(f"CPU Times: {result.cpu_times}")
                print(f"Memory Info: {result.memory_info}")
                print(f"I/O Counters: {result.io_counters}")
                print(f"Start Time: {result.start_time}")
                print(f"End Time: {result.end_time}")
                print(f"STDOUT:\n{result.stdout}")
                print(f"STDERR:\n{result.stderr}")
                print("-" * 50)

                writer.writerow({
                    'Command': command_to_run,
                    'Phase': 'No PROBE',
                    'Return Code': result.returncode,
                    'CPU Times': result.cpu_times,
                    'Memory Info': result.memory_info,
                    'IO Counters': result.io_counters,
                    'Start Time': result.start_time,
                    'End Time': result.end_time,
                    'Duration (s)': (result.end_time - result.start_time).total_seconds()
                })

            # Run ./PROBE record for both execution and transcription
            record_command = f"./PROBE record {command_to_run}"
            print(f"Running benchmark for command (Record): {record_command}")
            record_results = benchmark_command(record_command, warmup_count, benchmark_count)

            for idx, result in enumerate(record_results, start=1):
                print(f"Result {idx} (Record):")
                print(f"Return Code: {result.returncode}")
                print(f"CPU Times: {result.cpu_times}")
                print(f"Memory Info: {result.memory_info}")
                print(f"I/O Counters: {result.io_counters}")
                print(f"Start Time: {result.start_time}")
                print(f"End Time: {result.end_time}")
                print(f"STDOUT:\n{result.stdout}")
                print(f"STDERR:\n{result.stderr}")
                print("-" * 50)

                writer.writerow({
                    'Command': command_to_run,
                    'Phase': 'Record',
                    'Return Code': result.returncode,
                    'CPU Times': result.cpu_times,
                    'Memory Info': result.memory_info,
                    'IO Counters': result.io_counters,
                    'Start Time': result.start_time,
                    'End Time': result.end_time,
                    'Duration (s)': (result.end_time - result.start_time).total_seconds()
                })

            # Run ./PROBE record --no-transcribe for execution only
            no_transcribe_command = f"./PROBE record --no-transcribe {command_to_run}"
            print(f"Running benchmark for command (No Transcribe): {no_transcribe_command}")
            no_transcribe_results = benchmark_command(no_transcribe_command, warmup_count, benchmark_count)

            for idx, result in enumerate(no_transcribe_results, start=1):
                print(f"Result {idx} (No Transcribe):")
                print(f"Return Code: {result.returncode}")
                print(f"CPU Times: {result.cpu_times}")
                print(f"Memory Info: {result.memory_info}")
                print(f"I/O Counters: {result.io_counters}")
                print(f"Start Time: {result.start_time}")
                print(f"End Time: {result.end_time}")
                print(f"STDOUT:\n{result.stdout}")
                print(f"STDERR:\n{result.stderr}")
                print("-" * 50)

                writer.writerow({
                    'Command': command_to_run,
                    'Phase': 'No Transcribe',
                    'Return Code': result.returncode,
                    'CPU Times': result.cpu_times,
                    'Memory Info': result.memory_info,
                    'IO Counters': result.io_counters,
                    'Start Time': result.start_time,
                    'End Time': result.end_time,
                    'Duration (s)': (result.end_time - result.start_time).total_seconds()
                })

                # Run ./PROBE transcribe-only using the temporary probe directory
                if result.returncode == 0:
                    probe_log_dir = result.stdout.strip().split(': ')[-1]  # Extracting the probe log directory
                    transcribe_command = f"./PROBE transcribe-only {probe_log_dir} --output probe_log"
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

