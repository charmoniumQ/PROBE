import re
import pathlib
import io
import httpx
import nbconvert


url = "https://raw.githubusercontent.com/tensorflow/text/refs/heads/master/docs/tutorials/transformer.ipynb"


if __name__ == "__main__":
    notebook_text = httpx.get(url).content
    notebook_file = io.BytesIO(notebook_text)
    src, _ = nbconvert.exporters.PythonExporter().from_file(notebook_file)

    # IPython magic doesn't work here.
    src = re.sub(r"get_ipython\(\)\.system\('(.*)'\)", r"print('Run: \1')", src)

    # monkeypatch URL because old URL has different content now.
    src = """
from tensorflow_datasets.datasets.ted_hrlr_translate import ted_hrlr_translate_dataset_builder
ted_hrlr_translate_dataset_builder._DATA_URL = (
    "https://web.archive.org/web/20240301220426if_/http://www.phontron.com/data/qi18naacl-dataset.tar.gz"
)
    """ + src

    # IDK why this is different
    src = src.replace(
        "tokenizers = tf.saved_model.load(model_name)",
        "tokenizers = tf.saved_model.load(f'{model_name}_extracted/{model_name}')",
    )

    # For some reason .sumary doesn't work
    src = src.replace(
        "transformer.summary()",
        "#transformer.summary()",
    )

    # Reduce N epochs to simplify
    src = src.replace("epochs=20", "epochs=1")

    pathlib.Path("script.py").write_text(src)
    notebook_file.close()
