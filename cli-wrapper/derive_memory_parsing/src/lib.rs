#[proc_macro_derive(MemoryParsable)]
pub fn derive(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    (match derive_(proc_macro2::TokenStream::from(input)) {
        Ok(output) => output,
        Err(err) => err.into_compile_error(),
    })
    .into()
}

fn derive_(input: proc_macro2::TokenStream) -> syn::Result<proc_macro2::TokenStream> {
    syn::parse2::<syn::DeriveInput>(input).and_then(|derive_input| {
        let ident = derive_input.ident.clone();
        match &derive_input.data {
            syn::Data::Struct(struct_) => derive_struct(&ident, struct_, &derive_input.attrs),
            syn::Data::Enum(enum_) => derive_enum(&ident, enum_, &derive_input.attrs),
            syn::Data::Union(union_) => Err(syn::Error::new(
                union_.union_token.span,
                "Unions are not supported; try enum",
            )),
        }
    })
}

fn derive_struct(
    ident: &syn::Ident,
    input: &syn::DataStruct,
    attributes: &[syn::Attribute],
) -> syn::Result<proc_macro2::TokenStream> {
    if is_repr(attributes, "C") {
        let named_idents = get_named_idents(&input.fields);
        let types = get_types(&input.fields);
        let tuple_type = quote::quote! {(#(#types),*)};
        let constructor_args = match &input.fields {
            syn::Fields::Named(_) => quote::quote! {{#(#named_idents),*}},
            syn::Fields::Unnamed(_) => quote::quote! {(#(#named_idents),*)},
            syn::Fields::Unit => quote::quote! {{}},
        };
        let c_name = format!("struct {}", ident);
        Ok(quote::quote! {
            impl ::memory_parsing::SizedMemory for #ident {
                fn size() -> usize {
                    <#tuple_type as ::memory_parsing::SizedMemory>::size()
                }
                fn align() -> usize {
                    <#tuple_type as ::memory_parsing::SizedMemory>::align()
                }
                fn offsets() -> Vec<usize> {
                    <#tuple_type as ::memory_parsing::SizedMemory>::offsets()
                }
                fn c_name() -> Option<&'static str> {
                    Some(#c_name)
                }
            }
            impl ::memory_parsing::FromMemory for #ident {
                fn from_memory(memory: &::memory_parsing::Segments, pointer: usize) -> eyre::Result<(#ident, usize)> {
                    let ((#(#named_idents),*), new_pointer) = ::memory_parsing::FromMemory::from_memory(memory, pointer)?;
                    Ok((#ident #constructor_args, new_pointer))
                }
            }
            impl ::memory_parsing::ToMemory for #ident {
                fn to_memory(&self, memory: &mut ::memory_parsing::Segments, mut pointer: usize) -> eyre::Result<usize> {
                    let #ident #constructor_args = &self;
                    let tuple = (#(#named_idents,)*);
                    tuple.to_memory(memory, pointer)
                }
            }
        })
    } else {
        Err(syn::Error::new(
            ident.span(),
            format!("struct {ident} must be #[repr(C)]"),
        ))
    }
}

fn derive_enum(
    ident: &syn::Ident,
    input: &syn::DataEnum,
    attributes: &[syn::Attribute],
) -> syn::Result<proc_macro2::TokenStream> {
    if !is_repr(attributes, ENUM_TYPE_NAME) {
        return Err(syn::Error::new(
            ident.span(),
            format!("Must be #[repr({ENUM_TYPE_NAME})]"),
        ));
    }
    let discriminants = get_discriminants(input)?;
    let from_memory_match_arms = input.variants.iter().zip(discriminants.iter()).map(|(variant, discriminant)| {
        let named_idents = get_named_idents(&variant.fields);
        let constructor_args = match &variant.fields {
            syn::Fields::Named(_) => quote::quote!{{#(#named_idents),*}},
            syn::Fields::Unnamed(_) => quote::quote!{(#(#named_idents),*)},
            syn::Fields::Unit => quote::quote!{{}},
        };
        let variant_ident = &variant.ident;
            let types = get_types(&variant.fields);
            let tuple_type = quote::quote! {(#(#types),*)};
        quote::quote!{
            #discriminant => {
                let pointer = ::memory_parsing::align_pointer::<#tuple_type>(pointer);
                let ((#(#named_idents),*), pointer) = ::memory_parsing::FromMemory::from_memory(memory, pointer)?;
                Ok((#ident::#variant_ident #constructor_args, pointer))
            }
        }
    }).collect::<Vec<_>>();
    let to_memory_match_arms = input
        .variants
        .iter()
        .zip(discriminants.iter())
        .map(|(variant, discriminant)| {
            let named_idents = get_named_idents(&variant.fields);
            let constructor_args = match &variant.fields {
                syn::Fields::Named(_) => quote::quote! {{#(#named_idents),*}},
                syn::Fields::Unnamed(_) => quote::quote! {(#(#named_idents),*)},
                syn::Fields::Unit => quote::quote! {{}},
            };
            let variant_ident = &variant.ident;
            let types = get_types(&variant.fields);
            let tuple_type = quote::quote! {(#(#types),*)};
            quote::quote! {
                #ident::#variant_ident #constructor_args => {
                    let discriminant: u8 = #discriminant;
                    let pointer = discriminant.to_memory(memory, pointer)?;
                    let pointer = ::memory_parsing::align_pointer::<#tuple_type>(pointer);
                    let tuple = (#(#named_idents,)*);
                    let pointer = tuple.to_memory(memory, pointer)?;
                    Ok(pointer)
                },
            }
        })
        .collect::<Vec<_>>();
    let aligns = input
        .variants
        .iter()
        .map(|variant| {
            let types = get_types(&variant.fields);
            let tuple_type = quote::quote! {(#(#types),*)};
            quote::quote! {
                let align = align.max(<#tuple_type as ::memory_parsing::SizedMemory>::align());
            }
        })
        .collect::<Vec<_>>();
    let sizes = input
        .variants
        .iter()
        .map(|variant| {
            let types = get_types(&variant.fields);
            let tuple_type = quote::quote! {(#(#types),*)};
            quote::quote! {
                let tuple_size = ::memory_parsing::align_pointer::<#tuple_type>(tag_size) + <#tuple_type as ::memory_parsing::SizedMemory>::size();
                let size = size.max(tuple_size);
            }
        })
        .collect::<Vec<_>>();
    let any_variant_has_fields = input
        .variants
        .iter()
        .any(|variant| !variant.fields.is_empty());
    let c_name = if any_variant_has_fields {
        format!("union {}", ident)
    } else {
        format!("{}", ident)
    };
    Ok(quote::quote! {
        impl ::memory_parsing::SizedMemory for #ident {
            fn align() -> usize {
                let align = 1;
                #(#aligns)*
                align
            }
            fn size() -> usize {
                let tag_size = 1;
                let size = tag_size;
                #(#sizes)*
                ::memory_parsing::align_pointer::<Self>(size)
            }
            fn offsets() -> Vec<usize> {
                vec![]
            }
            fn c_name() -> Option<&'static str> {
                Some(#c_name)
            }
        }
        impl ::memory_parsing::FromMemory for #ident {
            fn from_memory(memory: &::memory_parsing::Segments, mut pointer: usize) -> eyre::Result<(#ident, usize)> {
                let (tag, pointer) = ::memory_parsing::FromMemory::from_memory(memory, pointer)?;
                match tag {
                    #(#from_memory_match_arms)*
                    _ => Err(eyre::eyre!("tag {tag} is not recognized for {}", stringify!(#ident))),
                }
            }
        }
        impl ::memory_parsing::ToMemory for #ident {
            fn to_memory(&self, memory: &mut ::memory_parsing::Segments, mut pointer: usize) -> eyre::Result<usize> {
                match self {
                    #(#to_memory_match_arms)*
                }
            }
        }
    })
}

fn get_named_idents(fields: &syn::Fields) -> Vec<syn::Ident> {
    match fields {
        syn::Fields::Named(fields) => fields
            .named
            .iter()
            .map(|field| field.ident.as_ref().unwrap().clone())
            .collect(),
        syn::Fields::Unnamed(fields) => (0..fields.unnamed.len())
            .map(|idx| syn::Ident::new(&format!("field_{idx}"), proc_macro2::Span::call_site()))
            .collect(),
        syn::Fields::Unit => vec![],
    }
}

fn get_types(fields: &syn::Fields) -> Vec<&syn::Type> {
    match fields {
        syn::Fields::Named(fields) => fields.named.iter().map(|field| &field.ty).collect(),
        syn::Fields::Unnamed(fields) => fields.unnamed.iter().map(|field| &field.ty).collect(),
        syn::Fields::Unit => vec![],
    }
}

fn get_discriminants(data_enum: &syn::DataEnum) -> syn::Result<Vec<u8>> {
    let mut unused_discriminant = 0u8;
    let discriminants = data_enum
        .variants
        .iter()
        .map(|variant| {
            let discriminant = match &variant.discriminant {
                Some((_, discriminant_expr)) => expr_to_int::<EnumType>(discriminant_expr)
                    .map_err(|err| {
                        syn::Error::new(
                            syn::spanned::Spanned::span(discriminant_expr),
                            err.to_string(),
                        )
                    })?,
                None => unused_discriminant,
            };
            unused_discriminant = discriminant + 1u8;
            Ok(discriminant)
        })
        .collect::<syn::Result<Vec<_>>>()?;
    Ok(discriminants)
}

const ENUM_TYPE_NAME: &str = "u8";
type EnumType = u8;

fn expr_to_int<Int>(expr: &syn::Expr) -> eyre::Result<Int>
where
    Int: std::str::FromStr,
    Int::Err: std::fmt::Display,
{
    match expr {
        syn::Expr::Lit(lit_expr) => match &lit_expr.lit {
            syn::Lit::Int(int) => int.base10_parse::<Int>().map_err(|err| {
                let type_name = std::any::type_name::<Int>();
                eyre::eyre!("Could not parse {expr:?} as {type_name}: {err:?}")
            }),
            _ => Err(eyre::eyre!("{expr:?} is not an integer")),
        },
        _ => Err(eyre::eyre!("{expr:?} is not a literal")),
    }
}

fn is_repr(attributes: &[syn::Attribute], repr_arg: &str) -> bool {
    attributes.iter().any(|attribute| {
        attribute.style == syn::AttrStyle::Outer
            && match &attribute.meta {
                syn::Meta::List(list) => list.path.segments.iter().any(|segment| {
                    segment.ident == "repr"
                        && list
                            .tokens
                            .clone()
                            .into_iter()
                            .any(|token_tree| match token_tree {
                                proc_macro2::TokenTree::Ident(ident) => ident == repr_arg,
                                _ => false,
                            })
                }),
                _ => false,
            }
    })
}

#[cfg(test)]
fn is_impl(item: &syn::Item) -> bool {
    matches!(item, syn::Item::Impl(_))
}

#[cfg(test)]
#[test]
fn test_derive_named_struct() -> syn::Result<()> {
    derive_(quote::quote! {
        #[repr(C)]
        struct Test {
            a: u64,
            b: u64,
        }
    })
    .and_then(|stream| {
        syn::parse2::<syn::File>(stream).map(|file| {
            assert_eq!(file.items.len(), 3);
            assert!(is_impl(&file.items[0]), "{:?}", &file.items[0]);
        })
    })?;
    assert!(derive_(quote::quote! {
        struct Test { }
    })
    .is_err());
    Ok(())
}

#[cfg(test)]
#[test]
fn test_derive_tuple_struct() -> syn::Result<()> {
    derive_(quote::quote! {
        #[repr(C)]
        struct Test(u64, u64);
    })
    .and_then(|stream| {
        syn::parse2::<syn::File>(stream).map(|file| {
            assert_eq!(file.items.len(), 3);
            assert!(is_impl(&file.items[0]), "{:?}", &file.items[0]);
        })
    })
}

#[cfg(test)]
#[test]
fn test_derive_enum() -> syn::Result<()> {
    derive_(quote::quote! {
        #[repr(u8)]
        enum Test {
            A,
            B(u64),
            C{int: u64},
        }
    })
    .and_then(|stream| {
        syn::parse2::<syn::File>(stream).map(|file| {
            assert_eq!(file.items.len(), 3);
            assert!(is_impl(&file.items[0]));
        })
    })?;
    assert!(derive_(quote::quote! {
        #[repr(C)]
        enum Test { }
    })
    .is_err());
    Ok(())
}

#[cfg(test)]
#[test]
fn ui() {
    let t = trybuild::TestCases::new();
    t.pass("tests/*.rs");
}
