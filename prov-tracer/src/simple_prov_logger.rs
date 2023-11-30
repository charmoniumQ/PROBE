use crate::util::short_cstr;
use libc::{c_char, c_int};

use envconfig::Envconfig;
#[derive(envconfig::Envconfig)]
struct ProvTraceConfig {
    #[envconfig(from = "PROV_TRACE_FILE", default = ".prov.trace")]
    file: String,

    #[envconfig(from = "PROV_TRACE_BUFFER_SIZE", default = "1000000")]
    buffer_size: usize,
}

pub struct SimpleProvLogger { }

impl crate::prov_logger::ProvLogger for SimpleProvLogger {
	fn new() -> Self {
        crate::prov_logger::LOG_OPEN64.set(false);
		let config = ProvTraceConfig::init_from_env().unwrap();
		let pid = unsafe { libc::getpid() };
		let fname = format!("{}{}", pid, &config.file);
		fast_log::init(
			fast_log::config::Config::new()
				.file(&fname)
				.chan_len(Some(config.buffer_size))
		).unwrap();
        log::info!("started,{}", pid);
        crate::prov_logger::LOG_OPEN64.set(true);
		Self { }
	}

	fn open64(
		&self,
		path: *const c_char,
		oflag: c_int,
		ret: c_int,
	) {
		log::info!("open64,{},{},{:?}", oflag, ret, short_cstr(path));
	}

	fn close(
		&self,
		fd: c_int,
		ret: c_int,
	) {
		log::info!("close,{},{}", fd, ret);
	}

	fn fork(
		&self,
		ret: c_int,
	) {
		log::info!("fork,{}", ret);
	}
}
