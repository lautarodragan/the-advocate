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

/// A map, as the conversion left it: what `wally` answered, the
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
    /// The objects, as `wally` answered them.
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
    /// The `ShowPicture` pictures the map carries in its sprite bank, if
    /// any: see [`MapPictures`].
    #[serde(default)]
    pub pictures: Option<MapPictures>,
}

/// A map's `ShowPicture` pictures: the first tile of its sprite bank they
/// start at, and each picture, in the order the bytecode numbers them.
#[derive(Deserialize)]
pub struct MapPictures {
    pub base: i64,
    pub images: Vec<PictureImage>,
}

/// One picture: half its size in RM2k's pixels —the console computes its
/// corner from its centre with it—, the first of its 32x32 objects among the
/// map's pictures' ones, each object's place from the picture's corner, and
/// its fifteen colours.
#[derive(Deserialize)]
pub struct PictureImage {
    pub half: [i64; 2],
    pub first: i64,
    pub objects: Vec<[i64; 2]>,
    pub palette: Vec<Color>,
}

/// `emit`: everything the cartridge carries, from every domain.
#[derive(Deserialize)]
pub struct Emit {
    /// The maps, in the order of the cartridge's table: see [`Map`].
    pub maps: Vec<Map>,
    /// The map the cartridge boots in, by its index.
    pub start: i64,
    /// Whether the hero goes above the upper layer, which only a test asks
    /// for; whether L and R change its speed; whether the battle draws the
    /// enemies' HP.
    pub hero_above: bool,
    pub speed_keys: bool,
    pub enemy_hp: bool,
    /// The party the game starts with.
    pub party: Vec<i64>,
    /// Who the cartridge is: its header title and its SRAM signature.
    pub rom: Rom,
    /// What `rm2k-snes-screens convert` answered, as it is: the message
    /// window and its font, the title's menu, the slots and the pause
    /// menu, the text screens with their windows, End Game, the texts they
    /// compose, and the geometry they were drawn with.
    pub screens: serde_json::Value,
    /// The text block of every `ShowMessage`, as the event compiler left it.
    #[serde(deserialize_with = "hex::bytes")]
    pub messages: Vec<u8>,
    /// The pair table its letters are written with: see `Pairs` in the
    /// event compiler's `messages.rs`.
    pub message_pairs: MessagePairs,
    /// The title's picture and the Game Over's, each one stream.
    pub title: Option<FullScreen>,
    pub game_over: Option<FullScreen>,
    /// The battle animations the compiled pages show.
    pub animations: Animations,
    /// The troops some battle of the cartridge asks for, in its order.
    pub troops: Vec<i64>,
    /// The battle's songs and sounds, as the compiler numbered them.
    pub battle_audio: Option<serde_json::Value>,
    /// The battle scene: the backdrops and the battlers, already as bytes.
    pub scene: serde_json::Value,
    /// What `rm2k-snes-battle tables` wrote —the experience's and the
    /// encounters' pieces— and its experience slots.
    pub battle_tables: BattleTables,
    /// The troops' event pages, as the compiler answered them, if any.
    pub troop_pages: Option<serde_json::Value>,
    /// The common events the menu runs on closing: `[switch, number,
    /// code]`.
    pub party_common: Vec<(i64, i64, String)>,
    /// The shared common event bodies —the automatic ones and what they
    /// call—, as the compiler answered them, if any.
    #[serde(default)]
    pub commons: Option<Commons>,
    /// What `rm2k-snes-battle model` answered.
    pub battle_model: serde_json::Value,
    /// The compiler's indices: each variable's slot, and each (actor,
    /// skill) pair's bit.
    pub variables: Vec<(i64, i64)>,
    pub skill_pairs: Vec<(i64, i64, i64)>,
    /// The items and actors the cartridge knows.
    pub items: Vec<i64>,
    pub actors: Vec<i64>,
    /// Dead texts after the items', for a test.
    pub text_padding: usize,
    /// Where the harness writes the case number, if there is more than one.
    pub case_slot: Option<i64>,
    /// The big pictures, each as a background layer: see [`BigLayer`].
    #[serde(default)]
    pub big_pictures: Vec<BigLayer>,
}

/// A `ShowPicture` picture too big for the sprites, as `rm2k-snes-images
/// background` drew it: where its canvas starts from the top of the screen,
/// its rows of 32 cells, its 4bpp tiles, a tilemap entry per cell and its
/// palettes, sixteen colours each from the first background palette above
/// the window's.
#[derive(Deserialize)]
pub struct BigLayer {
    pub top: i64,
    /// Where it was drawn: its centre on RM2k's screen, and half its size
    /// in RM2k's pixels at its zoom. A `MovePicture` scrolls it from there.
    pub center: [i64; 2],
    pub half: [i64; 2],
    /// Whether the picture goes past the screen's sides: then a wave shows
    /// its edges mirrored, and if not, black, as RM2k shows what is beyond
    /// it.
    #[serde(default)]
    pub wider: bool,
    pub rows: usize,
    #[serde(deserialize_with = "hex::bytes")]
    pub tiles: Vec<u8>,
    pub tilemap: Vec<u16>,
    pub palettes: Vec<Vec<Color>>,
}

/// The shared common event bodies: see `commons.rs` in the event compiler.
#[derive(Deserialize)]
pub struct Commons {
    /// Each body's common event number and its bytecode, by index.
    pub bodies: Vec<(i64, String)>,
    /// The automatic ones: the switch and the body's index.
    pub autostart: Vec<(i64, i64)>,
    /// The deepest chain of calls, or None if they loop.
    pub depth: Option<i64>,
}

#[derive(Deserialize)]
pub struct Rom {
    pub title: String,
    pub sram_signature: String,
}

/// The text block's pair table: the first byte value that stands for a
/// pair, and two bytes per pair from there up.
#[derive(Deserialize)]
pub struct MessagePairs {
    pub first: i64,
    #[serde(deserialize_with = "hex::bytes")]
    pub table: Vec<u8>,
}

/// A picture that fills the screen, as one LZ2 stream with its tiles,
/// tilemap and colours.
#[derive(Deserialize)]
pub struct FullScreen {
    pub tiles: i64,
    pub colors: i64,
    pub first_color: i64,
    #[serde(deserialize_with = "hex::bytes")]
    pub stream: Vec<u8>,
}

/// The battle animations, and the box they are drawn in.
#[derive(Deserialize)]
pub struct Animations {
    /// The box's side, an object's, how many objects and tiles it takes,
    /// and the console's screen.
    #[serde(rename = "box")]
    pub side: i64,
    pub obj: i64,
    pub objects: i64,
    pub tiles: i64,
    pub screen: [i64; 2],
    pub list: Vec<BattleAnimation>,
}

/// One battle animation: its frames as they end up in VRAM, its anchor as
/// the console's table carries it, and its colours.
#[derive(Deserialize)]
pub struct BattleAnimation {
    pub number: i64,
    #[serde(deserialize_with = "drawings")]
    pub frames: Vec<Vec<u8>>,
    pub anchor: [i64; 2],
    pub palette: Vec<Color>,
}

#[derive(Deserialize)]
pub struct BattleTables {
    pub experience: String,
    pub encounters: String,
    pub slots: serde_json::Value,
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
    Shared {
        shared: i64,
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
    /// Which entries of its palette the digits take, one bit each, as
    /// `wally` answered it: 0 without a timer.
    #[serde(default)]
    pub timer_mask: i64,
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
    /// The slots still events take turns in, if the map needed them: see
    /// `share` in `rm2k-snes-map-sprites`.
    #[serde(default)]
    pub shared: Option<Shared>,
}

/// The slots still events take turns in, as `wally` answered them.
#[derive(Deserialize)]
pub struct Shared {
    /// `[event, slot, pose, palette]`: the pose is an index into `poses`.
    pub events: Vec<(i64, usize, usize, u32)>,
    /// `[entry in the pose table, pose]`.
    pub poses: Vec<(usize, usize)>,
    /// Each slot's block in the sprite bank.
    pub slots: Vec<u32>,
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
    /// What it draws, for an event that changes graphic: see [`Draws`].
    /// The emission writes it as the console's OAM wants it
    /// ([`crate::objects::page_oam`]).
    pub draws: Option<Draws>,
    /// The variable condition: slot, comparison and against what.
    pub variable: Option<(i64, i64, i64)>,
    /// Its graphic, `[CharSet, index, pose]`, and whether it turns toward
    /// the hero.
    pub graphic: Option<(String, i64, i64)>,
    pub turns: bool,
}

/// What a page of an event that changes graphic draws, as the map's
/// conversion placed it.
#[derive(Deserialize)]
pub struct Draws {
    /// The 32x32 block of the sprite bank its poses start at, and its
    /// palette; no block for an event that only appears, whose own row
    /// already points at its poses.
    pub block: Option<u32>,
    #[serde(default)]
    pub palette: u32,
    /// The pose it shows, and the passage its tile imposes on its cell.
    pub pose: u32,
    pub tile_pass: Option<u32>,
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
