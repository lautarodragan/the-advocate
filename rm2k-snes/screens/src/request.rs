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
use crate::render::{Party, Shop};
use serde::de::DeserializeOwned;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

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

/// A request file: its JSON, and whose it is for the messages.
pub struct Json {
    pub data: Value,
    pub whose: String,
}

impl Json {
    pub fn read(path: &Path) -> Result<Json> {
        let whose = path.display().to_string();
        let text =
            std::fs::read_to_string(path).map_err(|e| Bad::usage(format!("{whose}: {e}")))?;
        let data = serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{whose}: {e}")))?;
        Ok(Json { data, whose })
    }

    /// The whole request as `T`, a complaint naming the file.
    pub fn typed<T: DeserializeOwned>(&self) -> Result<T> {
        serde_json::from_value(self.data.clone())
            .map_err(|e| Bad::answer(format!("{}: {e}", self.whose)))
    }

    fn get(&self, name: &str) -> Option<&Value> {
        self.data.get(name).filter(|v| !v.is_null())
    }

    fn field(&self, name: &str) -> Result<&Value> {
        self.get(name)
            .ok_or_else(|| Bad::answer(format!("{}: no `{name}`", self.whose)))
    }

    fn bad(&self, what: &str, v: &Value) -> Bad {
        Bad::answer(format!("{}: `{what}` is {v}", self.whose))
    }

    pub fn number(&self, name: &str) -> Result<i64> {
        let v = self.field(name)?;
        v.as_i64().ok_or_else(|| self.bad(name, v))
    }

    pub fn number_or(&self, name: &str, default: i64) -> Result<i64> {
        match self.get(name) {
            None => Ok(default),
            Some(_) => self.number(name),
        }
    }

    pub fn index_or(&self, name: &str, default: usize) -> Result<usize> {
        let n = self.number_or(name, default as i64)?;
        usize::try_from(n).map_err(|_| self.bad(name, &Value::from(n)))
    }

    pub fn flag(&self, name: &str, default: bool) -> Result<bool> {
        match self.get(name) {
            None => Ok(default),
            Some(v) => v.as_bool().ok_or_else(|| self.bad(name, v)),
        }
    }

    pub fn text(&self, name: &str) -> Result<String> {
        let v = self.field(name)?;
        v.as_str()
            .map(str::to_string)
            .ok_or_else(|| self.bad(name, v))
    }

    pub fn numbers(&self, name: &str) -> Result<Vec<i64>> {
        let v = self.field(name)?;
        v.as_array()
            .ok_or_else(|| self.bad(name, v))?
            .iter()
            .map(|n| n.as_i64().ok_or_else(|| self.bad(name, v)))
            .collect()
    }

    fn actors(&self, name: &str) -> Result<Vec<i32>> {
        Ok(self.numbers(name)?.into_iter().map(|n| n as i32).collect())
    }

    /// `name`: a list of one-letter texts, or empty if it is not there.
    pub fn letters(&self, name: &str) -> Result<Vec<char>> {
        let Some(v) = self.get(name) else {
            return Ok(Vec::new());
        };
        v.as_array()
            .ok_or_else(|| self.bad(name, v))?
            .iter()
            .map(|l| {
                let mut chars = l.as_str().unwrap_or("").chars();
                match (chars.next(), chars.next()) {
                    (Some(c), None) => Ok(c),
                    _ => Err(self.bad(name, v)),
                }
            })
            .collect()
    }

    fn optional_actors(&self, name: &str) -> Result<Option<Vec<i32>>> {
        match self.get(name) {
            None => Ok(None),
            Some(_) => Ok(Some(self.actors(name)?)),
        }
    }

    /// `{"<number>": value}`, or empty if it is not there.
    pub fn by_number(&self, name: &str) -> Result<BTreeMap<i32, i64>> {
        let v = match self.get(name) {
            None => return Ok(BTreeMap::new()),
            Some(v) => v,
        };
        v.as_object()
            .ok_or_else(|| self.bad(name, v))?
            .iter()
            .map(|(k, n)| {
                let key = k.parse::<i32>().map_err(|_| self.bad(name, v))?;
                Ok((key, n.as_i64().ok_or_else(|| self.bad(name, v))?))
            })
            .collect()
    }

    /// `{"<id>": [n, ...]}`, lists of numbers by number: each actor's
    /// conditions. Without it, empty.
    pub fn lists_by_number(&self, name: &str) -> Result<BTreeMap<i32, Vec<i32>>> {
        let v = match self.get(name) {
            None => return Ok(BTreeMap::new()),
            Some(v) => v,
        };
        v.as_object()
            .ok_or_else(|| self.bad(name, v))?
            .iter()
            .map(|(k, list)| {
                let key = k.parse::<i32>().map_err(|_| self.bad(name, v))?;
                let numbers = list
                    .as_array()
                    .ok_or_else(|| self.bad(name, v))?
                    .iter()
                    .map(|n| {
                        n.as_i64()
                            .and_then(|n| i32::try_from(n).ok())
                            .ok_or_else(|| self.bad(name, v))
                    })
                    .collect::<Result<_>>()?;
                Ok((key, numbers))
            })
            .collect()
    }

    /// The party a screen shows: `party`, and optionally `actors`, `hp`,
    /// `sp`, `levels`, `exps` and `states`, by actor number.
    pub fn party(&self) -> Result<Party> {
        Ok(Party {
            members: self.actors("party")?,
            actors: self.optional_actors("actors")?,
            hp: self.by_number("hp")?,
            sp: self.by_number("sp")?,
            levels: self.by_number("levels")?,
            exps: self.by_number("exps")?,
            states: self.lists_by_number("states")?,
        })
    }

    pub fn known_items(&self, name: &str) -> Result<Option<BTreeSet<i32>>> {
        Ok(self.optional_actors(name)?.map(|v| v.into_iter().collect()))
    }

    /// The shop's state: see [`Shop`].
    pub fn shop(&self) -> Result<Shop> {
        let party_equipment = match self.get("party_equipment") {
            None => Vec::new(),
            Some(v) => v
                .as_array()
                .ok_or_else(|| self.bad("party_equipment", v))?
                .iter()
                .map(|e| {
                    e.as_array()
                        .ok_or_else(|| self.bad("party_equipment", v))?
                        .iter()
                        .map(|i| {
                            i.as_i64()
                                .map(|i| i as i32)
                                .ok_or_else(|| self.bad("party_equipment", v))
                        })
                        .collect()
                })
                .collect::<Result<_>>()?,
        };
        Ok(Shop {
            kind: self.index_or("kind", 0)?,
            term_set: self.index_or("term_set", 0)?,
            sells: self.actors("sells")?,
            gold: self.number_or("gold", 0)?,
            inventory: self.by_number("inventory")?,
            party_equipment,
            party: self.optional_actors("party")?.unwrap_or_default(),
            frames: self
                .optional_actors("frames")?
                .unwrap_or_default()
                .into_iter()
                .map(|f| f as usize)
                .collect(),
            phase: self.index_or("phase", 0)?,
            mode: self.index_or("mode", 0)?,
            chosen: self.index_or("chosen", 0)?,
            top: self.index_or("top", 0)?,
            count: self.number_or("count", 1)?,
            regreeting: self.flag("regreeting", false)?,
            known: self.known_items("items")?,
        })
    }

    /// `{"<slot>": [actors]}` of the slot screen's `parties`.
    pub fn parties(&self) -> Result<BTreeMap<usize, Vec<i32>>> {
        let v = match self.get("parties") {
            None => return Ok(BTreeMap::new()),
            Some(v) => v,
        };
        v.as_object()
            .ok_or_else(|| self.bad("parties", v))?
            .iter()
            .map(|(k, members)| {
                let slot = k.parse::<usize>().map_err(|_| self.bad("parties", v))?;
                let members = members
                    .as_array()
                    .ok_or_else(|| self.bad("parties", v))?
                    .iter()
                    .map(|a| {
                        a.as_i64()
                            .map(|a| a as i32)
                            .ok_or_else(|| self.bad("parties", v))
                    })
                    .collect::<Result<_>>()?;
                Ok((slot, members))
            })
            .collect()
    }

    pub fn flags(&self, name: &str) -> Result<Vec<bool>> {
        let v = match self.get(name) {
            None => return Ok(Vec::new()),
            Some(v) => v,
        };
        v.as_array()
            .ok_or_else(|| self.bad(name, v))?
            .iter()
            .map(|b| b.as_bool().ok_or_else(|| self.bad(name, v)))
            .collect()
    }
}
