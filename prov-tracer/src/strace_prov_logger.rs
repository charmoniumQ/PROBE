use envconfig::Envconfig;
use std::io::Write;

use crate::prov_logger::{CType, CPrimType, CFuncSigs};

pub struct StraceProvLogger {
    cfunc_sigs: &'static CFuncSigs,
    file: std::fs::File,
}

impl crate::prov_logger::ProvLogger for StraceProvLogger {
	fn new(cfunc_sigs: &'static CFuncSigs) -> Self {
        crate::globals::ENABLE_TRACE.set(false);
		let config = ProvTraceConfig::init_from_env().unwrap();
		let pid = (unsafe { libc::getpid() }).to_string();
        let tid = (unsafe { libc::gettid() }).to_string();
        let filename =
            config.filename
                  .replace("%p", &pid)
                  .replace("%t", &tid)
            ;
        let file = std::fs::File::create(filename).unwrap();
        crate::globals::ENABLE_TRACE.set(true);
		Self { cfunc_sigs, file}
	}

	fn log_call(
		&mut self,
        name: &'static str,
        args: Vec<Box<dyn std::any::Any>>,
        _new_args: Vec<Box<dyn std::any::Any>>,
        ret: Box<dyn std::any::Any>,
	) {
        let cfunc_sig = self.cfunc_sigs.get(name).unwrap();
        let return_type = ctype_to_string(ret, &cfunc_sig.return_type);
        let args: String = cfunc_sig.arg_types.iter().zip(args).map(|(arg_type, arg)| {
            format!("{}={}", arg_type.arg, ctype_to_string(arg, &arg_type.ty))
        }).intersperse(", ".to_string()).collect();
        write!(self.file, "{}({}) -> {}\n", name, args, return_type).unwrap();
	}
}

#[allow(dead_code)]
#[derive(envconfig::Envconfig)]
struct ProvTraceConfig {
    #[envconfig(from = "PROV_TRACE_FILENAME", default = "%p.%t.prov.trace")]
    filename: String,
}

fn ctype_to_string(any: Box<dyn std::any::Any>, ctype: &CType) -> String {
    match ctype {
        CType::PtrMut(prim_type) => match prim_type {
            CPrimType::Void => format!("(void*){:p}", *any.downcast_ref::<*mut libc::c_void>().unwrap()),
            CPrimType::File => format!("(FILE*){:p}", *any.downcast_ref::<*mut libc::FILE>().unwrap()),
            CPrimType::Dir  => format!("(DIR*){:p}", *any.downcast_ref::<*mut libc::DIR>().unwrap()),
            _ => "Unknown mut ptr type".to_owned(),
        },
        CType::PtrConst(prim_type) => match prim_type {
            CPrimType::Char => format!("{:?}", crate::util::short_cstr(*any.downcast_ref::<*const libc::c_char>().unwrap()).to_str().unwrap()),
            _ => "Unknown const ptr type".to_owned(),
        },
        CType::PrimType(prim_type) => match prim_type {
            CPrimType::Int => format!("{:?}", any.downcast_ref::<libc::c_int>().unwrap()),
            CPrimType::Uint => format!("{:?}", any.downcast_ref::<libc::c_uint>().unwrap()),
            CPrimType::ModeT => format!("{:?}", any.downcast_ref::<libc::mode_t>().unwrap()),
            CPrimType::FtwFuncT => format!("{:?}", any.downcast_ref::<*const libc::c_void>().unwrap()),
            CPrimType::Ftw64FuncT => format!("{:?}", any.downcast_ref::<*const libc::c_void>().unwrap()),
            CPrimType::NftwFuncT => format!("{:?}", any.downcast_ref::<*const libc::c_void>().unwrap()),
            CPrimType::Nftw64FuncT => format!("{:?}", any.downcast_ref::<*const libc::c_void>().unwrap()),
            _ => "Unknown prim type type".to_owned(),
        },
    }
}
