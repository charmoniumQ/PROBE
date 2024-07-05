import psutil
import subprocess
from dataclasses import dataclass
import datetime

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
            except psutil.NoSuchProcess:
                break
            except psutil.AccessDenied:
                pass

        stdout, stderr = proc.communicate()
        
        end_time_psutil = datetime.datetime.now()

        start_time_wait = datetime.datetime.now()
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

    return results

if __name__ == "__main__":
    # command and other parameters 
    command_to_run = "./PROBE record --make head ../flake.nix"
    warmup_count = 5
    benchmark_count = 10
    
    benchmark_results = benchmark_command(command_to_run, warmup_count, benchmark_count)
    
    for idx, result in enumerate(benchmark_results, start=1):
        print(f"Result {idx}:")
        print(f"Return Code: {result.returncode}")
        print(f"CPU Times: {result.cpu_times}")
        print(f"Memory Info: {result.memory_info}")
        print(f"I/O Counters: {result.io_counters}")
        print(f"Start Time: {result.start_time}")
        print(f"End Time: {result.end_time}")
        print(f"STDOUT:\n{result.stdout}")
        print(f"STDERR:\n{result.stderr}")
        print("-" * 50)

