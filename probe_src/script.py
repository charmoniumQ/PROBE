import sys
import pathlib

probe_log_file = pathlib.Path("probe_log")
assert probe_log_file.exists()

python = pathlib.Path("probe_frontend")
assert python.exists()

sys.path.append(str(python))

import python.probe

probe_log = python.probe.load_log(probe_log_file)

import probe_py.analysis

probe_digraph = probe_py.analysis.provlog_to_digraph(probe_log)

probe_graphviz = probe_py.analysis.digraph_to_pydot_string(probe_digraph)

pathlib.Path("probe_log.gv").write_text(probe_graphviz)
