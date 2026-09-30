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
