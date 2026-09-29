//! The indices of the whole game, built before compiling anything: which
//! slot each variable gets, which bit each (actor, skill) pair gets, which
//! graphics an actor can be given, and which common events are the
//! equipment ones.
//!
//! The slots come from sweeping **every map of the game** —and the troops',
//! and the common events' for the pairs—, whether their pages compile or
//! not: a cheap superset, and a page that starts compiling later shifts
//! nobody's slot, so a game saved with one cartridge loads in another.

use crate::codes::*;
use crate::compile::{
    Indices, COND_ACTOR, COND_ACTOR_EQUIPMENT, COND_ACTOR_SKILL, COND_VARIABLE, VAR_VARIABLE,
};
use crate::fail::{Bad, Result};
use crate::game::{Command, Game, Map};
use std::collections::{BTreeMap, BTreeSet};

/// The bits live in `FAR_SKILL`, which has 256 bytes in the far RAM map.
const SKILL_SLOTS_MAX: usize = 256 * 8;
/// The end of a block of commands: the empty line that closes each branch.
const BLOCK_END: i32 = END;

/// The battle's branch commands, as the map's: the two kinds the game uses
/// have their operands in the same place.
pub fn battle_branch(code: i32) -> i32 {
    match code {
        BATTLE_COND_BRANCH => COND_BRANCH,
        BATTLE_COND_ELSE => COND_ELSE,
        BATTLE_COND_END => COND_END,
        c => c,
    }
}

/// The variables these commands name.
pub fn command_variables(commands: &[Command]) -> BTreeSet<i32> {
    let mut ids = BTreeSet::new();
    for cmd in commands {
        let p = &cmd.parameters;
        let code = cmd.code;
        if code == CONTROL_VARS && p.len() >= 7 {
            if p[0] == 0 {
                ids.insert(p[1]);
            } else if p[0] == 1 {
                ids.extend(p[1]..=p[2]);
            }
            if p[4] as i64 == VAR_VARIABLE {
                ids.insert(p[5]);
            }
        } else if code == COND_BRANCH && p.len() >= 5 && p[0] as i64 == COND_VARIABLE {
            ids.insert(p[1]);
            if p[2] == 1 {
                ids.insert(p[3]);
            }
        } else if code == KEY_INPUT_PROC && !p.is_empty() {
            ids.insert(p[0]);
        } else if code == TIMER_OPERATION && p.len() >= 3 && p[0] == 0 && p[1] != 0 {
            ids.insert(p[2]);
        } else if code == CHANGE_EVENT_LOCATION && p.len() >= 4 && p[1] == 1 {
            ids.extend([p[2], p[3]]);
        } else if code == STORE_TERRAIN_ID && p.len() >= 4 {
            if p[0] == 1 {
                ids.extend([p[1], p[2]]);
            }
            ids.insert(p[3]);
        } else if matches!(code, MEMORIZE_LOCATION | RECALL_TO_LOCATION) && p.len() >= 3 {
            ids.extend(&p[..3]);
        }
    }
    ids
}

/// The (actor, skill) pairs these commands name, in the forms that
/// compile: fixed actor and constant skill.
pub fn command_skill_pairs(commands: &[Command]) -> BTreeSet<(i32, i32)> {
    let mut pairs = BTreeSet::new();
    for cmd in commands {
        let p = &cmd.parameters;
        if cmd.code == CHANGE_SKILLS && p.len() >= 5 && p[0] == 1 && p[3] == 0 {
            pairs.insert((p[1], p[4]));
        } else if cmd.code == COND_BRANCH
            && p.len() >= 4
            && p[0] as i64 == COND_ACTOR
            && p[2] as i64 == COND_ACTOR_SKILL
        {
            pairs.insert((p[1], p[3]));
        }
    }
    pairs
}

/// Every map of the game, read once.
pub fn every_map(game: &Game) -> Result<Vec<Map>> {
    game.map_ids.iter().map(|&m| game.map(m)).collect()
}

/// The troop pages' commands, with the battle's branches as the map's.
fn troop_page_commands(game: &Game) -> Vec<Vec<Command>> {
    game.troops
        .values()
        .flat_map(|pages| pages.iter())
        .map(|page| {
            page.commands
                .iter()
                .map(|c| Command {
                    code: battle_branch(c.code),
                    ..c.clone()
                })
                .collect()
        })
        .collect()
}

/// Each variable some page of the game names —its maps' and its troops'—,
/// plus `extra`, with its slot.
pub fn variables(game: &Game, maps: &[Map], extra: &BTreeSet<i32>) -> BTreeMap<i32, usize> {
    let mut ids = extra.clone();
    for map in maps {
        for event in &map.events {
            for page in &event.pages {
                if let Some((v, _)) = page.condition.variable {
                    ids.insert(v);
                }
                ids.extend(command_variables(&page.commands));
            }
        }
    }
    for pages in game.troops.values() {
        for page in pages {
            if page.condition.flags.variable {
                ids.insert(page.condition.variable_id);
            }
        }
    }
    for commands in troop_page_commands(game) {
        ids.extend(command_variables(&commands));
    }
    ids.into_iter()
        .enumerate()
        .map(|(slot, v)| (v, slot))
        .collect()
}

/// Each (actor, skill) pair the game can look at, with its bit: the ones
/// the actors learn by level, the ones some `ChangeSkills` or some "knows
/// the skill" branch names —in the maps, the common events and the
/// troops—, and `extra`. A pair naming an actor or a skill the database
/// does not have is left out.
pub fn skills(
    game: &Game,
    maps: &[Map],
    extra: &BTreeSet<(i32, i32)>,
) -> Result<BTreeMap<(i32, i32), usize>> {
    let mut pairs = extra.clone();
    for (&number, learning) in &game.actors {
        pairs.extend(
            learning
                .iter()
                .filter(|(_, s)| *s != 0)
                .map(|&(_, s)| (number, s)),
        );
    }
    for map in maps {
        for event in &map.events {
            for page in &event.pages {
                pairs.extend(command_skill_pairs(&page.commands));
            }
        }
    }
    for c in game.common_events.values() {
        pairs.extend(command_skill_pairs(&c.commands));
    }
    for commands in troop_page_commands(game) {
        pairs.extend(command_skill_pairs(&commands));
    }
    let slots: BTreeMap<(i32, i32), usize> = pairs
        .into_iter()
        .filter(|(a, s)| game.actors.contains_key(a) && game.skills.contains(s))
        .enumerate()
        .map(|(slot, pair)| (pair, slot))
        .collect();
    if slots.len() > SKILL_SLOTS_MAX {
        return Err(Bad::answer(format!(
            "there are {} skill pairs and `FAR_SKILL` holds {SKILL_SLOTS_MAX}",
            slots.len()
        )));
    }
    Ok(slots)
}

/// The (CharSet, index) pairs some `ChangeSpriteAssociation` of these maps
/// —or of `extra`— names, in the order they appear: each one gets the same
/// slot in every map's graphics table, because the graphic an actor is
/// given crosses the teleport. All the pages are looked at, whether they
/// compile or not, so the list does not depend on what compiles.
pub fn associations(maps: &[Map], extra: &[Command]) -> Vec<(String, i32)> {
    let mut pairs: Vec<(String, i32)> = Vec::new();
    let commands = maps
        .iter()
        .flat_map(|m| m.events.iter())
        .flat_map(|e| e.pages.iter())
        .flat_map(|p| p.commands.iter())
        .chain(extra.iter());
    for cmd in commands {
        if cmd.code != CHANGE_SPRITE_ASSOCIATION {
            continue;
        }
        let p = &cmd.parameters;
        if p.len() != 3 || p[2] != 0 {
            continue;
        }
        let pair = (cmd.string.clone(), p[1]);
        if !pairs.contains(&pair) {
            pairs.push(pair);
        }
    }
    pairs
}

/// The parallel common events that only look at the equipment: with a
/// switch, and nothing but `ChangeSkills` and branches on an actor's
/// equipment. The ROM runs them when the menu closes and right after the
/// switch turns on; see the converter. By switch, and a later one takes
/// the switch of an earlier one.
pub fn party_common_events(game: &Game) -> BTreeMap<i32, i32> {
    let mut out = BTreeMap::new();
    for (&number, c) in &game.common_events {
        let allowed = |code: i32| {
            matches!(
                code,
                CHANGE_SKILLS | COND_BRANCH | COND_ELSE | COND_END | BLOCK_END
            )
        };
        let equipment_only = c
            .commands
            .iter()
            .filter(|x| x.code == COND_BRANCH)
            .all(|x| {
                x.parameters.first().map(|&v| v as i64) == Some(COND_ACTOR)
                    && x.parameters.get(2).map(|&v| v as i64) == Some(COND_ACTOR_EQUIPMENT)
            });
        if c.trigger == COMMON_PARALLEL
            && c.switch_flag
            && !c.commands.is_empty()
            && c.commands.iter().all(|x| allowed(x.code))
            && equipment_only
        {
            out.insert(c.switch_id, number);
        }
    }
    out
}

/// All of them.
pub fn build(
    game: &Game,
    maps: &[Map],
    extra_variables: &BTreeSet<i32>,
    extra_pairs: &BTreeSet<(i32, i32)>,
) -> Result<Indices> {
    Ok(Indices {
        variables: variables(game, maps, extra_variables),
        skills: skills(game, maps, extra_pairs)?,
        party_common_events: party_common_events(game),
    })
}
