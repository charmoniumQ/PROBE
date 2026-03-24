use crate::{
    align_pointer, is_aligned, FromMemory, Result, Segments, SizedMemory, ToMemory, LOGGING,
};
use eyre::eyre;

#[derive(PartialEq, Eq, Clone, Debug)]
pub struct ByteString(pub Vec<u8>);

impl schemars::JsonSchema for ByteString {
    fn schema_name() -> std::borrow::Cow<'static, str> {
        "ByteString".into()
    }
    fn json_schema(generator: &mut schemars::SchemaGenerator) -> schemars::Schema {
        Vec::<u8>::json_schema(generator)
    }
}

impl SizedMemory for ByteString {
    fn align() -> usize {
        <usize as SizedMemory>::align()
    }
    fn size() -> usize {
        <usize as SizedMemory>::size()
    }
    fn offsets() -> Vec<usize> {
        <usize as SizedMemory>::offsets()
    }
    fn c_name() -> Option<&'static str> {
        Some("ByteString")
    }
}

impl FromMemory for ByteString {
    fn from_memory(memory: &Segments, pointer: usize) -> Result<(Self, usize)> {
        assert!(is_aligned::<Self>(pointer));
        if LOGGING {
            eprintln!("(nonnull char*) mem[0x{pointer:08x}] = ");
        }
        let (string_pointer, new_pointer) = <usize as FromMemory>::from_memory(memory, pointer)?;
        match string_pointer {
            0 => {
                if LOGGING {
                    eprintln!("= (nonnull char*) NULL");
                }
                Err(eyre!("Expected string to be nonnull"))
            }
            _ => {
                if LOGGING {
                    eprintln!("= (nonnull char*) 0x{string_pointer:08x}");
                    eprintln!("(char) mem[0x{string_pointer:08x}] = ");
                }
                match memory.get(string_pointer) {
                    Some(bytes) => {
                        let mut n_elements = 0;
                        while bytes[n_elements] != 0u8 {
                            n_elements += 1;
                            if n_elements > bytes.len() {
                                return Err(eyre!("Could not find null-byte in string at 0x{string_pointer:08x} until end of memory segment {}", string_pointer + n_elements));
                            }
                        }
                        let string = bytes[..n_elements].to_vec();
                        if LOGGING {
                            eprintln!("= (char) {string:?} ({n_elements})");
                        }
                        Ok((Self(string), new_pointer))
                    }
                    None => Err(eyre!(
                        "0x{string_pointer:08x} is not mapped (trying for CString)"
                    )),
                }
            }
        }
    }
}
impl ToMemory for ByteString {
    fn to_memory(&self, memory: &mut Segments, pointer: usize) -> Result<usize> {
        assert!(is_aligned::<Self>(pointer));
        let len = self.0.len();
        let string_pointer = memory.alloc(len + 1).ok_or(eyre!("allocation failed"))?;
        match memory.get_mut(string_pointer) {
            Some(bytes) => {
                bytes[..len].copy_from_slice(&self.0[..]);
                bytes[len] = b'\0';
                if LOGGING {
                    eprintln!(
                        "(char) memory[0x{string_pointer:08x}] = {:?}",
                        memory.get(string_pointer).unwrap()[0]
                    );
                    eprintln!("...");
                    let end = string_pointer + len;
                    eprintln!(
                        "(char) memory[0x{end:08x}] = {:?}",
                        memory.get(end).unwrap()[0]
                    );
                    eprintln!("(char*) memory[0x{pointer:08x}] = 0x{string_pointer:08x}");
                }
                string_pointer.to_memory(memory, pointer)
            }
            None => Err(eyre!("0x{pointer:08x} that alloc returned is not mapped")),
        }
    }
}

impl serde::Serialize for ByteString {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        serializer.serialize_bytes(&self.0[..])
    }
}

#[cfg(test)]
#[test]
fn test_deserialize_nonnull_string() -> Result<()> {
    let value = (
        ByteString(c"abcdef".to_bytes().to_owned()),
        ByteString(c"hello world".to_bytes().to_owned()),
        ByteString(c"ohaefi".to_bytes().to_owned()),
    );
    let offset = 0x10000;
    let mut memory = Segments::single(offset, vec![0; 256]);
    value.to_memory(&mut memory, offset)?;
    let (value2, _) = FromMemory::from_memory(&memory, offset)?;
    assert_eq!(value, value2);
    Ok(())
}

impl SizedMemory for Option<ByteString> {
    fn align() -> usize {
        <usize as SizedMemory>::align()
    }
    fn size() -> usize {
        <usize as SizedMemory>::size()
    }
    fn offsets() -> Vec<usize> {
        <usize as SizedMemory>::offsets()
    }
    fn c_name() -> Option<&'static str> {
        Some("Option_ByteString")
    }
}

impl FromMemory for Option<ByteString> {
    fn from_memory(memory: &Segments, pointer: usize) -> Result<(Self, usize)> {
        assert!(is_aligned::<Self>(pointer));
        if LOGGING {
            eprintln!("(nullable char*) mem[0x{pointer:08x}] = ");
        }
        let (string_pointer, new_pointer) = <usize as FromMemory>::from_memory(memory, pointer)?;
        match string_pointer {
            0 => {
                if LOGGING {
                    eprintln!("= (nullable char*) NULL");
                }
                Ok((None, new_pointer))
            }
            _ => {
                let (byte_string, _) = <ByteString as FromMemory>::from_memory(memory, pointer)?;
                if LOGGING {
                    eprintln!("= (nullable char*) {byte_string:?}");
                }
                Ok((Some(byte_string), new_pointer))
            }
        }
    }
}
impl ToMemory for Option<ByteString> {
    fn to_memory(&self, memory: &mut Segments, pointer: usize) -> Result<usize> {
        assert!(is_aligned::<Self>(pointer));
        match &self {
            None => 0usize.to_memory(memory, pointer),
            Some(string) => string.to_memory(memory, pointer),
        }
    }
}

#[cfg(test)]
#[test]
fn test_deserialize_nullable_string() -> Result<()> {
    let value = (
        Some(ByteString(c"abcdef".to_bytes().to_owned())),
        None,
        Some(ByteString(c"ohaefi".to_bytes().to_owned())),
    );
    let offset = 0x10000;
    let mut memory = Segments::single(offset, vec![0; 256]);
    value.to_memory(&mut memory, offset)?;
    let (value2, _) = FromMemory::from_memory(&memory, offset)?;
    assert_eq!(value, value2);
    Ok(())
}

#[derive(PartialEq, Eq, Clone)]
pub struct StringArray(pub Vec<Vec<u8>>);

impl std::fmt::Debug for StringArray {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let (slice, ellipsis) = if self.0.len() > 10 {
            (&self.0[..10], true)
        } else {
            (&self.0[..], false)
        };
        f.write_str("[")?;
        for (i, string) in slice.iter().enumerate() {
            let string = string
                .iter()
                .map(|&chr| if chr.is_ascii() { chr as char } else { '�' })
                .collect::<String>();
            f.write_str(&string)?;
            if i != self.0.len() - 1 {
                f.write_str(", ")?;
            }
        }
        if ellipsis {
            f.write_str(", ...")?;
        }
        f.write_str("]")?;
        Ok(())
    }
}

impl schemars::JsonSchema for StringArray {
    fn schema_name() -> std::borrow::Cow<'static, str> {
        "StringArray".into()
    }
    fn json_schema(generator: &mut schemars::SchemaGenerator) -> schemars::Schema {
        Vec::<Vec<u8>>::json_schema(generator)
    }
}

impl SizedMemory for StringArray {
    fn align() -> usize {
        <usize as SizedMemory>::align()
    }
    fn size() -> usize {
        <usize as SizedMemory>::size()
    }
    fn offsets() -> Vec<usize> {
        <usize as SizedMemory>::offsets()
    }
    fn c_name() -> Option<&'static str> {
        Some("StringArray")
    }
}
impl FromMemory for StringArray {
    fn from_memory(memory: &Segments, pointer: usize) -> Result<(Self, usize)> {
        assert!(is_aligned::<Self>(pointer));
        if LOGGING {
            eprintln!("(char**) mem[0x{pointer:08x}] = ");
        }
        let (mut string_array_pointer, pointer_after_pointer) =
            <usize as FromMemory>::from_memory(memory, pointer)?;
        let mut ret = vec![];
        loop {
            match <Option<ByteString> as FromMemory>::from_memory(memory, string_array_pointer)? {
                (None, _) => break,
                (Some(string), next_string_array_pointer) => {
                    // TODO: unfortunate clone
                    ret.push(string.0.clone());
                    string_array_pointer = next_string_array_pointer;
                }
            }
        }
        Ok((StringArray(ret), pointer_after_pointer))
    }
}
impl ToMemory for StringArray {
    fn to_memory(&self, memory: &mut Segments, pointer: usize) -> Result<usize> {
        assert!(is_aligned::<Self>(pointer));
        let array_pointer = memory
            .alloc((self.0.len() + 1) * 8)
            .ok_or(eyre::eyre!("Alloc failed"))?;
        let mut next_string_pointer = array_pointer;
        for string in self.0.iter() {
            // TODO: unfortunate clone
            let value = ByteString(string.clone());
            next_string_pointer = value.to_memory(memory, next_string_pointer)?;
        }
        0usize.to_memory(memory, next_string_pointer)?;
        array_pointer.to_memory(memory, pointer)
    }
}

impl serde::Serialize for StringArray {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: serde::Serializer,
    {
        use serde::ser::SerializeSeq;
        let mut sequence_serializer = serializer.serialize_seq(Some(self.0.len()))?;
        for string in self.0.iter() {
            sequence_serializer.serialize_element(serde_bytes::Bytes::new(&string[..]))?;
        }
        sequence_serializer.end()
    }
}

#[cfg(test)]
#[test]
fn test_deserialize_cstring_array() -> Result<()> {
    let value = StringArray(vec![
        c"abcdef".to_bytes().to_owned(),
        c"hello".to_bytes().to_owned(),
        c"ohaefila".to_bytes().to_owned(),
    ]);
    let offset = 0x10000;
    let mut memory = Segments::single(offset, vec![0; 256]);
    value.to_memory(&mut memory, offset)?;
    let (value2, _) = <StringArray as FromMemory>::from_memory(&memory, offset)?;
    assert_eq!(value, value2);
    Ok(())
}

impl<Type: SizedMemory + Default + Copy + std::fmt::Debug, const LENGTH: usize> SizedMemory
    for [Type; LENGTH]
{
    fn align() -> usize {
        <Type as SizedMemory>::align()
    }
    fn size() -> usize {
        align_pointer::<Type>(<Type as SizedMemory>::size()) * LENGTH
    }
    fn offsets() -> Vec<usize> {
        (0..Self::size())
            .step_by(align_pointer::<Type>(<Type as SizedMemory>::size()))
            .collect()
    }
}
