use parking_lot::RwLock;
use quote::quote_spanned;
use std::fmt::Display;
use std::fs::File;
use std::io::Write;
use std::sync::OnceLock;
use syn::{spanned::Spanned, Data, Fields};

use crate::MacroResult;

fn pygen_file() -> &'static RwLock<PygenFile> {
    static INNER: OnceLock<RwLock<PygenFile>> = OnceLock::new();
    INNER.get_or_init(|| RwLock::new(PygenFile::new()))
}

pub fn pygen_dataclass_internal(input: syn::DeriveInput) -> MacroResult<()> {
    let syn::DeriveInput { data, ident, .. } = input.clone();

    match data {
        Data::Struct(data_struct) => {
            let fields = match data_struct.fields {
                Fields::Named(x) => x,
                _ => {
                    return Err(quote_spanned! {
                        input.span() =>
                        compile_error!("Unnamed and unit structs not implemented")
                    }
                    .into())
                }
            };

            let pairs = fields
                .named
                .iter()
                .filter_map(|field| {
                    if let syn::Type::Tuple(syn::TypeTuple { elems, .. }) = &field.ty {
                        // this is the unit type, so we just skip it
                        if elems.is_empty() {
                            return None;
                        }
                    }

                    let pair =
                        convert_to_pytype(&field.ty).and_then(|ty| match field.ident.as_ref() {
                            Some(ident) => Ok((ident.to_string(), ty)),
                            None => Err(quote_spanned! {
                                field.span() =>
                                compile_error!("Field doesn't have identifier");
                            }
                            .into()),
                        });

                    Some(pair)
                })
                .collect::<MacroResult<Vec<(_, _)>>>()?;

            let dataclass = basic_dataclass(ident.to_string(), &pairs);
            pygen_file().write().classes.push(dataclass);
        }
        Data::Enum(data_enum) => {
            let mut enu = Enum::new(ident.to_string());

            // this is the types that the produced union is over
            let mut variants = vec![];

            for variant in data_enum.variants {
                match variant.fields {
                    syn::Fields::Named(inner) => {
                        let name = variant.ident.to_string();

                        let pairs = inner
                            .named
                            .iter()
                            .filter_map(|field| {
                                // skip any field who's type is the unit type
                                if let syn::Type::Tuple(syn::TypeTuple { elems, .. }) = &field.ty {
                                    if elems.is_empty() {
                                        return None;
                                    }
                                }

                                let pair = convert_to_pytype(&field.ty).and_then(|ty| match field
                                    .ident
                                    .as_ref()
                                {
                                    Some(ident) => Ok((ident.to_string(), ty)),
                                    None => Err(quote_spanned! {
                                        field.span() =>
                                        compile_error!("Field doesn't have identifier");
                                    }
                                    .into()),
                                });

                                Some(pair)
                            })
                            .collect::<MacroResult<Vec<_>>>()?;

                        enu.add_variant_owned_class(basic_dataclass(name.clone(), &pairs));
                        variants.push(name);
                    }
                    syn::Fields::Unnamed(inner) => {
                        let fields = inner.unnamed.iter().collect::<Vec<_>>();
                        if fields.len() != 1 {
                            return Err(quote_spanned! {
                                inner.span() =>
                                compile_error!("Tuple enums of length != 1 not supported")
                            }
                            .into());
                        }
                        enu.add_variant_ref(convert_to_pytype(&fields[0].ty)?);
                    }
                    syn::Fields::Unit => {
                        return Err(quote_spanned! {
                            variant.fields.span() =>
                            compile_error!("Unit enum variants not supported")
                        }
                        .into())
                    }
                }
            }

            pygen_file().write().enums.push(enu);
        }
        Data::Union(_data_union) => {
            return Err(quote_spanned! {
                input.span() =>
                compile_error!("Unions not supported")
            }
            .into())
        }
    };

    Ok(())
}

fn basic_dataclass(name: String, pairs: &[(String, String)]) -> Dataclass {
    let mut dataclass = Dataclass::new(name);

    for (ident, ty) in pairs {
        dataclass.add_item(DataclassItem::new(ident.clone(), ty.clone()));
    }

    dataclass
}

fn convert_to_pytype(ty: &syn::Type) -> MacroResult<String> {
    match ty {
        syn::Type::Array(inner) => Ok(format!("list[{}]", convert_to_pytype(inner.elem.as_ref())?)),
        syn::Type::Path(inner) => {
            let name = crate::type_basename(inner)?.to_string();
            Ok(match name.as_str() {
                // that's a lot of ways to say "int", python ints are bigints so we don't have to
                // care about size
                "TaskType" | "__dev_t" | "__gid_t" | "__ino_t" | "__mode_t" | "__s32" | "__s64"
                | "__suseconds_t" | "__syscall_slong_t" | "__syseconds_t" | "__time_t"
                | "__u16" | "__u32" | "__u64" | "__uid_t" | "c_int" | "c_long" | "c_uint"
                | "c_ulong" | "dev_t" | "gid_t" | "i128" | "i16" | "i32" | "i64" | "i8"
                | "ino_t" | "isize" | "mode_t" | "pid_t" | "pthread_t" | "thrd_t" | "u128"
                | "u16" | "u32" | "u64" | "u8" | "uid_t" | "usize" => "int".to_owned(),

                // float, python uses doubles for everything
                "f32" | "f64" => "float".to_owned(),

                // CStrings are serialized as an array of bytes, so it makes sense to load them
                // into python as bytes
                "CString" => "bytes".to_owned(),

                // bool types are basically the same everywhere
                "bool" => name,

                _ => name,
            })
        }
        _ => Err(quote_spanned! {
            ty.span() =>
            compile_error!("Unsupported type type");
        }
        .into()),
    }
}

pub(crate) fn pygen_write_internal(path: syn::LitStr) -> MacroResult<()> {
    let path_str = path.value();
    let path_str = match std::env::var_os(path_str) {
        Some(x) => x,
        None => {
            return Err(quote_spanned! {
                path.span() =>
                compile_error!("Environmnet variable not defined");
            }
            .into())
        }
    };

    let mut file = match File::create(path_str) {
        Ok(x) => x,
        Err(e) => {
            eprintln!("pygen IO error: {}", e);
            return Err(quote_spanned! {
                path.span() =>
                compile_error!("Failed to create pygen file");
            }
            .into());
        }
    };

    pygen_file().write().prepend_preamble(
        [
            "from __future__ import annotations",
            "import typing",
            "from dataclasses import dataclass\n",
        ]
        .into_iter()
        .map(|x| x.to_owned())
        .collect(),
    );

    if let Err(e) = writeln!(file, "{}", pygen_file().read()) {
        eprintln!("pygen IO error: {}", e);
        return Err(quote_spanned! {
            path.span() =>
            compile_error!("Failed to write pygen file");
        }
        .into());
    }

    Ok(())
}

pub(crate) fn pygen_add_prop_internal(args: crate::AddPropArgs) -> MacroResult<()> {
    let class = args.class.to_string();
    let mut prop = DataclassProp::new(args.name.to_string(), args.ret.to_string());
    args.body.into_iter().for_each(|x| prop.body.push(x));

    let mut write_lock = pygen_file().write();

    let dataclass = match write_lock
        .classes
        .iter_mut()
        .find(|dataclass| dataclass.name == class)
    {
        Some(x) => x,
        None => {
            return Err(quote_spanned! {
                args.class.span() =>
                compile_error!("No such dataclass found");
            }
            .into())
        }
    };

    dataclass.add_prop(prop);

    Ok(())
}

pub(crate) fn pygen_add_preamble(args: crate::AddPreambleArgs) {
    pygen_file().write().append_preamble(args.0)
}

#[derive(Debug, Clone)]
struct PygenFile {
    preamble: Vec<String>,
    pub classes: Vec<Dataclass>,
    pub enums: Vec<Enum>,
}

#[derive(Debug, Clone)]
struct Enum {
    indent: usize,
    pub name: String,
    variants_owned_class: Vec<Dataclass>,
    variants_owned_enum: Vec<Enum>,
    variants_ref: Vec<String>,
}

#[derive(Debug, Clone)]
struct Dataclass {
    indent: usize,
    pub name: String,
    inclasses: Vec<Dataclass>,
    items: Vec<DataclassItem>,
    properties: Vec<DataclassProp>,
}

#[derive(Debug, Clone)]
struct DataclassItem {
    indent: usize,
    name: String,
    ty: String,
}

#[derive(Debug, Clone)]
struct DataclassProp {
    indent: usize,
    name: String,
    ret: String,
    pub body: Vec<String>,
}

#[allow(dead_code)]
impl PygenFile {
    pub fn new() -> Self {
        Self {
            preamble: vec![],
            classes: vec![],
            enums: vec![],
        }
    }

    pub fn prepend_preamble(&mut self, mut lines: Vec<String>) {
        lines.extend(std::mem::take(&mut self.preamble));
        self.preamble = lines;
    }

    pub fn append_preamble(&mut self, lines: Vec<String>) {
        self.preamble.extend(lines);
    }
}

#[allow(dead_code)]
impl Enum {
    pub fn new(name: String) -> Self {
        Self {
            indent: 0,
            name,
            variants_owned_class: vec![],
            variants_owned_enum: vec![],
            variants_ref: vec![],
        }
    }

    pub fn add_variant_owned_class(&mut self, mut item: Dataclass) {
        item.set_indent(self.indent);
        self.variants_owned_class.push(item);
    }

    pub fn add_variant_owned_enum(&mut self, mut item: Enum) {
        item.set_indent(self.indent);
        self.variants_owned_enum.push(item);
    }

    pub fn add_variant_ref(&mut self, item: String) {
        self.variants_ref.push(item);
    }

    pub fn set_indent(&mut self, indent: usize) {
        for class in &mut self.variants_owned_class {
            class.set_indent(indent);
        }
        for enu in &mut self.variants_owned_enum {
            enu.set_indent(indent);
        }

        self.indent = indent;
    }
}

#[allow(dead_code)]
impl Dataclass {
    pub fn new(name: String) -> Self {
        Self {
            indent: 0,
            name,
            inclasses: vec![],
            items: vec![],
            properties: vec![],
        }
    }

    pub fn add_inclass(&mut self, mut inclass: Dataclass) {
        inclass.set_indent(self.indent + 4);
        self.inclasses.push(inclass)
    }

    pub fn add_item(&mut self, mut item: DataclassItem) {
        item.set_indent(self.indent + 4);
        self.items.push(item)
    }

    pub fn add_prop(&mut self, mut prop: DataclassProp) {
        prop.set_indent(self.indent + 4);
        self.properties.push(prop)
    }

    pub fn set_indent(&mut self, indent: usize) {
        for inclass in &mut self.inclasses {
            inclass.set_indent(indent + 4);
        }
        for item in &mut self.items {
            item.set_indent(indent + 4);
        }

        self.indent = indent;
    }
}

impl DataclassItem {
    pub fn new(name: String, ty: String) -> Self {
        Self {
            indent: 0,
            name,
            ty,
        }
    }

    pub fn set_indent(&mut self, indent: usize) {
        self.indent = indent;
    }
}

impl DataclassProp {
    pub fn new(name: String, ret: String) -> Self {
        Self {
            indent: 0,
            name,
            ret,
            body: vec![],
        }
    }

    pub fn set_indent(&mut self, indent: usize) {
        self.indent = indent;
    }
}

// Display trait implementations for actual codegen

impl Display for PygenFile {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        writeln!(f, "# This file was @generated by probe_macros")?;

        for line in self.preamble.iter() {
            writeln!(f, "{line}")?;
        }
        writeln!(f)?;

        for class in self.classes.iter() {
            writeln!(f, "{class}")?;
        }

        for enu in self.enums.iter() {
            writeln!(f, "{enu}")?;
        }

        Ok(())
    }
}

impl Display for Enum {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        fn print_union_type(types: &[&str], f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
            if types.is_empty() {
                write!(f, "None")?;
                return Ok(());
            }
            let mut iter = types.iter();

            // unwrap allowed because we checked that types isn't empty
            let first = iter.next().unwrap();
            write!(f, "{first}")?;

            for ty in iter {
                write!(f, " | {ty}")?;
            }

            Ok(())
        }

        let name = &self.name;
        let mut acc = Vec::new();

        for owned_variant in self.variants_owned_class.iter() {
            writeln!(f, "{owned_variant}")?;
            acc.push(owned_variant.name.as_str());
        }

        for owned_variant in self.variants_owned_enum.iter() {
            writeln!(f, "{owned_variant}")?;
            acc.push(owned_variant.name.as_str());
        }

        self.variants_ref.iter().for_each(|x| acc.push(x));

        let indent_str = " ".repeat(self.indent);
        write!(f, "{indent_str}{name}: typing.TypeAlias = ")?;
        print_union_type(acc.as_slice(), f)
    }
}

impl Display for Dataclass {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let name = self.name.as_str();
        let indent_str = " ".repeat(self.indent);

        writeln!(
            f,
            "{indent_str}@dataclass(init=True, frozen=True)\n\
            {indent_str}class {name}:"
        )?;

        for inclass in &self.inclasses {
            writeln!(f, "{inclass}",)?;
        }

        for item in &self.items {
            writeln!(f, "{item}")?;
        }
        writeln!(f)?;

        for prop in &self.properties {
            writeln!(f, "{prop}")?;
        }

        Ok(())
    }
}

impl Display for DataclassItem {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let &Self { name, ty, .. } = &self;
        let indent_str = " ".repeat(self.indent);
        write!(f, "{indent_str}{name}: {ty}")
    }
}

impl Display for DataclassProp {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let &Self { name, ret, .. } = &self;
        let indent_str = " ".repeat(self.indent);

        writeln!(
            f,
            "{indent_str}@property\n\
            {indent_str}def {name}(self) -> {ret}:",
        )?;

        for line in &self.body {
            writeln!(f, "{indent_str}    {line}")?;
        }

        Ok(())
    }
}
