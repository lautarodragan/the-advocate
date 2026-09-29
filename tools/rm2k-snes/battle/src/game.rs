//! The game, as much of it as the battle tables read.
//!
//! It comes from a Ditto dump, in its **resolved view**: every field is
//! written with its default already applied, so a missing one means the
//! dump is broken and not that it is zero. Only what these tables use is
//! read —four numbers and six curves per actor, and the encounters of each
//! node of the tree—, into types of their own.
//!
//! **This is a stand-in.** The model of the format belongs to Ditto, and
//! once Ditto is a library its structs replace these; until then, copying
//! its whole model here would be a second reader to keep in step. So this
//! reads what it needs and nothing else.

use crate::fail::{Bad, Result};
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::Path;

/// The six parameter curves of an actor, in the format's order.
pub const CURVES: [&str; 6] = ["maxhp", "maxsp", "attack", "defense", "spirit", "agility"];

/// What the experience and level tables read of an actor.
#[derive(Debug, Clone)]
pub struct Actor {
    /// The level it starts at. A zero in the dump reads as 1, the way
    /// RM2k's editor never stores it.
    pub initial_level: i64,
    pub final_level: i64,
    /// The three numbers of RM2k's experience curve.
    pub exp_base: i64,
    pub exp_inflation: i64,
    pub exp_correction: i64,
    /// Each parameter per level, from level 1, in the order of [`CURVES`].
    pub params: [Vec<i64>; 6],
}

/// What the encounters read of a node of the map tree.
#[derive(Debug, Clone)]
pub struct Node {
    /// 0 the root, 1 a map, 2 an area: a rectangle of its parent map with
    /// encounters of its own.
    pub kind: i64,
    pub parent: i64,
    /// Every how many steps, on average, an encounter comes; 0 is never.
    pub encounter_steps: i64,
    /// The troops, by RM2k number, in the order of their ids.
    pub troops: Vec<i64>,
    /// Left, top, right, bottom: what an area covers.
    pub rect: [i64; 4],
}

/// The node type that is an area.
pub const AREA: i64 = 2;

/// The actors and the tree, by RM2k number.
#[derive(Debug, Clone, Default)]
pub struct Game {
    pub actors: BTreeMap<i64, Actor>,
    pub tree: BTreeMap<i64, Node>,
}

pub(crate) fn read_json(path: &Path) -> Result<Value> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{}: {e}", path.display())))
}

pub(crate) fn field<'a>(data: &'a Value, name: &str, whose: &str) -> Result<&'a Value> {
    data.get(name)
        .ok_or_else(|| Bad::answer(format!("{whose}: no `{name}`")))
}

pub(crate) fn number(data: &Value, name: &str, whose: &str) -> Result<i64> {
    field(data, name, whose)?
        .as_i64()
        .ok_or_else(|| Bad::answer(format!("{whose}: `{name}` is not a whole number")))
}

pub(crate) fn list<'a>(data: &'a Value, name: &str, whose: &str) -> Result<&'a Vec<Value>> {
    field(data, name, whose)?
        .as_array()
        .ok_or_else(|| Bad::answer(format!("{whose}: `{name}` is not a list")))
}

/// A list of whole numbers; `null` reads as empty.
fn numbers(data: &Value, name: &str, whose: &str) -> Result<Vec<i64>> {
    let value = field(data, name, whose)?;
    if value.is_null() {
        return Ok(Vec::new());
    }
    let bad = || Bad::answer(format!("{whose}: `{name}` is not a list of whole numbers"));
    value
        .as_array()
        .ok_or_else(bad)?
        .iter()
        .map(|v| v.as_i64().ok_or_else(bad))
        .collect()
}

/// An actor of `db/actors.json`.
pub fn actor(data: &Value, whose: &str) -> Result<Actor> {
    let parameters = field(data, "parameters", whose)?;
    let whose_params = format!("{whose}: parameters");
    let mut params: [Vec<i64>; 6] = Default::default();
    for (curve, values) in CURVES.iter().zip(params.iter_mut()) {
        *values = numbers(parameters, curve, &whose_params)?;
    }
    let initial_level = number(data, "initial_level", whose)?;
    Ok(Actor {
        initial_level: if initial_level == 0 { 1 } else { initial_level },
        final_level: number(data, "final_level", whose)?,
        exp_base: number(data, "exp_base", whose)?,
        exp_inflation: number(data, "exp_inflation", whose)?,
        exp_correction: number(data, "exp_correction", whose)?,
        params,
    })
}

/// A node of `maps.json`, the tree.
pub fn node(data: &Value, whose: &str) -> Result<Node> {
    let mut encounters = Vec::new();
    for e in list(data, "encounters", whose)? {
        let whose = format!("{whose}: an encounter");
        encounters.push((number(e, "id", &whose)?, number(e, "troop_id", &whose)?));
    }
    encounters.sort_by_key(|&(id, _)| id);
    let rect = field(data, "area_rect", whose)?;
    let whose_rect = format!("{whose}: area_rect");
    Ok(Node {
        kind: number(data, "type", whose)?,
        parent: number(data, "parent_map", whose)?,
        encounter_steps: number(data, "encounter_steps", whose)?,
        troops: encounters.into_iter().map(|(_, troop)| troop).collect(),
        rect: [
            number(rect, "l", &whose_rect)?,
            number(rect, "t", &whose_rect)?,
            number(rect, "r", &whose_rect)?,
            number(rect, "b", &whose_rect)?,
        ],
    })
}

impl Game {
    /// The actors of `db/actors.json` and the tree of `maps.json`, from the
    /// dump in `data`.
    pub fn from_dump(data: &Path) -> Result<Game> {
        let mut game = Game::default();
        let path = data.join("db").join("actors.json");
        let whose = path.display().to_string();
        let actors = read_json(&path)?;
        for a in actors
            .as_array()
            .ok_or_else(|| Bad::answer(format!("{whose}: not a list")))?
        {
            let id = number(a, "id", &whose)?;
            game.actors
                .insert(id, actor(a, &format!("{whose}: actor {id}"))?);
        }
        let path = data.join("maps.json");
        let whose = path.display().to_string();
        for n in list(&read_json(&path)?, "maps", &whose)? {
            game.add_node(n, &whose)?;
        }
        Ok(game)
    }

    /// A tree node in the dump's shape, over the one with its id if there
    /// is one. It is how a project adds a map the game does not have.
    pub fn add_node(&mut self, data: &Value, whose: &str) -> Result<()> {
        let id = number(data, "id", whose)?;
        self.tree
            .insert(id, node(data, &format!("{whose}: node {id}"))?);
        Ok(())
    }
}
