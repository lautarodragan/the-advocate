//! The key of the converter's disk cache.
//!
//! Almost nothing a conversion costs depends on what changes between one
//! build and the next, and what does change —the code— goes **into the
//! key**: each kind of value carries the hash of the sources it comes from,
//! so touching a module invalidates only its own part, without anyone having
//! to remember to delete anything.
//!
//! The values themselves are computed by whoever needs them, and kept with
//! [`store`] and [`store_file`] and read back with [`load`] and
//! [`fetch_file`]: one file per value, `<category>/<key>`.
//!
//! **The cache can be shared**: the machine can point `--cache` of every
//! checkout at the same directory, so a worktree finds what another one
//! already built. That is why a value is **written aside and renamed** into
//! place —two processes, or two threads of one, may compute the same key at
//! once, and a reader must find the whole value or nothing—, and why a key
//! carries contents and not a checkout's paths. And **nothing in it is
//! written in place**: a file is replaced whole, by a rename, so one that
//! was linked out of the cache into a build stays what it was.

use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};

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

/// Where the value of `key` lives: `<directory>/<category>/<key>`.
pub fn entry(directory: &Path, category: &str, key: &str) -> PathBuf {
    directory.join(category).join(key)
}

/// The value stored under `key`, or None if there is none.
pub fn load(directory: &Path, category: &str, key: &str) -> Option<Vec<u8>> {
    std::fs::read(entry(directory, category, key)).ok()
}

/// A name next to `target`, of this process and this call alone: two
/// threads of one process store the same key at once —the converter runs
/// its stages in threads, and two maps may ask for the same thing—, so the
/// process id is not enough.
fn aside(target: &Path) -> PathBuf {
    static COUNT: AtomicUsize = AtomicUsize::new(0);
    let n = COUNT.fetch_add(1, Ordering::Relaxed);
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(0);
    let name = target
        .file_name()
        .map(|n| n.to_string_lossy().into_owned())
        .unwrap_or_default();
    target.with_file_name(format!(".tmp-{}-{n}-{nanos:x}-{name}", std::process::id()))
}

/// Puts the file `fill` writes at `target`, whole or not at all.
fn into_place(target: &Path, fill: impl FnOnce(&Path) -> std::io::Result<()>) -> bool {
    if let Some(parent) = target.parent() {
        if std::fs::create_dir_all(parent).is_err() {
            return false;
        }
    }
    let tmp = aside(target);
    let done = fill(&tmp).and_then(|()| std::fs::rename(&tmp, target));
    if done.is_err() {
        let _ = std::fs::remove_file(&tmp);
    }
    done.is_ok()
}

/// Stores `value` under `key`, whole or not at all. Says whether it did: a
/// cache that cannot be written breaks nothing, so whoever calls this
/// usually ignores it.
pub fn store(directory: &Path, category: &str, key: &str, value: &[u8]) -> bool {
    into_place(&entry(directory, category, key), |tmp| {
        std::fs::write(tmp, value)
    })
}

/// Stores the file `from` under `key`: a hard link to it if the cache is on
/// the same disk —a track weighs tens of megabytes, and the build keeps its
/// copy anyway—, a copy otherwise.
pub fn store_file(directory: &Path, category: &str, key: &str, from: &Path) -> bool {
    into_place(&entry(directory, category, key), |tmp| link_or_copy(from, tmp))
}

/// Puts the file stored under `key` at `to`, replacing what was there, the
/// same way: a hard link or a copy, renamed into place. Says whether there
/// was one to put.
pub fn fetch_file(directory: &Path, category: &str, key: &str, to: &Path) -> bool {
    let from = entry(directory, category, key);
    from.is_file() && into_place(to, |tmp| link_or_copy(&from, tmp))
}

fn link_or_copy(from: &Path, to: &Path) -> std::io::Result<()> {
    std::fs::hard_link(from, to).or_else(|_| std::fs::copy(from, to).map(|_| ()))
}

/// The hash of everything below `directory`, at any depth: each file's path
/// relative to it and its content, in order, following links. Hidden files
/// count, since whoever reads the directory may read them. It is what goes
/// into a key in place of a directory's path, so that two checkouts with
/// the same content give the same key.
pub fn tree_version(directory: &Path) -> Result<String, Error> {
    let fail = |e: std::io::Error, p: &Path| Error(format!("{}: {e}", p.display()));
    let mut files = Vec::new();
    let mut pending = vec![directory.to_path_buf()];
    while let Some(dir) = pending.pop() {
        for item in std::fs::read_dir(&dir).map_err(|e| fail(e, &dir))? {
            let path = item.map_err(|e| fail(e, &dir))?.path();
            if path.is_dir() {
                pending.push(path);
            } else if path.is_file() {
                files.push(path);
            }
        }
    }
    files.sort();
    let mut h = Sha256::new();
    for path in files {
        let name = path.strip_prefix(directory).unwrap_or(&path);
        let name = name.as_os_str().as_encoded_bytes();
        h.update((name.len() as u64).to_le_bytes());
        h.update(name);
        let bytes = std::fs::read(&path).map_err(|e| fail(e, &path))?;
        h.update((bytes.len() as u64).to_le_bytes());
        h.update(&bytes);
    }
    Ok(hex(&h.finalize()))
}
