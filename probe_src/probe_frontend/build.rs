use std::collections::HashSet;
use std::env;
use std::path::PathBuf;
use std::sync::OnceLock;

use bindgen::callbacks::ParseCallbacks;

#[derive(Debug)]
struct LibprobeCallback;

fn derive_list(name: &str) -> bool {
    static DERIVE_LIST: OnceLock<HashSet<&'static str>> = OnceLock::new();
    DERIVE_LIST
        .get_or_init(|| {
            HashSet::from([
                "CloneOp",
                "CloseOp",
                "ExitOp",
                "GetRUsageOp",
                "InitProcessOp",
                "InitThreadOp",
                "MetadataValue__bindgen_ty_1",
                "MetadataValue__bindgen_ty_2",
                "WaitOp",
                "rusage",
                "statx",
                "statx_timestamp",
                "timespec",
                "timeval",
            ])
        })
        .contains(name)
}

impl ParseCallbacks for LibprobeCallback {
    fn add_derives(&self, info: &bindgen::callbacks::DeriveInfo<'_>) -> Vec<String> {
        if derive_list(info.name) {
            vec!["Serialize".to_owned(), "Deserialize".to_owned()]
        } else {
            vec![]
        }
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
            
            // defining this manually instead of using <sys/resource.h> is a
            // hack, but it greatly reduces the generated code complexity since
            // in glibc all the long ints are unions over two types that both 
            // alias to long int, this is done for kernel-userland compatibility
            // reasons that don't matter here.
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
        .header("./include/prov_ops.h")
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
