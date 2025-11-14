import hashlib
import pathlib
import shutil
import subprocess
import tempfile

import bs4
import typer


def main(
        input_html: pathlib.Path,
        output_html: pathlib.Path,
) -> None:
    output_html = output_html.resolve()
    soup = bs4.BeautifulSoup(input_html.read_text(), "lxml")
    with tempfile.TemporaryDirectory() as _tmp_dir:
        tmp_dir = pathlib.Path(_tmp_dir)
        for graphviz_node in soup.select("pre.graphviz"):
            graphviz_source = graphviz_node.text.encode()
            id = hashlib.sha256(graphviz_source).hexdigest()[:16]
            graphviz_source_path = (tmp_dir / f"{id}.dot")
            graphviz_source_path.write_bytes(graphviz_source)
            graphviz_image_path = output_html.parent / f"{id}.svg"
            subprocess.run(["dot", "-Tsvg", f"-o{graphviz_image_path}", str(graphviz_source_path)], check=True)
            graphviz_node.replace_with(
                soup.new_tag("img", src=graphviz_image_path.name)
            )
    output_html.write_text(str(soup))


if __name__ == "__main__":
    typer.run(main)
