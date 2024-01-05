extern crate proc_macro;

mod parsable;

use parsable::*;
use std::vec::Vec;
use syn::parse_macro_input;
use quote::{quote, format_ident};

/*
 * These macros are purpose-made for one use within the containing project.
 */

const PRINT_DEBUG: bool = false;
const INCLUDE_RTTI: bool = false;

#[proc_macro]
pub fn populate_libc_calls_and_hook_fns(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let input = parse_macro_input!(input as CFuncSigs);

    let hook_fns =
        input
        .0
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
            let args = cfunc_sig.arg_types.iter().map(|arg_type| arg_type.arg.clone()).collect::<Vec<_>>();

            let condition = if cfunc_sig.guard_call() { quote!(globals::ENABLE_TRACE.get()) } else { quote!(true) };
            let (print_begin, print_end, print_call0, print_call1, print_call2, print_call3);
            if PRINT_DEBUG {
                let arg_fmt_string = cfunc_sig
                    .arg_types
                    .iter()
                    .map(|arg_type| format!(":{}={{:?}}", arg_type.arg.to_string()))
                    .collect::<Vec<_>>()
                    .join(" ");
                let arg_fmt_args = cfunc_sig.arg_types.iter().map(|arg_type| {
                    let arg = &arg_type.arg;
                    let arg_rep = match arg_type.ty {
                        CType::PtrConst(_, _, CPrimType::Char(_)) => quote!(unsafe{crate::util::short_cstr(#arg)}),
                        _ => quote!(#arg),
                    };
                    quote!(#arg_rep)
                });
                let whole_arg_str = format!("  (call {} {} :unguard {} :ENABLE_TRACE {{}})", name.to_string(), arg_fmt_string, !cfunc_sig.guard_call());
                print_begin = quote!{
                    println!("(processing");
                    println!(#whole_arg_str, #(#arg_fmt_args),*, globals::ENABLE_TRACE.get());
                };
                print_end = quote!{
                    println!(" (returning ret={:?} errno={})", real_call_return, *libc::__errno_location());
                };
                print_call0 = quote!(print!("  (pre_call "););
                print_call1 = quote!(print!(")\n  (real_call "););
                print_call2 = quote!(print!(":ret {:?} :errno {})\n  (post_call ", call_return, *libc::__errno_location()););
                print_call3 = quote!(print!(")\n"););
            } else {
                print_begin = quote!();
                print_end = quote!();
                print_call0 = quote!();
                print_call1 = quote!();
                print_call2 = quote!();
                print_call3 = quote!();
            }
            let pre_call  = format_ident!( "pre_{}", name);
            let post_call = format_ident!("post_{}", name);
            quote!{
                redhook::hook! {
                    unsafe fn #name(
                        #(#arg_colon_types),*
                    ) -> #return_type => #traced_name {
                        #print_begin
                        let real_call_return = if #condition {
                            PROV_LOGGER.with_borrow_mut(|_prov_logger| {
                                let prov_logger = &mut _prov_logger.inner;
                                #print_call0
                                prov_logger.#pre_call(#(#args,)*);
                                #print_call1
                                let call_return = redhook::real!(#name)(#(#args,)*);
                                #print_call2
                                prov_logger.#post_call(#(#args,)* call_return);
                                #print_call3
                                call_return
                            })
                        } else {
                            redhook::real!(#name)(#(#args,)*)
                        };
                        #print_end
                        real_call_return
                    }
                }
            }
        });

    let cfunc_sigs =
        input
        .0
        .iter()
        .map(|cfunc_sig| {
            let name = &cfunc_sig.name;
            let arg_types = cfunc_sig.arg_types.iter().map(|arg_type| {
                let arg = &arg_type.arg;
                let ty = ctype_to_obj(&arg_type.ty);
                quote!(ArgType{arg: stringify!(#arg), ty: #ty})
            });
            let return_type = ctype_to_obj(&cfunc_sig.return_type);
            quote!(
                (stringify!(#name), CFuncSig{
                    return_type: #return_type,
                    name: stringify!(#name),
                    arg_types: &[#(#arg_types),*],
                })
            )
        });
    let cfunc_sigs_stmt = if INCLUDE_RTTI {
        quote!{
            lazy_static::lazy_static! {
                static ref CFUNC_SIGS: CFuncSigs = CFuncSigs::from([
                    #(#cfunc_sigs),*
                ]);
            }
        }
    } else { quote!() };

    let prov_logger_trait_fns =
        input
        .0
        .iter()
        .map(|cfunc_sig| {
            let name = &cfunc_sig.name;
            let pre_name = format_ident!("pre_{}", name.to_string());
            let post_name = format_ident!("post_{}", name.to_string());
            let arg_colon_types = cfunc_sig.arg_types.iter().map(|arg_type| {
                let ty = ctype_to_type(&arg_type.ty);
                let arg = format_ident!("_{}", arg_type.arg.to_string());
                quote!{#arg: #ty}
            }).collect::<Vec<_>>();
            let return_type = ctype_to_type(&cfunc_sig.return_type);
            quote!{
                fn #pre_name(&mut self, #(#arg_colon_types,)*) { }
                fn #post_name(&mut self, #(#arg_colon_types,)* _return_value: #return_type) { }
            }
        });

    let strace_prov_logger_fns =
        input
        .0
        .iter()
        .map(|cfunc_sig| {
            let name = &cfunc_sig.name;
            let post_name = format_ident!("post_{}", name.to_string());
            let arg_colon_types = cfunc_sig.arg_types.iter().map(|arg_type| {
                let ty = ctype_to_type(&arg_type.ty);
                let arg = &arg_type.arg;
                quote!{#arg: #ty}
            });
            let return_type = ctype_to_type(&cfunc_sig.return_type);
            let arg_fmt_string = cfunc_sig
                .arg_types
                .iter()
                .map(|arg_types| arg_types.arg.to_string() + "={:?}")
                .collect::<Vec<_>>()
                .join(", ");
            let arg_fmt_args = cfunc_sig.arg_types.iter().map(|arg_type| {
                let arg = &arg_type.arg;
                let arg_rep = match arg_type.ty {
                    CType::PtrConst(_, _, CPrimType::Char(_)) => quote!(unsafe{crate::util::short_cstr(#arg)}),
                    _ => quote!(#arg),
                };
                arg_rep
            });
            let whole_arg_str = format!("{}({}) -> {{:?}}\n", name.to_string(), arg_fmt_string);
            quote!{
                fn #post_name(&mut self, #(#arg_colon_types,)* ret: #return_type) {
                    use std::io::Write;
                    std::write!(self.file, #whole_arg_str, #(#arg_fmt_args,)* ret).unwrap();
                }
            }
        });

    let semantic_prov_logger_fns =
        input
        .0
        .iter()
        .map(|cfunc_sig| {
            let name = &cfunc_sig.name;
            let pre_name = format_ident!("pre_{}", name.to_string());
            let post_name = format_ident!("post_{}", name.to_string());
            let arg_colon_types = cfunc_sig.arg_types.iter().map(|arg_type| {
                let ty = ctype_to_type(&arg_type.ty);
                let arg = &arg_type.arg;
                quote!{#arg: #ty}
            }).collect::<Vec<_>>();
            let return_type = ctype_to_type(&cfunc_sig.return_type);
            let pre_call = cfunc_sig.semantic_pre_call.clone();
            let post_call = cfunc_sig.semantic_post_call.clone();
            quote!{
                fn #pre_name(&mut self, #(#arg_colon_types,)*) {
                    #pre_call
                }
                fn #post_name(&mut self, #(#arg_colon_types,)* ret: #return_type) {
                    #post_call
                }
            }
        });

    proc_macro::TokenStream::from(quote!{
        trait ProvLogger {
            #(#prov_logger_trait_fns)*
        }

        impl ProvLogger for StraceProvLogger {
            #(#strace_prov_logger_fns)*
        }

        impl ProvLogger for SemanticProvLogger {
            #(#semantic_prov_logger_fns)*
        }

        #(#hook_fns)*

        #cfunc_sigs_stmt
    })
}
