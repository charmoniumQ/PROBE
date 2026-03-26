use color_eyre::eyre::{eyre, Result, WrapErr};
use std::path::Path;

pub(crate) fn transcribe_to_tar<P: AsRef<Path>, T: std::io::Write>(
    record_dir: P,
    tar: &mut tar::Builder<T>,
) -> Result<()> {
    let log_dir = tempfile::TempDir::new()?;
    transcribe_to_dir(record_dir, &log_dir)?;
    tar.append_dir_all(".", &log_dir)?;
    tar.finish()?;
    Ok(())
}

fn transcribe_to_dir<P1: AsRef<Path>, P2: AsRef<Path>>(in_dir: P1, out_dir: P2) -> Result<()> {
    transcribe_process_tree_context(&in_dir, &out_dir)?;
    copy_inodes(&in_dir, &out_dir)?;
    transcribe_ops(&in_dir, &out_dir)?;
    Ok(())
}

fn transcribe_process_tree_context<P1: AsRef<Path>, P2: AsRef<Path>>(
    in_dir: P1,
    out_dir: P2,
) -> Result<()> {
    let ptc_file = in_dir
        .as_ref()
        .join(probe_headers::PROCESS_TREE_CONTEXT_FILE);
    let ptc_mem = memory_parsing::Segments::single(0, std::fs::read(ptc_file)?);
    let ptc = <probe_headers::ProcessTreeContext as memory_parsing::FromMemory>::from_memory(
        &ptc_mem, 0,
    )?
    .0;
    let mut file = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(out_dir.as_ref().join("process_tree_context.msgpack"))?;
    let mut serializer = rmp_serde::encode::Serializer::new(&mut file).with_struct_map();
    use serde::Serialize;
    ptc.serialize(&mut serializer)?;
    Ok(())
}

fn copy_inodes<P1: AsRef<Path>, P2: AsRef<Path>>(in_dir: P1, out_dir: P2) -> Result<()> {
    let inodes_in_dir = in_dir.as_ref().join(probe_headers::INODES_SUBDIR);
    let inodes_out_dir = out_dir.as_ref().join(probe_headers::INODES_SUBDIR);
    std::fs::create_dir(&inodes_out_dir)?;
    std::fs::read_dir(inodes_in_dir.clone())?
        .map(|inode_contents| {
            let name = inode_contents?.file_name();
            std::fs::hard_link(inodes_in_dir.join(name.clone()), inodes_out_dir.join(name))?;
            Ok(1usize)
        })
        .collect::<Result<Vec<_>>>()?;
    Ok(())
}

fn transcribe_ops<P1: AsRef<Path>, P2: AsRef<Path>>(in_dir: P1, out_dir: P2) -> Result<()> {
    let pids_out_dir = out_dir.as_ref().join(probe_headers::PIDS_SUBDIR);
    std::fs::create_dir(&pids_out_dir)?;
    std::fs::read_dir(in_dir.as_ref().join(probe_headers::PIDS_SUBDIR))?
        .map(|entry| {
            let pid_in_dir = entry?.path();
            let pid = filename_numeric(&pid_in_dir)?;
            let pid_out_dir = pids_out_dir.join(pid.to_string());
            transcribe_pid(&pid_in_dir, pid_out_dir)
        })
        .collect::<Result<Vec<_>>>()?;
    Ok(())
}

fn transcribe_pid<P1: AsRef<Path>, P2: AsRef<Path>>(pid_in_dir: P1, pid_out_dir: P2) -> Result<()> {
    std::fs::create_dir(&pid_out_dir)?;
    std::fs::read_dir(&pid_in_dir)?
        .map(|entry| {
            let exec_in_dir = entry?.path();
            let exec = filename_numeric(&exec_in_dir)?;
            let exec_out_dir = pid_out_dir.as_ref().join(exec.to_string());
            transcribe_exec(&exec_in_dir, exec_out_dir)
        })
        .collect::<Result<Vec<_>>>()?;
    Ok(())
}

fn transcribe_exec<P1: AsRef<Path>, P2: AsRef<Path>>(
    exec_in_dir: P1,
    exec_out_dir: P2,
) -> Result<()> {
    std::fs::create_dir(&exec_out_dir).wrap_err("Failed to create ExecEpoch output directory")?;
    std::fs::read_dir(&exec_in_dir)
        .wrap_err("Error opening ExecEpoch directory")?
        .map(|entry| {
            let tid_in_dir = entry?.path();
            let tid = filename_numeric(&tid_in_dir)?;
            let tid_out_file = exec_out_dir.as_ref().join(tid.to_string());
            transcribe_tid(&tid_in_dir, tid_out_file)
        })
        .collect::<Result<Vec<_>>>()?;
    Ok(())
}

pub fn transcribe_tid<P1: AsRef<Path>, P2: AsRef<Path>>(
    tid_in_dir: P1,
    tid_out_file: P2,
) -> Result<()> {
    let data_arena_dir = tid_in_dir.as_ref().join(probe_headers::DATA_SUBDIR);
    let ops_arena_dir = tid_in_dir.as_ref().join(probe_headers::OPS_SUBDIR);
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

    let mut tid_out_file = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(tid_out_file)?;
    {
        let mut serializer =
            rmp_serde::encode::Serializer::new(&mut tid_out_file).with_struct_map();
        use serde::Serialize;
        ops.serialize(&mut serializer)?;
    }

    Ok(())
}

fn filename_numeric<P: AsRef<Path>>(dir: P) -> Result<usize> {
    dir.as_ref()
        .file_stem()
        .ok_or(eyre!("File has no stem"))?
        .to_str()
        .ok_or(eyre!("Unable to parse as Unicode"))?
        .parse::<usize>()
        .map_err(|err| eyre!("{:?}", err))
}
