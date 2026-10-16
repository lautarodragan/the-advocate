//! The common events compiled **once**, apart from every map: the automatic
//! ones, the ones the pages call, and every one those call.
//!
//! RM2k runs an automatic common event —trigger 3— whenever its switch is
//! on, on whatever map, exactly like an automatic page of the map. Here its
//! body is compiled a single time, without a map —no events to name, no
//! audio package to note effects in, no pictures—, and the ROM looks at its
//! switch each time the foreground interpreter is free: see `common_start`
//! in runtime/common_events.s, and easyrpg's
//! `Game_Map::UpdateForegroundEvents`, which is what it copies.
//!
//! A `CallEvent` inside one of these bodies is **not** pasted in place: it is
//! an `OP_CALL` to the callee's own body, which returns with `OP_RETURN`.
//! That is RM2k's stack of frames, and it is what makes a menu built of calls
//! fit: pasted, common event 39 of the game this was written for, which calls
//! 21, which calls 25 eighteen times, which calls eight others, is more than
//! a hundred thousand commands; shared, each body is there once. A map's
//! page that runs in the foreground calls one too, when the body compiled
//! with the map is the same as without it: see `shares` in
//! [`crate::compile`].
//!
//! **Which bodies there are** is decided before compiling any page —the
//! [`Plan`]—, because the `OP_CALL` carries the callee's index: a body
//! compiles or not on its own —a call to one that does not compile is
//! skipped, as a pasted one is—, so a pass with throwaway registries says
//! which compile, and the ones that are kept are those reachable from an
//! automatic one or a page through bodies that compile. They are compiled
//! for real after every page, in the order of their numbers, with the same
//! registries: what they number goes at the end and moves nobody's index.

use crate::codes::*;
use rm2k_snes_bytecode::events::{OP_DONE, OP_MENU_OPEN, OP_RETURN, OP_SWITCH};
use crate::compile::{
    compile_page, Ctx, Indices, SoundSettings, COND_ACTOR, COND_ACTOR_EQUIPMENT, COND_SWITCH,
};
use crate::fail::{Bad, Result};
use crate::game::{Command, Game};
use crate::losses::{Losses, Origin};
use crate::messages::Messages;
use crate::registry::{Songs, Troops};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};

/// RM2k's trigger of a common event that runs on its own while its switch
/// is on.
const COMMON_AUTOSTART: i32 = TRIGGER_AUTOSTART;
/// How many bodies an `OP_CALL`'s byte can name.
const BODIES_MAX: usize = 256;

/// The shared bodies, in the order of their index.
#[derive(Debug, Clone, Default)]
pub struct Shared {
    /// Each body's common event number and its bytecode.
    pub bodies: Vec<(i32, Vec<u8>)>,
    /// The automatic ones: the switch that turns each on and its body's
    /// index, in the order of their numbers, which is the order RM2k looks
    /// at them in.
    pub autostart: Vec<(i32, u8)>,
    /// The deepest chain of frames, counting the automatic body or the page
    /// that calls as 1: the ROM's call stack has to hold one entry less. None
    /// if the calls make a loop, which only the ROM's cap stops.
    pub depth: Option<usize>,
    /// The common events an automatic one may reach that do not compile,
    /// automatic ones included: for the converter's report.
    pub left_out: Vec<i32>,
    /// The bodies a custom menu runs before a page: each common event's
    /// number and the index of its body without messages —see
    /// [`before_commands`]—, after every other body.
    pub menu_before: Vec<(i32, u8)>,
}

impl Shared {
    pub fn to_json(&self) -> Value {
        json!({
            "bodies": self.bodies.iter().map(|(n, code)| json!([n, crate::pages::hex(code)])).collect::<Vec<_>>(),
            "autostart": self.autostart,
            "depth": self.depth,
            "left_out": self.left_out,
            "menu_before": self.menu_before,
        })
    }
}

/// The automatic common events that can run: with a switch and with
/// something to run. One without a switch runs always, from the first
/// frame —RM2k does it—; this compiler does not take those, because a ROM
/// that runs one forever cannot be played, and no game was seen to have one.
pub fn automatic(game: &Game, indices: &Indices) -> Vec<(i32, i32)> {
    game.common_events
        .iter()
        .filter(|(_, c)| c.trigger == COMMON_AUTOSTART && c.switch_flag && !c.commands.is_empty())
        // A switch past the ROM's table: `common_start` would read past
        // `switches`. The table holds every switch the game names —see
        // `indices::switch_top`—, so it guards a mistake, not a game.
        .filter(|(_, c)| indices.holds_switch(c.switch_id as i64))
        .map(|(&n, c)| (n, c.switch_id))
        .collect()
}

/// The common events these commands call by number, which can become an
/// `OP_CALL`. Not the counters: those are their own opcode.
pub fn callees(game: &Game, commands: &[Command]) -> BTreeSet<i32> {
    commands
        .iter()
        .filter(|c| c.code == CALL_EVENT && c.parameters.len() >= 2 && c.parameters[0] == 0)
        .map(|c| c.parameters[1])
        .filter(|n| game.common_events.contains_key(n) && !game.patches.counters.contains_key(n))
        .collect()
}

/// The common events common event `n`'s body calls: none if a custom menu
/// replaces it, since its body is the menu's opcode and not its commands.
fn calls_of(game: &Game, n: i32) -> BTreeSet<i32> {
    if game.patches.menus.replaced.contains_key(&n) {
        return BTreeSet::new();
    }
    callees(game, &game.common_events[&n].commands)
}

/// What a common event a custom menu replaces compiles to, wherever it
/// runs or is called: the menu's opcode, and its switch turned off, which
/// is what the game's own body did when the menu closed —and an automatic
/// common event that does not turn it off runs forever—. Without the
/// `OP_RETURN` or `OP_DONE`, which belong to who carries it.
pub fn menu_open(game: &Game, n: i32) -> Vec<u8> {
    let mut out = vec![OP_MENU_OPEN, game.patches.menus.replaced[&n]];
    let c = &game.common_events[&n];
    if c.switch_flag {
        out.push(OP_SWITCH);
        out.extend((c.switch_id as u16).to_le_bytes());
        out.push(0);
    }
    out
}

/// What a common event a custom menu runs before a page can do: what
/// changes the game's state without waiting. The menu runs it to its end
/// before drawing, inside one frame, so a message would never be read and a
/// wait would never end; the messages and the pictures, which only showed
/// what it counted, are left out —the menu's page shows it instead—, and
/// anything else is refused.
const BEFORE_KEEPS: [i32; 13] = [
    END, CONTROL_SWITCHES, CONTROL_VARS, COND_BRANCH, COND_ELSE, COND_END, LABEL, JUMP_TO_LABEL,
    CALL_EVENT, COMMENT, COMMENT_2, LOOP, END_LOOP,
];
const BEFORE_DROPS: [i32; 6] = [SHOW_MESSAGE, SHOW_MESSAGE_2, SHOW_PICTURE, MOVE_PICTURE, ERASE_PICTURE, PLAY_SOUND];

/// Common event `n`'s commands as a custom menu runs it before a page.
pub fn before_commands(game: &Game, n: i32) -> Result<Vec<Command>> {
    let mut out = Vec::new();
    for c in &game.common_events[&n].commands {
        if BEFORE_DROPS.contains(&c.code) {
            continue;
        }
        if !BEFORE_KEEPS.contains(&c.code) && c.code != BREAK_LOOP {
            return Err(Bad::answer(format!(
                "common event {n} runs before a custom menu's page, and command {} is not one the \
                 menu can run inside a frame: only switches, variables, branches, labels, loops and \
                 calls",
                c.code
            )));
        }
        out.push(c.clone());
    }
    Ok(out)
}

/// What a shared body is compiled with besides its registries.
pub struct Setting<'a> {
    pub game: &'a Game,
    pub indices: &'a Indices,
    pub sound: &'a SoundSettings,
    pub map_index: &'a dyn Fn(i64) -> Option<usize>,
}

/// One body, with whatever registries it is given.
fn body(
    s: &Setting,
    number: i32,
    commons: &BTreeMap<i32, u8>,
    messages: &mut Messages,
    songs: &mut Songs,
    troops: &mut Troops,
    losses: &mut Losses,
) -> Result<Option<Vec<u8>>> {
    body_of(s, number, commons, messages, songs, troops, false, losses)
}

/// [`body`], or with `before` the one a custom menu runs before a page.
/// What it loses goes to `losses`, under the common event.
#[allow(clippy::too_many_arguments)]
fn body_of(
    s: &Setting,
    number: i32,
    commons: &BTreeMap<i32, u8>,
    messages: &mut Messages,
    songs: &mut Songs,
    troops: &mut Troops,
    before: bool,
    losses: &mut Losses,
) -> Result<Option<Vec<u8>>> {
    if !before && s.game.patches.menus.replaced.contains_key(&number) {
        let mut code = menu_open(s.game, number);
        code.push(OP_RETURN);
        return Ok(Some(code));
    }
    let stripped;
    let commands: &[Command] = if before {
        stripped = before_commands(s.game, number)?;
        &stripped
    } else {
        &s.game.common_events[&number].commands
    };
    let mut ctx = Ctx {
        game: s.game,
        indices: s.indices,
        sound: s.sound,
        map_index: s.map_index,
        messages: Some(messages),
        songs: Some(songs),
        graphics: None,
        pictures: None,
        troops: Some(troops),
        commons: Some(commons),
        shared: None,
        losses: std::mem::take(losses),
        face: None,
    };
    ctx.losses.enter(Origin::Common(number));
    let code = compile_page(&mut ctx, commands, None, 0, 0);
    ctx.losses.leave();
    *losses = ctx.losses;
    code
}

/// Which bodies there are and their indices, decided before compiling any
/// page.
#[derive(Debug, Clone, Default)]
pub struct Plan {
    /// Each kept body's common event number and its index.
    pub index: BTreeMap<i32, u8>,
    /// The bodies the custom menus run before a page, after the kept ones.
    pub before: BTreeMap<i32, u8>,
    roots: Vec<(i32, i32)>,
    from_pages: BTreeSet<i32>,
    left_out: Vec<i32>,
}

/// The plan: which of the common events an automatic one or a page may
/// reach compile as a shared body. `from_pages` are the ones the pages that
/// may call call by number: see `shared` in [`Ctx`].
///
/// Each one is compiled on its own, with throwaway registries and every
/// candidate given an index —a call compiles the same whether its callee
/// does or not—, and the ones kept are those reachable through bodies that
/// compile.
pub fn plan(
    s: &Setting,
    from_pages: BTreeSet<i32>,
    messages: &Messages,
    songs: &Songs,
) -> Result<Plan> {
    let roots = automatic(s.game, s.indices);
    let reach = |starts: Vec<i32>, only: Option<&BTreeSet<i32>>| {
        let keep = |n: &i32| only.is_none_or(|o| o.contains(n));
        let mut seen: BTreeSet<i32> = BTreeSet::new();
        let mut pending: Vec<i32> = starts.into_iter().filter(keep).collect();
        while let Some(n) = pending.pop() {
            if seen.insert(n) {
                pending.extend(calls_of(s.game, n).into_iter().filter(keep));
            }
        }
        seen
    };
    // And what the menus' bodies call: those bodies are compiled apart,
    // without their messages, but what they call is a body like any other.
    let mut before_calls = BTreeSet::new();
    for &n in &s.game.patches.menus.before {
        if !s.game.common_events.contains_key(&n) {
            return Err(Bad::answer(format!("a custom menu runs common event {n}, and there is none")));
        }
        before_calls.extend(callees(s.game, &before_commands(s.game, n)?));
    }
    let starts: Vec<i32> = roots
        .iter()
        .map(|&(n, _)| n)
        .chain(from_pages.iter().copied())
        .chain(before_calls)
        .collect();
    let reached = reach(starts.clone(), None);
    let every: BTreeMap<i32, u8> = reached.iter().map(|&n| (n, 0)).collect();
    let mut compiles = BTreeSet::new();
    for &n in &reached {
        let mut m = Messages::measuring(messages.step, messages.window);
        let mut so = songs.clone();
        let mut t = Troops::default();
        if body(s, n, &every, &mut m, &mut so, &mut t, &mut Losses::default())?.is_some() {
            compiles.insert(n);
        }
    }
    let kept = reach(starts, Some(&compiles));
    if kept.len() + s.game.patches.menus.before.len() > BODIES_MAX {
        return Err(Bad::answer(format!(
            "{} shared common event bodies, and OP_CALL names {BODIES_MAX}",
            kept.len()
        )));
    }
    let from_automatic = reach(roots.iter().map(|&(n, _)| n).collect(), None);
    Ok(Plan {
        index: kept
            .iter()
            .enumerate()
            .map(|(i, &n)| (n, i as u8))
            .collect(),
        before: s
            .game
            .patches
            .menus
            .before
            .iter()
            .enumerate()
            .map(|(k, &n)| (n, (kept.len() + k) as u8))
            .collect(),
        roots,
        from_pages,
        left_out: from_automatic.difference(&compiles).copied().collect(),
    })
}

/// The shared bodies, compiled with the cartridge's registries after every
/// page. Songs and effects are numbered but noted in no package
/// —`songs.current` is None—: a page that calls one noted its effects in
/// its map's package when it chose to call it, and an automatic one's play
/// only where the map's package already carries them.
pub fn compile(
    s: &Setting,
    plan: &Plan,
    messages: &mut Messages,
    songs: &mut Songs,
    troops: &mut Troops,
    losses: &mut Losses,
) -> Result<Shared> {
    let mut shared = Shared::default();
    for &n in plan.index.keys() {
        let Some(code) = body(s, n, &plan.index, messages, songs, troops, losses)? else {
            return Err(Bad::answer(format!(
                "common event {n} compiled on its own and not with the cartridge's registries"
            )));
        };
        shared.bodies.push((n, code));
    }
    shared.autostart = plan
        .roots
        .iter()
        .filter_map(|&(n, switch)| plan.index.get(&n).map(|&i| (switch, i)))
        .collect();
    for (&n, &index) in &plan.before {
        let Some(code) = body_of(s, n, &plan.index, messages, songs, troops, true, losses)? else {
            return Err(Bad::answer(format!(
                "common event {n}, which a custom menu runs before a page, does not compile"
            )));
        };
        debug_assert_eq!(index as usize, shared.bodies.len());
        shared.bodies.push((n, code));
        shared.menu_before.push((n, index));
    }
    shared.depth = depth(s.game, plan);
    shared.left_out = plan.left_out.clone();
    Ok(shared)
}

/// The longest chain of frames: from an automatic body, or from a page that
/// calls one —which counts one more—, through the kept bodies; None if they
/// loop. A page that may call is counted whether it ends up calling or
/// pasting: it is a bound.
fn depth(game: &Game, plan: &Plan) -> Option<usize> {
    fn walk(
        game: &Game,
        kept: &BTreeMap<i32, u8>,
        n: i32,
        open: &mut BTreeSet<i32>,
        memo: &mut BTreeMap<i32, usize>,
    ) -> Option<usize> {
        if let Some(&d) = memo.get(&n) {
            return Some(d);
        }
        if !open.insert(n) {
            return None;
        }
        let mut deepest = 0;
        for c in calls_of(game, n) {
            if kept.contains_key(&c) {
                deepest = deepest.max(walk(game, kept, c, open, memo)?);
            }
        }
        open.remove(&n);
        memo.insert(n, deepest + 1);
        Some(deepest + 1)
    }
    let mut memo = BTreeMap::new();
    let mut deepest = 0;
    let starts = plan
        .roots
        .iter()
        .map(|&(n, _)| (n, 0))
        .chain(plan.from_pages.iter().map(|&n| (n, 1)));
    for (n, extra) in starts {
        if plan.index.contains_key(&n) {
            deepest =
                deepest.max(extra + walk(game, &plan.index, n, &mut BTreeSet::new(), &mut memo)?);
        }
    }
    Some(deepest)
}

/// What a **pure** parallel common event may have: branches on a switch or
/// on what an actor has equipped, and the commands that only set a state
/// —its skills, the three permissions—, with their block ends and comments.
const PURE_KEEPS: [i32; 10] = [
    COND_BRANCH, COND_ELSE, COND_END, END, CHANGE_SKILLS, CHANGE_SAVE_ACCESS, CHANGE_MENU_ACCESS,
    CHANGE_ESCAPE_ACCESS, COMMENT, COMMENT_2,
];

/// Whether a parallel common event is pure: it only reads switches and the
/// equipment, and only writes skills and permissions. One of those gives the
/// same result on every frame until what it reads changes, or until
/// something else writes what it writes —a page's `ChangeSaveAccess`
/// against the game's `EnableSaving`—, and it never waits, so the ROM runs
/// it only on the frame after one of those: see `compar_tick` in
/// runtime/common_events.s. In the game this was written for they are
/// three: 2 `DisableSaving`, 8 `EnableSaving` and 37 `UpdateAG7 Skills`,
/// whose body every frame was measured on 2026-09-27 at about an eighth of
/// the frame's CPU.
///
/// What is left out: an actor that learns, by levelling up, a skill a pure
/// one takes away keeps it until the next run.
pub fn pure(commands: &[Command]) -> bool {
    commands.iter().all(|c| {
        PURE_KEEPS.contains(&c.code)
            && (c.code != COND_BRANCH
                || c.p(0) == Some(COND_SWITCH)
                || (c.p(0) == Some(COND_ACTOR) && c.p(2) == Some(COND_ACTOR_EQUIPMENT)))
    })
}

/// The parallel common events —trigger 4, with commands—, each compiled
/// once and without a map, as `[number, switch, pure, code]`: the switch
/// that turns it on, 0 if it has none and runs always; whether it is
/// [`pure`]; and its bytecode, or null if it does not compile.
///
/// RM2k gives each one **its own interpreter**, which runs every frame while
/// the switch is on, before the map's parallel pages: easyrpg's
/// `Game_Map::UpdateCommonEvents` and `Game_CommonEvent::Update`. The ROM
/// does the same —see `compar_tick` in runtime/common_events.s—, so these
/// bodies are pages that end in `OP_DONE` and start over on the next frame,
/// like a map's parallel page.
///
/// A `CallEvent` in them is **pasted**, as in a map's parallel page: the
/// ROM has one call stack, the foreground's, and a parallel that waits in
/// the middle of a call would hold it across frames. Songs and effects are
/// numbered but noted in no package, as in the shared bodies.
pub fn parallel_commons(
    s: &Setting,
    messages: &mut Messages,
    songs: &mut Songs,
    troops: &mut Troops,
    losses: &mut Losses,
) -> Result<Vec<Value>> {
    let mut out = Vec::new();
    for (&number, c) in &s.game.common_events {
        if c.trigger != COMMON_PARALLEL || c.commands.is_empty() {
            continue;
        }
        let code = if c.switch_flag && !s.indices.holds_switch(c.switch_id as i64) {
            // A switch past the ROM's table: the ROM would read it out of
            // bounds.
            None
        } else if s.game.patches.menus.replaced.contains_key(&number) {
            let mut code = menu_open(s.game, number);
            code.push(OP_DONE);
            Some(code)
        } else {
            let mut ctx = Ctx {
                game: s.game,
                indices: s.indices,
                sound: s.sound,
                map_index: s.map_index,
                messages: Some(&mut *messages),
                songs: Some(&mut *songs),
                graphics: None,
                pictures: None,
                troops: Some(&mut *troops),
                commons: None,
                shared: None,
                losses: std::mem::take(losses),
                face: None,
            };
            ctx.losses.enter(Origin::Common(number));
            let code = compile_page(&mut ctx, &c.commands, None, 0, 0);
            ctx.losses.leave();
            *losses = std::mem::take(&mut ctx.losses);
            code?
        };
        let switch = if c.switch_flag { c.switch_id } else { 0 };
        out.push(json!([
            number,
            switch,
            pure(&c.commands),
            code.map(|c| crate::pages::hex(&c))
        ]));
    }
    Ok(out)
}
