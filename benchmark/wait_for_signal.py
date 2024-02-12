#!/usr/bin/env python
import os
import sys
import signal

signal_mask = [getattr(signal, sys.argv[1].upper())]
exe = sys.argv[3]
args = sys.argv[3:]
wait_time = float(sys.argv[2])
# print(f"Waiting for {signal_mask}, {os.getpid()}")
signal.pthread_sigmask(signal.SIG_BLOCK, signal_mask)
signal.sigwait(signal_mask)
signal.pthread_sigmask(signal.SIG_UNBLOCK, signal_mask)
# print(f"Got {signal_mask}")

os.execvp(exe, args)
