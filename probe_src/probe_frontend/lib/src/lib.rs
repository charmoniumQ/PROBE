
/// Op definitions
///
/// While simple Ops containing only Integral values can be used/serialized directory from
/// libprobe, more complicated structs containing pointers (usually in the form of strings) need to
/// be manually converted to versions so they can be serialized. This module re-exports the trivial
/// structs and defines new ones (as well as methods for converting) for the non-trivial structs.
///
/// Raw ffi bindings for the raw C-structs emitted by libprobe, generated automatically with
/// rust-bindgen (these start with `Bindgen_`.
///
/// If you're trying to make sense of this it's going to be much easier if you have `prov_ops.h`
/// open as well.
pub mod ops;

/// Transcribe raw Bindgen Ops from libprobe to usable, serializable data.
///
/// # Serialization format
///
/// The serialization format output is very similar to the raw libprobe arena format. It's a
/// filesystem hierarchy of `<PID>/<EXEC_EPOCH>/<TID>` but instead of `<TID>` being a directory containing
/// `ops` and `data` directories with the raw C-struct arenas, `<TID>` is a
/// [jsonlines](https://jsonlines.org/) file, where each line is a json representation of an
/// [`ops::Op`].
pub mod transcribe;

// currently unused, get system metadata
mod metadata;

/// Library error type and definitions.
pub mod error;

