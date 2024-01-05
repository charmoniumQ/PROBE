pub type CFuncSigs = std::collections::HashMap<&'static str, CFuncSig>;

pub struct CFuncSig {
    pub return_type: CType,
    pub name: &'static str,
    pub arg_types: &'static [ArgType],
}

pub struct ArgType {
    pub arg: &'static str,
    pub ty: CType,
}

pub enum CType {
    PtrMut(CPrimType),
    PtrConst(CPrimType),
    PrimType(CPrimType),
}

pub enum CPrimType {
    Int,
    Uint,
    Char,
    File,
    ModeT,
    Void,
    Dir,
    SizeT,
    SsizeT,
    FtwFuncT,
    Ftw64FuncT,
    NftwFuncT,
    Nftw64FuncT,
}
