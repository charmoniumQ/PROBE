const MAX_PATH_SIZE: isize = 1024;

pub fn short_cstr(const_ptr_char: *const libc::c_char) -> &'static std::ffi::CStr {
	assert!({
		let mut is_null_terminated = false;
		let mut has_no_newlines = true;
		for i in 0..MAX_PATH_SIZE {
			let ch = unsafe { *const_ptr_char.offset(i) } as u8 as char;
			match ch {
				'\0' => {
					is_null_terminated = true;
					break;
				},
				'\n' => {
					has_no_newlines = false;
					break;
				},
				_ => (),
			}
		}
		is_null_terminated && has_no_newlines
	});
	unsafe { std::ffi::CStr::from_ptr(const_ptr_char) }
}
