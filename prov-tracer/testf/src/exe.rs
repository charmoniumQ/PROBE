fn main() {
    let args: Vec<_> = std::env::args_os().skip(1).collect();
    let pid = unsafe {libc::fork()};
    if pid == -1 {
        panic!("fork failed");
    } else {
        if pid == 0 {
            println!("exec {:?}", args);
            let mut args2: Vec<_> = args.iter().map(|arg| arg.as_encoded_bytes().as_ptr() as *const i8).collect();
            args2.push(std::ptr::null());
            let ret = unsafe {libc::execvp(args2[0], args2.as_ptr())};
            println!("exec returned {:?}", ret);
        } else {
            let mut status: libc::c_int = 0;
            unsafe { libc::waitpid(pid, &mut status, 0) };
        }
    }
}
