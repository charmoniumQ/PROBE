use proc_macro::TokenStream;
use proc_macro2::Span;
<<<<<<< HEAD
use quote::{quote, quote_spanned};
use syn::parse::Parse;
use syn::spanned::Spanned;
use syn::{parse_macro_input, Data, DeriveInput, Fields, Ident, Type};
use syn::{parse_quote, LitStr, Token};

mod pygen;

type MacroResult<T> = Result<T, TokenStream>;

/// Generate a native rust struct from a rust-bindgen struct.
///
/// In order to successfully generate a new struct, the struct it's invoked on must have the
/// following characteristics:
///
/// - be a named struct (tuple and unit structs not supported).
/// - Name starts with `C_`.
/// - contain only types that implement `FfiFrom` (defined in probe_frontend, see ops module for
///   details).
///
/// In will generate a struct with the following characteristics:
///
/// - same name, but without the `C_` prefix, and converted from snake_case to PascalCase.
/// - any field in the original struct starting with `__` is ignored.
/// - any field in the original struct starting with `ru_`, `tv_`, or `stx_` will have that prefix
///   removed.
/// - derives serde's `Serialize`, `Deserialize` traits.
/// - contains a unit field `_type` that serializes to the struct's name.
/// - implements `FfiFrom` by calling it recursively on each field.
/// - derives [`PygenDataclass`].
=======
use quote::quote;
use syn::parse::Parse;
use syn::{parse_macro_input, Data, DeriveInput, Fields, Ident, Type};
use syn::{parse_quote, LitStr, Token};

mod pygen;

<<<<<<< HEAD
>>>>>>> a83cce7 (version 0.2.0)
=======
// TODO: return compiler error instead of panicking on error
>>>>>>> f7c22ab (:sparkles: documentation :sparkles:)
#[proc_macro_derive(MakeRustOp)]
pub fn make_rust_op(input: TokenStream) -> TokenStream {
    let original_struct = parse_macro_input!(input as DeriveInput);
    let DeriveInput { data, ident, .. } = original_struct.clone();

    match data {
        Data::Struct(data_struct) => {
            let fields = match data_struct.fields {
                Fields::Named(x) => x,
<<<<<<< HEAD
                _ => {
                    return quote_spanned! {
                        original_struct.span() =>
                        compile_error!("Unit and Tuple structs not supported");
                    }
                    .into()
                }
            };

            let pairs = match fields
                .named
                .iter()
                .filter_map(|field| {
                    let ident = match field.ident.as_ref() {
                        Some(x) => x,
                        None => {
                            return Some(Err(quote_spanned! {
                                field.ident.span() =>
                                compile_error!("Field had no identifier");
                            }
                            .into()))
                        }
                    };
                    let ident_str = ident.to_string();
                    for prefix in ["__spare", "__reserved"] {
                        if ident_str.starts_with(prefix) {
                            return None;
                        }
                    }

                    let pair = convert_bindgen_type(&field.ty).map(|ty| (ident, ty));
                    Some(pair)
                })
                .collect::<MacroResult<Vec<(_, _)>>>()
            {
                Ok(x) => x,
                Err(e) => return e,
            };

            let field_idents = pairs.iter().map(|x| x.0).collect::<Vec<_>>();

            let field_idents_stripped = field_idents
                .iter()
                .map(|old| {
                    let span = old.span();
                    let str = old.to_string();
                    let mut slice = str.as_str();

                    for prefix in ["ru_", "tv_", "stx_"] {
                        if let Some(stripped) = str.strip_prefix(prefix) {
                            slice = stripped;
                            break;
                        }
                    }

                    Ident::new(slice, span)
                })
                .collect::<Vec<_>>();

            let field_types = pairs.into_iter().map(|x| x.1).collect::<Vec<_>>();

            let new_name = Ident::new(
                &snake_case_to_pascal(
                    ident
                        .to_string()
                        .strip_prefix("C_")
                        .expect("struct name doesn't start with 'C_'"),
                ),
                Span::call_site(),
            );

            let msgs = field_idents
                .iter()
                .map(|field_ident| {
                    format!(
                        "Error calling ffi_into() on {} while creating {}",
                        field_ident, new_name
                    )
                })
                .collect::<Vec<_>>();

            let serialize_type_path = format!("{}::serialize_type", new_name);
            let type_name = new_name.to_string();

            // This is rather bad macro hygiene, but this macro is only intend for probe_frontend's
            // op struct generation, so we're playing a little fast-n'-loose with scoping.
            quote! {
                #[derive(Debug, Clone, Serialize, Deserialize, PygenDataclass)]
                pub struct #new_name {
                    #(pub #field_idents_stripped: #field_types,)*

                    /// this is a placeholder field that get's serialized as the type name
                    #[serde(serialize_with = #serialize_type_path)]
                    #[serde(skip_deserializing)]
                    pub _type: (),
                }

                impl #new_name {
                    fn serialize_type<S: serde::Serializer>(
                        _: &(),
                        serializer: S
                    ) -> std::result::Result<S::Ok, S::Error> {
                        serializer.serialize_str(#type_name)
                    }
=======
                _ => unimplemented!("unnamed and unit structs not implemented"),
            };

            let pairs = fields
                .named
                .iter()
                .filter_map(|x| {
                    let ident = x.ident.as_ref().unwrap();
                    if ident.to_string().starts_with("__") {
                        return None;
                    }
                    Some((ident, convert_bindgen_type(&x.ty)))
                })
                .collect::<Vec<(_, _)>>();

            let field_idents = pairs.iter().map(|x| x.0).collect::<Vec<_>>();

            let field_idents_stripped = field_idents
                .iter()
                .map(|old| {
                    let span = old.span();
                    let str = old.to_string();
                    let mut slice = str.as_str();

                    for prefix in ["ru_", "tv_", "stx_"] {
                        if let Some(stripped) = str.strip_prefix(prefix) {
                            slice = stripped;
                            break;
                        }
                    }

                    Ident::new(slice, span)
                })
                .collect::<Vec<_>>();

            let field_types = pairs.into_iter().map(|x| x.1).collect::<Vec<_>>();

            let new_name = Ident::new(
                &snake_case_to_pascal(
                    ident
                        .to_string()
                        .strip_prefix("C_")
                        .expect("struct name doesn't start with 'C_'"),
                ),
                Span::call_site(),
            );

            let msgs = field_idents
                .iter()
                .map(|field_ident| {
                    format!(
                        "Error calling ffi_into() on {} while creating {}",
                        field_ident, new_name
                    )
                })
                .collect::<Vec<_>>();

            let serialize_type_path = format!("{}::serialize_type", new_name);
            let type_name = new_name.to_string();

            // This is rather bad macro hygiene, but this macro is only intend for probe_frontend's
            // op struct generation, so we're playing a little fast-n'-loose with scoping.
            quote! {
                #[derive(Debug, Clone, Serialize, Deserialize, PygenDataclass)]
                pub struct #new_name {
<<<<<<< HEAD
                    #(pub #field_idents: #field_types,)*
<<<<<<< HEAD
>>>>>>> a83cce7 (version 0.2.0)
=======
=======
                    #(pub #field_idents_stripped: #field_types,)*
>>>>>>> 122952f (improved rust struct generation)

                    /// this is a placeholder field that get's serialized as the type name
                    #[serde(serialize_with = #serialize_type_path)]
                    #[serde(skip_deserializing)]
                    pub _type: (),
                }

                impl #new_name {
                    fn serialize_type<S: serde::Serializer>(
                        _: &(),
                        serializer: S
                    ) -> std::result::Result<S::Ok, S::Error> {
                        serializer.serialize_str(#type_name)
                    }
>>>>>>> 0beca52 (improved pygen code)
                }

                impl FfiFrom<#ident> for #new_name {
                    fn ffi_from(value: &#ident, ctx: &ArenaContext) -> Result<Self> {
                        Ok(Self {
<<<<<<< HEAD
<<<<<<< HEAD
                            _type: (),
                            #(
                            #field_idents_stripped: value.#field_idents
<<<<<<< HEAD
                                .ffi_into(ctx)
                                .map_err(|e| {
                                    ProbeError::FFiConversionError {
                                        msg: #msgs,
=======
=======
                            _type: (),
>>>>>>> 0beca52 (improved pygen code)
                            #(
                            #field_idents: value.#field_idents
=======
>>>>>>> 122952f (improved rust struct generation)
                                .ffi_into(ctx)
                                .map_err(|e| {
                                    ProbeError::FFiConversionError {
<<<<<<< HEAD
                                        msg: "Error calling ffi_into() on\
<<<<<<< HEAD
                                            #field_idents creating #new_name", 
>>>>>>> a83cce7 (version 0.2.0)
=======
                                            #field_idents creating #new_name",
>>>>>>> b5a2591 (fix cargo fmt/clippy)
=======
                                        msg: #msgs,
>>>>>>> 0beca52 (improved pygen code)
                                        inner: Box::new(e),
                                    }
                                })?,
                            )*
                        })
                    }
                }
            }
            .into()
        }
<<<<<<< HEAD
        _ => quote_spanned! {
            original_struct.span() =>
            compile_error!("MakeRustOp only supports structs");
        }
        .into(),
    }
}

fn convert_bindgen_type(ty: &syn::Type) -> MacroResult<syn::Type> {
    match ty {
        syn::Type::Ptr(_inner) => Ok(parse_quote!(::std::ffi::CString)),
        syn::Type::Array(inner) => {
            let mut new = inner.clone();
            new.elem = Box::new(convert_bindgen_type(&new.elem)?);
            Ok(Type::Array(new))
        }
        syn::Type::Path(inner) => {
            if let Some(name) = type_basename(inner)?.to_string().strip_prefix("C_") {
                let name = snake_case_to_pascal(name);
                let name = Ident::new(&name, Span::mixed_site());
                Ok(parse_quote!(#name))
            } else {
                Ok(Type::Path(inner.clone()))
            }
        }
        _ => Err(quote_spanned! {
            ty.span() =>
            compile_error!("Unable to convert bindgen type");
        }
        .into()),
    }
}

fn type_basename(ty: &syn::TypePath) -> MacroResult<&syn::Ident> {
    if let Some(qself) = &ty.qself {
        return Err(quote_spanned! {
            qself.span() =>
            compile_error!("Qualified self types not supported");
        }
        .into());
    }

    match ty.path.segments.last() {
        Some(x) => Ok(&x.ident),
        None => Err(quote_spanned! {
            ty.path.segments.span() =>
            compile_error!("Type path has no segments");
        }
        .into()),
    }
}

fn snake_case_to_pascal(input: &str) -> String {
    input
        .chars()
        .fold((true, String::new()), |(prior_underscore, mut acc), ch| {
            if ch == '_' {
                return (true, acc);
            } else if prior_underscore {
                ch.to_uppercase().for_each(|x| acc.push(x))
            } else {
                acc.push(ch)
            }
            (false, acc)
        })
        .1
}

/// Generate a python dataclass from a rust struct.
///
/// In order to successfully generate a dataclass, the struct it's invoked on must have the
/// following characteristics:
///
/// - be a named struct (tuple and unit structs not supported).
/// - OR be an enum with either named variants or tuple enums containing only one item.
/// - contain only primitives, [`CString`](std::ffi::CString)s, or other generated dataclasses.
/// - field with the unit type are also allowed, but they're ignored.
#[proc_macro_derive(PygenDataclass)]
pub fn pygen_dataclass(input: TokenStream) -> TokenStream {
    let source = parse_macro_input!(input as DeriveInput);
    match pygen::pygen_dataclass_internal(source) {
        Ok(_) => TokenStream::new(),
        Err(e) => e,
    }
}

/// write the generated python to a path contained in a environment variable.
#[proc_macro]
pub fn pygen_write_to_env(input: TokenStream) -> TokenStream {
    let path = parse_macro_input!(input as syn::LitStr);
    match pygen::pygen_write_internal(path) {
        Ok(_) => TokenStream::new(),
        Err(e) => e,
    }
}

/// add a property to a python dataclass with the following syntax:
///
/// ```
/// pygen_add_prop!(ClassName impl prop_name -> return_type:
///     "line1",
///     "return line2"
///     ...
/// );
/// ```
#[proc_macro]
pub fn pygen_add_prop(input: TokenStream) -> TokenStream {
    let args = parse_macro_input!(input as AddPropArgs);
    match pygen::pygen_add_prop_internal(args) {
        Ok(_) => TokenStream::new(),
        Err(e) => e,
    }
}

pub(crate) struct AddPropArgs {
    class: Ident,
    name: Ident,
    ret: Ident,
    body: Vec<String>,
}

impl Parse for AddPropArgs {
    fn parse(input: syn::parse::ParseStream) -> syn::Result<Self> {
        let class = input.parse()?;
        input.parse::<Token![impl]>()?;
        let name = input.parse()?;
        input.parse::<Token![->]>()?;
        let ret = input.parse()?;
        input.parse::<Token![:]>()?;

        let mut body = vec![];
        body.push(input.parse::<LitStr>()?.value());
        while !input.is_empty() {
            input.parse::<Token![,]>()?;
            if input.is_empty() {
                break;
            }
            body.push(input.parse::<LitStr>()?.value());
        }

        Ok(Self {
            class,
            name,
            ret,
            body,
        })
    }
}

/// Add one or more lines to the generated python file, after the imports, but before any generated
/// class or enum.
#[proc_macro]
pub fn pygen_add_preamble(input: TokenStream) -> TokenStream {
    let args = parse_macro_input!(input as AddPreambleArgs);
    pygen::pygen_add_preamble(args);
    TokenStream::new()
}

pub(crate) struct AddPreambleArgs(pub Vec<String>);

impl Parse for AddPreambleArgs {
    fn parse(input: syn::parse::ParseStream) -> syn::Result<Self> {
        let mut lines = vec![];
        lines.push(input.parse::<LitStr>()?.value());
        while !input.is_empty() {
            input.parse::<Token![,]>()?;
            if input.is_empty() {
                break;
            }
            lines.push(input.parse::<LitStr>()?.value());
        }

        Ok(Self(lines))
    }
}
=======
        _ => unimplemented!("MakeRustOp only supports structs"),
    }
}

fn convert_bindgen_type(ty: &syn::Type) -> syn::Type {
    match ty {
        syn::Type::Ptr(_inner) => parse_quote!(::std::ffi::CString),
        syn::Type::Array(inner) => {
            let mut new = inner.clone();
            new.elem = Box::new(convert_bindgen_type(&new.elem));
            Type::Array(new)
        }
        syn::Type::Path(inner) => {
            if let Some(name) = type_basename(inner).to_string().strip_prefix("C_") {
                let name = snake_case_to_pascal(name);
                let name = Ident::new(&name, Span::mixed_site());
                parse_quote!(#name)
            } else {
                Type::Path(inner.clone())
            }
        }
        _ => unreachable!("unsupported bindgen type conversion"),
    }
}

fn type_basename(ty: &syn::TypePath) -> &syn::Ident {
    if ty.qself.is_some() {
        unimplemented!("qualified self-typs not supported");
    }

    &ty.path.segments.last().expect("type has no segments").ident
}

fn snake_case_to_pascal(input: &str) -> String {
    input
        .chars()
        .fold((true, String::new()), |(prior_underscore, mut acc), ch| {
            if ch == '_' {
                return (true, acc);
            } else if prior_underscore {
                ch.to_uppercase().for_each(|x| acc.push(x))
            } else {
                acc.push(ch)
            }
            (false, acc)
        })
        .1
}

// TODO: return compiler error instead of panicking on error
#[proc_macro_derive(PygenDataclass)]
pub fn pygen_dataclass(input: TokenStream) -> TokenStream {
    let source = parse_macro_input!(input as DeriveInput);
    pygen::pygen_dataclass_internal(source);
    // return empty token stream, we're not actually writing rust here
    TokenStream::new()
}
<<<<<<< HEAD
>>>>>>> a83cce7 (version 0.2.0)
=======

// TODO: return compiler error instead of panicking on error
#[proc_macro]
pub fn pygen_write_to_env(input: TokenStream) -> TokenStream {
    let path = parse_macro_input!(input as syn::LitStr);
    pygen::pygen_write_internal(path);
    TokenStream::new()
}
<<<<<<< HEAD
>>>>>>> 0beca52 (improved pygen code)
=======

// TODO: return compiler error instead of panicking on error
#[proc_macro]
pub fn pygen_add_prop(input: TokenStream) -> TokenStream {
    let args = parse_macro_input!(input as AddPropArgs);
    pygen::pygen_add_prop_internal(args);
    TokenStream::new()
}

pub(crate) struct AddPropArgs {
    class: Ident,
    name: Ident,
    ret: Ident,
    body: Vec<String>,
}

impl Parse for AddPropArgs {
    fn parse(input: syn::parse::ParseStream) -> syn::Result<Self> {
        let class = input.parse()?;
        input.parse::<Token![impl]>()?;
        let name = input.parse()?;
        input.parse::<Token![->]>()?;
        let ret = input.parse()?;
        input.parse::<Token![:]>()?;

        let mut body = vec![];
        body.push(input.parse::<LitStr>()?.value());
        while !input.is_empty() {
            input.parse::<Token![,]>()?;
            body.push(input.parse::<LitStr>()?.value());
        }

        Ok(Self {
            class,
            name,
            ret,
            body,
        })
    }
}

#[proc_macro]
pub fn pygen_add_preamble(input: TokenStream) -> TokenStream {
    let args = parse_macro_input!(input as AddPreambleArgs);
    pygen::pygen_add_preamble(args);
    TokenStream::new()
}

pub(crate) struct AddPreambleArgs(pub Vec<String>);

impl Parse for AddPreambleArgs {
    fn parse(input: syn::parse::ParseStream) -> syn::Result<Self> {
        let mut lines = vec![];
        lines.push(input.parse::<LitStr>()?.value());
        while !input.is_empty() {
            input.parse::<Token![,]>()?;
            lines.push(input.parse::<LitStr>()?.value());
        }

        Ok(Self(lines))
    }
}
>>>>>>> e1414d9 (pygen custom `@property`s)
