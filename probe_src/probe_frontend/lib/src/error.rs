use std::num::ParseIntError;

pub type Result<T> = std::result::Result<T, ProbeError>;

#[non_exhaustive]
#[derive(Debug, thiserror::Error)]
pub enum ProbeError {
    #[error("{msg}: {inner}")]
    FFiConversionError {
        msg: &'static str,
        inner: Box<ProbeError>,
    },

    #[error("Invalid variant of tagged union")]
    InvalidVariant(u32),

    #[error("Unable to decode pointer {0:#x}")]
    InvalidPointer(usize),

    #[error("Expected null byte but none found")]
    MissingNull,

    #[error("Reached code believed unreachable, please report this bug")]
    UnreachableCode,

    #[error("(de)serialization error ({context}):\n{error}")]
    JsonError {
        context: &'static str,
        error: serde_json::Error,
    },

    #[error("{context}:\n{error}")]
    Context {
        context: &'static str,
        error: Box<ProbeError>,
    },

    #[error("{context}:\n{error}")]
    ContextIO {
        context: &'static str,
        error: std::io::Error,
    },

    #[error("{context}:\nNeeded Option was None")]
    MissingOption { context: &'static str },

    #[error("{0}")]
    ArenaError(crate::transcribe::ArenaError),

    #[error("{0}")]
    ParseIntError(ParseIntError),
}

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
pub fn option_err(context: &'static str) -> ProbeError {
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
        ProbeError::ContextIO {
            context,
            error: self,
        }
    }
}

impl ConvertErr for ProbeError {
    fn convert(self, context: &'static str) -> ProbeError {
        ProbeError::Context {
            context,
            error: Box::new(self),
        }
    }
}

impl ConvertErr for serde_json::Error {
    fn convert(self, context: &'static str) -> ProbeError {
        ProbeError::JsonError {
            context,
            error: self,
        }
    }
}
