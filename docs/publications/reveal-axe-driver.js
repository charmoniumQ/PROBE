Reveal.on("slidechanged", (event) => {
    return axe
        .run()
        .then(results => {
            const state = Reveal.getState();
            console.log(state, results);
        })
        .catch(err => {
            console.error("Something bad happened:", err.message);
        });
});
