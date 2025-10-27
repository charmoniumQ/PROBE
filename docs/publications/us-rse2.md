My [prior US-RSE presentation][1] discussed a provenance tracer I am developing for RSE audience called PROBE. In that presentation, I described how PROBE can automatically containerize and display the dataflow within arbitrary black box applications; one need only run the application once by hand, and PROBE tracks the sequence of command executions and file I/O. My development of PROBE has continued, and now PROBE can not only containerize an application, it can turn the application into a workflow, in which each launched process becomes a node, and each file becomes an edge between nodes.

This talk will outline the motivation for workflow-ization, how to use PROBE for automatic workflow-ization, and how PROBE works under the hood.

[1]: https://zenodo.org/records/13963644


