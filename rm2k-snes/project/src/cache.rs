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
//!
//! **And it forgets what nobody used in four days**: see
//! [`evict_and_hold`], which `advocate build` calls before it touches the
//! cache. Every key carries the binaries and sources that made its value,
//! so each new converter leaves the whole previous set of answers behind,
//! and nothing else would ever delete it.

use std::fs::{File, FileTimes};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::sync::Mutex;
use std::time::{Duration, SystemTime};

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
    hold(directory);
    let path = entry(directory, category, key);
    let bytes = std::fs::read(&path).ok()?;
    stamp(&path);
    Some(bytes)
}

/// Says that the value under `key` is still used, without reading it: for
/// whoever finds its copy of a stored file already in place —a build whose
/// MSU-1 track is still the one the cache keeps— and must not let the
/// cache's copy be evicted because of that.
pub fn touch(directory: &Path, category: &str, key: &str) {
    hold(directory);
    stamp(&entry(directory, category, key));
}

/// A name next to `target`, of this process and this call alone, to write
/// there and rename over `target`: two threads of one process write the
/// same thing at once —the converter runs its stages in threads, and two
/// maps may ask for the same thing; the builder converts every cartridge
/// in threads of one process—, so the process id is not enough.
pub fn aside(target: &Path) -> PathBuf {
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
    hold(directory);
    into_place(&entry(directory, category, key), |tmp| {
        std::fs::write(tmp, value)
    })
}

/// Stores the file `from` under `key`: a hard link to it if the cache is on
/// the same disk —a track weighs tens of megabytes, and the build keeps its
/// copy anyway—, a copy otherwise.
pub fn store_file(directory: &Path, category: &str, key: &str, from: &Path) -> bool {
    hold(directory);
    let target = entry(directory, category, key);
    // A hard link shares the times of the build's file, whose last read
    // may be long ago.
    let stored = into_place(&target, |tmp| link_or_copy(from, tmp));
    if stored {
        stamp(&target);
    }
    stored
}

/// Puts the file stored under `key` at `to`, replacing what was there, the
/// same way: a hard link or a copy, renamed into place. Says whether there
/// was one to put.
pub fn fetch_file(directory: &Path, category: &str, key: &str, to: &Path) -> bool {
    hold(directory);
    let from = entry(directory, category, key);
    // A hard link reads nothing, so nothing else would mark it as used.
    let fetched = from.is_file() && into_place(to, |tmp| link_or_copy(&from, tmp));
    if fetched {
        stamp(&from);
    }
    fetched
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

/// How long an entry nobody used stays: four days, taro's (2026-11-28),
/// after the cache was measured growing some 18 GB a day —each new
/// converter leaves a gigabyte behind— and four days would have settled it
/// at a couple of hundred. A worktree older than that rebuilds what it
/// needs in the minutes of a cold build.
pub const UNUSED_FOR: Duration = Duration::from_secs(4 * 24 * 60 * 60);

/// How often a build sweeps: once a day is plenty against four days, and
/// a sweep stats every entry —some hundred and seventy thousand on
/// 2026-11-28, most of them stage answers—.
pub const SWEEP_EVERY: Duration = Duration::from_secs(24 * 60 * 60);

/// How old a stamp gets before a use writes it again: a day, so that
/// reading the same entry a thousand times in a build writes it once.
const STAMP_EVERY: Duration = Duration::from_secs(24 * 60 * 60);

/// The file the processes lock: shared while one uses the cache,
/// exclusive while one sweeps. See [`hold`].
const LOCK: &str = ".lock";

/// The file whose modification time says when the last sweep was.
const SWEPT: &str = ".swept";

/// **Marks `path` —an entry, a file or a directory— as used now**, by its
/// access time written by hand: the kernel's is not to be trusted
/// —`relatime` writes it once a day at most, `noatime` never, and a value
/// fetched as a hard link is not even read—, but one written with
/// `futimens` stays whatever the mount says. **Not the modification
/// time**: the MSU-1 tracks are hard links shared with the builds' `.pcm`,
/// whose modification time is the build's, and whoever copies a build may
/// compare by it. Written only once the stamp is a day old, so that a read
/// is not a write. A stamp that cannot be written breaks nothing but the
/// sweep's guess, so it is not reported.
pub fn stamp(path: &Path) {
    stamp_at(path, SystemTime::now());
}

fn stamp_at(path: &Path, now: SystemTime) {
    let Ok(file) = File::open(path) else {
        return;
    };
    let fresh = file
        .metadata()
        .and_then(|m| m.accessed())
        .is_ok_and(|at| at > now || now.duration_since(at).is_ok_and(|age| age < STAMP_EVERY));
    if !fresh {
        let _ = file.set_times(FileTimes::new().set_accessed(now));
    }
}

/// When an entry was last used: its [`stamp`].
fn used(meta: &std::fs::Metadata) -> SystemTime {
    meta.accessed()
        .or_else(|_| meta.modified())
        .unwrap_or(SystemTime::UNIX_EPOCH)
}

/// The lock files this process holds, one per cache directory, kept open
/// —and so locked— until it exits.
static HELD: Mutex<Vec<(PathBuf, File)>> = Mutex::new(Vec::new());

/// The name a directory is held under: the same directory however it is
/// spelled.
fn held_name(directory: &Path) -> PathBuf {
    std::fs::canonicalize(directory).unwrap_or_else(|_| crate::absolute(directory))
}

/// The lock file of `directory`, made if it is not there.
fn lock_file(directory: &Path) -> Option<File> {
    std::fs::create_dir_all(directory).ok()?;
    std::fs::OpenOptions::new()
        .read(true)
        .write(true)
        .create(true)
        .truncate(false)
        .open(directory.join(LOCK))
        .ok()
}

/// **Holds the cache at `directory` for the rest of the process**: a
/// shared lock on its `.lock`, which every reader and writer takes and
/// which [`evict_and_hold`] needs exclusive. So nothing is evicted while
/// a process that may read it lives —a build, a stage a test runs, a tool
/// reading the game unpacked in `zip/`—. Coarser than locking each entry,
/// and nobody has to remember to unlock: the lock goes with the process,
/// however it dies. Every function here that touches an entry calls it,
/// and so does `Environment::unpack`, for the game and the RTP that live
/// in the cache. It waits while another process sweeps. A cache that
/// cannot be locked is used unlocked: like one that cannot be written, it
/// breaks nothing but itself.
pub fn hold(directory: &Path) {
    let name = held_name(directory);
    let mut held = HELD.lock().unwrap_or_else(|e| e.into_inner());
    if held.iter().any(|(d, _)| *d == name) {
        return;
    }
    if let Some(file) = lock_file(directory) {
        if file.lock_shared().is_ok() {
            held.push((name, file));
        }
    }
}

/// What [`evict_and_hold`] did.
#[derive(Debug, PartialEq, Eq)]
pub enum Eviction {
    /// It swept, and this went.
    Swept(Swept),
    /// The last sweep was less than [`SWEEP_EVERY`] ago.
    NotDue,
    /// Another process holds the cache. It does not wait: the next build
    /// will sweep.
    Busy,
    /// This process already held it, so it cannot lock it exclusively.
    AlreadyHeld,
    /// The cache could not be locked at all.
    Unlockable,
}

/// What a sweep took, or would take: the entries, and the bytes of their
/// files that have no other name —a hard link a build still keeps frees
/// nothing—.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct Swept {
    pub entries: usize,
    pub bytes: u64,
}

/// **Deletes the entries nobody used in [`UNUSED_FOR`], and then holds the
/// cache** like [`hold`]. It sweeps only if no other process holds the
/// cache —it tries the exclusive lock and does not wait for it: a build is
/// not held up by another's tests— and if the last sweep was
/// [`SWEEP_EVERY`] or more before `now`; whatever it answers, the cache is
/// held after. It has to come before anything in this process touches the
/// cache, or its own shared lock is in the way. `now` is the clock, so
/// that a test can be four days ahead.
pub fn evict_and_hold(directory: &Path, now: SystemTime) -> Eviction {
    let name = held_name(directory);
    let mut held = HELD.lock().unwrap_or_else(|e| e.into_inner());
    if held.iter().any(|(d, _)| *d == name) {
        return Eviction::AlreadyHeld;
    }
    let Some(file) = lock_file(directory) else {
        return Eviction::Unlockable;
    };
    let answer = match file.try_lock() {
        Err(std::fs::TryLockError::WouldBlock) => Eviction::Busy,
        Err(std::fs::TryLockError::Error(_)) => Eviction::Unlockable,
        Ok(()) => {
            let swept = directory.join(SWEPT);
            let last = std::fs::metadata(&swept).and_then(|m| m.modified()).ok();
            let due = last
                .is_none_or(|last| now.duration_since(last).is_ok_and(|age| age >= SWEEP_EVERY));
            if due {
                let cutoff = now
                    .checked_sub(UNUSED_FOR)
                    .unwrap_or(SystemTime::UNIX_EPOCH);
                let gone = sweep(directory, cutoff, true);
                if let Ok(f) = File::create(&swept) {
                    let _ = f.set_times(FileTimes::new().set_modified(now).set_accessed(now));
                }
                Eviction::Swept(gone)
            } else {
                Eviction::NotDue
            }
        }
    };
    // Exclusive to shared, or nothing to shared. `flock` does not convert
    // atomically: another process may sweep in between, which is the same
    // as having swept here, since nothing was read yet.
    if file.lock_shared().is_ok() {
        held.push((name, file));
    }
    answer
}

/// **The entries of `directory` last used before `cutoff`**: each child of
/// each category —a file, or a directory like a game unpacked in `zip/`—,
/// by its [`stamp`]; and every value left half written by a process that
/// died, which nobody can be writing while the sweep holds the cache. It
/// deletes them if `delete`, which only whoever holds the cache
/// exclusively may ask for; without it, it only counts, which anyone may.
/// The files at the top —the lock, the date of the last sweep— are not
/// entries.
pub fn sweep(directory: &Path, cutoff: SystemTime, delete: bool) -> Swept {
    let mut swept = Swept::default();
    let Ok(categories) = std::fs::read_dir(directory) else {
        return swept;
    };
    for category in categories.flatten() {
        if !category.file_type().is_ok_and(|t| t.is_dir()) {
            continue;
        }
        let Ok(entries) = std::fs::read_dir(category.path()) else {
            continue;
        };
        for item in entries.flatten() {
            let path = item.path();
            let Ok(meta) = std::fs::symlink_metadata(&path) else {
                continue;
            };
            let half_written = item.file_name().to_string_lossy().starts_with(".tmp-");
            if !half_written && used(&meta) >= cutoff {
                continue;
            }
            let bytes = alone(&path, &meta);
            let gone = if !delete {
                // Counting read the directory, and `relatime` may have
                // stamped it for that: it was not a use.
                if meta.is_dir() {
                    if let Ok(dir) = File::open(&path) {
                        let _ = dir.set_times(FileTimes::new().set_accessed(used(&meta)));
                    }
                }
                true
            } else if meta.is_dir() {
                std::fs::remove_dir_all(&path).is_ok()
            } else {
                std::fs::remove_file(&path).is_ok()
            };
            if gone {
                swept.entries += 1;
                swept.bytes += bytes;
            }
        }
    }
    swept
}

/// The bytes deleting `path` frees: those of its files that have no other
/// name, at any depth, not following links.
fn alone(path: &Path, meta: &std::fs::Metadata) -> u64 {
    #[cfg(unix)]
    let other_names = {
        use std::os::unix::fs::MetadataExt;
        meta.nlink() > 1
    };
    #[cfg(not(unix))]
    let other_names = false;
    if meta.is_dir() {
        std::fs::read_dir(path)
            .map(|items| {
                items
                    .flatten()
                    .filter_map(|i| {
                        let p = i.path();
                        std::fs::symlink_metadata(&p).ok().map(|m| alone(&p, &m))
                    })
                    .sum()
            })
            .unwrap_or(0)
    } else if meta.is_file() && !other_names {
        meta.len()
    } else {
        0
    }
}
