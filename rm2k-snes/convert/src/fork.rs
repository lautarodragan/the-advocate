//! The project's manual patches: what is the project's and overrides the
//! dump —a map of the game redone, a map the game does not have, a ChipSet
//! added to the database—. Each is the whole file, not a description of
//! changes; the project file says where they are (`manual_patches`).
//!
//! Three things are enforced here, and all three are the same fear:
//!
//! * **a forked map is all or nothing.** Its layers live outside the JSON,
//!   so a `MapNNNN.json` without its `MapNNNN.tiles` would leave the build
//!   with the old layers and the new events, which looks fine until it
//!   does not;
//! * **the id inside is the one in the name.** A misnamed fork does not
//!   fail: it overwrites the wrong map, and the teleports land in a wall;
//! * **a fork replaces a map that exists**, and a new map **cannot**
//!   overwrite one: a misspelled name doing nothing silently is worse than
//!   an error. That is why the two live in different folders, `forks/` and
//!   `new/`.
//!
//! The ChipSets are **added**, never replace one: an id the database
//! already has is refused when the database is read, because a fork that
//! overwrites an entry goes stale without warning the day the dump changes.
//!
//! None of this touches the dump. It is read only for this project's own
//! dump: another game is read by passing it its own.

use crate::fail::{io, Result, Stop};
use ditto::dump::layers_path;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// What the project puts over its game's dump, validated.
#[derive(Debug, Clone, Default)]
pub struct Forks {
    /// `{map: (json, tiles)}` of the game's maps the project redid.
    pub maps: BTreeMap<i32, (PathBuf, PathBuf)>,
    /// `{map: (json, tiles, node)}` of the maps the game does not have,
    /// with their node of the tree, in the dump's shape.
    pub new_maps: BTreeMap<i32, (PathBuf, PathBuf, Value)>,
    /// `{chipset: (file, its entry)}` of the ChipSets the project adds.
    pub chipsets: BTreeMap<i32, (PathBuf, Value)>,
}

fn entries(dir: &Path) -> Result<Vec<String>> {
    let mut names: Vec<String> = std::fs::read_dir(dir)
        .map_err(|e| io(dir, e))?
        .flatten()
        .map(|e| e.file_name().to_string_lossy().to_string())
        .collect();
    names.sort();
    Ok(names)
}

fn read_json(path: &Path) -> Result<Value> {
    let text = std::fs::read_to_string(path).map_err(|e| io(path, e))?;
    serde_json::from_str(&text).map_err(|e| Stop::new(format!("{}: {e}", path.display())))
}

/// `name` split into its stem and its extension, as `os.path.splitext`.
fn split(name: &str) -> (&str, &str) {
    match name.rfind('.') {
        Some(at) if at > 0 => (&name[..at], &name[at..]),
        _ => (name, ""),
    }
}

/// Whether a file of a map folder is one of a map's two: its JSON, or its
/// layers beside it, where Ditto keeps them.
fn map_file(folder: &Path, base: &str, extension: &str) -> bool {
    let json = folder.join(format!("{base}.json"));
    extension == ".json" || layers_path(&json) == folder.join(format!("{base}{extension}"))
}

/// The map number of a `MapNNNN` stem, or None.
fn map_number(stem: &str) -> Option<i32> {
    let digits = stem.strip_prefix("Map")?;
    if digits.is_empty() || !digits.bytes().all(|b| b.is_ascii_digit()) {
        return None;
    }
    digits.parse().ok()
}

impl Forks {
    /// The patches under `manual`, checked against the maps of the game's
    /// dump, `game_maps`, by number.
    pub fn read(manual: &Path, game_maps: &BTreeSet<i32>) -> Result<Forks> {
        Ok(Forks {
            maps: maps(&manual.join("forks"), game_maps)?,
            new_maps: new_maps(&manual.join("new"), game_maps)?,
            chipsets: chipsets(&manual.join("chipsets"))?,
        })
    }

    /// The JSON a map is read from, if the project has its own: a fork of
    /// one of the game's or one the game does not have.
    pub fn map_file(&self, id: i32) -> Option<&Path> {
        self.maps
            .get(&id)
            .map(|p| p.0.as_path())
            .or_else(|| self.new_maps.get(&id).map(|p| p.0.as_path()))
    }

    /// `{map: file}` of every map read from the project's files.
    pub fn map_files(&self) -> BTreeMap<i32, PathBuf> {
        let mut out: BTreeMap<i32, PathBuf> =
            self.maps.iter().map(|(m, p)| (*m, p.0.clone())).collect();
        for (m, p) in &self.new_maps {
            out.insert(*m, p.0.clone());
        }
        out
    }
}

fn maps(folder: &Path, game_maps: &BTreeSet<i32>) -> Result<BTreeMap<i32, (PathBuf, PathBuf)>> {
    let mut found = BTreeMap::new();
    if !folder.is_dir() {
        return Ok(found);
    }
    for entry in entries(folder)? {
        let (base, extension) = split(&entry);
        if !map_file(folder, base, extension) {
            crate::stop!(
                "{entry}: only a map's JSON and its layers go in the manual patches' forks/"
            );
        }
        let Some(map_id) = map_number(base) else {
            crate::stop!("{entry}: the name has to be MapNNNN");
        };
        if found.contains_key(&map_id) {
            continue;
        }
        let json = folder.join(format!("{base}.json"));
        let pair = (json.clone(), layers_path(&json));
        let missing: Vec<String> = [&pair.0, &pair.1]
            .iter()
            .filter(|p| !p.is_file())
            .map(|p| p.file_name().unwrap().to_string_lossy().to_string())
            .collect();
        if !missing.is_empty() {
            crate::stop!(
                "the fork of map {map_id} is incomplete: {} is missing. The layers live outside \
                 the JSON, so half a piece leaves the build with the layers of one map and the \
                 events of another",
                missing.join(", ")
            );
        }
        if !game_maps.contains(&map_id) {
            crate::stop!(
                "the fork names map {map_id} and the dump has none: a fork replaces a map of \
                 the game, it does not add one"
            );
        }
        let inside = read_json(&pair.0)?
            .get("id")
            .cloned()
            .unwrap_or(Value::Null);
        if inside.as_i64() != Some(map_id as i64) {
            crate::stop!(
                "{entry} says inside that it is map {inside}: the id and the file name have to \
                 be the same, because the pipeline picks the map by the name and the teleports \
                 by the id"
            );
        }
        found.insert(map_id, pair);
    }
    Ok(found)
}

fn new_maps(
    folder: &Path,
    game_maps: &BTreeSet<i32>,
) -> Result<BTreeMap<i32, (PathBuf, PathBuf, Value)>> {
    let mut found = BTreeMap::new();
    if !folder.is_dir() {
        return Ok(found);
    }
    for entry in entries(folder)? {
        let (base, extension) = split(&entry);
        if !map_file(folder, base, extension) {
            crate::stop!(
                "{entry}: only a map's JSON and its layers go in the manual patches' new/"
            );
        }
        let Some(map_id) = map_number(base) else {
            crate::stop!("{entry}: the name has to be MapNNNN");
        };
        if found.contains_key(&map_id) {
            continue;
        }
        let json = folder.join(format!("{base}.json"));
        let pair = (json.clone(), layers_path(&json));
        let missing: Vec<String> = [&pair.0, &pair.1]
            .iter()
            .filter(|p| !p.is_file())
            .map(|p| p.file_name().unwrap().to_string_lossy().to_string())
            .collect();
        if !missing.is_empty() {
            crate::stop!(
                "the new map {map_id} is incomplete: {} is missing",
                missing.join(", ")
            );
        }
        if game_maps.contains(&map_id) {
            crate::stop!(
                "the new map {map_id} already exists in the dump: a new map does not overwrite \
                 one of the game's; if it is meant to change it, it is a fork and goes in \
                 the manual patches' forks/"
            );
        }
        let data = read_json(&pair.0)?;
        let node = data.get("tree").cloned().unwrap_or(Value::Null);
        let empty = match &node {
            Value::Null => true,
            Value::Object(o) => o.is_empty(),
            _ => false,
        };
        if data.get("id").and_then(Value::as_i64) != Some(map_id as i64)
            || empty
            || node.get("id").and_then(Value::as_i64) != Some(map_id as i64)
        {
            crate::stop!(
                "{entry}: the id inside, the one in the `tree` node and the one in the file \
                 name have to be the same"
            );
        }
        found.insert(map_id, (pair.0, pair.1, node));
    }
    Ok(found)
}

fn chipsets(folder: &Path) -> Result<BTreeMap<i32, (PathBuf, Value)>> {
    let mut added = BTreeMap::new();
    if !folder.is_dir() {
        return Ok(added);
    }
    for entry in entries(folder)? {
        let (base, extension) = split(&entry);
        if extension != ".json" || base.is_empty() || !base.bytes().all(|b| b.is_ascii_digit()) {
            crate::stop!("{entry}: the manual patches' chipsets/ takes NNNN.json");
        }
        let number: i32 = base
            .parse()
            .map_err(|_| Stop::new(format!("{entry}: not a number")))?;
        let path = folder.join(&entry);
        let data = read_json(&path)?;
        let inside = data["chipset"]["id"].as_i64().unwrap_or(-1);
        if inside != number as i64 {
            crate::stop!(
                "{entry} says inside that it is ChipSet {inside}: the id and the file name have \
                 to be the same"
            );
        }
        added.insert(number, (path, data));
    }
    Ok(added)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A manual patches folder of its own, with `forks/`, `new/` and
    /// `chipsets/`, removed when dropped.
    struct Patches(PathBuf);

    impl Patches {
        fn new(name: &str) -> Patches {
            let dir =
                std::env::temp_dir().join(format!("convert-fork-{name}-{}", std::process::id()));
            let _ = std::fs::remove_dir_all(&dir);
            for sub in ["forks", "new", "chipsets"] {
                std::fs::create_dir_all(dir.join(sub)).unwrap();
            }
            Patches(dir)
        }

        /// A map's two files in `folder`: its JSON saying it is `inside`,
        /// with `node` as its tree node if given, and its layers.
        fn map(&self, folder: &str, number: i32, inside: i32, node: Option<i32>, layers: bool) {
            // The project's files, in a folder of their own: not a dump.
            let json = self
                .0
                .join(folder)
                .join(format!("Map{number:04}"))
                .with_extension("json");
            let mut data = serde_json::json!({"id": inside});
            if let Some(node) = node {
                data["tree"] = serde_json::json!({"id": node, "name": "x"});
            }
            std::fs::write(&json, data.to_string()).unwrap();
            if layers {
                std::fs::write(layers_path(&json), "0\n").unwrap();
            }
        }

        fn read(&self) -> Result<Forks> {
            Forks::read(&self.0, &BTreeSet::from([11, 12]))
        }
    }

    impl Drop for Patches {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn refusal(r: Result<Forks>) -> String {
        r.expect_err("it should have refused").message
    }

    #[test]
    fn a_whole_fork_of_a_map_the_game_has_is_read() {
        let p = Patches::new("whole");
        p.map("forks", 11, 11, None, true);
        p.map("new", 900, 900, Some(900), true);
        let forks = p.read().unwrap();
        assert_eq!(forks.maps.keys().collect::<Vec<_>>(), [&11]);
        assert_eq!(forks.map_file(900).unwrap().file_stem().unwrap(), "Map0900");
        assert_eq!(forks.new_maps[&900].2["name"], "x");
    }

    #[test]
    fn half_a_fork_does_not_build_from_either_side() {
        let p = Patches::new("half");
        p.map("forks", 11, 11, None, false);
        assert!(refusal(p.read()).contains("incomplete"));
        let p = Patches::new("layers");
        std::fs::write(
            layers_path(&p.0.join("forks").join("Map0011").with_extension("json")),
            "0\n",
        )
        .unwrap();
        assert!(refusal(p.read()).contains("incomplete"));
    }

    #[test]
    fn a_fork_that_says_it_is_another_map_does_not_build() {
        let p = Patches::new("other");
        p.map("forks", 11, 12, None, true);
        assert!(refusal(p.read()).contains("map 12"));
    }

    #[test]
    fn a_fork_of_a_map_the_game_lacks_does_not_build() {
        let p = Patches::new("lacks");
        p.map("forks", 9999, 9999, None, true);
        assert!(refusal(p.read()).contains("has none"));
    }

    #[test]
    fn a_new_map_does_not_cover_one_of_the_game() {
        let p = Patches::new("covers");
        p.map("new", 11, 11, Some(11), true);
        assert!(refusal(p.read()).contains("already exists"));
    }

    #[test]
    fn a_new_map_brings_its_node_with_its_id_and_both_files() {
        let p = Patches::new("node");
        p.map("new", 9998, 9998, Some(9997), true);
        assert!(refusal(p.read()).contains("`tree`"));
        let p = Patches::new("newhalf");
        p.map("new", 9998, 9998, Some(9998), false);
        assert!(refusal(p.read()).contains("incomplete"));
    }

    #[test]
    fn a_chipset_says_inside_the_number_of_its_name() {
        let p = Patches::new("chipset");
        std::fs::write(
            p.0.join("chipsets").join("0053.json"),
            r#"{"chipset": {"id": 54}}"#,
        )
        .unwrap();
        assert!(refusal(p.read()).contains("ChipSet 54"));
    }
}
