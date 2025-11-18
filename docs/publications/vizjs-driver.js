/* Invoke Viz.js on elements whose class is graphviz */

if (!window.viz) {
    window.viz = new Viz();
}

Promise.all(Array.from(
    document.getElementsByClassName("graphviz")
).map(element => {
    window.viz.renderSVGElement(element.textContent).then(svg => {
        element.replaceWith(svg);
    });
}));
