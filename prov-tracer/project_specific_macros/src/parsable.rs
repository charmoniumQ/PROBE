use std::vec::Vec;
use syn::{parenthesized, token, Ident, Token, Result, Error, Block};
use syn::parse::{Parse, ParseStream, ParseBuffer, discouraged::Speculative};
use syn::punctuated::Punctuated;
use quote::quote;

pub enum CPrimType {
    Int(Ident),
    Uint(Ident, Ident),
    Char(Ident),
    File(Ident),
    ModeT(Ident),
    Void(Ident),
    Dir(Ident),
    SizeT(Ident),
    SsizeT(Ident),
    FtwFuncT(Ident),
    Ftw64FuncT(Ident),
    NftwFuncT(Ident),
    Nftw64FuncT(Ident),
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
            "__ftw_func_t" => Ok(CPrimType::FtwFuncT(ident)),
            "__ftw64_func_t" => Ok(CPrimType::Ftw64FuncT(ident)),
            "__nftw_func_t" => Ok(CPrimType::NftwFuncT(ident)),
            "__nftw64_func_t" => Ok(CPrimType::Nftw64FuncT(ident)),
            _ => Err(Error::new(ident.span(), "Unable to parse inner CType")),
        }
    }
}

pub enum CType {
    PtrMut(Token![*], CPrimType),
    PtrConst(Token![*], Option<Token![const]>, CPrimType),
    PrimType(CPrimType),
}

impl Parse for CType {
    fn parse(input: ParseStream) -> Result<Self> {
        if input.peek(Token![const]) {
            let constt = input.parse()?;
            let inner = input.parse()?;
            let star = input.parse()?;
            Ok(CType::PtrConst(star, Some(constt), inner))
        } else {
            let inner: CPrimType = input.parse()?;
            if input.peek(Token![*]) {
                let star = input.parse()?;
                Ok(CType::PtrMut(star, inner))
            } else {
                Ok(CType::PrimType(inner))
            }
        }
    }
}

pub struct ArgType {
    pub ty: CType,
    pub arg: Ident,
}

impl Parse for ArgType {
    fn parse(input: ParseStream) -> Result<Self> {
        Ok(Self {
            ty: input.parse()?,
            arg: input.parse()?,
        })
    }
}

pub struct CFuncSig {
    pub return_type: CType,
    pub name: Ident,
    pub _paren: token::Paren,
    pub _void: Option<Ident>,
    pub arg_types: Punctuated<ArgType, Token![,]>,
    pub options: Vec<Ident>,
    pub semantic_pre_call: Block,
    pub semantic_post_call: Block,
}

impl CFuncSig {
    pub fn guard_call(&self) -> bool {
        self.options.iter().any(|ident| ident.to_string() == "guard_call")
    }
}

impl Parse for CFuncSig {
    fn parse(input: ParseStream) -> Result<Self> {
        let return_type = input.parse()?;
        let name = input.parse()?;
        let content;
        let _paren = parenthesized!(content in input);
        let _void;
        let arg_types;
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

        let mut options = vec![];
        while input.peek(Ident) {
            options.push(input.parse::<Ident>().unwrap());
        }

        let semantic_pre_call = input.parse::<Block>()?;
        let semantic_post_call = input.parse::<Block>()?;

        Ok(Self {return_type, name, _paren, _void, arg_types, options, semantic_pre_call, semantic_post_call})
    }
}

pub struct CFuncSigs (pub Vec<CFuncSig>);

impl Parse for CFuncSigs {
    fn parse(input: ParseStream) -> Result<Self> {
        Ok(Self (parse_all(input, CFuncSig::parse)?))
    }
}

fn parse_all<Elem>(input: &ParseBuffer, parser: fn(_: ParseStream<'_>) -> Result<Elem>) -> Result<Vec<Elem>> {
    let mut ret = Vec::new();
    while !input.is_empty() {
        ret.push(parser(input)?);
    }
    Ok(ret)
}

pub fn cprim_type_to_type(typ: &CPrimType) -> proc_macro2::TokenStream {
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
        // Special case since __ftw_func_t is not wrapped in libc crate.
        CPrimType::FtwFuncT(_) => quote!(*const libc::c_void),
        CPrimType::Ftw64FuncT(_) => quote!(*const libc::c_void),
        CPrimType::NftwFuncT(_) => quote!(*const libc::c_void),
        CPrimType::Nftw64FuncT(_) => quote!(*const libc::c_void),
    }
}

pub fn ctype_to_type(typ: &CType) -> proc_macro2::TokenStream {
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

pub fn cprim_type_to_obj(typ: &CPrimType) -> proc_macro2::TokenStream {
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
        CPrimType::FtwFuncT(_) => quote!(CPrimType::FtwFuncT),
        CPrimType::Ftw64FuncT(_) => quote!(CPrimType::Ftw64FuncT),
        CPrimType::NftwFuncT(_) => quote!(CPrimType::NftwFuncT),
        CPrimType::Nftw64FuncT(_) => quote!(CPrimType::Nftw64FuncT),
    }
}

pub fn ctype_to_obj(typ: &CType) -> proc_macro2::TokenStream {
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
