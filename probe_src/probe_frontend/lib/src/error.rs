use std::num::ParseIntError;

pub type Result<T> = std::result::Result<T, ProbeError>;

#[non_exhaustive]
#[derive(Debug, thiserror::Error)]
pub enum ProbeError {
<<<<<<< HEAD
    /// wrapper explaining where an occurred converting a [`C_` struct](crate::ops) to its rust
    /// version, call [`root_cause()`](Self::root_cause()) to return the underlying error.
=======
>>>>>>> a83cce7 (version 0.2.0)
    #[error("{msg}: {inner}")]
    FFiConversionError {
        msg: &'static str,
        inner: Box<ProbeError>,
    },

<<<<<<< HEAD
    /// The tag of a tagged union type from an [`C_` struct](crate::ops) isn't a valid variant of
    /// that union
    #[error("Invalid variant of tagged union")]
    InvalidVariant(u32),

    /// A pointer from an [`C_` struct](crate::ops) couldn't be decoded into a byte slice.
    #[error("Unable to decode pointer {0:#x}")]
    InvalidPointer(usize),

    /// Unable to generate a [`CString`](std::ffi::CString) from a byte slice because it had no null byte.
    #[error("Expected null byte but none found")]
    MissingNull,

    /// Used instead of [`unreachable`] so that functions up the call stack can add
    /// [context](Self::Context).
    #[error("Reached code believed unreachable, please report this bug")]
    UnreachableCode,

    /// An error occurred serializing or deserializing a struct into/from json.
=======
    #[error("Invalid variant of tagged union")]
    InvalidVariant(u32),

    #[error("Unable to decode pointer {0:#x}")]
    InvalidPointer(usize),

    #[error("Expected null byte but none found")]
    MissingNull,

    #[error("Reached code believed unreachable, please report this bug")]
    UnreachableCode,

>>>>>>> a83cce7 (version 0.2.0)
    #[error("(de)serialization error ({context}):\n{error}")]
    JsonError {
        context: &'static str,
        error: serde_json::Error,
    },

<<<<<<< HEAD
    /// A generic wrapper around another [`ProbeError`] type that adds additional context, call
    /// [`root_cause()`](Self::root_cause()) to return the underlying error.
=======
>>>>>>> a83cce7 (version 0.2.0)
    #[error("{context}:\n{error}")]
    Context {
        context: &'static str,
        error: Box<ProbeError>,
    },

<<<<<<< HEAD
    /// A wrapper over a [`std::io::Error`] with a description of what the was being done when an
    /// IO error occurred
=======
>>>>>>> a83cce7 (version 0.2.0)
    #[error("{context}:\n{error}")]
    ContextIO {
        context: &'static str,
        error: std::io::Error,
    },

<<<<<<< HEAD
    /// An external function returned [`None`] when [`Some`] was required, contains explanation.
    // FIXME: this is an unhelpful error
    #[error("{context}:\nNeeded Option was None")]
    MissingOption { context: &'static str },

    /// A wrapper over [`ArenaError`](crate::transcribe::ArenaError), see that type for variant
    /// details.
    #[error("{0}")]
    ArenaError(crate::transcribe::ArenaError),

    /// An error occured trying to parse a string into an integer, this error is generally wrapped
    /// in [context](Self::Context).
=======
    #[error("{context}:\nNeeded Option was None")]
    MissingOption {
        context: &'static str,
    },

    #[error("{0}")]
    ArenaError(crate::transcribe::ArenaError),

>>>>>>> a83cce7 (version 0.2.0)
    #[error("{0}")]
    ParseIntError(ParseIntError),
}

<<<<<<< HEAD
impl ProbeError {
    /// Walks down the inner value(s) of one or more layers of [`Context`](Self::Context) or
    /// [`FfiConversionError`](Self::FFiConversionError) and returns a reference to the underlying
    /// error type, returns `&self` for other variants.
    pub fn root_cause(&self) -> &ProbeError {
        match self {
            Self::Context { error, .. } => error.as_ref().root_cause(),
            Self::FFiConversionError { inner, .. } => inner.as_ref().root_cause(),
            _ => self,
        }
    }
}

=======
>>>>>>> a83cce7 (version 0.2.0)
impl From<crate::transcribe::ArenaError> for ProbeError {
    fn from(value: crate::transcribe::ArenaError) -> Self {
        Self::ArenaError(value)
    }
}

impl From<ParseIntError> for ProbeError {
    fn from(value: ParseIntError) -> Self {
        Self::ParseIntError(value)
    }
}

/// create new [`ProbeError::MissingOption`] with the given context
<<<<<<< HEAD
pub(crate) fn option_err(context: &'static str) -> ProbeError {
=======
pub fn option_err(context: &'static str) -> ProbeError {
>>>>>>> a83cce7 (version 0.2.0)
    ProbeError::MissingOption { context }
}

pub(crate) trait WrapErr<T, E> {
    fn wrap_err(self, context: &'static str) -> Result<T>;
}

impl<T, E: ConvertErr> WrapErr<T, E> for std::result::Result<T, E> {
    fn wrap_err(self, context: &'static str) -> Result<T> {
        match self {
            Ok(x) => Ok(x),
            Err(e) => Err(e.convert(context)),
        }
    }
}

pub(crate) trait ConvertErr {
    fn convert(self, context: &'static str) -> ProbeError;
}

impl ConvertErr for std::io::Error {
    fn convert(self, context: &'static str) -> ProbeError {
<<<<<<< HEAD
        ProbeError::ContextIO {
            context,
            error: self,
        }
=======
        ProbeError::ContextIO { context, error: self }
>>>>>>> a83cce7 (version 0.2.0)
    }
}

impl ConvertErr for ProbeError {
    fn convert(self, context: &'static str) -> ProbeError {
<<<<<<< HEAD
        ProbeError::Context {
            context,
            error: Box::new(self),
        }
=======
        ProbeError::Context { context, error: Box::new(self) }
>>>>>>> a83cce7 (version 0.2.0)
    }
}

impl ConvertErr for serde_json::Error {
    fn convert(self, context: &'static str) -> ProbeError {
<<<<<<< HEAD
        ProbeError::JsonError {
            context,
            error: self,
        }
    }
}
=======
        ProbeError::JsonError { context, error: self }
    }
}

>>>>>>> a83cce7 (version 0.2.0)
