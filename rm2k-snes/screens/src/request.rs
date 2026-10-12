//! What the cartridge decided, which the game's dump does not say: the
//! requests each subcommand reads.

use crate::checks::Vram;
use crate::convert::Request;
use crate::fail::{Bad, Result};
use crate::render::{Party, Shop};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// A System the cartridge switches to with `ChangeSystemGraphics`: its
/// name, the colour its windows are drawn over —the project's
/// `[windows.background]` for it— and the stretch the command asks for.
#[derive(Debug, Clone)]
pub struct OtherSystem {
    pub system: String,
    pub background: Option<String>,
    pub stretch: Option<i32>,
}

/// A request file: its JSON, and whose it is for the messages.
pub struct Json {
    pub data: Value,
    pub whose: String,
}

impl Json {
    pub fn read(path: &Path) -> Result<Json> {
        let whose = path.display().to_string();
        let text = std::fs::read_to_string(path).map_err(|e| Bad::usage(format!("{whose}: {e}")))?;
        let data = serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{whose}: {e}")))?;
        Ok(Json { data, whose })
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
        v.as_str().map(str::to_string).ok_or_else(|| self.bad(name, v))
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

    /// `{"<id>": "<path>"}`, as paths in the order of their numbers.
    pub fn files(&self, name: &str) -> Result<Vec<PathBuf>> {
        let v = match self.get(name) {
            None => return Ok(Vec::new()),
            Some(v) => v,
        };
        let mut out: Vec<(i64, PathBuf)> = v
            .as_object()
            .ok_or_else(|| self.bad(name, v))?
            .iter()
            .map(|(k, p)| {
                let key = k.parse::<i64>().map_err(|_| self.bad(name, v))?;
                let path = p.as_str().ok_or_else(|| self.bad(name, v))?;
                Ok((key, PathBuf::from(path)))
            })
            .collect::<Result<_>>()?;
        out.sort();
        Ok(out.into_iter().map(|(_, p)| p).collect())
    }

    /// The conversion's request.
    ///
    /// ```json
    /// {"slots": 4, "actors": [1, 11, 14], "items": [1, 2, 7], "title": true,
    ///  "cgram_reserved": 9,
    ///  "vram": {"slot_vram": 8192, "slot_map": 15360,
    ///           "bg1_banks": [["WINDOW", 4096, 20480]]}}
    /// ```
    pub fn convert(&self) -> Result<Request> {
        let vram = self.field("vram")?;
        let vram_field = |name: &str| -> Result<usize> {
            vram.get(name)
                .and_then(Value::as_u64)
                .map(|n| n as usize)
                .ok_or_else(|| Bad::answer(format!("{}: no `vram.{name}`", self.whose)))
        };
        let banks = vram
            .get("bg1_banks")
            .and_then(Value::as_array)
            .ok_or_else(|| Bad::answer(format!("{}: no `vram.bg1_banks`", self.whose)))?
            .iter()
            .map(|b| {
                let bad = || Bad::answer(format!("{}: a BG1 bank is {b}", self.whose));
                let b = b.as_array().filter(|b| b.len() == 3).ok_or_else(bad)?;
                Ok((
                    b[0].as_str().ok_or_else(bad)?.to_string(),
                    b[1].as_u64().ok_or_else(bad)? as usize,
                    b[2].as_u64().ok_or_else(bad)? as usize,
                ))
            })
            .collect::<Result<_>>()?;
        let mut menus = Vec::new();
        if let Some(list) = self.get("menus") {
            for m in list.as_array().ok_or_else(|| self.bad("menus", list))? {
                let name = m.get("name").and_then(Value::as_str).ok_or_else(|| self.bad("menus", m))?;
                let spec = m.get("spec").cloned().ok_or_else(|| self.bad("menus", m))?;
                menus.push((name.to_string(), spec));
            }
        }
        let mut menu_context = crate::custom_menu::Context::default();
        if let Some(v) = self.get("variables") {
            for pair in v.as_array().ok_or_else(|| self.bad("variables", v))? {
                let p = pair.as_array().filter(|p| p.len() == 2).ok_or_else(|| self.bad("variables", v))?;
                let (var, slot) = (p[0].as_i64(), p[1].as_u64());
                match (var, slot) {
                    (Some(var), Some(slot)) => {
                        menu_context.variables.insert(var as i32, slot as usize);
                    }
                    _ => return Err(self.bad("variables", v)),
                }
            }
        }
        for (common, body) in self.by_number("before_bodies")? {
            menu_context.before_bodies.insert(common, body as u8);
        }
        Ok(Request {
            menus,
            menu_context,
            slots: self.index_or("slots", 0)?,
            actors: self.actors("actors")?,
            items: self.actors("items")?,
            title: self.flag("title", false)?,
            cgram_reserved: self.index_or("cgram_reserved", 0)?,
            text_rows: self.text_rows()?,
            vram: Vram {
                slot_vram: vram_field("slot_vram")?,
                slot_map: vram_field("slot_map")?,
                bg1_banks: banks,
            },
        })
    }

    /// `systems`, the other Systems a cartridge switches to, for the
    /// `window` subcommand: none if the request does not have it.
    pub fn systems(&self) -> Result<Vec<OtherSystem>> {
        let Some(v) = self.get("systems") else {
            return Ok(Vec::new());
        };
        let bad = || self.bad("systems", v);
        let mut out = Vec::new();
        for s in v.as_array().ok_or_else(bad)? {
            let system = s.get("system").and_then(Value::as_str).ok_or_else(bad)?.to_string();
            let background = match s.get("background") {
                None | Some(Value::Null) => None,
                Some(b) => Some(b.as_str().ok_or_else(bad)?.to_string()),
            };
            let stretch = match s.get("stretch") {
                None | Some(Value::Null) => None,
                Some(n) => Some(n.as_i64().and_then(|n| i32::try_from(n).ok()).ok_or_else(bad)?),
            };
            out.push(OtherSystem { system, background, stretch });
        }
        Ok(out)
    }

    /// `text_rows`, the glyph rows that take one entry each: a list of
    /// lists of rows, or nothing.
    pub fn text_rows(&self) -> Result<Option<crate::message_window::TextRows>> {
        let Some(v) = self.get("text_rows").filter(|v| !v.is_null()) else {
            return Ok(None);
        };
        let bad = || self.bad("text_rows", v);
        let mut out = Vec::new();
        for class in v.as_array().ok_or_else(bad)? {
            let rows: Option<Vec<usize>> =
                class.as_array().ok_or_else(bad)?.iter().map(|r| r.as_u64().map(|r| r as usize)).collect();
            out.push(rows.ok_or_else(bad)?);
        }
        let mut all: Vec<usize> = out.iter().flatten().copied().collect();
        all.sort_unstable();
        if all != (0..rm2k_snes_text::font::HEIGHT).collect::<Vec<_>>() {
            return Err(bad());
        }
        Ok(Some(out))
    }

    /// The party a screen shows: `party`, and optionally `actors`, `hp`,
    /// `levels` and `exps`, by actor number.
    pub fn party(&self) -> Result<Party> {
        Ok(Party {
            members: self.actors("party")?,
            actors: self.optional_actors("actors")?,
            hp: self.by_number("hp")?,
            levels: self.by_number("levels")?,
            exps: self.by_number("exps")?,
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
                        .map(|i| i.as_i64().map(|i| i as i32).ok_or_else(|| self.bad("party_equipment", v)))
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
                    .map(|a| a.as_i64().map(|a| a as i32).ok_or_else(|| self.bad("parties", v)))
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
