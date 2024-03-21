from __future__ import annotations
import dataclasses
import re
import pycparser
import pycparser.c_generator
import tempfile
import pathlib


def rename_decl(decl: pycparser.c_ast.Decl, name: str) -> pycparser.c_ast.Decl:
    return pycparser.c_ast.Decl(
        name=name,
        quals=decl.quals,
        align=decl.align,
        funcspec=decl.funcspec,
        type=decl.type,
        init=decl.init,
        bitsize=decl.bitsize,
    )


@dataclasses.dataclass(frozen=True)
class ParsedFunc:
    name: str
    params: list[tuple[str, pycparser.c_ast.Node]]
    return_type: pycparser.c_ast.Node
    varargs: bool = False

    @property
    def void_return(self) -> bool:
        return isinstance(self.return_type.type, pycparser.c_ast.IdentifierType) and self.return_type.type.names[0] == "void"

    @staticmethod
    def from_ast(decl: pycparser.c_ast.Decl) -> ParsedFunc:
        return ParsedFunc(
            name=decl.name,
            params=[
                (param_decl.name, param_decl.type)
                for param_decl in decl.type.args.params
                if isinstance(param_decl, pycparser.c_ast.Decl)
            ],
            return_type=decl.type.type,
            varargs=isinstance(decl.type.args.params[-1], pycparser.c_ast.EllipsisParam),
        )

    def declaration(self) -> pycparser.c_ast.FuncDecl:
        return pycparser.c_ast.FuncDecl(
            args=pycparser.c_ast.ParamList(
                params=[
                    pycparser.c_ast.Decl(
                        name=param_name,
                        quals=[],
                        align=[],
                        storage=[],
                        funcspec=[],
                        type=pycparser.c_ast.TypeDecl(
                            declname=param_name,
                            quals=[],
                            align=[],
                            type=param_type,
                        ),
                        init=None,
                        bitsize=None,
                    )
                        for param_name, param_type in self.params
                ] + ([pycparser.c_ast.EllipsisParam()] if self.varargs else []),
            ),
            type=pycparser.c_ast.TypeDecl(
                declname=self.name,
                quals=[],
                align=[],
                type=self.return_type,
            ),
        )

    def definition(self, stmts: list[pycparser.c_ast.Node]) -> pycparser.c_ast.FuncDef:
        return pycparser.c_ast.FuncDef(
            decl=pycparser.c_ast.Decl(
                name=self.name,
                quals=[],
                align=[],
                storage=[],
                funcspec=[],
                type=self.declaration(),
                init=None,
                bitsize=None
            ),
            param_decls=None,
            body=pycparser.c_ast.Compound(
                block_items=stmts,
            ),
        )

filename = pathlib.Path("libc_subset.c")
with tempfile.TemporaryDirectory() as _tmpdir:
    tmpdir = pathlib.Path(_tmpdir)
    (tmpdir / filename).write_text(re.sub("/\\*.*?\\*/", "", filename.read_text(), flags=re.DOTALL))

    ast = pycparser.parse_file(tmpdir / filename, use_cpp=False)
    generator = pycparser.c_generator.CGenerator()
    funcs = [
        ParsedFunc.from_ast(node)
        for node in ast.ext
        if isinstance(node, pycparser.c_ast.Decl) and isinstance(node.type, pycparser.c_ast.FuncDecl)
    ]
    func_prefix = "_o_"
    func_pointer_declarations = [
        pycparser.c_ast.Decl(
            name=func_prefix + func.name,
            quals=[],
            align=[],
            storage=[],
            funcspec=[],
            type=pycparser.c_ast.PtrDecl(
                quals=[],
                type=dataclasses.replace(func, name=func_prefix + func.name).declaration(),
            ),
            init=None,
            bitsize=None,
        )
        for func in funcs
        if func.name != "fopen"
        # fopen is handled specially in libprov_prefix.c
    ]
    libprov_setup = ParsedFunc(
        name="libprov_setup",
        params=[],
        return_type=pycparser.c_ast.IdentifierType(names=['void']),
        varargs=False,
    ).definition([
        pycparser.c_ast.Assignment(
            op='=',
            lvalue=pycparser.c_ast.ID(name=func_prefix + func.name),
            rvalue=pycparser.c_ast.FuncCall(
                name=pycparser.c_ast.ID(name="dlsym"),
                args=pycparser.c_ast.ExprList(
                    exprs=[
                        pycparser.c_ast.ID(name="RTLD_NEXT"),
                        pycparser.c_ast.Constant(type="string", value='"' + func.name + '"'),
                    ],
                ),
            ),
        )
        for func in funcs
    ])

    static_args_wrapper_func_declarations = [
        func.definition([
            *([pycparser.c_ast.Decl(
                name="ret",
                quals=[],
                align=[],
                storage=[],
                funcspec=[],
                type=pycparser.c_ast.TypeDecl(
                    declname="ret",
                    quals=[],
                    align=None,
                    type=func.return_type,
                ),
                init=pycparser.c_ast.FuncCall(
                    name=pycparser.c_ast.ID(
                        name=func_prefix + func.name,
                    ),
                    args=pycparser.c_ast.ExprList(
                        exprs=[
                            pycparser.c_ast.ID(name=param_name)
                            for param_name, _ in func.params
                        ],
                    ),
                ),
                bitsize=None
            )] if not func.void_return else []),
            pycparser.c_ast.FuncCall(
                name=pycparser.c_ast.ID("fprintf"),
                args=pycparser.c_ast.ExprList(
                    exprs=[
                        pycparser.c_ast.FuncCall(
                            name=pycparser.c_ast.ID("get_prov_log_file"),
                            args=pycparser.c_ast.ExprList(
                                exprs=[],
                            ),
                        ),
                        pycparser.c_ast.Constant(type="string", value='"' + func.name +  '\\n"'),
                    ],
                ),
            ),
            pycparser.c_ast.Return(
                expr=(pycparser.c_ast.ID(name="ret") if not func.void_return else None),
            ),
        ])
        for func in funcs
        if not func.varargs
    ]
    print(generator.visit(pycparser.c_ast.FileAST(ext=[
        *func_pointer_declarations,
        libprov_setup,
        *static_args_wrapper_func_declarations,
    ])))
