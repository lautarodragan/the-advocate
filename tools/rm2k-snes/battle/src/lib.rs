//! An RPG Maker 2000 game's battle, as the tables a Super Nintendo
//! cartridge carries: for now, experience and level per actor, and each
//! map's random encounters.
//!
//! It reads the game from a Ditto dump —see [`game`]— and what the
//! cartridge decided —which actors fight, which maps it carries— from a
//! [`Request`]. What comes out is two pieces of a ca65 `.inc`, which the
//! caller puts where they go, and a [`Tables`] with what the rest of the
//! conversion needs to know about them.

pub mod asm;
pub mod encounters;
pub mod experience;
pub mod fail;
pub mod game;

pub use encounters::{Encounters, Map};
pub use fail::{Bad, Result};
pub use game::Game;

use serde_json::{json, Value};
use std::path::Path;

/// The file the experience tables are written to.
pub const EXPERIENCE_FILE: &str = "experience.inc";
/// The file the encounter tables are written to.
pub const ENCOUNTERS_FILE: &str = "encounters.inc";
/// The file what the caller needs to know is written to.
pub const ANSWER_FILE: &str = "battle.json";

/// What the cartridge decided, which the game's dump does not say.
#[derive(Debug, Clone, Default)]
pub struct Request {
    /// The actors that can fight, by RM2k number: they are the ones that
    /// get an experience slot. See [`experience::slots`].
    pub party: Vec<i64>,
    /// The cartridge's maps, in its order, with their size in cells.
    pub maps: Vec<Map>,
    /// If given, every map's `encounter_steps`: see [`Encounters::of`].
    pub encounter_steps: Option<i64>,
}

impl Request {
    /// A request file:
    ///
    /// ```json
    /// {"party": [1, 3],
    ///  "maps": [{"id": 4, "width": 40, "height": 30}],
    ///  "encounter_steps": null,
    ///  "tree_nodes": []}
    /// ```
    ///
    /// `tree_nodes` are nodes of the map tree in the dump's shape, which go
    /// over the dump's: it is how a project that adds maps the game does not
    /// have gives them their encounters. They go into `game`.
    pub fn read(path: &Path, game: &mut Game) -> Result<Request> {
        let data = game::read_json(path)?;
        let whose = path.display().to_string();
        let ids = |name: &str| -> Result<Vec<i64>> {
            game::list(&data, name, &whose)?
                .iter()
                .map(|v| {
                    v.as_i64()
                        .ok_or_else(|| Bad::answer(format!("{whose}: `{name}` has {v}")))
                })
                .collect()
        };
        let party = ids("party")?;
        let mut maps = Vec::new();
        for m in game::list(&data, "maps", &whose)? {
            let whose = format!("{whose}: a map");
            maps.push(Map {
                id: game::number(m, "id", &whose)?,
                width: game::number(m, "width", &whose)?,
                height: game::number(m, "height", &whose)?,
            });
        }
        let steps = game::field(&data, "encounter_steps", &whose)?;
        let encounter_steps = if steps.is_null() {
            None
        } else {
            Some(steps.as_i64().ok_or_else(|| {
                Bad::answer(format!("{whose}: `encounter_steps` is not a whole number"))
            })?)
        };
        for node in game::list(&data, "tree_nodes", &whose)? {
            game.add_node(node, &format!("{whose}: tree_nodes"))?;
        }
        Ok(Request {
            party,
            maps,
            encounter_steps,
        })
    }
}

/// Everything this makes for a cartridge.
#[derive(Debug, Clone)]
pub struct Tables {
    pub experience: String,
    /// The experience slots, see [`experience::slots`]: what the save of
    /// each slot belongs to, which a save signature has to cover.
    pub slots: Vec<Option<i64>>,
    pub encounters: Encounters,
}

impl Tables {
    pub fn new(game: &Game, request: &Request) -> Result<Tables> {
        Ok(Tables {
            experience: experience::tables(game, &request.party)?,
            slots: experience::slots(game, &request.party),
            encounters: Encounters::of(game, &request.maps, request.encounter_steps)?,
        })
    }

    /// What the caller needs besides the `.inc`: the slots, and per map its
    /// encounter record; how many records and zones; and the troops, which
    /// the cartridge has to carry.
    pub fn answer(&self) -> Value {
        let e = &self.encounters;
        json!({
            "experience": {"slots": self.slots},
            "encounters": {
                "per_map": e.per_map,
                "records": e.bases.len(),
                "zones": e.zones.len(),
                "troops": e.troops,
            },
        })
    }

    /// Writes [`EXPERIENCE_FILE`], [`ENCOUNTERS_FILE`] and [`ANSWER_FILE`]
    /// into `dir`, which is created if it is not there.
    pub fn write(&self, dir: &Path) -> Result<()> {
        let io = |path: &Path, e: std::io::Error| Bad::usage(format!("{}: {e}", path.display()));
        std::fs::create_dir_all(dir).map_err(|e| io(dir, e))?;
        let answer = serde_json::to_string_pretty(&self.answer()).unwrap() + "\n";
        for (name, text) in [
            (EXPERIENCE_FILE, &self.experience),
            (ENCOUNTERS_FILE, &self.encounters.tables()),
            (ANSWER_FILE, &answer),
        ] {
            let path = dir.join(name);
            std::fs::write(&path, text).map_err(|e| io(&path, e))?;
        }
        Ok(())
    }
}
