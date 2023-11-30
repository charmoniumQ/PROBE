mod prov_logger;
mod simple_prov_logger;
mod util;

extern crate project_specific_macros;

use crate::prov_logger::ProvLogger;
use crate::simple_prov_logger::SimpleProvLogger;

#[macro_use]
extern crate ctor;

#[ctor]
static PROV_LOGGER: SimpleProvLogger = SimpleProvLogger::new();

#[macro_use]
extern crate redhook;

use libc::{c_int, c_uint, c_char, FILE, mode_t};

use project_specific_macros::log_libc_calls;

log_libc_calls!{
    // https://www.gnu.org/software/libc/manual/html_node/Opening-Streams.html
    fn fopen(filename: *const c_char, opentype: *const c_char) -> FILE;
    fn fopen64(filename: *const c_char, opentype: *const c_char) -> FILE;
    fn freopen(filename: *const c_char, opentype: *const c_char, stream: *mut FILE) -> FILE;
    fn freopen64(filename: *const c_char, opentype: *const c_char, stream: *mut FILE) -> FILE;

    // We need these in case an analysis wants to use open-to-close consistency
    // https://www.gnu.org/software/libc/manual/html_node/Closing-Streams.html
    fn fclose(stream: *mut FILE) -> c_int;
    fn fcloseall() -> c_int;

    // https://www.gnu.org/software/libc/manual/html_node/Opening-and-Closing-Files.html
    // TODO: what to do about optional third argument: mode_t mode?
    fn open(path: *const c_char, oflag: c_int) -> c_int;
    fn open64(path: *const c_char, oflag: c_int) -> c_int;
    fn creat(filename: *const c_char, mode: mode_t) -> c_int;
    fn close(filedes: c_int) -> c_int;
    fn close_range(low: c_uint, high: c_uint, flags: c_int) -> c_int;
    fn closefrom(low: c_int) -> c_int;

    // Fun extra Glibc functions that are not in the Glibc manual
    fn openat(dirfd: c_int, pathname: *const c_char, flags: c_int) -> c_int;
    fn openat64(dirfd: c_int, pathname: *const c_char, flags: c_int) -> c_int;
}
