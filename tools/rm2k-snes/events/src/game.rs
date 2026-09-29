//! The game, as much of it as the compiler reads: the maps' events and, of
//! the database, the common events, the troops' pages, the battle
//! animations, the inn's terms, the battle's audio, and which actors and
//! skills there are.
//!
//! It comes from a Ditto dump, read with Ditto's own reader into the
//! schema's types, and is turned here into the few shapes the compiler
//! walks: a command is its code, indent, text and integers, whatever its
//! code is. Two things the project changed on top of the dump are applied
//! while reading, both from the request —see [`Patches`]—: the text boxes
//! it rebuilt for another window, and the names of the graphics it
//! decorated.

use crate::codes::*;
use crate::fail::{Bad, Result};
use ditto::dump::{read_map, Dump};
use ditto::schema;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::path::{Path, PathBuf};

/// One line of a page's script. RM2k's ~130 commands all have this shape.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Command {
    pub code: i32,
    pub indent: i32,
    pub string: String,
    pub parameters: Vec<i32>,
}

impl Command {
    pub fn new(code: i32, indent: i32, string: &str, parameters: Vec<i32>) -> Command {
        Command {
            code,
            indent,
            string: string.to_string(),
            parameters,
        }
    }

    /// Parameter `i`, if the command has it.
    pub fn p(&self, i: usize) -> Option<i64> {
        self.parameters.get(i).map(|&v| v as i64)
    }
}

/// What has to hold for a page to be the active one. Each field is `Some`
/// with its operand when the page asks for it.
#[derive(Debug, Clone, Default)]
pub struct Condition {
    pub switch_a: Option<i32>,
    pub switch_b: Option<i32>,
    /// The variable and the value it has to reach.
    pub variable: Option<(i32, i32)>,
    pub item: Option<i32>,
    pub actor: Option<i32>,
    pub timer: bool,
}

impl Condition {
    pub fn is_empty(&self) -> bool {
        self.switch_a.is_none()
            && self.switch_b.is_none()
            && self.variable.is_none()
            && self.item.is_none()
            && self.actor.is_none()
            && !self.timer
    }
}

/// `compare_operator` is RPG Maker 2003's, and a 2000 game always holds
/// its default: `>=`, which is 1.
pub const CONDITION_OPERATOR: i32 = 1;

/// One of the versions an event can take.
#[derive(Debug, Clone)]
pub struct Page {
    pub trigger: i32,
    pub layer: i32,
    pub move_type: i32,
    pub move_frequency: i32,
    pub move_speed: i32,
    pub animation_type: i32,
    /// The CharSet, as the project named it: see [`Patches::names`].
    pub character_name: String,
    pub character_index: i32,
    pub commands: Vec<Command>,
    /// The page's own route: its commands' codes, whether it repeats and
    /// whether a blocked command is skipped.
    pub route: Vec<i32>,
    pub route_repeat: bool,
    pub route_skippable: bool,
    pub condition: Condition,
}

#[derive(Debug, Clone)]
pub struct Event {
    pub id: i32,
    /// In the order of their ids.
    pub pages: Vec<Page>,
}

impl Event {
    /// The page the engine shows in a freshly started game: the last one
    /// with no condition.
    pub fn active_page(&self) -> Option<&Page> {
        self.pages.iter().rev().find(|p| p.condition.is_empty())
    }
}

#[derive(Debug, Clone)]
pub struct Map {
    pub id: i32,
    /// In the order of their ids, which is the ROM's table's.
    pub events: Vec<Event>,
}

/// A troop's page: when it runs and what it does.
#[derive(Debug, Clone)]
pub struct TroopPage {
    pub condition: schema::TroopPageCondition,
    pub commands: Vec<Command>,
}

/// A battle animation, as much as the map's `ShowBattleAnimation` reads.
#[derive(Debug, Clone)]
pub struct Animation {
    pub timings: Vec<Timing>,
    /// How many frames it has: it lasts two ticks each.
    pub frames: usize,
    /// `Animation::Scope`: 1 is the screen.
    pub scope: i32,
}

#[derive(Debug, Clone)]
pub struct Timing {
    pub frame: i32,
    pub se: Sound,
    pub flash_scope: i32,
    pub rgb: (i32, i32, i32),
    pub power: i32,
}

/// A sound as RM2k plays it: the name, volume, tempo and pan.
pub type Sound = (String, i32, i32, i32);

/// What the project changed on top of the dump, which the request brings.
#[derive(Debug, Clone, Default)]
pub struct Patches {
    /// Maps that are read from another file than the dump's: a fork of one
    /// of the game's, or one the game does not have.
    pub map_files: BTreeMap<i32, PathBuf>,
    /// The text boxes rebuilt for the console's window: the lines as they
    /// are in the dump, and the boxes that go in their place. A box that is
    /// not here is kept as it is. It applies to the maps and the common
    /// events, not to the troops, whose window is another.
    pub boxes: HashMap<Vec<String>, Vec<Vec<String>>>,
    /// Graphics that go by another name: (map, event, page id) and the name.
    /// It is how a translucent page gets a graphic of its own.
    pub names: HashMap<(i32, i32, i32), String>,
}

/// The game.
#[derive(Debug, Clone, Default)]
pub struct Game {
    pub dump: PathBuf,
    pub patches: Patches,
    /// Every map of the game, by number: the ones the sweeps look at.
    pub map_ids: Vec<i32>,
    pub common_events: BTreeMap<i32, CommonEvent>,
    pub troops: BTreeMap<i32, Vec<TroopPage>>,
    pub animations: BTreeMap<i32, Animation>,
    /// The terms the inn's greeting is built with: the gold's, and per inn
    /// type the three greetings, yes and no.
    pub gold_term: String,
    pub inn_terms: [[String; 5]; 2],
    pub battle_music: String,
    pub battle_end_music: String,
    /// The system effects, by their name in `System`.
    pub system_se: BTreeMap<&'static str, Sound>,
    /// The actors, with the skills they learn by level.
    pub actors: BTreeMap<i32, Vec<(i32, i32)>>,
    pub skills: BTreeSet<i32>,
}

#[derive(Debug, Clone)]
pub struct CommonEvent {
    pub trigger: i32,
    pub switch_flag: bool,
    pub switch_id: i32,
    pub commands: Vec<Command>,
}

/// The system effects the battle plays, by their field in `System`.
pub const SYSTEM_SE: [&str; 8] = [
    "battle_se",
    "escape_se",
    "enemy_attack_se",
    "enemy_damaged_se",
    "actor_damaged_se",
    "dodge_se",
    "enemy_death_se",
    "item_se",
];

fn answer(e: ditto::lcf::Error) -> Bad {
    Bad::answer(e.0)
}

fn sound(s: &schema::Sound) -> Sound {
    (s.name.clone(), s.volume, s.tempo, s.balance)
}

/// The commands of a page or a common event, with its boxes rebuilt if
/// `boxes` says so.
pub fn commands(
    raw: &[schema::EventCommand],
    boxes: Option<&HashMap<Vec<String>, Vec<Vec<String>>>>,
) -> Vec<Command> {
    let raw: Vec<Command> = raw
        .iter()
        .map(|c| Command {
            code: c.code.to_i32(),
            indent: c.indent,
            string: c.string.clone(),
            parameters: c.parameters.clone(),
        })
        .collect();
    match boxes {
        Some(boxes) if !boxes.is_empty() => refit(raw, boxes),
        _ => raw,
    }
}

/// A `ShowMessage` with its `ShowMessage_2`s, replaced by the boxes the
/// project rebuilt it into, with the same indent and no parameters. What is
/// not a box, and a box that is not in the table, stays as it is.
fn refit(raw: Vec<Command>, boxes: &HashMap<Vec<String>, Vec<Vec<String>>>) -> Vec<Command> {
    let mut out = Vec::with_capacity(raw.len());
    let mut i = 0;
    while i < raw.len() {
        if raw[i].code != SHOW_MESSAGE {
            out.push(raw[i].clone());
            i += 1;
            continue;
        }
        let mut j = i + 1;
        while j < raw.len() && raw[j].code == SHOW_MESSAGE_2 {
            j += 1;
        }
        let lines: Vec<String> = raw[i..j].iter().map(|c| c.string.clone()).collect();
        match boxes.get(&lines) {
            None => out.extend_from_slice(&raw[i..j]),
            Some(frames) => {
                for frame in frames {
                    for (k, text) in frame.iter().enumerate() {
                        let code = if k == 0 { SHOW_MESSAGE } else { SHOW_MESSAGE_2 };
                        out.push(Command::new(code, raw[i].indent, text, vec![]));
                    }
                }
            }
        }
        i = j;
    }
    out
}

impl Game {
    /// The game in the dump at `data`, with the project's patches.
    pub fn from_dump(data: &Path, patches: Patches) -> Result<Game> {
        let dump = Dump::open(data).map_err(answer)?;
        let mut map_ids = Vec::new();
        for path in dump.map_files().map_err(answer)? {
            let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or("");
            if let Some(n) = stem.strip_prefix("Map").and_then(|n| n.parse::<i32>().ok()) {
                map_ids.push(n);
            }
        }
        map_ids.sort();

        let raw: Vec<schema::CommonEvent> = dump.section("commonevents").map_err(answer)?;
        let common_events = raw
            .iter()
            .map(|c| {
                (
                    c.id,
                    CommonEvent {
                        trigger: c.trigger.to_i32(),
                        switch_flag: c.switch_flag,
                        switch_id: c.switch_id,
                        commands: commands(&c.event_commands, Some(&patches.boxes)),
                    },
                )
            })
            .collect();

        let raw: Vec<schema::Troop> = dump.section("troops").map_err(answer)?;
        let troops = raw
            .iter()
            .map(|t| {
                let mut pages: Vec<&schema::TroopPage> = t.pages.iter().collect();
                pages.sort_by_key(|p| p.id);
                (
                    t.id,
                    pages
                        .into_iter()
                        .map(|p| TroopPage {
                            condition: p.condition.clone(),
                            commands: commands(&p.event_commands, None),
                        })
                        .collect(),
                )
            })
            .collect();

        let raw: Vec<schema::Animation> = dump.section("animations").map_err(answer)?;
        let animations = raw
            .iter()
            .map(|a| {
                let mut timings: Vec<&schema::AnimationTiming> = a.timings.iter().collect();
                timings.sort_by_key(|t| t.id);
                (
                    a.id,
                    Animation {
                        timings: timings
                            .into_iter()
                            .map(|t| Timing {
                                frame: t.frame,
                                se: sound(&t.se),
                                flash_scope: t.flash_scope.to_i32(),
                                rgb: (t.flash_red, t.flash_green, t.flash_blue),
                                power: t.flash_power,
                            })
                            .collect(),
                        frames: a.frames.len(),
                        scope: a.scope.to_i32(),
                    },
                )
            })
            .collect();

        let terms: schema::Terms = dump.section("terms").map_err(answer)?;
        let inn_terms = [
            [
                terms.inn_a_greeting_1.clone(),
                terms.inn_a_greeting_2.clone(),
                terms.inn_a_greeting_3.clone(),
                terms.inn_a_accept.clone(),
                terms.inn_a_cancel.clone(),
            ],
            [
                terms.inn_b_greeting_1.clone(),
                terms.inn_b_greeting_2.clone(),
                terms.inn_b_greeting_3.clone(),
                terms.inn_b_accept.clone(),
                terms.inn_b_cancel.clone(),
            ],
        ];

        let system: schema::System = dump.section("system").map_err(answer)?;
        let system_se = BTreeMap::from([
            ("battle_se", sound(&system.battle_se)),
            ("escape_se", sound(&system.escape_se)),
            ("enemy_attack_se", sound(&system.enemy_attack_se)),
            ("enemy_damaged_se", sound(&system.enemy_damaged_se)),
            ("actor_damaged_se", sound(&system.actor_damaged_se)),
            ("dodge_se", sound(&system.dodge_se)),
            ("enemy_death_se", sound(&system.enemy_death_se)),
            ("item_se", sound(&system.item_se)),
        ]);

        let raw: Vec<schema::Actor> = dump.section("actors").map_err(answer)?;
        let actors = raw
            .iter()
            .map(|a| {
                let mut learning: Vec<&schema::Learning> = a.skills.iter().collect();
                learning.sort_by_key(|l| l.id);
                (
                    a.id,
                    learning
                        .into_iter()
                        .map(|l| (l.level, l.skill_id))
                        .collect(),
                )
            })
            .collect();
        let raw: Vec<schema::Skill> = dump.section("skills").map_err(answer)?;
        let skills = raw.iter().map(|s| s.id).collect();

        Ok(Game {
            dump: data.to_path_buf(),
            patches,
            map_ids,
            common_events,
            troops,
            animations,
            gold_term: terms.gold.clone(),
            inn_terms,
            battle_music: system.battle_music.name.clone(),
            battle_end_music: system.battle_end_music.name.clone(),
            system_se,
            actors,
            skills,
        })
    }

    /// Map `id`: the project's file if it has one, the dump's otherwise.
    pub fn map(&self, id: i32) -> Result<Map> {
        let path = match self.patches.map_files.get(&id) {
            Some(p) => p.clone(),
            None => self.dump.join("maps").join(format!("Map{id:04}.json")),
        };
        let raw = read_map(&path).map_err(answer)?;
        Ok(self.convert(id, &raw))
    }

    fn convert(&self, id: i32, raw: &schema::Map) -> Map {
        let mut events: Vec<&schema::Event> = raw.events.iter().collect();
        events.sort_by_key(|e| e.id);
        let events = events
            .into_iter()
            .map(|e| {
                let mut pages: Vec<&schema::EventPage> = e.pages.iter().collect();
                pages.sort_by_key(|p| p.id);
                Event {
                    id: e.id,
                    pages: pages
                        .into_iter()
                        .map(|p| {
                            let c = &p.condition;
                            let f = &c.flags;
                            let name = self
                                .patches
                                .names
                                .get(&(id, e.id, p.id))
                                .cloned()
                                .unwrap_or_else(|| p.character_name.clone());
                            Page {
                                trigger: p.trigger.to_i32(),
                                layer: p.layer.to_i32(),
                                move_type: p.move_type.to_i32(),
                                move_frequency: p.move_frequency,
                                move_speed: p.move_speed.to_i32(),
                                animation_type: p.animation_type.to_i32(),
                                character_name: name,
                                character_index: p.character_index,
                                commands: commands(&p.event_commands, Some(&self.patches.boxes)),
                                route: p
                                    .move_route
                                    .move_commands
                                    .iter()
                                    .map(|m| m.command_id.to_i32())
                                    .collect(),
                                route_repeat: p.move_route.repeat,
                                route_skippable: p.move_route.skippable,
                                condition: Condition {
                                    switch_a: f.switch_a.then_some(c.switch_a_id),
                                    switch_b: f.switch_b.then_some(c.switch_b_id),
                                    variable: f
                                        .variable
                                        .then_some((c.variable_id, c.variable_value)),
                                    item: f.item.then_some(c.item_id),
                                    actor: f.actor.then_some(c.actor_id),
                                    timer: f.timer,
                                },
                            }
                        })
                        .collect(),
                }
            })
            .collect();
        Map { id, events }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn show(code: i32, text: &str) -> Command {
        Command::new(code, 1, text, vec![])
    }

    #[test]
    fn a_box_the_project_rebuilt_goes_in_its_place_and_the_rest_stays() {
        let raw = vec![
            show(SHOW_MESSAGE, "A"),
            show(SHOW_MESSAGE_2, "B"),
            Command::new(WAIT, 1, "", vec![5]),
            show(SHOW_MESSAGE, "C"),
        ];
        let boxes = HashMap::from([(
            vec!["A".to_string(), "B".to_string()],
            vec![
                vec!["X".to_string()],
                vec!["Y".to_string(), "Z".to_string()],
            ],
        )]);
        let out = refit(raw, &boxes);
        let codes: Vec<(i32, &str)> = out.iter().map(|c| (c.code, c.string.as_str())).collect();
        assert_eq!(
            codes,
            [
                (SHOW_MESSAGE, "X"),
                (SHOW_MESSAGE, "Y"),
                (SHOW_MESSAGE_2, "Z"),
                (WAIT, ""),
                (SHOW_MESSAGE, "C")
            ]
        );
        assert!(out.iter().all(|c| c.indent == 1));
    }
}
