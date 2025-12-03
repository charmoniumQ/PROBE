from __future__ import annotations
import pathlib
import warnings
import charmonium.time_block
import networkx
import tqdm
from .dataflow_graph import (
    DataflowGraph,
    InodeVersionNode,
    It,
    IVNs,
    Map,
    Quads,
    Seq,
    _is_interesting_for_dataflow,
    add_inode_intervals,
    compressed_dfg_node_flattener,
    find_intervals,
)
from . import graph_utils
from . import hb_graph
from . import ops
from . import ptypes
from . import util



@charmonium.time_block.decor(print_start=False)
def hb_graph_to_dataflow_graph(
        probe_log: ptypes.ProbeLog,
) -> tuple[
    DataflowGraph,
    Map[ptypes.Inode, It[pathlib.Path]],
    ptypes.HbGraph,
    graph_utils.ReachabilityOracle[ptypes.OpQuad],
]:
    # Find the HBG
    hbg = hb_graph.probe_log_to_hb_graph(probe_log)

    # Remove unnecessary nodes
    hbg = hb_graph.retain_only(probe_log, hbg, _is_interesting_for_dataflow)

    # Find the ops in each thread, which is lesser than the total ops after we do retain
    thread_to_ops: Map[ptypes.ThreadTriple, Seq[ptypes.OpQuad]] = util.groupby_dict(
        hbg.nodes(),
        key_func=lambda quad: quad.thread_triple(),
        map_func=lambda _, quads: sorted(quads, key=lambda quad: quad.op_no),
    )
    exec_to_quads: Map[ptypes.ExecPair, Quads] = util.groupby_dict(
        hbg.nodes(),
        key_func=lambda quad: quad.exec_pair(),
        map_func=lambda exec_pair, quads: Quads(frozenset(quads), exec_pair)
    )

    exec_hb = clone_wait_graph(probe_log)

    def get_quadset_for_exec_pair(exec_pair: ptypes.ExecPair) -> frozenset[ptypes.OpQuad]:
        return exec_to_quads[exec_pair].inner
    quadset_hb: networkx.DiGraph[frozenset[ptypes.OpQuad]] = graph_utils.map_nodes(
        get_quadset_for_exec_pair,
        exec_hb,
    )
    quadset_hb_oracle: graph_utils.ReachabilityOracle[frozenset[ptypes.OpQuad]] = graph_utils.PrecomputedReachabilityOracle.create(quadset_hb)
    hb_oracle = graph_utils.PartitionOracle.create(quadset_hb_oracle)

    def get_quads_for_exec_pair(exec_pair: ptypes.ExecPair) -> Quads:
        return exec_to_quads[exec_pair]
    dataflow_graph: networkx.DiGraph[Quads | IVNs] = graph_utils.map_nodes(
        get_quads_for_exec_pair,
        exec_hb,
    )

    # For each inode, find the interval in which it was accessed
    inode_intervals, inode_to_paths = find_intervals(probe_log, hbg, hb_oracle, thread_to_ops)

    # For each inode
    def to_node(node: ptypes.OpQuad | InodeVersionNode) -> Quads | IVNs:
        if isinstance(node, ptypes.OpQuad):
            return exec_to_quads[node.exec_pair()]
        elif isinstance(node, InodeVersionNode):
            return IVNs(frozenset({node}))
        else:
            raise TypeError(node)
    for inode, interval_infos in tqdm.tqdm(inode_intervals.items(), desc="Add intervals for inode to graph"):
        add_inode_intervals(inode, interval_infos, dataflow_graph, hb_oracle, to_node)

    # Make dfg have the same datatype as a compressed graph
    return dataflow_graph, inode_to_paths, hbg, hb_oracle


def clone_wait_graph(
        probe_log: ptypes.ProbeLog,
) -> networkx.DiGraph[ptypes.ExecPair]:
    graph: networkx.DiGraph[ptypes.ExecPair] = networkx.DiGraph()
    for quad, op in probe_log.ops():
        graph.add_node(quad.exec_pair())
        if isinstance(op.data, ops.CloneOp) and op.data.ferrno == 0 and op.data.task_type == ptypes.TaskType.TASK_PID:
            target_pid = ptypes.Pid(op.data.task_id)
            if target_pid in probe_log.processes:
                target = ptypes.ExecPair(target_pid, ptypes.initial_exec_no)
                graph.add_edge(quad.exec_pair(), target)
        # WaitOp does not "really" introduce a DFG dependency
        # If proc A reads file B and then gets waited on by proc C, B may influence the exit code of A, which is available from C.
        # However, it seems like that "shouldn't" matter.
        # If C reads B, then there will be a DFG dependency from B to C anyway (not merely through a wait).
        # If C does not read B, then there is no "true" DFG dependency from B to C.
        # However, the returncode of B could still influence the execution of C.
        # I think that is unlikely. It would be a "pointless check" like:
        # ```bash
        # if [ -e file.txt ]; then
        #     # some code that never reads file.txt
        # fi
        # ```
        # The return code of A could be faked in the reproduction anyway.
        # elif isinstance(op.data, ops.WaitOp) and op.data.ferrno == 0 and op.data.task_type == ptypes.TaskType.TASK_PID:
        #     target_pid = ptypes.Pid(op.data.task_id)
        #     if target_pid in probe_log.processes:
        #         last_exec_no = max(probe_log.processes[target_pid].execs.keys())
        #         target = ptypes.ExecPair(target_pid, last_exec_no)
        #         graph.add_edge(target, quad.exec_pair())


    if not networkx.is_directed_acyclic_graph(graph):
        cycle = [node.exec_pair() for node, _ in networkx.find_cycle(graph)]
        warnings.warn(ptypes.UnusualProbeLog(f"Cycle in HB: {cycle}"))
        return
    return graph
