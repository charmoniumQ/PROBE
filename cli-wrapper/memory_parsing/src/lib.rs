/*!
 * This create defines [Segment], [Segments], [FromMemory], and [ToMemory].
 *
 * [FromMemory] and [ToMemory] is a non-self-describing, binary format that is natively understood by C.
 * For example, in Postcard, to serialize a variable-sized string, one just writes the bytes of the string.
 * But structs in C have to have fixed size, so the message would not be transparently interpretable as a struct.
 * Instead, C uses _indirection_: in place of the string, we write a fixed-width integer (pointer) referring to elsewhere where the bytes actually are.
 *
 * */

mod segments;
mod strings;
mod util;

use eyre::Result;

pub use segments::{Segment, Segments};
pub use strings::{ByteString, StringArray};

/*
Invariant: Size % Align == 0
*/
pub trait SizedMemory {
    fn size() -> usize;
    fn align() -> usize;
    /* Address of fields (impl defined) within this object. */
    fn offsets() -> Vec<usize>;
    fn c_name() -> Option<&'static str> {
        None
    }
}

pub trait FromMemory: SizedMemory {
    fn from_memory(segments: &Segments, pointer: usize) -> Result<(Self, usize)>
    where
        Self: Sized;
}

pub trait ToMemory: SizedMemory {
    fn to_memory(&self, segments: &mut Segments, pointer: usize) -> Result<usize>;
}

const LOGGING: bool = false;

impl SizedMemory for () {
    fn size() -> usize {
        0
    }
    fn align() -> usize {
        1
    }
    fn offsets() -> Vec<usize> {
        vec![]
    }
}

impl FromMemory for () {
    fn from_memory(_memory: &Segments, pointer: usize) -> Result<(Self, usize)> {
        Ok(((), pointer))
    }
}
impl ToMemory for () {
    fn to_memory(&self, _memory: &mut Segments, pointer: usize) -> Result<usize> {
        Ok(pointer)
    }
}

pub fn align_pointer<Type: SizedMemory>(pointer: usize) -> usize {
    let align = <Type as SizedMemory>::align();
    let remainder = pointer % align;
    if remainder != 0 {
        pointer + align - remainder
    } else {
        pointer
    }
}

fn is_aligned<Type: SizedMemory>(pointer: usize) -> bool {
    pointer.is_multiple_of(Type::align())
}

macro_rules! impl_memory_parsable_for_tuple {
    ( $($num:literal),* ) => {
        pastey::paste!{
            impl<$([<T $num>]: std::fmt::Debug + SizedMemory),*> SizedMemory for ($([<T $num>],)*) {
                fn size() -> usize {
                    let offset = 0;
                    $(
                        let offset = align_pointer::<[<T $num>]>(offset);
                        let offset = offset + <[<T $num>] as SizedMemory>::size();
                    )*
                    align_pointer::<Self>(offset)
                }
                fn align() -> usize {
                    let offset = 1;
                    $(
                        let offset = offset.max(<[<T $num>] as SizedMemory>::align());
                    )*
                    offset
                }
                fn offsets() -> Vec<usize> {
                    let mut ret = vec![];
                    let offset = 0;
                    $(
                        let offset = align_pointer::<[<T $num>]>(offset);
                        ret.push(offset);
                        #[allow(unused_variables)] /* the very last offset will be unused */
                        let offset = offset + <[<T $num>] as SizedMemory>::size();
                    )*
                    ret
                }
            }
            impl<$([<T $num>]: std::fmt::Debug + FromMemory),*> FromMemory for ($([<T $num>],)*) {
                fn from_memory(memory: &Segments, pointer: usize) -> Result<(Self, usize)> {
                    assert!(is_aligned::<Self>(pointer));
                    if LOGGING {
                        eprintln!("(tuple) mem[0x{pointer:08x}]");
                    }
                    $(
                        let pointer = align_pointer::<[<T $num>]>(pointer);
                        if LOGGING {
                            let type_name = std::any::type_name::< [<T $num>] >();
                            eprintln!("(tuple.{} {type_name}) mem[0x{pointer:08x}]", $num);
                        }
                        let [<ret $num>] = FromMemory::from_memory(memory, pointer);
                        if LOGGING {
                            let type_name = std::any::type_name::< [<T $num>] >();
                            match &[<ret $num>] {
                                Ok((obj, _)) => eprintln!("= (tuple.{} {type_name}) {obj:?}", $num),
                                Err(err) => eprintln!("err for {type_name}: {err:?}"),
                            }
                        }
                        let ([<t $num>], pointer) = [<ret $num>]?;
                    )*
                    Ok((($([<t $num>],)*), align_pointer::<Self>(pointer)))
                }
            }
            impl<$([<T $num>]: std::fmt::Debug + ToMemory),*> ToMemory for ($([<T $num>],)*) {
                fn to_memory(&self, memory: &mut Segments, pointer: usize) -> Result<usize> {
                    assert!(is_aligned::<Self>(pointer), "{}", std::any::type_name::<($([<T $num>],)*)>());
                    $(
                        let pointer = align_pointer::<[<T $num>]>(pointer);
                        if LOGGING {
                            let type_name = std::any::type_name::< [<T $num>] >();
                            eprintln!("(tuple.{} {type_name}) mem[0x{pointer:08x}] = {:?}", $num, self.$num);
                        }
                        let pointer = self.$num.to_memory(memory, pointer)?;
                    )*
                    Ok(align_pointer::<Self>(pointer))
                }
            }
        }
    }
}

impl_memory_parsable_for_tuple!(0);
impl_memory_parsable_for_tuple!(0, 1);
impl_memory_parsable_for_tuple!(0, 1, 2);
impl_memory_parsable_for_tuple!(0, 1, 2, 3);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5, 6);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5, 6, 7);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5, 6, 7, 8);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5, 6, 7, 8, 9);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15);
impl_memory_parsable_for_tuple!(0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16);

macro_rules! impl_memory_parsable_for_primitive {
    ( $($ty:ident)* ) => {
        $(
            impl SizedMemory for $ty {
                fn align() -> usize {
                    std::mem::align_of::<$ty>()
                }
                fn size() -> usize {
                    std::mem::size_of::<$ty>()
                }
                fn offsets() -> Vec<usize> { vec![0] }
                fn c_name() -> Option<&'static str> {
                    Some(std::any::type_name::<$ty>())
                }
            }
            impl FromMemory for $ty {
                fn from_memory(memory: &Segments, pointer: usize) -> Result<(Self, usize)> {
                    assert!(is_aligned::<Self>(pointer));
                    let (object, pointer) = util::primitive_from_bytes::<$ty>(memory, pointer)?;
                    if LOGGING {
                        let type_name = std::any::type_name::<$ty>();
                        eprintln!("mem[0x{pointer:08x}] = {object} (prim {type_name})")
                    }
                    Ok((object, align_pointer::<Self>(pointer)))
                }
            }
            impl ToMemory for $ty {
                fn to_memory(&self, memory: &mut Segments, pointer: usize) -> Result<usize> {
                    assert!(is_aligned::<Self>(pointer));
                    if LOGGING {
                        let type_name = std::any::type_name::<$ty>();
                        eprintln!("({type_name}) mem[0x{pointer:08x}] = {self:?}");
                    }
                    util::primitive_to_bytes::<$ty>(memory, pointer, self)
                }
            }
        )*
    }
}

impl_memory_parsable_for_primitive!(u8 u16 u32 u64 u128 usize i8 i16 i32 i64 i128 isize f32 f64 bool char);

impl<T: SizedMemory> SizedMemory for &T {
    fn align() -> usize {
        <T as SizedMemory>::align()
    }
    fn size() -> usize {
        <T as SizedMemory>::size()
    }
    fn offsets() -> Vec<usize> {
        <T as SizedMemory>::offsets()
    }
    fn c_name() -> Option<&'static str> {
        <T as SizedMemory>::c_name()
    }
}
impl<T: ToMemory> ToMemory for &T {
    fn to_memory(&self, memory: &mut Segments, pointer: usize) -> Result<usize> {
        (*self).to_memory(memory, pointer)
    }
}

#[cfg(test)]
#[test]
fn test_parse_int() -> Result<()> {
    let value = (
        123u8,
        1239u16,
        2478133u32,
        1392480984392u64,
        -1392480984392i64,
    );
    let offset = 0x10000;
    let mut memory = Segments::single(offset, vec![0; 256]);
    value.to_memory(&mut memory, offset)?;
    let (value2, _) = FromMemory::from_memory(&memory, offset)?;
    assert_eq!(value, value2);
    Ok(())
}

impl<Type: FromMemory + Default + Copy + std::fmt::Debug, const LENGTH: usize> FromMemory
    for [Type; LENGTH]
{
    fn from_memory(memory: &Segments, pointer: usize) -> Result<(Self, usize)> {
        assert!(is_aligned::<Self>(pointer));
        let mut ret = [Type::default(); LENGTH];
        if LOGGING {
            eprint!(
                "({}[{LENGTH}]) mem[0x{pointer:08x}] = ",
                std::any::type_name::<Type>()
            );
        }
        let new_pointer = (0..LENGTH).try_fold(
            pointer,
            |elem_pointer: usize, idx: usize| -> Result<usize> {
                let element = <Type as FromMemory>::from_memory(memory, elem_pointer);
                let element_unwrapped = element?;
                ret[idx] = element_unwrapped.0;
                Ok(element_unwrapped.1)
            },
        )?;
        if LOGGING {
            eprintln!("{ret:?}");
        }
        Ok((ret, new_pointer))
    }
}
impl<Type: ToMemory + Default + Copy + std::fmt::Debug, const LENGTH: usize> ToMemory
    for [Type; LENGTH]
{
    fn to_memory(&self, memory: &mut Segments, pointer: usize) -> Result<usize> {
        assert!(is_aligned::<Self>(pointer));
        self.iter()
            .try_fold(pointer, |pointer, elem| elem.to_memory(memory, pointer))
    }
}
