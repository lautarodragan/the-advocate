//! Where the suite's own files are: the directory the tools were built from.
//!
//! The runtime in assembly travels with the tools, and so do the scripts the
//! suite still runs; neither belongs to a game. A binary finds them through
//! the source tree it was compiled from, which cargo records at build time.
//! So an installed binary answers for **the checkout it was installed from**,
//! the same way a symlink to a script does: installing from a checkout that
//! is later deleted leaves it pointing nowhere, and it is installed again.

use std::path::{Path, PathBuf};

/// The directory that holds the tools: this crate's parent.
pub fn tools() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .expect("a crate lives inside a directory")
        .to_path_buf()
}

/// The directory above the tools. `ca65` and `ld65` run standing here, so
/// the source paths they write into a debug file are relative to it —a
/// debugger that looks for them climbing from the debug file finds them in
/// any clone of the tree—.
pub fn root() -> PathBuf {
    tools()
        .parent()
        .expect("the tools live inside a directory")
        .to_path_buf()
}

/// The runtime: the console-side engine, assembled together with each game's
/// generated data.
pub fn runtime() -> PathBuf {
    tools().join("runtime")
}
