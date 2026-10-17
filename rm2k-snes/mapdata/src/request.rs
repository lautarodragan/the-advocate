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
    /// The background: its tiles and its CGRAM words. 8bpp, or 4bpp in a
    /// map whose panorama goes in mode 1: `bpp` says.
    #[serde(deserialize_with = "hex::bytes")]
    pub tiles: Vec<u8>,
    #[serde(default = "eight")]
    pub bpp: usize,
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
    /// The still ones that animate in another one's slot, as `[event,
    /// whose]`: drawn with that slot, which the other keeps up to date.
    /// Missing, none.
    #[serde(default)]
    pub animates_with: Vec<[i64; 2]>,
    /// Every event's starting cell, in the map's order, drawn or not.
    pub events: Vec<[i64; 2]>,
    /// The cells of the events that share another's row, as `[x, y, the
    /// index of that event]`: the converter's twins, in a map with more
    /// events than the RAM holds. Missing, none.
    #[serde(default)]
    pub twins: Vec<[i64; 3]>,
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
    /// The panorama, if the cartridge shows it: see [`Panorama`].
    #[serde(default)]
    pub panorama: Option<Panorama>,
    /// What the map forbids once the tree's "the parent's" are resolved,
    /// as the bits of the ROM's `FAR_ACCESS`: see `map_access_enter` in
    /// runtime/enter_map.s. Missing, nothing.
    #[serde(default)]
    pub access: u8,
}

fn eight() -> usize {
    8
}

/// A map's panorama as `wally` converted it: the mode it goes in, the
/// whole picture's size and the stretch the cartridge carries, how it
/// moves —RM2k's loop flags and auto-scroll speeds—, its tiles, a tilemap
/// entry per cell of the stretch with the tile numbers from 0, and in mode
/// 1 the colour of the screen's backdrop. Its palettes are not here: in
/// mode 3 they travel as the upper layer's, in mode 1 inside the
/// background's.
#[derive(Deserialize)]
pub struct Panorama {
    pub name: String,
    pub mode: u8,
    pub size: [i64; 2],
    pub stretch: [i64; 2],
    #[serde(rename = "loop")]
    pub looped: [bool; 2],
    pub auto: [i64; 2],
    #[serde(deserialize_with = "hex::bytes")]
    pub tiles: Vec<u8>,
    pub tilemap: Vec<Vec<u16>>,
    pub backdrop: Option<u16>,
    /// Whether its map raised what it draws above the hero to BG1's
    /// priority 1: a flattened map, see `Way` in Wally.
    #[serde(default)]
    pub above_bg1: bool,
}

/// A map's `ShowPicture` pictures: the first tile of its sprite bank they
/// start at, and each picture, in the order the bytecode numbers them.
#[derive(Deserialize)]
pub struct MapPictures {
    pub base: i64,
    pub images: Vec<PictureImage>,
}

/// One picture: half its size in RM2k's pixels —the console computes its
/// corner from its centre with it—, its objects —each one's place from the
/// picture's corner and its tile word: see `picture_tables`—, the colours
/// of the palette it shares and which palette that is, from the top.
#[derive(Deserialize)]
pub struct PictureImage {
    pub half: [i64; 2],
    pub objects: Vec<[i64; 3]>,
    pub palette: Vec<Color>,
    #[serde(default)]
    pub palette_index: i64,
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
    /// The colour-memory entries the message window takes, as
    /// `rm2k-snes-screens window` counted them from the System: each map's
    /// background starts after them. See [`crate::cgram::cgram_reserved`].
    pub window_colors: u32,
    /// The message window of every other System the cartridge switches to,
    /// in its order, as `rm2k-snes-screens window` answered each in its
    /// `systems`: `{"system": name, "window": ...}`. Empty in a cartridge
    /// that does not switch.
    #[serde(default)]
    pub window_systems: Vec<serde_json::Value>,
    /// The text block of every `ShowMessage`, as the event compiler left it.
    #[serde(deserialize_with = "hex::bytes")]
    pub messages: Vec<u8>,
    /// The pair table its letters are written with: see `Pairs` in the
    /// event compiler's `messages.rs`.
    pub message_pairs: MessagePairs,
    /// The faces the message window shows, in the order `OP_FACE` counts
    /// them: as `rm2k-snes-screens faces` drew each, with a face the
    /// converter could not draw already replaced by what it shows instead.
    /// Absent in a request from before 2026-10-15: none.
    #[serde(default)]
    pub faces: Vec<MessageFace>,
    /// The title's picture and the Game Over's, each one stream.
    pub title: Option<FullScreen>,
    pub game_over: Option<FullScreen>,
    /// And the one that says the MSU-1 is missing, in a cartridge that
    /// needs it: see `msu_required` in the runtime's `msu1.s`.
    #[serde(default)]
    pub msu_missing: Option<FullScreen>,
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
    /// The parallel common events that compile: `[switch, number, pure,
    /// code]`, with switch 0 for one that runs always and `pure` for one
    /// that only runs when what it reads changes —see `commons::pure` in the
    /// event compiler and `compar_tick` in the runtime's `common_events.s`—.
    #[serde(default)]
    pub parallel_common: Vec<(i64, i64, bool, String)>,
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
    /// Every name a `ChangeHeroName` gives, as (actor, name), in the order
    /// `OP_CHANGE_NAME` counts them from one: see `renames` in the event
    /// compiler's indices and the runtime's `actor_names.s`.
    #[serde(default)]
    pub names: Vec<(i64, String)>,
    /// The highest switch the game names, which the ROM's table holds:
    /// `SWITCH_BYTES` is this over eight plus one. See `switch_top` in
    /// the event compiler.
    pub switch_top: i64,
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
    /// Its mode 7 texture, for a `MovePicture` that zooms it: see
    /// [`Mode7Texture`].
    #[serde(default)]
    pub mode7: Option<Mode7Texture>,
}

/// A big picture as a mode 7 texture, as `rm2k-snes-images background`
/// drew it: its tiles, a byte a pixel and the first one blank, a tile per
/// cell of the layer, and the point of the screen a zoom shrinks it
/// towards.
#[derive(Deserialize)]
pub struct Mode7Texture {
    #[serde(deserialize_with = "hex::bytes")]
    pub tiles: Vec<u8>,
    pub map: Vec<u8>,
    pub center: [i64; 2],
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
    /// The automatic ones copied into maps, which do not start from here on
    /// those maps: see [`Copies`]. Missing in a cartridge without copies.
    #[serde(default)]
    pub copies: Copies,
}

/// The automatic common events the converter copies into the maps as pages
/// of their event 0, by number, and the maps that carry the copies, by
/// index: see `common_pages.rs` in rm2k-snes-convert and `switch_of` in the
/// runtime's `common_events.s`.
#[derive(Deserialize, Default)]
pub struct Copies {
    pub commons: Vec<i64>,
    pub maps: Vec<i64>,
}

#[derive(Deserialize)]
pub struct Rom {
    pub title: String,
    pub sram_signature: String,
    /// Whether the cartridge needs the MSU-1: see [`MsuData`].
    #[serde(default)]
    pub msu: MsuData,
}

/// What the `.msu` may carry that the ROM cannot do without. Which pieces
/// go is decided by `pack_with_msu`, in `rm2k-snes-cartridge`: this only
/// marks the ones that may, and says whether they may.
#[derive(Deserialize, Default, Clone, Copy, PartialEq, Eq, Debug)]
#[serde(rename_all = "lowercase")]
pub enum MsuData {
    /// Nothing: without MSU-1 the game is the same. What every game is
    /// while its ROM reaches.
    #[default]
    Optional,
    /// What does not fit in the ROM, and the ROM refuses to start without
    /// the MSU-1 and its `.msu`.
    Required,
    /// Everything that may go, even if it fitted: for the tests, so that a
    /// game that fits runs the path.
    Everything,
}

/// The text block's pair table: the first byte value that stands for a
/// pair, and two bytes per pair from there up.
#[derive(Deserialize)]
pub struct MessagePairs {
    pub first: i64,
    #[serde(deserialize_with = "hex::bytes")]
    pub table: Vec<u8>,
}

/// A face of the message window: its 36 4bpp tiles, row by row, and the
/// fifteen colour words of its palette, entries 1 to 15. See `faces.rs` in
/// `rm2k-snes-screens`, which draws them, and `message_face.s` in the
/// runtime, which reads them.
#[derive(Deserialize)]
pub struct MessageFace {
    #[serde(deserialize_with = "hex::bytes")]
    pub tiles: Vec<u8>,
    pub palette: Vec<u16>,
}

/// A picture that fills the screen, as one LZ2 stream with its tiles,
/// tilemap and colours.
#[derive(Deserialize)]
pub struct FullScreen {
    pub tiles: i64,
    pub colors: i64,
    pub first_color: i64,
    /// Bits per pixel of its tiles: 8, or 4 for a title that does not fit
    /// at 8, which goes on BG1 in mode 1.
    #[serde(default = "eight_bits")]
    pub bpp: i64,
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

/// A graphic of command 34: see [`Sprite::route_gfx`].
#[derive(Deserialize, Clone, Debug, PartialEq, Eq)]
#[serde(untagged)]
pub enum RouteGfx {
    Colored(i64, i64, Vec<u32>),
    Plain(i64, i64),
}

impl RouteGfx {
    /// Its entry in the pose table, or $FF.
    pub fn entry(&self) -> i64 {
        match self {
            RouteGfx::Colored(k, ..) | RouteGfx::Plain(k, _) => *k,
        }
    }

    pub fn palette(&self) -> i64 {
        match self {
            RouteGfx::Colored(_, p, _) | RouteGfx::Plain(_, p) => *p,
        }
    }

    /// The colours the console uploads into the leaders' palette when the
    /// hero takes it; none for one with a palette of its own in the map.
    pub fn colors(&self) -> &[u32] {
        match self {
            RouteGfx::Colored(_, _, c) => c,
            RouteGfx::Plain(..) => &[],
        }
    }
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
    Cache {
        cache: i64,
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
    /// Each one's palette, in the same order. An event that walks carries
    /// one graphic's poses in its row, and a page that brings another one
    /// gives the row this entry and this palette: see `page_table`.
    #[serde(default)]
    pub animated_palettes: Vec<i64>,
    /// Each one's twelve poses, as this map quantized them.
    pub banks: Vec<(String, i64, String)>,
    /// The graphics command 34 changes to: `[pose table entry or $FF,
    /// palette]`, and a third element for one drawn in the leaders'
    /// palette with colours of its own: those, as CGRAM words.
    pub route_gfx: Vec<RouteGfx>,
    /// The raindrops, the turn slot's block, the `ShowPicture` picture and
    /// the battle animation's box: `[first tile, palette]`, 0 if none.
    pub rain: (i64, i64),
    pub turn_block: Option<u32>,
    pub image: (i64, i64),
    pub animation: Option<Animation>,
    /// The slots still events take turns in, if the map needed them: see
    /// `sprites::share` in Wally.
    #[serde(default)]
    pub shared: Option<Shared>,
    /// The cache of slots, if the map needed one: see `sprites::cache` in
    /// Wally.
    #[serde(default)]
    pub cache: Option<Cache>,
}

/// The cache of slots, as `wally` answered it.
#[derive(Deserialize)]
pub struct Cache {
    /// `[event, still pose or null, palette]`: each event drawn, with the
    /// still pose it starts with —an index into `stills`— or nothing if it
    /// walks.
    pub events: Vec<(i64, Option<u32>, u32)>,
    /// `[CharSet, index, pose, entry in the pose table, palette]`.
    pub stills: Vec<(String, i64, i64, usize, u32)>,
    /// Each slot's block in the sprite bank.
    pub slots: Vec<u32>,
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
    /// `AnimType_fixed_graphic`: its column never changes, not even when a
    /// move route turns it or walks it.
    pub fixed_graphic: bool,
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
    /// A parallel page that runs only when what it reads changes: the
    /// emission marks it in the trigger's bit 7.
    pub pure: bool,
}

/// What a page of an event that changes graphic draws, as the map's
/// conversion placed it.
#[derive(Deserialize)]
pub struct Draws {
    /// The 32x32 block of the sprite bank its poses start at, and its
    /// palette; no block for an event that only appears, whose own row
    /// already points at its poses.
    pub block: Option<u32>,
    /// In a map with a cache of slots, the still pose instead of the block:
    /// what the row carries in its tile byte. See `sprites::cache` in Wally.
    #[serde(default)]
    pub key: Option<u32>,
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
    /// Whether it turns in place —`AnimType_spin`—, and the column it
    /// shows meanwhile.
    #[serde(default)]
    pub spin: bool,
    #[serde(default)]
    pub pattern: i64,
    /// Whether it walks by a movement type and not a route: its one
    /// command is `ROUTE_BY_TYPE` plus the type. The console gives it a
    /// slot only while others stay free for forced routes.
    #[serde(default)]
    pub by_type: bool,
    pub frequency: i64,
    pub speed: i64,
    /// How many commands it has.
    pub orders: usize,
}

fn eight_bits() -> i64 {
    8
}
