//! A game's cartridges, the ones its project file declares in
//! `[cartridges]`: `release`, the ROM that is played and that carries every
//! test case, and the others, with what does not fit in it.
//!
//! **What each cartridge carries belongs to the game**, and is in its project
//! file: which maps go in, which are left out, which cartridges exist and
//! which cases each one carries. What lives here is the mechanism that reads
//! it and builds: the converter, the MSU-1 tracks and the assembler, each
//! called as a library, in this process. Until 2026-11-25 the first two
//! were run from the PATH, `rm2k-snes-convert` and `rm2k-snes-audio msu`.
//!
//! **The maps are expanded here and passed to the converter as flags**, on
//! purpose: the stamp carries the flags and not the game's data, so a tree
//! that changes which maps go in makes the cartridge stale only if the list
//! travels expanded.

use std::collections::{BTreeMap, BTreeSet};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::mpsc;

use ditto::dump::Dump;
use ditto::schema::{MapInfo, TreeMapMapType};
use rm2k_project::environment::Environment;
use rm2k_project::log::{self, Log};
use rm2k_project::{cache, suite, Project};
use rm2k_rules::tree::Tree;
use serde_json::{json, Value};
use sha2::{Digest, Sha256};

use crate::assemble::{assemble, which, Failure};
use rm2k_snes_audio::game::Game;
use rm2k_snes_audio::tracks::{Tracks, GAIN};

pub use rm2k_project::environment::RELEASE;

/// What the converter needs from the machine, which it receives as flags,
/// as its binary did until 2026-11-25; and what the builder adds: where the
/// test cartridges go, and the replacements for the MSU-1 tracks.
pub const TO_CONVERTER: &[&str] = &["game_dir", "rtp_dir", "soundfont", "cache"];
pub const FROM_ENVIRONMENT: &[&str] = &[
    "game_dir",
    "rtp_dir",
    "soundfont",
    "cache",
    "test_cartridges",
    "replacements",
];

/// The variables the converter reads by itself, which no flag carries: they
/// change the ROM, so they go in the stamp. Without them, a cartridge built
/// with `TRANSLUCENT_MODE=dither` stayed "up to date" when built again
/// without it, and the other way round.
pub const CONVERTER_VARIABLES: &[&str] = &["TRANSLUCENT_MODE", "DITHER_PATTERN"];

/// The stamp's line for each of `CONVERTER_VARIABLES`, with its value as
/// `lookup` gives it: unset is not the same as empty.
pub fn variables_stamp(lookup: impl Fn(&str) -> Option<String>) -> String {
    CONVERTER_VARIABLES
        .iter()
        .map(|name| match lookup(name) {
            Some(value) => format!("variable {name}={value:?}\n"),
            None => format!("variable {name} unset\n"),
        })
        .collect()
}

/// The extensions of what the stages read from the original game, in lower
/// case: the graphics —`.xyz` too, which the battle's lookups accept— and
/// the songs and sounds. What else a game ships is not read, or reaches
/// the ROM some other way: the `.lmu`, `.ldb` and `.lmt` through the dump;
/// the saves, which change every time someone plays the original, the
/// executable, the `.mp3` and the videos, never. A lookup that starts
/// accepting another extension adds it here.
pub const GAME_EXTENSIONS: &[&str] = &["png", "bmp", "xyz", "mid", "wav"];

/// The file beside each built cartridge's ROM with what it has left: see
/// [`Cartridges::measure_space`].
pub const SPACE: &str = "space.json";

/// What a build thread leaves: whether it built —`release` says that
/// through a channel instead, earlier— and the tracks' line.
struct Outcome {
    built: Option<Result<bool, String>>,
    tracks: Option<Result<String, String>>,
}

/// One cartridge of the file.
#[derive(Debug, Clone)]
pub struct Cartridge {
    pub name: String,
    /// The converter flags, in the usual order —the party, the starting map,
    /// the maps, the graphics, the rest—, because they go into the stamp as
    /// they are.
    pub flags: Vec<String>,
    /// Its cases, or None if it is all of them.
    pub cases: Option<Vec<String>>,
}

/// Everything the project file says about the cartridges, read once.
pub struct Cartridges {
    pub project: Project,
    pub environment: Environment,
    /// Where the suite's runtime and the converter's sources are.
    pub root: PathBuf,
    pub runtime: PathBuf,
    pub cases_dir: PathBuf,
    pub maps_below: i64,
    pub excluded_maps: Vec<i64>,
    /// The file's `added`, and the debug map after them when it goes in.
    pub added_maps: Vec<i64>,
    pub with_debug_map: bool,
    /// None in a game that has no debug map, which is any but ABL.
    pub debug_map: Option<i64>,
    pub game_maps: Vec<i64>,
    /// The ones that only exist for the test cases.
    pub test_maps: Vec<i64>,
    pub rom_name: String,
    pub cartridges: Vec<Cartridge>,
    excluded_cases: BTreeSet<String>,
    pub real_game: String,
    pub debug_map_entry: String,
    /// The program that builds: the converter, the bank packing and the
    /// assembler are its code, so the fingerprint hashes it. The running
    /// one, set by [`Cartridges::load`]; a test sets a stand-in.
    pub builder: PathBuf,
    /// The map tree, with the new maps' nodes in it.
    tree: Tree,
}

fn read_json(path: &Path) -> Result<Value, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    serde_json::from_str(&text).map_err(|e| format!("{}: {e}", path.display()))
}

/// The names of `directory`'s entries, sorted, without the hidden ones.
fn entries(directory: &Path) -> Result<Vec<String>, String> {
    let mut names = Vec::new();
    let read = std::fs::read_dir(directory).map_err(|e| format!("{}: {e}", directory.display()))?;
    for entry in read {
        let entry = entry.map_err(|e| format!("{}: {e}", directory.display()))?;
        let name = entry.file_name().to_string_lossy().into_owned();
        if !name.starts_with('.') {
            names.push(name);
        }
    }
    names.sort();
    Ok(names)
}

/// The maps the game does not have: `{id: tree node}` of each `MapNNNN.json`
/// in the patches' `maps/` that brings a `tree` field. A map that does not
/// exist has no node in the tree either, so each one brings its own; a fork
/// of one of the game's brings none. That the two are what they say is
/// checked by the converter, `fork.rs` in `rm2k-snes-convert`.
fn new_maps(project: &Project) -> Result<BTreeMap<i64, MapInfo>, String> {
    let folder = project.manual_maps()?;
    let mut found = BTreeMap::new();
    if !folder.is_dir() {
        return Ok(found);
    }
    for entry in entries(&folder)? {
        let Some(base) = entry.strip_suffix(".json") else {
            continue;
        };
        let id = base
            .strip_prefix("Map")
            .filter(|n| !n.is_empty() && n.chars().all(|c| c.is_ascii_digit()))
            .and_then(|n| n.parse::<i64>().ok())
            .ok_or_else(|| format!("{entry}: the name has to be MapNNNN"))?;
        let data = read_json(&folder.join(&entry))?;
        if data.get("tree").is_none() {
            continue;
        }
        let node = data
            .get("tree")
            .filter(|n| n.get("id").and_then(Value::as_i64) == Some(id))
            .ok_or_else(|| {
                format!(
                    "{entry}: the id inside, the one in the `tree` node and the one in the \
                     file name have to be the same"
                )
            })?;
        // A node in the dump's shape: Ditto's type reads it.
        let node =
            serde_json::from_value(node.clone()).map_err(|e| format!("{entry}: tree: {e}"))?;
        found.insert(id, node);
    }
    Ok(found)
}

/// A value of a cartridge's table that is either a word or a list.
enum WordOrList<'a> {
    Word(&'a str),
    List,
}

impl Cartridges {
    /// Reads the project file, the map tree and the new maps.
    pub fn load(project: Project, mut environment: Environment) -> Result<Cartridges, String> {
        // A `.zip` game or RTP, as a directory from here on —and for the
        // tools this runs—: see `unpack`.
        environment.unpack(&project)?;
        let p = &project;
        let maps_below = p.int(&["maps", "below"])?;
        let excluded_maps = p.ints(&["maps", "excluded"])?;
        let mut added_maps = p.ints(&["maps", "added"])?;
        let test_maps = p.ints(&["maps", "test"])?;

        // The debug map is the only new map: it comes from there and not from
        // the project file so as not to write the number twice. A game that
        // has none has no new maps at all, and then it cannot ask for it.
        let new = new_maps(p)?;
        let with_debug_map = p.boolean(&["debug", "debug_map"])?;
        if new.len() > 1 || (with_debug_map && new.is_empty()) {
            return Err(format!(
                "the debug map is the only new map in {}, and there are {}: {:?}",
                p.manual_maps()?.display(),
                new.len(),
                new.keys().collect::<Vec<_>>()
            ));
        }
        let debug_map = new.keys().next().copied();
        if let (true, Some(m)) = (with_debug_map, debug_map) {
            added_maps.push(m);
        }
        // The enemies' HP in battle, in every cartridge.
        let with_enemy_hp = p.boolean(&["debug", "enemy_hp"])?;
        // And the debug screen in the pause menu, in every cartridge too.
        let with_debug_screen = p.boolean(&["debug", "debug_screen"])?;
        // And Select walking the hero through everything, RPG_RT's test
        // play's Ctrl: its own key and not the debug screen's, because every
        // port has that one on and this changes how the hero walks.
        let with_phasing = p.boolean(&["debug", "phasing"])?;

        // The tree comes from Ditto's reader, into the schema's types: this
        // crate keeps no model of the dump. A new map's node goes over the
        // game's one with its number, if there is one.
        let dump = Dump::open(&p.data()?).map_err(|e| e.0)?;
        let mut tree = Tree::from(&dump.tree().map_err(|e| e.0)?);
        for node in new.into_values() {
            tree.insert(node);
        }

        let mut cartridges = Cartridges {
            root: suite::root(),
            runtime: suite::runtime(),
            cases_dir: p.cases()?,
            maps_below,
            excluded_maps,
            added_maps,
            with_debug_map,
            debug_map,
            game_maps: Vec::new(),
            test_maps,
            rom_name: p.string(&["rom", "name"])?.to_string(),
            cartridges: Vec::new(),
            // Read once `release` is known to be there, below.
            excluded_cases: BTreeSet::new(),
            real_game: p.string(&["cases", "real_game"])?.to_string(),
            debug_map_entry: p.string(&["cases", "debug_map_entry"])?.to_string(),
            builder: std::env::current_exe()
                .map_err(|e| format!("the builder cannot find its own binary: {e}"))?,
            tree,
            project: project.clone(),
            environment,
        };
        cartridges.game_maps =
            cartridges.rule_maps(&cartridges.excluded_maps, &cartridges.added_maps);
        let names: Vec<String> = cartridges
            .project
            .table(&["cartridges"])?
            .keys()
            .cloned()
            .collect();
        for name in names {
            let c =
                cartridges.read_cartridge(&name, with_enemy_hp, with_debug_screen, with_phasing)?;
            cartridges.cartridges.push(c);
        }
        if !cartridges
            .cartridges
            .iter()
            .any(|c| c.name == RELEASE && c.cases.is_none())
        {
            return Err(format!(
                "{}: missing [cartridges.{RELEASE}], with cases = \"all\"",
                cartridges.project.file().display()
            ));
        }
        // The cases `release` does not carry, because there they would
        // change the others' images.
        cartridges.excluded_cases = cartridges
            .project
            .strings(&["cartridges", RELEASE, "excluded_cases"])?
            .into_iter()
            .collect();
        Ok(cartridges)
    }

    fn word_or_list<'a>(&'a self, keys: &[&str]) -> Result<WordOrList<'a>, String> {
        let v = self.project.value(keys)?;
        match v {
            toml::Value::String(s) => Ok(WordOrList::Word(s)),
            toml::Value::Array(_) => Ok(WordOrList::List),
            other => Err(self.project.wrong_type(keys, "str or list", other).0),
        }
    }

    fn read_cartridge(
        &self,
        name: &str,
        with_enemy_hp: bool,
        with_debug_screen: bool,
        with_phasing: bool,
    ) -> Result<Cartridge, String> {
        let p = &self.project;
        let key = |k: &'static str| ["cartridges", name, k];
        let start_map = p.int(&key("start_map"))?;
        let party = p.ints(&key("party"))?;
        let maps: Vec<i64> = match self.word_or_list(&key("maps"))? {
            WordOrList::Word("game") => self.all_maps(),
            WordOrList::Word(other) => {
                return Err(format!(
                    "{}: maps of {name} is a list or \"game\", and it is {other:?}",
                    p.file().display()
                ))
            }
            WordOrList::List => p.ints(&key("maps"))?,
        };
        let cases = match self.word_or_list(&key("cases"))? {
            WordOrList::Word("all") => None,
            WordOrList::Word(other) => {
                return Err(format!(
                    "{}: cases of {name} is a list or \"all\", and it is {other:?}",
                    p.file().display()
                ))
            }
            WordOrList::List => Some(p.strings(&key("cases"))?),
        };
        let mut flags = Vec::new();
        if !party.is_empty() {
            flags.push("--party".to_string());
            flags.extend(party.iter().map(i64::to_string));
        }
        flags.extend(["--map-id".to_string(), start_map.to_string()]);
        // Without other maps, no `--maps`: empty, the converter refuses it.
        let others: Vec<String> = maps
            .iter()
            .filter(|&&m| m != start_map)
            .map(i64::to_string)
            .collect();
        if !others.is_empty() {
            flags.push("--maps".to_string());
            flags.extend(others);
        }
        for graphic in p.list(&key("test_graphics"))? {
            let pair = graphic
                .as_array()
                .and_then(|a| Some((a.first()?.as_str()?, a.get(1)?.as_str()?)))
                .ok_or_else(|| {
                    p.wrong_type(&key("test_graphics"), "a list of [CharSet, index]", graphic)
                        .0
                })?;
            flags.extend([
                "--test-graphic".to_string(),
                pair.0.to_string(),
                pair.1.to_string(),
            ]);
        }
        flags.extend(p.strings(&key("flags"))?);
        if with_enemy_hp {
            flags.push("--enemy-hp".to_string());
        }
        if with_debug_screen {
            flags.push("--debug-screen".to_string());
        }
        if with_phasing {
            flags.push("--phasing".to_string());
        }
        Ok(Cartridge {
            name: name.to_string(),
            flags,
            cases,
        })
    }

    /// The game's maps in the order they go to `--maps`: the ones from the
    /// rule —a real map of the tree with an id below `below`, and not
    /// excluded— in ascending order, and then the added ones. **The order is
    /// that of the ROM's table**, so changing it moves the table.
    pub fn rule_maps(&self, excluded: &[i64], added: &[i64]) -> Vec<i64> {
        let mut maps: Vec<i64> = (1..self.maps_below)
            .filter(|&m| self.is_map(m) && !excluded.contains(&m))
            .collect();
        let from_rule = maps.clone();
        maps.extend(added.iter().filter(|m| !from_rule.contains(m)));
        maps
    }

    /// Whether the tree's node `id` is a real map, and not the root or an area.
    fn is_map(&self, id: i64) -> bool {
        i32::try_from(id)
            .ok()
            .and_then(|id| self.tree.get(id))
            .is_some_and(|n| n.r#type == TreeMapMapType::Map)
    }

    /// The game's maps and the test ones: what "game" means in a cartridge.
    pub fn all_maps(&self) -> Vec<i64> {
        let mut maps = self.game_maps.clone();
        maps.extend(&self.test_maps);
        maps
    }

    pub fn get(&self, name: &str) -> Option<&Cartridge> {
        self.cartridges.iter().find(|c| c.name == name)
    }

    fn cartridge(&self, name: &str) -> Result<&Cartridge, String> {
        self.get(name).ok_or_else(|| {
            format!(
                "there is no cartridge {name:?}: the ones there are {}",
                self.names().join(", ")
            )
        })
    }

    pub fn names(&self) -> Vec<String> {
        self.cartridges.iter().map(|c| c.name.clone()).collect()
    }

    // --- The cases ----------------------------------------------------------

    /// The case on page 0 of `release`: what the game runs when it starts.
    /// With the debug map, its entry; without it, the real game.
    pub fn first_case(&self, with_debug_map: bool) -> &str {
        if with_debug_map {
            &self.debug_map_entry
        } else {
            &self.real_game
        }
    }

    /// The cases `release` does not carry. Without the debug map, not its
    /// entry either: its `Teleport` leads to a map that is not there.
    pub fn excluded_cases(&self, with_debug_map: bool) -> BTreeSet<String> {
        let mut out = self.excluded_cases.clone();
        if !with_debug_map {
            out.insert(self.debug_map_entry.clone());
        }
        out
    }

    /// Every case: one JSON per case in the cases directory.
    pub fn all_cases(&self) -> Result<Vec<String>, String> {
        let mut out: Vec<String> = entries(&self.cases_dir)?
            .into_iter()
            .filter_map(|n| n.strip_suffix(".json").map(str::to_string))
            .collect();
        out.sort();
        Ok(out)
    }

    /// The cartridge's cases, in the order of its pages. `with_debug_map`
    /// is a parameter so the clean delivery can be looked at without
    /// building it.
    pub fn cases_of(&self, name: &str, with_debug_map: bool) -> Result<Vec<String>, String> {
        match &self.cartridge(name)?.cases {
            Some(cases) => Ok(cases.clone()),
            None => {
                let first = self.first_case(with_debug_map).to_string();
                let excluded = self.excluded_cases(with_debug_map);
                let mut out = vec![first.clone()];
                out.extend(
                    self.all_cases()?
                        .into_iter()
                        .filter(|n| !excluded.contains(n) && *n != first),
                );
                Ok(out)
            }
        }
    }

    /// [`Self::cases_of`], as the file says.
    pub fn cases(&self, name: &str) -> Result<Vec<String>, String> {
        self.cases_of(name, self.with_debug_map)
    }

    /// Whether the cartridge starts without a title screen.
    pub fn without_title(&self, name: &str) -> Result<bool, String> {
        Ok(self
            .cartridge(name)?
            .flags
            .iter()
            .any(|f| f == "--no-title"))
    }

    /// The cartridges that carry the case: first the ones that carry all of
    /// them, then the rest by name. **Not in the file's order**, on purpose:
    /// a case that is in two runs in the first, and with the file in another
    /// order it would run in the small one and move its golden without
    /// anyone touching the case.
    pub fn where_is(&self, case: &str) -> Result<Vec<String>, String> {
        let mut out = Vec::new();
        for c in &self.cartridges {
            if self.cases(&c.name)?.iter().any(|n| n == case) {
                out.push(c);
            }
        }
        out.sort_by(|a, b| (a.cases.is_some(), &a.name).cmp(&(b.cases.is_some(), &b.name)));
        Ok(out.into_iter().map(|c| c.name.clone()).collect())
    }

    fn case_path(&self, case: &str) -> PathBuf {
        self.cases_dir.join(format!("{case}.json"))
    }

    /// (the cases, whether each one starts with a `Teleport`), per page: the
    /// harness waits for the arrival of the ones that do.
    pub fn manifest(&self, name: &str) -> Result<(Vec<String>, Vec<bool>), String> {
        let cases = self.cases(name)?;
        let mut teleports = Vec::new();
        for case in &cases {
            let data = read_json(&self.case_path(case))?;
            let first = data
                .get("event_commands")
                .and_then(Value::as_array)
                .and_then(|c| c.first())
                .and_then(|c| c.get("code"))
                .and_then(Value::as_str);
            teleports.push(first == Some("Teleport"));
        }
        Ok((cases, teleports))
    }

    // --- Where each one is ------------------------------------------------

    /// The cartridge's directory: `release` in the project's build, the
    /// others with the test cartridges.
    pub fn directory(&self, name: &str) -> Result<PathBuf, String> {
        Ok(self.environment.cartridge(&self.project, name)?)
    }

    /// The ROM. `release`'s carries the game's name, because the MSU-1 looks
    /// for its tracks by the ROM's name; the others are called `test`.
    pub fn rom_of(&self, name: &str) -> Result<PathBuf, String> {
        let file = if name == RELEASE {
            format!("{}.sfc", self.rom_name)
        } else {
            "test.sfc".to_string()
        };
        Ok(self.directory(name)?.join(file))
    }

    /// The `.msu` next to the ROM and with its name: the converter writes it
    /// with the data the MSU-1 serves to the ROM, and it is also what turns
    /// the MSU-1 on for the tracks.
    pub fn msu_of(&self, name: &str) -> Result<PathBuf, String> {
        Ok(self.rom_of(name)?.with_extension("msu"))
    }

    // --- Whether it is up to date -------------------------------------------

    /// The files [`Self::fingerprint`] reads, in order: whatever changes the
    /// ROM and is not here leaves it silently stale. That is why the
    /// binaries and the hand-made patches go in, since they change it without
    /// touching any source. `runtime` is a parameter so a test can pass a
    /// tree built by hand.
    ///
    /// **The game's dump goes in, and so do the original game's resources,
    /// by content.** A change to a `.lmu` reaches the ROM only through the
    /// dump —whoever regenerates it is the game's recipe, not this—, and
    /// the dump is also edited by hand to isolate a cause; what the stages
    /// read from the original game itself —its PNGs, its MIDIs— changes
    /// when the game is retouched. Until 2026-10-11 both stayed out, and
    /// either left the cartridge "up to date" with the old ROM. Which
    /// resources, in [`Self::game_files`].
    ///
    /// **The RTP and the SoundFont go in by their path, not their
    /// content**, in [`Self::fingerprint`]: they are not edited, and if
    /// they are, `--force` rebuilds by hand. It is taro's, 2026-10-11.
    ///
    /// **A game or an RTP that comes as a `.zip` goes in by the `.zip`'s
    /// content**, whole, and not by what was unpacked from it —see
    /// `Environment::unpack` in `rm2k-project`—: hashing it is cheap, and
    /// a `.zip` is what taro wants the games to be, so that they are not
    /// retouched and every change goes through the patches.
    pub fn fingerprint_files(&self, runtime: &Path) -> Result<Vec<PathBuf>, String> {
        // All of the runtime, and not only what `main.s` includes today: a
        // file that is added and included in the same change has to make the
        // cartridge stale.
        let mut parts = files_below(runtime)?;
        // What assembles, and the program that converts and packs the
        // banks: this one, the running binary and not one of its name on
        // the PATH. The converter, its stages —and the patches, whose files
        // the check reads from the build— are libraries compiled into it, as
        // Voodoo, LZ2, Adeleine, Gunter and `rm2k-render` are into them.
        // Until 2026-11-25 the converter ran from the PATH and went in by
        // its name there, and so did this one, which it then was the same
        // file as unless run from somewhere else.
        for name in ["ca65", "ld65"] {
            parts.push(which(name).ok_or_else(|| {
                format!("`{name}` is not on the PATH, and the cartridges need it")
            })?);
        }
        parts.push(self.builder.clone());
        // The dump, whole: the converter and its stages read it, and it
        // changes without touching any of the above.
        parts.extend(files_below(&self.project.data()?)?);
        // What the stages can read from the original game.
        parts.extend(self.game_files()?);
        // And the RTP, if it is a `.zip`: as a directory it goes by its
        // path, in `fingerprint`.
        if let Some((zip, _)) = self.environment.archive("rtp_dir") {
            parts.push(zip.to_path_buf());
        }
        // The hand-made patches. Their RM2k folders hold the files that
        // replace the game's —see `own_files` in `rm2k-project`—, and each
        // of them goes in with its name, in `fingerprint`: renaming one
        // changes which of the game's it replaces. They reach the converter
        // inside `--game-dir`, but a game that is a `.zip` goes in here as
        // the `.zip` alone.
        let manual = self.project.manual_patches()?;
        let mut patches = Vec::new();
        if manual.is_dir() {
            for directory in entries(&manual)? {
                let directory = manual.join(directory);
                if directory.is_dir() {
                    for file in entries(&directory)? {
                        let path = directory.join(file);
                        if path.is_file() {
                            patches.push(path);
                        } else if path.is_dir() {
                            patches.extend(files_below(&path)?);
                        }
                    }
                }
            }
        }
        sort_as_text(&mut patches);
        parts.extend(patches);
        // And the project file, whole: the converter and the music read it,
        // and not only what reaches the stamp's flags.
        parts.push(self.project.file());
        // And each custom menu's file, which `[menus]` names and the
        // converter reads whole: changing a page's text changes the ROM
        // without touching the project file.
        if let Some(menus) = self
            .project
            .settings()
            .get("menus")
            .and_then(|m| m.as_table())
        {
            for file in menus.values().filter_map(|f| f.as_str()) {
                parts.push(self.project.directory().join(file));
            }
        }
        // And the game's own font, if it brings one: `[text] font` is a
        // sheet's path when it is a PNG —see `font.rs` in
        // `rm2k-snes-convert`—, and retouching the sheet changes the ROM
        // without touching the project file. A font the engine carries is
        // inside the converter's binaries, which are above.
        if let Ok(font) = self.project.string(&["text", "font"]) {
            if font.to_ascii_lowercase().ends_with(".png") {
                parts.push(self.project.directory().join(font));
            }
        }
        // And its ExFont's sheet, which `[text] exfont` names the same way
        // when it is not `false`.
        if let Ok(sheet) = self.project.string(&["text", "exfont"]) {
            parts.push(self.project.directory().join(sheet));
        }
        Ok(parts)
    }

    /// The original game's files the stages can read: every one below
    /// `--game-dir`, in any folder, with an extension in
    /// [`GAME_EXTENSIONS`].
    ///
    /// **What they can read, not what they read.** The lookups are three
    /// functions in three crates —the converter's, `rm2k-render`'s for the
    /// maps and the screens, `rm2k-snes-audio`'s— and a few paths joined by
    /// hand, in separate processes: having each one report what it opens
    /// needs a channel between processes, and a reader that forgets to
    /// report is the same silently stale ROM. A resource the game ships and
    /// does not use goes in too, and retouching it rebuilds for nothing.
    ///
    /// A game that came as a `.zip` is the `.zip`, alone.
    pub fn game_files(&self) -> Result<Vec<PathBuf>, String> {
        if let Some((zip, _)) = self.environment.archive("game_dir") {
            return Ok(vec![zip.to_path_buf()]);
        }
        let game = self.environment.game()?;
        Ok(files_below(game)?
            .into_iter()
            .filter(|path| {
                path.extension()
                    .map(|e| e.to_string_lossy().to_ascii_lowercase())
                    .is_some_and(|e| GAME_EXTENSIONS.contains(&e.as_str()))
            })
            .collect())
    }

    /// What a cartridge depends on, besides its flags and its cases. The
    /// content is looked at and not the date, which a checkout changes.
    pub fn fingerprint(&self) -> Result<String, String> {
        let mut h = Sha256::new();
        let game = self.environment.game()?;
        let own = self.project.own_files()?;
        for path in self.fingerprint_files(&self.runtime)? {
            // A game's file goes in with its name too: renaming a resource
            // changes which one a lookup finds. And so does one of the
            // port's own, which replaces the game's by name.
            if let Ok(name) = path.strip_prefix(game) {
                h.update(format!("game {}\n", name.display()));
            } else if let Ok(name) = path.strip_prefix(&own) {
                h.update(format!("own {}\n", name.display()));
            }
            // A `.zip` by the hash `unpack` already took, and not read twice:
            // it is the biggest file here.
            if let Some((_, hash)) = ["game_dir", "rtp_dir"]
                .iter()
                .filter_map(|n| self.environment.archive(n))
                .find(|(zip, _)| *zip == path)
            {
                h.update(format!("zip {hash}\n"));
                continue;
            }
            h.update(std::fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))?);
        }
        // The RTP and the SoundFont, by their path: see `fingerprint_files`.
        // An RTP that is a `.zip` went in by content, among the files.
        if self.environment.archive("rtp_dir").is_none() {
            h.update(format!("rtp {}\n", self.environment.rtp()?.display()));
        }
        h.update(format!(
            "soundfont {}\n",
            self.environment.soundfont()?.display()
        ));
        Ok(cache::hex(&h.finalize())[..16].to_string())
    }

    /// What the cartridge's stamp has to say for it to be up to date: the
    /// fingerprint, the converter flags, the variables it reads, and each case with the hash of its
    /// file.
    pub fn stamp(&self, name: &str, inputs: &str) -> Result<String, String> {
        let cartridge = self.cartridge(name)?;
        let mut out = format!(
            "inputs {inputs}\nflags {}\n{}",
            serde_json::to_string(&cartridge.flags).unwrap(),
            variables_stamp(|name| std::env::var(name).ok())
        );
        for case in self.cases(name)? {
            let path = self.case_path(&case);
            let bytes = std::fs::read(&path).map_err(|e| format!("{}: {e}", path.display()))?;
            out += &format!("case {case} {}\n", cache::hex(&Sha256::digest(&bytes)));
        }
        Ok(out)
    }

    /// Why the cartridge is no good, or None if it is up to date.
    pub fn stale(&self, name: &str, inputs: &str) -> Result<Option<&'static str>, String> {
        if self.get(name).is_none() {
            return Ok(Some("does not exist"));
        }
        let Ok(stamped) = std::fs::read_to_string(self.directory(name)?.join("stamp.txt")) else {
            return Ok(Some("is not built"));
        };
        if stamped != self.stamp(name, inputs)? {
            return Ok(Some(
                "was built with other sources, other flags or other cases",
            ));
        }
        // The converter writes it along with the ROM and it does not go into
        // the stamp: without it the cartridge would work, but the MSU-1 would
        // have nothing to read.
        if !self.msu_of(name)?.is_file() {
            return Ok(Some("does not have its .msu"));
        }
        Ok(None)
    }

    // --- Building -------------------------------------------------------------

    /// Converts and assembles the cartridge, if it is not up to date or if
    /// `force` says so: that is how one rebuilds after changing what the
    /// fingerprint does not look at by content, the RTP or the SoundFont.
    /// Says whether it built it.
    pub fn build(&self, name: &str, inputs: &str, force: bool) -> Result<bool, String> {
        if !force && self.stale(name, inputs)?.is_none() {
            return Ok(false);
        }
        let directory = self.directory(name)?;
        // The stamp goes before converting: a build that fails half-way
        // with the same inputs would otherwise leave the old one, which
        // still matches, and the cartridge would say "up to date" over
        // whatever the failure left. And so does the space it had.
        let stamp = directory.join("stamp.txt");
        let space = directory.join(SPACE);
        for old in [&stamp, &space] {
            match std::fs::remove_file(old) {
                Err(e) if e.kind() != std::io::ErrorKind::NotFound => {
                    return Err(format!("{}: {e}", old.display()))
                }
                _ => {}
            }
        }
        let rom = self.rom_of(name)?;
        self.convert(name, &directory, &rom, &[])?;
        self.measure_space(name)?;
        std::fs::write(&stamp, self.stamp(name, inputs)?)
            .map_err(|e| format!("{}: {e}", stamp.display()))?;
        Ok(true)
    }

    /// What the built cartridge has left, measured from what its build
    /// left beside the ROM, into [`SPACE`] there: see `space` for each
    /// number. Measured when it is built because it reads the whole `.dbg`,
    /// which takes a fifth of a second a cartridge, and every test session
    /// would otherwise ask it again of a ROM that did not change.
    pub fn measure_space(&self, name: &str) -> Result<serde_json::Value, String> {
        let rom = self.rom_of(name)?;
        let measured = crate::space::measure(&rom, &self.runtime)?.json(&rom);
        let file = self.directory(name)?.join(SPACE);
        std::fs::write(&file, format!("{measured:#}\n"))
            .map_err(|e| format!("{}: {e}", file.display()))?;
        Ok(measured)
    }

    /// The space [`Self::measure_space`] left beside the cartridge, or None
    /// if it left none.
    pub fn space(&self, name: &str) -> Result<Option<serde_json::Value>, String> {
        let file = self.directory(name)?.join(SPACE);
        match std::fs::read_to_string(&file) {
            Ok(text) => serde_json::from_str(&text)
                .map(Some)
                .map_err(|e| format!("{}: {e}", file.display())),
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
            Err(e) => Err(format!("{}: {e}", file.display())),
        }
    }

    /// Builds `names`, each if it is not up to date or if `force` says so,
    /// and the MSU-1 tracks after `release` if `tracks` says so; prints
    /// each one's "built" or "up to date", and the tracks' line. Every one
    /// is tried: the first failure is answered once all have finished.
    pub fn build_these(
        &self,
        names: &[String],
        inputs: &str,
        force: bool,
        tracks: bool,
    ) -> Result<(), String> {
        // The cartridges and the tracks are built at the same time, in
        // threads: each one writes in its own directory, and converts into
        // its own log —see `rm2k_project::log`—. What they share is the disk
        // cache, which writes aside and renames. What is printed stays in
        // the usual order.
        //
        // The tracks, **after `release`** and not alongside it: they are its
        // songs', which the converter leaves next to its ROM. Meanwhile the
        // other cartridges get built.
        std::thread::scope(|scope| {
            let (release_built, release_done) = mpsc::channel();
            let handles: Vec<_> = names
                .iter()
                .map(|name| {
                    let sender = (name == RELEASE).then(|| release_built.clone());
                    scope.spawn(move || {
                        let built = self.build(name, inputs, force);
                        let Some(sender) = sender else {
                            return Outcome {
                                built: Some(built),
                                tracks: None,
                            };
                        };
                        // `release` says it is built before its tracks start.
                        let ok = built.is_ok();
                        let _ = sender.send(built);
                        Outcome {
                            built: None,
                            tracks: (ok && tracks).then(|| self.msu_tracks()),
                        }
                    })
                })
                .collect();
            drop(release_built);
            // Every thread is joined before answering, so a failure does not
            // leave a conversion half-way through a directory; the first
            // failure is the answer.
            let mut failed = None;
            for (name, handle) in names.iter().zip(handles) {
                let mut said = |done: Result<String, String>| match done {
                    Ok(line) => println!("{line}"),
                    Err(e) => {
                        failed.get_or_insert(e);
                    }
                };
                let state = |built: bool| if built { "built" } else { "up to date" };
                if name == RELEASE {
                    let built = release_done
                        .recv()
                        .unwrap_or_else(|_| Err(format!("{RELEASE}: the build did not finish")));
                    said(built.map(|b| format!("{name}: {}", state(b))));
                }
                let outcome = handle.join().expect("a build thread panicked");
                if let Some(built) = outcome.built {
                    said(built.map(|b| format!("{name}: {}", state(b))));
                }
                if let Some(line) = outcome.tracks {
                    said(line);
                }
            }
            failed.map_or(Ok(()), Err)
        })
    }

    /// Converts and assembles the cartridge in `dest`, without a stamp and
    /// even if it is up to date. `extra` are extra flags for the converter:
    /// that is how a copy of a cartridge is built with some other setting,
    /// without touching the real one.
    pub fn convert(
        &self,
        name: &str,
        dest: &Path,
        sfc: &Path,
        extra: &[String],
    ) -> Result<(), String> {
        let cartridge = self.cartridge(name)?;
        std::fs::create_dir_all(dest).map_err(|e| format!("{}: {e}", dest.display()))?;
        let log_file = dest.join("converter.log");
        // The converter's flags, as its binary takes them.
        let mut argv: Vec<String> = vec!["--project".into(), text(self.project.directory())];
        argv.extend(
            self.environment
                .as_flags(TO_CONVERTER)
                .iter()
                .map(|f| f.to_string_lossy().into_owned()),
        );
        argv.extend([
            "-o".into(),
            text(&dest.join("mapdata.inc")),
            "--msu".into(),
            text(&sfc.with_extension("msu")),
        ]);
        argv.extend(cartridge.flags.iter().cloned());
        argv.extend(extra.iter().cloned());
        // The cases go at the end: after a `--case`, any cartridge flag would
        // belong to that case, and the converter rejects it. By their whole
        // path: the converter ran standing in the suite's root and was given
        // them relative to it, and a call runs wherever this was run. They
        // are only printed in what the converter answers no with.
        for (k, case) in self.cases(name)?.iter().enumerate() {
            if k > 0 {
                argv.push("--case".into());
            }
            argv.extend(["--test-commands".into(), text(&self.case_path(case))]);
        }
        // What it says goes into its own log, not onto this one's stdout:
        // the cartridges convert at the same time, in threads. And a panic
        // stops this cartridge, not the build, as a converter process that
        // died did; it is said in its log, as the process said it on the
        // stderr that went there.
        log::panics_into_logs();
        let said = Log::new();
        let done = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            rm2k_snes_convert::convert(argv, &said)
        }));
        let failure = match done {
            Ok(Ok(())) => None,
            // As the binary said it: last, on its stderr.
            Ok(Err(stop)) => {
                said.during(|| rm2k_project::errln!("{}", stop.message));
                Some(format!("{name}: the converter failed; everything is in"))
            }
            Err(panic) => {
                let what = panic
                    .downcast_ref::<&str>()
                    .map(|s| s.to_string())
                    .or_else(|| panic.downcast_ref::<String>().cloned())
                    .unwrap_or_default();
                Some(format!(
                    "{name}: the converter panicked: {what}; everything is in"
                ))
            }
        };
        std::fs::write(&log_file, said.bytes())
            .map_err(|e| format!("{}: {e}", log_file.display()))?;
        if let Some(failure) = failure {
            let out = String::from_utf8_lossy(&said.out()).into_owned();
            let chars: Vec<char> = out.chars().collect();
            let tail: String = chars[chars.len().saturating_sub(3000)..].iter().collect();
            let mut stderr = std::io::stderr();
            let _ = stderr.write_all(tail.as_bytes());
            let _ = stderr.write_all(&said.err());
            return Err(format!("{failure} {}", log_file.display()));
        }
        // The assembler is called, not run: it is this crate's code. Until
        // 2026-11-23 it was a command of its own, `rm2k-snes-assemble`, and
        // the call stayed a process when it became `assemble`, a subcommand
        // of this same program. It gets what that subcommand made of its
        // flags, and says what it said: its lines on this one's stdout,
        // where `ca65` and `ld65` still write theirs.
        let cache_dir = self
            .environment
            .cache(&self.project)
            .map_err(|e| e.to_string())?;
        // The same cache the converter uses, for `ca65`'s objects; none with
        // `NO_CACHE=1`.
        let cache_dir = (!cache::disabled()).then(|| rm2k_project::absolute(&cache_dir));
        match assemble(
            &self.runtime.join("main.s"),
            dest,
            sfc,
            Some(&with_suffix(sfc, ".sym")),
            &self.root,
            cache_dir.as_deref(),
        ) {
            Ok(from_the_cache) => {
                if from_the_cache {
                    println!("ca65: the object came from the cache");
                }
                Ok(())
            }
            Err(failure) => {
                // `ca65` and `ld65` said why on their own stderr. A message
                // of the assembler's own is said now, as the process said
                // it, and not when the build thread is joined.
                if let Failure::Message(message) = failure {
                    eprintln!("{message}");
                }
                Err(format!("{name}: the assembler failed"))
            }
        }
    }

    /// The MSU-1 tracks next to the ROM that is played. They go outside the
    /// stamp and are checked even if the ROM is up to date: which ones they
    /// are is said by the cartridge, but how each one sounds depends on the
    /// MIDI, the soundfont and the synthesizer, and the tool that makes them
    /// already knows which ones are there. Returns the line that reports it,
    /// which is printed in its place; the tracks it makes are printed as
    /// they come.
    pub fn msu_tracks(&self) -> Result<String, String> {
        // A call of the music's library since 2026-11-25; until then
        // `rm2k-snes-audio msu`, run from the PATH, whose last line this
        // printed in its place. Its cache keys on what the tracks are made
        // from and with —see `tracks.rs`—, not on a binary.
        let failed = |e: String| format!("{RELEASE}: the MSU-1 tracks failed: {e}");
        let e = &self.environment;
        let game = Game {
            game_dir: e.game().map_err(|e| failed(e.to_string()))?.to_path_buf(),
            rtp_dir: e.rtp().ok().map(Path::to_path_buf),
            project: self.project.clone(),
        };
        let soundfont = e
            .soundfont()
            .map_err(|e| failed(e.to_string()))?
            .to_path_buf();
        let replacements = e.msu_replacements().map(Path::to_path_buf);
        let cache_dir = if cache::disabled() {
            None
        } else {
            Some(e.cache(&self.project).map_err(|e| failed(e.to_string()))?)
        };
        let tracks = Tracks::new(game, soundfont, GAIN, replacements, cache_dir);
        // The tracks it makes, as they come; not the ones already there.
        let (made, already) = tracks
            .build(&self.rom_of(RELEASE)?, false, &mut |line| {
                let mut stdout = std::io::stdout().lock();
                let _ = writeln!(stdout, "{line}");
                let _ = stdout.flush();
            })
            .map_err(|e| failed(e.to_string()))?;
        Ok(format!(
            "{RELEASE}: MSU-1 tracks, {made} made and {already} that were already there"
        ))
    }

    // --- What the tests read -------------------------------------------------

    /// Everything a game's test suite needs to know about its cartridges,
    /// as JSON: which ones there are, where each one is, what it carries and
    /// whether it is up to date.
    pub fn describe(&self) -> Result<Value, String> {
        let inputs = self.fingerprint()?;
        let mut cartridges = Vec::new();
        for c in &self.cartridges {
            let (cases, teleports) = self.manifest(&c.name)?;
            cartridges.push(json!({
                "name": c.name,
                "directory": self.directory(&c.name)?,
                "rom": self.rom_of(&c.name)?,
                "msu": self.msu_of(&c.name)?,
                "flags": c.flags,
                "all_cases": c.cases.is_none(),
                "cases": cases,
                "teleports": teleports,
                "without_title": self.without_title(&c.name)?,
                "stale": self.stale(&c.name, &inputs)?,
            }));
        }
        let all_cases = self.all_cases()?;
        let mut where_is = serde_json::Map::new();
        for case in &all_cases {
            where_is.insert(case.clone(), json!(self.where_is(case)?));
        }
        Ok(json!({
            "root": self.root,
            "runtime": self.runtime,
            "project": self.project.directory(),
            "cases_dir": self.cases_dir,
            "release": RELEASE,
            "rom_name": self.rom_name,
            "real_game": self.real_game,
            "debug_map_entry": self.debug_map_entry,
            "with_debug_map": self.with_debug_map,
            "debug_map": self.debug_map,
            "first_case": self.first_case(self.with_debug_map),
            "maps": {
                "below": self.maps_below,
                "excluded": self.excluded_maps,
                "added": self.added_maps,
                "game": self.game_maps,
                "test": self.test_maps,
                "all": self.all_maps(),
                "by_the_rule_alone": self.rule_maps(&[], &[]),
            },
            "release_cases": {
                "with_debug_map": self.cases_of(RELEASE, true)?,
                "without_debug_map": self.cases_of(RELEASE, false)?,
            },
            "all_cases": all_cases,
            "where_is": where_is,
            "fingerprint": inputs,
            "fingerprint_files": self.fingerprint_files(&self.runtime)?,
            "cartridges": cartridges,
        }))
    }
}

/// Every file below `directory`, at any depth, skipping hidden entries,
/// sorted as text.
fn files_below(directory: &Path) -> Result<Vec<PathBuf>, String> {
    let mut out = Vec::new();
    let mut pending = vec![directory.to_path_buf()];
    while let Some(dir) = pending.pop() {
        for name in entries(&dir)? {
            let path = dir.join(name);
            if path.is_dir() {
                pending.push(path);
            } else if path.is_file() {
                out.push(path);
            }
        }
    }
    sort_as_text(&mut out);
    Ok(out)
}

/// Sorted as the text of the path, not component by component: the same
/// order a listing prints.
fn sort_as_text(paths: &mut [PathBuf]) {
    paths.sort_by(|a, b| a.as_os_str().cmp(b.as_os_str()));
}

/// A path as the converter's flags take it.
fn text(path: &Path) -> String {
    path.to_string_lossy().into_owned()
}

fn with_suffix(path: &Path, suffix: &str) -> PathBuf {
    let mut s = path.as_os_str().to_os_string();
    s.push(suffix);
    PathBuf::from(s)
}
