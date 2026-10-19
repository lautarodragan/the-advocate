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
//!   an error. Both live in `maps/`, as in Ditto's `data/maps/`, and the
//!   id tells them apart: from [`FIRST_NEW_MAP`] on, a new map.
//!
//! The ChipSets are **added**, never replace one: an id the database
//! already has is refused when the database is read, because a fork that
//! overwrites an entry goes stale without warning the day the dump changes.
//! Their records go in `ChipSet/NNNN.json`, beside the images that replace
//! the game's: one folder per kind of asset.
//!
//! **A common event is the other way round: it replaces one the game has**
//! —`commonevents/NNNN.json`, the whole record as Ditto dumps it, the id
//! inside the name's—, because what a port redoes is a menu or a loop the
//! game already calls by its number, and a new one nothing would call.
//! Every stage reads the common events from the dump on its own —the event
//! compiler, Wally, the screens, the music—, so instead of telling each of
//! them, the converter hands them all a dump with ours in place: see
//! [`with_common_events`]. Frozen World's B menu was the first, on
//! 2026-10-19.
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
    /// `{common event: (file, its record)}` of the game's common events the
    /// project redid.
    pub common_events: BTreeMap<i32, (PathBuf, Value)>,
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
    /// The patches under `manual`, checked against the maps and the common
    /// events of the game's dump, `game_maps` and `game_commons`, by number.
    pub fn read(
        manual: &Path,
        game_maps: &BTreeSet<i32>,
        game_commons: &BTreeSet<i32>,
    ) -> Result<Forks> {
        let (maps, new_maps) = maps(&manual.join("maps"), game_maps)?;
        Ok(Forks {
            maps,
            new_maps,
            chipsets: chipsets(manual)?,
            common_events: common_events(&manual.join("commonevents"), game_commons)?,
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

/// The first id of a map the game does not have. RM2k numbers maps up to
/// 9999, and no game we know of goes near a thousand.
pub const FIRST_NEW_MAP: i32 = 1000;

/// The maps of `folder`, the patches' `maps/`, as `(forks, new maps)`.
///
/// Both kinds share the folder, as in Ditto's `data/maps/`, and **the id
/// tells them apart**: from [`FIRST_NEW_MAP`] on it is a new map, which
/// brings its node of the tree because the game has none for it; below, a
/// fork, which replaces one of the game's and keeps its node. So a fork has
/// to name a map the game has, and a new map one it does not: either way a
/// mistyped number stops the build instead of passing in silence. What
/// `forks/` and `new/` guarded, until 2026-10-19, with two folders.
#[allow(clippy::type_complexity)]
fn maps(
    folder: &Path,
    game_maps: &BTreeSet<i32>,
) -> Result<(
    BTreeMap<i32, (PathBuf, PathBuf)>,
    BTreeMap<i32, (PathBuf, PathBuf, Value)>,
)> {
    let mut forks = BTreeMap::new();
    let mut new = BTreeMap::new();
    if !folder.is_dir() {
        return Ok((forks, new));
    }
    for entry in entries(folder)? {
        let (base, extension) = split(&entry);
        if !map_file(folder, base, extension) {
            crate::stop!(
                "{entry}: only a map's JSON and its layers go in the manual patches' maps/"
            );
        }
        let Some(map_id) = map_number(base) else {
            crate::stop!("{entry}: the name has to be MapNNNN");
        };
        if forks.contains_key(&map_id) || new.contains_key(&map_id) {
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
                "map {map_id} of the manual patches is incomplete: {} is missing. The layers \
                 live outside the JSON, so half a piece leaves the build with the layers of one \
                 map and the events of another",
                missing.join(", ")
            );
        }
        let data = read_json(&pair.0)?;
        let inside = data.get("id").cloned().unwrap_or(Value::Null);
        if inside.as_i64() != Some(map_id as i64) {
            crate::stop!(
                "{entry} says inside that it is map {inside}: the id and the file name have to \
                 be the same, because the pipeline picks the map by the name and the teleports \
                 by the id"
            );
        }
        if map_id < FIRST_NEW_MAP {
            if !game_maps.contains(&map_id) {
                crate::stop!(
                    "{entry} replaces map {map_id} and the dump has none: below \
                     {FIRST_NEW_MAP} a map of the manual patches replaces one of the game's; a \
                     map the game does not have takes an id from {FIRST_NEW_MAP} on"
                );
            }
            if data.get("tree").is_some() {
                crate::stop!(
                    "{entry} replaces map {map_id} of the game and brings a `tree` node, which \
                     would be ignored: the game's node is kept. Only a new map, from \
                     {FIRST_NEW_MAP} on, brings one"
                );
            }
            forks.insert(map_id, pair);
            continue;
        }
        if game_maps.contains(&map_id) {
            crate::stop!(
                "the new map {map_id} already exists in the dump: a new map does not overwrite \
                 one of the game's"
            );
        }
        let Some(node) = data.get("tree").cloned() else {
            crate::stop!(
                "{entry}: a new map brings its node of the tree in its `tree` field, with its \
                 name, its parent and its music, because the game has none for it"
            );
        };
        let empty = match &node {
            Value::Null => true,
            Value::Object(o) => o.is_empty(),
            _ => false,
        };
        if empty || node.get("id").and_then(Value::as_i64) != Some(map_id as i64) {
            crate::stop!(
                "{entry}: the id inside, the one in the `tree` node and the one in the file \
                 name have to be the same"
            );
        }
        new.insert(map_id, (pair.0, pair.1, node));
    }
    Ok((forks, new))
}

/// The entry of `directory` named `name` without regard to case, as RM2k
/// looks its folders up.
fn entry_like(directory: &Path, name: &str) -> Option<PathBuf> {
    let found = entries(directory).ok()?;
    found
        .into_iter()
        .find(|n| n.eq_ignore_ascii_case(name))
        .map(|n| directory.join(n))
}

/// The ChipSets the project adds: the records of `ChipSet/` —its
/// `NNNN.json`, see `is_record` in `rm2k-project`—. The rest of the folder
/// is images, which replace the game's: see `own_files` there.
///
/// **A record's image and a hand-made one never share a name.** The recipe
/// builds its image after the game is merged with ours, and the built ones
/// go first in the search, so it would cover the hand-made one without a
/// word: one of the two is a mistake. The converter also refuses a name
/// the game or the RTP has, when it builds the images (`build_images`), but
/// this one is said here, where both files are.
///
/// And **only `ChipSet/` takes records** today: a `NNNN.json` in another
/// of RM2k's folders is not a file of the game either, and nothing would
/// read it.
fn chipsets(manual: &Path) -> Result<BTreeMap<i32, (PathBuf, Value)>> {
    let mut added = BTreeMap::new();
    if !manual.is_dir() {
        return Ok(added);
    }
    for folder in entries(manual)? {
        let is_rm2k = rm2k_project::own_files::FOLDERS
            .iter()
            .any(|f| f.eq_ignore_ascii_case(&folder));
        if !is_rm2k || folder.eq_ignore_ascii_case("ChipSet") || !manual.join(&folder).is_dir() {
            continue;
        }
        if let Some(record) = entries(&manual.join(&folder))?
            .into_iter()
            .find(|e| rm2k_project::own_files::is_record(e))
        {
            crate::stop!(
                "{folder}/{record}: only ChipSet/ takes database records in the manual patches; \
                 nothing reads one in {folder}/"
            );
        }
    }
    let Some(folder) = entry_like(manual, "ChipSet").filter(|f| f.is_dir()) else {
        return Ok(added);
    };
    let listing = entries(&folder)?;
    let images: Vec<&String> = listing
        .iter()
        .filter(|e| !rm2k_project::own_files::is_record(e))
        .collect();
    for entry in &listing {
        if !rm2k_project::own_files::is_record(entry) {
            continue;
        }
        let (base, _) = split(entry);
        let number: i32 = base
            .parse()
            .map_err(|_| Stop::new(format!("{entry}: not a number")))?;
        let path = folder.join(entry);
        let data = read_json(&path)?;
        let inside = data["chipset"]["id"].as_i64().unwrap_or(-1);
        if inside != number as i64 {
            crate::stop!(
                "{entry} says inside that it is ChipSet {inside}: the id and the file name have \
                 to be the same"
            );
        }
        let name = data["chipset"]["chipset_name"].as_str().unwrap_or("");
        if let Some(image) = images
            .iter()
            .find(|i| split(i).0.eq_ignore_ascii_case(name))
        {
            crate::stop!(
                "{entry} builds ChipSet {} with its recipe, and ChipSet/{image} is a hand-made \
                 image with that name: the built one would cover it without a word. One of the \
                 two takes another name",
                crate::text::repr(name)
            );
        }
        added.insert(number, (path, data));
    }
    Ok(added)
}

fn common_events(
    folder: &Path,
    game_commons: &BTreeSet<i32>,
) -> Result<BTreeMap<i32, (PathBuf, Value)>> {
    let mut found = BTreeMap::new();
    if !folder.is_dir() {
        return Ok(found);
    }
    for entry in entries(folder)? {
        let (base, extension) = split(&entry);
        if extension != ".json" || base.is_empty() || !base.bytes().all(|b| b.is_ascii_digit()) {
            crate::stop!("{entry}: the manual patches' commonevents/ takes NNNN.json");
        }
        let number: i32 = base
            .parse()
            .map_err(|_| Stop::new(format!("{entry}: not a number")))?;
        let path = folder.join(&entry);
        let data = read_json(&path)?;
        let inside = data["id"].as_i64().unwrap_or(-1);
        if inside != number as i64 {
            crate::stop!(
                "{entry} says inside that it is common event {inside}: the id and the file name \
                 have to be the same, because the events call it by its number"
            );
        }
        if !game_commons.contains(&number) {
            crate::stop!(
                "{entry}: the game has no common event {number}, and the manual patches replace \
                 one, they do not add one: nothing would call it"
            );
        }
        found.insert(number, (path, data));
    }
    Ok(found)
}

/// The dump at `dump` with the project's common events in place of the
/// game's, as a directory of its own below `into`, named by what goes in
/// it: the dump's own common events and ours. The rest of it is the
/// dump's, through symbolic links, so a map or a database file is never
/// copied and never goes stale. Made once per content, and by a rename, so
/// two cartridges converted at once find the same one or make it twice and
/// keep one. `dump` itself unless the project redid some.
pub fn with_common_events(dump: &Path, forks: &Forks, into: &Path) -> Result<PathBuf> {
    if forks.common_events.is_empty() {
        return Ok(dump.to_path_buf());
    }
    let game = ditto::dump::Dump::open(dump)?;
    let mut commons: Value = game.section("commonevents")?;
    let mut parts: Vec<Vec<u8>> = vec![commons.to_string().into_bytes()];
    for (path, _) in forks.common_events.values() {
        parts.push(std::fs::read(path).map_err(|e| io(path, e))?);
    }
    let key = rm2k_project::cache::key(&parts);
    let target = into.join(format!("dump-{}", &key[..16]));
    if target.is_dir() {
        return Ok(target);
    }
    let Some(list) = commons.as_array_mut() else {
        crate::stop!("{}: its common events are not a list", dump.display());
    };
    for c in list.iter_mut() {
        let id = c["id"].as_i64().unwrap_or(-1) as i32;
        if let Some((_, ours)) = forks.common_events.get(&id) {
            *c = ours.clone();
        }
    }
    let stamp = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(0);
    let aside = into.join(format!(".dump.tmp-{}-{stamp}", std::process::id()));
    let _ = std::fs::remove_dir_all(&aside);
    game.with_section("commonevents", &commons, &aside)?;
    if std::fs::rename(&aside, &target).is_err() {
        let _ = std::fs::remove_dir_all(&aside);
        if !target.is_dir() {
            crate::stop!(
                "{}: could not make the dump with the project's common events",
                target.display()
            );
        }
    }
    Ok(target)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A manual patches folder of its own, with `maps/`, `ChipSet/` and
    /// `commonevents/`, removed when dropped.
    struct Patches(PathBuf);

    impl Patches {
        fn new(name: &str) -> Patches {
            let dir =
                std::env::temp_dir().join(format!("convert-fork-{name}-{}", std::process::id()));
            let _ = std::fs::remove_dir_all(&dir);
            for sub in ["maps", "ChipSet", "commonevents"] {
                std::fs::create_dir_all(dir.join(sub)).unwrap();
            }
            Patches(dir)
        }

        /// A map's two files in `maps/`: its JSON saying it is `inside`,
        /// with `node` as its tree node if given, and its layers.
        fn map(&self, number: i32, inside: i32, node: Option<i32>, layers: bool) {
            // The project's files, in a folder of their own: not a dump.
            let json = self
                .0
                .join("maps")
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
            Forks::read(&self.0, &BTreeSet::from([11, 12]), &BTreeSet::from([15]))
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
        p.map(11, 11, None, true);
        p.map(1000, 1000, Some(1000), true);
        let forks = p.read().unwrap();
        assert_eq!(forks.maps.keys().collect::<Vec<_>>(), [&11]);
        assert_eq!(forks.map_file(1000).unwrap().file_stem().unwrap(), "Map1000");
        assert_eq!(forks.new_maps[&1000].2["name"], "x");
    }

    #[test]
    fn half_a_fork_does_not_build_from_either_side() {
        let p = Patches::new("half");
        p.map(11, 11, None, false);
        assert!(refusal(p.read()).contains("incomplete"));
        let p = Patches::new("layers");
        std::fs::write(
            layers_path(&p.0.join("maps").join("Map0011").with_extension("json")),
            "0\n",
        )
        .unwrap();
        assert!(refusal(p.read()).contains("incomplete"));
    }

    #[test]
    fn a_fork_that_says_it_is_another_map_does_not_build() {
        let p = Patches::new("other");
        p.map(11, 12, None, true);
        assert!(refusal(p.read()).contains("map 12"));
    }

    #[test]
    fn below_a_thousand_replacing_a_map_the_game_lacks_does_not_build() {
        // Even if it brings a node, as a new map would: the id says which
        // it is, so a new map with a mistyped id does not pass for one.
        let p = Patches::new("lacks");
        p.map(13, 13, None, true);
        assert!(refusal(p.read()).contains("the dump has none"));
        let p = Patches::new("lacks-node");
        p.map(999, 999, Some(999), true);
        assert!(refusal(p.read()).contains("the dump has none"));
    }

    #[test]
    fn a_fork_does_not_bring_a_node_of_the_tree() {
        let p = Patches::new("fork-node");
        p.map(11, 11, Some(11), true);
        assert!(refusal(p.read()).contains("would be ignored"));
    }

    #[test]
    fn from_a_thousand_a_new_map_does_not_cover_one_of_the_game() {
        // A game with a map from a thousand on: no game we know of, but the
        // rule has to hold.
        let p = Patches::new("covers");
        p.map(1001, 1001, Some(1001), true);
        let refused = Forks::read(&p.0, &BTreeSet::from([11, 1001]), &BTreeSet::new());
        assert!(refusal(refused).contains("already exists"));
    }

    #[test]
    fn a_new_map_brings_its_node_with_its_id_and_both_files() {
        let p = Patches::new("node");
        p.map(9998, 9998, Some(9997), true);
        assert!(refusal(p.read()).contains("`tree`"));
        let p = Patches::new("no-node");
        p.map(9998, 9998, None, true);
        assert!(refusal(p.read()).contains("`tree` field"));
        let p = Patches::new("newhalf");
        p.map(9998, 9998, Some(9998), false);
        assert!(refusal(p.read()).contains("incomplete"));
    }

    #[test]
    fn a_chipset_says_inside_the_number_of_its_name() {
        let p = Patches::new("chipset");
        std::fs::write(
            p.0.join("ChipSet").join("0053.json"),
            r#"{"chipset": {"id": 54}}"#,
        )
        .unwrap();
        assert!(refusal(p.read()).contains("ChipSet 54"));
    }

    #[test]
    fn a_chipset_record_and_a_hand_made_image_do_not_share_a_name() {
        let p = Patches::new("chipset-image");
        let folder = p.0.join("ChipSet");
        std::fs::write(
            folder.join("0053.json"),
            r#"{"chipset": {"id": 53, "chipset_name": "LasheINT11"}}"#,
        )
        .unwrap();
        // An image of another name beside it replaces the game's, and is
        // not a record.
        std::fs::write(folder.join("Other.png"), "png").unwrap();
        assert_eq!(
            p.read().unwrap().chipsets.keys().collect::<Vec<_>>(),
            [&53]
        );
        // Without regard to case or extension, as RM2k looks it up.
        std::fs::write(folder.join("lasheint11.bmp"), "bmp").unwrap();
        assert!(refusal(p.read()).contains("hand-made image"));
    }

    #[test]
    fn only_chipset_takes_records() {
        let p = Patches::new("records");
        std::fs::create_dir_all(p.0.join("Picture")).unwrap();
        std::fs::write(p.0.join("Picture").join("0001.json"), "{}").unwrap();
        assert!(refusal(p.read()).contains("only ChipSet/"));
    }

    #[test]
    fn a_common_event_replaces_one_of_the_game_with_its_id_inside() {
        let p = Patches::new("common");
        let folder = p.0.join("commonevents");
        std::fs::write(folder.join("0015.json"), r#"{"id": 16}"#).unwrap();
        assert!(refusal(p.read()).contains("common event 16"));
        std::fs::write(folder.join("0015.json"), r#"{"id": 15}"#).unwrap();
        assert_eq!(
            p.read().unwrap().common_events.keys().collect::<Vec<_>>(),
            [&15]
        );
        std::fs::write(folder.join("0099.json"), r#"{"id": 99}"#).unwrap();
        assert!(refusal(p.read()).contains("no common event 99"));
    }
}
