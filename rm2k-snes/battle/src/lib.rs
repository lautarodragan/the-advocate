//! An RPG Maker 2000 game's battle, as a Super Nintendo cartridge carries
//! it: experience and level per actor, and each map's random encounters,
//! as tables; the battle's model —which skills, actions and items it
//! offers, what a troop gives— and its text screen, as data the rest of
//! the conversion writes; and the battle itself, played turn by turn with
//! the console's randomness, for whoever compares a console against it.
//!
//! It reads the game from a Ditto dump —see [`game`] and [`db`]— and what
//! the cartridge decided from a request. The tables come out as two pieces
//! of a ca65 `.inc`, which the caller puts where they go, and a [`Tables`]
//! with what the rest of the conversion needs to know about them; the rest,
//! as JSON: see [`model`].

pub mod asm;
pub mod attributes;
pub mod db;
pub mod encounters;
pub mod experience;
pub mod fail;
pub mod field;
pub mod fit;
pub mod game;
pub mod model;
pub mod rules;
pub mod screen;
pub mod simulate;
pub mod stage;
pub mod states;

pub use encounters::{Encounters, Map};
pub use fail::{Bad, Result};
pub use game::Game;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::path::Path;

/// The file the experience tables are written to.
pub const EXPERIENCE_FILE: &str = "experience.inc";
/// The file the encounter tables are written to.
pub const ENCOUNTERS_FILE: &str = "encounters.inc";
/// The file what the caller needs to know is written to.
pub const ANSWER_FILE: &str = "battle.json";

/// What the cartridge decided, which the game's dump does not say:
///
/// ```json
/// {"party": [1, 3],
///  "maps": [{"id": 4, "width": 40, "height": 30}],
///  "encounter_steps": null,
///  "tree_nodes": []}
/// ```
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Request {
    /// The actors that can fight, by RM2k number: they are the ones that
    /// get an experience slot. See [`experience::slots`].
    pub party: Vec<i64>,
    /// The cartridge's maps, in its order, with their size in cells.
    pub maps: Vec<Map>,
    /// If given, every map's `encounter_steps`: see [`Encounters::of`].
    pub encounter_steps: Option<i64>,
    /// Nodes of the map tree in the dump's shape, which go over the dump's:
    /// it is how a project that adds maps the game does not have gives them
    /// their encounters. [`Request::of`] puts them into the game.
    pub tree_nodes: Vec<Value>,
}

impl Request {
    /// A request file: see [`Request::of`].
    pub fn read(path: &Path, game: &mut Game) -> Result<Request> {
        let text = std::fs::read_to_string(path)
            .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
        let whose = path.display().to_string();
        let data: Value =
            serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{whose}: {e}")))?;
        Request::of(&data, &whose, game)
    }

    /// A request already parsed, with its tree's nodes put into `game`;
    /// `whose` is what its complaints start with.
    pub fn of(data: &Value, whose: &str, game: &mut Game) -> Result<Request> {
        let request =
            Request::deserialize(data).map_err(|e| Bad::answer(format!("{whose}: {e}")))?;
        request.put_nodes(whose, game)?;
        Ok(request)
    }

    /// Its tree's nodes, into `game`.
    pub fn put_nodes(&self, whose: &str, game: &mut Game) -> Result<()> {
        // Nodes of the tree in the dump's shape: Ditto's type reads them.
        for node in &self.tree_nodes {
            let node = ditto::schema::MapInfo::deserialize(node)
                .map_err(|e| Bad::answer(format!("{whose}: tree_nodes: {e}")))?;
            game.add_node(node);
        }
        Ok(())
    }
}

/// What `tables` answers besides the `.inc`, in [`ANSWER_FILE`]: the
/// experience slots, and the encounters' counts.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Answer {
    pub experience: ExperienceAnswer,
    pub encounters: EncountersAnswer,
}

/// The experience slots, see [`experience::slots`]: what the save of each
/// slot belongs to, which a save signature has to cover.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExperienceAnswer {
    pub slots: Vec<Option<i64>>,
}

/// Per map its encounter record, or `encounters::NONE`; how many records
/// and zones; and the troops, which the cartridge has to carry.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct EncountersAnswer {
    pub per_map: Vec<i64>,
    pub records: usize,
    pub zones: usize,
    pub troops: Vec<i64>,
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

    /// What the caller needs besides the `.inc`: see [`Answer`].
    pub fn answer(&self) -> Answer {
        let e = &self.encounters;
        Answer {
            experience: ExperienceAnswer {
                slots: self.slots.clone(),
            },
            encounters: EncountersAnswer {
                per_map: e.per_map.clone(),
                records: e.bases.len(),
                zones: e.zones.len(),
                troops: e.troops.clone(),
            },
        }
    }

    /// [`EXPERIENCE_FILE`], [`ENCOUNTERS_FILE`] and [`ANSWER_FILE`], by
    /// name.
    pub fn files(&self) -> stage::Files {
        let answer = serde_json::to_string_pretty(&self.answer()).unwrap() + "\n";
        stage::Files::from([
            (
                EXPERIENCE_FILE.to_string(),
                self.experience.clone().into_bytes(),
            ),
            (
                ENCOUNTERS_FILE.to_string(),
                self.encounters.tables().into_bytes(),
            ),
            (ANSWER_FILE.to_string(), answer.into_bytes()),
        ])
    }
}
