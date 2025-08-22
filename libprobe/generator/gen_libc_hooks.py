from __future__ import annotations
import dataclasses
import pycparser  # type: ignore
import pycparser.c_generator  # type: ignore
import typing
import itertools
import pathlib


# Intercept libc functions
# But ignore pre_call/post_call actions
# Don't produce ops
ignore_actions = False


_T = typing.TypeVar("_T")
def expect_type(typ: type[_T], data: typing.Any) -> _T:
    if not isinstance(data, typ):
        raise TypeError(f"Expected type {typ} for {data}")
    return data


if typing.TYPE_CHECKING:
    class CGenerator:
        def _parenthesize_if(self, n: Node, condition: typing.Callable[[Node], bool]) -> str: ...
        def _generate_decl(self, n: pycparser.c_ast.Node) -> str: ...
        def visit(self, n: pycparser.c_ast.Node | str | list[str]) -> str: ...
        def _visit_expr(self, n: pycparser.c_ast.Node) -> str: ...
        def _make_indent(self) -> str: ...
        indent_level: int
    class Node:
        def __iter__(self) -> typing.Iterator[Node]: ...
    @dataclasses.dataclass
    class IdentifierType(Node):
        names: list[str]
    @dataclasses.dataclass
    class Assignment(Node):
        op: str
        lvalue: Node
        rvalue: Node
    @dataclasses.dataclass
    class Compound(Node):
        block_items: list[Node]
    @dataclasses.dataclass
    class ID(Node):
        name: str
    @dataclasses.dataclass
    class Decl(Node):
        name: str
        quals: list[str]
        align: list[str]
        storage: list[str]
        funcspec: list[str]
        type: TypeDecl | PtrDecl
        init: Node | None = None
        bitsize: Node | None = None
    @dataclasses.dataclass
    class TypeDecl(Node):
        declname: str | None
        quals: list[Node]
        align: Node | None
        type: Node
    @dataclasses.dataclass
    class FuncDecl(Node):
        args: ParamList | None
        type: TypeDecl
    @dataclasses.dataclass
    class ParamList(Node):
        params: list[Decl]
    @dataclasses.dataclass
    class PtrDecl(Node):
        quals: list[str]
        type: TypeDecl | FuncDecl
else:
    CGenerator = pycparser.c_generator.CGenerator
    Node = pycparser.c_ast.Node
    IdentifierType = pycparser.c_ast.IdentifierType
    Assignment = pycparser.c_ast.Assignment
    Compound = pycparser.c_ast.Compound
    Decl = pycparser.c_ast.Decl
    TypeDecl = pycparser.c_ast.TypeDecl
    ID = pycparser.c_ast.ID
    FuncDecl = pycparser.c_ast.FuncDecl
    ParamList = pycparser.c_ast.ParamList
    PtrDecl = pycparser.c_ast.PtrDecl


class GccCGenerator(CGenerator):
    """A C generator that is able to emit gcc statement-expr ({...;})"""

    def visit_Assignment(self, n: Assignment) -> str:
        rval_str = self._parenthesize_if(
            n.rvalue,
            lambda n: isinstance(n, (Assignment, Compound)),
        )
        return '%s %s %s' % (self.visit(n.lvalue), n.op, rval_str)

    def visit_Decl(self, n: Decl, no_type: bool = False) -> str:
        s = n.name if no_type else self._generate_decl(n)
        if n.bitsize:
            s += ' : ' + self.visit(n.bitsize)
        if n.init:
            s += ' = ' + self._parenthesize_if(n.init, lambda n: isinstance(n, (Assignment, Compound)))
        return s

    def _parenthesize_if(self, n: Node, condition: typing.Callable[[Node], bool]) -> str:
        self.indent_level += 2
        s = self._visit_expr(n)
        self.indent_level -= 2
        if condition(n):
            if isinstance(n, Compound):
                return "(\n" + s + self._make_indent() + ")"
            else:
                return '(' + s + ')'
        else:
            return s


class FunctionalNodeVisitor(typing.Generic[_T]):
    _method_cache: None | dict[str, typing.Callable[[Node], list[_T]]] = None

    def visit(self, node: Node) -> list[_T]:
        """ Visit a node."""

        if self._method_cache is None:
            self._method_cache = {}

        visitor = self._method_cache.get(node.__class__.__name__, None)
        if visitor is None:
            method = 'visit_' + node.__class__.__name__
            visitor = getattr(self, method, self.generic_visit)
            self._method_cache[node.__class__.__name__] = visitor

        assert visitor

        return visitor(node)

    def generic_visit(self, node: Node) -> list[_T]:
        """ Called if no explicit visitor function exists for a
            node. Implements preorder visiting of the node.
        """
        return list(itertools.chain.from_iterable(self.visit(c) for c in node))


class ErrnoDetector(FunctionalNodeVisitor[bool]):
    def visit_ID(self, node: ID) -> list[bool]:
        if node.name == "errno":
            return [True]
        else:
            return []


def is_void(node: TypeDecl) -> bool:
    return isinstance(node.type, IdentifierType) and node.type.names[0] == "void"


def define_var(var_type: Node, var_name: str, value: Node) -> Decl:
    return Decl(
        name=var_name,
        quals=[],
        align=[],
        storage=[],
        funcspec=[],
        type=pycparser.c_ast.TypeDecl(
            declname=var_name,
            quals=[],
            align=None,
            type=var_type,
        ),
        init=value,
        bitsize=None,
    )


void = IdentifierType(names=['void'])

c_ast_int = IdentifierType(names=['int'])


def ptr_type(type: Node) -> PtrDecl:
    return PtrDecl(
        quals=[],
        type=TypeDecl(
            declname="v",
            quals=[],
            align=None,
            type=type,
        ),
    )


void_fn_ptr = pycparser.c_ast.Typename(
    name=None,
    quals=[],
    align=None,
    type=PtrDecl(
        quals=[],
        type=FuncDecl(
            args=None,
            type=TypeDecl(
                declname=None,
                quals=[],
                align=None,
                type=void,
            ),
        ),
    ),
)


def strip_restrict(ty: TypeDecl | PtrDecl) -> TypeDecl | PtrDecl:
    if isinstance(ty, PtrDecl):
        return PtrDecl(
            quals=[qual for qual in ty.quals if qual != "restrict"],
            type=ty.type,
        )
    else:
        return ty

@dataclasses.dataclass(frozen=True)
class ParsedFunc:
    name: str
    # Using tuples rather than lists since tuples are covariant
    params: typing.Sequence[tuple[str, TypeDecl | PtrDecl]]
    return_type: TypeDecl
    variadic: bool = False
    stmts: typing.Sequence[Node] = ()

    @staticmethod
    def from_decl(decl: Decl) -> ParsedFunc:
        return ParsedFunc(
            name=decl.name,
            params=tuple(
                (param_decl.name, param_decl.type)
                for param_decl in expect_type(ParamList, expect_type(FuncDecl, decl.type).args).params
                if isinstance(param_decl, Decl)
            ),
            return_type=expect_type(FuncDecl, decl.type).type,
            variadic=isinstance(expect_type(ParamList, expect_type(FuncDecl, decl.type).args).params[-1], pycparser.c_ast.EllipsisParam),
        )

    @staticmethod
    def from_defn(func_def: pycparser.c_ast.FuncDef) -> ParsedFunc:
        return dataclasses.replace(
            ParsedFunc.from_decl(func_def.decl),
            stmts=tuple(func_def.body.block_items) if func_def.body.block_items is not None else (),
        )

    def declaration(self) -> pycparser.c_ast.FuncDecl:
        return pycparser.c_ast.FuncDecl(
            args=ParamList(
                params=[
                    Decl(
                        name=param_name,
                        quals=[],
                        align=[],
                        storage=[],
                        funcspec=[],
                        type=param_type,
                        init=None,
                        bitsize=None,
                    )
                    for param_name, param_type in self.params
                ] + ([pycparser.c_ast.EllipsisParam()] if self.variadic else []),
            ),
            type=pycparser.c_ast.TypeDecl(
                declname=self.name,
                quals=[],
                align=[],
                type=self.return_type,
            ),
        )

    def definition(self, visibility: str | None = None) -> pycparser.c_ast.FuncDef:
        return pycparser.c_ast.FuncDef(
            decl=Decl(
                name=self.name,
                quals=[],
                align=[],
                storage=[] if visibility is None else [f'__attribute__((visibility("{visibility}")))'],
                funcspec=[],
                type=self.declaration(),
                init=None,
                bitsize=None
            ),
            param_decls=None,
            body=Compound(
                block_items=list(self.stmts),
            ),
        )


filename = pathlib.Path("generator/libc_hooks_source.c")
ast = pycparser.parse_file(filename, use_cpp=True, cpp_args=["-Wno-unused-command-line-argument", "-I."])
orig_funcs = {
    node.decl.name: ParsedFunc.from_defn(node)
    for node in ast.ext
    if isinstance(node, pycparser.c_ast.FuncDef)
}
funcs = {
    **orig_funcs,
    **{
        node.name: dataclasses.replace(orig_funcs[typing.cast(ID, node.init).name], name=node.name)
        for node in ast.ext
        if isinstance(node, Decl) and isinstance(node.type, pycparser.c_ast.TypeDecl) and node.type.type.names == ["fn"]
    },
}
func_prefix = "client_"
func_pointer_declarations = [
    Decl(
        name=func_prefix + func_name,
        quals=[],
        align=[],
        storage=[],
        funcspec=[],
        type=PtrDecl(
            quals=[],
            type=dataclasses.replace(func, name=func_prefix + func.name).declaration(),
        ),
        init=None,
        bitsize=None,
    )
    for func_name, func in funcs.items()
]
func_pointer_extern_declarations = [
    Decl(
        name=func_prefix + func_name,
        quals=[],
        align=[],
        storage=["extern"],
        funcspec=[],
        type=PtrDecl(
            quals=[],
            type=dataclasses.replace(func, name=func_prefix + func.name).declaration(),
        ),
        init=None,
        bitsize=None,
    )
    for func_name, func in funcs.items()
]
init_function_pointers = ParsedFunc(
    name="init_function_pointers",
    params=(),
    return_type=TypeDecl(declname="a", quals=[], align=None, type=void),
    variadic=False,
    stmts=[
        *itertools.chain.from_iterable([
            [
                Assignment(
                    op='=',
                    lvalue=pycparser.c_ast.ID(name=func_prefix + func_name),
                    rvalue=pycparser.c_ast.FuncCall(
                        name=pycparser.c_ast.ID(name="dlsym"),
                        args=pycparser.c_ast.ExprList(
                            exprs=[
                                pycparser.c_ast.ID(name="RTLD_NEXT"),
                                pycparser.c_ast.Constant(type="string", value=f'"{func_name}"'),
                            ],
                        ),
                    ),
                ),
                # TODO: guard this with `#ifndef NDEBUG`
                # pycparser.c_ast.If(
                #     cond=pycparser.c_ast.UnaryOp(
                #         op="!",
                #         expr=pycparser.c_ast.ID(name=func_prefix + func_name),
                #     ),
                #     iftrue=pycparser.c_ast.FuncCall(
                #         name=pycparser.c_ast.ID("DEBUG"),
                #         args=pycparser.c_ast.ExprList(
                #             exprs=[
                #                 pycparser.c_ast.Constant(type="string", value=f'"{func_name}(...) not found"'),
                #             ],
                #         ),
                #     ),
                #     iffalse=None,
                # ),
            ]
            for func_name, func in funcs.items()
        ]),
    ],
).definition()


T = typing.TypeVar("T")
def raise_(exception: Exception) -> typing.NoReturn:
    raise exception


def raise_thunk(exception: Exception) -> typing.Callable[..., typing.NoReturn]:
    return lambda *args, **kwarsg: raise_(exception)


def find_decl(
        block: typing.Sequence[Node],
        name: str,
        comment: typing.Any,
) -> Decl | None:
    relevant_stmts = [
        stmt
        for stmt in block
        if isinstance(stmt, Decl) and stmt.name == name
    ]
    if not relevant_stmts:
        return None
    elif len(relevant_stmts) > 1:
        raise ValueError(f"Multiple definitions of {name}" + " ({})".format(comment) if comment else "")
    else:
        return relevant_stmts[0]


def wrapper_func_body(func: ParsedFunc) -> typing.Sequence[Node]:
    pre_call_stmts = [
        pycparser.c_ast.FuncCall(
            name=pycparser.c_ast.ID(name="ensure_thread_initted"),
            args=pycparser.c_ast.ExprList(exprs=[]),
        ),
        # pycparser.c_ast.FuncCall(
        #     name=pycparser.c_ast.ID(name="DEBUG"),
        #     args=pycparser.c_ast.ExprList(exprs=[
        #         pycparser.c_ast.Constant(type="string", value='"Interposed call"'),
        #     ]),
        # ),
    ]

    noreturn = bool(find_decl(func.stmts, "noreturn", func.name))

    # For some reason, Clang analyzer can suddenly prove that if execle returns, errno (call_errno) must be non-zero.
    # So this is a dead store.
    # But it can't prove that for the other execs
    if func.name != "execle" and not noreturn:
        pre_call_stmts.insert(0, define_var(c_ast_int, "saved_errno", pycparser.c_ast.ID(name="errno")))
    post_call_stmts = []


    for stmt in func.stmts:
        if ErrnoDetector().visit(stmt):
            raise RuntimeError(f"{func.name} accesses errno")

    pre_call_action = find_decl(func.stmts, "pre_call", func.name)
    if not ignore_actions and pre_call_action:
        pre_call_stmts.extend(expect_type(Compound, pre_call_action.init).block_items)

    post_call_action = find_decl(func.stmts, "post_call", func.name)
    assert not noreturn or not post_call_action
    if not ignore_actions and post_call_action:
        post_call_stmts.extend(
            expect_type(Compound, post_call_action.init).block_items,
        )

    pre_call_stmts.append(
        Assignment(
            op="=",
            lvalue=pycparser.c_ast.ID(name="errno"),
            rvalue=pycparser.c_ast.Constant(
                type="int",
                value="0",
            ),
        ),
    )

    call_stmts_block = find_decl(func.stmts, "call", func.name) if not ignore_actions else None
    if call_stmts_block is None:
        call_expr = pycparser.c_ast.FuncCall(
            name=pycparser.c_ast.ID(
                name=func_prefix + func.name,
            ),
            args=pycparser.c_ast.ExprList(
                exprs=[
                    pycparser.c_ast.ID(name=param_name)
                    for param_name, _ in func.params
                ],
            ),
        )
        if is_void(func.return_type):
            call_stmts = [call_expr]
        else:
            call_stmts = [define_var(func.return_type, "ret", call_expr)]
    else:
        call_stmts = expect_type(Compound, call_stmts_block.init).block_items

    if noreturn:
        assert is_void(func.return_type)
        post_call_stmts.append(
            pycparser.c_ast.FuncCall(
                name=pycparser.c_ast.ID(name="__builtin_unreachable"),
                args=pycparser.c_ast.ExprList(exprs=[]),
            )
        )
    else:
        post_call_stmts.insert(
            0,
            define_var(c_ast_int, "call_errno", pycparser.c_ast.ID(name="errno")),
        )

        post_call_stmts.append(
            Assignment(
                op="=",
                lvalue=pycparser.c_ast.ID(name="errno"),
                rvalue=pycparser.c_ast.TernaryOp(
                    cond=pycparser.c_ast.ID(name="call_errno"),
                    iftrue=pycparser.c_ast.ID(name="call_errno"),
                    iffalse=pycparser.c_ast.ID(name="saved_errno"),
                ) if func.name != "execle" else pycparser.c_ast.ID(name="call_errno"),
                # See note above regarding execle
            ),
        )

        if not is_void(func.return_type):
            post_call_stmts.append(
                pycparser.c_ast.Return(expr=pycparser.c_ast.ID(name="ret"))
            )

    return pre_call_stmts + call_stmts + post_call_stmts


wrapper_func_declarations = [
    dataclasses.replace(
        func,
        stmts=wrapper_func_body(func),
    ).definition(visibility="default")
    for _, func in funcs.items()
    if func.stmts
]
generated = pathlib.Path("generated")
generated.mkdir(exist_ok=True)

warning = """
/*
 ********************************************************************************
 * This file is automatically generated from generator/libc_hooks.py and generator/libc_hooks_source.c
 * All modifications will be LOST
 ********************************************************************************
 */
"""

libc_hooks_h_preamble = """
#pragma once

#define _GNU_SOURCE

#include <dirent.h>               // for DIR
#include <features.h>             // for __USE_GNU
#include <ftw.h>                  // for FTW
#include <pthread.h>              // IWYU pragma: keep for pthread_t, pthread_attr_t
#include <signal.h>               // for siginfo_t
#include <spawn.h>                // for posix_spawn_file_actions_t
#include <stdio.h>                // for L_tmpnam, FILE, size_t
#include <sys/stat.h>             // IWYU pragma: keep for stat
#include <sys/time.h>             // IWYU pragma: keep for timeval
#include <sys/types.h>            // for pid_t, mode_t, ssize_t, gid_t, uid_t
#include <sys/wait.h>             // IWYU pragma: keep for idtype_t
#include <threads.h>              // for thrd_t, thrd_start_t
// IWYU pragma: no_include "bits/pthreadtypes.h" for pthread_t
// IWYU pragma: no_include "bits/types/idtype_t.h" for idtype_t
// IWYU pragma: no_include "bits/types/sigevent_t.h" for pthread_attr_t

struct rusage;
struct stat;
struct statx;
struct timeval;
struct utimbuf;

/*
 * There is some bug with pycparser unable to parse inline function pointers.
 * So we will use a typedef alias.
 */
typedef int (*fn_ptr_int_void_ptr)(void*);
typedef int (*ftw_func)(const char *, const struct stat *, int);
typedef int (*nftw_func)(const char *, const struct stat *, int, struct FTW *);

/*
 * Smooth out differences between GCC vs Clang and Musl vs Glibc.
 * Best to feature test than test for compiler/libc, but sometimes feature testing is not possible in the preprocessor.
 */

#ifndef __USE_GNU
#define __MUSL__
#endif

// Musl defines tmpnam(char*)
// Glibc defines tmpnam(char[L_tmpnam])
// We use tmpnam(char[L_tmpnam]) and let this macro handle the difference
#ifdef __MUSL__
#define __PROBE_L_tmpnam
#elif __USE_GNU
#define __PROBE_L_tmpnam L_tmpnam
#endif

// Musl does not define closefrom; gcc does and we interpose it.
__attribute__((visibility("default"))) void closefrom(int lowfd);

// On Glibc, struct dirent is 32-bit, with macros switch it to 64-bit or add new struct dirent64
// On Musl, struct dirent is 64-bit
#ifdef __MUSL__
#define dirent64 dirent
#endif

void init_function_pointers();
"""
(generated / "libc_hooks.h").write_text(
    warning + "\n\n" +
    libc_hooks_h_preamble.strip() + "\n\n" +
    GccCGenerator().visit(
        pycparser.c_ast.FileAST(ext=[
            *func_pointer_extern_declarations,
        ])
    )
)
libc_hooks_c_preamble = """
#define _GNU_SOURCE

#include "libc_hooks.h"

#include <dirent.h>                                          // for DIR, dirfd
#include <dlfcn.h>                                           // for dlsym
#include <errno.h>                                           // for errno
#include <fcntl.h>                                           // for AT_FDCWD, O_TMPFILE
#include <ftw.h>                                             // for ftw, nftw
#include <limits.h>                                          // IWYU pragma: keep for INT_MAX, PATH_MAX
#include <linux/close_range.h>                               // for CLOSE_RANGE_CLOEXEC
#include <pthread.h>                                         // for pthread_...
#include <sched.h>                                           // for CLONE_TH...
#include <spawn.h>                                           // for posix_spawn_file_actions_t
#include <stdarg.h>                                          // for va_arg
#include <stdbool.h>                                         // for false, true
#include <stdint.h>                                          // for int64_t
#include <stdio.h>                                           // for fileno
#include <stdlib.h>                                          // for free
#include <sys/stat.h>                                        // for chmod, statx
#include <sys/time.h>                                        // for futimes
#include <sys/wait.h>                                        // for wait, wait3
#include <threads.h>                                         // for thrd_t
#include <unistd.h>                                          // for environ
#include <utime.h>                                           // for utimbuf
// IWYU pragma: no_include "bits/statx-generic.h"               for statx
// IWYU pragma: no_include "bits/types/siginfo_t.h"             for si_pid, si_status
// IWYU pragma: no_include "linux/limits.h"                     for PATH_MAX

#include "../include/libprobe/prov_ops.h"                    // for Op, OpCode
#include "../src/arena.h"                                    // for prov_log...
#include "../src/debug_logging.h"                            // for DEBUG
#include "../src/env.h"                                      // for arena_co...
#include "../src/global_state.h"                             // for ensure_i...
#include "../src/lookup_on_path.h"                           // for lookup_o...
#include "../src/pthread_helper.h"                           // for pthread_helper
#include "../src/probe_libc.h"                               // for probe_libc_...
#include "../src/prov_buffer.h"                              // for prov_log...
#include "../src/prov_utils.h"                               // for create_p...
#include "../src/util.h"                                     // for LIKELY

struct rusage;
struct stat;
struct statx;

/*
 * pycparser cannot parse type-names as function-arguments (as in `va_arg(var_name, type_name)` or `sizeof(type_name)`)
 * so we use some macros instead.
 * To pycparser, these macros are defined as variable names (parsable as arguments).
 * To GCC these macros are defined as type names.
 */
typedef mode_t __type_mode_t;
typedef char* __type_charp;
typedef char** __type_charpp;
typedef int __type_int;
typedef void* __type_voidp;

/*
 * Smooth out differences between GCC and Clang
 */
#ifndef O_TMPFILE
#ifndef __O_TMPFILE
#error "Neither O_TMPFILE nor __O_TMPFILE are defined"
#else
#define O_TMPFILE __O_TMPFILE
#endif
#endif

// Clang and GCC disagree on how to construct this struct inline.
// So I will construct it not inline, here.
const struct my_rusage null_usage = {0};
"""

(generated / "libc_hooks.c").write_text(
    warning + "\n\n" +
    libc_hooks_c_preamble.strip() + "\n\n" +
    GccCGenerator().visit(
        pycparser.c_ast.FileAST(ext=[
            *func_pointer_declarations,
            init_function_pointers,
            *wrapper_func_declarations,
        ])
    )
)
(generated / "libc_fns.csv").write_text(
    "\n".join([
        func_name for func_name, _ in funcs.items()
    ])
)
