//! The game, as much of it as a map's conversion reads: the map and its
//! ChipSet, and where the pictures are.
//!
//! It comes from a Ditto dump, read with Ditto's own reader into the
//! schema's types, so there is no model of the format here. What the
//! project changed on top of the dump arrives as files of the same shape
//! —a map of its own, a ChipSet it adds— and is read the same way.

use crate::fail::{Bad, Result};
use ditto::dump::{read_map, Dump};
use ditto::schema::{Chipset, Map};
use rm2k_render::source::find_resource;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// Where the game is, and what the project puts over it.
#[derive(Debug, Clone, Default)]
pub struct Game {
    /// The Ditto dump.
    pub data: PathBuf,
    /// Maps read from the project's files and not from the dump: forks of
    /// the game's, and maps the game does not have. By map number.
    pub map_files: BTreeMap<i32, PathBuf>,
    /// ChipSets the project adds to the database, each a file with the
    /// entry under `chipset`. They are added, never replace one: an id the
    /// dump already has is refused.
    pub chipset_files: BTreeMap<i32, PathBuf>,
    /// The events each map leaves out because they do not fit in the
    /// console's RAM, by map and id: the caller decides them, and the map
    /// is read without them so the indices are the caller's.
    pub dropped: BTreeMap<i32, BTreeSet<i32>>,
    /// Where the pictures are looked up, in order: the first directory that
    /// has one wins.
    pub search_dirs: Vec<PathBuf>,
    /// The request's map's `ShowPicture` pictures that are part of it: see
    /// [`crate::map_pictures`]. The caller decides them.
    pub map_pictures: Vec<crate::map_pictures::MapPicture>,
}

fn answer(e: ditto::lcf::Error) -> Bad {
    Bad::answer(e.0)
}

impl Game {
    /// Map `id`: the project's file if it has one, the dump's otherwise.
    pub fn map(&self, id: i32) -> Result<Map> {
        let mut map = match self.map_files.get(&id) {
            Some(path) => read_map(path),
            None => Dump::open(&self.data).and_then(|d| d.map(id as u32)),
        }
        .map_err(answer)?;
        if let Some(dropped) = self.dropped.get(&id) {
            map.events.retain(|e| !dropped.contains(&e.id));
        }
        Ok(map)
    }

    /// ChipSet `id` of the database, or one the project adds.
    pub fn chipset(&self, id: i32) -> Result<Chipset> {
        let dump = Dump::open(&self.data).map_err(answer)?;
        let chipsets: Vec<Chipset> = dump.section("chipsets").map_err(answer)?;
        let found = chipsets.into_iter().find(|c| c.id == id);
        match (found, self.chipset_files.get(&id)) {
            (Some(_), Some(path)) => Err(Bad::answer(format!(
                "{}: ChipSet {id} is already in the dump, and the project adds ChipSets, it \
                 does not replace them",
                path.display()
            ))),
            (Some(chipset), None) => Ok(chipset),
            (None, Some(path)) => added_chipset(path),
            (None, None) => Err(Bad::answer(format!(
                "ChipSet {id} is neither in the dump nor added by the project"
            ))),
        }
    }

    /// The CharSet each actor is drawn with: `(character_name,
    /// character_index)`, by actor number.
    pub fn actors(&self) -> Result<std::collections::HashMap<i32, (String, i32)>> {
        let dump = Dump::open(&self.data).map_err(answer)?;
        let actors: Vec<ditto::schema::Actor> = dump.section("actors").map_err(answer)?;
        Ok(actors
            .into_iter()
            .map(|a| (a.id, (a.character_name, a.character_index)))
            .collect())
    }

    /// Every command of the common events, as `(code, parameters)`: a
    /// `CallEvent` can bring any of them into any map.
    pub fn common_commands(&self) -> Result<Vec<(i32, Vec<i32>)>> {
        let dump = Dump::open(&self.data).map_err(answer)?;
        let common: Vec<ditto::schema::CommonEvent> = dump.section("commonevents").map_err(answer)?;
        Ok(common
            .iter()
            .flat_map(|c| c.event_commands.iter().map(|e| (e.code.to_i32(), e.parameters.clone())))
            .collect())
    }

    /// Where a new game starts: `(map, x, y)`.
    pub fn start(&self) -> Result<(i32, i32, i32)> {
        let dump = Dump::open(&self.data).map_err(answer)?;
        let tree = dump.tree().map_err(answer)?;
        Ok((tree.start.party_map_id, tree.start.party_x, tree.start.party_y))
    }

    /// The picture file of a resource, looked up by name in every search
    /// directory, without regard to case.
    pub fn resource(&self, folder: &str, name: &str) -> Option<PathBuf> {
        find_resource(&self.search_dirs, folder, name)
    }
}

fn added_chipset(path: &Path) -> Result<Chipset> {
    let whose = path.display().to_string();
    let text = std::fs::read_to_string(path).map_err(|e| Bad::usage(format!("{whose}: {e}")))?;
    let mut data: serde_json::Value =
        serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{whose}: {e}")))?;
    let entry = data
        .as_object_mut()
        .and_then(|o| o.remove("chipset"))
        .ok_or_else(|| Bad::answer(format!("{whose}: no `chipset`")))?;
    serde_json::from_value(entry).map_err(|e| Bad::answer(format!("{whose}: {e}")))
}
