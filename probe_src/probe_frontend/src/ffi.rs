#![allow(non_upper_case_globals)]
#![allow(non_camel_case_types)]
#![allow(non_snake_case)]

/// raw ffi bindings for the raw C-structs emitted by libprobe, generated automatically with
/// rust-bindgen
use serde::{Deserialize, Serialize};

include!(concat!(env!("OUT_DIR"), "/bindings.rs"));
