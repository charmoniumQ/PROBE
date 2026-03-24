use eyre::Result;
use memory_parsing::{Segment, Segments};
use std::path::Path;

#[repr(C)]
#[derive(Debug, Clone, derive_memory_parsing::MemoryParsable)]
pub struct ArenaHeader {
    pub instantiation: usize,
    pub base_address: usize,
    pub capacity: usize,
    pub used: usize,
}

fn parse_arena_bytes(bytes: Vec<u8>, expected_instantiation: Option<usize>) -> Result<Segment> {
    let header_size = std::mem::size_of::<ArenaHeader>();
    let arena_bytes = &bytes[..header_size];
    let memory = Segments::single(0, arena_bytes.to_vec());
    let header: ArenaHeader = memory_parsing::FromMemory::from_memory(&memory, 0)?.0;
    if header.capacity != bytes.len() {
        Err(eyre::eyre!(
            "Mismatch between header's stated capacity ({}) and byte region length ({})",
            header.capacity,
            bytes.len(),
        ))
    } else if header.used > header.capacity {
        Err(eyre::eyre!(
            "Header claims we used ({}) more than the capacity ({})",
            header.used,
            header.capacity
        ))
    } else if expected_instantiation
        .map(|e| header.instantiation != e)
        .unwrap_or(true)
    {
        Err(eyre::eyre!(
            "Header's instantiation ({}) doesn't match expected ({:?})",
            header.instantiation,
            expected_instantiation
        ))
    } else {
        let subset_bytes = bytes[header_size..header.used].to_vec();
        let subset_base_address = header.base_address + header_size;
        Ok(Segment::new(subset_base_address, subset_bytes))
    }
}

pub fn parse_arena_file<P: AsRef<Path> + std::fmt::Debug>(file: P) -> Result<Segment> {
    let expected_instantiation = file
        .as_ref()
        .file_stem()
        .ok_or(eyre::eyre!("No file stem"))?
        .to_str()
        .ok_or(eyre::eyre!("Not unicode"))?
        .parse::<usize>()
        .map_err(|e| eyre::eyre!("Could not parse {e:?}"))?;
    let bytes =
        std::fs::read(file.as_ref()).map_err(|e| eyre::eyre!("Could not read {file:?}: {e:?}"))?;
    parse_arena_bytes(bytes, Some(expected_instantiation))
}

pub fn parse_arena_dir<P: AsRef<Path> + std::fmt::Debug>(dir: P) -> Result<Segments> {
    use eyre::WrapErr;
    let segments = std::fs::read_dir(&dir)
        .with_context(|| format!("{dir:?}"))?
        .map(|entry| parse_arena_file(entry?.path()))
        .collect::<Result<Vec<_>>>()?;
    Segments::new(segments)
}
