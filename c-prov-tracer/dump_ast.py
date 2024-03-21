import pycparser
import pycparser.c_generator
import sys


parser = pycparser.CParser()
ast = parser.parse(sys.stdin.read(), "test.c")
ast.show(showcoord=False)
print(ast)
c_generator = pycparser.c_generator.CGenerator()
