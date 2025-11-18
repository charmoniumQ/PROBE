window.MathJax = {
    tex: {
        macros: {
            events: "\\mathrm{Events}",
            programorder: "\\overset{P}{\\leq}",
            syncorder: "\\overset{S}{\\leq}",
            hb: "\\overset{HB}{\\leq}",
            nhb: "\\overset{HB}{\\not\\leq}",
            transitiveclosure: ["(#1)^*", 1],
            simultaneous: "\\overset{HB}{\\sim}",
            readsof: ["\\mathrm{Rd}(#1)", 1],
            writesof: ["\\mathrm{Wr}(#1)", 1],
            accessesof: ["\\mathrm{Acc}(#1)", 1],
            eventsin: ["\\mathrm{Process}(#1)", 1],
            dfg: ["#1 \\overset{DFG}{\\to} #2", 2],
            xor: "\\textrm{xor}",
            powerset: ["2^{#1}", 1],
            intervals: "\\mathrm{Intrvs}",
            files: "\\mathrm{Files}",
            dom: "\\mathrm{dom}",
            idom: "\\mathrm{idom}",
            processes: "\\mathrm{PIDs}",
            reverse: "\\mathrm{Reverse}",
            toposort: "\\mathrm{Toposort}",
            O: ["\\mathcal{O}(#1)", 1],
        },
        packages: {
            "[+]": [
                "color",
                "physics",
            ],
        },
    },
    loader: {
        load: [
            "[tex]/color",
            "[tex]/physics",
        ],
    },
    options: {
        processHtmlClass: "mathjax-process",  //  class that marks tags that should be searched
    },
};
