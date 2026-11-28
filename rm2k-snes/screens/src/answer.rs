//! What `convert` answers, as the emission takes it: the message window
//! and its font, the title's menu, the slots and the pause menu, the text
//! screens with their windows, End Game, the texts they compose, and the
//! geometry they were drawn with. The converter reads a few of its fields
//! and hands the rest on to `rm2k-snes-mapdata`, which depends on this
//! crate for these types.
//!
//! Bytes go as hex text and tiles as rows of colour indices, as they always
//! went; a geometry is a list of numbers by name, which the emission writes
//! out by name.

use crate::borders::{CompactShop, CompactTarget, CompactTargetSkill};
use crate::cells::Color;
use crate::message_window::{FontInk, Ink};
use crate::slots::MenuBlocks;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use voodoo::pack::Indices;

/// The whole answer.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Answer {
    pub font: ScreenFont,
    pub custom_menus: CustomMenus,
    /// Only in a cartridge that carries the debug screen.
    pub debug_screen: Option<DebugScreen>,
    pub window: Window,
    pub title: Option<Title>,
    pub slots: Slots,
    pub text_inks: TextInks,
    pub battle_windows: BattleWindows,
    pub skills_screen: SkillsScreen,
    /// Per skill of the database, by number: see [`SkillRow`].
    pub skills: BTreeMap<i32, SkillRow>,
    pub items_border: Borders,
    /// The item and equipment windows' first tile in the bank.
    pub items_border_first: usize,
    pub shop_border: ShopBorder,
    pub shop_party: ShopParty,
    pub target: Target,
    pub end_game: EndGame,
    pub texts: Texts,
    /// The geometry the screens are drawn with, by name: see
    /// `layout::publish`.
    pub layout: Value,
    /// What the conversion says, line by line, and what of it is a loss.
    pub says: Vec<String>,
    pub losses: Vec<Loss>,
}

/// A loss of the cartridge's screens: `kind` is the stable slug the
/// converter lists it by in the cartridge's degradations.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Loss {
    pub kind: String,
    pub text: String,
}

/// The font's glyphs past the console's, as the text screens draw them.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ScreenFont {
    /// Each glyph prerendered, as hex.
    #[serde(with = "hex::each")]
    pub prerender: Vec<Vec<u8>>,
    /// Where the letters start among the glyphs, and the letters the text
    /// screens reach from there: the emission writes the database's texts
    /// with them.
    pub letters_at: usize,
    pub screen_letters: Vec<char>,
}

/// The message window of one System, as the emission takes it: what
/// changes from one System to another. See `message_window::Window`.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
pub struct SystemWindow {
    pub disabled: Vec<u8>,
    /// The box's ink entry, 0 without one, and the twenty colours: see
    /// `message_window::inks`.
    pub ink: u8,
    pub inks: Vec<Ink>,
    pub gold: Gold,
    #[serde(with = "hex")]
    pub tiles: Vec<u8>,
    pub cgram: Vec<u16>,
    pub cells: Vec<Vec<usize>>,
    pub base: usize,
    #[serde(with = "hex")]
    pub background: Vec<u8>,
    pub color: Vec<u8>,
    pub shadow: u8,
    pub arrow: Vec<usize>,
    #[serde(with = "hex")]
    pub bar: Vec<u8>,
    #[serde(with = "hex")]
    pub bar_bare: Vec<u8>,
}

/// The gold window `ShowInn` opens: its tiles, its colours, where its right
/// edge falls, its size and its text's row. See `message_window::Gold`.
#[derive(Serialize, Deserialize, Debug, Clone, PartialEq)]
pub struct Gold {
    #[serde(with = "hex")]
    pub tiles: Vec<u8>,
    pub cgram: Vec<u16>,
    pub right: usize,
    pub width: usize,
    pub height: usize,
    pub text_y: usize,
}

/// The starting System's message window, with the font: its glyphs, how
/// far each moves the line and paints, and the colours it is drawn in.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Window {
    #[serde(flatten)]
    pub system: SystemWindow,
    #[serde(with = "hex")]
    pub font: Vec<u8>,
    pub advances: Vec<u8>,
    pub reach: Vec<u8>,
    pub font_ink: FontInk,
}

/// The title's menu: its options' texts, tiles, colours and a tilemap per
/// option chosen.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Title {
    pub texts: Vec<String>,
    pub tiles: Vec<Indices>,
    pub palette: Vec<Color>,
    pub tilemaps: Vec<Vec<u16>>,
}

/// The slots screen and the pause menu: see `slots::Slots`.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Slots {
    pub tiles: Vec<Indices>,
    /// The tiles the menu's own take, and where the slot screen's names go
    /// among them: `[first, end)`.
    pub menu_tiles: usize,
    pub slot_names: (usize, usize),
    pub palettes: Vec<Vec<Color>>,
    pub headers: Vec<Vec<u16>>,
    pub rows: Vec<[Vec<u16>; 2]>,
    /// Each actor's face, by number.
    pub faces: BTreeMap<i32, Vec<u16>>,
    pub menu: MenuBlocks,
    pub font_ink: FontInk,
    pub states: States,
}

/// The conditions as the party panel and the skills screen show them: see
/// `slots::StateInks`.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct States {
    pub names: Vec<String>,
    pub ink: Vec<usize>,
    pub inks: Vec<StateInk>,
    pub shadow: u8,
    pub gray_shadow: u8,
}

/// A condition's colour: its palette, its glyph rows, and its colour words
/// as the skills screen uploads them —the System colour's twelve rows and
/// its shadow—.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct StateInk {
    pub palette: u16,
    pub rows: Vec<u8>,
    pub cgram: Vec<u16>,
}

/// The text screens' inks: a palette per colour, the colours of the font
/// for them, and how far each of their glyphs moves the line and paints
/// —the console's, `TL_FIGURE`'s place and the icons' halves—.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct TextInks {
    pub palettes: Vec<Vec<Color>>,
    pub font_ink: FontInk,
    pub advances: Vec<u8>,
    pub reach: Vec<u8>,
    pub icons: Vec<usize>,
}

/// The battle's windows: see `battle::battle_windows`.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct BattleWindows {
    pub tiles: Vec<Indices>,
    pub colors: Vec<Color>,
    pub first: usize,
    pub cgram: usize,
    pub band_row: usize,
    pub band: Vec<Vec<u16>>,
    pub help: Vec<u16>,
    pub patches: Vec<u16>,
    /// Per layout and set, each bar where it changes: `[row, col, rows,
    /// cols, its first word in patches]`.
    pub bars: Vec<Vec<Vec<[usize; 5]>>>,
}

/// The skills screen's windows: see `skills::windows`.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct SkillsScreen {
    pub tiles: Vec<Indices>,
    pub colors: Vec<Color>,
    pub map: Vec<u16>,
    pub bars: Vec<u16>,
}

/// What the cartridge needs of a skill to write it on the map: see
/// `skills::per_skill`.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct SkillRow {
    /// The description's two lines: the first's letters, and the second's
    /// start and letters.
    pub lines: [usize; 3],
    pub field: bool,
    pub revives: bool,
    pub target_name: String,
}

/// Windows drawn over one bank: their tiles and colours, and per screen
/// its tilemap and each bar's. See `borders::Borders`.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Borders {
    pub tiles: Vec<Indices>,
    pub colors: Vec<Color>,
    pub maps: Vec<(Vec<u16>, Vec<Vec<u16>>)>,
}

/// The shop's windows: see `borders::CompactShop`.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ShopBorder {
    pub tiles: Vec<Indices>,
    pub colors: Vec<Color>,
    #[serde(flatten)]
    pub compact: CompactShop,
}

/// The shop's party: each member's frames and colours —none for one
/// without a CharSet, whose place stays empty—, the System's arrows, and
/// the first of their tiles.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ShopParty {
    pub on: bool,
    pub members: Vec<ShopMember>,
    pub arrows: Vec<Indices>,
    pub arrow_colors: Vec<Color>,
    pub tile0: usize,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ShopMember {
    pub actor: i32,
    #[serde(flatten)]
    pub drawn: Option<crate::party::Member>,
}

/// The actor choice: see `borders::CompactTarget`.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Target {
    pub tiles: Vec<Indices>,
    pub colors: Vec<Color>,
    #[serde(flatten)]
    pub compact: CompactTarget,
    pub skill: CompactTargetSkill,
}

/// End Game's screen: see `end_game::EndGame`.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct EndGame {
    pub tiles: Vec<Indices>,
    pub rows: Vec<u16>,
    pub row0: usize,
    pub palettes: [Vec<Color>; 2],
}

/// What the cartridge composes as text.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Texts {
    /// Each actor's three strips: its name, its level and its maximums.
    pub actors: Vec<[String; 3]>,
    /// Each rename's name strip, as `(actor, strip)`.
    pub renamed: Vec<(i32, String)>,
    pub items: Vec<ItemText>,
    /// The items the actor choice opens for, with their name on its line.
    pub medicines: Vec<Medicine>,
    pub params: Vec<String>,
    pub equipment: Vec<String>,
    /// The shop's messages, per set, each in two lines.
    pub shop: Vec<Vec<Vec<String>>>,
    pub owned: String,
    pub carried: String,
    pub currency: String,
}

/// An item's name and description lines, and whether the map can use it
/// and opens the actor choice for it.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct ItemText {
    pub number: i32,
    pub texts: Vec<String>,
    pub usable: bool,
    pub needs_actor: bool,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Medicine {
    pub number: i32,
    pub name: String,
}

/// The custom menus: see `custom_menu::Built`. Without menus only the
/// geometry goes, which the runtime assembles the same with or without.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct CustomMenus {
    pub labels: Vec<String>,
    #[serde(flatten)]
    pub built: Option<BuiltMenus>,
    /// The geometry the runtime writes with, by name.
    pub layout: Value,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct BuiltMenus {
    #[serde(with = "hex")]
    pub blob: Vec<u8>,
    pub offsets: Vec<u16>,
    pub layouts: Vec<Vec<u16>>,
    pub bars: Vec<Vec<u16>>,
    pub tiles: Vec<Indices>,
    pub colors: Vec<Color>,
    pub inks: Vec<Vec<Color>>,
    pub portraits: Vec<Portrait>,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Portrait {
    pub tiles: Vec<Indices>,
    pub palette: Vec<Color>,
}

/// The debug screen: see `debug_screen::Built`.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct DebugScreen {
    pub label: String,
    /// Each page's block, as hex.
    #[serde(with = "hex::each")]
    pub pages: Vec<Vec<u8>>,
    pub layout: Vec<u16>,
    pub bars: Vec<Vec<u16>>,
    pub tiles: Vec<Indices>,
    pub colors: Vec<Color>,
    /// The geometry the runtime writes with, by name.
    pub geometry: Value,
    pub font: DebugFont,
}

#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct DebugFont {
    pub advances: Vec<u8>,
    pub reach: Vec<u8>,
    #[serde(with = "hex::each")]
    pub prerender: Vec<Vec<u8>>,
}

/// Another System the cartridge switches to, as the emission takes it from
/// `window`'s `systems`: its name and its message window.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct OtherSystem {
    pub system: String,
    pub window: SystemWindow,
}

/// What `window` answers: the colour-memory entries the message window
/// takes, and what the starting System lost to fit them —how many colours
/// it brought, Adeleine's merges, `[victim, target, pixels]`—. With the
/// Systems the cartridge switches to, the text's entries common to all of
/// them, `text_rows`, and each one's window in `systems`; without them,
/// neither.
///
/// The stage writes it through a `Value`, as when it was built with
/// `json!` and the crate's binary wrote its keys sorted: see
/// `stage::window_of`.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct WindowAnswer {
    pub colors: usize,
    pub brought: usize,
    pub merges: Vec<WindowMerge>,
    pub system: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub text_rows: Option<Vec<Vec<usize>>>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub systems: Vec<SwitchedWindow>,
}

/// A colour Adeleine merged into another, and how many pixels it had.
pub type WindowMerge = ([u8; 3], [u8; 3], u64);

/// Another System's entry in [`WindowAnswer`]: its window, as the emission
/// takes it, and what it lost —as the starting one's, with the entries it
/// fits in, `colors`—; the frame's colours it fused, if any, and the rows
/// of its text colour that are not one colour.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct SwitchedWindow {
    #[serde(flatten)]
    pub other: OtherSystem,
    pub brought: usize,
    pub merges: Vec<WindowMerge>,
    pub colors: usize,
    pub frame_fused: Option<usize>,
    pub mixed_text_rows: Vec<usize>,
}

/// What `faces` answers: each face asked for, in the order asked.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct FacesAnswer {
    pub faces: Vec<Face>,
}

/// A face of the message window as the cartridge stores it: see
/// `faces::DrawnFace`. `missing` is one whose FaceSet is neither the
/// game's nor the RTP's, drawn as the window's background alone.
#[derive(Serialize, Deserialize, Debug, Clone)]
pub struct Face {
    #[serde(with = "hex")]
    pub tiles: Vec<u8>,
    pub palette: Vec<u16>,
    pub missing: bool,
}

/// Bytes as hex text, both ways: `#[serde(with = "hex")]`.
pub mod hex {
    pub fn encode(bytes: &[u8]) -> String {
        bytes.iter().map(|b| format!("{b:02x}")).collect()
    }

    pub fn decode(text: &str) -> Result<Vec<u8>, String> {
        if !text.len().is_multiple_of(2) || !text.is_ascii() {
            return Err(format!("{text:?} is not hex"));
        }
        (0..text.len())
            .step_by(2)
            .map(|k| u8::from_str_radix(&text[k..k + 2], 16).map_err(|e| e.to_string()))
            .collect()
    }

    pub fn serialize<S: serde::Serializer>(bytes: &[u8], s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&encode(bytes))
    }

    pub fn deserialize<'de, D: serde::Deserializer<'de>>(d: D) -> Result<Vec<u8>, D::Error> {
        let text: String = serde::Deserialize::deserialize(d)?;
        decode(&text).map_err(serde::de::Error::custom)
    }

    /// A list of byte strings, each as hex text: `#[serde(with =
    /// "hex::each")]`.
    pub mod each {
        pub fn serialize<S: serde::Serializer>(lists: &[Vec<u8>], s: S) -> Result<S::Ok, S::Error> {
            s.collect_seq(lists.iter().map(|bytes| super::encode(bytes)))
        }

        pub fn deserialize<'de, D: serde::Deserializer<'de>>(
            d: D,
        ) -> Result<Vec<Vec<u8>>, D::Error> {
            let texts: Vec<String> = serde::Deserialize::deserialize(d)?;
            texts
                .iter()
                .map(|t| super::decode(t).map_err(serde::de::Error::custom))
                .collect()
        }
    }
}
