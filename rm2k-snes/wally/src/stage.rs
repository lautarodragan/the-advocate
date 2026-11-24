//! Wally as a stage of a converter: what each of its commands answers, as
//! the files the binary writes into `--out`, by name. The converter calls
//! [`map`] as a function, and the binary is a `main` over these that reads
//! the request and writes the files.
//!
//! **They read nothing but the dump, the search directories and the request
//! they are given** —and the files the request names, the project's maps,
//! ChipSets and pictures—: the converter keeps their answers in its cache
//! under the key of those, and a function that read anything else would
//! hand back a stale answer.

use crate::fail::Result;
use crate::map::{self, MapRequest};
use crate::{inspect, layers, request, Bad, Game, LayersRequest};
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// What a command answers: every file it makes, by name.
pub type Files = BTreeMap<String, Vec<u8>>;

/// One of the commands, as the binary calls them: the dump, the search
/// directories, the request and what its complaints start with.
pub type Command = fn(&Path, &[PathBuf], &Value, &str) -> Result<Files>;

/// What a request's complaints start with when it comes as a value and not
/// from a file.
const WHOSE: &str = "the request";

/// The game in `data`, its pictures looked up in `search_dirs`, with the
/// project's files `request` names over the dump's —see
/// [`request::patches`]—.
pub fn game(data: &Path, search_dirs: &[PathBuf], request: &Value, whose: &str) -> Result<Game> {
    let mut game = Game {
        data: data.to_path_buf(),
        search_dirs: search_dirs.to_vec(),
        ..Game::default()
    };
    request::patches(request, whose, &mut game)?;
    Ok(game)
}

/// `map`: a whole map —its layers, the events baked into them, its
/// characters as objects, its blocks and where the hero starts—, for the
/// cartridge `request` describes. See [`MapRequest::from_json`] and
/// [`map::files`].
pub fn map(data: &Path, search_dirs: &[PathBuf], request: &Value) -> Result<Files> {
    map_of(data, search_dirs, request, WHOSE)
}

/// [`map`], with `whose` starting its complaints.
pub fn map_of(data: &Path, search_dirs: &[PathBuf], request: &Value, whose: &str) -> Result<Files> {
    let game = game(data, search_dirs, request, whose)?;
    let request = MapRequest::from_json(request, whose)?;
    map::files(&map::convert(&game, &request)?)
}

/// `layers`: the map's two background layers, alone. See
/// [`LayersRequest::from_json`] and [`layers::files`].
pub fn layers_of(
    data: &Path,
    search_dirs: &[PathBuf],
    request: &Value,
    whose: &str,
) -> Result<Files> {
    let game = game(data, search_dirs, request, whose)?;
    let request = LayersRequest::from_json(request, whose)?;
    layers::run(&game, &request)
}

/// `bakeable`: which events of a map can be baked, and why that is safe.
pub fn bakeable_of(
    data: &Path,
    search_dirs: &[PathBuf],
    request: &Value,
    whose: &str,
) -> Result<Files> {
    let game = game(data, search_dirs, request, whose)?;
    let asked = MapRequest::partial(request, whose)?;
    Ok(one(
        "bakeable.json",
        &inspect::bakeable_report(&game, &asked)?,
    ))
}

/// `split`: how a map's object palettes are split with `palettes` of
/// them, which the request says.
pub fn split_of(
    data: &Path,
    search_dirs: &[PathBuf],
    request: &Value,
    whose: &str,
) -> Result<Files> {
    let game = game(data, search_dirs, request, whose)?;
    let asked = MapRequest::partial(request, whose)?;
    let palettes = request
        .get("palettes")
        .and_then(Value::as_u64)
        .ok_or_else(|| Bad::answer(format!("{whose}: no `palettes`, how many the split gets")))?;
    Ok(one(
        "split.json",
        &inspect::split_report(&game, &asked, palettes as usize)?,
    ))
}

/// `answer` as the file `name`, compact, as the questions always wrote it.
fn one(name: &str, answer: &Value) -> Files {
    Files::from([(name.to_string(), answer.to_string().into_bytes())])
}
