//! The troops' event pages, which the battle runs with the same
//! interpreter as the maps: compiled with the same compiler, with a
//! narrower list of what is accepted and their messages in a block of
//! their own.
//!
//! `Game_Interpreter_Battle`: each troop brings its pages, and the battle
//! runs them **with the same interpreter as the maps**, `run_code`, so they
//! are compiled with the same `compile_page`. The only thing that changes is
//! what is accepted: see `TROOP_COMMANDS`.
//!
//! When each one runs is decided by the ROM and it is copied from
//! `Scene_Battle_Rpg2k`; see `ba_page_test` in runtime/battle_troop.s.

use crate::codes::*;
use crate::compile::{compile_page, Ctx, ACCEPTED_UNDONE, CALL_MAX};
use crate::losses::Origin;
use crate::fail::Result;
use crate::game::{Command, Game, TroopPage};
use crate::indices::battle_branch;
use crate::messages::Messages;
use crate::registry::Package;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};

/// What a troop page can do in this port. **It is a list of the ones that
/// do, not of the ones that do not**, on purpose: almost everything that
/// compiles on a map assumes the map —a teleport, a route, a tint, a choice,
/// which opens the map's window— and inside the battle it would do
/// something else without warning.
///
/// `PlaySound` sounds in the battle's audio package if its effect fits there
/// —see `TroopPages::compile`—, and `ShakeScreen` moves the scene: see
/// `ba_shake`. Its wait, an OP_DELAY, is counted by `ba_page_step`.
///
/// **What changes the party**, since 2026-09-30 —`ChangePartyMembers`,
/// `ChangeHP`, `FullHeal`, the `ChangeCondition` that revives, and
/// `ControlVars` with an actor's HP—, is the map's opcode as it is: the
/// battle keeps its HP in `BA_ONE`, but each stretch of a page runs between
/// `ba_sync_out` and `ba_sync_in`, which take them to `FAR_HP` and bring them
/// back with whoever joined or left. `ChangeMonsterHP` and `ChangeMonsterMP`
/// are OP_ENEMY.
///
/// `ChangeEquipment` equips, and the battle takes up the parameters it changes
/// —`ba_reparam`—. `PlayBGM` goes into the battle's audio package: see
/// `PLAY_BGM` in the compiler.
///
/// `Comment` is in since 2026-10-06, as in a map: the author's notes run as
/// nothing. A troop page with one in the middle was left out whole for it.
///
/// `FlashScreen` and `TintScreen` are in since 2026-10-12: they leave the
/// same state as on a map, and the battle draws it on the scene's palette
/// —see `ba_tone_tick` in runtime/battle_tone.s—. Their waits are OP_DELAY,
/// like `ShakeScreen`'s, and so is `Wait`, which came in with them: Book of
/// Three asks for it. `TerminateBattle` ends the battle with no victory.
/// `ChangeMonsterCondition` came in the same day as a debt, and is done since
/// the battle keeps conditions: OP_MONSTER_STATE, see `battle_states.s`.
///
/// **RPG Maker 2003's**, since 2026-10-15, for a 2003 game fought with
/// this battle: `ChangeSP`, like `ChangeHP`, through the sync; `ForceFlee`
/// for the party —OP_BATTLE_FLEE, an escape that cannot fail—, not for an
/// enemy, which the 2000 battle has no way to send off; and
/// `CallCommonEvent`, which is not here but in [`runs_in_battle`], with a
/// `CallEvent` to a common event: both are expanded before this list is
/// asked, see [`expand_calls`]. A page conditioned on what only 2003 has
/// —an actor's command, a turn of one actor or enemy— never runs here, and
/// is left out: see [`trigger`].
const TROOP_COMMANDS: [i32; 32] = [
    END,
    CHANGE_SP,
    FORCE_FLEE,
    SHOW_MESSAGE,
    SHOW_MESSAGE_2,
    CONTROL_SWITCHES,
    CONTROL_VARS,
    CHANGE_SKILLS,
    CHANGE_GOLD,
    CHANGE_ITEMS,
    CHANGE_PARTY_MEMBERS,
    CHANGE_EQUIPMENT,
    CHANGE_HP,
    FULL_HEAL,
    CHANGE_CONDITION,
    PLAY_SOUND,
    PLAY_BGM,
    SHAKE_SCREEN,
    FLASH_SCREEN,
    TINT_SCREEN,
    CHANGE_MONSTER_CONDITION,
    TERMINATE_BATTLE,
    WAIT,
    CHANGE_MONSTER_HP,
    CHANGE_MONSTER_MP,
    SHOW_HIDDEN_MONSTER,
    COND_BRANCH,
    COND_ELSE,
    COND_END,
    MESSAGE_OPTIONS,
    COMMENT,
    COMMENT_2,
];

/// What a troop page accepts **without doing it**: the troops' own
/// `ACCEPTED_UNDONE`, a debt and not an equivalence, warned about by the
/// converter like the other.
///
/// `ShowBattleAnimationB`, the animation on the monsters, since 2026-10-14:
/// the battle scene plays no animation, and the command is kept to its
/// length, a wait —see its arm in the compiler—. taro's: "not having this
/// command shouldn't stop anyone from playing". It is what lets in the two
/// scripted endings of The Book of Three, troops 96 and 136, which end the
/// battle with `TerminateBattle` right after it. The divergence is in the
/// book's `divergences/what-troop-pages-do-not-model.md`.
const TROOP_ACCEPTED_UNDONE: [i32; 1] = [SHOW_BATTLE_ANIMATION_B];

// Which triggers the ROM knows how to look at, with their bit in
// `tpage_flags`: RM2k's six. The three from 2003 —an actor's or an enemy's
// turn, fatigue and an actor's command— do not exist in a 2000 game, and a
// page that asked for them is left out.
const SWITCH_A: u8 = 0x01;
const SWITCH_B: u8 = 0x02;
const VARIABLE: u8 = 0x04;
const TURN: u8 = 0x08;
const ENEMY: u8 = 0x10;
const ACTOR: u8 = 0x20;
/// The triggers that carry a **header**: the turn and HP numbers do not go
/// in per-page tables in bank 1 —which no longer has room for ten bytes for
/// each of the five hundred— but in front of the page's code, in
/// `troop_code`, which is in RODATA. See [`Trigger::header`] and
/// `ba_page_header`.
const WITH_HEADER: u8 = TURN | ENEMY | ACTOR;

/// The trigger of a troop page, with what the ROM reads from each one; the
/// fields of what it does not look at go at zero.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Trigger {
    pub flags: u8,
    pub switch_a: i32,
    pub switch_b: i32,
    pub slot: i32,
    pub value: i32,
    pub turn_base: i32,
    pub turn_mult: i32,
    pub enemy: i32,
    pub enemy_min: i32,
    pub enemy_max: i32,
    pub actor: i32,
    pub actor_min: i32,
    pub actor_max: i32,
}

impl Trigger {
    fn to_json(&self) -> Value {
        json!([
            self.flags,
            self.switch_a,
            self.switch_b,
            self.slot,
            self.value,
            self.turn_base,
            self.turn_mult,
            self.enemy,
            self.enemy_min,
            self.enemy_max,
            self.actor,
            self.actor_min,
            self.actor_max
        ])
    }

    /// The ten bytes in front of a page that looks at the turn or the HP:
    /// the turn's base and multiple, a word each, and the enemy's place, the
    /// actor and their ranges, a byte each. Empty if it looks at none of
    /// that. The order is `BA_COND`'s in runtime/far_ram.s.
    fn header(&self) -> Vec<u8> {
        if self.flags & WITH_HEADER == 0 {
            return vec![];
        }
        vec![
            (self.turn_base & 0xFF) as u8,
            (self.turn_base >> 8) as u8,
            (self.turn_mult & 0xFF) as u8,
            (self.turn_mult >> 8) as u8,
            self.enemy as u8,
            self.enemy_min as u8,
            self.enemy_max as u8,
            self.actor as u8,
            self.actor_min as u8,
            self.actor_max as u8,
        ]
    }
}

/// A troop page's `Trigger`, or None if it looks at something the ROM does
/// not know how to look at, or at nothing —then it never runs—.
///
/// A page **without any trigger never runs** —`AreConditionsMet` returns
/// false right away— and it also gives None: there is no point carrying it.
/// The variable one is `>=`, always: RM2k gives it no operator.
///
/// **The turn goes with base and multiple in that order**, and not in the
/// names' order: easyrpg calls `CheckTurns(turn, turn_b, turn_a)` and its
/// signature is `(turns, base, multiple)`, so `turn_b` is the base. With the
/// other order the agents' takeoff page —`turn_a` 0, `turn_b` 1— would run
/// on every turn instead of on the first.
///
/// HP is in percent, from 0 to 100: an enemy's by its place in the troop,
/// an actor's by its LDB number.
pub(crate) fn trigger(ctx: &Ctx, page: &TroopPage) -> Option<Trigger> {
    let c = &page.condition;
    let f = &c.flags;
    if !(f.switch_a || f.switch_b || f.variable || f.turn || f.fatigue || f.enemy_hp || f.actor_hp)
    {
        return None;
    }
    if f.fatigue {
        return None;
    }
    // RPG Maker 2003's conditions —an actor's command, a turn of one actor
    // or one enemy— **and** one of 2000's: the page asks for both, and the
    // 2000 battle has no event for the first, so it never runs. A page on a
    // 2003 condition alone fell to the test above. In Zounds that is the 36
    // pages of its own Escape command, measured on 2026-10-15.
    if f.command_actor || f.turn_actor || f.turn_enemy {
        return None;
    }
    let mut t = Trigger::default();
    for (on, bit) in [
        (f.switch_a, SWITCH_A),
        (f.switch_b, SWITCH_B),
        (f.variable, VARIABLE),
        (f.turn, TURN),
        (f.enemy_hp, ENEMY),
        (f.actor_hp, ACTOR),
    ] {
        if on {
            t.flags |= bit;
        }
    }
    if f.switch_a {
        t.switch_a = c.switch_a_id;
    }
    if f.switch_b {
        t.switch_b = c.switch_b_id;
    }
    if !ctx.indices.holds_switch(t.switch_a as i64) || !ctx.indices.holds_switch(t.switch_b as i64) {
        return None;
    }
    if f.variable {
        t.value = c.variable_value;
        if !(-0x8000..=0x7FFF).contains(&t.value) {
            return None;
        }
        t.slot = ctx.indices.variable_slot(c.variable_id as i64).ok()? as i32;
    }
    if f.turn {
        t.turn_base = c.turn_b;
        t.turn_mult = c.turn_a;
        // `ba_div` needs the divisor below 32768.
        if !((0..=0xFFFF).contains(&t.turn_base) && (0..0x8000).contains(&t.turn_mult)) {
            return None;
        }
    }
    if f.enemy_hp {
        (t.enemy, t.enemy_min, t.enemy_max) = (c.enemy_id, c.enemy_hp_min, c.enemy_hp_max);
        if !((0..256).contains(&t.enemy)
            && (0..=100).contains(&t.enemy_min)
            && (0..=100).contains(&t.enemy_max))
        {
            return None;
        }
    }
    if f.actor_hp {
        (t.actor, t.actor_min, t.actor_max) = (c.actor_id, c.actor_hp_min, c.actor_hp_max);
        if !((0..256).contains(&t.actor)
            && (0..=100).contains(&t.actor_min)
            && (0..=100).contains(&t.actor_max))
        {
            return None;
        }
    }
    Some(t)
}

/// A troop page's boxes rebuilt for the battle's window, which is
/// narrower than the map's: each `ShowMessage` with its `ShowMessage_2`s
/// goes as the boxes `rm2k-snes-text`'s `refit` makes of it —itself, if it
/// fits—, one after the other, and the battle shows them one after the
/// other. It is the same reflow the map's boxes go through, for another
/// width: before, the battle cut every line at its edge, and "The Captain
/// has taken off in the ship!" came out "...taken off in th".
#[cfg(test)]
fn reflow(raw: Vec<Command>, measure: &rm2k_snes_text::refit::Measure, rows: usize) -> Vec<Command> {
    reflow_from(raw, measure, rows).into_iter().map(|(_, c)| c).collect()
}

/// [`reflow`], with the index in `raw` each command comes from: a box cut
/// in two comes from the same `ShowMessage`.
pub(crate) fn reflow_from(
    raw: Vec<Command>,
    measure: &rm2k_snes_text::refit::Measure,
    rows: usize,
) -> Vec<(usize, Command)> {
    let mut out = Vec::with_capacity(raw.len());
    let mut i = 0;
    while i < raw.len() {
        if raw[i].code != SHOW_MESSAGE {
            out.push((i, raw[i].clone()));
            i += 1;
            continue;
        }
        let mut j = i + 1;
        while j < raw.len() && raw[j].code == SHOW_MESSAGE_2 {
            j += 1;
        }
        let lines: Vec<String> = raw[i..j].iter().map(|c| c.string.clone()).collect();
        for frame in rm2k_snes_text::refit::refit_measured(&lines, measure, rows) {
            for (k, text) in frame.iter().enumerate() {
                let code = if k == 0 { SHOW_MESSAGE } else { SHOW_MESSAGE_2 };
                out.push((i, Command::new(code, raw[i].indent, text, vec![])));
            }
        }
        i = j;
    }
    out
}

/// A troop page's commands as a map's, or None if one does not run in a
/// troop page. The calls are already expanded: see [`expand_calls`].
fn commands(raw: &[Command]) -> Option<Vec<Command>> {
    if !raw.iter().all(runs_in_battle) {
        return None;
    }
    Some(raw.iter().map(as_map_command).collect())
}

/// Whether a command can be in a troop page: see `TROOP_COMMANDS`. The
/// battle's branch only with the two questions the map's has, a switch and
/// a variable; `ForceFlee` only for the party; a call only to a common
/// event, which [`expand_calls`] pastes before this is asked.
pub(crate) fn runs_in_battle(cmd: &Command) -> bool {
    if cmd.code == BATTLE_COND_BRANCH && !matches!(cmd.parameters.first(), Some(0) | Some(1)) {
        return false;
    }
    if cmd.code == FORCE_FLEE && cmd.parameters.first() != Some(&0) {
        return false;
    }
    if called_common(cmd).is_some() {
        return true;
    }
    let code = battle_branch(cmd.code);
    TROOP_COMMANDS.contains(&code) || TROOP_ACCEPTED_UNDONE.contains(&code)
}

/// The common event a command calls, if it is a call to one: RPG Maker
/// 2003's `CallCommonEvent`, by number, or a `CallEvent` of type 0.
pub(crate) fn called_common(cmd: &Command) -> Option<i32> {
    match (cmd.code, cmd.parameters.as_slice()) {
        (CALL_COMMON_EVENT, [id, ..]) => Some(*id),
        (CALL_EVENT, [0, id, ..]) => Some(*id),
        _ => None,
    }
}

/// A troop page's commands with every call to a common event replaced by
/// the callee's body, the index in `raw` each one comes from —a pasted
/// command's is the call's—, and the calls that were skipped instead,
/// as (index, common event).
///
/// On a map a call is `OP_CALL` or a pasted body; in a battle it is only
/// the second, because what a troop page accepts is decided here, before
/// compiling, and a pasted body has to pass the same list. EasyRPG's
/// `CommandCallCommonEvent` is a `Push`, so pasting gives the same result:
/// the callee runs whole before the caller goes on. A callee with a command
/// outside the list, or missing, is **skipped**, like a call to a body that
/// does not compile on a map; one nested past `CALL_MAX`, or in a loop, the
/// same. The pasted commands' indent is shifted by the call's, so that the
/// callee's branches close inside the caller's. In Zounds this is the steal
/// mechanic: 18 pages calling common event 2, which calls two more.
pub(crate) fn expand_calls(game: &Game, raw: &[Command]) -> (Vec<(usize, Command)>, Vec<(usize, i32)>) {
    /// Common event `id`'s body into `out`, shifted by `shift`, with the
    /// calls inside it pasted the same way: `None` if a command of its own
    /// does not run in a battle, and then nothing of it is pasted; the
    /// calls it makes that are skipped go to `skipped`.
    fn paste(game: &Game, id: i32, shift: i32, stack: &mut Vec<i32>, skipped: &mut Vec<i32>) -> Option<Vec<Command>> {
        let body = game.common_events.get(&id).map(|c| c.commands.as_slice()).unwrap_or(&[]);
        let mut out = Vec::with_capacity(body.len());
        for cmd in body {
            if let Some(callee) = called_common(cmd) {
                if stack.len() >= CALL_MAX || stack.contains(&callee) {
                    skipped.push(callee);
                    continue;
                }
                stack.push(callee);
                let pasted = paste(game, callee, shift + cmd.indent, stack, skipped);
                stack.pop();
                match pasted {
                    Some(pasted) => out.extend(pasted),
                    None => skipped.push(callee),
                }
                continue;
            }
            if !runs_in_battle(cmd) {
                return None;
            }
            out.push(Command { indent: cmd.indent + shift, ..cmd.clone() });
        }
        Some(out)
    }
    let mut out = Vec::with_capacity(raw.len());
    let mut skipped = Vec::new();
    for (i, cmd) in raw.iter().enumerate() {
        let Some(id) = called_common(cmd) else {
            out.push((i, cmd.clone()));
            continue;
        };
        let mut inner = Vec::new();
        match paste(game, id, cmd.indent, &mut vec![id], &mut inner) {
            Some(pasted) => out.extend(pasted.into_iter().map(|c| (i, c))),
            None => skipped.push((i, id)),
        }
        skipped.extend(inner.into_iter().map(|id| (i, id)));
    }
    (out, skipped)
}

/// A troop page's command as the map's: the battle's branch is the map's.
pub(crate) fn as_map_command(cmd: &Command) -> Command {
    Command {
        code: battle_branch(cmd.code),
        ..cmd.clone()
    }
}

/// A page that got in: its trigger, where its code is, and which of the
/// troop's pages it is.
pub type Entry = (Trigger, usize, usize);

/// The pages of the cartridge's troops, compiled and deduplicated: the
/// game copies its systems' pages into every troop, so the key is the
/// compiled bytecode, header included.
///
/// `bodies` is the code of all of them, one after the other and **each
/// distinct body only once**: the game copies its systems' pages into every
/// troop —4588 pages and 295 distinct bodies—, so the key is the already
/// compiled bytecode, same as the converter's `Materials` with the map's
/// blocks.
///
/// The messages go to **their own block**, `messages_troop`, and not to the
/// maps': `OP_MESSAGE` carries a sixteen-bit offset and the maps' block of
/// the test cartridge is already around 65 KB. The battle draws them on its
/// screen and not in the map's window, so reading them from elsewhere costs
/// it nothing.
pub struct TroopPages {
    pub messages: Messages,
    pub bodies: Vec<u8>,
    where_: HashMap<Vec<u8>, usize>,
    /// Per troop, each page that got in: its trigger, where its code is,
    /// and which of the troop's pages it is.
    pub per_troop: Vec<(i32, Vec<Entry>)>,
    pub pages: usize,
    pub left_out: usize,
    /// What the pages that got in accept without doing —`ACCEPTED_UNDONE`—:
    /// per command, each (troop, page) that uses it, for the converter to
    /// warn, as it does with the maps' automatic pages.
    pub debts: BTreeMap<i32, Vec<(i32, usize)>>,
}

impl TroopPages {
    pub fn new(messages: Messages) -> TroopPages {
        TroopPages {
            messages,
            bodies: vec![],
            where_: HashMap::new(),
            per_troop: vec![],
            pages: 0,
            left_out: 0,
            debts: BTreeMap::new(),
        }
    }

    /// A troop's pages. With songs, a `PlaySound` is compiled with its
    /// effect, which counts for **the battle's audio package** —the one
    /// loaded when the page runs, see [`Package`]— and not for the map's;
    /// and it goes into it only if it is in `troop_in_package`: otherwise it
    /// is asked for and does not sound, like a route one that does not fit.
    /// Without songs it is accepted and not done.
    pub fn compile(&mut self, ctx: &mut Ctx, number: i32, pages: &[TroopPage]) -> Result<()> {
        let previous = ctx.songs.as_ref().and_then(|s| s.current);
        if let Some(songs) = ctx.songs.as_deref_mut() {
            songs.current = Some(Package::Battle);
        }
        let result = self.pages_of(ctx, number, pages);
        if let Some(songs) = ctx.songs.as_deref_mut() {
            songs.current = previous;
        }
        self.per_troop.push((number, result?));
        Ok(())
    }

    fn pages_of(&mut self, ctx: &mut Ctx, number: i32, pages: &[TroopPage]) -> Result<Vec<Entry>> {
        let mut theirs = Vec::new();
        for (k, page) in pages.iter().enumerate() {
            self.pages += 1;
            let t = trigger(ctx, page);
            let window = self.messages.window;
            // The pasted calls and the rebuilt boxes move the indices: each
            // command keeps the one it comes from, to say where a loss is.
            let (expanded, skipped) = expand_calls(ctx.game, &page.commands);
            let origin: Vec<usize> = expanded.iter().map(|(i, _)| *i).collect();
            let expanded: Vec<Command> = expanded.into_iter().map(|(_, c)| c).collect();
            let cmds = t
                .as_ref()
                .and_then(|_| commands(&expanded))
                .map(|cmds| reflow_from(cmds, &window.measure(), window.lines));
            let from: Vec<usize> = cmds.iter().flatten().map(|(i, _)| origin[*i]).collect();
            let cmds = cmds.map(|c| c.into_iter().map(|(_, c)| c).collect::<Vec<_>>());
            let code = match cmds {
                None => None,
                Some(cmds) => {
                    let mut inner = Ctx {
                        game: ctx.game,
                        indices: ctx.indices,
                        sound: ctx.sound,
                        map_index: &|_| None,
                        messages: Some(&mut self.messages),
                        songs: ctx.songs.as_deref_mut(),
                        graphics: None,
                        pictures: None,
                        troops: None,
                        commons: None,
                        shared: None,
                        losses: std::mem::take(&mut ctx.losses),
                    };
                    let mark = inner.losses.mark();
                    inner.losses.enter(Origin::Troop { troop: number, page: k as i32 + 1 });
                    let code = compile_page(&mut inner, &cmds, None, 0, 0);
                    inner.losses.leave();
                    inner.losses.reindex_from(mark, |i| from.get(i).copied().unwrap_or(i));
                    // The calls `expand_calls` skipped, at the call's own
                    // index: after the reindexing, which is for the rebuilt
                    // list's.
                    for (i, id) in &skipped {
                        inner.losses.lose_on(
                            vec![(Origin::Troop { troop: number, page: k as i32 + 1 }, Some(*i))],
                            Some(page.commands[*i].code),
                            "call-skipped",
                            format!("common event {id} uses a command the battle has no opcode for, and the call is skipped"),
                        );
                    }
                    ctx.losses = std::mem::take(&mut inner.losses);
                    code?
                }
            };
            let (Some(t), Some(code)) = (t, code) else {
                self.left_out += 1;
                continue;
            };
            let undone: BTreeSet<i32> = page
                .commands
                .iter()
                .map(|c| c.code)
                .filter(|code| ACCEPTED_UNDONE.contains(code) || TROOP_ACCEPTED_UNDONE.contains(code))
                .collect();
            for code in undone {
                self.debts.entry(code).or_default().push((number, k));
            }
            // The header goes right in front and is part of the key: two pages
            // with the same code and another turn are two bodies. The offset
            // noted is the code's, so the ROM finds the header ten bytes
            // before it.
            let header = t.header();
            let mut key = header.clone();
            key.extend(code);
            let at = match self.where_.get(&key) {
                Some(&at) => at,
                None => {
                    let at = self.bodies.len() + header.len();
                    self.bodies.extend(&key);
                    self.where_.insert(key, at);
                    at
                }
            };
            theirs.push((t, at, k));
        }
        Ok(theirs)
    }

    pub fn to_json(&self) -> Value {
        let mut out = json!({
            "pages": self.pages,
            "left_out": self.left_out,
            "distinct": self.where_.len(),
            "per_troop": self.per_troop.iter().map(|(n, theirs)| json!([
                n,
                theirs.iter().map(|(t, at, k)| json!([t.to_json(), at, k])).collect::<Vec<_>>(),
            ])).collect::<Vec<_>>(),
            "code": crate::pages::hex(&self.bodies),
            "messages": crate::pages::hex(&self.messages.bytes()),
            "message_count": self.messages.count(),
        });
        // Only when there are some, so the answer of a game without them
        // stays the one the tests that hold its hashes expect.
        if !self.debts.is_empty() {
            out["debts"] = json!(self
                .debts
                .iter()
                .map(|(code, pages)| json!([code, pages]))
                .collect::<Vec<_>>());
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::losses::Losses;
    use crate::compile::{Indices, SoundSettings};
    use crate::game::Game;
    use crate::messages::Window;
    use rm2k_snes_bytecode::events::*;

    fn message(lines: &[&str]) -> Vec<Command> {
        lines
            .iter()
            .enumerate()
            .map(|(k, l)| {
                let code = if k == 0 { SHOW_MESSAGE } else { SHOW_MESSAGE_2 };
                Command::new(code, 1, l, vec![])
            })
            .collect()
    }

    #[test]
    fn the_inscribe_page_runs_in_battle() {
        // What `Inscribe` (switch 799) and `ControlMachines` (803) ask for,
        // and the agency captain's `TintScreen` and `TerminateBattle`.
        for (code, p) in [
            (FLASH_SCREEN, vec![0, 0, 31, 31, 5, 1]),
            (TINT_SCREEN, vec![0, 0, 0, 100, 1, 1]),
            (CHANGE_MONSTER_CONDITION, vec![0, 0, 23]),
            (TERMINATE_BATTLE, vec![]),
            (WAIT, vec![10]),
        ] {
            assert!(runs_in_battle(&Command::new(code, 1, "", p)), "{code}");
        }
    }

    #[test]
    fn an_animation_on_the_monsters_is_a_wait_and_a_debt() {
        // The Book of Three's troop 96, page 11: at turn 6 the Blazing Star,
        // three animations the page waits for, and the battle ends. Until
        // 2026-10-14 the command kept the page out, and with it the only way
        // that fight ends.
        let mut game = Game::default();
        let anim = |frames| crate::game::Animation { timings: vec![], frames, scope: 0 };
        game.animations.insert(128, anim(10));
        game.animations.insert(129, anim(0));
        let indices = Indices::default();
        let sound = SoundSettings::default();
        let mut ctx = Ctx {
            game: &game,
            indices: &indices,
            sound: &sound,
            map_index: &|_| None,
            messages: None,
            songs: None,
            graphics: None,
            pictures: None,
            troops: None,
            commons: None,
            shared: None,
            losses: Losses::default(),
        };
        let mut condition = ditto::schema::TroopPageCondition::default();
        condition.flags.turn = true;
        condition.turn_b = 6;
        let page = TroopPage {
            condition,
            commands: vec![
                Command::new(SHOW_BATTLE_ANIMATION_B, 0, "", vec![128, -1, 1]),
                Command::new(SHOW_BATTLE_ANIMATION_B, 0, "", vec![128, -1, 0]),
                Command::new(SHOW_BATTLE_ANIMATION_B, 0, "", vec![129, -1, 1]),
                Command::new(TERMINATE_BATTLE, 0, "", vec![]),
            ],
        };
        let mut pages = TroopPages::new(Messages::new(1, Window::columns(31, 4)));
        pages.compile(&mut ctx, 96, &[page]).unwrap();
        assert_eq!(pages.left_out, 0);
        // Ten frames of two ticks; the one that does not wait and the one
        // with no frames are nothing.
        let (_, at, _) = pages.per_troop[0].1[0];
        assert_eq!(&pages.bodies[at..at + 3], &[OP_DELAY, 20, 0]);
        assert_eq!(pages.bodies[at + 3], OP_BATTLE_ABORT);
        assert_eq!(pages.debts[&SHOW_BATTLE_ANIMATION_B], vec![(96, 0)]);
    }

    /// Zounds' steal mechanic: a page on switch 3 calls common event 2,
    /// which changes SP, shows a box and calls common event 65; one of its
    /// calls goes to a common event with a `Teleport`, which the battle has
    /// no stand-in for, and that call alone is skipped.
    #[test]
    fn a_call_to_a_common_event_is_pasted_in_the_battle_and_a_callee_the_battle_cannot_run_is_skipped() {
        let mut game = Game::default();
        let common = |commands: Vec<Command>| crate::game::CommonEvent {
            trigger: 0,
            switch_flag: false,
            switch_id: 1,
            commands,
        };
        game.common_events.insert(
            2,
            common(vec![
                Command::new(CHANGE_SP, 0, "", vec![0, 1, 1, 0, 5]),
                Command::new(CALL_EVENT, 0, "", vec![0, 65, 0]),
                Command::new(CALL_EVENT, 0, "", vec![0, 70, 0]),
                Command::new(END, 0, "", vec![]),
            ]),
        );
        game.common_events.insert(65, common(vec![Command::new(CONTROL_SWITCHES, 0, "", vec![0, 4, 4, 0])]));
        game.common_events.insert(70, common(vec![Command::new(TELEPORT, 0, "", vec![1, 1, 1])]));
        let page = vec![
            Command::new(COND_BRANCH, 0, "", vec![0, 3, 0]),
            Command::new(CALL_COMMON_EVENT, 1, "", vec![2]),
            Command::new(COND_END, 0, "", vec![]),
        ];
        let (expanded, skipped) = expand_calls(&game, &page);
        let codes: Vec<(usize, i32, i32)> = expanded.iter().map(|(i, c)| (*i, c.code, c.indent)).collect();
        assert_eq!(
            codes,
            vec![
                (0, COND_BRANCH, 0),
                (1, CHANGE_SP, 1),
                (1, CONTROL_SWITCHES, 1),
                (1, END, 1),
                (2, COND_END, 0),
            ],
            "the callee's body in the call's place, at the call's indent, with the call it makes pasted too"
        );
        assert_eq!(skipped, vec![(1, 70)], "the callee with the teleport is skipped, by the call's index");
        assert!(commands(&expanded.into_iter().map(|(_, c)| c).collect::<Vec<_>>()).is_some());
        // A call to a map event's page has no place in a battle; one to a
        // common event does, and so does RPG Maker 2003's own command.
        assert!(!runs_in_battle(&Command::new(CALL_EVENT, 0, "", vec![1, 5, 1])));
        assert!(runs_in_battle(&Command::new(CALL_EVENT, 0, "", vec![0, 5, 0])));
        assert!(runs_in_battle(&Command::new(CALL_COMMON_EVENT, 0, "", vec![2])));
    }

    /// Zounds' own Escape command: `ForceFlee` for the party, and nothing
    /// for an enemy, which the 2000 battle has no way to send off.
    #[test]
    fn force_flee_is_the_party_s_and_not_an_enemy_s() {
        assert!(runs_in_battle(&Command::new(FORCE_FLEE, 0, "", vec![0, 0, 1])));
        assert!(!runs_in_battle(&Command::new(FORCE_FLEE, 0, "", vec![1, 0, 1])));
        assert!(!runs_in_battle(&Command::new(FORCE_FLEE, 0, "", vec![2, 3, 0])));
        assert!(runs_in_battle(&Command::new(CHANGE_SP, 0, "", vec![0, 1, 1, 0, 5])));
    }

    /// A page conditioned on what only RPG Maker 2003 asks —an actor's
    /// command, here together with a switch— never runs in the 2000 battle,
    /// and is left out instead of running on the switch alone.
    #[test]
    fn a_page_on_a_2003_condition_never_runs() {
        let game = Game::default();
        let indices = Indices::default();
        let sound = SoundSettings::default();
        let ctx = Ctx {
            game: &game,
            indices: &indices,
            sound: &sound,
            map_index: &|_| None,
            messages: None,
            songs: None,
            graphics: None,
            pictures: None,
            troops: None,
            commons: None,
            shared: None,
            losses: Losses::default(),
        };
        let mut condition = ditto::schema::TroopPageCondition::default();
        condition.flags.switch_a = true;
        condition.switch_a_id = 3;
        let on_switch = TroopPage { condition: condition.clone(), commands: vec![] };
        assert!(trigger(&ctx, &on_switch).is_some());
        for set in [
            |f: &mut ditto::schema::TroopPageConditionFlags| f.command_actor = true,
            |f: &mut ditto::schema::TroopPageConditionFlags| f.turn_actor = true,
            |f: &mut ditto::schema::TroopPageConditionFlags| f.turn_enemy = true,
        ] {
            let mut condition = condition.clone();
            set(&mut condition.flags);
            assert!(trigger(&ctx, &TroopPage { condition, commands: vec![] }).is_none());
        }
    }

    #[test]
    fn a_comment_runs_in_battle_as_nothing() {
        for code in [COMMENT, COMMENT_2] {
            assert!(runs_in_battle(&Command::new(code, 0, "a note", vec![])), "{code}");
        }
        assert!(!runs_in_battle(&Command::new(TELEPORT, 0, "", vec![1, 1, 1])));
    }

    #[test]
    fn a_box_too_wide_for_the_battle_is_rebuilt_and_one_that_fits_is_not() {
        let mut page = message(&["MARLO", "The Admiral has sailed off in the boat!"]);
        page.push(Command::new(CONTROL_SWITCHES, 1, "", vec![0, 5, 5, 0]));
        page.extend(message(&["Nothing happens at all."]));
        let out = reflow(page, &rm2k_snes_text::refit::Measure::columns(31), 4);
        let lines: Vec<&str> = out.iter().map(|c| c.string.as_str()).collect();
        assert_eq!(
            lines,
            ["MARLO", "The Admiral has sailed off", "in the boat!", "", "Nothing happens at all."]
        );
        assert_eq!(out[3].code, CONTROL_SWITCHES);
        assert!(out.iter().all(|c| c.indent == 1));
        assert_eq!(out[1].code, SHOW_MESSAGE_2);
    }
}
