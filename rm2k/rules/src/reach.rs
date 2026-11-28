//! Where a character can ever be drawn on a map: which cells the sprite of
//! the hero or of an event can cover, whatever the game does.
//!
//! A character stands on one cell and its CharSet frame, 24x32, is drawn
//! with the bottom of the frame on the bottom of the cell and centred on it
//! —easyrpg's `Game_Character::GetScreenX`/`GetScreenY` and
//! `Sprite_Character`'s origin—, so on cell (x, y) it covers 4 px of x-1
//! and x+1 and all of y-1. A cell no such frame can ever touch is a cell
//! where nothing is ever drawn between the two tile layers, and a tile
//! drawn above the hero there could just as well be drawn below.
//!
//! **What can move a character is the whole game**, and this answers for
//! all of it: the hero walks wherever the map lets him from every cell he
//! can be put on; an event walks wherever its movement type takes it; and
//! every move route that can run on the map —a page's own, a `MoveEvent`
//! of a page, of a common event or of whatever the caller adds— is walked
//! as RM2k walks it, on every cell its character can be on, again and
//! again until nobody can be anywhere new. A route that walks through walls
//! moves one cell at a time wherever the map is; a jump lands on a cell
//! passable from some side (`Game_Map::CheckOrMakeWayEx` with every bit)
//! and rises 16 px at most on the way (`GetJumpHeight`), one more row of
//! cover. What cannot be known puts a character anywhere: a
//! `ChangeEventLocation` by variables, a route that leaves walking through
//! walls on for a character that then walks on its own —the hero walks
//! through walls after it, `Game_Player`'s `move_route_through`—.
//!
//! Except where a page holds the hero: one that is not a parallel process
//! keeps the player's hand off him while it runs, and if it takes him off
//! the map before it can end —a `Teleport` to another map outside every
//! branch, with nothing between that can end the list or jump—, where its
//! routes leave him he is only while it runs. His routes walk from there,
//! through walls if they left him so; he does not walk from there on his
//! own, and no other page that holds him starts there. A cutscene that
//! seats the hero through a row of seats and walks him out of the door
//! left him, without this, walking through walls anywhere.
//!
//! And such a page that starts only as he arrives —an autostart page that
//! asks for nothing, under pages that ask only for switches nothing on
//! the map turns off— starts where he arrives, not wherever he can walk.
//!
//! It errs toward covering: a move the engine would refuse because an event
//! is in the way, or a direction the passability closes, is taken as
//! possible —a cell is "open" if any of its sides lets one in—, every page
//! of an event counts, whatever its conditions, and a common event runs on
//! any map with any event as "this event". What is taken on trust is what
//! the caller says of where the hero arrives from outside the map's pages
//! —[`Outside`]—.

use crate::chipset::{LOWER, TILES_PER_LAYER, UPPER};
use crate::passability::{cell, ALL};
use ditto::schema::{Map, MapScrollType};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

/// The event commands this reads.
const TELEPORT: i32 = 10810;
const CHANGE_EVENT_LOCATION: i32 = 10860;
const TRADE_EVENT_LOCATIONS: i32 = 10870;
const MOVE_EVENT: i32 = 11330;
const TILE_SUBSTITUTION: i32 = 11750;

/// Who a command names: the hero —10002 to 10004 are the vehicles— and
/// "this event"; any number below them is an event of the map.
/// `Game_Character::GetCharacter`.
const HERO: i32 = 10001;
const THIS_EVENT: i32 = 10005;

/// The move route commands this reads: the eight steps, the four that pick
/// a direction while walking, the jump and walking through walls. And the
/// three that carry operands inside a `MoveEvent`'s integers.
const STEPS: [(i32, i32); 8] = [
    (0, -1),
    (1, 0),
    (0, 1),
    (-1, 0),
    (1, -1),
    (1, 1),
    (-1, 1),
    (-1, -1),
];
const ROUTE_RANDOM: i32 = 8;
const ROUTE_FORWARD: i32 = 11;
const BEGIN_JUMP: i32 = 24;
const END_JUMP: i32 = 25;
const SWITCH_ON: i32 = 32;
const SWITCH_OFF: i32 = 33;
const CHANGE_GRAPHIC: i32 = 34;
const PLAY_SOUND: i32 = 35;
const THROUGH_ON: i32 = 36;
const THROUGH_OFF: i32 = 37;

/// The movement types that walk on their own: random, vertical, horizontal,
/// toward and away from the hero. Custom, 6, walks its route, which is read
/// as a route.
const WALKS_ALONE: std::ops::RangeInclusive<i32> = 1..=5;
const MOVE_CUSTOM: i32 = 6;

/// A `MoveEvent`'s route, out of its integers: `[target, frequency, repeat,
/// skippable, commands…]`, each command its code and the operands of the
/// three that have them —`Game_Interpreter::CommandMoveEvent`'s
/// `DecodeMove`—. A route cut in the middle of an operand ends there.
pub fn decode_route(params: &[i32]) -> Vec<i32> {
    let mut codes = Vec::new();
    let n = params.len();
    let mut i = 4.min(n);
    let integer = |i: &mut usize| -> Option<i64> {
        let mut value: i64 = 0;
        loop {
            let x = i64::from(*params.get(*i)?);
            *i += 1;
            value = value.wrapping_shl(7) | (x & 0x7F);
            if x & 0x80 == 0 {
                return Some(value);
            }
        }
    };
    let text = |i: &mut usize| -> Option<()> {
        let length = usize::try_from(integer(i)?).ok()?;
        *i = i.checked_add(length).filter(|&end| end <= n)?;
        Some(())
    };
    while i < n {
        let code = params[i];
        i += 1;
        let whole = match code {
            SWITCH_ON | SWITCH_OFF => integer(&mut i).map(|_| ()),
            CHANGE_GRAPHIC => text(&mut i).and_then(|_| integer(&mut i).map(|_| ())),
            PLAY_SOUND => {
                text(&mut i).and_then(|_| (0..3).try_for_each(|_| integer(&mut i).map(|_| ())))
            }
            _ => Some(()),
        };
        if whole.is_none() {
            break;
        }
        codes.push(code);
    }
    codes
}

/// Who a route or a placement is for.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
enum Who {
    Hero,
    Event(i32),
    /// "This event" in a common event: any of the map's.
    AnyEvent,
}

fn who(target: i32, this: Option<i32>) -> Option<Who> {
    match target {
        HERO => Some(Who::Hero),
        THIS_EVENT => Some(this.map_or(Who::AnyEvent, Who::Event)),
        n if n > 0 && n < HERO => Some(Who::Event(n)),
        // The vehicles: the caller answers for them.
        _ => None,
    }
}

/// What the walk looks at to know whether a character can be anywhere new.
type Shape = (usize, usize, bool, bool, bool);

impl Places {
    fn shape(&self) -> Shape {
        (
            self.cells.len(),
            self.held.len(),
            self.through,
            self.held_through,
            self.anywhere,
        )
    }
}

/// Where one character can be.
#[derive(Clone, Debug, Default)]
struct Places {
    cells: BTreeSet<usize>,
    /// Those of `cells` the hero is on only while a page holds him, one
    /// that takes him off the map before it lets go —see
    /// [`Move::Leave`]—: routes start from them, he never walks from them.
    held: BTreeSet<usize>,
    /// Whether a route may have left it walking through walls.
    through: bool,
    /// The same, only while a page holds him: the routes of any list walk
    /// through walls from his cells, he never walks through them.
    held_through: bool,
    anywhere: bool,
    /// Whether it walks on its own: the hero, by the player's hand.
    walks: bool,
}

/// The map's grid: its size and whether it wraps.
#[derive(Clone, Copy)]
struct Grid {
    width: i32,
    height: i32,
    loop_x: bool,
    loop_y: bool,
}

impl Grid {
    fn of(map: &Map) -> Grid {
        let scroll = map.scroll_type;
        Grid {
            width: map.width.max(1),
            height: map.height.max(1),
            loop_x: matches!(scroll, MapScrollType::Horizontal | MapScrollType::Both),
            loop_y: matches!(scroll, MapScrollType::Vertical | MapScrollType::Both),
        }
    }

    /// The cell at (x, y), wrapped on an axis that loops; `None` off a
    /// map's edge that does not.
    fn at(&self, x: i32, y: i32) -> Option<usize> {
        let fit = |v: i32, size: i32, looped: bool| -> Option<i32> {
            if looped {
                Some(v.rem_euclid(size))
            } else {
                (0..size).contains(&v).then_some(v)
            }
        };
        let x = fit(x, self.width, self.loop_x)?;
        let y = fit(y, self.height, self.loop_y)?;
        Some((y * self.width + x) as usize)
    }

    fn xy(&self, at: usize) -> (i32, i32) {
        (at as i32 % self.width, at as i32 / self.width)
    }
}

/// What a route walks: a state per possibility.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
struct State {
    at: usize,
    through: bool,
    /// While jumping, where it will land, from where it took off.
    jump: Option<(i32, i32)>,
}

/// What walking the routes leaves besides where everyone stands: the cells
/// a sprite passes over —between two cells of a diagonal step— and those
/// it rises from in a jump.
#[derive(Default)]
struct Passed {
    over: BTreeSet<usize>,
    /// A jump's path, each cell with the 16 px it can rise.
    risen: BTreeSet<usize>,
}

struct Walker<'a> {
    grid: Grid,
    open: &'a [bool],
}

impl Walker<'_> {
    fn directions(code: i32) -> &'static [(i32, i32)] {
        match code {
            0..=7 => std::slice::from_ref(&STEPS[code as usize]),
            // Random, toward and away from the hero, forward: one of the
            // four, decided while walking.
            ROUTE_RANDOM..=ROUTE_FORWARD => &STEPS[..4],
            _ => &[],
        }
    }

    /// One state after one command. A step that a route that is not
    /// skippable cannot take leaves the state in `stuck`: RM2k waits on it
    /// forever, and the rest of the route never runs.
    fn step(
        &self,
        s: State,
        code: i32,
        skippable: bool,
        passed: &mut Passed,
        out: &mut Vec<State>,
        stuck: &mut Vec<State>,
    ) {
        let (x, y) = self.grid.xy(s.at);
        match code {
            THROUGH_ON => out.push(State { through: true, ..s }),
            THROUGH_OFF => out.push(State {
                through: false,
                ..s
            }),
            BEGIN_JUMP if s.jump.is_none() => out.push(State {
                jump: Some((0, 0)),
                ..s
            }),
            END_JUMP => out.extend(self.land(s, passed)),
            _ => {
                let dirs = Self::directions(code);
                if dirs.is_empty() {
                    out.push(s);
                    return;
                }
                for &(dx, dy) in dirs {
                    if let Some((jx, jy)) = s.jump {
                        out.push(State {
                            jump: Some((jx + dx, jy + dy)),
                            ..s
                        });
                        continue;
                    }
                    // A step can always fail —an event in the way— and
                    // leave it where it was, if the route skips it. One
                    // that does not waits until the event is gone, and
                    // steps: it never goes on from here without stepping.
                    // A direction picked while walking is taken as
                    // skippable: the one it picks may be closed.
                    let skips = skippable || dirs.len() > 1;
                    if !s.through && skips {
                        out.push(s);
                    }
                    let Some(to) = self.grid.at(x + dx, y + dy) else {
                        if s.through || !skips {
                            out.push(s);
                        }
                        continue;
                    };
                    if !s.through && !skips && !self.open[to] {
                        stuck.push(s);
                        continue;
                    }
                    if s.through || self.open[to] {
                        if dx != 0 && dy != 0 {
                            passed.over.extend(self.grid.at(x + dx, y));
                            passed.over.extend(self.grid.at(x, y + dy));
                        }
                        out.push(State { at: to, ..s });
                    }
                }
            }
        }
    }

    /// Where a jump ends: on its landing cell if it may land there, and
    /// where it took off if not —it jumps in place—. Every cell between
    /// the two is passed over in the air.
    fn land(&self, s: State, passed: &mut Passed) -> Vec<State> {
        let Some((dx, dy)) = s.jump else {
            return vec![s];
        };
        let still = State { jump: None, ..s };
        passed.risen.insert(s.at);
        let (x, y) = self.grid.xy(s.at);
        let to = self.grid.at(x + dx, y + dy);
        let lands = to.filter(|&t| s.through || self.open[t]);
        let Some(to) = lands else {
            return vec![still];
        };
        // The straight line between the two, sampled finer than a cell:
        // the sprite goes over every cell it crosses, on both sides of a
        // fraction.
        let steps = (dx.abs().max(dy.abs()) * 4).max(1);
        for k in 0..=steps {
            let fx = x * steps + dx * k;
            let fy = y * steps + dy * k;
            for cx in [fx.div_euclid(steps), (fx + steps - 1).div_euclid(steps)] {
                for cy in [fy.div_euclid(steps), (fy + steps - 1).div_euclid(steps)] {
                    passed.risen.extend(self.grid.at(cx, cy));
                }
            }
        }
        let mut out = vec![State { at: to, ..still }];
        if !s.through {
            out.push(still);
        }
        out
    }

    /// Every state a route can leave from those of `from`, and every cell
    /// it stands on along the way, if only for a moment; and those of them
    /// it stands on walking through walls.
    fn walk(&self, from: &[State], route: &Route, passed: &mut Passed) -> Walked {
        let mut seen: HashSet<State> = from.iter().copied().collect();
        let mut current: Vec<State> = from.to_vec();
        let mut ends: HashSet<State> = HashSet::new();
        let mut stood: BTreeSet<usize> = from.iter().map(|s| s.at).collect();
        let mut phased: BTreeSet<usize> = from.iter().filter(|s| s.through).map(|s| s.at).collect();
        loop {
            for &code in &route.codes {
                let code = if route.who == Who::Hero {
                    on_hero(code)
                } else {
                    code
                };
                let mut next = Vec::new();
                let mut stuck = Vec::new();
                for &s in &current {
                    self.step(s, code, route.skippable, passed, &mut next, &mut stuck);
                }
                stood.extend(stuck.iter().map(|s| s.at));
                phased.extend(stuck.iter().filter(|s| s.through).map(|s| s.at));
                ends.extend(stuck);
                next.sort_by_key(|s| (s.at, s.through, s.jump));
                next.dedup();
                stood.extend(next.iter().map(|s| s.at));
                phased.extend(next.iter().filter(|s| s.through).map(|s| s.at));
                current = next;
            }
            // A route that ends in the air lands.
            let landed: Vec<State> = current.iter().flat_map(|&s| self.land(s, passed)).collect();
            stood.extend(landed.iter().map(|s| s.at));
            phased.extend(landed.iter().filter(|s| s.through).map(|s| s.at));
            let fresh: Vec<State> = landed.into_iter().filter(|s| ends.insert(*s)).collect();
            current = fresh.into_iter().filter(|s| seen.insert(*s)).collect();
            if !route.repeat || current.is_empty() {
                passed.over.extend(stood.iter().copied());
                return Walked {
                    ends: ends.into_iter().collect(),
                    stood,
                    phased,
                };
            }
        }
    }

    /// The cells a character walking on its own reaches from `cells`: any
    /// open neighbour up, down, left or right, again and again. Not the
    /// diagonals: RM2k 2000 walks the hero by the player's hand, and an
    /// event by its movement type, in four directions
    /// (`Game_Player::UpdateNextMovementAction`, `Game_Event::MoveTypeRandom`
    /// and the others); only a route steps diagonally.
    ///
    /// Not from the cells of `held`: one that it reaches is no longer held.
    fn spread(&self, cells: &mut BTreeSet<usize>, held: &mut BTreeSet<usize>) {
        let mut todo: Vec<usize> = cells.difference(held).copied().collect();
        while let Some(at) = todo.pop() {
            let (x, y) = self.grid.xy(at);
            for &(dx, dy) in &STEPS[..4] {
                let Some(to) = self.grid.at(x + dx, y + dy) else {
                    continue;
                };
                if self.open[to] && (cells.insert(to) | held.remove(&to)) {
                    todo.push(to);
                }
            }
        }
    }
}

/// What a route walked: see [`Walker::walk`].
struct Walked {
    ends: Vec<State>,
    stood: BTreeSet<usize>,
    phased: BTreeSet<usize>,
}

/// A route that can run on the map, and whom it moves.
#[derive(Clone, Debug)]
struct Route {
    who: Who,
    codes: Vec<i32>,
    repeat: bool,
    /// Whether a step it cannot take is skipped: if not, it waits there.
    skippable: bool,
}

impl Route {
    /// Whether it leaves its character where it was and as it was: no
    /// step, no jump —one in place still rises—, nothing that lets it
    /// through walls.
    fn still(&self) -> bool {
        !self.codes.iter().any(|&c| {
            (0..=ROUTE_FORWARD).contains(&c) || matches!(c, BEGIN_JUMP | END_JUMP | THROUGH_ON)
        })
    }
}

/// What a command that looks at the hero means on the hero: himself.
/// `GetDirectionToCharacter` with both on the same cell gives down, and
/// `GetDirectionAwayCharacter` up.
fn on_hero(code: i32) -> i32 {
    const TOWARD: i32 = 9;
    const AWAY: i32 = 10;
    match code {
        TOWARD => 2,
        AWAY => 0,
        other => other,
    }
}

/// The tiles each tile of a layer can become through the substitutions
/// `subs` —`(upper layer, old, new)`, each numbered within its layer—,
/// itself included, as many steps as they chain.
fn becomes(subs: &[(bool, i32, i32)], id: i32) -> BTreeSet<i32> {
    let upper = id >= UPPER;
    let base = if upper { UPPER } else { LOWER };
    let mut seen: BTreeSet<i32> = [id].into();
    let mut todo = vec![id];
    while let Some(t) = todo.pop() {
        for &(u, old, new) in subs {
            if u == upper
                && (0..TILES_PER_LAYER).contains(&new)
                && base + old == t
                && seen.insert(base + new)
            {
                todo.push(base + new);
            }
        }
    }
    seen
}

/// What of a command list moves someone.
#[derive(Clone, Debug)]
enum Move {
    Route(usize),
    /// Put on a cell —`None`: off the map— or, with `None` outside, on
    /// any cell. `top`: whether it runs whenever the list does, outside
    /// every branch.
    Place {
        who: Who,
        at: Option<Option<usize>>,
        top: bool,
    },
    Trade(Who, Who),
    /// Something after which the hero can be anywhere he can be: a call,
    /// which may run anything, or a loop or a label, which may run what
    /// came before again.
    Lose,
    /// A `Teleport` to another map. `top`, as in `Place`.
    Leave {
        top: bool,
    },
    /// An `EndEventProcessing`, which may end the list here.
    Stop,
}

/// A list of commands that runs from start to end: a page, or every
/// command the caller adds, as one.
struct Run {
    /// Its event, if it is a page.
    this: Option<i32>,
    /// Whether it only starts with the hero beside its event: a page that
    /// starts by the action key or by a touch, which nothing calls.
    beside: bool,
    /// Whether the player cannot move the hero while it runs: a page that
    /// is not a parallel process —`Game_Interpreter`'s foreground—.
    holds: bool,
    /// Whether it starts only as the hero arrives on the map: an autostart
    /// page nothing can turn on while he is there. See `on_arrival`.
    on_arrival: bool,
    /// Whether, starting so, it runs once in the whole game: it turns on
    /// the switches of a page above it, which then holds for good. See
    /// `once`.
    once: bool,
    moves: Vec<Move>,
}

impl Run {
    /// Whether, after its move `mi`, the list takes the hero off the map
    /// before it can end and let the player move him: a `Teleport` to
    /// another map outside every branch, with no `EndEventProcessing` nor
    /// anything that can jump —a call, a loop, a label— between.
    fn leaves_after(&self, mi: usize) -> bool {
        self.leaves_from(mi + 1)
    }

    fn leaves_from(&self, start: usize) -> bool {
        self.holds
            && self.moves[start..]
                .iter()
                .find(|m| matches!(m, Move::Leave { top: true } | Move::Lose | Move::Stop))
                .is_some_and(|m| matches!(m, Move::Leave { .. }))
    }
}

/// The event commands this reads besides the ones that move.
const CALL_EVENT: i32 = 12330;
const END_EVENT_PROCESSING: i32 = 12310;
const LOOP: i32 = 12210;
const LABEL: i32 = 12110;
const JUMP_TO_LABEL: i32 = 12120;
/// `CallEvent`'s first parameter for a map event's page, by number and by
/// variables.
const CALL_MAP_EVENT: i32 = 1;
const CALL_BY_VARIABLES: i32 = 2;
/// The triggers that start a page with the hero beside it: the action key,
/// the hero's touch and the event's.
const BESIDE_TRIGGERS: std::ops::RangeInclusive<i32> = 0..=2;
/// The trigger of a page that runs alongside the player: a parallel
/// process.
const PARALLEL: i32 = 4;
const AUTOSTART: i32 = 3;
/// `ControlSwitches`, and its operations that may turn a switch off.
const CONTROL_SWITCHES: i32 = 10210;
const SWITCH_ON_OP: i32 = 0;
const SWITCH_OFF_OP: i32 = 1;
const SWITCH_TOGGLE_OP: i32 = 2;

/// Where the hero can arrive on a map from outside its pages, which only
/// the whole game knows.
#[derive(Clone, Copy, Debug, Default)]
pub struct Outside<'a> {
    /// The cells he can be put on: the game's start, the `Teleport`s of
    /// other maps and of the common events into this one. `None`: anywhere.
    pub entries: Option<&'a [(i32, i32)]>,
    /// Whether he can also be put on any cell one can step on: where a
    /// `RecallToLocation` whose variables the game works out takes him. A
    /// game that recalls a place it computed —ABL's, the hero's own cell
    /// five rows up— means one where the hero can stand, and that is the
    /// one thing taken on trust.
    pub any_open: bool,
    /// The cells a vehicle he rides carries him over besides where he
    /// walks —a boat's or a ship's water—, or none.
    pub sail: &'a [bool],
}

/// Where each character's feet can ever be on map `id`, or `None` if
/// someone can be anywhere: see the module.
///
/// `flags` is the ChipSet's passability by tile id
/// —[`crate::chipset::passability_table`]—. `commands` are the ones that
/// can run on the map besides its pages' —the common events', and whatever
/// the caller runs there—, as `(code, parameters)`: "this event" in them is
/// any event of the map.
///
/// A page that starts with the hero beside its event moves him from there:
/// the cells next to the event's, or two away in a straight line, the most
/// the action key reaches over a counter —`Game_Player::CheckActionEvent`—.
/// That is what keeps a door that walks the hero through a wall from
/// walking him through every wall: the page runs again only with him beside
/// the door again.
pub fn standing(
    id: i32,
    map: &Map,
    flags: &[u8],
    commands: &[(i32, Vec<i32>)],
    outside: Outside,
) -> Option<Vec<Standing>> {
    let grid = Grid::of(map);
    let cells = (grid.width * grid.height) as usize;

    let mut places: BTreeMap<Who, Places> = BTreeMap::new();
    places.insert(
        Who::Hero,
        Places {
            walks: true,
            ..Default::default()
        },
    );
    for event in &map.events {
        let p = places.entry(Who::Event(event.id)).or_default();
        p.cells.extend(grid.at(event.x, event.y));
        for page in &event.pages {
            p.walks |= WALKS_ALONE.contains(&page.move_type.to_i32());
        }
    }
    let events: Vec<Who> = places
        .keys()
        .copied()
        .filter(|k| matches!(k, Who::Event(_)))
        .collect();

    // The pages a `CallEvent` runs are not started by the hero beside them.
    let lists = map
        .events
        .iter()
        .flat_map(|e| {
            e.pages
                .iter()
                .map(move |p| (Some(e.id), p.trigger.to_i32(), &p.event_commands))
        })
        .collect::<Vec<_>>();
    let mut called: BTreeSet<i32> = BTreeSet::new();
    let mut by_variables = false;
    let calls = lists
        .iter()
        .flat_map(|(this, _, cs)| {
            cs.iter()
                .map(move |c| (*this, c.code.to_i32(), &c.parameters[..]))
        })
        .chain(commands.iter().map(|(code, p)| (None, *code, &p[..])));
    for (this, code, p) in calls {
        if code != CALL_EVENT {
            continue;
        }
        match p.first() {
            Some(&CALL_MAP_EVENT) => match p.get(1).and_then(|&t| who(t, this)) {
                Some(Who::Event(e)) => {
                    called.insert(e);
                }
                _ => by_variables = true,
            },
            Some(&CALL_BY_VARIABLES) => by_variables = true,
            _ => {}
        }
    }

    // Every command that can run here, as runs.
    let mut routes: Vec<Route> = Vec::new();
    let mut runs: Vec<Run> = Vec::new();
    let mut subs: Vec<(bool, i32, i32)> = Vec::new();
    let mut read = |this: Option<i32>,
                    beside: bool,
                    holds: bool,
                    on_arrival: bool,
                    once: bool,
                    list: &mut dyn Iterator<Item = (i32, &[i32], bool)>,
                    routes: &mut Vec<Route>,
                    runs: &mut Vec<Run>,
                    places: &mut BTreeMap<Who, Places>| {
        let mut moves = Vec::new();
        for (code, p, top) in list {
            let get = |k: usize| p.get(k).copied();
            let target = |k: usize| get(k).and_then(|t| who(t, this));
            match code {
                TELEPORT if get(0) != Some(id) => moves.push(Move::Leave { top }),
                END_EVENT_PROCESSING => moves.push(Move::Stop),
                TELEPORT => {
                    if let (Some(x), Some(y)) = (get(1), get(2)) {
                        moves.push(Move::Place {
                            who: Who::Hero,
                            at: Some(grid.at(x, y)),
                            top,
                        });
                    }
                }
                CHANGE_EVENT_LOCATION => {
                    if let Some(w) = target(0) {
                        let at = match (get(1), get(2), get(3)) {
                            (Some(0), Some(x), Some(y)) => Some(grid.at(x, y)),
                            _ => None,
                        };
                        moves.push(Move::Place { who: w, at, top });
                    }
                }
                TRADE_EVENT_LOCATIONS => {
                    if let (Some(a), Some(b)) = (target(0), target(1)) {
                        moves.push(Move::Trade(a, b));
                    }
                }
                MOVE_EVENT => {
                    if let Some(w) = target(0) {
                        routes.push(Route {
                            who: w,
                            codes: decode_route(p),
                            repeat: get(2).is_some_and(|r| r != 0),
                            skippable: get(3) != Some(0),
                        });
                        moves.push(Move::Route(routes.len() - 1));
                    }
                }
                TILE_SUBSTITUTION if p.len() >= 3 => subs.push((p[0] != 0, p[1], p[2])),
                CALL_EVENT | LOOP | LABEL => moves.push(Move::Lose),
                _ => {}
            }
        }
        // A placement is for good: it is there from the start.
        for m in &moves {
            if let Move::Place { who: w, at, .. } = m {
                let targets = match w {
                    Who::AnyEvent => events.clone(),
                    w => vec![*w],
                };
                for t in targets {
                    let place = places.entry(t).or_default();
                    match at {
                        Some(Some(c)) => {
                            place.cells.insert(*c);
                        }
                        Some(None) => {}
                        None => place.anywhere = true,
                    }
                }
            }
        }
        if moves
            .iter()
            .any(|m| !matches!(m, Move::Leave { .. } | Move::Stop))
        {
            runs.push(Run {
                this,
                beside,
                holds,
                on_arrival,
                once,
                moves,
            });
        }
    };
    // The switches a command that can run here may turn off: by number,
    // or any if one picks them by a variable.
    let mut off: BTreeSet<i32> = BTreeSet::new();
    let mut any_off = false;
    let every = map
        .events
        .iter()
        .flat_map(|e| e.pages.iter())
        .flat_map(|p| {
            p.event_commands
                .iter()
                .map(|c| (c.code.to_i32(), &c.parameters[..]))
        })
        .chain(commands.iter().map(|(code, p)| (*code, &p[..])));
    for (code, p) in every {
        if code != CONTROL_SWITCHES
            || !matches!(p.get(3), Some(&(SWITCH_OFF_OP | SWITCH_TOGGLE_OP)))
        {
            continue;
        }
        match (p.first(), p.get(1), p.get(2)) {
            (Some(&0), Some(&a), _) => {
                off.insert(a);
            }
            (Some(&1), Some(&a), Some(&b)) => off.extend(a..=b.max(a)),
            _ => any_off = true,
        }
    }
    // Whether page `k` of `event`, an autostart page that asks for
    // nothing, starts only as the hero arrives: no page above it can go
    // off while he is on the map —each asks only for switches nothing here
    // turns off—, so if it does not start then, it never does; and nothing
    // calls it. `Game_Map`'s refresh picks the highest page that holds.
    let on_arrival = |event: &ditto::schema::Event, k: usize| -> bool {
        let page = &event.pages[k];
        let quiet = |c: &ditto::schema::EventPageCondition| {
            let f = &c.flags;
            !(f.variable || f.item || f.actor || f.timer || f.timer2)
                && !(f.switch_a && (any_off || off.contains(&c.switch_a_id)))
                && !(f.switch_b && (any_off || off.contains(&c.switch_b_id)))
        };
        let f = &page.condition.flags;
        page.trigger.to_i32() == AUTOSTART
            && !(f.switch_a || f.switch_b || f.variable || f.item || f.actor || f.timer || f.timer2)
            && !by_variables
            && !called.contains(&event.id)
            && event.pages[k + 1..].iter().all(|p| quiet(&p.condition))
    };
    // Whether page `k` of `event`, one that starts only as the hero
    // arrives, runs once in the whole game: it turns on, for sure, every
    // switch a page above it asks for, and that page asks for nothing
    // else. Nothing turns those switches off —`on_arrival` asked—, so the
    // page above holds from then on and this one never starts again: it
    // starts the first time the hero arrives, from where he comes from
    // outside, and not from every cell a recalled place can put him on
    // later. A Blurred Line's Hover-Tram: the trip turns on switch 69,
    // which its page 2 asks for, and takes him away.
    //
    // For sure: by number, at the list's top level, with no
    // `EndEventProcessing` or `JumpToLabel` before it, which could end the
    // list or jump past it.
    let once = |event: &ditto::schema::Event, k: usize| -> bool {
        let mut on: BTreeSet<i32> = BTreeSet::new();
        for c in &event.pages[k].event_commands {
            let (code, p) = (c.code.to_i32(), &c.parameters[..]);
            if code == END_EVENT_PROCESSING || code == JUMP_TO_LABEL {
                break;
            }
            if code != CONTROL_SWITCHES || c.indent != 0 || p.get(3) != Some(&SWITCH_ON_OP) {
                continue;
            }
            match (p.first(), p.get(1), p.get(2)) {
                (Some(&0), Some(&a), _) => {
                    on.insert(a);
                }
                (Some(&1), Some(&a), Some(&b)) => on.extend(a..=b),
                _ => {}
            }
        }
        event.pages[k + 1..].iter().any(|p| {
            let c = &p.condition;
            let f = &c.flags;
            (f.switch_a || f.switch_b)
                && !(f.variable || f.item || f.actor || f.timer || f.timer2)
                && (!f.switch_a || on.contains(&c.switch_a_id))
                && (!f.switch_b || on.contains(&c.switch_b_id))
        })
    };
    for event in &map.events {
        for (k, page) in event.pages.iter().enumerate() {
            if page.move_type.to_i32() == MOVE_CUSTOM {
                routes.push(Route {
                    who: Who::Event(event.id),
                    codes: page
                        .move_route
                        .move_commands
                        .iter()
                        .map(|c| c.command_id.to_i32())
                        .collect(),
                    repeat: page.move_route.repeat,
                    skippable: page.move_route.skippable,
                });
                runs.push(Run {
                    this: Some(event.id),
                    beside: false,
                    holds: false,
                    on_arrival: false,
                    once: false,
                    moves: vec![Move::Route(routes.len() - 1)],
                });
            }
            let beside = BESIDE_TRIGGERS.contains(&page.trigger.to_i32())
                && !by_variables
                && !called.contains(&event.id);
            let mut list = page
                .event_commands
                .iter()
                .map(|c| (c.code.to_i32(), &c.parameters[..], c.indent == 0));
            read(
                Some(event.id),
                beside,
                page.trigger.to_i32() != PARALLEL,
                on_arrival(event, k),
                on_arrival(event, k) && once(event, k),
                &mut list,
                &mut routes,
                &mut runs,
                &mut places,
            );
        }
    }
    let mut list = commands.iter().map(|(code, p)| (*code, &p[..], false));
    read(
        None,
        false,
        false,
        false,
        false,
        &mut list,
        &mut routes,
        &mut runs,
        &mut places,
    );

    // The tiles each cell can show, through every substitution that can run
    // here, and with them where one can step or land.
    let mut open: Vec<bool> = (0..cells)
        .map(|at| {
            let (l, u) = (
                i32::from(*map.lower_layer.get(at).unwrap_or(&0)),
                i32::from(*map.upper_layer.get(at).unwrap_or(&(UPPER as i16))),
            );
            let lows = becomes(&subs, l);
            let highs = becomes(&subs, u);
            lows.iter().any(|&l| {
                highs.iter().any(|&u| {
                    let ok = |t: i32| usize::try_from(t).is_ok_and(|t| t < flags.len());
                    ok(l) && ok(u) && cell(flags, l, u) & ALL != 0
                })
            })
        })
        .collect();

    for (o, &s) in open.iter_mut().zip(outside.sail) {
        *o |= s;
    }
    let hero = places.get_mut(&Who::Hero).expect("the hero is there");
    match outside.entries {
        Some(cells) => hero
            .cells
            .extend(cells.iter().filter_map(|&(x, y)| grid.at(x, y))),
        None => hero.anywhere = true,
    }
    // Where he enters the map from outside, before a recalled place can
    // put him anywhere: where a scene that runs once starts.
    let entered: BTreeSet<usize> = hero.cells.clone();
    if outside.any_open {
        hero.cells.extend((0..cells).filter(|&c| open[c]));
    }
    // An event drawn with a tile opens its cells: the tile may be a bridge.
    // Not one drawn with a CharSet, which RM2k does not walk on: it steps
    // off a wall a page puts it on —a step looks only where it goes— but
    // nobody steps onto one, and the people seated on a row of closed
    // seats did not let the hero sit among them.
    let tiled: BTreeSet<i32> = map
        .events
        .iter()
        .filter(|e| e.pages.iter().any(|p| p.character_name.is_empty()))
        .map(|e| e.id)
        .collect();
    for (w, p) in &places {
        if matches!(w, Who::Event(id) if tiled.contains(id)) {
            for &c in &p.cells {
                open[c] = true;
            }
        }
    }

    let walker = Walker { grid, open: &open };
    let mut passed: BTreeMap<Who, Passed> = BTreeMap::new();
    let states = |cells: &BTreeSet<usize>, through: &dyn Fn(usize) -> bool| -> Vec<State> {
        cells
            .iter()
            .flat_map(|&at| {
                let through = through(at);
                [false, true]
                    .into_iter()
                    .filter(move |&t| !t || through)
                    .map(move |t| State {
                        at,
                        through: t,
                        jump: None,
                    })
            })
            .collect()
    };
    // Beside an event's cells: next to them, or two away in a line.
    let beside = |cells: &BTreeSet<usize>| -> BTreeSet<usize> {
        let mut out = BTreeSet::new();
        for &c in cells {
            let (x, y) = grid.xy(c);
            out.insert(c);
            for (dx, dy) in [(0, -1), (1, 0), (0, 1), (-1, 0)] {
                out.extend(grid.at(x + dx, y + dy));
                out.extend(grid.at(x + 2 * dx, y + 2 * dy));
            }
        }
        out
    };
    let shape = |places: &BTreeMap<Who, Places>| -> Vec<Shape> {
        places.values().map(Places::shape).collect()
    };
    // What each list reads: the hero, its event and whoever it moves.
    let signature = |places: &BTreeMap<Who, Places>, run: &Run| -> Vec<Shape> {
        let mut who: BTreeSet<Who> = [Who::Hero].into();
        who.extend(run.this.map(Who::Event));
        for m in &run.moves {
            match m {
                Move::Route(r) => match routes[*r].who {
                    Who::AnyEvent => who.extend(events.iter().copied()),
                    w => {
                        who.insert(w);
                    }
                },
                Move::Place {
                    who: Who::AnyEvent, ..
                } => who.extend(events.iter().copied()),
                Move::Place { who: w, .. } => {
                    who.insert(*w);
                }
                Move::Trade(a, b) => who.extend([*a, *b]),
                Move::Lose | Move::Leave { .. } | Move::Stop => {}
            }
        }
        who.iter()
            .map(|w| {
                places
                    .get(w)
                    .map_or((0, 0, false, false, false), Places::shape)
            })
            .collect()
    };
    // Where the hero is as he arrives, before he takes a step.
    let arrival: BTreeSet<usize> = places[&Who::Hero].cells.clone();
    let mut last: Vec<Option<Vec<Shape>>> = vec![None; runs.len()];
    // By list, move and character: the states walked, the cells stood on,
    // and those stood on walking through walls while a page holds the hero.
    type Seen = (HashSet<State>, BTreeSet<usize>, BTreeSet<usize>);
    let mut seen: HashMap<(usize, usize, Who), Seen> = HashMap::new();
    loop {
        // Anyone anywhere covers everything: nothing else can change that.
        if places.values().any(|p| p.anywhere) {
            break;
        }
        let before = shape(&places);
        for p in places.values_mut() {
            if p.walks && !p.anywhere {
                if p.through {
                    p.anywhere = true;
                } else {
                    walker.spread(&mut p.cells, &mut p.held);
                }
            }
        }
        for (ri, run) in runs.iter().enumerate() {
            // A list whose characters are where they were the last time it
            // was walked has nothing new to give.
            let reads = signature(&places, run);
            if last[ri].as_ref() == Some(&reads) {
                continue;
            }
            last[ri] = Some(reads);
            // Where each character is while this runs, from its start: the
            // hero beside its event if it starts so, anyone else wherever
            // they can be.
            let mut now: BTreeMap<Who, BTreeSet<usize>> = BTreeMap::new();
            if let Some(this) = run.this.map(Who::Event).filter(|_| run.beside) {
                let e = &places[&this];
                let hero = &places[&Who::Hero];
                // Not where another page holds him: it runs only after
                // that one is done, and that one takes him away.
                let free: BTreeSet<usize> = hero.cells.difference(&hero.held).copied().collect();
                if !e.anywhere && !hero.anywhere {
                    // Only on the cells where the hero can be beside it.
                    let there: BTreeSet<usize> = e
                        .cells
                        .iter()
                        .copied()
                        .filter(|&c| beside(&[c].into()).iter().any(|b| free.contains(b)))
                        .collect();
                    let b = beside(&there);
                    now.insert(Who::Hero, free.intersection(&b).copied().collect());
                    now.insert(this, there);
                }
            }
            let mut moved: BTreeSet<Who> = BTreeSet::new();
            let mut lost = false;
            // Where a route of this list left the hero walking through
            // walls while it holds him.
            let mut held_through: BTreeSet<usize> = BTreeSet::new();
            for (mi, m) in run.moves.iter().enumerate() {
                match m {
                    Move::Route(r) => {
                        let whom: Vec<Who> = match routes[*r].who {
                            Who::AnyEvent => events.clone(),
                            w => vec![w],
                        };
                        for w in whom {
                            moved.insert(w);
                            // Where it leaves the hero, if the list takes
                            // him off the map before the player has him
                            // again, he is only held: see `Places::held`.
                            let leaves = w == Who::Hero && run.leaves_after(mi);
                            let place = places.entry(w).or_default();
                            if place.anywhere {
                                continue;
                            }
                            // A page that holds the hero starts where no
                            // other holds him; a parallel one runs while
                            // they do.
                            // One that starts only as he arrives and takes
                            // him away before it ends starts where he
                            // arrives: see `Run::on_arrival`. If it runs
                            // once, where he first arrives: `Run::once`.
                            let here = now.entry(w).or_insert_with(|| {
                                if w == Who::Hero && run.on_arrival && run.leaves_from(0) {
                                    if run.once {
                                        entered.clone()
                                    } else {
                                        arrival.clone()
                                    }
                                } else if run.holds {
                                    place.cells.difference(&place.held).copied().collect()
                                } else {
                                    place.cells.clone()
                                }
                            });
                            // Where another page holds the hero, a parallel
                            // one walks him on as that one left him, and
                            // leaves him held: that one still takes him
                            // away. Anywhere else, this list decides.
                            let held: BTreeSet<usize> = if w == Who::Hero && !run.holds {
                                here.intersection(&place.held).copied().collect()
                            } else {
                                BTreeSet::new()
                            };
                            let free: BTreeSet<usize> = here.difference(&held).copied().collect();
                            let hero = w == Who::Hero;
                            let through =
                                |c: usize| place.through || (hero && held_through.contains(&c));
                            let mut starts = states(&free, &through);
                            let from_held = states(&held, &|c| through(c) || place.held_through);
                            let held_from = starts.len();
                            starts.extend(from_held);
                            // Each state walked once: what it gave is
                            // already where it goes, and kept for the rest
                            // of the list.
                            let done = seen.entry((ri, mi, w)).or_default();
                            let mut groups = [Vec::new(), Vec::new()];
                            for (k, s) in starts.into_iter().enumerate() {
                                if done.0.insert(s) {
                                    groups[usize::from(k >= held_from)].push(s);
                                }
                            }
                            for (k, fresh) in groups.into_iter().enumerate() {
                                let walked = if fresh.is_empty() || routes[*r].still() {
                                    Walked {
                                        ends: fresh.clone(),
                                        stood: fresh.iter().map(|s| s.at).collect(),
                                        phased: fresh
                                            .iter()
                                            .filter(|s| s.through)
                                            .map(|s| s.at)
                                            .collect(),
                                    }
                                } else {
                                    walker.walk(&fresh, &routes[*r], passed.entry(w).or_default())
                                };
                                done.1.extend(walked.stood);
                                if leaves {
                                    done.2.extend(walked.phased);
                                }
                                for s in walked.ends {
                                    if leaves || k == 1 {
                                        if place.cells.insert(s.at) {
                                            place.held.insert(s.at);
                                        }
                                        place.held_through |= s.through;
                                    } else {
                                        place.cells.insert(s.at);
                                        place.held.remove(&s.at);
                                        place.through |= s.through;
                                    }
                                }
                            }
                            here.extend(done.1.iter().copied());
                            if hero {
                                held_through.extend(done.2.iter().copied());
                            }
                        }
                    }
                    Move::Place { who, at, top } => {
                        let whom: Vec<Who> = match who {
                            Who::AnyEvent => events.clone(),
                            w => vec![*w],
                        };
                        for w in whom {
                            let Some(Some(c)) = at else {
                                now.remove(&w);
                                continue;
                            };
                            // Put there for sure only if nothing moved it
                            // before in this list: a route of its still
                            // walking goes on from the new cell.
                            if *top && !lost && !moved.contains(&w) {
                                now.insert(w, [*c].into());
                            } else {
                                let cells = &places[&w].cells;
                                now.entry(w).or_insert_with(|| cells.clone()).insert(*c);
                            }
                            moved.insert(w);
                        }
                    }
                    Move::Trade(a, b) => {
                        let (pa, pb) = (
                            places.get(a).cloned().unwrap_or_default(),
                            places.get(b).cloned().unwrap_or_default(),
                        );
                        for (w, other) in [(*a, &pb), (*b, &pa)] {
                            let p = places.entry(w).or_default();
                            p.cells.extend(other.cells.iter().copied());
                            p.anywhere |= other.anywhere;
                            now.remove(&w);
                            moved.insert(w);
                        }
                    }
                    Move::Lose => {
                        now.clear();
                        lost = true;
                    }
                    Move::Leave { .. } | Move::Stop => {}
                }
            }
        }
        if before == shape(&places) {
            break;
        }
    }

    if places.values().any(|p| p.anywhere) {
        return None;
    }
    let mut out = Vec::new();
    for (w, p) in places {
        let who = match w {
            Who::Hero => Stander::Hero,
            Who::Event(id) => Stander::Event(id),
            Who::AnyEvent => Stander::AnyEvent,
        };
        let walked = passed.remove(&w).unwrap_or_default();
        let phases = p.through
            || p.held_through
            || routes.iter().any(|r| {
                r.codes.contains(&THROUGH_ON)
                    && (r.who == w || (r.who == Who::AnyEvent && w != Who::Hero))
            });
        let mut stands = p.cells;
        stands.extend(walked.over);
        out.push(Standing {
            who,
            cells: stands,
            risen: walked.risen,
            phases,
        });
    }
    Some(out)
}

/// Whose feet a [`Standing`] is about.
#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Stander {
    Hero,
    /// An event of the map, by its id: a command can name one the map does
    /// not have, and then it is nowhere.
    Event(i32),
    /// Whichever event a common event's "this event" is.
    AnyEvent,
}

/// Where one character's feet can ever be on the map: the cells it stands
/// on, walks through or passes over between the two of a diagonal step;
/// and those it rises from in a jump, 16 px over its cell.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Standing {
    pub who: Stander,
    pub cells: BTreeSet<usize>,
    pub risen: BTreeSet<usize>,
    /// Whether it may walk through walls and other characters somewhere on
    /// the map: a route turns it on.
    pub phases: bool,
}

/// The cells of map `id` a character's sprite can cover: see the module and
/// [`standing`], whose arguments these are.
pub fn covered(
    id: i32,
    map: &Map,
    flags: &[u8],
    commands: &[(i32, Vec<i32>)],
    outside: Outside,
) -> Vec<bool> {
    let grid = Grid::of(map);
    let cells = (grid.width * grid.height) as usize;
    let Some(standing) = standing(id, map, flags, commands, outside) else {
        return vec![true; cells];
    };
    let mut out = vec![false; cells];
    let mut cover = |at: usize, rise: bool| {
        let (x, y) = grid.xy(at);
        let up = if rise { 2 } else { 1 };
        for cy in y - up..=y {
            for cx in x - 1..=x + 1 {
                if let Some(c) = grid.at(cx, cy) {
                    out[c] = true;
                }
            }
        }
    };
    for s in &standing {
        for &c in &s.cells {
            cover(c, false);
        }
        for &c in &s.risen {
            cover(c, true);
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use ditto::schema::{Event, EventCommand, EventCommandCode, EventPage, EventPageMoveType};

    /// A map `rows` draws: `.` a floor tile passable from every side, `#` a
    /// wall passable from none. Lower tiles 5000 and 5001, upper empty.
    fn map(rows: &[&str]) -> (Map, Vec<u8>) {
        let width = rows[0].len() as i32;
        let lower: Vec<i16> = rows
            .iter()
            .flat_map(|r| r.chars().map(|c| if c == '.' { 5000 } else { 5001 }))
            .collect();
        let mut flags = vec![0u8; UPPER as usize + TILES_PER_LAYER as usize];
        flags[5000] = ALL;
        flags[UPPER as usize] = ALL | crate::passability::ABOVE;
        let m = Map {
            width,
            height: rows.len() as i32,
            upper_layer: vec![UPPER as i16; lower.len()],
            lower_layer: lower,
            ..Default::default()
        };
        (m, flags)
    }

    fn event(id: i32, x: i32, y: i32, move_type: i32, commands: Vec<(i32, Vec<i32>)>) -> Event {
        Event {
            id,
            x,
            y,
            pages: vec![EventPage {
                move_type: EventPageMoveType::from_i32(move_type),
                event_commands: commands
                    .into_iter()
                    .map(|(code, parameters)| EventCommand {
                        code: EventCommandCode::from_i32(code),
                        parameters,
                        ..Default::default()
                    })
                    .collect(),
                ..Default::default()
            }],
            ..Default::default()
        }
    }

    /// The covered cells as rows of `x` and `.`.
    fn drawn(m: &Map, out: &[bool]) -> Vec<String> {
        out.chunks(m.width as usize)
            .map(|r| r.iter().map(|&c| if c { 'x' } else { '.' }).collect())
            .collect()
    }

    /// The hero walks his room, and his sprite covers the row above it and
    /// a cell to each side; the room's other side of the wall is never
    /// covered.
    #[test]
    fn the_hero_covers_his_room_and_a_cell_around_it() {
        let (m, flags) = map(&[
            "#######", //
            "#######", //
            "##..###", //
            "##..#.#", //
            "#######", //
        ]);
        let out = covered(
            1,
            &m,
            &flags,
            &[],
            Outside {
                entries: Some(&[(2, 2)]),
                ..Default::default()
            },
        );
        assert_eq!(
            drawn(&m, &out),
            [".......", ".xxxx..", ".xxxx..", ".xxxx..", "......."]
        );
        // A place the game recalls can be any floor: the room past the wall
        // too.
        let recalled = Outside {
            entries: Some(&[(2, 2)]),
            any_open: true,
            ..Default::default()
        };
        assert_eq!(
            drawn(&m, &covered(1, &m, &flags, &[], recalled)),
            [".......", ".xxxx..", ".xxxxxx", ".xxxxxx", "......."]
        );
    }

    /// A `MoveEvent` that walks the hero through the wall takes him to the
    /// cell on its other side, and he walks on from there.
    #[test]
    fn a_route_through_walls_goes_through_them() {
        let (m, flags) = map(&[
            "#######", //
            "#.#...#", //
            "#######", //
        ]);
        // Through on, right twice, through off.
        let route = vec![HERO, 8, 0, 0, THROUGH_ON, 1, 1, THROUGH_OFF];
        let out = covered(
            1,
            &m,
            &flags,
            &[(MOVE_EVENT, route)],
            Outside {
                entries: Some(&[(1, 1)]),
                ..Default::default()
            },
        );
        assert_eq!(drawn(&m, &out), ["xxxxxxx", "xxxxxxx", "......."]);
    }

    /// A jump crosses the wall and lands only on a floor; on the wall it
    /// jumps in place. In the air it rises a row more.
    #[test]
    fn a_jump_lands_on_a_floor_and_rises_a_row() {
        let (m, flags) = map(&[
            "#####", //
            "#####", //
            "#####", //
            ".#.##", //
        ]);
        // Begin jump, right twice, end jump; and one right, onto the wall.
        let over = vec![HERO, 8, 0, 0, BEGIN_JUMP, 1, 1, END_JUMP];
        let onto = vec![HERO, 8, 0, 0, BEGIN_JUMP, 1, END_JUMP];
        let out = covered(
            1,
            &m,
            &flags,
            &[(MOVE_EVENT, over), (MOVE_EVENT, onto)],
            Outside {
                entries: Some(&[(0, 3)]),
                ..Default::default()
            },
        );
        assert_eq!(drawn(&m, &out), [".....", "xxxx.", "xxxx.", "xxxx."]);
    }

    /// An event placed by variables can be anywhere, and so everything is
    /// covered.
    #[test]
    fn a_location_by_variables_is_anywhere() {
        let (mut m, flags) = map(&["###", "#.#", "###"]);
        m.events = vec![event(
            1,
            1,
            1,
            0,
            vec![(CHANGE_EVENT_LOCATION, vec![1, 1, 5, 6])],
        )];
        let out = covered(
            1,
            &m,
            &flags,
            &[],
            Outside {
                entries: Some(&[]),
                ..Default::default()
            },
        );
        assert!(out.iter().all(|&c| c));
    }

    /// A substitution that opens a wall lets the hero through it.
    #[test]
    fn a_substitution_that_opens_a_wall_opens_it() {
        let (m, flags) = map(&["#.##.#"]);
        let out = covered(
            1,
            &m,
            &flags,
            &[],
            Outside {
                entries: Some(&[(1, 0)]),
                ..Default::default()
            },
        );
        assert_eq!(drawn(&m, &out), ["xxx..."]);
        // Lower tile 1 becomes tile 0, the floor.
        let out = covered(
            1,
            &m,
            &flags,
            &[(TILE_SUBSTITUTION, vec![0, 1, 0])],
            Outside {
                entries: Some(&[(1, 0)]),
                ..Default::default()
            },
        );
        assert_eq!(drawn(&m, &out), ["xxxxxx"]);
    }

    /// A door the hero touches walks him through the wall to the next
    /// room; from there he is not beside it, so it never walks him through
    /// the next wall too, as it would if it could run with him anywhere.
    #[test]
    fn a_door_walks_the_hero_only_from_beside_it() {
        let (mut m, flags) = map(&[
            "#.###", //
            "#####", //
            "#####", //
            "#####", //
            "#.###", //
            "#####", //
            "#####", //
            "#####", //
            "#.###", //
        ]);
        let up_four = vec![HERO, 8, 0, 0, THROUGH_ON, 0, 0, 0, 0, THROUGH_OFF];
        let mut door = event(1, 1, 7, 0, vec![(MOVE_EVENT, up_four.clone())]);
        door.pages[0].trigger = ditto::schema::EventPageTrigger::from_i32(1);
        m.events = vec![door];
        let out = covered(
            1,
            &m,
            &flags,
            &[],
            Outside {
                entries: Some(&[(1, 8)]),
                ..Default::default()
            },
        );
        // (The door's own cell is taken as one he may stand on: from there
        // the walk takes him to the wall under the second room.)
        assert_eq!(&drawn(&m, &out)[..2], ["....."; 2]);
        // The same walk in a common event can run anywhere: from the second
        // room it reaches the first.
        let out = covered(
            1,
            &m,
            &flags,
            &[(MOVE_EVENT, up_four)],
            Outside {
                entries: Some(&[(1, 8)]),
                ..Default::default()
            },
        );
        assert_eq!(drawn(&m, &out)[0], "xxx..");
    }

    /// A cutscene walks the hero through a wall into a closed room and
    /// takes him off the map: his route covers its cells, and he walks
    /// neither on from them nor through walls afterwards. Without the
    /// teleport, or in a parallel process the player walks alongside, he
    /// can be left walking through walls, which is anywhere.
    #[test]
    fn a_cutscene_that_takes_the_hero_away_leaves_him_nowhere() {
        let (mut m, flags) = map(&[
            "#######", //
            "#.#...#", //
            "#######", //
        ]);
        // Through on, right twice; and away.
        let route = vec![HERO, 8, 0, 0, THROUGH_ON, 1, 1];
        let scene = |trigger: i32, away: bool| {
            let mut commands = vec![(MOVE_EVENT, route.clone())];
            if away {
                commands.push((TELEPORT, vec![2, 0, 0, 0]));
            }
            let mut e = event(1, 6, 1, 0, commands);
            e.pages[0].trigger = ditto::schema::EventPageTrigger::from_i32(trigger);
            e
        };
        let outside = Outside {
            entries: Some(&[(1, 1)]),
            ..Default::default()
        };
        const AUTOSTART: i32 = 3;
        m.events = vec![scene(AUTOSTART, true)];
        assert_eq!(
            drawn(&m, &covered(1, &m, &flags, &[], outside)),
            ["xxxxxxx", "xxxxxxx", "......."]
        );
        let hero = standing(1, &m, &flags, &[], outside)
            .expect("nobody anywhere")
            .into_iter()
            .find(|s| s.who == Stander::Hero)
            .expect("the hero");
        assert_eq!(hero.cells, [8, 9, 10].into());
        // A common event that turns him, which may run while the scene
        // holds him, walks him on as the scene left him: still held.
        let turn = vec![(MOVE_EVENT, vec![HERO, 8, 0, 0, 13])];
        assert!(standing(1, &m, &flags, &turn, outside).is_some());
        // The same route with no teleport, or in a parallel process.
        m.events = vec![scene(AUTOSTART, false)];
        assert!(standing(1, &m, &flags, &[], outside).is_none());
        m.events = vec![scene(PARALLEL, true)];
        assert!(standing(1, &m, &flags, &[], outside).is_none());
        // Nor if the list may end before the teleport.
        let mut e = scene(AUTOSTART, true);
        e.pages[0].event_commands.insert(
            1,
            EventCommand {
                code: EventCommandCode::from_i32(END_EVENT_PROCESSING),
                indent: 1,
                ..Default::default()
            },
        );
        m.events = vec![e];
        assert!(standing(1, &m, &flags, &[], outside).is_none());
    }

    /// A person drawn with a CharSet seated on a closed cell beside the
    /// hero's room does not open it: nobody steps onto it, and the hero's
    /// sprite never covers the row above it. One drawn with a tile does,
    /// as a bridge.
    #[test]
    fn only_an_event_drawn_with_a_tile_opens_its_cell() {
        let (mut m, flags) = map(&[
            "#####", //
            "#####", //
            "##.##", //
            "##.##", //
        ]);
        let mut seated = event(1, 3, 2, 0, vec![]);
        seated.pages[0].character_name = "People".to_string();
        m.events = vec![seated];
        let outside = Outside {
            entries: Some(&[(2, 3)]),
            ..Default::default()
        };
        let hero = |m: &Map| {
            standing(1, m, &flags, &[], outside)
                .expect("nobody anywhere")
                .into_iter()
                .find(|s| s.who == Stander::Hero)
                .expect("the hero")
                .cells
        };
        assert_eq!(hero(&m), [12, 17].into());
        m.events[0].pages[0].character_name = String::new();
        assert_eq!(hero(&m), [12, 13, 17].into());
    }

    /// A route that is not skippable waits at a step it cannot take, and
    /// what comes after never runs: the hero never walks through the wall.
    /// One that is skippable skips it, and goes on.
    #[test]
    fn a_route_that_cannot_skip_a_step_waits_there() {
        let (m, flags) = map(&[
            "#####", //
            "#.#.#", //
            "#####", //
        ]);
        // Right, into the wall; through on; right again.
        let route = |skippable: i32| vec![HERO, 8, 0, skippable, 1, THROUGH_ON, 1];
        let outside = Outside {
            entries: Some(&[(1, 1)]),
            ..Default::default()
        };
        let waits =
            standing(1, &m, &flags, &[(MOVE_EVENT, route(0))], outside).expect("nobody anywhere");
        let hero = waits
            .iter()
            .find(|s| s.who == Stander::Hero)
            .expect("the hero");
        assert_eq!(hero.cells, [6].into());
        assert!(standing(1, &m, &flags, &[(MOVE_EVENT, route(1))], outside).is_none());
    }

    /// An autostart scene that asks for nothing starts as the hero
    /// arrives, where he arrives: it walks him one cell on and through the
    /// wall above, and away. Not if a page above it can go off while he
    /// walks the corridor: then it can start wherever he is.
    #[test]
    fn a_scene_on_arrival_starts_where_the_hero_arrives() {
        let (mut m, flags) = map(&[
            "######", //
            "#....#", //
            "######", //
        ]);
        let route = vec![HERO, 8, 0, 0, 1, THROUGH_ON, 0];
        const AUTOSTART: i32 = 3;
        let mut scene = event(
            1,
            5,
            1,
            0,
            vec![(MOVE_EVENT, route), (TELEPORT, vec![2, 0, 0, 0])],
        );
        scene.pages[0].trigger = ditto::schema::EventPageTrigger::from_i32(AUTOSTART);
        // Page 2, once switch 7 is on: nothing.
        let mut after = EventPage::default();
        after.condition.flags.switch_a = true;
        after.condition.switch_a_id = 7;
        scene.pages.push(after);
        m.events = vec![scene];
        let outside = Outside {
            entries: Some(&[(1, 1)]),
            ..Default::default()
        };
        let top = |commands: &[(i32, Vec<i32>)]| -> BTreeSet<usize> {
            let all = standing(1, &m, &flags, commands, outside).expect("nobody anywhere");
            let hero = all
                .into_iter()
                .find(|s| s.who == Stander::Hero)
                .expect("the hero");
            hero.cells.into_iter().filter(|&c| c < 6).collect()
        };
        assert_eq!(top(&[]), [2].into());
        // A common event that turns switch 7 off: its code from Ditto, not
        // from the constant under test.
        let control_switches = EventCommandCode::ControlSwitches.to_i32();
        let off = vec![(control_switches, vec![0, 7, 7, SWITCH_OFF_OP])];
        // (The scene's own cell, a tile, is one he can step on.)
        assert_eq!(top(&off), [2, 3, 4, 5].into());
    }

    /// The Hover-Tram's shape: an autostart scene walks the hero two cells
    /// along the aisle and up through the wall onto a seat, turns on switch
    /// 69, which its page 2 asks for, and takes him away. The game recalls
    /// computed places, so he can be on any aisle cell; but the scene runs
    /// once, as he first arrives on (1, 2), and seats him only on (3, 1).
    /// Without the switch it runs every time he arrives, a recall included,
    /// and can seat him on any seat two cells right of the aisle.
    #[test]
    fn a_scene_that_runs_once_starts_where_the_hero_first_arrives() {
        let (mut m, flags) = map(&[
            "#########", //
            "#########", //
            "#.......#", //
            "#########", //
        ]);
        const AUTOSTART: i32 = 3;
        let control_switches = EventCommandCode::ControlSwitches.to_i32();
        let mut seats = |switch_on: bool| -> BTreeSet<usize> {
            let mut commands = vec![(MOVE_EVENT, vec![HERO, 8, 0, 0, 1, 1, THROUGH_ON, 0])];
            if switch_on {
                commands.push((control_switches, vec![0, 69, 69, 0]));
            }
            commands.push((TELEPORT, vec![2, 0, 0, 0]));
            let mut scene = event(1, 7, 0, 0, commands);
            scene.pages[0].trigger = ditto::schema::EventPageTrigger::from_i32(AUTOSTART);
            let mut after = EventPage::default();
            after.condition.flags.switch_a = true;
            after.condition.switch_a_id = 69;
            scene.pages.push(after);
            m.events = vec![scene];
            let outside = Outside {
                entries: Some(&[(1, 2)]),
                any_open: true,
                ..Default::default()
            };
            let all = standing(1, &m, &flags, &[], outside).expect("nobody anywhere");
            let hero = all
                .into_iter()
                .find(|s| s.who == Stander::Hero)
                .expect("the hero");
            hero.cells
                .into_iter()
                .filter(|&c| (9..18).contains(&c))
                .collect()
        };
        assert_eq!(seats(true), [12].into());
        assert_eq!(seats(false), [12, 13, 14, 15, 16].into());
    }

    /// The hero walks in four directions: a floor he could only step onto
    /// diagonally he never reaches by himself.
    #[test]
    fn the_hero_does_not_walk_diagonally() {
        let (m, flags) = map(&[
            "###", //
            "#.#", //
            "##.", //
        ]);
        let outside = Outside {
            entries: Some(&[(1, 1)]),
            ..Default::default()
        };
        let all = standing(1, &m, &flags, &[], outside).expect("nobody anywhere");
        let hero = all
            .iter()
            .find(|s| s.who == Stander::Hero)
            .expect("the hero");
        assert_eq!(hero.cells, [4].into());
    }

    /// A scene's later route walks through walls only from where an
    /// earlier one left the hero walking through them: arrived on (3, 1)
    /// he steps right and phases, and goes up through the wall; arrived on
    /// (1, 1) the step into the wall never comes, and he does not.
    #[test]
    fn a_scene_walks_through_walls_only_from_where_it_phased() {
        let (mut m, flags) = map(&[
            "#######", //
            "#.#...#", //
            "#######", //
        ]);
        const AUTOSTART: i32 = 3;
        let mut scene = event(
            1,
            5,
            2,
            0,
            vec![
                (MOVE_EVENT, vec![HERO, 8, 0, 0, 1, THROUGH_ON]),
                (MOVE_EVENT, vec![HERO, 8, 0, 0, 0]),
                (TELEPORT, vec![2, 0, 0, 0]),
            ],
        );
        scene.pages[0].trigger = ditto::schema::EventPageTrigger::from_i32(AUTOSTART);
        m.events = vec![scene];
        let outside = Outside {
            entries: Some(&[(1, 1), (3, 1)]),
            ..Default::default()
        };
        let all = standing(1, &m, &flags, &[], outside).expect("nobody anywhere");
        let hero = all
            .iter()
            .find(|s| s.who == Stander::Hero)
            .expect("the hero");
        let top: BTreeSet<usize> = hero.cells.iter().copied().filter(|&c| c < 7).collect();
        assert_eq!(top, [4].into());
    }

    #[test]
    fn a_route_is_read_past_its_operands() {
        // Switch 300 on —two integers, 0x82 0x2C—, then a jump.
        assert_eq!(
            decode_route(&[HERO, 8, 0, 0, SWITCH_ON, 0x82, 0x2C, BEGIN_JUMP]),
            [SWITCH_ON, BEGIN_JUMP]
        );
    }
}
