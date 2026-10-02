//! A map's events as the compiler sees them, and the pages the ROM needs
//! to resolve them.

use crate::codes::*;
use crate::compile::{compile_page, instructions, Ctx, Indices, ROUTE_HERO, ROUTE_THIS_EVENT};
use crate::fail::{Bad, Result, Step, Stop};
use crate::game::{Command, Map, Page, CONDITION_OPERATOR};
use crate::opcodes::{OP_DONE, OP_ROUTE};
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
    /// Each event's pages' commands, for `CallEvent`: calling a map event
    /// compiles its page in place. The pages go and not their commands
    /// because the number the call brings is the page's, and in RM2k it
    /// starts at one.
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
            .filter_map(|p| p.condition.variable.map(|(v, _)| v))
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
        }
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

/// Whether the ROM knows how to trigger this page. Touching it asks for a
/// layer other than the hero's: one on the same layer blocks the way.
///
/// The two layer rules come from `Game_Player`, and they are opposite on
/// purpose:
///
/// * **Action key**: the cell in front is looked at, and there only the
///   events on the hero's layer count —`CheckEventTriggerThere` asks for
///   `GetLayer() == Layers_same`—. An action event on the **own** cell does
///   exist in RM2k, but it asks for the opposite layer
///   —`CheckEventTriggerHere` asks for `!= Layers_same`—, and since
///   2026-09-07 those trigger too: see `can_trigger`.
/// * **Touch**: it triggers on stepping on the cell, and there it is the
///   other way around: the layer has to be different from the hero's,
///   because an event on the same layer blocks its way and it would never
///   get to step on it. Of the game's 983 touch pages, 978 are on the lower
///   layer.
///
/// **Turning toward the hero does not stop the page.** Until 2026-09-08 it
/// did, and that cost **1572 action pages across 1224 events on 220 maps**:
/// half the game's NPCs could not be used. Since 2026-09-11 the event also
/// turns for real: see `turns`.
pub fn can_trigger(page: &Page) -> bool {
    // An action page: both cells count, and each one asks for the opposite
    // layer. The one in front is `CheckEventTriggerThere`, which asks for
    // `Layers_same`; the own one is `CheckEventTriggerHere`, which asks for
    // `!= Layers_same` —it has to be so: an event on the hero's layer closes
    // its way and it would never get to stand on it—.
    //
    // The own one was not done until 2026-09-07 and taro found it while
    // playing: the door out of Talan's pad is `TalDoorTop`, action and
    // **layer 2**, and it opens by standing on it. Without this it never
    // triggered and there was no way out of the pad.
    if page.trigger == TRIGGER_TOUCH_HERO {
        return page.layer != LAYER_SAME;
    }
    true
}

/// What triggers a page that the ROM knows how to trigger. The rest of an
/// event's pages are emitted anyway —they are needed to know which one is
/// active— but without code.
fn triggerable(trigger: i32) -> bool {
    matches!(
        trigger,
        TRIGGER_ACTION | TRIGGER_TOUCH_HERO | TRIGGER_AUTOSTART | TRIGGER_PARALLEL
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
fn turns(page: &Page) -> bool {
    !page.character_name.is_empty()
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
    for (number, event) in map.events.iter().enumerate() {
        if event
            .pages
            .iter()
            .any(|p| p.condition.timer.is_some() && p.condition.variable.is_some())
        {
            continue;
        }
        for (page_number, page) in event.pages.iter().enumerate() {
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
            if triggerable(page.trigger) && can_trigger(page) && !empty {
                // A parallel page pastes what it calls: the ROM has one call
                // stack, the foreground's. See `shared` in `Ctx`.
                let shared = ctx.shared;
                if page.trigger == TRIGGER_PARALLEL {
                    ctx.shared = None;
                }
                let compiled = compile_page(
                    ctx,
                    &page.commands,
                    Some(map_events.for_event(event.id)),
                    0,
                    0,
                );
                ctx.shared = shared;
                code = compiled?;
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
            // **The timer travels in the variable's place**, with a slot no
            // variable has: the page record has no room for another condition
            // and the BSS none for a copy of it. It is
            // `Game_Event::AreConditionsMet`: the page holds while the seconds
            // left are at most `timer_sec`. Only one event of the game asks
            // for it —the 81 of map 312, the fire's Game Over— and no page
            // asks for both; one that did is left out above.
            let variable = match (c.variable, c.timer) {
                (Some((v, value)), _) => {
                    let slot = variable_slot(ctx.indices, v)?;
                    json!([slot, CONDITION_OPERATOR, value])
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
            }));
        }
    }
    Ok(out)
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
