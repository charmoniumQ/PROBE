extern crate proc_macro;

use std::vec::Vec;
use syn::{parenthesized, parse_macro_input, token, Ident, Token, Result, Error, Block, Stmt};
use syn::parse::{Parse, ParseStream, discouraged::Speculative};
use syn::punctuated::Punctuated;
use quote::{quote, format_ident};

/*
 * These macros are purpose-made for one use within the containing project.
 */

enum CPrimType {
    Int(Ident),
    Uint(Ident, Ident),
    Char(Ident),
    File(Ident),
    ModeT(Ident),
    Void(Ident),
    Dir(Ident),
    SizeT(Ident),
    SsizeT(Ident),
}

impl Parse for CPrimType {
    fn parse(input: ParseStream) -> Result<Self> {
        let ident: syn::Ident = input.parse()?;
        match ident.to_string().as_str() {
            "int" => Ok(CPrimType::Int(ident)),
            "unsigned" => {
                let second_ident: syn::Ident = input.parse()?;
                if second_ident == "int" {
                    Ok(CPrimType::Uint(ident, second_ident))
                } else {
                    Err(Error::new(second_ident.span(), "Unknown unsigned type"))
                }
            },
            "char" => Ok(CPrimType::Char(ident)),
            "FILE" => Ok(CPrimType::File(ident)),
            "mode_t" => Ok(CPrimType::ModeT(ident)),
            "void" => Ok(CPrimType::Void(ident)),
            "DIR" => Ok(CPrimType::Dir(ident)),
            "size_t" => Ok(CPrimType::SizeT(ident)),
            "ssize_t" => Ok(CPrimType::SsizeT(ident)),
            _ => Err(Error::new(ident.span(), "Unable to parse inner CType")),
        }
    }
}

enum CType {
    PtrMut(Token![*], CPrimType),
    PtrConst(Token![*], Option<Token![const]>, CPrimType),
    PrimType(CPrimType),
}

impl Parse for CType {
    fn parse(input: ParseStream) -> Result<Self> {
        if input.peek(Token![const]) {
            let constt: Token![const] = input.parse()?;
            let inner: CPrimType = input.parse()?;
            let star: Token![*] = input.parse()?;
            Ok(CType::PtrConst(star, Some(constt), inner))
        } else {
            let inner: CPrimType = input.parse()?;
            if input.peek(Token![*]) {
                let star: Token![*] = input.parse()?;
                Ok(CType::PtrMut(star, inner))
            } else {
                Ok(CType::PrimType(inner))
            }
        }
    }
}

struct ArgType {
    ty: CType,
    arg: Ident,
}

impl Parse for ArgType {
    fn parse(input: ParseStream) -> Result<Self> {
        Ok(Self {
            ty: input.parse()?,
            arg: input.parse()?,
        })
    }
}

struct CFuncSig {
    return_type: CType,
    name: Ident,
    _paren: token::Paren,
    _void: Option<Ident>,
    arg_types: Punctuated<ArgType, Token![,]>,
    pre_call: Vec<Stmt>,
    post_call: Vec<Stmt>,
}

impl Parse for CFuncSig {
    fn parse(input: ParseStream) -> Result<Self> {
        let return_type: CType = input.parse()?;
        let name: Ident = input.parse()?;
        let content;
        let _paren = parenthesized!(content in input);
        let _void: Option<Ident>;
        let arg_types: Punctuated<ArgType, Token![,]>;
        let void_fork = content.fork();

        let possibly_void: Option<Ident> = void_fork.parse().ok();
        if possibly_void.clone().map(|void2| void2 == "void").unwrap_or(false) && void_fork.is_empty() {
            _void = possibly_void;
            arg_types = Punctuated::new();
            content.advance_to(&void_fork);
        } else {
            _void = None;
            arg_types = content.parse_terminated(ArgType::parse, Token![,])?
        }

        let block0: Option<Block> = input.parse().ok();
        let block1: Option<Block> = input.parse().ok();

        fn option_block_to_stmts(block: Option<Block>) -> Vec<Stmt> {
            block.map_or_else(Vec::new, |block| block.stmts)
        }

        let (pre_call, post_call);
        match block1 {
            Some(block1_real) => {
                pre_call = option_block_to_stmts(block0);
                post_call = block1_real.stmts;
            },
            None => {
                pre_call = vec![];
                post_call = option_block_to_stmts(block0);
            },
        }

        Ok(Self {return_type, name, _paren, _void, arg_types, pre_call, post_call})
    }
}

struct CFuncSigs {
    cfunc_sigs: Punctuated<CFuncSig, Token![;]>,
}

impl Parse for CFuncSigs {
    fn parse(input: ParseStream) -> Result<Self> {
        Ok(Self {cfunc_sigs: input.parse_terminated(CFuncSig::parse, Token![;])?})
    }
}

fn cprim_type_to_type(typ: &CPrimType) -> proc_macro2::TokenStream {
    match typ {
        CPrimType::Int(_) => quote!(libc::c_int),
        CPrimType::Uint(_, _) => quote!(libc::c_uint),
        CPrimType::Char(_) => quote!(libc::c_char),
        CPrimType::File(_) => quote!(libc::FILE),
        CPrimType::ModeT(_) => quote!(libc::mode_t),
        CPrimType::Void(_) => quote!(libc::c_void),
        CPrimType::Dir(_) => quote!(libc::DIR),
        CPrimType::SizeT(_) => quote!(libc::size_t),
        CPrimType::SsizeT(_) => quote!(libc::ssize_t),
    }
}

fn ctype_to_type(typ: &CType) -> proc_macro2::TokenStream {
    match typ {
        CType::PtrConst(_, _, cprim_type) => {
            let inner = cprim_type_to_type(cprim_type);
            quote!(*const #inner)
        },
        CType::PtrMut(_, cprim_type) => {
            let inner = cprim_type_to_type(cprim_type);
            quote!(*mut #inner)
        },
        CType::PrimType(CPrimType::Void(_)) => quote!(()),
        CType::PrimType(cprim_type) => cprim_type_to_type(cprim_type),
    }
}

fn cprim_type_to_obj(typ: &CPrimType) -> proc_macro2::TokenStream {
    match typ {
        CPrimType::Int(_) => quote!(CPrimType::Int),
        CPrimType::Uint(_, _) => quote!(CPrimType::Uint),
        CPrimType::Char(_) => quote!(CPrimType::Char),
        CPrimType::File(_) => quote!(CPrimType::File),
        CPrimType::ModeT(_) => quote!(CPrimType::ModeT),
        CPrimType::Void(_) => quote!(CPrimType::Void),
        CPrimType::Dir(_) => quote!(CPrimType::Dir),
        CPrimType::SizeT(_) => quote!(CPrimType::SizeT),
        CPrimType::SsizeT(_) => quote!(CPrimType::SsizeT),
    }
}

fn ctype_to_obj(typ: &CType) -> proc_macro2::TokenStream {
    match typ {
        CType::PtrConst(_, _, cprim_type) => {
            let inner = cprim_type_to_obj(cprim_type);
            quote!(CType::PtrConst(#inner))
        },
        CType::PtrMut(_, cprim_type) => {
            let inner = cprim_type_to_obj(cprim_type);
            quote!(CType::PtrMut(#inner))
        },
        CType::PrimType(cprim_type) => {
            let inner = cprim_type_to_obj(cprim_type);
            quote!(CType::PrimType(#inner))
        },
    }
}

#[proc_macro]
pub fn populate_libc_calls_and_hook_fns(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let input = parse_macro_input!(input as CFuncSigs);

    let hook_fns =
        input
        .cfunc_sigs
        .iter()
        .map(|cfunc_sig| {
            let name = &cfunc_sig.name;
            let arg_colon_types = cfunc_sig.arg_types.iter().map(|arg_type| {
                let ty = ctype_to_type(&arg_type.ty);
                let arg = &arg_type.arg;
                quote!{#arg: #ty}
            });
            let return_type = ctype_to_type(&cfunc_sig.return_type);
            let traced_name = format_ident!("__traced_{}", cfunc_sig.name);
            let args = cfunc_sig.arg_types.iter().map(|arg_type| {
                let arg = &arg_type.arg;
                quote!(#arg,)
            }).collect::<proc_macro2::TokenStream>();
            let boxed_args = cfunc_sig.arg_types.iter().map(|arg_type| {
                let arg = &arg_type.arg;
                quote!(Box::new(#arg),)
            }).collect::<proc_macro2::TokenStream>();

            /* vvv stuff vvv */
            let arg_fmt_string = cfunc_sig
                .arg_types
                .iter()
                .map(|arg_type| arg_type.arg.to_string() + "={:?}")
                .collect::<Vec<_>>()
                .join(" ");
            let arg_fmt_args = cfunc_sig.arg_types.iter().map(|arg_type| {
                let arg = &arg_type.arg;
                let arg_rep = match arg_type.ty {
                    CType::PtrConst(_, _, CPrimType::Char(_)) => quote!(unsafe{crate::util::short_cstr(#arg)}),
                    _ => quote!(#arg),
                };
                quote!(#arg_rep,)
            }).collect::<proc_macro2::TokenStream>();
            /* ^^^ stuff ^^^ */

            let pre_call = &cfunc_sig.pre_call;
            let post_call = &cfunc_sig.post_call;
            quote!{
                redhook::hook! {
                    unsafe fn #name(
                        #(#arg_colon_types),*
                    ) -> #return_type => #traced_name {
                        // println!("(processing");
                        // println!(concat!("(", stringify!(#name), " ", #arg_fmt_string, ")"), #arg_fmt_args);
                        let mut guard_inner_call = false;
                        let mut call_return;
                        #(#pre_call)*
                        // print!("(real-call ");
                        call_return = redhook::real!(#name)(#args);
                        // println!("ret={:?} errno={:?})", call_return, *libc::__errno_location());
                        // println!("(prov-logger?\n{}", !guard_inner_call || globals::ENABLE_TRACE.get());
                        if !guard_inner_call || globals::ENABLE_TRACE.get() {
                            PROV_LOGGER.with_borrow_mut(|prov_logger| {
                                prov_logger.log_call(stringify!(#name), vec![#boxed_args], vec![], Box::new(call_return));
                                #(#post_call)*
                            });
                        }
                        // print!(")");
                        // println!(")");
                        call_return
                    }
                }
            }
        })
        .collect::<proc_macro2::TokenStream>();

    let cfunc_sigs =
        input
        .cfunc_sigs
        .iter()
        .map(|cfunc_sig| {
            let name = &cfunc_sig.name;
            let arg_types = cfunc_sig.arg_types.iter().map(|arg_type| {
                let arg = &arg_type.arg;
                let ty = ctype_to_obj(&arg_type.ty);
                quote!(ArgType{arg: stringify!(#arg), ty: #ty},)
            }).collect::<proc_macro2::TokenStream>();
            let return_type = ctype_to_obj(&cfunc_sig.return_type);
            quote!(
                (stringify!(#name), CFuncSig{
                    return_type: #return_type,
                    name: stringify!(#name),
                    arg_types: &[#arg_types],
                }),
            )
        })
        .collect::<proc_macro2::TokenStream>();

    proc_macro::TokenStream::from(quote!{
        #hook_fns

        lazy_static::lazy_static! {
            static ref CFUNC_SIGS: CFuncSigs = CFuncSigs::from([
                #cfunc_sigs
            ]);
        }
    })
}
