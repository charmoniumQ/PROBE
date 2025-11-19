Array.from(
    document.getElementsByTagName("section")
).forEach((section) => {
    let first = true;
    Array.from(section.children).forEach((child) => {
        console.log(child.tagName);
        if (child.tagName.startsWith("H")) {
            console.log(child);
        } else if (child.tagName == "ol" || child.tagName == "ul") {
            Array.from(child.children).forEach((grandchild) => {
                if (!first) {
                    grandchild.classList.add("fragment");
                }
                first = false;
            });
        } else {
            if (!first) {
                child.classList.add("fragment")
            }
            first = false;
        }
    });
});
