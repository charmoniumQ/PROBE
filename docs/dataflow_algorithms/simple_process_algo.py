"""
This algo just connects inodes to processes.

Downside, is you don't know which inode writers connect to which inode readers, if there are multiple inode writers.
"""

@charmonium.time_block.decor(print_start=False)
def hb_graph_to_dataflow_graph_simple(
        probe_log: ptypes.ProbeLog,
) -> tuple[
    DataflowGraph,
    Map[ptypes.Inode, frozenset[pathlib.Path]],
    ptypes.HbGraph,
    graph_utils.ReachabilityOracle[ptypes.OpQuad] | None,
]:
    # Find the HBG
    hbg = hb_graph.probe_log_to_hb_graph(probe_log)

    dataflow_graph: UncompressedDataflowGraph = networkx.DiGraph()

    ee_to_init = {}
    for quad in hbg.nodes():
        op_data = probe_log.get_op(quad).data
        if isinstance(op_data, ops.InitExecEpochOp):
            ee_to_init[quad.exec_pair()] = quad

    inode_versions: dict[ptypes.Inode, int] = {}
    inode_to_paths = collections.defaultdict[ptypes.Inode, set[pathlib.Path]](set)
    cwds = dict[ptypes.Pid, pathlib.Path]()

    for quad in tqdm.tqdm(networkx.topological_sort(hbg), desc="dfg", total=len(hbg.nodes())):
        op_data = probe_log.get_op(quad).data
        match op_data:
            case ops.InitExecEpochOp():
                new_cwd = _to_path(cwds, inode_to_paths, quad, op_data.cwd)
                if new_cwd:
                    cwds[quad.pid] = new_cwd
                inode_version = ptypes.InodeVersion.from_probe_path(op_data.exe)
                exe_path = _to_path(cwds, inode_to_paths, quad, op_data.exe)
                if exe_path:
                    inode_to_paths[inode_version.inode].add(exe_path)
            case ops.OpenOp():
                if op_data.ferrno != 0:
                    inode = ptypes.InodeVersion.from_probe_path(op_data.path).inode
                    access = ptypes.AccessMode.from_open_flags(op_data.flags)
                    path = _to_path(cwds, inode_to_paths, quad, op_data.path)
                    if path:
                        inode_to_paths[inode].add(path)
                        if access.is_read:
                            version = inode_versions.get(inode, -1)
                            ivn = InodeVersionNode(inode, version)
                            dataflow_graph.add_edge(ivn, ee_to_init[quad.exec_pair()])
                        if access.is_write:
                            old_version = inode_versions.get(inode, -1)
                            new_version = old_version + 1
                            new_ivn = InodeVersionNode(inode, version + 1)
                            if access.is_mutating_write:
                                old_ivn = InodeVersionNode(inode, version)
                                dataflow_graph.add_edge(old_ivn, new_ivn)
                            inode_versions[inode] = new_version
                            dataflow_graph.add_edge(ee_to_init[quad.exec_pair()], new_ivn)
            case ops.ChdirOp():
                path = _to_path(cwds, inode_to_paths, quad, op_data.path)
                if path:
                    cwds[quad.pid] = path
            case ops.CloneOp():
                if op_data.task_type == ptypes.TaskType.TASK_PID:
                    dataflow_graph.add_edge(
                        ee_to_init[quad.exec_pair()],
                        ee_to_init[ptypes.ExecPair(ptypes.Pid(op_data.task_id), ptypes.ExecNo(0))],
                    )
            case ops.ExecOp():
                if op_data.ferrno == 0:
                    target = ptypes.ExecPair(quad.pid, ptypes.ExecNo(quad.exec_no + 1))
                    if target in ee_to_init:
                        dataflow_graph.add_edge(
                            ee_to_init[quad.exec_pair()],
                            ee_to_init[ptypes.ExecPair(quad.pid, ptypes.ExecNo(quad.exec_no + 1))],
                        )
                    else:
                        warnings.warn(ptypes.UnusualProbeLog(f"Next exec of {quad} is not traced"))

    inode_to_paths2 = {
        key: frozenset(val)
        for key, val in inode_to_paths.items()
    }

    return null_compression(dataflow_graph), inode_to_paths2, hbg, None


