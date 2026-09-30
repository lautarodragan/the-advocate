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
/// Today the game uses far fewer; if some day they are not enough, the
/// converter stops instead of overwriting the neighbor.
const SKILL_SLOTS_MAX: usize = 256 * 8;
/// The end of a block of commands: the empty line that closes each branch.
const BLOCK_END: i32 = END;

/// The battle's branch commands, as the map's: the two kinds the game uses
/// have their operands in the same place.
///
/// Of the six questions of `CommandConditionalBranchBattle` the game uses
/// **only two** —the switch and the variable, in 1108 branches of 295
/// distinct bodies, measured on 2026-09-21— and those have the operands in
/// the same place as the map's: `[kind, number, polarity or value kind,
/// value, comparison, else]`. So they are translated to the map's code and
/// compile to OP_IF and OP_IF_VAR without a new opcode. The other four
/// —whether an actor or an enemy can act, whom it targets, which command it
/// gave— ask for battle state and do not compile.
pub fn battle_branch(code: i32) -> i32 {
    match code {
        BATTLE_COND_BRANCH => COND_BRANCH,
        BATTLE_COND_ELSE => COND_ELSE,
        BATTLE_COND_END => COND_END,
        c => c,
    }
}

/// The variables these commands name: the `variables` sweep, which is also
/// that of the test pages.
///
/// `ChangeEventLocation` with the cell in two variables came in on
/// 2026-09-18, when the test page started using it. In the game they are
/// 129 and add none: measured, all their variables are already named by
/// another command.
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
        } else if matches!(code, CHANGE_HP | CHANGE_SP) && p.len() >= 5 && p[3] == 1 {
            ids.insert(p[4]);
        }
    }
    ids
}

/// The (actor, skill) pairs these commands name, in the forms that
/// compile: fixed actor and constant skill. A pair that comes in a variable
/// cannot be indexed, and those commands do not compile. None in the game
/// does it.
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

/// The troop pages' commands, with the battle's branches as the map's, for
/// the sweeps that look for variables and skill pairs. **It does not
/// filter**: the sweep is a superset, like the maps', whether the page
/// compiles or not.
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
///
/// The game declares five thousand and uses **81**, the highest being 201.
/// The ROM does not carry the five thousand: this looks at which variables
/// the pages **of every map in the game** name and gives each one a
/// **slot**, from zero up, and the bytecode talks in slots. That way the RAM
/// it costs is 162 bytes, they live in bank 1's RAM (`FAR_VARIABLES`) and
/// travel in the saved game. Until the night of 2026-09-10 the index was of
/// each ROM's maps —six variables on maps 1 to 10— and with that a game
/// saved with one ROM was not valid for another with more maps: the slots
/// shifted. With the whole game's index a variable's slot is the same in any
/// ROM, and the save went from 256 to 512 bytes of SRAM.
///
/// All the commands and conditions of all the pages are looked at, whether
/// they compile or not: it is a cheap superset —two bytes per variable— and
/// that way a page that compiles later does not change the others' slots.
/// `extra` are those of the test pages, which do not come from any map.
///
/// **`KeyInputProc` also names a variable, and until 2026-09-13 it was not
/// in this list.** It is the only command in the game that writes to a
/// variable without being a `ControlVars`, so a variable only it touched
/// was left without a slot and the page did not compile for a reason that
/// had nothing to do with the command. **Two** get through: 5, from the
/// stones minigame engine on map 11, and 151, from two other pages; all
/// three are written by this command and read by nobody else. It was not
/// circular —it did not depend on the page compiling—: this sweep looks at
/// all the commands whether they compile or not, and it did not look at
/// this one.
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
    // And those of the troops' pages, which belong to the whole game and not
    // to a map. They add up to **forty**, measured on 2026-09-21: the
    // characters' systems each carry their counters —Talan's 81 and 106
    // count how many times he absorbed each technique—, and no map names
    // them.
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
/// does not have is left out: RM2k ignores them with a warning, and here
/// they do not compile.
///
/// `ChangeSkills` teaches an actor skills and makes it forget them, and that
/// is world state: it travels in the save, like the equipment. What the ROM
/// stores is **one bit per (actor, skill) pair**, and not a list per actor,
/// because the game teaches many at a time —actor 14 gets seventy set and
/// removed in the common events— and a variable-length list in far RAM
/// would require searching, sorted insertion and capping.
///
/// The pairs are the ones the whole game may end up looking at, and no more:
/// those of the LDB's learning table **at every level** —the day there is
/// leveling up, `LearnLevelSkills` turns on the ones that apply—, the ones
/// some `ChangeSkills` names and the ones some "knows the skill" branch
/// asks about. A pair nobody names can neither change nor be asked about,
/// so its bit is not needed. All of the game's maps and all common events
/// are swept, whether they compile or not, for the same reason as the
/// variables: that way a page that compiles later does not shift anyone
/// else's slot, and a game saved with one ROM works with another.
///
/// The order is by actor and then by skill, and it is not cosmetic: it
/// leaves each actor's pairs together and sorted by number, which is the
/// order `LearnSkill` leaves them in and the one the battle menu shows them
/// in. That way the ROM builds the list by walking a stretch, without
/// sorting anything.
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
    // And the troops' pages, which since 2026-09-21 run in the battle. Today
    // they add no pair —the ones the systems teach are already named by some
    // map—, but without this the first one that is not would not compile.
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
///
/// It is `Graphics`' prior pass: it reserves for each one the same slot in
/// the graphics table of every ROM map, because the graphic the command
/// gives an actor **crosses the teleport** and its index has to mean the
/// same on both sides of the jump.
///
/// **All** the pages are looked at and not only the ones that compile, on
/// purpose: if it depended on what compiles, the list would depend on
/// whether the ROM carries a message window —same as `possible_leaders`—
/// and the converter's two passes would number differently. Reserving one
/// slot too many costs the twelve poses of a CharSet in the sprite bank and
/// nothing else.
///
/// In the game they are two pairs —`Future3:0` and `BLVehicles:2`— and only
/// if the ROM carries any of maps 49, 50, 52 or 54, which are the car chase.
///
/// `extra` are the commands of the test pages, which go after.
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
            // The ones `compile_command` is going to reject.
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
/// equipment —with their `else`, their closer and the block ends—. The ROM
/// runs them when the menu closes and right after the switch turns on; see
/// the converter. By switch, and a later one takes the switch of an earlier
/// one.
///
/// It is the tailored path of Lashe City's milestone 4, and in the game
/// there is a single one: 37, `UpdateAG7 Skills`, parallel on switch 150,
/// which takes AG7-17's seventeen skills away and gives it the one of each
/// piece it has equipped.
///
/// The ROM does not run parallel common events. Doing them for real —one
/// more interpreter, running the body **on every frame** while the switch is
/// on— is the general way, and it was measured on 2026-09-27 against this
/// (see `workflow/tasks/*/lashe-4-ag7-en-la-pelea.md`): what ruled it out
/// was not the cost but that it would also turn on 2 (`DisableSaving`, parallel
/// **without a switch**, which turns saving off every time 236 is off), 3
/// and 8, and that changes `release` far beyond this milestone.
///
/// A parallel one that only reads its switch and the equipment, and only
/// writes skills, gives the same result on every frame until one of those
/// two things changes, and what it writes depends on nobody but itself. So
/// it is enough to run it **when they change**: when the switch turns on
/// —the compiler pastes the body after the `ControlSwitches` that turns it
/// on, like a `CallEvent`— and when closing the menu, which is where the
/// equipment is changed —the ROM runs it from `menu_screen`, see
/// `equipment_commons` in tools/runtime/equipment_from_events.s—. It is
/// what the droid tutorial says: "these abilities become available once you
/// equip a particular component and exit the menu".
///
/// What is left out: a page's `ChangeEquipment` on the actor the event looks
/// at does not run it again. In the game there is none on 18.
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
