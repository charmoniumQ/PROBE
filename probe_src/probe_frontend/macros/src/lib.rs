use proc_macro::TokenStream;
use proc_macro2::Span;
use quote::quote;
use syn::parse::Parse;
use syn::{parse_macro_input, Data, DeriveInput, Fields, Ident, Type};
use syn::{parse_quote, LitStr, Token};

mod pygen;

/// Generate a native rust struct from a rust-bindgen struct.
///
/// In order to successfully generate a new struct, the struct it's invoked on must have the
/// following characteristics:
///
/// - be a named struct (tuple and unit structs not supported).
/// - Name starts with `C_`.
/// - contain only types that implement `FfiFrom` (defined in probe_frontend, see ops module for
/// details).
///
/// In will generate a struct with the following characteristics:
///
/// - same name, but without the `C_` prefix, and converted from snake_case to PascalCase.
/// - any field in the original struct starting with `__` is ignored.
/// - any field in the original struct starting with `ru_`, `tv_`, or `stx_` will have that prefix
/// removed.
/// - derives serde's `Serialize`, `Deserialize` traits.
/// - contains a unit field `_type` that serializes to the struct's name.
/// - implements `FfiFrom` by calling it recursively on each field.
/// - derives [`PygenDataclass`].
// TODO: return compiler error instead of panicking on error
#[proc_macro_derive(MakeRustOp)]
pub fn make_rust_op(input: TokenStream) -> TokenStream {
    let original_struct = parse_macro_input!(input as DeriveInput);
    let DeriveInput { data, ident, .. } = original_struct.clone();

    match data {
        Data::Struct(data_struct) => {
            let fields = match data_struct.fields {
                Fields::Named(x) => x,
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
                }

                impl FfiFrom<#ident> for #new_name {
                    fn ffi_from(value: &#ident, ctx: &ArenaContext) -> Result<Self> {
                        Ok(Self {
                            _type: (),
                            #(
                            #field_idents_stripped: value.#field_idents
                                .ffi_into(ctx)
                                .map_err(|e| {
                                    ProbeError::FFiConversionError {
                                        msg: #msgs,
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
/// Generate a python dataclass from a rust struct.
///
/// In order to successfully generate a dataclass, the struct it's invoked on must have the
/// following characteristics:
///
/// - be a named struct (tuple and unit structs not supported).
/// - OR be an enum with either named variants or tuple enums containing only one item.
/// - contain only primitives, [`CString`](std::ffi::CString)s, or other generated dataclasses.
/// - field with the unit type are also allowed, but they're ignored.
// TODO: return compiler error instead of panicking on error
#[proc_macro_derive(PygenDataclass)]
pub fn pygen_dataclass(input: TokenStream) -> TokenStream {
    let source = parse_macro_input!(input as DeriveInput);
    pygen::pygen_dataclass_internal(source);
    // return empty token stream, we're not actually writing rust here
    TokenStream::new()
}

/// write the generated python to a path contained in a environment variable.
// TODO: return compiler error instead of panicking on error
#[proc_macro]
pub fn pygen_write_to_env(input: TokenStream) -> TokenStream {
    let path = parse_macro_input!(input as syn::LitStr);
    pygen::pygen_write_internal(path);
    TokenStream::new()
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

/// Add one or more lines to the generated python file, after the imports, but before any generated
/// class or enum.
// TODO: return compiler error instead of panicking on error
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
