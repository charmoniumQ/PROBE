import pathlib
import tempfile
import pycparser
import pycparser.c_generator
import sys


with tempfile.TemporaryDirectory() as tmpdir:
    src_file = pathlib.Path(tmpdir) / "test.c"
    src_file.write_text(sys.stdin.read())
    ast = pycparser.parse_file(src_file, use_cpp=True)


ast.show(showcoord=False)
print(ast)
c_generator = pycparser.c_generator.CGenerator()
print(c_generator.visit(ast))
