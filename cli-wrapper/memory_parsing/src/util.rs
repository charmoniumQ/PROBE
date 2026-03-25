use crate::segments::Segments;

pub(crate) fn primitive_from_bytes<Type: Sized + Clone>(
    memory: &Segments,
    pointer: usize,
) -> eyre::Result<(Type, usize)> {
    let size = std::mem::size_of::<Type>();
    let type_ = std::any::type_name::<Type>();
    match memory.get(pointer) {
        Some(bytes) => {
            let memory_length = bytes.len();
            if size <= memory_length {
                let object = unsafe { (*(bytes.as_ptr() as *const Type)).clone() };
                Ok((object, pointer + size))
            } else {
                Err(eyre::eyre!(
                    "Memory at 0x{pointer:08x} is only 0x{memory_length:08x} long; need 0x{size:08x} for {type_}"
                ))
            }
        }
        None => Err(eyre::eyre!("{pointer} not mapped")),
    }
}

pub(crate) fn primitive_to_bytes<Type: Sized>(
    memory: &mut Segments,
    pointer: usize,
    object: &Type,
) -> eyre::Result<usize> {
    let size = std::mem::size_of::<Type>();
    let type_ = std::any::type_name::<Type>();
    let bytes = unsafe {
        core::slice::from_raw_parts(
            (object as *const Type) as *const u8,
            std::mem::size_of::<Type>(),
        )
    };
    assert_eq!(size, bytes.len(), "{type_} {bytes:?}");
    match memory.get_mut(pointer) {
        Some(byte_dest) => {
            let memory_length = byte_dest.len();
            if size <= memory_length {
                byte_dest[..size].copy_from_slice(bytes);
                Ok(pointer + size)
            } else {
                Err(eyre::eyre!(
                    "Memory at 0x{pointer:08x} is only 0x{memory_length:08x} long; need 0x{size:08x} for {type_}"
                ))
            }
        }
        None => Err(eyre::eyre!("{pointer} not mapped")),
    }
}
