//! A port's own files, in front of the game's: `patches/manual/files/`.
//!
//! **It is RM2k's own tree** —`Picture/`, `System/`, `CharSet/`…— and a
//! file there **replaces the game's of the same name**: same folder, same
//! name without extension, both without regard to case, which is how RM2k
//! looks a resource up (see `find_resource` in `rm2k-render`). So a
//! `Picture/Menu.png` of ours hides the game's `picture/menu.bmp` too: if
//! both stayed, which one a lookup found would depend on the order of a
//! directory listing.
//!
//! **Nobody looks the files up here.** The lookups are three functions in
//! three crates and a few paths joined by hand, in separate processes —see
//! `game_files` in `rm2k-snes-cartridges`—, all of them below `--game-dir`.
//! So this builds **one directory** that is the game with ours on top, and
//! from [`crate::environment::Environment::unpack`] on `--game-dir` is that
//! directory: every reader sees the port's file without knowing it exists.
//! The same reason the `.zip` is unpacked instead of read inside.
//!
//! The directory is **links to the game's files**, and copies of ours, in
//! `own-files/` in the project's cache, named by everything it depends on
//! —the game's identity and our files, by name and content—: changing a
//! file of ours is another directory, never half of each. It is written
//! aside and renamed, like the unpacked `.zip`, because a game's tests ask
//! for it from several processes at once.
//!
//! **A file of ours replaces one that exists**, in the game or in the RTP:
//! a misspelled name would do nothing, silently, and that is worse than an
//! error —the same rule as a forked map's—. One the game lacks and the RTP
//! has goes into the game's tree and covers the RTP's, which is looked up
//! after the game.
//!
//! What it replaced stays written inside the directory, in [`RECORD`], so
//! a tool that receives the directory already built —the converter, from
//! `rm2k-snes-cartridges`— knows it is one and can say what changed.

use std::collections::{BTreeMap, BTreeSet};
use std::fs;
use std::path::{Path, PathBuf};

use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::cache;
use crate::Error;

/// The file inside the merged directory that says it is one, and what it
/// replaced. Hidden: the fingerprint and the lookups skip it.
pub const RECORD: &str = ".rm2k-own-files.json";

/// RM2k's resource folders —2000's, and 2003's on top—: the only ones a
/// file of ours can go in. A folder that is not one is a typo, and it would
/// replace nothing.
pub const FOLDERS: &[&str] = &[
    "Backdrop",
    "Battle",
    "CharSet",
    "ChipSet",
    "FaceSet",
    "GameOver",
    "Monster",
    "Movie",
    "Music",
    "Panorama",
    "Picture",
    "Sound",
    "System",
    "Title",
    "Battle2",
    "BattleCharSet",
    "BattleWeapon",
    "Frame",
    "System2",
];

/// What the port's files did to the game.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct OwnFiles {
    /// The merged directory: what `--game-dir` is from here on.
    pub directory: PathBuf,
    /// `Folder/Name.ext` of ours → the game's files it hides, each as
    /// `Folder/Name.ext` with the game's spelling.
    pub replaced: BTreeMap<String, Vec<String>>,
    /// Ours that the game does not have: they cover the RTP's.
    pub over_rtp: Vec<String>,
}

impl OwnFiles {
    /// One line per file, for a build's log.
    pub fn lines(&self) -> Vec<String> {
        let mut out = Vec::new();
        for (ours, theirs) in &self.replaced {
            out.push(format!("{ours} replaces the game's {}", theirs.join(", ")));
        }
        for ours in &self.over_rtp {
            out.push(format!("{ours} replaces the RTP's"));
        }
        out
    }

    fn to_json(&self) -> Value {
        json!({"replaced": self.replaced, "over_rtp": self.over_rtp})
    }

    /// The record of a directory this module built, or None if it is not
    /// one.
    pub fn read(directory: &Path) -> Result<Option<OwnFiles>, Error> {
        let path = directory.join(RECORD);
        let Ok(text) = fs::read_to_string(&path) else {
            return Ok(None);
        };
        let bad = |e: String| Error(format!("{}: {e}", path.display()));
        let v: Value = serde_json::from_str(&text).map_err(|e| bad(e.to_string()))?;
        let mut replaced = BTreeMap::new();
        for (ours, theirs) in v["replaced"].as_object().into_iter().flatten() {
            let theirs = theirs
                .as_array()
                .into_iter()
                .flatten()
                .filter_map(|t| t.as_str().map(String::from))
                .collect();
            replaced.insert(ours.clone(), theirs);
        }
        let over_rtp = v["over_rtp"]
            .as_array()
            .into_iter()
            .flatten()
            .filter_map(|t| t.as_str().map(String::from))
            .collect();
        Ok(Some(OwnFiles {
            directory: directory.to_path_buf(),
            replaced,
            over_rtp,
        }))
    }
}

fn io(path: &Path, e: std::io::Error) -> Error {
    Error(format!("{}: {e}", path.display()))
}

fn names(directory: &Path) -> Result<Vec<String>, Error> {
    let mut out: Vec<String> = fs::read_dir(directory)
        .map_err(|e| io(directory, e))?
        .flatten()
        .map(|e| e.file_name().to_string_lossy().into_owned())
        .filter(|n| !n.starts_with('.'))
        .collect();
    out.sort();
    Ok(out)
}

/// `name.ext` without its extension, in lower case: what RM2k compares.
fn stem(file_name: &str) -> String {
    match file_name.rfind('.') {
        Some(at) if at > 0 => file_name[..at].to_lowercase(),
        _ => file_name.to_lowercase(),
    }
}

/// The entry of `directory` named `name` without regard to case.
fn entry_like(directory: &Path, name: &str) -> Option<String> {
    let wanted = name.to_lowercase();
    names(directory)
        .ok()?
        .into_iter()
        .find(|n| n.to_lowercase() == wanted)
}

/// Our files, as (folder as written, file name), checked: only folders of
/// [`FOLDERS`], only files inside them, and no two of ours with the same
/// name in the same folder.
fn ours(own: &Path) -> Result<Vec<(String, String)>, Error> {
    let mut out = Vec::new();
    for folder in names(own)? {
        let path = own.join(&folder);
        if !path.is_dir() {
            return Err(Error(format!(
                "{}: only RM2k's folders go here —Picture/, System/…—, each with the files \
                 that replace the game's",
                path.display()
            )));
        }
        if !FOLDERS.iter().any(|f| f.eq_ignore_ascii_case(&folder)) {
            return Err(Error(format!(
                "{}: {folder} is not one of RM2k's folders ({}), so it would replace nothing",
                path.display(),
                FOLDERS.join(", ")
            )));
        }
        let mut seen = BTreeSet::new();
        for file in names(&path)? {
            let file_path = path.join(&file);
            if !file_path.is_file() {
                return Err(Error(format!(
                    "{}: RM2k's folders have no folders inside",
                    file_path.display()
                )));
            }
            if !seen.insert(stem(&file)) {
                return Err(Error(format!(
                    "{}: two files of ours with the same name, and RM2k looks them up without \
                     the extension",
                    file_path.display()
                )));
            }
            out.push((folder.clone(), file));
        }
    }
    Ok(out)
}

/// Whether `own` has any file at all: without one the game is read as it
/// is, and nothing is built.
pub fn any(own: &Path) -> bool {
    own.is_dir() && names(own).is_ok_and(|n| !n.is_empty())
}

/// The game with our files on top, below `into`: built if it is not there.
/// `identity` says which game it is —the `.zip`'s hash, or nothing for a
/// directory, whose listing goes into the name instead—; `rtp`, if known,
/// is where a file the game lacks has to be.
pub fn merged(
    game: &Path,
    identity: &str,
    own: &Path,
    rtp: Option<&Path>,
    into: &Path,
) -> Result<OwnFiles, Error> {
    let files = ours(own)?;

    // What it depends on: the game, by its hash or by its path and its
    // listing —its files are links, so a change in their content is seen
    // through them, but one added or removed is not—, and ours whole.
    let mut h = Sha256::new();
    h.update(format!("game {identity}\n{}\n", game.display()));
    if identity.is_empty() {
        for folder in names(game)? {
            h.update(format!("{folder}\n"));
            let path = game.join(&folder);
            if path.is_dir() {
                for file in names(&path)? {
                    h.update(format!("{folder}/{file}\n"));
                }
            }
        }
    }
    for (folder, file) in &files {
        let path = own.join(folder).join(file);
        h.update(format!("own {folder}/{file}\n"));
        h.update(fs::read(&path).map_err(|e| io(&path, e))?);
    }
    let key = cache::hex(&h.finalize());
    let game_name = game
        .file_name()
        .map(|s| s.to_string_lossy().into_owned())
        .unwrap_or_default();
    let target = into.join(format!("{game_name}-{}", &key[..16]));

    // Which of the game's each one replaces, and the check against the
    // RTP: done every time, the RTP is not in the key.
    let mut result = OwnFiles {
        directory: target.clone(),
        ..OwnFiles::default()
    };
    let mut hidden: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
    for (folder, file) in &files {
        let ours = format!("{folder}/{file}");
        let theirs: Vec<String> = match entry_like(game, folder) {
            Some(their_folder) => names(&game.join(&their_folder))?
                .into_iter()
                .filter(|n| stem(n) == stem(file))
                .map(|n| {
                    hidden
                        .entry(their_folder.clone())
                        .or_default()
                        .insert(n.clone());
                    format!("{their_folder}/{n}")
                })
                .collect(),
            None => Vec::new(),
        };
        if !theirs.is_empty() {
            result.replaced.insert(ours, theirs);
            continue;
        }
        if let Some(rtp) = rtp {
            let in_rtp = entry_like(rtp, folder).is_some_and(|f| {
                names(&rtp.join(f)).is_ok_and(|n| n.iter().any(|n| stem(n) == stem(file)))
            });
            if !in_rtp {
                return Err(Error(format!(
                    "{}: neither the game nor the RTP has a {folder}/ file with that name, so it \
                     would replace nothing",
                    own.join(folder).join(file).display()
                )));
            }
        }
        result.over_rtp.push(ours);
    }
    if target.is_dir() {
        return Ok(result);
    }

    let fail = |e: std::io::Error, p: &Path| io(p, e);
    fs::create_dir_all(into).map_err(|e| fail(e, into))?;
    let nanos = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(0);
    let aside = into.join(format!(".{game_name}.tmp-{}-{nanos}", std::process::id()));
    let _ = fs::remove_dir_all(&aside);
    let built = build(game, own, &files, &hidden, &aside, &result);
    if let Err(e) = built {
        let _ = fs::remove_dir_all(&aside);
        return Err(e);
    }
    // Another process may have finished first: then its copy stays, which
    // is the same one.
    if fs::rename(&aside, &target).is_err() {
        let _ = fs::remove_dir_all(&aside);
        if !target.is_dir() {
            return Err(Error(format!(
                "{}: could not build the game with the port's files in it",
                target.display()
            )));
        }
    }
    Ok(result)
}

/// A link to `from` at `to`, or a copy where links can not be made.
fn link(from: &Path, to: &Path) -> Result<(), Error> {
    #[cfg(unix)]
    if std::os::unix::fs::symlink(from, to).is_ok() {
        return Ok(());
    }
    if from.is_dir() {
        fs::create_dir_all(to).map_err(|e| io(to, e))?;
        for name in names(from)? {
            link(&from.join(&name), &to.join(&name))?;
        }
        return Ok(());
    }
    fs::copy(from, to).map(|_| ()).map_err(|e| io(to, e))
}

fn build(
    game: &Path,
    own: &Path,
    files: &[(String, String)],
    hidden: &BTreeMap<String, BTreeSet<String>>,
    aside: &Path,
    result: &OwnFiles,
) -> Result<(), Error> {
    fs::create_dir_all(aside).map_err(|e| io(aside, e))?;
    // The folders ours go into, with the game's spelling if it has them.
    let mut touched: BTreeMap<String, String> = BTreeMap::new();
    for (folder, _) in files {
        let theirs = entry_like(game, folder).unwrap_or_else(|| folder.clone());
        touched.insert(folder.to_lowercase(), theirs);
    }
    for name in names(game)? {
        if touched.contains_key(&name.to_lowercase()) {
            continue;
        }
        link(&game.join(&name), &aside.join(&name))?;
    }
    for folder in touched.values() {
        let dir = aside.join(folder);
        fs::create_dir_all(&dir).map_err(|e| io(&dir, e))?;
        let theirs = game.join(folder);
        if theirs.is_dir() {
            let skip = hidden.get(folder);
            for name in names(&theirs)? {
                if skip.is_some_and(|s| s.contains(&name)) {
                    continue;
                }
                link(&theirs.join(&name), &dir.join(&name))?;
            }
        }
    }
    // Ours are copied, not linked: the directory is named by their content,
    // and a link would let an edit reach a directory named by the old one.
    for (folder, file) in files {
        let into = aside.join(&touched[&folder.to_lowercase()]).join(file);
        let from = own.join(folder).join(file);
        fs::copy(&from, &into).map_err(|e| io(&into, e))?;
    }
    let record = aside.join(RECORD);
    let text = serde_json::to_string_pretty(&result.to_json()).expect("JSON always serializes");
    fs::write(&record, text).map_err(|e| io(&record, e))
}
