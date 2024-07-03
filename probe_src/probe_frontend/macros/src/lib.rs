use proc_macro::TokenStream;
use proc_macro2::Span;
use quote::quote;
use syn::parse_quote;
use syn::{parse_macro_input, Data, DeriveInput, Fields, Ident, Type};

mod pygen;

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

            let field_types = pairs.into_iter().map(|x| x.1).collect::<Vec<_>>();

            let new_name = Ident::new(
                ident
                    .to_string()
                    .strip_prefix("C_")
                    .expect("struct name doesn't start with 'C_'"),
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
                #[derive(Debug, Clone, Serialize, Deserialize, MakePyDataclass)]
                pub struct #new_name {
                    #(pub #field_idents: #field_types,)*

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
                            #field_idents: value.#field_idents
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
                let name = Ident::new(name, Span::mixed_site());
                parse_quote!(#name)
            } else {
                Type::Path(inner.clone())
            }
        }
        _ => unreachable!("unsupported bindgen type conversion"),
    }
}

pub(crate) fn type_basename(ty: &syn::TypePath) -> &syn::Ident {
    if ty.qself.is_some() {
        unimplemented!("qualified self-typs not supported");
    }

    &ty.path.segments.last().expect("type has no segments").ident
}

// TODO: return compiler error instead of panicking on error
#[proc_macro_derive(MakePyDataclass)]
pub fn make_py_dataclass(input: TokenStream) -> TokenStream {
    let source = parse_macro_input!(input as DeriveInput);
    pygen::make_py_dataclass_internal(source);
    // return empty token stream, we're not actually writing rust here
    TokenStream::new()
}

// TODO: return compiler error instead of panicking on error
#[proc_macro]
pub fn write_pygen_file_from_env(item: TokenStream) -> TokenStream {
    let path = parse_macro_input!(item as syn::LitStr);
    pygen::write_pygen_internal(path);
    // return empty token stream, we're not actually writing rust here
    TokenStream::new()
}
