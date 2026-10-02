//! The common events compiled **once**, apart from every map: the automatic
//! ones, the ones the pages call, and every one those call.
//!
//! RM2k runs an automatic common event —trigger 3— whenever its switch is
//! on, on whatever map, exactly like an automatic page of the map. Here its
//! body is compiled a single time, without a map —no events to name, no
//! audio package to note effects in, no pictures—, and the ROM looks at its
//! switch each time the foreground interpreter is free: see `common_start`
//! in tools/runtime/common_events.s, and easyrpg's
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
use crate::compile::{compile_page, Ctx, Indices, SoundSettings};
use crate::fail::{Bad, Result};
use crate::game::{Command, Game};
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
}

impl Shared {
    pub fn to_json(&self) -> Value {
        json!({
            "bodies": self.bodies.iter().map(|(n, code)| json!([n, crate::pages::hex(code)])).collect::<Vec<_>>(),
            "autostart": self.autostart,
            "depth": self.depth,
            "left_out": self.left_out,
        })
    }
}

/// The automatic common events that can run: with a switch and with
/// something to run. One without a switch runs always, from the first
/// frame —RM2k does it—; this compiler does not take those, because a ROM
/// that runs one forever cannot be played, and no game was seen to have one.
pub fn automatic(game: &Game) -> Vec<(i32, i32)> {
    game.common_events
        .iter()
        .filter(|(_, c)| c.trigger == COMMON_AUTOSTART && c.switch_flag && !c.commands.is_empty())
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
) -> Result<Option<Vec<u8>>> {
    let commands = &s.game.common_events[&number].commands;
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
    };
    compile_page(&mut ctx, commands, None, 0, 0)
}

/// Which bodies there are and their indices, decided before compiling any
/// page.
#[derive(Debug, Clone, Default)]
pub struct Plan {
    /// Each kept body's common event number and its index.
    pub index: BTreeMap<i32, u8>,
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
    let roots = automatic(s.game);
    let reach = |starts: Vec<i32>, only: Option<&BTreeSet<i32>>| {
        let keep = |n: &i32| only.is_none_or(|o| o.contains(n));
        let mut seen: BTreeSet<i32> = BTreeSet::new();
        let mut pending: Vec<i32> = starts.into_iter().filter(keep).collect();
        while let Some(n) = pending.pop() {
            if seen.insert(n) {
                pending.extend(
                    callees(s.game, &s.game.common_events[&n].commands)
                        .into_iter()
                        .filter(keep),
                );
            }
        }
        seen
    };
    let starts: Vec<i32> = roots
        .iter()
        .map(|&(n, _)| n)
        .chain(from_pages.iter().copied())
        .collect();
    let reached = reach(starts.clone(), None);
    let every: BTreeMap<i32, u8> = reached.iter().map(|&n| (n, 0)).collect();
    let mut compiles = BTreeSet::new();
    for &n in &reached {
        let mut m = Messages::measuring(messages.step, messages.window);
        let mut so = songs.clone();
        let mut t = Troops::default();
        if body(s, n, &every, &mut m, &mut so, &mut t)?.is_some() {
            compiles.insert(n);
        }
    }
    let kept = reach(starts, Some(&compiles));
    if kept.len() > BODIES_MAX {
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
) -> Result<Shared> {
    let mut shared = Shared::default();
    for &n in plan.index.keys() {
        let Some(code) = body(s, n, &plan.index, messages, songs, troops)? else {
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
        for c in callees(game, &game.common_events[&n].commands) {
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
