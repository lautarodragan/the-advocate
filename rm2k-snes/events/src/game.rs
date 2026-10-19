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
use rm2k_rules::event::starting_page;
use rm2k_snes_bytecode::level::Level;
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
    /// The variable, how it is compared —`CheckOperator`'s codes, see
    /// [`CONDITION_OPERATOR`]— and against what.
    pub variable: Option<(i32, i32, i32)>,
    pub item: Option<i32>,
    pub actor: Option<i32>,
    /// The seconds the timer has to be at or under.
    pub timer: Option<i32>,
}

/// How RPG Maker 2000 compares a page's variable: `>=`, which is 1 of
/// `CheckOperator`'s codes —`==` `>=` `<=` `>` `<` `!=`—. 2003 lets the page
/// choose, in `compare_operator`, and a 2000 game ignores the field, as
/// `Game_Event::AreConditionsMet` does with `Player::IsRPG2k()`.
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
    /// The column it shows, 0 to 2: the one a spinning page keeps.
    pub character_pattern: i32,
    pub commands: Vec<Command>,
    /// The page's own route: its commands' codes, whether it repeats and
    /// whether a blocked command is skipped.
    pub route: Vec<i32>,
    pub route_repeat: bool,
    pub route_skippable: bool,
    pub condition: Condition,
    /// RM2k's number for the page, from 1: only to say where something is.
    pub id: i32,
    /// Two fields nothing compiles, kept to say they are lost: the page
    /// drawn half transparent, and RM2k 2003's "forbid overlap" —see
    /// [`crate::losses`]—.
    pub translucent: bool,
    pub overlap_forbidden: bool,
}

#[derive(Debug, Clone)]
pub struct Event {
    pub id: i32,
    /// Its cell, only to say where something is.
    pub x: i32,
    pub y: i32,
    /// In the order of their ids.
    pub pages: Vec<Page>,
    /// Which of them the engine shows in a freshly started game, if any:
    /// `rm2k-rules`' `starting_page`.
    pub starting: Option<usize>,
}

impl Event {
    pub fn active_page(&self) -> Option<&Page> {
        self.starting.map(|k| &self.pages[k])
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
    /// Common events the project declares as counters: the common event's
    /// number and the variable it shows. See `compile_counter`.
    pub counters: BTreeMap<i32, i32>,
    /// What the project's custom menus ask of the events: the common event
    /// each one replaces, with the menu's number —its body becomes
    /// `OP_MENU_OPEN`—, and the ones a menu runs before a page, which get a
    /// body of their own without messages or pictures. See [`crate::commons`].
    pub menus: MenuHooks,
    /// The events each map leaves out because they do not fit in the
    /// console's RAM, by map and id: the map is read without them, so the
    /// indices are the converter's. A page that names one does not compile.
    pub dropped: BTreeMap<i32, std::collections::BTreeSet<i32>>,
    /// The exits each map could not keep, by map: the one event of each
    /// that keeps its row to say so —its pages become [`exit_left_out_box`],
    /// with their trigger and layer—, and whose row the other exits left
    /// out share as twins. See `trim.rs` in the converter.
    pub boxed_exits: BTreeMap<i32, std::collections::BTreeSet<i32>>,
    /// The Systems the cartridge carries a message window for, in its
    /// order: the one it starts with, and every one a `ChangeSystemGraphics`
    /// switches to. Empty is a cartridge that does not switch, and then the
    /// command does not compile.
    pub systems: Vec<String>,
}

/// See [`Patches::menus`].
#[derive(Debug, Clone, Default)]
pub struct MenuHooks {
    pub replaced: BTreeMap<i32, u8>,
    pub before: std::collections::BTreeSet<i32>,
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
    ///
    /// They are the game's and not ours —the game this was built with
    /// charges in "Cr"— so they come from the LDB and not from a literal,
    /// for the same reason as the title screen's. The two sets are
    /// `ShowInn`'s `inn_type`: 0 set A and 1 set B.
    ///
    /// Without them `ShowInn` does not compile —and says so—, instead of
    /// building the greeting with made-up words: the price and the currency
    /// are the only thing the player is going to read to decide.
    pub gold_term: String,
    pub inn_terms: [[String; 5]; 2],
    pub battle_music: String,
    pub battle_end_music: String,
    /// And their levels —volume, tempo, balance and fade-in—, which the ROM
    /// starts a game with: a `ChangeSystemBGM` changes them with the song.
    pub battle_levels: [Level; 2],
    /// The system effects, by their name in `System`.
    pub system_se: BTreeMap<&'static str, Sound>,
    /// The actors, with the skills they learn by level. It is what the two
    /// actor questions of `ConditionalBranch` and `ChangeEquipment` look at
    /// to know an actor exists: it is read once before compiling anything,
    /// so all pages read the same reading of the LDB.
    pub actors: BTreeMap<i32, Vec<(i32, i32)>>,
    /// Each actor's name in the database: what `\N[n]` shows until some
    /// `ChangeHeroName` changes it; see [`crate::indices::hero_names`].
    pub actor_names: BTreeMap<i32, String>,
    pub skills: BTreeSet<i32>,
    /// The items `ChangeEquipment` can equip: by number, its type —1 the
    /// weapon to 5 the accessory, the slot plus one— and who can use it,
    /// `actor_set` by actor number minus one.
    pub items: BTreeMap<i32, (i32, Vec<bool>)>,
    /// The two-handed weapons and the actors with two weapons: what
    /// `ChangeEquipment` needs to know whether equipping a weapon is the
    /// plain case. See it in `compile.rs`.
    pub two_handed: BTreeSet<i32>,
    pub two_weapons: BTreeSet<i32>,
    /// The switches the database turns on by itself: its switch items' and
    /// its switch skills'. The ROM's table has to hold them too: see
    /// [`crate::indices::switch_top`].
    pub database_switches: BTreeSet<i32>,
    /// Whether the database is RPG Maker 2003's —`System.ldb_id` 2003, the
    /// way Ditto tells them apart—. The one command whose parameters are
    /// laid out by engine is `KeyInputProc`: see its arm in `compile.rs`.
    pub is_2003: bool,
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

/// The page of an exit the converter could not keep: a box that says so,
/// in place of a `Teleport` that would not be there, like the one of a
/// `Teleport` to a map the cartridge does not carry. The same box for every
/// exit of the map, which share its row as twins: nothing tells which one
/// it is but the cell the player is on.
pub fn exit_left_out_box() -> Vec<Command> {
    vec![
        Command::new(10110, 0, "An exit left out here: the", vec![]),
        Command::new(20110, 0, "map has more events than", vec![]),
        Command::new(20110, 0, "the console holds.", vec![]),
    ]
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

        let mut raw: Vec<schema::Troop> = dump.section("troops").map_err(answer)?;
        let troops = raw
            .iter_mut()
            .map(|t| {
                // Its pages renumbered to the members the battle carries,
                // as the battle's tables read them: see the battle's `fit`.
                rm2k_snes_battle::fit::fit(t);
                (
                    t.id,
                    t.pages
                        .iter()
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
        let actor_names = raw.iter().map(|a| (a.id, a.name.clone())).collect();
        let two_weapons = raw.iter().filter(|a| a.two_weapon).map(|a| a.id).collect();
        let raw: Vec<schema::Skill> = dump.section("skills").map_err(answer)?;
        let skills = raw.iter().map(|s| s.id).collect();
        let mut database_switches: BTreeSet<i32> = raw
            .iter()
            .filter(|s| s.r#type == schema::SkillType::Switch)
            .map(|s| s.switch_id)
            .collect();
        // A dump without items equips nothing: `ChangeEquipment` to equip
        // then does not compile, which is what it did before it read them.
        // The small game of this crate's tests has none.
        let raw: Vec<schema::Item> = dump.section("items").unwrap_or_default();
        let items = raw
            .iter()
            .map(|i| (i.id, (i.r#type.to_i32(), i.actor_set.clone())))
            .collect();
        let two_handed = raw.iter().filter(|i| i.two_handed).map(|i| i.id).collect();
        database_switches.extend(
            raw.iter()
                .filter(|i| i.r#type == schema::ItemType::Switch)
                .map(|i| i.switch_id),
        );

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
            battle_levels: [&system.battle_music, &system.battle_end_music].map(|m| {
                Level::new(
                    m.fadein.into(),
                    m.volume.into(),
                    m.tempo.into(),
                    m.balance.into(),
                )
            }),
            system_se,
            actors,
            actor_names,
            skills,
            items,
            two_handed,
            two_weapons,
            database_switches,
            is_2003: system.ldb_id == 2003,
        })
    }

    /// Every System a `ChangeSystemGraphics` of the game names, once each,
    /// in the order they are found: the maps', the common events' and the
    /// troops'.
    pub fn system_names(&self) -> Result<Vec<String>> {
        let mut out: Vec<String> = Vec::new();
        let mut note = |c: &Command| {
            if c.code == CHANGE_SYSTEM_GRAPHICS
                && !out.iter().any(|s| s.eq_ignore_ascii_case(&c.string))
            {
                out.push(c.string.clone());
            }
        };
        for &id in &self.map_ids {
            for event in self.map(id)?.events {
                event
                    .pages
                    .iter()
                    .flat_map(|p| p.commands.iter())
                    .for_each(&mut note);
            }
        }
        self.common_events
            .values()
            .flat_map(|c| c.commands.iter())
            .for_each(&mut note);
        self.troops
            .values()
            .flatten()
            .flat_map(|p| p.commands.iter())
            .for_each(&mut note);
        Ok(out)
    }

    /// The panorama map `id` names, if it can be read: only to tell whether
    /// a `ChangePBG` asks for another picture —see its arm—, which is rare
    /// enough to read the map again for it.
    pub fn panorama(&self, id: i32) -> Option<String> {
        let raw = match self.patches.map_files.get(&id) {
            Some(p) => read_map(p),
            None => Dump::open(&self.dump).and_then(|d| d.map(id as u32)),
        }
        .ok()?;
        Some(raw.parallax_name.clone())
    }

    /// Map `id`: the project's file if it has one, the dump's otherwise.
    pub fn map(&self, id: i32) -> Result<Map> {
        let raw = match self.patches.map_files.get(&id) {
            Some(p) => read_map(p),
            // Where the dump keeps a map is Ditto's to know.
            None => Dump::open(&self.dump).and_then(|d| d.map(id as u32)),
        }
        .map_err(answer)?;
        Ok(self.convert(id, &raw))
    }

    fn convert(&self, id: i32, raw: &schema::Map) -> Map {
        let dropped = self.patches.dropped.get(&id);
        let mut events: Vec<&schema::Event> = raw
            .events
            .iter()
            .filter(|e| dropped.is_none_or(|d| !d.contains(&e.id)))
            .collect();
        events.sort_by_key(|e| e.id);
        let events = events
            .into_iter()
            .map(|e| {
                let mut pages: Vec<&schema::EventPage> = e.pages.iter().collect();
                pages.sort_by_key(|p| p.id);
                let starting =
                    starting_page(e).and_then(|s| pages.iter().position(|p| p.id == s.id));
                Event {
                    id: e.id,
                    starting,
                    pages: pages
                        .into_iter()
                        .map(|p| {
                            let c = &p.condition;
                            let f = &c.flags;
                            let comparison = if self.is_2003 {
                                c.compare_operator.to_i32()
                            } else {
                                CONDITION_OPERATOR
                            };
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
                                character_pattern: p.character_pattern.to_i32(),
                                commands: if self
                                    .patches
                                    .boxed_exits
                                    .get(&id)
                                    .is_some_and(|b| b.contains(&e.id))
                                {
                                    exit_left_out_box()
                                } else {
                                    commands(&p.event_commands, Some(&self.patches.boxes))
                                },
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
                                    // A comparison outside `CheckOperator`'s six
                                    // asks for nothing, as in `AreConditionsMet`.
                                    variable: (f.variable && (0..=5).contains(&comparison))
                                        .then_some((c.variable_id, comparison, c.variable_value)),
                                    item: f.item.then_some(c.item_id),
                                    actor: f.actor.then_some(c.actor_id),
                                    timer: f.timer.then_some(c.timer_sec),
                                },
                                id: p.id,
                                translucent: p.translucent,
                                overlap_forbidden: p.overlap_forbidden,
                            }
                        })
                        .collect(),
                    x: e.x,
                    y: e.y,
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

    /// A page's variable comparison is 2003's to choose and 2000 always
    /// asks `>=`. Until 2026-10-19 the 2003 one was dropped and every page
    /// asked `>=`: Zounds' map 88 asked "X <= 1" as "X >= 1", and the
    /// desert sent the hero back to its middle forever —see
    /// tasks/zounds-entering-map-88-loops-on-a-teleport.md—.
    #[test]
    fn a_2003_page_keeps_its_comparison_and_a_2000_one_asks_at_least() {
        let mut raw = schema::Map::default();
        let mut event = schema::Event {
            id: 1,
            ..Default::default()
        };
        let mut page = schema::EventPage {
            id: 1,
            ..Default::default()
        };
        page.condition.flags.variable = true;
        page.condition.variable_id = 7;
        page.condition.variable_value = 1;
        page.condition.compare_operator = schema::EventPageConditionComparison::LessEqual;
        event.pages.push(page);
        raw.events.push(event);
        let asks = |is_2003: bool| {
            let game = Game {
                is_2003,
                ..Game::default()
            };
            game.convert(88, &raw).events[0].pages[0].condition.variable
        };
        assert_eq!(asks(true), Some((7, 2, 1)));
        assert_eq!(asks(false), Some((7, CONDITION_OPERATOR, 1)));
    }
}
