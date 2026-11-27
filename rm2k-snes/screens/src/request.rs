//! What the cartridge decided, which the game's dump does not say: the
//! requests each subcommand reads.
//!
//! The four a converter sends —[`Convert`], [`Boxes`], [`Faces`] and
//! [`Window`]— are types, which it builds and the stage reads with serde:
//! a key renamed on one side does not compile on the other. **Their
//! `#[serde(default)]`s are what a request may leave out**, as the tests'
//! files do. What only the tests send —`render`, `equip`— is read key by
//! key through [`Json`].
//!
//! The order of the fields is the order of the keys the converter's
//! request had when it was a `json!`, and a field it left out when empty
//! is skipped the same: the request is part of the stage's cache key.

use crate::checks::Vram;
use crate::fail::{Bad, Result};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::PathBuf;

/// The font a request draws with: `font`, the project file's `[text]
/// font` —`rm2k`, one the engine carries, or the path of a sheet—, spaced
/// by its `letter_spacing`, and the ExFont's sheet, `exfont`, null when the
/// project names none. See `Font::with_exfont_of`.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TextFont {
    pub font: String,
    #[serde(default)]
    pub letter_spacing: i64,
    #[serde(default)]
    pub exfont: Option<PathBuf>,
}

/// How a request's window measures a line —see `stage::measure_of`—:
/// `font`, spaced by `letter_spacing` and with the icons of `exfont`, and
/// `width` in pixels; or `advances`, each glyph's from the space on, and
/// `width`, which is the window the converter hands the event compiler,
/// with its `letters`, the Latin-1 the font draws, each with its advance;
/// or, without either, `columns` characters of RM2k's fixed-width font,
/// which is how it was asked until 2026-10-03.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Line {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub font: Option<String>,
    #[serde(default)]
    pub letter_spacing: i64,
    #[serde(default)]
    pub exfont: Option<PathBuf>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub advances: Option<Vec<u8>>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub letters: Vec<(char, u8)>,
    #[serde(default)]
    pub width: usize,
    #[serde(default, skip_serializing_if = "is_zero")]
    pub columns: usize,
}

fn is_zero(n: &usize) -> bool {
    *n == 0
}

fn is_false(b: &bool) -> bool {
    !*b
}

/// `boxes`' request: the maps' files the boxes are read from, by number
/// —a fork's, or the dump's—, and the window they are reflowed for,
/// `lines` tall.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Boxes {
    #[serde(default)]
    pub map_files: BTreeMap<i32, PathBuf>,
    #[serde(flatten)]
    pub line: Line,
    #[serde(default)]
    pub lines: usize,
}

/// `faces`' request: each face as `[FaceSet, index, mirrored]`.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Faces {
    pub faces: Vec<crate::faces::Request>,
}

/// `window`'s request: the other Systems the cartridge switches to, none
/// in one that does not.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Window {
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub systems: Vec<OtherSystem>,
}

/// A System the cartridge switches to with `ChangeSystemGraphics`: its
/// name, the colour its windows are drawn over —the project's
/// `[windows.background]` for it— and the stretch the command asks for.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OtherSystem {
    pub system: String,
    #[serde(default)]
    pub background: Option<String>,
    #[serde(default)]
    pub stretch: Option<i32>,
}

/// A custom menu the project declares: its name, and its table in the
/// project file as it is, whose shape is the game's and not a stage's
/// —`custom_menu` reads it—.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Menu {
    pub name: String,
    pub spec: Value,
}

/// `convert`'s request: what the cartridge decided that the screens
/// depend on, read into [`crate::convert::Request`], which says what each
/// is.
///
/// ```json
/// {"font": "rm2k", "slots": 4, "actors": [1, 11, 14], "items": [1, 2, 7],
///  "title": true, "cgram_reserved": 9,
///  "vram": {"slot_vram": 8192, "slot_map": 15360,
///           "bg1_banks": [["WINDOW", 4096, 20480]]}}
/// ```
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Convert {
    #[serde(flatten)]
    pub font: TextFont,
    #[serde(default)]
    pub slots: usize,
    pub actors: Vec<i32>,
    pub items: Vec<i32>,
    #[serde(default)]
    pub title: bool,
    #[serde(default)]
    pub cgram_reserved: usize,
    #[serde(default)]
    pub letters: Vec<char>,
    #[serde(default)]
    pub screen_letters: Vec<char>,
    pub vram: Vram,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub text_rows: Option<crate::message_window::TextRows>,
    #[serde(default)]
    pub menus: Vec<Menu>,
    /// Each variable a custom menu shows, and its slot.
    #[serde(default)]
    pub variables: Vec<(i32, usize)>,
    /// The body each common event runs before a custom menu's page.
    #[serde(default)]
    pub before_bodies: BTreeMap<i32, u8>,
    #[serde(default)]
    pub names: Vec<(i32, String)>,
    #[serde(default, skip_serializing_if = "is_false")]
    pub debug: bool,
}

impl Convert {
    /// The request as the conversion takes it: `text_rows`, when there,
    /// name every glyph row once.
    pub fn read(&self) -> Result<crate::convert::Request> {
        if let Some(rows) = &self.text_rows {
            let mut all: Vec<usize> = rows.iter().flatten().copied().collect();
            all.sort_unstable();
            if all != (0..rm2k_snes_text::font::HEIGHT).collect::<Vec<_>>() {
                return Err(Bad::answer(format!(
                    "`text_rows` do not name every glyph row once: {rows:?}"
                )));
            }
        }
        Ok(crate::convert::Request {
            slots: self.slots,
            actors: self.actors.clone(),
            items: self.items.clone(),
            title: self.title,
            cgram_reserved: self.cgram_reserved,
            letters: self.letters.clone(),
            screen_letters: self.screen_letters.clone(),
            vram: self.vram.clone(),
            menus: self
                .menus
                .iter()
                .map(|m| (m.name.clone(), m.spec.clone()))
                .collect(),
            menu_context: crate::custom_menu::Context {
                variables: self.variables.iter().copied().collect(),
                before_bodies: self.before_bodies.clone(),
            },
            text_rows: self.text_rows.clone(),
            names: self.names.clone(),
            debug: self.debug,
        })
    }
}
