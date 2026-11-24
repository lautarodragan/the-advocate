//! Running a stage of the conversion: a function of its crate, or still a
//! program of its own.
//!
//! Each domain reads the game from the dump itself, gets what the cartridge
//! decided in a JSON request, and answers what it made —pieces of the `.inc`
//! and a JSON with what the rest of the conversion needs—, as files by name.
//! What goes in the request and where each piece goes is the converter's
//! business, not this module's. See "One stage of a converter" in
//! `rm2k-snes-battle`'s README for the shape.
//!
//! **The stages are becoming functions the converter calls**, one crate at
//! a time: [`call`] calls one of those; [`run`] still runs an executable on
//! the PATH and reads back what it wrote into `--out`. Both answer the same
//! [`Files`], so a stage moves from one to the other without its caller
//! reading anything differently. `run`, [`run_uncached`], [`hand_over`],
//! [`which`] and [`Scratch`] go with the last stage that is a process.
//!
//! **What a stage answers is kept in the disk cache**, under the key of
//! everything it can depend on: see [`key`]. A stage is a function of the
//! code that answers, its command, its request and what its flags point at,
//! and its whole answer is its files; so the second time it is asked the
//! same thing —in another cartridge of the same game, or in another worktree
//! that shares the cache— the answer comes from the disk. A stage that
//! writes anywhere else does not fit that, and goes through
//! [`call_uncached`] or [`run_uncached`].

use crate::fail::{io, Result, Stop};
use rm2k_project::cache;
use serde_json::Value;
use std::collections::BTreeMap;
use std::ffi::OsString;
use std::fmt::Display;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::atomic::{AtomicUsize, Ordering};
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
/// content —a reinstalled stage, or a converter built again, expires its
/// answers on its own—, the stage, the request, and the flags, each path
/// among them and in the request by what it holds —the dump, the game, the
/// RTP, the folders searched—. **A stage reads no variable and no other
/// file**: one that started to would have to say so here.
///
/// Who answers is the stage's own binary while it is a process, keyed as it
/// always was —`"stage 1"`, its command alone—, so its answers already on
/// disk are still found; and the converter's, [`std::env::current_exe`],
/// once it is a function of its crate —`"stage 2"`—, with the stage named
/// by its binary and its command, because one binary answers every one of
/// them: `rm2k-snes-screens layout` and `rm2k-snes-battle layout` are both
/// asked `{}`.
pub fn key(
    answerer: &Answerer,
    request: &Value,
    flags: &[OsString],
    cache_dir: &Path,
) -> Result<String> {
    let (tag, binary, name) = match answerer {
        Answerer::Process { binary, command } => ("stage 1", binary.clone(), command.clone()),
        Answerer::Function(stage) => ("stage 2", converter()?, stage.to_string()),
    };
    let mut parts = vec![
        tag.to_string(),
        version(&binary, Reads::Everything, cache_dir)?,
        name,
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

/// Who answers a stage, for its [`key`].
pub enum Answerer {
    /// Its own binary, run as a process, and the command it is run with.
    // Nothing runs a cached stage as a process since A1-A4 of
    // the-stages-speak-json-nobody-types; it goes in A9, with `run`, and
    // its key stays until then for the test that keeps the two apart.
    #[allow(dead_code)]
    Process { binary: PathBuf, command: String },
    /// A function of its crate, which the converter calls.
    Function(Stage),
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

/// A directory of its own for one call, removed when it is dropped.
pub struct Scratch(pub PathBuf);

impl Scratch {
    pub fn new(prefix: &str) -> Result<Scratch> {
        static COUNT: AtomicUsize = AtomicUsize::new(0);
        let n = COUNT.fetch_add(1, Ordering::Relaxed);
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.subsec_nanos())
            .unwrap_or(0);
        let dir =
            std::env::temp_dir().join(format!("{prefix}-{}-{n}-{stamp:x}", std::process::id()));
        std::fs::create_dir_all(&dir).map_err(|e| io(&dir, e))?;
        Ok(Scratch(dir))
    }
}

impl Drop for Scratch {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
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
    let key = key(&Answerer::Function(stage), request, flags, cache_dir)?;
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
pub fn call_uncached<E: Display>(
    stage: Stage,
    answer: impl FnOnce() -> std::result::Result<Files, E>,
) -> Result<Files> {
    match std::panic::catch_unwind(std::panic::AssertUnwindSafe(answer)) {
        Ok(Ok(files)) => Ok(files),
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

/// The path of `binary` on the PATH, or why it is not there.
pub fn which(binary: &str, project: &str) -> Result<PathBuf> {
    let path = std::env::var_os("PATH").unwrap_or_default();
    for dir in std::env::split_paths(&path) {
        let candidate = dir.join(binary);
        if candidate.is_file() {
            return Ok(candidate);
        }
    }
    Err(Stop::new(format!(
        "`{binary}` is missing, one of the converter's stages.\n\nIt is a Rust binary of the \
         suite, and is installed as a system tool:\n\n    just install {project}"
    )))
}

fn write_request(dir: &Path, request: &Value) -> Result<PathBuf> {
    let path = dir.join("request.json");
    let text = serde_json::to_string(request).expect("a request is JSON");
    std::fs::write(&path, text).map_err(|e| io(&path, e))?;
    Ok(path)
}

/// `binary command --request <request> --out <dir> *flags`, and `{name:
/// bytes}` of every file it wrote. `project` is the name `install` knows
/// it by, for the message when it is not on the PATH. What it answers no
/// to stops the conversion with its message.
///
/// The answer comes from the disk cache if the same thing was asked
/// before: see the top of this module.
///
/// No stage is called this way since A1-A4 of
/// the-stages-speak-json-nobody-types: it goes in A9.
#[allow(dead_code)]
pub fn run(
    binary: &str,
    project: &str,
    command: &str,
    request: &Value,
    flags: &[OsString],
) -> Result<Files> {
    let Some(cache_dir) = CACHE.get() else {
        return run_uncached(binary, project, command, request, flags);
    };
    let answerer = Answerer::Process {
        binary: which(binary, project)?,
        command: command.to_string(),
    };
    let key = key(&answerer, request, flags, cache_dir)?;
    if let Some(written) = cache::load(cache_dir, CATEGORY, &key).and_then(|v| unpack(&v)) {
        return Ok(written);
    }
    let written = run_uncached(binary, project, command, request, flags)?;
    cache::store(cache_dir, CATEGORY, &key, &pack(&written));
    Ok(written)
}

/// [`run`], always running the stage: for one that writes something besides
/// its answer, which a cached answer would not write.
///
/// The emission was the one, until A6 of the-stages-speak-json-nobody-types
/// put its raw data in its answer; since then only [`run`] calls this, and
/// it goes with it in A9.
pub fn run_uncached(
    binary: &str,
    project: &str,
    command: &str,
    request: &Value,
    flags: &[OsString],
) -> Result<Files> {
    let path = which(binary, project)?;
    let scratch = Scratch::new(binary)?;
    let request_path = write_request(&scratch.0, request)?;
    let out = scratch.0.join("out");
    let _ = std::io::stdout().flush();
    let done = Command::new(&path)
        .arg(command)
        .arg("--request")
        .arg(&request_path)
        .arg("--out")
        .arg(&out)
        .args(flags)
        .stdin(Stdio::null())
        .output()
        .map_err(|e| Stop::new(format!("{binary}: {e}")))?;
    if !done.status.success() {
        let text = String::from_utf8_lossy(&done.stderr).trim().to_string();
        return Err(Stop::new(if text.is_empty() {
            format!(
                "{binary} {command} exited with {}",
                done.status.code().unwrap_or(-1)
            )
        } else {
            text
        }));
    }
    let mut written = BTreeMap::new();
    let mut names: Vec<_> = std::fs::read_dir(&out)
        .map_err(|e| io(&out, e))?
        .flatten()
        .map(|e| e.file_name().to_string_lossy().to_string())
        .collect();
    names.sort();
    for name in names {
        let file = out.join(&name);
        written.insert(name, std::fs::read(&file).map_err(|e| io(&file, e))?);
    }
    Ok(written)
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
    serde_json::from_str(&text(written, name)?).map_err(|e| Stop::new(format!("{name}: {e}")))
}

/// `binary [command] --request <request> *args`, for a program that writes
/// what it makes where `args` say, and whose output goes out with what the
/// converter prints: `rm2k-snes-patches`, which writes what the converter
/// decided to lose next to the ROM, and the music, `rm2k-snes-audio
/// cartridge`, of whose pieces the rest of the conversion reads only the
/// `losses` of its `audio.json`, for `degradations.json`.
///
/// Neither is called this way since A7 and A8 of
/// the-stages-speak-json-nobody-types: it goes in A9.
#[allow(dead_code)]
pub fn hand_over(
    binary: &str,
    project: &str,
    request: &Value,
    args: &[OsString],
    command: Option<&str>,
) -> Result<()> {
    let path = which(binary, project)?;
    let scratch = Scratch::new(binary)?;
    let request_path = write_request(&scratch.0, request)?;
    let _ = std::io::stdout().flush();
    let mut call = Command::new(&path);
    if let Some(command) = command {
        call.arg(command);
    }
    let done = call
        .arg("--request")
        .arg(&request_path)
        .args(args)
        .stdin(Stdio::null())
        .stdout(Stdio::inherit())
        .stderr(Stdio::piped())
        .output()
        .map_err(|e| Stop::new(format!("{binary}: {e}")))?;
    if !done.status.success() {
        let text = String::from_utf8_lossy(&done.stderr).trim().to_string();
        return Err(Stop::new(if text.is_empty() {
            format!("{binary} exited with {}", done.status.code().unwrap_or(-1))
        } else {
            text
        }));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    /// `binary map`, a stage that is a process.
    fn process(binary: &Path) -> Answerer {
        Answerer::Process {
            binary: binary.to_path_buf(),
            command: "map".to_string(),
        }
    }

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
        let binary = root.join("wally");
        std::fs::write(&binary, b"a stage").unwrap();
        let mut keys = Vec::new();
        for (side, map) in [("one", "{}"), ("two", "{}"), ("three", "{\"x\": 1}")] {
            let data = root.join(side).join("data");
            std::fs::create_dir_all(data.join("some")).unwrap();
            std::fs::write(data.join("some").join("file"), map).unwrap();
            let forked = root.join(side).join("forked");
            std::fs::write(&forked, "forked").unwrap();
            let request = json!({"map": 1, "map_files": {"1": forked.display().to_string()}});
            let flags: Vec<OsString> = vec!["--data".into(), data.into_os_string()];
            keys.push(key(&process(&binary), &request, &flags, &cache_dir).unwrap());
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
        let binary = root.join("wally");
        std::fs::write(&binary, b"a stage").unwrap();
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
            keys.push(key(&process(&binary), &json!({}), &flags, &cache_dir).unwrap());
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
        let binary = root.join("wally");
        std::fs::write(&binary, b"a stage").unwrap();
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
                key(&process(&binary), &json!({}), &flags, &root.join("cache")).unwrap()
            })
            .collect();
        assert_eq!(keys[0], keys[1]);
        // And a folder that is there is not the same as one that is not.
        let there = root.join("there");
        std::fs::create_dir_all(&there).unwrap();
        let flags: Vec<OsString> = vec!["--search-dir".into(), there.into_os_string()];
        assert_ne!(
            keys[0],
            key(&process(&binary), &json!({}), &flags, &root.join("cache")).unwrap()
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

    /// One binary answers every stage that is a function, so the stage's
    /// name is what tells two of them apart: both layouts are asked `{}`.
    /// And a stage that became a function does not find what its process
    /// answered: the code that answers is another one.
    #[test]
    fn a_function_s_key_names_the_stage_and_not_its_old_binary() {
        let root = scratch("function");
        let cache_dir = root.join("cache");
        let request = json!({});
        let screens = key(
            &Answerer::Function(SCREENS_LAYOUT),
            &request,
            &[],
            &cache_dir,
        )
        .unwrap();
        let battle = key(
            &Answerer::Function(BATTLE_LAYOUT),
            &request,
            &[],
            &cache_dir,
        )
        .unwrap();
        assert_ne!(screens, battle);
        assert_eq!(
            screens,
            key(
                &Answerer::Function(SCREENS_LAYOUT),
                &request,
                &[],
                &cache_dir
            )
            .unwrap()
        );
        let binary = root.join("rm2k-snes-screens");
        std::fs::write(&binary, b"a stage").unwrap();
        let old = Answerer::Process {
            binary,
            command: "layout".to_string(),
        };
        assert_ne!(screens, key(&old, &request, &[], &cache_dir).unwrap());
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
