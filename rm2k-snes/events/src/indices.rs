//! The indices of the whole game, built before compiling anything: which
//! slot each variable gets, which bit each (actor, skill) pair gets, which
//! graphics an actor can be given, and which common events are the
//! equipment ones.
//!
//! The slots come from sweeping **every map of the game**, its troops' pages
//! and its common events, whether they compile or not: a cheap superset, and a page that starts compiling later shifts
//! nobody's slot, so a game saved with one cartridge loads in another.

use crate::codes::*;
use crate::compile::{
    Indices, COND_ACTOR, COND_ACTOR_SKILL, COND_SWITCH, COND_VARIABLE, SWITCH_TABLE_MAX, VAR_VARIABLE,
};
use crate::fail::{Bad, Result};
use crate::game::{Command, Game, Map};
use std::collections::{BTreeMap, BTreeSet};

/// The bits live in `FAR_SKILL`, which has 256 bytes in the far RAM map.
/// Today the game uses far fewer; if some day they are not enough, the
/// converter stops instead of overwriting the neighbor.
const SKILL_SLOTS_MAX: usize = 256 * 8;

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
        } else if code == INPUT_NUMBER && p.len() >= 2 {
            ids.insert(p[1]);
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
        } else if code == CHANGE_ITEMS && p.len() >= 5 {
            // The item and the amount by a variable, since 2026-10-14: The
            // Book of Three's essences and Vampires Dawn's.
            if p[1] != 0 {
                ids.insert(p[2]);
            }
            if p[3] != 0 {
                ids.insert(p[4]);
            }
        } else if matches!(code, CHANGE_MONSTER_HP | CHANGE_MONSTER_MP) && p.len() >= 4 && p[2] == 1 {
            ids.insert(p[3]);
        } else if code == SHOW_PICTURE && p.len() >= 4 && p[1] == 1 {
            // A picture placed by two variables, since 2026-10-01. In the
            // game they are the smoke's and the aura numbers', and they add
            // none: a `ControlVars` names all four.
            ids.extend([p[2], p[3]]);
        } else if matches!(code, SHOW_MESSAGE | SHOW_MESSAGE_2) {
            // A variable's value in the text, `\V[n]`, since 2026-10-02. In
            // the game they are three of the portable console and add none:
            // its `ControlVars` and the troops' name them.
            ids.extend(text_variables(&cmd.string));
        }
    }
    ids
}

/// The variables a text names with `\V[n]`, in its plain form: see
/// `with_variables` in [`crate::compile`].
fn text_variables(text: &str) -> Vec<i32> {
    let mut out = Vec::new();
    let mut rest = text;
    while let Some(at) = rest.find(['\\']) {
        rest = &rest[at + 1..];
        let Some(tail) = rest.strip_prefix(['V', 'v']).and_then(|r| r.strip_prefix('[')) else {
            continue;
        };
        let digits: String = tail.chars().take_while(|c| c.is_ascii_digit()).collect();
        if !digits.is_empty() && tail[digits.len()..].starts_with(']') {
            if let Ok(n) = digits.parse() {
                out.push(n);
            }
        }
    }
    out
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

/// Each variable some page of the game names —its maps', its troops' and
/// its common events'—, plus `extra`, with its slot.
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
    // And the common events', which a `CallEvent` compiles in place: a
    // variable only a common event names —the fifty-three of common 35,
    // `ResetAfterBattles`, which count each summon's uses and put back
    // Talan's HP— had no slot until 2026-09-30, and the whole common event
    // was skipped for it. Adding them shifted the other slots, so a game
    // saved with an older cartridge does not load in a newer one: that was
    // a deliberate choice, not an oversight.
    for c in game.common_events.values() {
        ids.extend(command_variables(&c.commands));
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

/// The name each actor keeps for the whole game, for `\N[n]` to be baked
/// into the text: the ones in the database whose name **no**
/// `ChangeHeroName` in any page of the game changes. A renamed actor is not
/// here, and neither is `\N[0]`, the leader, whose name depends on who is in
/// the party: those boxes are left out as before, since the ROM has no way
/// to write a name that is only known at run time.
pub fn hero_names(game: &Game, maps: &[Map]) -> BTreeMap<i32, String> {
    let mut renamed = BTreeSet::new();
    let mut sweep = |commands: &[Command]| {
        renamed.extend(commands.iter().filter(|c| c.code == CHANGE_HERO_NAME).filter_map(|c| c.parameters.first().copied()));
    };
    for map in maps {
        for event in &map.events {
            for page in &event.pages {
                sweep(&page.commands);
            }
        }
    }
    for commands in troop_page_commands(game) {
        sweep(&commands);
    }
    for c in game.common_events.values() {
        sweep(&c.commands);
    }
    game.actor_names
        .iter()
        .filter(|(id, _)| !renamed.contains(id))
        .map(|(&id, name)| (id, name.clone()))
        .collect()
}

/// The switches these commands name: a `ControlSwitches` on one or on a
/// range, and a branch on one. The one by variable names a variable, and
/// does not compile.
pub fn command_switches(commands: &[Command]) -> BTreeSet<i32> {
    let mut ids = BTreeSet::new();
    for cmd in commands {
        let p = &cmd.parameters;
        if cmd.code == CONTROL_SWITCHES && p.len() >= 3 && (p[0] == 0 || p[0] == 1) {
            ids.extend([p[1], p[2]]);
        } else if cmd.code == COND_BRANCH && p.len() >= 2 && p[0] as i64 == COND_SWITCH {
            ids.insert(p[1]);
        }
    }
    ids
}

/// The highest switch the game names, which is what the ROM's table holds:
/// the cartridge's `SWITCH_BYTES` is this over eight plus one.
///
/// Until 2026-10-15 the table was 128 bytes for every game —1024 switches,
/// the most ABL names being 1008—, and nothing stopped a `ControlSwitches`
/// past it: Vampires Dawn has a thousand such commands, up to 1643, and The
/// Frozen World seventy-eight, up to 1077, and they wrote into whatever RAM
/// followed the table, while their page conditions read it. Now the table is
/// the game's, and a game that names none past 127 pays 16 bytes.
///
/// Like the variables, **every** page of every map, troop and common event
/// is swept, whether it compiles or not —its conditions, its triggers and its
/// commands—, plus the database's switch items and skills and `extra`, the
/// test pages' and the harness's. That way the table does not depend on
/// what compiles, and a game saved with one cartridge loads in another.
pub fn switch_top(game: &Game, maps: &[Map], extra: &BTreeSet<i32>) -> Result<i32> {
    let mut ids = extra.clone();
    ids.extend(&game.database_switches);
    for map in maps {
        for event in &map.events {
            for page in &event.pages {
                ids.extend([page.condition.switch_a, page.condition.switch_b].into_iter().flatten());
                ids.extend(command_switches(&page.commands));
            }
        }
    }
    for pages in game.troops.values() {
        for page in pages {
            let c = &page.condition;
            if c.flags.switch_a {
                ids.insert(c.switch_a_id);
            }
            if c.flags.switch_b {
                ids.insert(c.switch_b_id);
            }
        }
    }
    for commands in troop_page_commands(game) {
        ids.extend(command_switches(&commands));
    }
    for c in game.common_events.values() {
        if c.switch_flag {
            ids.insert(c.switch_id);
        }
        ids.extend(command_switches(&c.commands));
    }
    let top = ids.last().copied().unwrap_or(0).max(0);
    if top >= SWITCH_TABLE_MAX {
        return Err(Bad::answer(format!(
            "the game names switch {top} and the ROM's table holds {SWITCH_TABLE_MAX}: see SWITCHRAM in rm2k-snes/cartridge"
        )));
    }
    Ok(top)
}

/// All of them.
pub fn build(
    game: &Game,
    maps: &[Map],
    extra_variables: &BTreeSet<i32>,
    extra_pairs: &BTreeSet<(i32, i32)>,
    extra_switches: &BTreeSet<i32>,
) -> Result<Indices> {
    Ok(Indices {
        variables: variables(game, maps, extra_variables),
        skills: skills(game, maps, extra_pairs)?,
        hero_names: hero_names(game, maps),
        switch_top: switch_top(game, maps, extra_switches)?,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::CommonEvent;

    fn control_var(variable: i32) -> Command {
        Command::new(CONTROL_VARS, 0, "", vec![0, variable, variable, 0, 0, 1, 0])
    }

    /// A variable that only a common event names gets a slot, in order with
    /// the others: a `CallEvent` compiles the common event in place, and one
    /// naming a variable without a slot does not compile.
    #[test]
    fn a_variable_only_a_common_event_names_has_a_slot() {
        let mut game = Game::default();
        game.common_events.insert(
            35,
            CommonEvent {
                trigger: 5,
                switch_flag: false,
                switch_id: 1,
                commands: vec![control_var(70), control_var(134)],
            },
        );
        let slots = variables(&game, &[], &BTreeSet::from([100]));
        assert_eq!(slots, BTreeMap::from([(70, 0), (100, 1), (134, 2)]));
    }

    fn switches_page(switch_a: Option<i32>, commands: Vec<Command>) -> crate::game::Page {
        crate::game::Page {
            trigger: 0,
            layer: 1,
            move_type: 0,
            move_frequency: 3,
            move_speed: 3,
            animation_type: 0,
            character_name: String::new(),
            character_index: 0,
            character_pattern: 1,
            commands,
            route: Vec::new(),
            route_repeat: false,
            route_skippable: false,
            condition: crate::game::Condition { switch_a, ..Default::default() },
        }
    }

    fn on_a_map(pages: Vec<crate::game::Page>) -> Map {
        Map { id: 1, events: vec![crate::game::Event { id: 1, pages, starting: None }] }
    }

    /// Each place a switch can be named raises the table: a page's
    /// condition, a `ControlSwitches` on one or on a range —not by
    /// variable—, a branch, a common event's trigger, a troop page's
    /// condition and its commands, the database's switch skills and items,
    /// and `extra`.
    #[test]
    fn the_table_holds_the_highest_switch_named_anywhere() {
        let top = |game: &Game, maps: &[Map], extra: &[i32]| {
            switch_top(game, maps, &extra.iter().copied().collect()).unwrap()
        };
        let control = |p: &[i32]| Command::new(CONTROL_SWITCHES, 0, "", p.to_vec());
        let game = Game::default();
        assert_eq!(top(&game, &[], &[]), 0);
        assert_eq!(top(&game, &[on_a_map(vec![switches_page(Some(1521), vec![])])], &[]), 1521);
        assert_eq!(top(&game, &[on_a_map(vec![switches_page(None, vec![control(&[1, 1070, 1077, 0])])])], &[]), 1077);
        // By variable, 1500 is the variable.
        assert_eq!(top(&game, &[on_a_map(vec![switches_page(None, vec![control(&[2, 1500, 1500, 0])])])], &[]), 0);
        let branch = Command::new(COND_BRANCH, 0, "", vec![0, 1060, 0, 0, 0, 0]);
        assert_eq!(top(&game, &[on_a_map(vec![switches_page(None, vec![branch])])], &[]), 1060);
        assert_eq!(top(&game, &[], &[1023]), 1023);

        let mut game = Game::default();
        game.common_events.insert(1, CommonEvent { trigger: 3, switch_flag: true, switch_id: 1600, commands: vec![] });
        assert_eq!(top(&game, &[], &[]), 1600);
        game.common_events.insert(2, CommonEvent { trigger: 5, switch_flag: false, switch_id: 1700, commands: vec![control(&[0, 1643, 1643, 0])] });
        assert_eq!(top(&game, &[], &[]), 1643, "a trigger without its flag names nothing");

        let mut game = Game::default();
        let mut condition = ditto::schema::TroopPageCondition::default();
        condition.flags.switch_b = true;
        condition.switch_b_id = 1400;
        game.troops.insert(1, vec![crate::game::TroopPage { condition, commands: vec![] }]);
        assert_eq!(top(&game, &[], &[]), 1400);
        game.database_switches.insert(1450);
        assert_eq!(top(&game, &[], &[]), 1450);
    }

    /// Past the 256 bytes the cartridge gives the table the converter stops,
    /// instead of reading and writing whatever RAM follows it.
    #[test]
    fn a_game_past_the_table_is_refused() {
        let mut game = Game::default();
        game.database_switches.insert(SWITCH_TABLE_MAX - 1);
        assert_eq!(switch_top(&game, &[], &BTreeSet::new()).unwrap(), 2047);
        game.database_switches.insert(SWITCH_TABLE_MAX);
        assert!(switch_top(&game, &[], &BTreeSet::new()).is_err());
    }
}
