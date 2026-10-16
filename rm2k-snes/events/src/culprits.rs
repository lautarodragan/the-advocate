//! Which commands keep each page out of the cartridge: the report that
//! answers "what is left to implement?" over a whole game, and not one page
//! at a time.
//!
//! A page that does not compile is left out whole —see the README—, and the
//! compiler knows which command it stopped at: see
//! [`crate::compile::judged_page`]. That is one culprit, the first; a page
//! can have more behind it. So each page is **chased**: the culprit is
//! noted and taken out —turned into a `Comment`, which compiles to
//! nothing—, and the page is compiled again, until it compiles or stops at
//! something that cannot be taken out. What is left is every command that
//! keeps that page out, and so the pages that **only one** keeps out: the
//! ones that command would let in.
//!
//! Taking a command out is not what the command does —that is the point—,
//! so the page that compiles at the end of the chase is not a page to run:
//! it is only how the next culprit is found. A `ConditionalBranch` is not
//! taken out but turned into a question the compiler knows —switch 1 on—,
//! so its body and its `else` are still looked at.
//!
//! Three kinds of page, each as the cartridge compiles it:
//!
//! * a map's, with its map, on its own —the way `scan` compiles it—;
//! * a common event's, without a map, the way the shared bodies are
//!   compiled: a call to another is a call, not the other's body;
//! * a troop's, with the battle's list of commands —see `TROOP_COMMANDS`—
//!   and its window: every command outside the list is a culprit, and a
//!   trigger the ROM cannot look at too.
//!
//! A command is counted by its **family**: an `else` or the end of a block
//! by its opener, a choice's option by the choice, a battle's handlers by the
//! battle. What a page needs is the command, not the half of it.

use crate::codes::*;
use crate::compile::{judged_page, Culprit, Ctx, Indices, SoundSettings};
use crate::losses::Losses;
use crate::fail::{Result, Stop};
use crate::game::{Command, Game, TroopPage};
use crate::messages::{Messages, Window};
use crate::pages::{MapEvents, Substitutions};
use crate::registry::{Graphics, Songs};
use crate::troops;
use crate::Request;
use ditto::schema::EventCommandCode;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::rc::Rc;

/// The file the report is written to.
pub const ANSWER_FILE: &str = "culprits.json";

/// What a page's chase found.
#[derive(Debug, Clone, Default)]
pub struct Chase {
    /// Every command that kept the page out, in the order they were found,
    /// with its index in the page.
    pub culprits: Vec<(usize, Command)>,
    /// The page's trigger is one the ROM cannot look at: only troop pages.
    pub trigger: bool,
    /// It stopped at the page as a whole —a block left open, a jump out of
    /// its body— or at a culprit already taken out: what is left cannot be
    /// pinned on a command.
    pub whole: bool,
    /// It stopped the conversion: where —see [`Culprit`]— and with what
    /// message. A cartridge that carried the page would not build; only the
    /// report goes on after one.
    pub fatal: Option<(Culprit, String)>,
}

/// One compilation: Ok if the page compiles, or why not and where.
type Judgement = std::result::Result<(), (Stop, Culprit)>;

impl Chase {
    pub fn compiles(&self) -> bool {
        self.culprits.is_empty() && !self.trigger && !self.whole && self.fatal.is_none()
    }

    /// The families of its culprits.
    fn families(&self) -> BTreeSet<i32> {
        self.culprits.iter().map(|(_, c)| family(c.code)).collect()
    }

    /// Whether the family `code` is all that keeps it out.
    fn only(&self, code: i32) -> bool {
        !self.trigger && !self.whole && self.fatal.is_none() && self.families() == BTreeSet::from([code])
    }
}

/// The command a part of a command belongs to: the one a page has to be
/// able to do for the part to mean anything.
pub fn family(code: i32) -> i32 {
    match code {
        SHOW_MESSAGE_2 => SHOW_MESSAGE,
        SHOW_CHOICE_OPTION | SHOW_CHOICE_END => SHOW_CHOICE,
        VICTORY_HANDLER | ESCAPE_HANDLER | DEFEAT_HANDLER | END_BATTLE => ENEMY_ENCOUNTER,
        SHOP_TRANSACTION | SHOP_NO_TRANSACTION | SHOP_END => OPEN_SHOP,
        INN_STAY | INN_NO_STAY | INN_END => SHOW_INN,
        COND_ELSE | COND_END => COND_BRANCH,
        BATTLE_COND_ELSE | BATTLE_COND_END => BATTLE_COND_BRANCH,
        END_LOOP | BREAK_LOOP => LOOP,
        COMMENT_2 => COMMENT,
        c => c,
    }
}

/// liblcf's name for a command code.
pub fn name(code: i32) -> String {
    match EventCommandCode::from_i32(code) {
        EventCommandCode::Other(v) => format!("({v})"),
        c => format!("{c:?}"),
    }
}

/// What a culprit is turned into so the chase can go on: see the module.
fn taken_out(cmd: &Command) -> Command {
    if cmd.code == COND_BRANCH {
        // Switch 1, on; the rest —whether it has an `else`— as it was.
        let mut p = cmd.parameters.clone();
        p.resize(p.len().max(6), 0);
        p[..5].copy_from_slice(&[0, 1, 0, 0, 0]);
        return Command::new(COND_BRANCH, cmd.indent, "", p);
    }
    Command::new(COMMENT, cmd.indent, "", vec![])
}

/// Compiles `commands` over and over, taking out each culprit, with `judge`:
/// Ok if it compiles, or the command it stopped at. `chase` takes care of the
/// rest.
fn chase<F>(mut commands: Vec<Command>, mut judge: F) -> Chase
where
    F: FnMut(&[Command]) -> Judgement,
{
    let mut out = Chase::default();
    let mut out_already = BTreeSet::new();
    loop {
        match judge(&commands) {
            Ok(()) => return out,
            Err((Stop::Cannot, Some(i))) if out_already.insert(i) => {
                out.culprits.push((i, commands[i].clone()));
                commands[i] = taken_out(&commands[i]);
            }
            Err((Stop::Cannot, _)) => {
                out.whole = true;
                return out;
            }
            Err((Stop::Fatal(bad), at)) => {
                out.fatal = Some((at, bad.message().to_string()));
                return out;
            }
        }
    }
}

/// Where a page is.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum Place {
    /// Map, event id, page number from one.
    Map(i32, i32, usize),
    /// The common event's number.
    Common(i32),
    /// Troop, page number from one.
    Troop(i32, usize),
}

impl Place {
    fn kind(&self) -> &'static str {
        match self {
            Place::Map(..) => "maps",
            Place::Common(_) => "commons",
            Place::Troop(..) => "troops",
        }
    }

    fn to_json(self) -> Value {
        match self {
            Place::Map(m, e, p) => json!({"map": m, "event": e, "page": p}),
            Place::Common(n) => json!({"common": n}),
            Place::Troop(t, p) => json!({"troop": t, "page": p}),
        }
    }
}

/// One page: where, its trigger —RM2k's number; a troop's is none—, its
/// commands as the game has them, and what the chase found.
pub struct Judged {
    pub place: Place,
    pub trigger: Option<i32>,
    pub commands: Vec<Command>,
    pub chase: Chase,
    /// The common events a map's page calls whose body does not compile
    /// **with the page's map**, each with its chase. The page does not
    /// stop for them —a call whose body does not compile is skipped, see
    /// `compile_call`—, so this is what is lost without a page being left
    /// out: the losses no count of pages shows.
    pub skipped: Vec<(i32, Chase)>,
}

/// Every page of the maps —the request's, or every map of the game with
/// `every_map`—, every common event and every troop page, chased.
pub fn judge_game(game: &Game, request: &Request, every_map: bool) -> Result<Vec<Judged>> {
    let mut request = request.clone();
    if every_map {
        request.maps = game.map_ids.clone();
    }
    let (indices, _, maps) = crate::prepare(game, &request)?;
    let order: HashMap<i64, usize> =
        request.maps.iter().enumerate().map(|(i, &m)| (m as i64, i)).collect();
    let map_index = |m: i64| order.get(&m).copied();
    let sound = SoundSettings::default();
    let window = request.window();
    let mut out = Vec::new();

    // See the common events below.
    let every_common: BTreeMap<i32, u8> = game.common_events.keys().map(|&n| (n, 0)).collect();
    for map in &maps {
        // The `TileSubstitution`s as the request resolved them, if it did
        // —`compile`'s request does, for its maps—: without them one does not
        // compile, and that is the converter missing, not the command.
        let subs = request.substitutions.get(&map.id).map(|table| {
            Rc::new(Substitutions {
                table: table.clone(),
                ..Default::default()
            })
        });
        let me = MapEvents::new(map, subs).numbered(map, &indices);
        for event in &map.events {
            for (k, page) in event.pages.iter().enumerate() {
                let found = chase(page.commands.clone(), |commands| {
                    judge(game, &indices, &sound, &map_index, window, commands, Some(me.for_event(event.id)), None, false)
                });
                let mut skipped = Vec::new();
                for n in pasted_commons(game, &page.commands) {
                    let body = game.common_events[&n].commands.clone();
                    let callee = chase(body, |commands| {
                        let me = Some(me.for_event(event.id));
                        judge(game, &indices, &sound, &map_index, window, commands, me, Some(&every_common), false)
                    });
                    if !callee.compiles() {
                        skipped.push((n, callee));
                    }
                }
                out.push(Judged {
                    place: Place::Map(map.id, event.id, k + 1),
                    trigger: Some(page.trigger),
                    commands: page.commands.clone(),
                    chase: found,
                    skipped,
                });
            }
        }
    }

    // Each common event as a shared body, where a `CallEvent` to another is
    // an `OP_CALL` and not the other's body pasted: so each one answers for
    // its own commands. Pasting, a chain of calls can outgrow the 64 KB a
    // page's destinations address, which the cartridge never does —it calls
    // what the foreground pages call— and would stop the report. Without a
    // map, so what a common event does to a map's event is a culprit here
    // even if it compiles where it is called: `skipped` says that.
    for (&number, common) in &game.common_events {
        let found = chase(common.commands.clone(), |commands| {
            judge(game, &indices, &sound, &map_index, window, commands, None, Some(&every_common), true)
        });
        out.push(Judged {
            place: Place::Common(number),
            trigger: Some(common.trigger),
            commands: common.commands.clone(),
            chase: found,
            skipped: vec![],
        });
    }

    let troop_window = request.troop_window.unwrap_or(window);
    for (&number, pages) in &game.troops {
        for (k, page) in pages.iter().enumerate() {
            out.push(Judged {
                place: Place::Troop(number, k + 1),
                trigger: None,
                commands: page.commands.clone(),
                chase: chase_troop_page(game, &indices, &sound, troop_window, page)?,
                skipped: vec![],
            });
        }
    }
    Ok(out)
}

/// The common events `commands` call that `compile_call` pastes: the ones
/// the project turns into something else —a counter, a custom menu— are
/// not.
fn pasted_commons(game: &Game, commands: &[Command]) -> BTreeSet<i32> {
    commands
        .iter()
        .filter(|c| c.code == CALL_EVENT && c.parameters.len() >= 2 && c.parameters[0] == 0)
        .map(|c| c.parameters[1])
        .filter(|n| game.common_events.contains_key(n))
        .filter(|n| !game.patches.counters.contains_key(n) && !game.patches.menus.replaced.contains_key(n))
        .collect()
}

/// One compilation of a map's page or a common event, with what `scan`
/// compiles each page with: a text block, songs and graphics of its own.
/// `commons` as in [`Ctx::commons`].
#[allow(clippy::too_many_arguments)]
fn judge(
    game: &Game,
    indices: &Indices,
    sound: &SoundSettings,
    map_index: &dyn Fn(i64) -> Option<usize>,
    window: Window,
    commands: &[Command],
    map_events: Option<MapEvents>,
    commons: Option<&BTreeMap<i32, u8>>,
    shared_body: bool,
) -> Judgement {
    let mut messages = Messages::new(1, window);
    let mut songs = Songs::default();
    let mut graphics = Graphics::default();
    let mut ctx = Ctx {
        game,
        indices,
        sound,
        map_index,
        messages: Some(&mut messages),
        songs: Some(&mut songs),
        // A shared body is compiled by `commons::body` with no graphics
        // registry, so what changes a graphic (a `MoveEvent` on the hero)
        // keeps it out there even if it compiles pasted into a page.
        graphics: if shared_body { None } else { Some(&mut graphics) },
        pictures: None,
        troops: None,
        commons,
        shared: None,
        losses: Losses::default(),
    };
    judged_page(&mut ctx, commands, map_events, 0, 0).map(|_| ())
}

/// A troop page: its trigger, every command outside the battle's list, and
/// then the chase of what is left, reflowed for the battle's window as
/// `TroopPages` does. The culprits' indices are the page's, not the
/// reflowed one's.
fn chase_troop_page(
    game: &Game,
    indices: &Indices,
    sound: &SoundSettings,
    window: Window,
    page: &TroopPage,
) -> Result<Chase> {
    let mut found = Chase::default();
    {
        let ctx = Ctx {
            game,
            indices,
            sound,
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
        found.trigger = troops::trigger(&ctx, page).is_none();
    }
    // With the calls to common events pasted, as `TroopPages` compiles them:
    // a pasted command's index is the call's. A call skipped there is not a
    // culprit —the page compiles without it— and is not listed.
    let (expanded, _skipped) = troops::expand_calls(game, &page.commands);
    let mut commands = Vec::with_capacity(expanded.len());
    let mut origin = Vec::with_capacity(expanded.len());
    for (i, cmd) in &expanded {
        origin.push(*i);
        if troops::runs_in_battle(cmd) {
            commands.push(troops::as_map_command(cmd));
        } else {
            found.culprits.push((*i, cmd.clone()));
            commands.push(taken_out(&troops::as_map_command(cmd)));
        }
    }
    let reflowed = troops::reflow_from(commands, &window.measure(), window.lines);
    let reflowed: Vec<(usize, Command)> = reflowed.into_iter().map(|(i, c)| (origin[i], c)).collect();
    let (from, commands): (Vec<usize>, Vec<Command>) = reflowed.into_iter().unzip();
    let rest = chase(commands, |commands| {
        let mut messages = Messages::new(1, window);
        let mut songs = Songs::default();
        let mut ctx = Ctx {
            game,
            indices,
            sound,
            map_index: &|_| None,
            messages: Some(&mut messages),
            songs: Some(&mut songs),
            graphics: None,
            pictures: None,
            troops: None,
            commons: None,
            shared: None,
            losses: Losses::default(),
        };
        judged_page(&mut ctx, commands, None, 0, 0).map(|_| ())
    });
    // A culprit inside a pasted body is named as itself, at the call's
    // index: the call is where it is in the page, the command is what has
    // to be looked at.
    found.culprits.extend(rest.culprits.into_iter().map(|(i, cmd)| {
        let own = &page.commands[from[i]];
        (from[i], if troops::called_common(own).is_some() { cmd } else { own.clone() })
    }));
    found.whole = rest.whole;
    found.fatal = rest.fatal.map(|(at, message)| (at.map(|i| from[i]), message));
    Ok(found)
}

/// The report as JSON: `pages`, every page that does not compile with its
/// culprits; and `commands`, per kind of page —`maps`, `commons`,
/// `troops`—, every command family the game uses, with:
///
/// * `uses` and `pages`: how many times it is used and in how many pages;
/// * `culprit_uses`: how many of those uses keep their page out;
/// * `alone`: the pages it is all that keeps out —the ones it would let in—;
/// * `with_others`: the pages it keeps out along with something else;
/// * `skipped`: the calls from a map's page to a common event it keeps from
///   compiling with that page's map —see [`Judged::skipped`]—, counted in
///   the maps' table.
///
/// Sorted by `alone`, then by `with_others`. And `totals` per kind: pages,
/// how many compile, how many have a trigger the ROM cannot look at, and how
/// many end at the page as a whole; and `skipped_calls`, each of those calls
/// with the callee's culprits.
pub fn report(judged: &[Judged]) -> Value {
    #[derive(Default)]
    struct Row {
        uses: usize,
        pages: usize,
        culprit_uses: usize,
        alone: usize,
        with_others: usize,
        skipped: usize,
    }
    let mut rows: BTreeMap<&str, BTreeMap<i32, Row>> = BTreeMap::new();
    let mut totals: BTreeMap<&str, [usize; 5]> = BTreeMap::new();
    let mut pages = Vec::new();
    let mut skipped_calls = Vec::new();
    for j in judged {
        let kind = j.place.kind();
        let table = rows.entry(kind).or_default();
        let mut used = BTreeSet::new();
        for cmd in &j.commands {
            let f = family(cmd.code);
            if f == END {
                continue;
            }
            table.entry(f).or_default().uses += usize::from(f == cmd.code);
            used.insert(f);
        }
        for f in &used {
            table.entry(*f).or_default().pages += 1;
        }
        for (_, c) in &j.chase.culprits {
            table.entry(family(c.code)).or_default().culprit_uses += 1;
        }
        let families = j.chase.families();
        for f in &families {
            let row = table.entry(*f).or_default();
            if j.chase.only(*f) {
                row.alone += 1;
            } else {
                row.with_others += 1;
            }
        }
        for (n, callee) in &j.skipped {
            for f in callee.families() {
                table.entry(f).or_default().skipped += 1;
            }
            let mut entry = j.place.to_json();
            entry["common"] = json!(n);
            entry["page_compiles"] = json!(j.chase.compiles());
            entry["culprits"] = culprits_json(&callee.culprits);
            entry["whole"] = json!(callee.whole);
            skipped_calls.push(entry);
        }
        let t = totals.entry(kind).or_default();
        t[0] += 1;
        t[1] += usize::from(j.chase.compiles());
        t[2] += usize::from(j.chase.trigger);
        t[3] += usize::from(j.chase.whole);
        t[4] += usize::from(j.chase.fatal.is_some());
        if !j.chase.compiles() {
            let mut entry = j.place.to_json();
            entry["trigger"] = json!(j.trigger);
            entry["culprits"] = culprits_json(&j.chase.culprits);
            entry["bad_trigger"] = json!(j.chase.trigger);
            entry["whole"] = json!(j.chase.whole);
            entry["fatal"] = match &j.chase.fatal {
                None => Value::Null,
                Some((at, message)) => json!({
                    "at": at,
                    "name": at.map(|i| name(j.commands[i].code)),
                    "message": message,
                }),
            };
            pages.push(entry);
        }
    }
    let commands: serde_json::Map<String, Value> = rows
        .into_iter()
        .map(|(kind, table)| {
            let mut table: Vec<(i32, Row)> = table.into_iter().collect();
            table.sort_by_key(|(code, r)| (std::cmp::Reverse((r.alone, r.with_others)), *code));
            let list = table
                .into_iter()
                .map(|(code, r)| {
                    json!({
                        "code": code,
                        "name": name(code),
                        "uses": r.uses,
                        "pages": r.pages,
                        "culprit_uses": r.culprit_uses,
                        "alone": r.alone,
                        "with_others": r.with_others,
                        "skipped": r.skipped,
                    })
                })
                .collect();
            (kind.to_string(), Value::Array(list))
        })
        .collect();
    let totals: serde_json::Map<String, Value> = totals
        .into_iter()
        .map(|(kind, [all, compile, trigger, whole, fatal])| {
            (
                kind.to_string(),
                json!({"pages": all, "compile": compile, "bad_trigger": trigger, "whole": whole, "fatal": fatal}),
            )
        })
        .collect();
    json!({"totals": totals, "commands": commands, "pages": pages, "skipped_calls": skipped_calls})
}

fn culprits_json(culprits: &[(usize, Command)]) -> Value {
    json!(culprits
        .iter()
        .map(|(i, c)| json!({
            "at": i,
            "code": c.code,
            "name": name(c.code),
            "parameters": c.parameters,
            "string": c.string,
        }))
        .collect::<Vec<_>>())
}

/// The report's `commands` as a table to read: per kind, the families that
/// keep some page out.
pub fn table(report: &Value) -> String {
    let mut out = String::new();
    for (kind, totals) in report["totals"].as_object().into_iter().flatten() {
        out += &format!(
            "{kind}: {} pages, {} compile, {} with a trigger the ROM cannot look at, {} stop at the page as a whole\n",
            totals["pages"], totals["compile"], totals["bad_trigger"], totals["whole"]
        );
        out += &format!(
            "  {:>6} {:<28} {:>6} {:>6} {:>8} {:>6} {:>7} {:>8}\n",
            "code", "command", "uses", "pages", "culprit", "alone", "others", "skipped"
        );
        for row in report["commands"][kind].as_array().into_iter().flatten() {
            if row["culprit_uses"] == 0 && row["skipped"] == 0 {
                continue;
            }
            out += &format!(
                "  {:>6} {:<28} {:>6} {:>6} {:>8} {:>6} {:>7} {:>8}\n",
                row["code"].to_string(),
                row["name"].as_str().unwrap_or(""),
                row["uses"].to_string(),
                row["pages"].to_string(),
                row["culprit_uses"].to_string(),
                row["alone"].to_string(),
                row["with_others"].to_string(),
                row["skipped"].to_string(),
            );
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cmd(code: i32, indent: i32) -> Command {
        Command::new(code, indent, "", vec![])
    }

    /// A judge that says no at the first command whose code is in `bad`.
    fn refusing(bad: &'static [i32]) -> impl FnMut(&[Command]) -> Judgement {
        move |commands| match commands.iter().position(|c| bad.contains(&c.code)) {
            Some(i) => Err((Stop::Cannot, Some(i))),
            None => Ok(()),
        }
    }

    #[test]
    fn the_chase_finds_every_culprit_in_order() {
        let page = vec![cmd(WAIT, 0), cmd(LOOP, 0), cmd(WAIT, 1), cmd(END_LOOP, 0), cmd(GAME_OVER, 0)];
        let found = chase(page, refusing(&[LOOP, END_LOOP, GAME_OVER]));
        let at: Vec<usize> = found.culprits.iter().map(|(i, _)| *i).collect();
        assert_eq!(at, [1, 3, 4]);
        assert!(!found.whole);
        // A loop and its end are one command; the Game Over is another.
        assert_eq!(found.families(), BTreeSet::from([LOOP, GAME_OVER]));
        assert!(!found.only(LOOP));
    }

    #[test]
    fn a_page_kept_out_by_one_command_is_that_commands_alone() {
        let page = vec![cmd(LOOP, 0), cmd(WAIT, 1), cmd(END_LOOP, 0)];
        let found = chase(page, refusing(&[LOOP, END_LOOP]));
        assert!(found.only(LOOP));
        let judged = [Judged {
            place: Place::Common(1),
            trigger: Some(5),
            commands: vec![cmd(LOOP, 0), cmd(WAIT, 1), cmd(END_LOOP, 0)],
            chase: found,
            skipped: vec![],
        }];
        let report = report(&judged);
        let rows = report["commands"]["commons"].as_array().unwrap();
        assert_eq!(rows[0]["code"], LOOP);
        assert_eq!(rows[0]["uses"], 1);
        assert_eq!(rows[0]["culprit_uses"], 2);
        assert_eq!(rows[0]["alone"], 1);
    }

    #[test]
    fn a_culprit_that_comes_back_ends_the_chase_at_the_page() {
        // A judge that always blames the first command, whatever it is.
        let found = chase(vec![cmd(WAIT, 0)], |_| Err((Stop::Cannot, Some(0))));
        assert_eq!(found.culprits.len(), 1);
        assert!(found.whole);
        assert!(!found.only(WAIT));
    }

    #[test]
    fn a_branch_is_taken_out_as_a_question_that_compiles() {
        let branch = Command::new(COND_BRANCH, 2, "", vec![5, 7, 0, 0, 0, 1]);
        let out = taken_out(&branch);
        assert_eq!((out.code, out.indent), (COND_BRANCH, 2));
        assert_eq!(out.parameters, [0, 1, 0, 0, 0, 1]);
    }
}
