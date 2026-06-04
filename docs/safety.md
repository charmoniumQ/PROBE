# Thread-safety

Most ops are logged in a thread-local mmapped buffer.
Threads won't interfere with each other.

When one thread successfully calls open, we hold the returned FD and set fd_table[fd] = atomic_fetch_add(open_number). That is not atomic, and can get interrupted. If it is interrupted, the fd will be different though, so I think that is ok.

The inode_table and fd_table has a spin-lock in it.

# Long-term safety

- Exhaust boot numbers
- Exhaust open numbers
- Exhaust PIDs
- Exhaust exec nos within PID (unlikely)
- Exhaust TIDs within exec_no (unlikely)
