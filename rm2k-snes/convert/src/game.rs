//! The game, as much of it as the converter reads to decide what goes in
//! the cartridge: its maps' events and commands, of the database the
//! party, the actors' graphics, the items, the enemies and troops, the
//! terrains' backdrops, the common events, the battle animations and the
//! ChipSets, and the map tree.
//!
//! It comes from a Ditto dump, read with Ditto's own reader into the
//! schema's types: there is no model of the format here. What the project
//! changed on top of the dump is applied while reading, the way every
//! stage applies it: its maps and ChipSets (see [`crate::fork`]), and the
//! names the port gives some graphics —a translucent page's, baked against
//! its cell; see [`decorate_translucent`]—.
//!
//! Which dump: the game directory's own, if it has one —a `ditto.json`
//! inside—, which is how another game is read; and the project's
//! otherwise. The project's patches apply only to the project's dump.

use crate::fail::{Result, Stop};
use crate::fork::Forks;
use ditto::dump::{read_map, Dump};
use ditto::schema;
use rm2k_project::windows::WindowBackground;
use rm2k_project::Project;
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// One line of a page's script: code, indent, a string and integers,
/// whatever the code is.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Command {
    pub code: i32,
    pub indent: i32,
    pub string: String,
    pub parameters: Vec<i32>,
}

impl Command {
    pub fn from_dump(c: &schema::EventCommand) -> Command {
        Command {
            code: c.code.to_i32(),
            indent: c.indent,
            string: c.string.clone(),
            parameters: c.parameters.clone(),
        }
    }
}

pub fn commands(raw: &[schema::EventCommand]) -> Vec<Command> {
    raw.iter().map(Command::from_dump).collect()
}

/// An event page, with what the converter reads of it.
#[derive(Debug, Clone)]
pub struct Page {
    pub id: i32,
    /// The CharSet as the port names it: see [`decorate_translucent`], and
    /// `separate_from_hero` in [`crate::maps`].
    pub character_name: String,
    /// The name as the dump has it.
    pub dump_name: String,
    pub character_index: i32,
    pub direction: i32,
    pub pattern: i32,
    pub layer: i32,
    pub animation_type: i32,
    pub commands: Vec<Command>,
}

#[derive(Debug, Clone)]
pub struct Event {
    pub id: i32,
    pub x: i32,
    pub y: i32,
    /// In the order of their ids.
    pub pages: Vec<Page>,
}

/// A map, with its events in the order of their ids —which is the ROM's
/// table's—.
#[derive(Debug, Clone)]
pub struct GameMap {
    pub id: i32,
    pub chipset_id: i32,
    pub width: i32,
    pub height: i32,
    pub events: Vec<Event>,
    /// The two tile layers, which only the fork's ChipSet images look at.
    pub lower_layer: Vec<i16>,
    pub upper_layer: Vec<i16>,
    /// The cells of the events that share another's row, `(x, y, its id)`:
    /// see [`crate::trim::twins`]. Empty in a map whose events fit.
    pub twins: Vec<(i32, i32, i32)>,
}

impl GameMap {
    /// Every command of every page, in order.
    pub fn all_commands(&self) -> impl Iterator<Item = &Command> {
        self.events.iter().flat_map(|e| e.pages.iter().flat_map(|p| p.commands.iter()))
    }
}

/// A battle animation, as much as the converter reads of it.
#[derive(Debug, Clone)]
pub struct Animation {
    pub name: String,
    pub sheet: String,
    pub large: bool,
    pub scope: i32,
    pub position: i32,
}

/// A troop: its enemies and where each stands, in the order of the
/// members' ids, and its pages' commands.
#[derive(Debug, Clone)]
pub struct Troop {
    pub members: Vec<i32>,
    pub positions: Vec<(i32, i32)>,
    pub pages: Vec<Vec<Command>>,
}

/// The database, as much of it as the converter reads.
#[derive(Debug, Clone, Default)]
pub struct Database {
    pub actors: BTreeMap<i32, schema::Actor>,
    pub items: BTreeMap<i32, schema::Item>,
    pub enemies: BTreeMap<i32, schema::Enemy>,
    /// Fit to what a battle holds: see `rm2k_snes_battle::fit`.
    pub troops: BTreeMap<i32, Troop>,
    /// What each troop with too many members lost to fit, by troop.
    pub troop_cuts: BTreeMap<i32, rm2k_snes_battle::fit::Cut>,
    /// Each terrain's battle backdrop, "" for none.
    pub terrain_backdrops: BTreeMap<i32, String>,
    /// The common events' commands, by number.
    pub common_events: BTreeMap<i32, Vec<Command>>,
    /// The automatic common events with a switch, and their switch: see
    /// [`crate::common_pages`].
    pub autostart_commons: BTreeMap<i32, i32>,
    pub animations: BTreeMap<i32, Animation>,
    /// The ChipSets, with the ones the project adds.
    pub chipsets: BTreeMap<i32, schema::Chipset>,
    pub party: Vec<i32>,
    pub system_name: String,
    pub title_name: String,
    pub gameover_name: String,
}

impl Database {
    pub fn actor(&self, id: i32) -> Result<&schema::Actor> {
        self.actors
            .get(&id)
            .ok_or_else(|| Stop::new(format!("actor {id} is not in the database")))
    }
}

/// The map tree, with the nodes of the maps the game does not have: what
/// a map inherits and its encounters are `rm2k-rules`' to say.
#[derive(Debug, Clone, Default)]
pub struct Tree {
    pub rules: rm2k_rules::tree::Tree,
    /// The nodes the project added, as its files write them, in order: a
    /// stage that reads the tree itself gets them in its request.
    pub added_nodes: Vec<Value>,
}

impl Tree {
    pub fn name(&self, id: i32) -> &str {
        self.rules.get(id).map_or("?", |n| n.name.as_str())
    }

    /// The battle backdrop of an encounter on this map, or None for the
    /// terrain's.
    pub fn map_background(&self, map_id: i32) -> Option<String> {
        self.rules.background(map_id).map(str::to_string)
    }

    /// The names of the nodes whose backdrop is their own: what a battle
    /// can ask for from the tree.
    pub fn named_backgrounds(&self) -> Vec<String> {
        self.rules
            .nodes
            .values()
            .filter(|n| n.background_type.to_i32() == 2 && !n.background_name.is_empty())
            .map(|n| n.background_name.clone())
            .collect()
    }
}

/// The CharSets drawn opaque even though their page says translucent,
/// lowercase, and how the rest are drawn: what `decorate_translucent`
/// needs.
#[derive(Debug, Clone)]
pub struct Translucent {
    pub opaque: Vec<String>,
    /// `TRANSLUCENT_MODE`: "dither" goes back to the checkerboard, to
    /// compare both on the same tree; anything else bakes.
    pub mode: String,
}

/// The suffixes the port's made-up graphics carry: see `wally`'s
/// `sheets.rs`, which draws them.
pub const BAKED_SUFFIX: &str = "~horneado";
pub const DITHER_SUFFIX: &str = "~trama";
pub const COPY_SUFFIX: &str = "~aparte";
pub const TILE_PREFIX: &str = "@tile:";

/// The name the graphic of a translucent page carries. Three ways out,
/// and the first one wins: those in `[graphics] opaque` of the project are
/// drawn opaque —taro's decision, a deliberate divergence from RM2k—, the
/// rest go baked against their cell's background, and `TRANSLUCENT_MODE=
/// dither` goes back to the checkerboard. For the rest of the program it is
/// another CharSet: the baked name carries the map and the cell, which is
/// all `wally` needs to rebuild the background.
pub fn decorate_translucent(t: &Translucent, name: &str, map_id: i32, x: i32, y: i32) -> String {
    if t.opaque.iter().any(|o| *o == name.to_lowercase()) {
        return name.to_string();
    }
    if t.mode == "dither" {
        return format!("{name}{DITHER_SUFFIX}");
    }
    format!("{name}{BAKED_SUFFIX}:{map_id}:{x}:{y}")
}

/// The game, read once.
pub struct Game {
    /// The original game's folder, where the pictures and the music are.
    pub game_dir: PathBuf,
    /// The RTP, where what the game does not ship is looked for: the
    /// converter sets it, and the stages it calls get it as `--rtp-dir`.
    pub rtp_dir: Option<PathBuf>,
    /// The dump the data is read from.
    pub dump: PathBuf,
    pub forks: Forks,
    pub db: Database,
    pub tree: Tree,
    pub translucent: Translucent,
    /// The pictures the game crops instead of scaling.
    pub cropped: crate::pictures::Cropped,
    /// `[graphics] system`, the System the cartridge draws with instead of
    /// the database's —see [`system_choice`]—. None, the database's.
    pub system: Option<String>,
    /// `[windows.background]`: what fills the windows of each System
    /// instead of its own background, by its name —see
    /// [`Game::window_background`]—.
    pub window_backgrounds: BTreeMap<String, WindowBackground>,
    /// `[graphics] decorative_events`: whether the events that are only a
    /// drawing are painted into the background and stop being events. Off
    /// when the key is missing: it changes the map of any game that has
    /// them, and a game opts in.
    pub decorative: bool,
    /// `[graphics] map_pictures`: whether the `ShowPicture` pictures that
    /// are part of a map are drawn into it —see [`crate::map_pictures`]—.
    /// Off when the key is missing, for the same reason.
    pub map_pictures: bool,
    /// `[graphics] painted_maps`: whether a map whose panorama is the map
    /// itself —fixed to it, with nothing of the ChipSet over it— goes
    /// painted, a tile per cell uploaded as it comes into view: see
    /// `Way::Painted` in Wally. Off when the key is missing, for the same
    /// reason.
    pub painted_maps: bool,
    /// The events each map leaves out because they do not fit in the
    /// console's RAM, by map and id: see [`crate::trim`] and
    /// [`Game::trim`]. They are taken out as the map is read.
    pub dropped: BTreeMap<i32, BTreeSet<i32>>,
    /// The twins each map keeps as a cell, by map: `(x, y, id of the event
    /// whose row it shares)`. See [`crate::trim::twins`].
    pub twins: BTreeMap<i32, Vec<(i32, i32, i32)>>,
    /// Of [`Game::dropped`], the ones that lose something —not the twins—:
    /// `(map, event, (x, y), what it loses)`, for the cartridge's
    /// degradations.
    pub trimmed: Vec<(i32, i32, (i32, i32), &'static str)>,
}

/// `[graphics] system`, **optional**: the System to draw with instead of
/// the one the database names. A name, looked for as the database's is
/// —in the game and then in the RTP—; or a picture of the project's own,
/// a path relative to the project file that ends in `.png` or `.bmp`,
/// which comes back absolute. The screens stage takes it as `--system`.
fn system_choice(project: &Project) -> Result<Option<String>> {
    let keys = ["graphics", "system"];
    if project.value(&keys).is_err() {
        return Ok(None);
    }
    let given = project.string(&keys)?;
    let lower = given.to_ascii_lowercase();
    if !(lower.ends_with(".png") || lower.ends_with(".bmp")) {
        return Ok(Some(given.to_string()));
    }
    let path = rm2k_project::absolute(project.directory().join(given));
    if !path.is_file() {
        crate::stop!("[graphics] system: {} is not a file", path.display());
    }
    Ok(Some(path.to_string_lossy().into_owned()))
}

/// The dump a game folder is read from: its own, if it has one, and the
/// project's otherwise.
pub fn dump_dir(game_dir: &Path, project: &Project) -> Result<PathBuf> {
    let own = rm2k_project::absolute(game_dir);
    if ditto::dump::is_dump(&own) {
        return Ok(own);
    }
    Ok(project.data()?)
}

impl Game {
    /// The System the cartridge starts with, by the name
    /// `[windows.background]` keys it with: `[graphics] system`'s —the
    /// stem of its file, if it is a picture of the project's own— or the
    /// database's.
    pub fn starting_system(&self) -> String {
        match &self.system {
            Some(spec) if Path::new(spec).is_absolute() => Path::new(spec)
                .file_stem()
                .map(|s| s.to_string_lossy().into_owned())
                .unwrap_or_default(),
            Some(name) => name.clone(),
            None => self.db.system_name.clone(),
        }
    }

    /// What fills the windows of System `system` instead of its own
    /// background, or None: then they keep the System's.
    pub fn window_background(&self, system: &str) -> Option<&WindowBackground> {
        let system = system.to_lowercase();
        self.window_backgrounds
            .iter()
            .find(|(name, _)| name.to_lowercase() == system)
            .map(|(_, v)| v)
    }

    /// That every System `[windows.background]` names is one the game can
    /// draw with —in its folder, in the RTP, or `[graphics] system`—: a
    /// misspelt name would leave its windows as they were without a word.
    /// Once the RTP is known.
    pub fn check_window_backgrounds(&self) -> Result<()> {
        let starting = self.starting_system().to_lowercase();
        let rtp: Vec<PathBuf> = self.rtp_dir.iter().cloned().collect();
        for name in self.window_backgrounds.keys() {
            let found = name.to_lowercase() == starting
                || crate::resources::find(&[&self.game_dir], "System", name, &[".png", ".bmp"]).is_some()
                || crate::resources::find(&rtp, "System", name, &[".png", ".bmp"]).is_some();
            if !found {
                crate::stop!(
                    "[windows.background] {}: the game has no System by that name, nor does the RTP; \
                     the key is the System's name without its extension",
                    crate::text::repr(name)
                );
            }
        }
        Ok(())
    }

    pub fn read(game_dir: &Path, project: &Project) -> Result<Game> {
        let dump_path = dump_dir(game_dir, project)?;
        let this_game = dump_path == project.data()?;
        let dump = Dump::open(&dump_path)?;
        let forks = if this_game {
            // The maps the game has, by number: a fork replaces one of
            // those, and a new map is none of them.
            let mut game_maps = std::collections::BTreeSet::new();
            for path in dump.map_files()? {
                let stem = path.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
                if let Some(n) = stem.strip_prefix("Map").and_then(|n| n.parse::<i32>().ok()) {
                    game_maps.insert(n);
                }
            }
            Forks::read(&project.manual_patches()?, &game_maps)?
        } else {
            Forks::default()
        };
        let db = database(&dump, &forks)?;
        let mut tree = Tree::default();
        for node in dump.tree()?.maps {
            tree.rules.insert(node);
        }
        for (id, (_json, _tiles, node)) in &forks.new_maps {
            let parsed: schema::MapInfo = serde_json::from_value(node.clone())
                .map_err(|e| Stop::new(format!("the node of new map {id}: {e}")))?;
            tree.rules.insert(parsed);
            tree.added_nodes.push(node.clone());
        }
        let opaque = project
            .strings(&["graphics", "opaque"])?
            .into_iter()
            .map(|s| s.to_lowercase())
            .collect();
        let translucent = Translucent {
            opaque,
            mode: std::env::var("TRANSLUCENT_MODE").unwrap_or_else(|_| "baked".to_string()),
        };
        Ok(Game {
            game_dir: rm2k_project::absolute(game_dir),
            rtp_dir: None,
            dump: dump_path,
            forks,
            db,
            tree,
            translucent,
            cropped: crate::pictures::Cropped::read(project)?,
            system: system_choice(project)?,
            window_backgrounds: project.window_backgrounds()?,
            decorative: match project.value(&["graphics", "decorative_events"]) {
                Err(_) => false,
                Ok(_) => project.boolean(&["graphics", "decorative_events"])?,
            },
            map_pictures: match project.value(&["graphics", "map_pictures"]) {
                Err(_) => false,
                Ok(_) => project.boolean(&["graphics", "map_pictures"])?,
            },
            painted_maps: match project.value(&["graphics", "painted_maps"]) {
                Err(_) => false,
                Ok(_) => project.boolean(&["graphics", "painted_maps"])?,
            },
            dropped: BTreeMap::new(),
            twins: BTreeMap::new(),
            trimmed: Vec::new(),
        })
    }

    /// Decides which events of `maps` do not fit in the console's RAM, and
    /// says it: from here on [`Game::map`] reads them without those, and
    /// the requests carry them —[`Game::dropped_json`]—. The map where the
    /// test page runs, `test_event_map`, keeps one place for its event.
    /// `test_commands` are the test pages', which can name events too.
    /// `events_max` is how many the RAM holds: `EV_MAX`, unless a test
    /// asks for fewer.
    pub fn trim(
        &mut self,
        maps: &[i32],
        test_commands: &[Command],
        test_event_map: Option<i32>,
        events_max: usize,
    ) -> Result<()> {
        let common: Vec<&Command> = self.db.common_events.values().flatten().chain(test_commands).collect();
        for &id in maps {
            let raw = self.raw_map(id)?;
            let cap = events_max - usize::from(test_event_map == Some(id));
            if raw.events.len() <= cap {
                continue;
            }
            let named = crate::trim::named(&raw.events, common.iter().copied());
            // First the twins, which lose nothing; then, if they are not
            // enough, what loses the least. A first one left out takes its
            // twins with it.
            let twins = crate::trim::twins(&raw.events, &named);
            let twin_ids: BTreeSet<i32> = twins.iter().map(|&(t, _)| t).collect();
            let rest: Vec<schema::Event> = raw.events.iter().filter(|e| !twin_ids.contains(&e.id)).cloned().collect();
            let out = crate::trim::left_out(&rest, &named, cap);
            let gone: BTreeSet<i32> = out.iter().map(|&(e, _)| e).collect();
            let kept: Vec<(i32, i32, i32)> = twins
                .iter()
                .filter(|(_, owner)| !gone.contains(owner))
                .filter_map(|&(t, owner)| raw.events.iter().find(|e| e.id == t).map(|e| (e.x, e.y, owner)))
                .collect();
            if !twins.is_empty() {
                println!(
                    "  map {id}: {} events and the console's RAM holds {cap}: {} are twins —the same pages as an \
                     earlier one, nothing drawn, still— and share the row of one of {} events",
                    raw.events.len(),
                    twins.len(),
                    twins.iter().map(|&(_, o)| o).collect::<BTreeSet<_>>().len()
                );
            }
            if !out.is_empty() {
                // The twins of one left out are left out too, with it.
                let mut lost = out.clone();
                for &(t, owner) in &twins {
                    if let Some(&(_, loss)) = out.iter().find(|&&(e, _)| e == owner) {
                        lost.push((t, loss));
                    }
                }
                lost.sort();
                println!("{}", crate::trim::warning(id, raw.events.len() - twins.len(), cap, &lost));
                for &(e, loss) in &lost {
                    if loss == crate::trim::Loss::Nothing {
                        continue;
                    }
                    let at = raw.events.iter().find(|r| r.id == e).map_or((0, 0), |r| (r.x, r.y));
                    self.trimmed.push((id, e, at, loss.describe()));
                }
            }
            self.dropped.insert(id, twin_ids.into_iter().chain(gone).collect());
            if !kept.is_empty() {
                self.twins.insert(id, kept);
            }
        }
        Ok(())
    }

    /// [`Game::dropped`] as the stages' requests carry it: the ids by map
    /// number as text.
    pub fn dropped_json(&self) -> Value {
        Value::Object(self.dropped.iter().map(|(m, ids)| (m.to_string(), serde_json::json!(ids))).collect())
    }

    /// The same, only map `id`'s: what a map's own request carries.
    pub fn dropped_json_of(&self, id: i32) -> Value {
        Value::Object(
            self.dropped.get(&id).map(|ids| (id.to_string(), serde_json::json!(ids))).into_iter().collect(),
        )
    }

    /// Map `id` as the project has it, with every event.
    fn raw_map(&self, id: i32) -> Result<schema::Map> {
        Ok(match self.forks.map_file(id) {
            Some(path) => read_map(path)?,
            None => Dump::open(&self.dump)?.map(id as u32)?,
        })
    }

    /// Map `id`: the project's file if it has one, the dump's otherwise,
    /// with the translucent pages' graphics decorated.
    pub fn map(&self, id: i32) -> Result<GameMap> {
        let raw = self.raw_map(id)?;
        let dropped = self.dropped.get(&id);
        let mut events: Vec<&schema::Event> =
            raw.events.iter().filter(|e| dropped.is_none_or(|d| !d.contains(&e.id))).collect();
        events.sort_by_key(|e| e.id);
        let events = events
            .into_iter()
            .map(|e| {
                let mut pages: Vec<&schema::EventPage> = e.pages.iter().collect();
                pages.sort_by_key(|p| p.id);
                Event {
                    id: e.id,
                    x: e.x,
                    y: e.y,
                    pages: pages
                        .into_iter()
                        .map(|p| {
                            let mut name = p.character_name.clone();
                            if p.translucent && !name.is_empty() {
                                name = decorate_translucent(&self.translucent, &name, id, e.x, e.y);
                            }
                            Page {
                                id: p.id,
                                character_name: name,
                                dump_name: p.character_name.clone(),
                                character_index: p.character_index,
                                direction: p.character_direction.to_i32(),
                                pattern: p.character_pattern.to_i32(),
                                layer: p.layer.to_i32(),
                                animation_type: p.animation_type.to_i32(),
                                commands: commands(&p.event_commands),
                            }
                        })
                        .collect(),
                }
            })
            .collect();
        Ok(GameMap {
            id,
            chipset_id: raw.chipset_id,
            width: raw.width,
            height: raw.height,
            events,
            lower_layer: raw.lower_layer,
            upper_layer: raw.upper_layer,
            twins: self.twins.get(&id).cloned().unwrap_or_default(),
        })
    }

    /// The numbers of every map in the original game's folder, in order:
    /// what a sweep over the whole game walks.
    pub fn game_map_ids(&self) -> Result<Vec<i32>> {
        let mut ids = Vec::new();
        let entries = std::fs::read_dir(&self.game_dir).map_err(|e| crate::fail::io(&self.game_dir, e))?;
        for entry in entries.flatten() {
            let name = entry.file_name().to_string_lossy().to_string();
            // `Map[0-9][0-9][0-9][0-9].lmu`, as the glob had it.
            if name.len() == 11
                && name.starts_with("Map")
                && name.ends_with(".lmu")
                && name[3..7].bytes().all(|b| b.is_ascii_digit())
            {
                ids.push(name[3..7].parse().unwrap());
            }
        }
        ids.sort();
        Ok(ids)
    }

    /// The numbers of every map of the dump, in order.
    pub fn dump_map_ids(&self) -> Result<Vec<i32>> {
        let mut ids = Vec::new();
        for path in Dump::open(&self.dump)?.map_files()? {
            let stem = path.file_stem().map(|s| s.to_string_lossy().to_string()).unwrap_or_default();
            if let Some(n) = stem.strip_prefix("Map").and_then(|n| n.parse::<i32>().ok()) {
                ids.push(n);
            }
        }
        ids.sort();
        Ok(ids)
    }

    pub fn chipset(&self, id: i32) -> Result<&schema::Chipset> {
        self.db
            .chipsets
            .get(&id)
            .ok_or_else(|| Stop::new(format!("ChipSet {id} is not in the database")))
    }
}

fn database(dump: &Dump, forks: &Forks) -> Result<Database> {
    let mut db = Database::default();
    for a in dump.section::<Vec<schema::Actor>>("actors")? {
        db.actors.insert(a.id, a);
    }
    for i in dump.section::<Vec<schema::Item>>("items")? {
        db.items.insert(i.id, i);
    }
    for e in dump.section::<Vec<schema::Enemy>>("enemies")? {
        db.enemies.insert(e.id, e);
    }
    for mut t in dump.section::<Vec<schema::Troop>>("troops")? {
        // Sorted, and cut to what a battle holds: the battle's tables and
        // the event compiler cut it the same way.
        if let Some(cut) = rm2k_snes_battle::fit::fit(&mut t) {
            db.troop_cuts.insert(t.id, cut);
        }
        let members = &t.members;
        let pages = &t.pages;
        db.troops.insert(
            t.id,
            Troop {
                members: members.iter().map(|m| m.enemy_id).collect(),
                positions: members.iter().map(|m| (m.x, m.y)).collect(),
                pages: pages.iter().map(|p| commands(&p.event_commands)).collect(),
            },
        );
    }
    for t in dump.section::<Vec<schema::Terrain>>("terrains")? {
        db.terrain_backdrops.insert(t.id, t.background_name.clone());
    }
    for c in dump.section::<Vec<schema::CommonEvent>>("commonevents")? {
        db.common_events.insert(c.id, commands(&c.event_commands));
        if c.trigger.to_i32() == rm2k_snes_events::codes::TRIGGER_AUTOSTART && c.switch_flag {
            db.autostart_commons.insert(c.id, c.switch_id);
        }
    }
    for a in dump.section::<Vec<schema::Animation>>("animations")? {
        db.animations.insert(
            a.id,
            Animation {
                name: a.name.clone(),
                sheet: a.animation_name.clone(),
                large: a.large,
                scope: a.scope.to_i32(),
                position: a.position.to_i32(),
            },
        );
    }
    for c in dump.section::<Vec<schema::Chipset>>("chipsets")? {
        db.chipsets.insert(c.id, c);
    }
    for (number, (path, data)) in &forks.chipsets {
        if db.chipsets.contains_key(number) {
            crate::stop!("ChipSet {number} is already in the dump: the project adds, it does not replace");
        }
        let entry: schema::Chipset = serde_json::from_value(data["chipset"].clone())
            .map_err(|e| Stop::new(format!("{}: {e}", path.display())))?;
        db.chipsets.insert(*number, entry);
    }
    let system: schema::System = dump.section("system")?;
    db.party = system.party.iter().map(|&a| a as i32).collect();
    db.system_name = system.system_name.clone();
    db.title_name = system.title_name.clone();
    db.gameover_name = system.gameover_name.clone();
    Ok(db)
}
