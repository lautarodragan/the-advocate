//! What the emission gets: what each domain of the conversion answered, as
//! data. Bytes travel as hex.

use crate::fail::{Bad, Result};
use crate::hex;
use crate::snes::Color;
use serde::de::DeserializeOwned;
use serde::Deserialize;
use std::path::Path;

/// A request file, read into `T`.
pub fn read<T: DeserializeOwned>(path: &Path) -> Result<T> {
    let whose = path.display();
    let text = std::fs::read_to_string(path).map_err(|e| Bad::usage(format!("{whose}: {e}")))?;
    serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{whose}: {e}")))
}

/// `maps`: the cartridge's maps, in the order of its table.
#[derive(Deserialize)]
pub struct Maps {
    pub maps: Vec<Map>,
}

/// A map, as the conversion left it: what `rm2k-snes-maps` answered, the
/// pages the event compiler compiled, and what the cartridge decided.
#[derive(Deserialize)]
pub struct Map {
    /// Its RM2k number, and its name in the map tree.
    pub id: i64,
    pub name: String,
    /// The background's tilemap, in 8x8 cells: `[width, height]`.
    pub tilemap: [i64; 2],
    /// The map, in RM2k's 16x16 cells.
    pub size: [i64; 2],
    /// Where the hero starts, in cells.
    pub start: [i64; 2],
    /// The VRAM layout it got, by name: see [`crate::vram::LAYOUTS`].
    pub layout: String,
    /// The background: its 8bpp tiles and its CGRAM words.
    #[serde(deserialize_with = "hex::bytes")]
    pub tiles: Vec<u8>,
    #[serde(deserialize_with = "hex::bytes")]
    pub cgram: Vec<u8>,
    /// The upper layer: its 4bpp tiles, its CGRAM words, and the palette it
    /// starts at.
    #[serde(deserialize_with = "hex::bytes")]
    pub above_tiles: Vec<u8>,
    #[serde(deserialize_with = "hex::bytes")]
    pub above_cgram: Vec<u8>,
    pub above_first: i64,
    /// The ChipSet's animation: each family's run, with its drawings.
    pub runs: Vec<Run>,
    /// The map in 16x16 blocks: one block per cell, the table, and each
    /// block's passability and terrain; and the terrain outside the map.
    #[serde(deserialize_with = "hex::bytes")]
    pub cells: Vec<u8>,
    #[serde(deserialize_with = "hex::bytes")]
    pub blocks: Vec<u8>,
    #[serde(deserialize_with = "hex::bytes")]
    pub block_pass: Vec<u8>,
    #[serde(deserialize_with = "hex::bytes")]
    pub block_terrain: Vec<u8>,
    pub terrain_outside: i64,
    /// The objects, as `rm2k-snes-maps` answered them.
    pub sprite: Option<Sprite>,
    /// The events that are drawn, and who among them walks and who
    /// animates standing still.
    pub npcs: Vec<Npc>,
    pub movable: Vec<i64>,
    pub animates_still: Vec<i64>,
    /// Every event's starting cell, in the map's order, drawn or not.
    pub events: Vec<[i64; 2]>,
    /// The event pages, and their code and own routes in one block.
    pub pages: Vec<Page>,
    #[serde(deserialize_with = "hex::bytes")]
    pub evcode: Vec<u8>,
    /// The events whose graphic follows the page, those that only appear
    /// and disappear with it, and those that turn toward the hero.
    pub changing: Vec<i64>,
    pub appearing: Vec<i64>,
    pub turning: Vec<i64>,
}

/// A family's run of the ChipSet's animation.
#[derive(Deserialize)]
pub struct Run {
    /// `water` or `animated`.
    pub family: String,
    /// The tile of the background's bank it starts at, and how many.
    pub base: i64,
    pub tiles: i64,
    /// Each drawing's tiles.
    #[serde(deserialize_with = "drawings")]
    pub drawings: Vec<Vec<u8>>,
}

fn drawings<'de, D: serde::Deserializer<'de>>(d: D) -> std::result::Result<Vec<Vec<u8>>, D::Error> {
    let texts: Vec<String> = Deserialize::deserialize(d)?;
    texts
        .iter()
        .map(|t| hex::decode(t).map_err(|bad| serde::de::Error::custom(bad.message())))
        .collect()
}

/// A slot of the sprite bank, by what it holds.
#[derive(Deserialize, Clone, Debug, PartialEq, Eq)]
#[serde(untagged)]
pub enum Slot {
    Hero {
        hero: bool,
    },
    Turn {
        turn: bool,
    },
    Event {
        event: i64,
    },
    Still {
        charset: String,
        index: i64,
        pose: i64,
    },
}

/// The objects of a map.
#[derive(Deserialize)]
pub struct Sprite {
    #[serde(deserialize_with = "hex::bytes")]
    pub tiles: Vec<u8>,
    /// The palettes, fifteen colours at most each.
    pub palettes: Vec<Vec<Color>>,
    /// Where each slot ended up: `[slot, block, palette]`.
    pub place: Vec<(Slot, u32, u32)>,
    /// The leader candidates: `[actor, palette, its entry in the pose
    /// table or null, its colours as CGRAM words]`.
    pub actors: Vec<(i64, i64, Option<usize>, Vec<u32>)>,
    /// The timer's digits, `[first tile, palette]`, if this map carries
    /// them; the palette may be missing.
    pub timer: Option<(i64, Option<i64>)>,
    /// The characters that change pose, `[CharSet, index]`, in the order of
    /// the pose table.
    pub animated: Vec<(String, i64)>,
    /// Each one's twelve poses, as this map quantized them.
    pub banks: Vec<(String, i64, String)>,
    /// The graphics command 34 changes to: `[pose table entry or $FF,
    /// palette]`.
    pub route_gfx: Vec<(i64, i64)>,
    /// The raindrops, the turn slot's block, the `ShowPicture` picture and
    /// the battle animation's box: `[first tile, palette]`, 0 if none.
    pub rain: (i64, i64),
    pub turn_block: Option<u32>,
    pub image: (i64, i64),
    pub animation: Option<Animation>,
}

/// Where the battle animation's box landed.
#[derive(Deserialize)]
pub struct Animation {
    pub base: i64,
    pub palette: i64,
}

/// An event that is drawn.
#[derive(Deserialize)]
pub struct Npc {
    pub event: i64,
    /// Its cell.
    pub x: i64,
    pub y: i64,
    pub charset: String,
    pub index: i64,
    pub pose: i64,
    pub layer: i64,
    pub speed: i64,
    pub visible: bool,
    /// The passage bits its tile imposes on its cell, if it is drawn with
    /// one.
    pub tile_pass: Option<i64>,
}

/// An event page, compiled.
#[derive(Deserialize, Default)]
#[serde(default)]
pub struct Page {
    pub event: i64,
    pub page: i64,
    pub trigger: i64,
    pub switch_a: i64,
    pub switch_b: i64,
    pub actor: i64,
    pub layer: i64,
    pub item: i64,
    /// Whether it has code to run, and where it starts in the map's block.
    pub has_code: bool,
    pub offset: usize,
    /// Its own route's commands, after its code.
    pub route_offset: usize,
    pub frequency: i64,
    pub speed: i64,
    pub fixed_direction: bool,
    pub own_route: Option<OwnRoute>,
    /// What it draws, as the console's OAM wants it: tile, attributes,
    /// pose and passage.
    pub oam: Option<[u8; 4]>,
    /// The variable condition: slot, comparison and against what.
    pub variable: Option<(i64, i64, i64)>,
    /// Its graphic, `[CharSet, index, pose]`, and whether it turns toward
    /// the hero.
    pub graphic: Option<(String, i64, i64)>,
    pub turns: bool,
}

/// The route a page walks by itself.
#[derive(Deserialize)]
pub struct OwnRoute {
    pub repeats: bool,
    pub skippable: bool,
    pub fixed_direction: bool,
    pub animation_continues: bool,
    pub frequency: i64,
    pub speed: i64,
    /// How many commands it has.
    pub orders: usize,
}
