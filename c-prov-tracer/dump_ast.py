import pycparser
import pycparser.c_generator
import sys

ast = pycparser.parse_file(sys.argv[1], use_cpp=False)
ast.show(showcoord=False)
print(ast)
c_generator = pycparser.c_generator.CGenerator()
print(c_generator.visit(ast))
