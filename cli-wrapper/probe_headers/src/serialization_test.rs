use eyre::{Result, WrapErr};
use std::str::FromStr;

fn main() -> Result<()> {
    let data_arena_dir = std::path::PathBuf::from_str("arenas/data")?;
    let ops_arena_dir = std::path::PathBuf::from_str("arenas/ops")?;
    let data_arena = {
        probe_headers::parse_arena_dir(&data_arena_dir)
            .wrap_err(format!("Failed to parse arena dir {data_arena_dir:?}"))?
    };

    let mut ops = vec![];

    let op_size = <probe_headers::Op as memory_parsing::SizedMemory>::size();
    std::fs::read_dir(&ops_arena_dir)
        .wrap_err(format!("Error opening ops directory {:?}", ops_arena_dir))?
        .map(|entry| {
            let ops_arena_file = entry.wrap_err("direntry")?.path();
            let range;
            let both_arenas;
            {
                let ops_arena_segment = probe_headers::parse_arena_file(&ops_arena_file).wrap_err(format!("parsing op segment in {:?}", ops_arena_file))?;
                let ops_arena_segments = memory_parsing::Segments::from_segment(ops_arena_segment.clone());
                range = ops_arena_segment.range().clone();
                both_arenas = data_arena.extend(&ops_arena_segments).wrap_err(format!("combining data arena with op arena 0x{:08x}--0x{:08x} in {:?}", ops_arena_segment.range().start, ops_arena_segment.range().end, ops_arena_file))?;
            }
            range
                .clone()
                .step_by(op_size)
                .map(|op_pointer| {
                    let ret = <probe_headers::Op as memory_parsing::FromMemory>::from_memory(
                        &both_arenas,
                        op_pointer,
                    )
                    .wrap_err(format!(
                        "Failed to parse op at 0x{op_pointer:08x} in op segment 0x{:08x}--0x{:08x}\n",
                        range.start,
                        range.end,
                        // memory_parsing::Segment::new(op_pointer, ops_arena_segment.get(op_pointer).unwrap()[..op_size].to_vec()),
                    ))?;
                    ops.push(ret.0.clone());
                    Ok(())
                })
                .collect::<Result<Vec<_>>>()
                .wrap_err(format!("parsing ops in {:?}", ops_arena_file))?;

            Ok(())
        })
        .collect::<Result<Vec<_>>>()?;

    Ok(())
}
