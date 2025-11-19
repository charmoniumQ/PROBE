Opens now call stat twice:
- once before the open to make sure we aren't going to truncate an inode that we need.
- once after the open, so we know what file is getting read.
Both of these can be reduced.
The first only needs to be done when the flags are O_TRUNC, at which point we would call maybe_copy_file.
(Still need to maybe_copy_file, after the file is opened).
The second only needs to happen if the first does not.
Perhaps the stats on dup can even be removed.

Try reducing the size of the Op structure in libprobe. Can do away with timestamp and thread IDs.

Try only storing the diff of the environment the current process's initial environment in exec.

Deduplicate information that is currently in both: ExecOp and InitExecOp.
On the one hand, the information is passed _by_ (i.e., created/set by) the parent exec op. On the other hand, the "root" exec would be missing, as that comes from probe CLI, prior to LD_PRELOAD being set. Also if we ever find ourselves in a process created by a raw syscall, it may be nice to note our current surroundings.
Resolved: Track it all in ExecOp, unless the current ExecOp is "unmarked". All probe-interposed exec*-family lib calls "mark" the target exec-op, indicated by the process_context.
