//! The game, as much of it as the battle tables read: the actors and the
//! map tree.
//!
//! It comes from a Ditto dump, read with Ditto's own reader into the
//! schema's types —`ditto::schema::Actor` and `MapInfo`—, so there is no
//! model of the format here. Of the database only `actors` is read: the
//! other sections are not parsed.

use crate::fail::{Bad, Result};
use ditto::dump::Dump;
use ditto::schema::{Actor, MapInfo};
use rm2k_rules::tree::Tree;
use std::collections::BTreeMap;
use std::path::Path;

/// The actors, by RM2k number, and the tree.
#[derive(Debug, Clone, Default)]
pub struct Game {
    pub actors: BTreeMap<i64, Actor>,
    pub tree: Tree,
}

impl Game {
    /// The actors and the tree of the dump in `data`.
    pub fn from_dump(data: &Path) -> Result<Game> {
        let answer = |e: ditto::lcf::Error| Bad::answer(e.0);
        let dump = Dump::open(data).map_err(answer)?;
        let actors: Vec<Actor> = dump.section("actors").map_err(answer)?;
        Ok(Game {
            actors: actors.into_iter().map(|a| (a.id as i64, a)).collect(),
            tree: Tree::from(&dump.tree().map_err(answer)?),
        })
    }

    /// A tree node, over the one with its number if there is one. It is how
    /// a project adds a map the game does not have.
    pub fn add_node(&mut self, node: MapInfo) {
        self.tree.insert(node);
    }
}
