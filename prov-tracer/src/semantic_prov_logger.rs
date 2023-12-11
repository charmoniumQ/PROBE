use envconfig::Envconfig;

use crate::prov_logger::{CType, CPrimType, CFuncSigs};

#[derive(envconfig::Envconfig)]
struct ProvTraceConfig {
    #[envconfig(from = "PROV_TRACE_FILE", default = ".prov.trace")]
    file: String,

    #[envconfig(from = "PROV_TRACE_BUFFER_SIZE", default = "1000000")]
    buffer_size: usize,
}

pub struct SimpleProvLogger {
    cfunc_sigs: &'static CFuncSigs,
}

fn ctype_to_string(any: Box<dyn std::any::Any>, ctype: &CType) -> String {
    match ctype {
        CType::PtrMut(prim_type) => match prim_type {
            CPrimType::Void => format!("(void*)0x{:x}", any.downcast_ref::<*mut libc::c_void>().unwrap().clone() as usize).to_string(),
            CPrimType::File => format!("(FILE*)0x{:x}", any.downcast_ref::<*mut libc::FILE>().unwrap().clone() as usize).to_string(),
            _ => "Unknown type".to_string(),
        },
        CType::PtrConst(prim_type) => match prim_type {
            CPrimType::Char => format!("\"{:?}\"", crate::util::short_cstr(any.downcast_ref::<*const libc::c_char>().unwrap().clone())).to_string(),
            _ => "Unknown type".to_string(),
        },
        CType::PrimType(prim_type) => match prim_type {
            CPrimType::Int => any.downcast_ref::<libc::c_int>().unwrap().to_string(),
            CPrimType::Uint => any.downcast_ref::<libc::c_uint>().unwrap().to_string(),
            CPrimType::ModeT => any.downcast_ref::<libc::mode_t>().unwrap().to_string(),
            _ => "Unknown type".to_string(),
        },
    }
}

impl crate::prov_logger::ProvLogger for SimpleProvLogger {
	fn new(cfunc_sigs: &'static CFuncSigs) -> Self {
        crate::globals::ENABLE_TRACE_OPEN64.set(false);
        print!("Starting prov logger\n");
		let config = ProvTraceConfig::init_from_env().unwrap();
		let pid = unsafe { libc::getpid() };
		let fname = format!("{}{}", pid, &config.file);
		fast_log::init(
			fast_log::config::Config::new()
				.file(&fname)
				.chan_len(Some(config.buffer_size))
		).unwrap();
        log::info!("started,{}", pid);
        print!("Started prov logger\n");
        crate::globals::ENABLE_TRACE_OPEN64.set(true);
		Self { cfunc_sigs, }
	}

	fn log(
		&self,
        name: &'static str,
        args: Vec<Box<dyn std::any::Any>>,
        _new_args: Vec<Box<dyn std::any::Any>>,
        ret: Box<dyn std::any::Any>,
	) {
        let cfunc_sig = self.cfunc_sigs.get(name).unwrap();
        let return_type = ctype_to_string(ret, &cfunc_sig.return_type);
        let args: String = cfunc_sig.arg_types.iter().zip(args).map(|(arg_type, arg)| {
            format!("{} = {}", arg_type.arg, ctype_to_string(arg, &arg_type.ty))
        }).intersperse(", ".to_string()).collect();
		log::info!("{}({}) -> {}", name, args, return_type);
	}
}
