use std::collections::HashSet;
use std::env;
use std::path::PathBuf;
use std::sync::OnceLock;

use bindgen::callbacks::ParseCallbacks;

<<<<<<< HEAD
fn find_in_cpath(name: &str) -> Result<PathBuf, &str> {
    Ok(env::var("CPATH")
        .map_err(|_| "CPATH needs to be set (in unicode) so I can find include header files")?
        .split(':')
        .map(|path_str| PathBuf::from(path_str).join(name))
        .filter(|path| path.exists())
        .collect::<Vec<_>>()
        .first()
        .ok_or("name not found in CPATH")?
        .clone())
}

#[derive(Debug)]
struct LibprobeCallback;

/// These C-structs get prefixed with "C_" because a rust version of the struct will be
=======
#[derive(Debug)]
struct LibprobeCallback;

<<<<<<< HEAD
/// These C-structs get prefixed with "Bindgen_" because a rust version of the struct will be
>>>>>>> a83cce7 (version 0.2.0)
=======
/// These C-structs get prefixed with "C_" because a rust version of the struct will be
>>>>>>> f7c22ab (:sparkles: documentation :sparkles:)
/// either generated or manually implemented.
fn should_prefix(name: &str) -> bool {
    static LIST: OnceLock<HashSet<&'static str>> = OnceLock::new();
    LIST.get_or_init(|| {
        HashSet::from([
            "Path",
            "InitProcessOp",
            "InitExecEpochOp",
            "InitThreadOp",
            "OpenOp",
            "CloseOp",
            "ChdirOp",
            "ExecOp",
            "CloneOp",
            "ExitOp",
            "AccessOp",
            "StatOp",
            "ReaddirOp",
            "WaitOp",
            "GetRUsageOp",
            "MetadataKind",
            "MetadataValue",
            "UpdateMetadataOp",
            "ReadLinkOp",
            "OpCode",
            "Op",
            "statx",
            "rusage",
            "statx_timestamp",
            "timespec",
            "timeval",
        ])
    })
    .contains(name)
}

/// These structs are parts of tagged unions and so the rust versions of the structs can't (yet) be
/// autogenerated and have to be implemented manually
fn no_derive(name: &str) -> bool {
    static LIST: OnceLock<HashSet<&'static str>> = OnceLock::new();
    LIST.get_or_init(|| {
        HashSet::from([
            "MetadataKind",
            "MetadataValue",
            "UpdateMetadataOp",
            "OpCode",
            "Op",
        ])
    })
    .contains(name)
}

impl ParseCallbacks for LibprobeCallback {
    fn item_name(&self, _original_item_name: &str) -> Option<String> {
        if should_prefix(_original_item_name) {
<<<<<<< HEAD
<<<<<<< HEAD
            Some(format!("C_{}", _original_item_name))
=======
            Some(format!("Bindgen_{}", _original_item_name))
>>>>>>> a83cce7 (version 0.2.0)
=======
            Some(format!("C_{}", _original_item_name))
>>>>>>> f7c22ab (:sparkles: documentation :sparkles:)
        } else {
            None
        }
    }

    fn add_derives(&self, info: &bindgen::callbacks::DeriveInfo<'_>) -> Vec<String> {
        let mut ret = vec![];

        match info.kind {
            bindgen::callbacks::TypeKind::Struct => {
<<<<<<< HEAD
<<<<<<< HEAD
                let orig_name = info.name.strip_prefix("C_");
=======
                let orig_name = info.name.strip_prefix("Bindgen_");
>>>>>>> a83cce7 (version 0.2.0)
=======
                let orig_name = info.name.strip_prefix("C_");
>>>>>>> f7c22ab (:sparkles: documentation :sparkles:)
                if orig_name.is_some() && !no_derive(orig_name.unwrap()) {
                    ret.push("MakeRustOp".to_owned());
                }
            }
            bindgen::callbacks::TypeKind::Enum => (),
            bindgen::callbacks::TypeKind::Union => (),
        };

        ret
    }
}

fn main() {
    // Tell cargo to look for shared libraries in the specified directory
    // println!("cargo:rustc-link-search=/path/to/lib");

    // Tell cargo to tell rustc to link the system bzip2
    // shared library.
    // println!("cargo:rustc-link-lib=bz2");

    // The bindgen::Builder is the main entry point
    // to bindgen, and lets you build up options for
    // the resulting bindings.
    let bindings = bindgen::Builder::default()
        .header_contents(
            "wrapper",
            "
            #define _GNU_SOURCE
            #include <stdbool.h>
            #include <stddef.h>
            #include <stdint.h>
            #include <sys/stat.h>
            #include <sys/types.h>
            #include <utime.h>
<<<<<<< HEAD
            #include <threads.h>
            #include <pthread.h>
=======
>>>>>>> a83cce7 (version 0.2.0)

            // HACK: defining this manually instead of using <sys/resource.h> is
            // a huge hack, but it greatly reduces the generated code complexity
            // since in glibc all the long ints are unions over two types that
            // both alias to long int, this is done for kernel-userland
<<<<<<< HEAD
            // compatibility reasons that don't matter here.
=======
            // compatibilityreasons that don't matter here.
>>>>>>> a83cce7 (version 0.2.0)
            struct rusage {
                struct timeval ru_utime;
                struct timeval ru_stime;
                long int ru_maxrss;
                long int ru_ixrss;
                long int ru_idrss;
                long int ru_isrss;
                long int ru_minflt;
                long int ru_majflt;
                long int ru_nswap;
                long int ru_inblock;
                long int ru_oublock;
                long int ru_msgsnd;
                long int ru_msgrcv;
                long int ru_nsignals;
                long int ru_nvcsw;
                long int ru_nivcsw;
            };

            #define BORROWED
            #define OWNED
            ",
        )
        // The input header we would like to generate
        // bindings for.
<<<<<<< HEAD
        .header(
            find_in_cpath("libprobe/prov_ops.h")
                .unwrap()
                .into_os_string()
                .into_string()
                .unwrap(),
        )
=======
        .header("./include/prov_ops.h")
>>>>>>> a83cce7 (version 0.2.0)
        // .header_contents("sizeof", "
        //     const size_t OP_SIZE = sizeof(struct Op);
        // ")
        // only parse the Op type (and any types contained within, recursively)
        .allowlist_item("^(Op)$")
        // Tell cargo to invalidate the built crate whenever any of the
        // included header files changed.
        .parse_callbacks(Box::new(bindgen::CargoCallbacks::new()))
        .parse_callbacks(Box::new(LibprobeCallback {}))
        // Finish the builder and generate the bindings.
        .generate()
        // Unwrap the Result and panic on failure.
        .expect("Unable to generate bindings");

    // Write the bindings to the $OUT_DIR/bindings.rs file.
    let out_path = PathBuf::from(env::var("OUT_DIR").unwrap());
    bindings
        .write_to_file(out_path.join("bindings.rs"))
        .expect("Couldn't write bindings!");
}
