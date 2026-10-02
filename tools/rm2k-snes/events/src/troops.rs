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
//! `Scene_Battle_Rpg2k`; see `ba_page_test` in tools/runtime/battle_troop.s.

use crate::codes::*;
use crate::compile::{compile_page, Ctx};
use crate::fail::Result;
use crate::game::{Command, TroopPage};
use crate::indices::battle_branch;
use crate::messages::Messages;
use crate::registry::Package;
use serde_json::{json, Value};
use std::collections::HashMap;

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
/// The ones left out that the game uses, in case someone wants to add them:
/// `FlashScreen`, `Wait`, `TintScreen`, `ChangeMonsterCondition` —the battle
/// has no states— and `TerminateBattle`.
const TROOP_COMMANDS: [i32; 23] = [
    END,
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
    CHANGE_MONSTER_HP,
    CHANGE_MONSTER_MP,
    SHOW_HIDDEN_MONSTER,
    COND_BRANCH,
    COND_ELSE,
    COND_END,
    MESSAGE_OPTIONS,
];

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
/// How many switches the ROM's bitmap holds.
const SWITCH_MAX: i32 = 1024;

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
    /// that. The order is `BA_COND`'s in tools/runtime/far_ram.s.
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
fn trigger(ctx: &Ctx, page: &TroopPage) -> Option<Trigger> {
    let c = &page.condition;
    let f = &c.flags;
    if !(f.switch_a || f.switch_b || f.variable || f.turn || f.fatigue || f.enemy_hp || f.actor_hp)
    {
        return None;
    }
    if f.fatigue {
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
    if !(0..SWITCH_MAX).contains(&t.switch_a) || !(0..SWITCH_MAX).contains(&t.switch_b) {
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

/// A troop page's commands as a map's, or None if one does not run in a
/// troop page.
fn commands(raw: &[Command]) -> Option<Vec<Command>> {
    let mut out = Vec::new();
    for cmd in raw {
        let code = battle_branch(cmd.code);
        if cmd.code == BATTLE_COND_BRANCH && !matches!(cmd.parameters.first(), Some(0) | Some(1)) {
            return None;
        }
        if !TROOP_COMMANDS.contains(&code) {
            return None;
        }
        out.push(Command {
            code,
            ..cmd.clone()
        });
    }
    Some(out)
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
        let result = self.pages_of(ctx, pages);
        if let Some(songs) = ctx.songs.as_deref_mut() {
            songs.current = previous;
        }
        self.per_troop.push((number, result?));
        Ok(())
    }

    fn pages_of(&mut self, ctx: &mut Ctx, pages: &[TroopPage]) -> Result<Vec<Entry>> {
        let mut theirs = Vec::new();
        for (k, page) in pages.iter().enumerate() {
            self.pages += 1;
            let t = trigger(ctx, page);
            let cmds = t.as_ref().and_then(|_| commands(&page.commands));
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
                    };
                    compile_page(&mut inner, &cmds, None, 0, 0)?
                }
            };
            let (Some(t), Some(code)) = (t, code) else {
                self.left_out += 1;
                continue;
            };
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
        json!({
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
        })
    }
}
