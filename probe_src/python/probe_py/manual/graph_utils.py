import pathlib
import networkx  # type: ignore


def serialize_graph(
        graph: networkx.Graph,
        output: pathlib.Path,
) -> None:
    pydot_graph = networkx.drawing.nx_pydot.to_pydot(graph)
    if output.suffix == "dot":
        pydot_graph.write_raw(output)
    else:
        pydot_graph.write_png(output)
