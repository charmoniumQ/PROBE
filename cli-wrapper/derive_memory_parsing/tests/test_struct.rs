#[derive(derive_memory_parsing::MemoryParsable, Debug, Clone, PartialEq, Eq)]
#[repr(C)]
struct Test1 {
    a: u64,
    b: u64,
}

#[derive(derive_memory_parsing::MemoryParsable, Debug, Clone, PartialEq, Eq)]
#[repr(C)]
struct Test2 {}

#[derive(derive_memory_parsing::MemoryParsable, Debug, Clone, PartialEq, Eq)]
#[repr(C)]
struct Test3(u64, u64, Test1);

#[derive(derive_memory_parsing::MemoryParsable, Debug, Clone, PartialEq, Eq)]
#[repr(C)]
struct Test4();

#[derive(derive_memory_parsing::MemoryParsable, Debug, Clone, PartialEq, Eq)]
#[repr(u8)]
enum Test5 {
    A,
    B(),
    C {},
    D(Test1),
    E { obj: Test3 },
}

fn main() {
    use memory_parsing::ToMemory;
    let offset = 0x10000;
    let mut memory = memory_parsing::Segments::single(offset, vec![0u8; 0x1000]);
    let value = (
        Test1 {
            a: 123845643,
            b: 7437984239,
        },
        Test2 {},
        Test3(
            3904781043,
            1847914978,
            Test1 {
                a: 1283971,
                b: 8912739128,
            },
        ),
        Test4(),
        Test5::A,
        Test5::B(),
        Test5::C {},
        Test5::D(Test1 {
            a: 1238947143,
            b: 239823978234,
        }),
        Test5::E {
            obj: Test3(
                231794239,
                23978243978243,
                Test1 {
                    a: 234789243789,
                    b: 89247324739,
                },
            ),
        },
    );
    value.to_memory(&mut memory, offset).unwrap();
    let (value2, _) = memory_parsing::FromMemory::from_memory(&memory, offset).unwrap();
    assert_eq!(value, value2);
}
