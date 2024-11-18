The Oxford English Dictionary defines \textbf{provenance} as ``a record of the ultimate origin and passage of an item through its previous owners.''
In a scientific context, the origin of an artifact is some experimental procedure, so provenance is a description of that;
each input used in the procedure has its own provenance, which might be included in the final product, depending on the depth requested.
\textbf{Computational provenance} refers to the software programs and input data used to generate the artifact can serve as a description of the experimental procedure \cite{freire_provenance_2008}.
This provenance is either \textbf{prospective}, which describes the computational procedure one would need to take to generate an analogous artifact, or \textbf{retrospective}, which describes the computational procedure that the authors took to generate the artifact \cite{zhao_applying_2006}.
Somewhat independently from the retrospective/prospective classification, provenance can be collected at the application-level, workflow-level, or system-level \cite{muniswamy-reddy_layering_2009,freire_provenance_2008}.

\begin{itemize}
\item
To collect \textbf{application-level provenance}, one would modify each application to emit provenace data.
This is the most semantically rich but least general, as it only enables collection by that particular modified applicaiton \cite{muniswamy-reddy_layering_2009}.

\item To collect \textbf{workflow-level provenance}, one would modify the workflow engine, and all workflows written for that engine would emit provenance data.
Workflow engines are only aware of the dataflow not higher-level semantics, so workflow-level provenance is not as semantically rich as application-level provenance.
However, it is more general than application-level provenance, as it enables collection in any workflow written for that modified engine \cite{freire_provenance_2008}.

\item
To collect \textbf{system-level provenance}, one uses operating system facilities to report the inputs and outpus that a process makes.
This is the least semantically aware because it does not even know dataflow, just a history of inputs and outputs, but it is the most general, because it supports any process (including any application or workflow engine) that uses watchable I/O operations \cite{freire_provenance_2008}.
\end{itemize}

\begin{figure}
\centering
\begin{subfigure}[b]{0.23\textwidth}
\centering
\includegraphics[width=\textwidth]{./application-level.pdf}
\caption{Application-level provenance}
\end{subfigure}
\hfill
\begin{subfigure}[b]{0.23\textwidth}
\centering
\includegraphics[width=\textwidth]{./workflow-level.pdf}
\caption{Workflow-level provenance}
\label{subfigure:workflow-level-graph}
\end{subfigure}
\hfill
\begin{subfigure}[b]{0.23\textwidth}
\begin{verbatim}
read A
write B
read C
write D
write E
\end{verbatim}
\caption{System-level input/output log}
\label{subfigure:system-level-log}
\end{subfigure}
\hfill
\begin{subfigure}[b]{0.23\textwidth}
\centering
\includegraphics[width=\textwidth]{./system-level.pdf}
\caption{System-level provenance}
\label{subfigure:system-level-graph}
\end{subfigure}
\caption{Several provenance graphs collected at different levels.}
\label{figure:graphs}
\end{figure}

The workflow-level provenance graph (\Cref{subfigure:workflow-level-graph}) knows what data goes where, but not what the data represents, so it uses arbitrary labels A, B, C, D for data and X, Y for programs.

If X and Y are called as functions from within one process, system-level provenance would see \Cref{subfigure:system-level-log}.
D does not really depend on A, but the system-level graph (\Cref{subfigure:system-level-graph}) would have no way of knowing that from just the input/output log.
The system-level graph also does not know that E only depends on the information in A and C which is also present in B and D.
Most applications (e.g., reusing cached results) would prefer false positives than false negatives to the question, ``does this depend on that?'', so we conservatively assume an input effects any future output.
The system-levle graph also does not know the any of the transformations (e.g., from A to B).
However, if X and Y are called as subprocesses, the system-level graph may be closer to the workflow-level provenance graph.Provenance
