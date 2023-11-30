extern crate proc_macro;

use syn::{parenthesized, parse_macro_input, token, Type, Ident, Token, Result};
use syn::parse::{Parse, ParseStream};
use syn::punctuated::Punctuated;
use quote::{quote, ToTokens, format_ident};

// macro_rules! log_libc_calls {
//     {
//         $(fn $func_name:ident($($arg:ident: $type:ty),*) -> $ret:ty;)*
//     } => {
//         $(
//             paste!{
//                 redhook::hook! {
//                     unsafe fn $func_name($($arg: $type),*) -> $ret => [< logged_ $func_name >] {
//                         let ret = real!($func_name)($($arg),*);
// 		                PROV_LOGGER.[< $ident >]($($arg),*, ret);
// 		                ret
//                     }
//                 }
//             }
//         )*
//     }
// }

/*
 * These macros are purpose-made for one use within the containing project.
 */

struct ArgType {
    arg: Ident,
    _colon: Token![:],
    ty: Type,
}

impl ToTokens for ArgType {
    fn to_tokens(&self, tokens: &mut proc_macro2::TokenStream) {
        self.arg.to_tokens(tokens);
        self._colon.to_tokens(tokens);
        self.ty.to_tokens(tokens);
    }
}

impl Parse for ArgType {
    fn parse(input: ParseStream) -> Result<Self> {
        Ok(Self {
            arg: input.parse()?,
            _colon: input.parse()?,
            ty: input.parse()?,
        })
    }
}

struct LibCall {
    _fn: Token![fn],
    name: Ident,
    _paren_token: token::Paren,
    arg_types: Punctuated<ArgType, Token![,]>,
    _arrow: Token![->],
    return_type: Type,
}

impl Parse for LibCall {
    fn parse(input: ParseStream) -> Result<Self> {
        let content;
        Ok(Self {
            _fn: input.parse()?,
            name: input.parse()?,
            _paren_token: parenthesized!(content in input),
            arg_types: content.parse_terminated(ArgType::parse, Token![,])?,
            _arrow: input.parse()?,
            return_type: input.parse()?,
        })
    }
}

struct LibCalls {
    lib_calls: Punctuated<LibCall, Token![;]>,
}

impl Parse for LibCalls {
    fn parse(input: ParseStream) -> Result<Self> {
        Ok(Self {lib_calls: input.parse_terminated(LibCall::parse, Token![;])?})
    }
}

#[proc_macro]
pub fn log_libc_calls(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let input = parse_macro_input!(input as LibCalls);

    let output: proc_macro2::TokenStream =
        input
        .lib_calls
        .iter()
        .map(|lib_call| {
            let name = &lib_call.name;
            let args_types = lib_call.arg_types.iter();
            let args = lib_call.arg_types.iter().map(|arg_type| {
                proc_macro2::TokenTree::Ident(arg_type.arg.clone())
            }).collect::<Vec<proc_macro2::TokenTree>>();
            let return_type = &lib_call.return_type;
            let traced_name = format_ident!("__traced_{}", lib_call.name);
            quote!{
                redhook::hook! {
                    unsafe fn #name(
                        #(#args_types),*
                    ) -> #return_type => #traced_name {
                        let ret = real!(#name)( #(#args),* );
                        PROV_LOGGER.#name( #(#args,)* ret);
                        ret
                    }
                }
            }
        })
        .collect();

    proc_macro::TokenStream::from(output)
}

#[proc_macro]
pub fn create_trait(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let input = parse_macro_input!(input as LibCalls);

    let output: proc_macro2::TokenStream =
        input
        .lib_calls
        .iter()
        .map(|lib_call| {
            let name = &lib_call.name;
            let args_types = lib_call.arg_types.iter();
            let args = lib_call.arg_types.iter().map(|arg_type| {
                proc_macro2::TokenTree::Ident(arg_type.arg.clone())
            }).collect::<Vec<proc_macro2::TokenTree>>();
            let return_type = &lib_call.return_type;
            let traced_name = format_ident!("__traced_{}", lib_call.name);
            quote!{
                redhook::hook! {
                    unsafe fn #name(
                        #(#args_types),*
                    ) -> #return_type => #traced_name {
                        let ret = real!(#name)( #(#args),* );
                        PROV_LOGGER.#name( #(#args,)* ret);
                        ret
                    }
                }
            }
        })
        .collect();

    proc_macro::TokenStream::from(output)
}
