//! Calling a stage of the conversion: a function of its crate.
//!
//! Each domain reads the game from the dump itself, gets what the cartridge
//! decided in a JSON request, and answers what it made —pieces of the `.inc`
//! and a JSON with what the rest of the conversion needs—, as files by name.
//! What goes in the request and where each piece goes is the converter's
//! business, not this module's. See "One stage of a converter" in
//! `rm2k-snes-battle`'s README for the shape.
//!
//! **The stages are functions the converter calls**, through [`call`]: each
//! answers [`Files`], what its binary writes into `--out`.
//!
//! **What a stage answers is kept in the disk cache**, under the key of
//! everything it can depend on: see [`key`]. A stage is a function of the
//! code that answers, its command, its request and what its flags point at,
//! and its whole answer is its files; so the second time it is asked the
//! same thing —in another cartridge of the same game, or in another worktree
//! that shares the cache— the answer comes from the disk. A stage that
//! writes anywhere else does not fit that, and goes through
//! [`call_uncached`].

use crate::fail::{io, Result, Stop};
use rm2k_project::cache;
use serde_json::Value;
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fmt::Display;
use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

/// What a stage answers: every file it made, by name, as its binary wrote
/// them into `--out`.
pub type Files = BTreeMap<String, Vec<u8>>;

/// The disk cache's category for the stages' answers.
const CATEGORY: &str = "stages";

/// The disk cache the answers are kept in: set once, by the conversion,
/// unless `NO_CACHE=1`. Without it every stage runs.
static CACHE: OnceLock<PathBuf> = OnceLock::new();

/// Keeps the stages' answers in `directory` from here on.
pub fn keep_answers_in(directory: PathBuf) {
    let _ = CACHE.set(directory);
}

/// How a stage reads a directory it is given, which is what of it goes into
/// a key.
#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum Reads {
    /// Whatever is below it: the dump, the game, a file.
    Everything,
    /// A `--search-dir`: only RM2k's resource folders right below it, and
    /// the files right inside them, which is all a lookup opens —see
    /// `find_resource` in `rm2k-render`—. One of them is the root of the
    /// tools' checkout, and taking it whole would expire every answer with
    /// any change to the runtime or the tests, which no stage reads.
    Resources,
}

/// What each path the keys named turned out to be: the dump is named by
/// every map's call, and is read once.
static VERSIONS: Mutex<BTreeMap<(PathBuf, Reads), String>> = Mutex::new(BTreeMap::new());

/// What goes into a key in place of a path: its content, so two checkouts
/// with the same dump give the same key. A directory the cache itself made
/// —a game unpacked from its `.zip`, the game with the port's files on
/// top— is already named by its content, so its name is enough.
fn version(path: &Path, reads: Reads, cache_dir: &Path) -> Result<String> {
    let mut versions = VERSIONS.lock().unwrap_or_else(|e| e.into_inner());
    let memo = (path.to_path_buf(), reads);
    if let Some(v) = versions.get(&memo) {
        return Ok(v.clone());
    }
    let made_by_the_cache = ["zip", "own-files"]
        .iter()
        .find_map(|c| path.strip_prefix(cache_dir.join(c)).ok().map(|r| (c, r)));
    let v = if let Some((category, name)) = made_by_the_cache {
        format!("cache {category}/{}", name.display())
    } else if !path.is_dir() {
        format!("file {}", cache::version_of(Path::new("/"), &[path])?)
    } else if reads == Reads::Resources {
        format!("resources {}", resources_version(path)?)
    } else {
        format!("tree {}", cache::tree_version(path)?)
    };
    versions.insert(memo, v.clone());
    Ok(v)
}

/// The hash of the files a resource lookup can open below `directory`: the
/// ones right inside each of its folders named as one of RM2k's, whatever
/// the case, with their names.
fn resources_version(directory: &Path) -> Result<String> {
    let folders: Vec<String> = rm2k_project::own_files::FOLDERS
        .iter()
        .map(|f| f.to_lowercase())
        .collect();
    let sorted = |dir: &Path| -> Result<Vec<PathBuf>> {
        let mut out: Vec<PathBuf> = std::fs::read_dir(dir)
            .map_err(|e| io(dir, e))?
            .flatten()
            .map(|e| e.path())
            .collect();
        out.sort();
        Ok(out)
    };
    let mut parts: Vec<Vec<u8>> = Vec::new();
    for folder in sorted(directory)? {
        let name = folder.file_name().unwrap_or_default().to_string_lossy();
        if !folder.is_dir() || !folders.contains(&name.to_lowercase()) {
            continue;
        }
        for file in sorted(&folder)? {
            if file.is_file() {
                let relative = file.strip_prefix(directory).unwrap_or(&file);
                parts.push(relative.as_os_str().as_encoded_bytes().to_vec());
                parts.push(std::fs::read(&file).map_err(|e| io(&file, e))?);
            }
        }
    }
    Ok(cache::key(&parts))
}

/// A request or flag value as it goes into a key: an absolute path that
/// exists goes by what it holds, anything else as it is.
fn in_key(text: &str, reads: Reads, cache_dir: &Path) -> Result<String> {
    let path = Path::new(text);
    if path.is_absolute() && path.exists() {
        Ok(format!("\0path {}", version(path, reads, cache_dir)?))
    } else {
        Ok(text.to_string())
    }
}

/// The request with each path it carries in place by its content.
fn request_in_key(value: &Value, cache_dir: &Path) -> Result<Value> {
    Ok(match value {
        Value::String(s) => Value::String(in_key(s, Reads::Everything, cache_dir)?),
        Value::Array(items) => Value::Array(
            items
                .iter()
                .map(|v| request_in_key(v, cache_dir))
                .collect::<Result<_>>()?,
        ),
        Value::Object(map) => Value::Object(
            map.iter()
                .map(|(k, v)| Ok((k.clone(), request_in_key(v, cache_dir)?)))
                .collect::<Result<_>>()?,
        ),
        other => other.clone(),
    })
}

/// The stages' flags whose value is a path they read.
const PATH_FLAGS: &[&str] = &["--data", "--search-dir", "--game-dir", "--rtp-dir"];

/// Everything a stage's answer can depend on: the code that answers, by
/// content —a converter built again expires its answers on its own—, the stage, the request, and the flags, each path
/// among them and in the request by what it holds —the dump, the game, the
/// RTP, the folders searched—. **A stage reads no variable and no other
/// file**: one that started to would have to say so here.
///
/// Who answers is the converter, [`std::env::current_exe`], with the stage
/// named by its binary and its command, because one binary answers every
/// one of them: `rm2k-snes-screens layout` and `rm2k-snes-battle layout` are
/// both asked `{}`. `"stage 2"` is from when a stage that was still a
/// process was keyed `"stage 1"`, by its own binary.
pub fn key(stage: Stage, request: &Value, flags: &[OsString], cache_dir: &Path) -> Result<String> {
    let mut parts = vec![
        "stage 2".to_string(),
        version(&converter()?, Reads::Everything, cache_dir)?,
        stage.to_string(),
        serde_json::to_string(&request_in_key(request, cache_dir)?).expect("a request is JSON"),
    ];
    let mut reads = Reads::Everything;
    let mut names_a_path = false;
    for flag in flags {
        let flag = flag.to_string_lossy();
        // A folder that is not there —`build/patches-manual` in a game
        // without manual patches— is the same nothing in every worktree,
        // and its path is the worktree's. Only after a flag that names a
        // path: in a request, a text that starts with a slash may be
        // anything.
        parts.push(if names_a_path && !Path::new(flag.as_ref()).exists() {
            "\0missing".to_string()
        } else {
            in_key(&flag, reads, cache_dir)?
        });
        names_a_path = PATH_FLAGS.contains(&flag.as_ref());
        reads = if flag == "--search-dir" {
            Reads::Resources
        } else {
            Reads::Everything
        };
    }
    Ok(cache::key(&parts))
}

/// The binary the converter's own code is in —`rm2k-snes-convert`, or a
/// test's—, which is what answers every stage that is a function.
fn converter() -> Result<PathBuf> {
    std::env::current_exe()
        .map_err(|e| Stop::new(format!("the converter cannot find its own binary: {e}")))
}

/// The files a stage wrote, as one value of the cache: each name and its
/// bytes, with their lengths in front.
fn pack(written: &Files) -> Vec<u8> {
    let mut out = b"rm2k-snes stage answer 1\n".to_vec();
    for (name, bytes) in written {
        out.extend((name.len() as u64).to_le_bytes());
        out.extend(name.as_bytes());
        out.extend((bytes.len() as u64).to_le_bytes());
        out.extend(bytes);
    }
    out
}

/// [`pack`] the other way, or None if the value is not one.
fn unpack(value: &[u8]) -> Option<Files> {
    let mut rest = value.strip_prefix(b"rm2k-snes stage answer 1\n".as_slice())?;
    let take = |rest: &mut &[u8]| -> Option<Vec<u8>> {
        let (len, tail) = rest.split_first_chunk::<8>()?;
        let len = usize::try_from(u64::from_le_bytes(*len)).ok()?;
        let (bytes, tail) = (tail.get(..len)?, tail.get(len..)?);
        *rest = tail;
        Some(bytes.to_vec())
    };
    let mut written = BTreeMap::new();
    while !rest.is_empty() {
        let name = String::from_utf8(take(&mut rest)?).ok()?;
        let bytes = take(&mut rest)?;
        written.insert(name, bytes);
    }
    Some(written)
}

/// A stage the converter calls as a function of its crate: which binary
/// it was and which of its commands. Both name it in the [`key`], and the
/// binary starts what it answers no with, as its `main` did.
#[derive(Clone, Copy, Debug)]
pub struct Stage {
    pub binary: &'static str,
    pub command: &'static str,
}

impl std::fmt::Display for Stage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{} {}", self.binary, self.command)
    }
}

/// `answer()`, the stage's function, asked `request` with `flags`: the two
/// are what its binary was run with —the flags without `--request` and
/// `--out`— and what the [`key`] reads, so `answer` must read nothing they
/// do not name. What it answers no to stops the conversion with its
/// message, after the binary's name, as its process said it.
///
/// The answer comes from the disk cache if the same thing was asked
/// before: see the top of this module.
pub fn call<E: Display>(
    stage: Stage,
    request: &Value,
    flags: &[OsString],
    answer: impl FnOnce() -> std::result::Result<Files, E>,
) -> Result<Files> {
    let Some(cache_dir) = CACHE.get() else {
        return call_uncached(stage, answer);
    };
    let key = key(stage, request, flags, cache_dir)?;
    if let Some(files) = cache::load(cache_dir, CATEGORY, &key).and_then(|v| unpack(&v)) {
        return Ok(files);
    }
    let files = call_uncached(stage, answer)?;
    cache::store(cache_dir, CATEGORY, &key, &pack(&files));
    Ok(files)
}

/// [`call`], always calling the stage: for one whose answer is not worth
/// keeping —constants— or that the converter does not want kept.
///
/// A stage that panics stops the conversion with what it said, as its
/// process did when it died: in one of the threads that convert the maps it
/// would otherwise take the converter down with it, and the message would
/// lose which map it was about. The panic itself is already on standard
/// error, where the default hook prints it.
pub fn call_uncached<T, E: Display>(
    stage: Stage,
    answer: impl FnOnce() -> std::result::Result<T, E>,
) -> Result<T> {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(answer)) {
        Ok(Ok(answer)) => Ok(answer),
        Ok(Err(e)) => Err(Stop::new(format!("{}: {e}", stage.binary))),
        Err(panic) => {
            let what = panic
                .downcast_ref::<&str>()
                .map(|s| s.to_string())
                .or_else(|| panic.downcast_ref::<String>().cloned())
                .unwrap_or_default();
            Err(Stop::new(format!("{stage} panicked: {what}")))
        }
    }
}

/// A file a stage wrote, as text.
pub fn text(written: &Files, name: &str) -> Result<String> {
    let bytes = written
        .get(name)
        .ok_or_else(|| Stop::new(format!("the stage did not write {name}")))?;
    String::from_utf8(bytes.clone()).map_err(|e| Stop::new(format!("{name}: {e}")))
}

/// A JSON file a stage wrote.
pub fn json(written: &Files, name: &str) -> Result<Value> {
    typed(written, name)
}

/// A JSON file a stage wrote, as the type its stage answers it with.
pub fn typed<T: serde::de::DeserializeOwned>(written: &Files, name: &str) -> Result<T> {
    serde_json::from_str(&text(written, name)?).map_err(|e| Stop::new(format!("{name}: {e}")))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    const WALLY_MAP: Stage = Stage {
        binary: "wally",
        command: "map",
    };

    fn scratch(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!(
            "rm2k-snes-convert-stage-{name}-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    /// Two worktrees with the same dump ask a stage the same thing with
    /// different paths: the key has to be the same, or no worktree finds
    /// what another one built. And a dump that changes is another key, even
    /// at the same path. The memo of each path's version is per process, so
    /// each side gets a dump of its own.
    #[test]
    fn a_key_holds_what_the_paths_hold_not_where_they_are() {
        let root = scratch("key");
        let cache_dir = root.join("cache");
        let mut keys = Vec::new();
        for (side, map) in [("one", "{}"), ("two", "{}"), ("three", "{\"x\": 1}")] {
            let data = root.join(side).join("data");
            std::fs::create_dir_all(data.join("some")).unwrap();
            std::fs::write(data.join("some").join("file"), map).unwrap();
            let forked = root.join(side).join("forked");
            std::fs::write(&forked, "forked").unwrap();
            let request = json!({"map": 1, "map_files": {"1": forked.display().to_string()}});
            let flags: Vec<OsString> = vec!["--data".into(), data.into_os_string()];
            keys.push(key(WALLY_MAP, &request, &flags, &cache_dir).unwrap());
        }
        assert_eq!(keys[0], keys[1]);
        assert_ne!(keys[0], keys[2]);
    }

    /// A directory the cache made is named by its content already, and goes
    /// by its name: the game unpacked from its `.zip` is not read whole on
    /// every conversion.
    #[test]
    fn a_directory_the_cache_made_goes_by_its_name() {
        let root = scratch("made");
        let unpacked = root.join("zip").join("game-0123456789abcdef");
        std::fs::create_dir_all(&unpacked).unwrap();
        assert_eq!(
            version(&unpacked, Reads::Everything, &root).unwrap(),
            "cache zip/game-0123456789abcdef"
        );
    }

    /// One of the folders searched is the root of the tools' checkout: a
    /// branch that only touches the runtime must find Wally's answers all
    /// the same. What a lookup can open —a file in a folder named as one of
    /// RM2k's— does change the key.
    #[test]
    fn a_search_dir_goes_by_its_resource_folders_alone() {
        let root = scratch("search");
        let cache_dir = root.join("cache");
        let data = root.join("data");
        std::fs::create_dir_all(&data).unwrap();
        let mut keys = Vec::new();
        for (side, runtime, picture) in [
            ("one", "lda #0", "a"),
            ("two", "lda #1", "a"),
            ("three", "lda #1", "b"),
        ] {
            let tools = root.join(side);
            std::fs::create_dir_all(tools.join("runtime")).unwrap();
            std::fs::create_dir_all(tools.join("picture")).unwrap();
            std::fs::write(tools.join("runtime").join("main.s"), runtime).unwrap();
            std::fs::write(tools.join("README.md"), side).unwrap();
            std::fs::write(tools.join("picture").join("Sign.png"), picture).unwrap();
            let flags: Vec<OsString> = vec![
                "--data".into(),
                data.clone().into_os_string(),
                "--search-dir".into(),
                tools.into_os_string(),
            ];
            keys.push(key(WALLY_MAP, &json!({}), &flags, &cache_dir).unwrap());
        }
        assert_eq!(keys[0], keys[1]);
        assert_ne!(keys[1], keys[2]);
    }

    /// A folder searched that a game does not have —the patches' built
    /// images, `build/patches-manual`, in a game without manual patches—
    /// is in each worktree's `build`: it goes into the key as missing, not
    /// by where it would be. Measured: without this, Sunset, Vampires Dawn
    /// and Zounds found none of Wally's answers from another worktree.
    #[test]
    fn a_missing_folder_goes_as_missing_wherever_it_would_be() {
        let root = scratch("missing");
        let keys: Vec<String> = ["one", "two"]
            .iter()
            .map(|side| {
                let flags: Vec<OsString> = vec![
                    "--search-dir".into(),
                    root.join(side)
                        .join("build")
                        .join("patches-manual")
                        .into_os_string(),
                ];
                key(WALLY_MAP, &json!({}), &flags, &root.join("cache")).unwrap()
            })
            .collect();
        assert_eq!(keys[0], keys[1]);
        // And a folder that is there is not the same as one that is not.
        let there = root.join("there");
        std::fs::create_dir_all(&there).unwrap();
        let flags: Vec<OsString> = vec!["--search-dir".into(), there.into_os_string()];
        assert_ne!(
            keys[0],
            key(WALLY_MAP, &json!({}), &flags, &root.join("cache")).unwrap()
        );
    }

    #[test]
    fn an_answer_comes_back_from_the_cache_as_it_was_written() {
        let mut written = BTreeMap::new();
        written.insert("map.json".to_string(), b"{}".to_vec());
        written.insert("empty.inc".to_string(), Vec::new());
        written.insert("ñ.bin".to_string(), vec![0, 1, 2, 255]);
        assert_eq!(unpack(&pack(&written)), Some(written.clone()));
        assert_eq!(unpack(&pack(&BTreeMap::new())), Some(BTreeMap::new()));
        // Cut short, it is not an answer: the stage runs again.
        let packed = pack(&written);
        assert_eq!(unpack(&packed[..packed.len() - 1]), None);
        assert_eq!(unpack(b"something else"), None);
    }

    const SCREENS_LAYOUT: Stage = Stage {
        binary: "rm2k-snes-screens",
        command: "layout",
    };
    const BATTLE_LAYOUT: Stage = Stage {
        binary: "rm2k-snes-battle",
        command: "layout",
    };

    /// One binary answers every stage, so the stage's name is what tells
    /// two of them apart: both layouts are asked `{}`.
    #[test]
    fn a_function_s_key_names_the_stage() {
        let root = scratch("function");
        let cache_dir = root.join("cache");
        let request = json!({});
        let screens = key(SCREENS_LAYOUT, &request, &[], &cache_dir).unwrap();
        let battle = key(BATTLE_LAYOUT, &request, &[], &cache_dir).unwrap();
        assert_ne!(screens, battle);
        assert_eq!(
            screens,
            key(SCREENS_LAYOUT, &request, &[], &cache_dir).unwrap()
        );
    }

    /// What a stage answers no to, or panics with, stops the conversion
    /// with what it said, after its binary's name as its process printed
    /// it; it does not take the converter down.
    #[test]
    fn a_stage_that_says_no_or_panics_stops_with_its_message() {
        let no = call_uncached(BATTLE_LAYOUT, || Err::<Files, _>("it does not fit")).unwrap_err();
        assert_eq!(no.message, "rm2k-snes-battle: it does not fit");
        assert_eq!(no.code, 1);
        let panicked = call_uncached(BATTLE_LAYOUT, || -> std::result::Result<Files, String> {
            panic!("index out of bounds: {}", 3)
        })
        .unwrap_err();
        assert_eq!(
            panicked.message,
            "rm2k-snes-battle layout panicked: index out of bounds: 3"
        );
    }

    /// The second time a function is asked the same thing it is not
    /// called: its answer comes from the disk as it was. The only test that
    /// sets the cache, which is once per process.
    #[test]
    fn a_function_asked_again_answers_from_the_cache() {
        let root = scratch("call");
        keep_answers_in(root.join("cache"));
        let calls = std::cell::Cell::new(0);
        let answer = || -> std::result::Result<Files, String> {
            calls.set(calls.get() + 1);
            Ok(Files::from([(
                "layout.json".to_string(),
                b"{\"x\": 1}\n".to_vec(),
            )]))
        };
        let request = json!({"asked": "once"});
        let first = call(SCREENS_LAYOUT, &request, &[], answer).unwrap();
        let again = call(SCREENS_LAYOUT, &request, &[], answer).unwrap();
        assert_eq!(calls.get(), 1);
        assert_eq!(first, again);
        // Another stage asked the same is called.
        call(BATTLE_LAYOUT, &request, &[], answer).unwrap();
        assert_eq!(calls.get(), 2);
    }
}
