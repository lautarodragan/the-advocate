//! What the cartridge decided about a map, which the game's dump does not
//! say.

use crate::fail::{Bad, Result};
use crate::game::Game;
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// A request for one map's layers:
///
/// ```json
/// {"map": 7,
///  "map_files": {"11": "/…/Map0011.json"},
///  "chipset_files": {"53": "/…/0053.json"},
///  "baked": [[412, 10005]]}
/// ```
///
/// `baked` are the cells of the upper layer the caller painted a tile
/// into, as `[cell, tile id]`: the events it bakes into the map.
#[derive(Debug, Clone, Default)]
pub struct LayersRequest {
    pub map: i32,
    pub baked: Vec<(usize, i16)>,
}

fn field<'a>(data: &'a Value, name: &str, whose: &str) -> Result<&'a Value> {
    data.get(name)
        .ok_or_else(|| Bad::answer(format!("{whose}: no `{name}`")))
}

fn number(v: &Value, what: &str, whose: &str) -> Result<i64> {
    v.as_i64()
        .ok_or_else(|| Bad::answer(format!("{whose}: {what} is {v}, not a whole number")))
}

/// `{"<id>": "<path>"}` into a map by number.
fn files(v: &Value, whose: &str) -> Result<BTreeMap<i32, PathBuf>> {
    let obj = v
        .as_object()
        .ok_or_else(|| Bad::answer(format!("{whose}: not an object: {v}")))?;
    obj.iter()
        .map(|(k, v)| {
            let id = k
                .parse::<i32>()
                .map_err(|_| Bad::answer(format!("{whose}: {k} is not a number")))?;
            let path = v
                .as_str()
                .ok_or_else(|| Bad::answer(format!("{whose}: {v} is not a path")))?;
            Ok((id, PathBuf::from(path)))
        })
        .collect()
}

/// Reads a request file: the JSON, and the project's files into `game`.
pub fn read(path: &Path) -> Result<(Value, String)> {
    let whose = path.display().to_string();
    let text = std::fs::read_to_string(path).map_err(|e| Bad::usage(format!("{whose}: {e}")))?;
    let data = serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{whose}: {e}")))?;
    Ok((data, whose))
}

/// The project's patches every request carries: its map and ChipSet files.
pub fn patches(data: &Value, whose: &str, game: &mut Game) -> Result<()> {
    game.map_files = files(field(data, "map_files", whose)?, whose)?;
    game.chipset_files = files(field(data, "chipset_files", whose)?, whose)?;
    Ok(())
}

impl LayersRequest {
    pub fn from_json(data: &Value, whose: &str) -> Result<LayersRequest> {
        let map = number(field(data, "map", whose)?, "`map`", whose)?;
        let baked = field(data, "baked", whose)?
            .as_array()
            .ok_or_else(|| Bad::answer(format!("{whose}: `baked` is not a list")))?
            .iter()
            .map(|pair| {
                let bad = || Bad::answer(format!("{whose}: a baked cell is {pair}"));
                let pair = pair.as_array().filter(|p| p.len() == 2).ok_or_else(bad)?;
                let cell = usize::try_from(number(&pair[0], "a cell", whose)?).map_err(|_| bad())?;
                let tile = i16::try_from(number(&pair[1], "a tile", whose)?).map_err(|_| bad())?;
                Ok((cell, tile))
            })
            .collect::<Result<_>>()?;
        Ok(LayersRequest {
            map: i32::try_from(map).map_err(|_| Bad::answer(format!("{whose}: map {map}")))?,
            baked,
        })
    }
}

fn list<'a>(data: &'a Value, name: &str, whose: &str) -> Result<&'a Vec<Value>> {
    field(data, name, whose)?
        .as_array()
        .ok_or_else(|| Bad::answer(format!("{whose}: `{name}` is not a list")))
}

fn text(v: &Value, what: &str, whose: &str) -> Result<String> {
    v.as_str()
        .map(str::to_string)
        .ok_or_else(|| Bad::answer(format!("{whose}: {what} is {v}, not text")))
}

fn index(v: &Value, what: &str, whose: &str) -> Result<usize> {
    usize::try_from(number(v, what, whose)?).map_err(|_| Bad::answer(format!("{whose}: {what} is {v}")))
}

fn small(v: &Value, what: &str, whose: &str) -> Result<i32> {
    i32::try_from(number(v, what, whose)?).map_err(|_| Bad::answer(format!("{whose}: {what} is {v}")))
}

/// `[charset, index]`.
fn key(v: &Value, whose: &str) -> Result<(String, i32)> {
    let pair = v
        .as_array()
        .filter(|p| p.len() == 2)
        .ok_or_else(|| Bad::answer(format!("{whose}: a graphic is {v}, not [CharSet, index]")))?;
    Ok((text(&pair[0], "a CharSet", whose)?, small(&pair[1], "an index", whose)?))
}

fn keys(v: &Value, whose: &str) -> Result<Vec<(String, i32)>> {
    v.as_array()
        .ok_or_else(|| Bad::answer(format!("{whose}: {v} is not a list of graphics")))?
        .iter()
        .map(|k| key(k, whose))
        .collect()
}

fn indices(data: &Value, name: &str, whose: &str) -> Result<std::collections::BTreeSet<usize>> {
    list(data, name, whose)?
        .iter()
        .map(|v| index(v, &format!("an entry of `{name}`"), whose))
        .collect()
}

/// `[[upper layer, old tile, new tile]]`: `TileSubstitution`s.
fn triples(data: &Value, name: &str, whose: &str) -> Result<Vec<crate::substitutions::Triple>> {
    list(data, name, whose)?
        .iter()
        .map(|t| {
            let bad = || Bad::answer(format!("{whose}: a substitution is {t}, not [upper, old, new]"));
            let a = t.as_array().filter(|a| a.len() == 3).ok_or_else(bad)?;
            Ok((
                a[0].as_bool().ok_or_else(bad)?,
                small(&a[1], "an old tile", whose)?,
                small(&a[2], "a new tile", whose)?,
            ))
        })
        .collect()
}

/// A page record of the event compiler's scan.
fn scanned_page(p: &Value, whose: &str) -> Result<crate::moves::ScannedPage> {
    let flag = |name: &str| -> Result<bool> {
        field(p, name, whose)?
            .as_bool()
            .ok_or_else(|| Bad::answer(format!("{whose}: a page's `{name}` is not true or false")))
    };
    Ok(crate::moves::ScannedPage {
        event: index(field(p, "event", whose)?, "a page's event", whose)?,
        page: index(field(p, "page", whose)?, "a page's number", whose)?,
        trigger: small(field(p, "trigger", whose)?, "a page's trigger", whose)?,
        compiles: !field(p, "code", whose)?.is_null(),
        route_targets: list(p, "route_targets", whose)?
            .iter()
            .map(|v| index(v, "a route target", whose))
            .collect::<Result<_>>()?,
        own_route: !field(p, "own_route", whose)?.is_null(),
        turns: flag("turns")?,
    })
}

impl crate::map::MapRequest {
    /// A request that only says some of what a whole map's says —the
    /// questions of [`crate::inspect`] need less—: what it leaves out is
    /// empty, nothing, or no.
    pub fn partial(data: &Value, whose: &str) -> Result<crate::map::MapRequest> {
        let mut full = serde_json::json!({
            "map_files": {}, "chipset_files": {}, "names": [], "test_event": false,
            "leaders": [], "pages": [], "route_graphics": [], "also_walk": [],
            "timer": null, "rain": false, "picture": null,
            "battle_animation": false, "singles": [], "palette_weight": {},
            "dither": "five_of_eight", "substitutions": [], "common_substitutions": [],
        });
        let given = data
            .as_object()
            .ok_or_else(|| Bad::answer(format!("{whose}: not an object")))?;
        for (k, v) in given {
            full[k] = v.clone();
        }
        Self::from_json(&full, whose)
    }

    /// A request for a whole map:
    ///
    /// ```json
    /// {"map": 7, "map_files": {}, "chipset_files": {},
    ///  "names": [[3, 1, "Ghost~horneado:7:4:5"]], "test_event": false,
    ///  "leaders": [10, 1],
    ///  "pages": [{"event": 2, "page": 0, "trigger": 0, "code": "0600…",
    ///             "route_targets": [2], "own_route": null, "turns": true}],
    ///  "route_graphics": [["People1", 3]], "also_walk": [],
    ///  "timer": null, "rain": false, "picture": null,
    ///  "battle_animation": false, "singles": [["People1", 3]],
    ///  "palette_weight": {"savept": 1}, "dither": "five_of_eight",
    ///  "substitutions": [[false, 80, 81]], "common_substitutions": []}
    /// ```
    ///
    /// `substitutions` are the `TileSubstitution`s the map's events and its
    /// test pages can run, as `[upper layer, old tile, new tile]`: their
    /// blocks are built. `common_substitutions` are the common events', which
    /// a `CallEvent` can bring into any map: they are only translated, with
    /// the blocks there are.
    ///
    /// `pages` are the records the event compiler's scan answered for this
    /// map, as it wrote them: of each, only `event`, `page`, `trigger`,
    /// whether `code` is null, `route_targets`, whether `own_route` is null
    /// and `turns` are read.
    ///
    /// A `picture` is `{"name", "objects", "tiles", "cells": [[tile,
    /// [64 indices]], ...]}`, already cut by whoever decided it.
    pub fn from_json(data: &Value, whose: &str) -> Result<crate::map::MapRequest> {
        use crate::map::{MapRequest, PictureAsked};
        use rm2k_snes_map_sprites::extras::Image;
        let mut names = BTreeMap::new();
        for n in list(data, "names", whose)? {
            let a = n
                .as_array()
                .filter(|a| a.len() == 3)
                .ok_or_else(|| Bad::answer(format!("{whose}: a name is {n}")))?;
            names.insert(
                (small(&a[0], "an event", whose)?, small(&a[1], "a page", whose)?),
                text(&a[2], "a name", whose)?,
            );
        }
        let pages = list(data, "pages", whose)?
            .iter()
            .map(|p| scanned_page(p, whose))
            .collect::<Result<_>>()?;
        let picture = match field(data, "picture", whose)? {
            Value::Null => None,
            p => {
                let mut cells = Vec::new();
                for c in list(p, "cells", whose)? {
                    let bad = || Bad::answer(format!("{whose}: a picture cell is {c}"));
                    let a = c.as_array().filter(|a| a.len() == 2).ok_or_else(bad)?;
                    let values = a[1].as_array().filter(|v| v.len() == 64).ok_or_else(bad)?;
                    let mut cell = [[0u8; 8]; 8];
                    for (i, v) in values.iter().enumerate() {
                        cell[i / 8][i % 8] = v.as_u64().and_then(|n| u8::try_from(n).ok()).ok_or_else(bad)?;
                    }
                    cells.push((index(&a[0], "a picture tile", whose)?, cell));
                }
                Some(PictureAsked {
                    name: text(field(p, "name", whose)?, "the picture's name", whose)?,
                    objects: index(field(p, "objects", whose)?, "`objects`", whose)?,
                    image: Image {
                        tiles: index(field(p, "tiles", whose)?, "`tiles`", whose)?,
                        cells,
                    },
                })
            }
        };
        let weights = field(data, "palette_weight", whose)?
            .as_object()
            .ok_or_else(|| Bad::answer(format!("{whose}: `palette_weight` is not an object")))?
            .iter()
            .map(|(k, v)| Ok((k.clone(), number(v, "a weight", whose)?)))
            .collect::<Result<_>>()?;
        let flag = |name: &str| -> Result<bool> {
            field(data, name, whose)?
                .as_bool()
                .ok_or_else(|| Bad::answer(format!("{whose}: `{name}` is not true or false")))
        };
        Ok(MapRequest {
            map: small(field(data, "map", whose)?, "`map`", whose)?,
            names,
            test_event: flag("test_event")?,
            leaders: list(data, "leaders", whose)?
                .iter()
                .map(|v| small(v, "a leader", whose))
                .collect::<Result<_>>()?,
            pages,
            route_graphics: keys(field(data, "route_graphics", whose)?, whose)?,
            also_walk: indices(data, "also_walk", whose)?,
            timer: match field(data, "timer", whose)? {
                Value::Null => None,
                v => Some(PathBuf::from(text(v, "`timer`", whose)?)),
            },
            rain: flag("rain")?,
            picture,
            battle_animation: flag("battle_animation")?,
            singles: keys(field(data, "singles", whose)?, whose)?.into_iter().collect(),
            weights,
            dither: text(field(data, "dither", whose)?, "`dither`", whose)?,
            substitutions: triples(data, "substitutions", whose)?,
            common_substitutions: triples(data, "common_substitutions", whose)?,
        })
    }
}
