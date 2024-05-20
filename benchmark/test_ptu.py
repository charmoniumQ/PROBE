import shutil
import pathlib
from run_exec_wrapper import run_exec, DirMode

work_dir = pathlib.Path("/tmp/test/work")
log_dir = pathlib.Path("/tmp/test/work")

if work_dir.exists():
    shutil.rmtree(work_dir)
work_dir.mkdir(parents=True)

if log_dir.exists():
    shutil.rmtree(log_dir)
log_dir.mkdir(parents=True)

full_env = {
    'PATH': ':'.join([
        '/nix/store/khndnv11g1rmzhzymm1s5dw7l2ld45bc-coreutils-9.4/bin'
        '/nix/store/90y3i68k8r3xajgl1bq8fmfhabaqkbys-bash-5.2-p21-man/bin'
        '/nix/store/9vafkkic27k7m4934fpawl6yip3a6k4h-bash-5.2-p21/bin'
        '/nix/store/rkgp88plb6xbsx800js2jk1ny04kfnn3-provenance-to-use-0.0.0/bin',
        '/nix/store/gpi5zk0s1mnvbr12j26572438h8n09v8-strace-6.6/bin',
    ]),
    'PYTHONNOUSERSITE': 'true:true',
    'LC_CTYPE': 'C.UTF-8:C.UTF-8'
}

cmd = ('strace', '/nix/store/rkgp88plb6xbsx800js2jk1ny04kfnn3-provenance-to-use-0.0.0/bin/ptu', '-o', log_dir, 'bash', '-e', '-c', 'for i in $(seq 10000); do true; done')

stats = run_exec(
    cmd=cmd,
    env=full_env,
    dir_modes={
        work_dir: DirMode.FULL_ACCESS,
        log_dir: DirMode.FULL_ACCESS,
        pathlib.Path(): DirMode.READ_ONLY,
        pathlib.Path("/nix/store"): DirMode.READ_ONLY,
    },
    network_access=False,
)
print("vvv")
print(stats.stdout)
print("---")
print(stats.stderr)
print("^^^")
print(stats.success)
