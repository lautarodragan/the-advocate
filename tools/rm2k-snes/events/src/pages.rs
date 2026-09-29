//! A map's events as the compiler sees them, and the pages the ROM needs
//! to resolve them.

use crate::codes::*;
use crate::compile::{compile_page, Ctx, Indices, ROUTE_HERO, ROUTE_THIS_EVENT};
use crate::fail::{Bad, Result, Step, Stop};
use crate::game::{Command, Map, Page, CONDITION_OPERATOR};
use crate::opcodes::OP_DONE;
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
    /// Each event's pages' commands, for `CallEvent`.
    pages: HashMap<i32, Vec<Vec<Command>>>,
    /// Which graphic each one is drawn with on its first page: two with the
    /// same share a palette on the console, and flash together.
    graphic: HashMap<i32, (String, i32)>,
}

/// The map's events, pointed at the page being compiled.
#[derive(Debug, Clone)]
pub struct MapEvents {
    shared: Rc<Shared>,
    /// The event that owns the page: whom "this event" is.
    pub owner: Option<i32>,
    /// Which variables some page condition of the map looks at: a write to
    /// one of them asks for the refresh. None is "not known" —after the page
    /// jumped to another map— and every write asks for it.
    pub watched: Option<Rc<HashSet<i32>>>,
    pub map_id: i32,
    /// None after a jump: the blocks there are another map's.
    pub substitutions: Option<Rc<Substitutions>>,
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

    /// The same, for what the page does after jumping to another map: which
    /// variables the pages there look at is not known here, and the blocks
    /// there are not these.
    pub fn after_jump(&self) -> MapEvents {
        MapEvents {
            watched: None,
            substitutions: None,
            ..self.clone()
        }
    }

    pub fn pages(&self, event: i32) -> Option<&Vec<Vec<Command>>> {
        self.shared.pages.get(&event)
    }

    /// The target byte of a route: 0 the hero, and an event its index plus
    /// one; None for a vehicle or an id the map does not have.
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
pub fn can_trigger(page: &Page) -> bool {
    if page.trigger == TRIGGER_TOUCH_HERO {
        return page.layer != LAYER_SAME;
    }
    true
}

/// What triggers a page that the ROM knows how to trigger.
fn triggerable(trigger: i32) -> bool {
    matches!(
        trigger,
        TRIGGER_ACTION | TRIGGER_TOUCH_HERO | TRIGGER_AUTOSTART | TRIGGER_PARALLEL
    )
}

/// The animation types that fix the direction, plus `spin`: an event with
/// one does not turn toward the hero.
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
/// one is active depends on the conditions of all of them. An event with a
/// condition the ROM cannot evaluate —a timer— is left out whole: running
/// the wrong page is worse than running none.
///
/// What each page draws is not here: it is the caller's, who knows the
/// ChipSet and what it drew.
pub fn map_pages(ctx: &mut Ctx, map: &Map, map_events: &MapEvents) -> Result<Vec<Value>> {
    let mut out = Vec::new();
    for (number, event) in map.events.iter().enumerate() {
        if event.pages.iter().any(|p| p.condition.timer) {
            continue;
        }
        for (page_number, page) in event.pages.iter().enumerate() {
            let c = &page.condition;
            let mut code = None;
            // An automatic or parallel page without a command starts
            // nothing, and one that compiles to nothing neither: here it
            // would run every tick and freeze the map.
            let empty = page.commands.is_empty()
                && matches!(page.trigger, TRIGGER_AUTOSTART | TRIGGER_PARALLEL);
            if triggerable(page.trigger) && can_trigger(page) && !empty {
                code = compile_page(
                    ctx,
                    &page.commands,
                    Some(map_events.for_event(event.id)),
                    0,
                    0,
                )?;
                if code.as_deref() == Some(&[OP_DONE][..])
                    && matches!(page.trigger, TRIGGER_AUTOSTART | TRIGGER_PARALLEL)
                {
                    code = None;
                }
            }
            let variable = match c.variable {
                Some((v, value)) => {
                    let slot = variable_slot(ctx.indices, v)?;
                    json!([slot, CONDITION_OPERATOR, value])
                }
                None => Value::Null,
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
                "code": code.map(|c| hex(&c)),
                "own_route": route::own(page),
                "turns": turns(page),
            }));
        }
    }
    Ok(out)
}

/// A page condition's variable has a slot always: the sweep saw it.
fn variable_slot(indices: &Indices, v: i32) -> Result<u8> {
    indices
        .variable_slot(v as i64)
        .map_err(|_| Bad::answer(format!("variable {v} of a page condition has no slot")))
}

pub fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

/// The pages of every map, by map, as `(event index, page index)` and
/// whether they compile: the question the party's scan asks.
pub type Compiles = BTreeMap<i32, Vec<(usize, usize, bool)>>;
