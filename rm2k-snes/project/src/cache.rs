//! The key of the converter's disk cache.
//!
//! Almost nothing a conversion costs depends on what changes between one
//! build and the next, and what does change —the code— goes **into the
//! key**: each kind of value carries the hash of the sources it comes from,
//! so touching a module invalidates only its own part, without anyone having
//! to remember to delete anything.
//!
//! The values themselves are stored by whoever computes them. This is the
//! part every language that shares the cache has to agree on byte for byte:
//! [`key`] gives exactly what the converter's own `key` gives, so a value one
//! side wrote is found by the other.

use std::path::{Path, PathBuf};

use sha2::{Digest, Sha256};

use crate::environment::Environment;
use crate::{Error, Project};

/// Whether the cache is off for this run: `NO_CACHE=1`. It is what is used to
/// check that with and without the cache the same ROM comes out byte for
/// byte, which is the only honest verification of a cache.
pub fn disabled() -> bool {
    std::env::var_os("NO_CACHE").is_some_and(|v| v == "1")
}

/// The cache directory: `--cache`, or `cache/` in the project's build.
pub fn directory(environment: &Environment, project: &Project) -> Result<PathBuf, Error> {
    environment.cache(project)
}

/// A key from its parts, with each part's length in front so that two
/// different partitions of the same bytes do not give the same key.
pub fn key<P: AsRef<[u8]>>(parts: &[P]) -> String {
    let mut h = Sha256::new();
    for part in parts {
        let part = part.as_ref();
        h.update((part.len() as u64).to_le_bytes());
        h.update(part);
    }
    hex(&h.finalize())
}

/// The hash of the files a value comes from, to put into its key. Relative
/// paths are taken from `base`.
pub fn version_of<P: AsRef<Path>>(base: &Path, files: &[P]) -> Result<String, Error> {
    let mut h = Sha256::new();
    for name in files {
        let path = base.join(name);
        let bytes = std::fs::read(&path).map_err(|e| Error(format!("{}: {e}", path.display())))?;
        h.update(bytes);
    }
    Ok(hex(&h.finalize()))
}

/// Lower-case hexadecimal, the way the keys are written.
pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}
