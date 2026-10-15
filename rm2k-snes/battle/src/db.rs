//! The database, as much of it as the battle's model reads: the actors,
//! the skills, the items, the enemies, the terms, the states, the
//! attributes and, when asked for, the troops.
//!
//! It comes from a Ditto dump, read with Ditto's own reader into the
//! schema's types, so there is no model of the format here. The troops are
//! most of a database —every page of every troop, with its commands— and
//! are only read by whoever needs them.
//!
//! The lists whose order means something —an actor's learning table, an
//! enemy's actions, a troop's members and pages— are sorted by their id
//! here, which is the order RM2k walks them in, whatever order the dump
//! holds them in.

use crate::fail::{Bad, Result};
use ditto::dump::Dump;
use ditto::schema::{Actor, Attribute, Enemy, Item, Skill, State, Terms, Troop};
use std::collections::BTreeMap;
use std::path::Path;

/// `lcf::rpg::Item::Type`: the ones the battle reads, and the material, whose
/// table the converter emits next to the medicines'.
pub const ITEM_WEAPON: i32 = 1;
pub const ITEM_MEDICINE: i32 = 6;
pub const ITEM_MATERIAL: i32 = 8;

/// `lcf::rpg::Skill::Type`.
pub const SKILL_NORMAL: i32 = 0;
pub const SKILL_SWITCH: i32 = 3;

/// `lcf::rpg::Skill::Scope`. `Algo::SkillTargetsEnemies` is "enemy or
/// enemies"; everything else targets one's own side.
pub const SCOPE_ENEMY: i32 = 0;
pub const SCOPE_ENEMIES: i32 = 1;
pub const SCOPE_SELF: i32 = 2;
pub const SCOPE_ALLY: i32 = 3;
pub const SCOPE_PARTY: i32 = 4;

/// How many enemies a battle holds, which is also how many of a troop's
/// members count: a troop with more is fit to it by [`crate::fit`]. It is
/// the console's, and the converter's `ENEMIES_MAX`.
pub const ENEMIES_MAX: usize = 8;

/// What the battle reads of a game.
#[derive(Debug, Clone, Default)]
pub struct Db {
    pub actors: BTreeMap<i32, Actor>,
    pub skills: BTreeMap<i32, Skill>,
    pub items: BTreeMap<i32, Item>,
    pub enemies: BTreeMap<i32, Enemy>,
    pub troops: BTreeMap<i32, Troop>,
    pub states: BTreeMap<i32, State>,
    /// By id, which is also their order: see [`crate::attributes`].
    pub attributes: BTreeMap<i32, Attribute>,
    pub terms: Terms,
}

fn answer(e: ditto::lcf::Error) -> Bad {
    Bad::answer(e.0)
}

fn by_id<T, F: Fn(&T) -> i32>(list: Vec<T>, id: F) -> BTreeMap<i32, T> {
    list.into_iter().map(|x| (id(&x), x)).collect()
}

impl Db {
    /// The database of the dump in `data`; its troops only `with_troops`.
    pub fn from_dump(data: &Path, with_troops: bool) -> Result<Db> {
        let dump = Dump::open(data).map_err(answer)?;
        let mut actors: Vec<Actor> = dump.section("actors").map_err(answer)?;
        for a in &mut actors {
            a.skills.sort_by_key(|l| l.id);
        }
        let mut enemies: Vec<Enemy> = dump.section("enemies").map_err(answer)?;
        for e in &mut enemies {
            e.actions.sort_by_key(|a| a.id);
        }
        let troops: Vec<Troop> = if with_troops {
            let mut troops: Vec<Troop> = dump.section("troops").map_err(answer)?;
            for t in &mut troops {
                // Sorted, and cut to what a battle holds: see `fit`.
                crate::fit::fit(t);
            }
            troops
        } else {
            Vec::new()
        };
        Ok(Db {
            actors: by_id(actors, |a| a.id),
            skills: by_id(dump.section("skills").map_err(answer)?, |s: &Skill| s.id),
            items: by_id(dump.section("items").map_err(answer)?, |i: &Item| i.id),
            enemies: by_id(enemies, |e| e.id),
            troops: by_id(troops, |t| t.id),
            states: by_id(dump.section("states").map_err(answer)?, |s: &State| s.id),
            attributes: by_id(dump.section("attributes").map_err(answer)?, |a: &Attribute| a.id),
            terms: dump.section("terms").map_err(answer)?,
        })
    }

    pub fn actor(&self, id: i32) -> Result<&Actor> {
        self.actors
            .get(&id)
            .ok_or_else(|| Bad::answer(format!("there is no actor {id} in the database")))
    }

    pub fn skill(&self, id: i32) -> Result<&Skill> {
        self.skills
            .get(&id)
            .ok_or_else(|| Bad::answer(format!("there is no skill {id} in the database")))
    }

    pub fn item(&self, id: i32) -> Result<&Item> {
        self.items
            .get(&id)
            .ok_or_else(|| Bad::answer(format!("there is no item {id} in the database")))
    }

    pub fn enemy(&self, id: i32) -> Result<&Enemy> {
        self.enemies
            .get(&id)
            .ok_or_else(|| Bad::answer(format!("there is no enemy {id} in the database")))
    }

    pub fn troop(&self, id: i32) -> Result<&Troop> {
        self.troops
            .get(&id)
            .ok_or_else(|| Bad::answer(format!("there is no troop {id} in the database")))
    }

    /// A troop's members that count, in their order: up to
    /// [`ENEMIES_MAX`].
    pub fn members(&self, troop: i32) -> Result<Vec<&ditto::schema::TroopMember>> {
        Ok(self
            .troop(troop)?
            .members
            .iter()
            .take(ENEMIES_MAX)
            .collect())
    }
}

/// `Algo::SkillTargetsEnemies`.
pub fn targets_enemies(skill: &Skill) -> bool {
    matches!(skill.scope.to_i32(), SCOPE_ENEMY | SCOPE_ENEMIES)
}
