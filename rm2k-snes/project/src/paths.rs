//! Paths the way the callers spell them.
//!
//! Lexical on purpose, like Python's `os.path.abspath` and `relpath`, which
//! the rest of the suite still uses: a symlink is not resolved, so a path
//! that went in through one comes out through the same one. What ends up
//! written —inside a debug file, in a stamp, in a flag passed to another
//! tool— has to be the same whichever side computed it.

use std::path::{Component, Path, PathBuf};

/// `path` made absolute against the current directory, with `.` and `..`
/// folded away without touching the disk.
pub fn absolute(path: impl AsRef<Path>) -> PathBuf {
    let path = path.as_ref();
    let joined = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("/"))
            .join(path)
    };
    normalize(&joined)
}

fn normalize(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                // At the root, `..` is the root: `/..` is `/`.
                if out.parent().is_some() {
                    out.pop();
                }
            }
            other => out.push(other.as_os_str()),
        }
    }
    out
}

/// `path` relative to `base`, both made absolute first. It climbs with `..`
/// when it has to, like `os.path.relpath`.
pub fn relative(path: impl AsRef<Path>, base: impl AsRef<Path>) -> PathBuf {
    let path = absolute(path);
    let base = absolute(base);
    let ours: Vec<_> = path.components().collect();
    let theirs: Vec<_> = base.components().collect();
    let shared = ours
        .iter()
        .zip(&theirs)
        .take_while(|(a, b)| a == b)
        .count();
    let mut out = PathBuf::new();
    for _ in shared..theirs.len() {
        out.push("..");
    }
    for c in &ours[shared..] {
        out.push(c.as_os_str());
    }
    if out.as_os_str().is_empty() {
        out.push(".");
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn dots_fold_away() {
        assert_eq!(absolute("/a/b/../c/./d"), PathBuf::from("/a/c/d"));
        assert_eq!(absolute("/.."), PathBuf::from("/"));
    }

    #[test]
    fn relative_climbs_when_it_has_to() {
        assert_eq!(relative("/a/b/c", "/a"), PathBuf::from("b/c"));
        assert_eq!(relative("/a/x", "/a/b/c"), PathBuf::from("../../x"));
        assert_eq!(relative("/a", "/a"), PathBuf::from("."));
    }
}
