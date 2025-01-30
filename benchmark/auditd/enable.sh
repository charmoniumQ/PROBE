#!/usr/bin/env sh

# See strace_syscalls in prov_collectors.py
file_syscalls="open,openat,openat2,creat,close,close_range,dup,dup2,dup3,link,linkat,symlink,symlinkat,unlink,unlinkat,rmdir,rename,renameat,mkdir,mkdirat,fstat,newfstatat,chown,fchown,lchown,fchownat,chmod,fchmod,fchmodat,access,faccessat,utime,utimes,futimesat,utimensat,truncate,ftruncate,mknod,mknodat,readlink,readlinkat,fcntl,fgetxattr,flistxattr,fremovexattr,fsetxattr,getxattr,lgetxattr,listxattr,llistxattr,lremovexattr,lsetxattr,removexattr,setxattr,chroot,fchdir,chdir"

proc_syscalls="clone,clone3,fork,vfork,execve,execveat,exit,exit_group,,sockets,bind,accept,accept4,connect,socketcall,shutdown,pipe,pipe2"

# Track all fork/clone from this user
sudo auditctl -s all            -A task,always -F uid=$UID -F gid=$GID                   -k sams_prov

# Track all exec from this user
sudo auditctl -S $proc_syscalls -A exit,always -F uid=$UID -F gid=$GID                   -k sams_prov

# Track all file accesses from this user to specific directories
sudo auditctl -S $file_syscalls -A exit,always -F uid=$UID -F gid=$GID -F dir=/tmp/..    -k sams_prov
sudo auditctl -S $file_syscalls -A exit,always -F uid=$UID -F gid=$GID -F dir=/nix/store -k sams_prov
