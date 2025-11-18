function stripWs(element) {
    Array.from(element.childNodes).forEach((node) => {
        switch (node.nodeType) {
        case Node.TEXT_NODE: {
            let counter = 0;
            for (const char of node.textContent) {
                let shouldExit  = false;
                switch (char) {
                case "\n":
                    counter = 0;
                    break;
                case " ":
                    counter++;
                    break;
                default:
                    shouldExit = true;
                }
                if (shouldExit) {
                    break;
                }
            }
            node.textContent = node.textContent.split("\n").map((line) => {
                if (line.substring(0, counter).match(/ */)) {
                    return line.substring(counter);
                } else {
                    line;
                }
            }).join("\n");
            break;
        }
        case Node.ELEMENT_NODE:
            stripWs(node);
            break;
        }
    })
}
Array.from(
    document.getElementsByClassName("strip-ws")
).forEach(stripWs);
