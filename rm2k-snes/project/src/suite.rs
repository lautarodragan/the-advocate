//! Where the suite's own files are: the directory the tools were built from.
//!
//! The runtime in assembly travels with the tools, and does not belong to a
//! game. A binary finds it through
//! the source tree it was compiled from, which cargo records at build time.
//! So an installed binary answers for **the checkout it was installed from**,
//! the same way a symlink to a script does: installing from a checkout that
//! is later deleted leaves it pointing nowhere, and it is installed again.

use std::path::{Path, PathBuf};

/// The directory that holds the tools: two above this crate, which lives in
/// its layer's directory, `rm2k-snes/`. Since 2026-10-10 it is the root of
/// the repository; until then the tools lived in its `tools/` folder.
///
/// **Moving the checkout does not move this.** The path is
/// `CARGO_MANIFEST_DIR`, and cargo keeps the compiled crate while its
/// fingerprint holds —and a fingerprint is relative to the workspace, so
/// moving the whole workspace keeps it—: after moving it, touch this file
/// before installing again, or the binaries keep answering the old path.
pub fn tools() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("a crate lives inside its layer's directory, inside the tools")
        .to_path_buf()
}

/// Where `ca65` and `ld65` run, so the source paths they write into a debug
/// file are relative to it —a debugger that looks for them climbing from
/// the debug file finds them in any clone of the tree—. It is the same
/// directory as [`tools`]: it was the one above it while the tools lived in
/// a `tools/` folder, and the paths in the debug file said `tools/runtime/`.
pub fn root() -> PathBuf {
    tools()
}

/// The runtime: the console-side engine, assembled together with each game's
/// generated data.
pub fn runtime() -> PathBuf {
    tools().join("runtime")
}

#[cfg(test)]
mod tests {
    use super::*;

    // `tools()` counts directories up from this crate, so moving the crate
    // one level deeper or shallower breaks it without a compile error: this
    // is what notices.
    #[test]
    fn the_tools_are_where_the_runtime_is() {
        assert!(runtime().join("main.s").is_file(), "{}", runtime().display());
        assert!(tools().join("Cargo.toml").is_file(), "{}", tools().display());
    }
}
