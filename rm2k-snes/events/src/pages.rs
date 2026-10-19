//! A map's events as the compiler sees them, and the pages the ROM needs
//! to resolve them.

use crate::codes::*;
use crate::compile::{compile_page, instructions, Ctx, Indices, ROUTE_HERO, ROUTE_THIS_EVENT};
use crate::losses::Origin;
use crate::fail::{Bad, Result, Step, Stop};
use crate::game::{Command, Map, Page};
use rm2k_snes_bytecode::events::{CALL_LEVELS, OP_DONE, OP_ROUTE};
use crate::route;
use serde_json::{json, Value};
use std::cell::RefCell;
use std::collections::{BTreeMap, HashMap, HashSet};
use std::rc::Rc;

/// How a `TileSubstitution` translates to the ROM's blocks, which the caller
/// resolved —it depends on how the map's blocks ended up, which is the
/// console's business—: per `(upper layer, old tile, new tile)`, the
/// `(old block, new block)` pairs, or None if it cannot be expressed.
/// Per `(upper layer, old tile, new tile)`, the pairs of blocks or None.
pub type SubstitutionTable = HashMap<(bool, i64, i64), Option<Vec<(i64, i64)>>>;

#[derive(Debug, Default)]
pub struct Substitutions {
    pub table: SubstitutionTable,
    /// Which ones some page asked for: the caller keeps count of the keys
    /// those use, which is a table of the ROM with a cap.
    pub asked: RefCell<Vec<(bool, i64, i64)>>,
}

impl Substitutions {
    pub fn pairs(&self, upper: bool, old: i64, new: i64) -> Step<Option<Vec<(i64, i64)>>> {
        let key = (upper, old, new);
        let Some(pairs) = self.table.get(&key) else {
            return Err(Stop::Fatal(Bad::answer(format!(
                "a TileSubstitution {key:?} the request did not resolve"
            ))));
        };
        if !self.asked.borrow().contains(&key) {
            self.asked.borrow_mut().push(key);
        }
        Ok(pairs.clone())
    }
}

/// What is the same for every page of a map.
#[derive(Debug)]
struct Shared {
    /// RM2k's event id to its index in the ROM's table. **They are not the
    /// same**: many maps have gaps in the numbering.
    indices: HashMap<i32, usize>,
    /// Each event's pages' commands, for `CallEvent` where it still pastes
    /// —a parallel page's, after a jump to another map—. The pages go and
    /// not their commands because the number the call brings is the page's,
    /// and in RM2k it starts at one.
    pages: HashMap<i32, Vec<Vec<Command>>>,
    /// Which graphic each one is drawn with on its first page: two with the
    /// same share a palette on the console, and flash together. On the
    /// console the flash is done on the character's palette, so two events
    /// with the same graphic would flash together: see `FlashSprite` in
    /// `compile_command`.
    graphic: HashMap<i32, (String, i32)>,
}

/// The map's events, pointed at the page being compiled.
///
/// It exists for a reason that was measured and is paid dearly otherwise:
/// **RM2k's event id is not the index in the ROM's table**. 39 maps of the
/// game have gaps in the numbering —events deleted in the editor— so a
/// route aimed at id 8 would move whichever is eighth in the list, which can
/// be any other. The translation is done here, once, and the bytecode never
/// sees an RM2k id again.
#[derive(Debug, Clone)]
pub struct MapEvents {
    shared: Rc<Shared>,
    /// The event that owns the page: whom "this event" is.
    pub owner: Option<i32>,
    /// Which variables some page condition of the map looks at: a write to
    /// one of them asks for the refresh. None is "not known" —after the page
    /// jumped to another map— and every write asks for it.
    ///
    /// It is `Game_Map::RefreshEvent`'s `map_cache`, which is filled with
    /// each page's `pg.condition.variable_id`. `refresh` in the compiler
    /// reads it. Measured over the 328 maps: at most **one** per map, and
    /// 314 have none.
    pub watched: Option<Rc<HashSet<i32>>>,
    /// Which map it belongs to, to know when a page leaves it: see
    /// `after_jump`.
    pub map_id: i32,
    /// How a `TileSubstitution` translates to ROM block pairs. The converter
    /// sets it on the map, because it depends on how the blocks ended up
    /// —which is the console's business— and not on RM2k. Without it the
    /// command does not compile, which is what happens in any ROM built
    /// without going through the converter.
    ///
    /// None after a jump: the blocks there are another map's.
    pub substitutions: Option<Rc<Substitutions>>,
    /// Whether the page already jumped to another map. Then "this event" is
    /// nobody: `Game_Interpreter_Map::OnMapChange` puts 0 in every frame's
    /// event id, which is what `EraseEvent` looks at.
    pub jumped: bool,
    /// Whether the commands are a common event's, pasted into the page that
    /// calls it. In RM2k a common event's frame has no event —
    /// `GetThisEventId` is 0 there— and `EraseEvent` does nothing; the rest
    /// of the "this event"s resolve to the caller, as they always have.
    /// [`MapEvents::for_event`] clears it: a called map event's page is its
    /// own again.
    pub in_common: bool,
    /// Whether the frame runs on the interpreter that owns the call stack,
    /// the foreground's. A parallel page's does not —the ROM has one stack,
    /// and a parallel that waited inside a call would hold it across frames
    /// while the foreground runs—, so it **pastes** what it calls, as every
    /// page did until 2026-10-15: see [`MapEvents::pasting`] and
    /// `compile_call`.
    pub stack: bool,
    /// Each page's index in the ROM's page table, by `(event id, page
    /// number from 1)`: what `OP_CALL_PAGE` carries. It is the position the
    /// page gets in [`map_pages`]'s list, which skips the events left out
    /// whole —see [`left_out`]—, so [`map_pages`] rebuilds it before
    /// compiling with [`MapEvents::without`]; as built here no event is left
    /// out, which is right for every map a test builds and off by the
    /// left-out events for the scan's single pages and the culprits, whose
    /// bytes nobody runs.
    pub table: Rc<HashMap<(i32, i32), u16>>,
    /// The calls to a page of this map that were compiled as calls, with
    /// where each was made: after every page is compiled, the ones whose
    /// callee has no code are noted as skipped, which is what the console
    /// does with them. See [`map_pages`].
    pub page_calls: Rc<RefCell<Vec<PageCall>>>,
}

/// A `CallEvent` to a page of the map, compiled as `OP_CALL_PAGE`: the
/// frames the compiler was in, with the call's command, and the callee.
#[derive(Debug, Clone)]
pub struct PageCall {
    pub path: Vec<(Origin, Option<usize>)>,
    pub event: i32,
    pub page: i32,
}

/// Each page's index in the ROM's page table, by `(event id, page number
/// from 1)`, with the events in `left_out` having none: the position
/// [`map_pages`] gives it.
fn page_table(map: &Map, left_out: &HashSet<i32>) -> HashMap<(i32, i32), u16> {
    let mut table = HashMap::new();
    let mut index: u16 = 0;
    for event in &map.events {
        if left_out.contains(&event.id) {
            continue;
        }
        for k in 1..=event.pages.len() as i32 {
            table.insert((event.id, k), index);
            index = index.saturating_add(1);
        }
    }
    table
}

impl MapEvents {
    pub fn new(map: &Map, substitutions: Option<Rc<Substitutions>>) -> MapEvents {
        let indices = map
            .events
            .iter()
            .enumerate()
            .map(|(n, e)| (e.id, n))
            .collect();
        let pages = map
            .events
            .iter()
            .map(|e| (e.id, e.pages.iter().map(|p| p.commands.clone()).collect()))
            .collect();
        let table = Rc::new(page_table(map, &HashSet::new()));
        let graphic = map
            .events
            .iter()
            .filter_map(|e| {
                let p = e.active_page()?;
                (!p.character_name.is_empty())
                    .then(|| (e.id, (p.character_name.clone(), p.character_index)))
            })
            .collect();
        let watched = map
            .events
            .iter()
            .flat_map(|e| e.pages.iter())
            .filter_map(|p| p.condition.variable.map(|(v, _, _)| v))
            .collect();
        MapEvents {
            shared: Rc::new(Shared {
                indices,
                pages,
                graphic,
            }),
            owner: None,
            watched: Some(Rc::new(watched)),
            map_id: map.id,
            substitutions,
            jumped: false,
            in_common: false,
            stack: true,
            table,
            page_calls: Rc::new(RefCell::new(Vec::new())),
        }
    }

    /// The same, with the page table as the ROM gets it: without the events
    /// `left_out` names. See [`MapEvents::table`].
    pub fn without(&self, map: &Map, left_out: &HashSet<i32>) -> MapEvents {
        MapEvents {
            table: Rc::new(page_table(map, left_out)),
            ..self.clone()
        }
    }

    /// [`MapEvents::without`] the events [`map_pages`] leaves out whole, as
    /// it decides them: for the pages compiled apart from it that run on
    /// the map —a test page, the scan's single pages, the culprits'—.
    pub fn numbered(&self, map: &Map, indices: &Indices) -> MapEvents {
        let left_out = map
            .events
            .iter()
            .filter(|e| left_out_why(indices, e).is_some())
            .map(|e| e.id)
            .collect();
        self.without(map, &left_out)
    }

    /// The same, for a page that runs on a parallel interpreter: it pastes
    /// what it calls. See [`MapEvents::stack`].
    pub fn pasting(&self) -> MapEvents {
        MapEvents {
            stack: false,
            ..self.clone()
        }
    }

    /// Where page `page` —from 1— of event `event` is in the ROM's page
    /// table, if the event is in it.
    pub fn page_slot(&self, event: i32, page: i32) -> Option<u16> {
        self.table.get(&(event, page)).copied()
    }

    /// Whether this event draws with the same graphic as another one.
    pub fn shares_graphic(&self, who: Option<i32>) -> bool {
        let Some(which) = who.and_then(|w| self.shared.graphic.get(&w)) else {
            return false;
        };
        self.shared.graphic.values().filter(|g| *g == which).count() > 1
    }

    pub fn for_event(&self, event: i32) -> MapEvents {
        MapEvents {
            owner: Some(event),
            in_common: false,
            ..self.clone()
        }
    }

    /// The same, for a common event's commands pasted in: see `in_common`.
    pub fn in_a_common(&self) -> MapEvents {
        MapEvents {
            in_common: true,
            ..self.clone()
        }
    }

    /// The same, for what the page does **after jumping to another map**: it
    /// keeps running there, and which variables the pages there look at
    /// cannot be known from here, so every write asks for a refresh. And the
    /// blocks there are not these: a substitution after the jump would talk
    /// about the new map's tiles and the translation is the old one's.
    ///
    /// The rest does not change, and not because it is right: an event named
    /// by id after the jump is translated against this map and not against
    /// the destination. No page of the game that compiles today does it.
    ///
    /// A **parallel** page does not keep running there: it goes on in the
    /// same frame, on this map, until it waits or ends, and the new map's
    /// load ends it —`op_teleport` in the runtime—. For it the event ids are
    /// right as they are, and the rest of this is only cautious.
    pub fn after_jump(&self) -> MapEvents {
        MapEvents {
            watched: None,
            substitutions: None,
            jumped: true,
            ..self.clone()
        }
    }

    pub fn pages(&self, event: i32) -> Option<&Vec<Vec<Command>>> {
        self.shared.pages.get(&event)
    }

    /// The target byte of a route: 0 the hero, and an event its index plus
    /// one; None for a vehicle or an id the map does not have. Vehicles do
    /// not exist in this ROM and neither does an id the map does not have:
    /// both return None, which cuts the page.
    pub fn route_target(&self, who: i64) -> Option<usize> {
        if who == ROUTE_HERO {
            return Some(0);
        }
        let who = if who == ROUTE_THIS_EVENT {
            self.owner.map(|o| o as i64)
        } else {
            Some(who)
        };
        let who = i32::try_from(who?).ok()?;
        self.shared.indices.get(&who).map(|i| i + 1)
    }
}

/// What triggers a page that the ROM knows how to trigger. The rest of an
/// event's pages are emitted anyway —they are needed to know which one is
/// active— but without code.
///
/// The layer does not count here: every layer triggers from one of the two
/// cells the hero looks at, and the ROM applies their rules —see
/// `queue_by_action` in runtime/action_key.s—. They come from
/// `Game_Player`, and they are opposite on purpose:
///
/// * **The cell in front** —`CheckEventTriggerThere`— only counts the events
///   on the hero's layer. The action key looks there for action pages **and
///   for touch ones**; bumping into it, for touch ones.
/// * **The own cell** —`CheckEventTriggerHere`— only counts the other
///   layers: an event on the hero's layer blocks the way, so he never stands
///   on it. The action key looks there for action pages; stopping on it, for
///   touch ones.
///
/// Until 2026-10-05 a touch page on the hero's layer was left without code,
/// because "he would never get to step on it": true, but RM2k fires it from
/// the cell in front, with the action key and with a bump —measured in the
/// original runtime with a shopkeeper standing in his doorway, whose touch
/// page is the one that opens his shop—.
///
/// **Turning toward the hero does not stop the page.** Until 2026-09-08 it
/// did, and that cost **1572 action pages across 1224 events on 220 maps**:
/// half the game's NPCs could not be used. Since 2026-09-11 the event also
/// turns for real: see `turns`.
///
/// **The event's touch —`Trigger_collision`, 2— since 2026-10-14.** From
/// the hero's side it is touch: the two cells and the action key ask for
/// both. And it adds one way of its own: the event on the hero's layer that
/// tries to step onto the hero's cell and cannot —`Game_Event::Move` and
/// its `CheckCollisonOnMoveFailure`—, which is how ABL's Agency guard on
/// map 105 starts his battle. Until then its pages had no code, without a
/// word in the converter or in `culprits`, and the guard came, stood next
/// to Talan and nothing happened: 64 pages of ABL on 8 maps, 284 more in
/// three of the other games. What is still missing is the event on
/// **another** layer that steps onto the hero —`CheckEventCollision`, and
/// the hero standing still on top of one—: none of ABL's 64 is on another
/// layer. See `collide_with_hero` in runtime/event_routes.s.
fn triggerable(trigger: i32) -> bool {
    matches!(
        trigger,
        TRIGGER_ACTION | TRIGGER_TOUCH_HERO | TRIGGER_COLLISION | TRIGGER_AUTOSTART | TRIGGER_PARALLEL
    )
}

/// The animation types that fix the direction, plus `spin`: an event with
/// one does not turn toward the hero.
///
/// An event with a graphic **turns toward the hero** when he triggers it,
/// unless it has a fixed direction: it is the
/// `SetFacing(GetDirectionToCharacter(GetPlayer()))` of
/// `Game_Event::ScheduleForegroundExecution`. Since 2026-09-11 it is done,
/// on both sides —before, it answered facing wherever it was—. The rules, which the ROM
/// follows in `turn_fire` and company:
///
/// * It turns if its page turns —a CharSet, since a chipset tile has nowhere
///   to look, and an animation that does not fix the direction: this— and it
///   has no route: with a route, the route decides where it looks. The ones
///   that walk on their own always have a route, so they do not turn; in
///   RM2k they pause while their page runs and they do, and that is not
///   modeled.
/// * It looks toward the hero while **that event's page** lasts, and at the
///   end it goes back to its pose: `OnFinishForegroundEvent`'s
///   `UpdateFacing`.
/// * A refresh that changes its page undoes it if the new one does not turn
///   or draws something else; with the same graphic it stays turned, as in
///   `RefreshPage`. If the new one brings another CharSet with the same
///   direction and column, RM2k leaves it turned with the new drawing and
///   here it is undone: declared.
/// * A route that grabs it undoes it, and so does loading a map.
///
/// On the console a still one shares its VRAM slot with the other still
/// ones of the same pose, so to turn it moves to **the map's turn slot** —a
/// single one, because one turns at a time— and there the pose is uploaded
/// from the twelve of its graphic, which is why they go into the cartridge.
/// The one that walks or animates while still turns in its own slot.
///
/// The animation types with a fixed direction are the `fixed_*` of
/// `rpg::EventPage::AnimType`, plus `spin`, which turns on its own and does
/// not obey either. The whole rule is also next to `TURN` in the
/// converter's events.py, which the converter's side cites.
///
/// **A page without commands does not turn**: `ScheduleForegroundExecution`
/// returns on an empty list before `SetFacing`. Until 2026-10-16 it did
/// here, and a still event that turns animates in a slot of its own: the
/// sixty-one empty torches of A Blurred Line's map 148 wanted sixty-one
/// slots instead of their twins' two, and stood still.
fn turns(page: &Page) -> bool {
    !page.commands.is_empty()
        && !page.character_name.is_empty()
        && !matches!(
            page.animation_type,
            ANIM_FIXED_NOT_CONTINUOUS | ANIM_FIXED_CONTINUOUS | ANIM_FIXED_GRAPHIC | ANIM_SPIN
        )
}

/// The pages the ROM needs to resolve the map's events, one record each.
///
/// **All** the pages of an event go, not only the ones that trigger: which
/// one stays active depends on the conditions of all of them, and a later
/// page that triggers nothing still wins and keeps the one below from
/// running. An event with a condition the ROM cannot evaluate —a timer next
/// to a variable— is left out whole: running the wrong page is worse than
/// running none.
///
/// And **all** events go, whether or not they have a page that triggers
/// something: since 2026-09-05 the table also says which layer the active
/// page is on, which is what decides whether the event blocks the hero's
/// way —or another event's—, and any event does that, even one that runs
/// nothing. Before, only the ones with code were stored, and a droid without
/// a compilable page —the battle one— would not have stopped anyone.
///
/// If some page of the event asks for a condition the ROM does not know how
/// to evaluate then it is not known which page is active, and running the
/// wrong one is worse than running none. The whole event is left out, and
/// it does not block either: its layer is as unknown as its code.
///
/// What each page draws is not here: it is the caller's, who knows the
/// ChipSet and what it drew.
pub fn map_pages(ctx: &mut Ctx, map: &Map, map_events: &MapEvents) -> Result<Vec<Value>> {
    let mut out = Vec::new();
    let place = |event: &crate::game::Event, page: Option<i32>| Origin::Page {
        map: map.id,
        event: event.id,
        page,
        x: event.x,
        y: event.y,
    };
    // An event left out whole: none of its pages runs, blocks or is drawn.
    let left_out = |ctx: &mut Ctx, event: &crate::game::Event, why: String| {
        ctx.losses.enter(place(event, None));
        ctx.losses.lose(None, "event-left-out", why);
        ctx.losses.leave();
    };
    // Which events are left out whole, first: the page table skips them, so
    // every page's index in it —what a call to it carries— is known only
    // once they are.
    let mut skipped: HashSet<i32> = HashSet::new();
    for event in &map.events {
        if let Some((why, warn)) = left_out_why(ctx.indices, event) {
            if warn {
                eprintln!("  map {}: WARNING, event {} is left out: {why}", map.id, event.id);
            }
            left_out(ctx, event, format!("the event is left out: {why}"));
            skipped.insert(event.id);
        }
    }
    let map_events = map_events.without(map, &skipped);
    // Which pages compiled, for the chains of calls below.
    let mut compiled: HashSet<(i32, i32)> = HashSet::new();
    for (number, event) in map.events.iter().enumerate() {
        if skipped.contains(&event.id) {
            continue;
        }
        for (page_number, page) in event.pages.iter().enumerate() {
            ctx.losses.enter(place(event, Some(page.id)));
            page_losses(ctx, page);
            let c = &page.condition;
            let mut code = None;
            // **An automatic or parallel page without a single command starts
            // nothing.** It is `Game_Interpreter::Push`, which returns right
            // away with an empty list: the interpreter does not keep running
            // and the player walks. Here, instead, the empty page became the
            // active one, ran in one tick, ended, and since an automatic page
            // repeats while it stays active, it started again: the map stayed
            // frozen forever and the hero did not take a step.
            //
            // It is the idiom with which RM2k deactivates an event —a page
            // below turns on the switch that activates one above, and that one
            // is empty—, so it is not a rare case: in Rat Tracks B1 there are
            // two, and the map was unplayable.
            //
            // It is turned off by leaving its code out, which is what the
            // converter already looks at to decide whether an automatic page
            // counts: the page's bit 7.
            let empty = page.commands.is_empty()
                && matches!(page.trigger, TRIGGER_AUTOSTART | TRIGGER_PARALLEL);
            if triggerable(page.trigger) && !empty {
                // A parallel page pastes what it calls: the ROM has one call
                // stack, the foreground's. See `shared` in `Ctx` and
                // `MapEvents::stack`.
                let shared = ctx.shared;
                let mut me = map_events.for_event(event.id);
                if page.trigger == TRIGGER_PARALLEL {
                    ctx.shared = None;
                    me = me.pasting();
                }
                let out = compile_page(ctx, &page.commands, Some(me), 0, 0);
                ctx.shared = shared;
                code = out?;
                // **And the same with one that compiles to nothing**: all it
                // had were calls that got skipped —see `compile_call`—. In
                // RM2k it is not empty, and what it calls is what turns it
                // off; here it would be the empty page above, with the map
                // frozen. It is `AfterBattleMint` on the maps with
                // encounters: with switch 498, which turns on each troop's
                // turn 0 page, it calls common event 35, `ResetAfterBattles`,
                // which does not compile and is the one that turns 498 off.
                // Without this, the first battle on those maps left the hero
                // unable to take a step.
                if code.as_deref() == Some(&[OP_DONE][..])
                    && matches!(page.trigger, TRIGGER_AUTOSTART | TRIGGER_PARALLEL)
                {
                    code = None;
                }
            }
            if code.is_some() {
                compiled.insert((event.id, page_number as i32 + 1));
            }
            // **The timer travels in the variable's place**, with a slot no
            // variable has: the page record has no room for another condition
            // and the BSS none for a copy of it. It is
            // `Game_Event::AreConditionsMet`: the page holds while the seconds
            // left are at most `timer_sec`. Only one event of the game asks
            // for it —the 81 of map 312, the fire's Game Over— and no page
            // asks for both; one that did is left out above.
            let variable = match (c.variable, c.timer) {
                (Some((v, comparison, value)), _) => {
                    let slot = variable_slot(ctx.indices, v)?;
                    json!([slot, comparison, value])
                }
                (None, Some(seconds)) => json!([TIMER_SLOT, AT_MOST, seconds]),
                (None, None) => Value::Null,
            };
            out.push(json!({
                "event": number,
                "page": page_number,
                "trigger": page.trigger,
                "switch_a": c.switch_a.unwrap_or(0),
                "switch_b": c.switch_b.unwrap_or(0),
                "actor": c.actor.unwrap_or(0),
                "variable": variable,
                "item": c.item.unwrap_or(0),
                "layer": page.layer,
                "frequency": page.move_frequency,
                "speed": page.move_speed,
                "route_targets": code.as_deref().map(route_targets).unwrap_or_default(),
                "code": code.map(|c| hex(&c)),
                "own_route": route::own(page),
                "turns": turns(page),
                "pure": page.trigger == TRIGGER_PARALLEL && crate::commons::pure_page(&page.commands),
            }));
            ctx.losses.leave();
        }
    }
    // The calls to a page that has no code: the console skips them —the
    // table's pointer is zero—, which is what a call to a body that does
    // not compile has always done; said here, where the call is.
    for call in map_events.page_calls.borrow().iter() {
        if compiled.contains(&(call.event, call.page)) {
            continue;
        }
        ctx.losses.lose_on(
            call.path.clone(),
            Some(CALL_EVENT),
            "call-skipped",
            format!("event {}'s page {} does not compile here, and the call is skipped", call.event, call.page),
        );
    }
    // And the chains of calls deeper than the console's stack: a call past
    // it is skipped, and nothing in the console says so. Counted from each
    // page that runs in the foreground, through the pages it calls and the
    // shared common events, as a bound: a page that may call is counted
    // whether it ends up calling or pasting.
    for event in &map.events {
        for (k, page) in event.pages.iter().enumerate() {
            let number = k as i32 + 1;
            if page.trigger == TRIGGER_PARALLEL || !compiled.contains(&(event.id, number)) {
                continue;
            }
            let depth = call_depth(ctx, &map_events, &compiled, Node::Page(event.id, number));
            let text = match depth {
                // The root is a frame too, and not on the stack: a chain of
                // `d` frames pushes `d - 1`.
                Some(d) if d <= CALL_LEVELS + 1 => continue,
                Some(d) => format!(
                    "a chain of {} calls starts here, and the console's stack holds {CALL_LEVELS}: the ones past it are skipped",
                    d - 1
                ),
                None => format!(
                    "the calls from here loop, and the console's stack holds {CALL_LEVELS}: the ones past it are skipped"
                ),
            };
            ctx.losses.enter(place(event, Some(page.id)));
            ctx.losses.lose(Some(CALL_EVENT), "call-stack-exceeded", text);
            ctx.losses.leave();
        }
    }
    Ok(out)
}

/// Why an event is left out whole, if it is, and whether the converter's
/// log warns about it: a condition the ROM cannot evaluate, or one it would
/// read outside its tables. The whole event and not the page, because the
/// table is indexed by the event's pages, and dropping one would shift the
/// others.
fn left_out_why(indices: &Indices, event: &crate::game::Event) -> Option<(String, bool)> {
    if event
        .pages
        .iter()
        .any(|p| p.condition.timer.is_some() && p.condition.variable.is_some())
    {
        return Some(("a page's condition asks for the timer and a variable".into(), false));
    }
    // A page whose condition names a variable that has no slot (the game
    // has more than fit in far RAM).
    if let Some(v) = event
        .pages
        .iter()
        .filter_map(|p| p.condition.variable)
        .map(|(v, _, _)| v)
        .find(|&v| variable_slot(indices, v).is_err())
    {
        return Some((format!("a page's condition names variable {v}, which has no slot in far RAM"), true));
    }
    // And the same with a switch past the ROM's table, which the console
    // would test in whatever RAM follows it: until 2026-10-15 the table
    // was 1024 switches for every game, and Vampires Dawn's map 433 picked
    // its figures' dead page that way. The table holds every switch the
    // game names —see `indices::switch_top`—, so this guards a mistake.
    if let Some(s) = event
        .pages
        .iter()
        .flat_map(|p| [p.condition.switch_a, p.condition.switch_b])
        .flatten()
        .find(|&s| !indices.holds_switch(s as i64))
    {
        return Some((format!("a page's condition names switch {s}, past the ROM's table"), true));
    }
    None
}

/// A frame in a chain of calls: a page of the map, or a shared common
/// event's body.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
enum Node {
    Page(i32, i32),
    Common(i32),
}

/// How many frames a chain of calls from `root` can be waiting at once,
/// counting `root` as the first: `OP_CALL_PAGE` to the pages of the map
/// that compiled, and `OP_CALL` to the shared common events the cartridge
/// has, through both. None if the calls loop. A pasted call counts as a
/// frame too: it is a bound, and the console's stack is what it is measured
/// against.
fn call_depth(ctx: &Ctx, me: &MapEvents, compiled: &HashSet<(i32, i32)>, root: Node) -> Option<usize> {
    fn walk(
        ctx: &Ctx,
        me: &MapEvents,
        compiled: &HashSet<(i32, i32)>,
        node: Node,
        open: &mut Vec<Node>,
        memo: &mut HashMap<Node, usize>,
    ) -> Option<usize> {
        if let Some(&d) = memo.get(&node) {
            return Some(d);
        }
        if open.contains(&node) {
            return None;
        }
        open.push(node);
        let empty = Vec::new();
        let commands: &[Command] = match node {
            Node::Page(e, p) => me.pages(e).and_then(|pages| pages.get((p - 1) as usize)).unwrap_or(&empty),
            Node::Common(n) => ctx.game.common_events.get(&n).map_or(&empty[..], |c| &c.commands),
        };
        let mut deepest = 0;
        for c in commands.iter().filter(|c| c.code == CALL_EVENT && c.parameters.len() >= 2) {
            let p = &c.parameters;
            let callee = match (p[0], node) {
                (0, _) if ctx.shared.is_some_and(|s| s.contains_key(&p[1])) => Node::Common(p[1]),
                (1, Node::Page(..)) if p.len() >= 3 && compiled.contains(&(p[1], p[2])) => Node::Page(p[1], p[2]),
                _ => continue,
            };
            deepest = deepest.max(walk(ctx, me, compiled, callee, open, memo)?);
        }
        open.pop();
        memo.insert(node, deepest + 1);
        Some(deepest + 1)
    }
    walk(ctx, me, compiled, root, &mut Vec::new(), &mut HashMap::new())
}

/// What a map's page loses whatever its commands: the fields nothing
/// compiles, and its own route, walked without some commands or not at
/// all —see `route::own`—.
fn page_losses(ctx: &mut Ctx, page: &Page) {
    let mut lose = |kind, text: &str| ctx.losses.lose(None, kind, text);
    if page.translucent && !page.character_name.is_empty() {
        lose("translucent-drawn-opaque", "the event is drawn opaque instead of half transparent");
    }
    if page.overlap_forbidden && page.move_type != MOVE_STATIONARY {
        lose("overlap-not-forbidden", "\"forbid overlap\" is not kept: it collides only with events on its layer");
    }
    let walks = (MOVE_RANDOM..=MOVE_AWAY).contains(&page.move_type)
        || (page.move_type == MOVE_CUSTOM && !page.route.is_empty());
    if !walks {
        return;
    }
    if route::own(page).is_none() {
        lose("own-route-not-walked", "the page's own route is not walked: the event stands still");
        return;
    }
    if page.move_type != MOVE_CUSTOM {
        return;
    }
    if page.route.contains(&ROUTE_SOUND) {
        lose("sound-not-played", "the sound in the page's own route does not play");
    }
    if page.route.iter().any(|c| ROUTE_TRANSPARENCY.contains(c)) {
        lose("route-transparency-dropped", "the page's own route's steps of transparency are not done");
    }
}

/// The events a compiled page sends a route to, by index in the map's
/// table, sorted. The bytecode is walked and not the commands, which is what
/// makes it the truth and not a guess: what counts is what ended up emitted.
/// Target 0 is the hero, who is not an event.
fn route_targets(code: &[u8]) -> Vec<usize> {
    let mut targets: Vec<usize> = instructions(code)
        .filter(|&at| code[at] == OP_ROUTE && code[at + 1] != 0)
        .map(|at| code[at + 1] as usize - 1)
        .collect();
    targets.sort();
    targets.dedup();
    targets
}

/// A page condition's variable has a slot always: the sweep saw it. And
/// not one of the two the record reserves —`$FF` is "none" and
/// [`TIMER_SLOT`] the timer—: 174 slots are used today, so this is a wall
/// for a game with many more, not a case that happens.
fn variable_slot(indices: &Indices, v: i32) -> Result<u8> {
    let slot = indices
        .variable_slot(v as i64)
        .map_err(|_| Bad::answer(format!("variable {v} of a page condition has no slot")))?;
    if slot >= TIMER_SLOT {
        return Err(Bad::answer(format!(
            "variable {v} of a page condition takes slot {slot}, which the page record reserves"
        )));
    }
    Ok(slot)
}

/// The slot a page record's variable condition carries to mean "the
/// timer's seconds": `conditions_ok` reads `timer_sec` instead.
pub const TIMER_SLOT: u8 = 0xFE;

/// `compare_var`'s `<=`: the codes are `CheckOperator`'s, `==` `>=` `<=` `>`
/// `<` `!=`.
const AT_MOST: i32 = 2;

pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// The pages of every map, by map, as `(event index, page index)` and
/// whether they compile: the question the party's scan asks.
pub type Compiles = BTreeMap<i32, Vec<(usize, usize, bool)>>;

#[cfg(test)]
mod tests {
    use super::*;
    use crate::game::Condition;

    fn page(commands: Vec<Command>) -> Page {
        Page {
            trigger: 0,
            layer: 1,
            move_type: 0,
            move_frequency: 3,
            move_speed: 6,
            animation_type: 1,
            character_name: "Crown7".into(),
            character_index: 3,
            character_pattern: 1,
            commands,
            route: Vec::new(),
            route_repeat: true,
            route_skippable: false,
            condition: Condition::default(),
            id: 1,
            translucent: false,
            overlap_forbidden: false,
        }
    }

    #[test]
    fn a_page_without_commands_does_not_turn() {
        // A Blurred Line's map 148: sixty-one torches on the hero's layer,
        // action pages with nothing in them. RM2k never turns them, and
        // here turning kept each one out of its twins' slot.
        assert!(!turns(&page(Vec::new())));
        assert!(turns(&page(vec![Command::new(10110, 0, "hot", Vec::new())])));
    }
}
