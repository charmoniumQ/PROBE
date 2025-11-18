Array.from(document.getElementsByClassName("qrcode-link")).forEach((container) => {
    const a = document.createElement("a");
    const figure = document.createElement("figure");
    const figCaption = document.createElement("figcaption");

    container.appendChild(a);
    a.appendChild(figure);
    figure.appendChild(figCaption);

    a.href = container.dataset.encoded;
    figCaption.textContent = container.dataset.caption;
    new QRCode(figure, {
	    text: container.dataset.encoded,
    });
});
