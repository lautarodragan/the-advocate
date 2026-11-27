//! Wally as a stage of a converter: what each of its commands answers, as
//! the files it makes, by name. The converter calls [`map`] as a function;
//! the others —`layers_of`, `bakeable_of`, `split_of`— are the crate's
//! tests' questions. Until 2026-11-27 a binary was a `main` over them, for
//! a game's tests.
//!
//! **They read nothing but the dump, the search directories and the request
//! they are given** —and the files the request names, the project's maps,
//! ChipSets and pictures—: the converter keeps their answers in its cache
//! under the key of those, and a function that read anything else would
//! hand back a stale answer.

use crate::fail::Result;
use crate::map;
use crate::request::{self, Asked, LayersAsked};
use crate::{inspect, layers, Bad};
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};

/// What a command answers: every file it makes, by name.
pub type Files = BTreeMap<String, Vec<u8>>;

/// One of the questions on a request: the dump, the search directories,
/// the request and what its complaints start with.
pub type Command = fn(&Path, &[PathBuf], &Value, &str) -> Result<Files>;

/// What a request's complaints start with when it comes as a value and not
/// from a file.
const WHOSE: &str = "the request";

/// `map`: a whole map —its layers, the events baked into them, its
/// characters as objects, its blocks and where the hero starts—, for the
/// cartridge `request` describes, in the game in `data` with its pictures
/// looked up in `search_dirs`. See [`Asked`] and [`map::files`].
pub fn map(data: &Path, search_dirs: &[PathBuf], request: &Asked) -> Result<Files> {
    let game = request.game(data, search_dirs);
    map::files(&map::convert(&game, &request.request(WHOSE)?)?)
}

/// `layers`: the map's two background layers, alone. See [`LayersAsked`]
/// and [`layers::files`].
pub fn layers_of(
    data: &Path,
    search_dirs: &[PathBuf],
    request: &Value,
    whose: &str,
) -> Result<Files> {
    let asked: LayersAsked = request::typed(request, whose)?;
    layers::run(&asked.game(data, search_dirs), &asked.request(whose)?)
}

/// `bakeable`: which events of a map can be baked, and why that is safe.
pub fn bakeable_of(
    data: &Path,
    search_dirs: &[PathBuf],
    request: &Value,
    whose: &str,
) -> Result<Files> {
    let asked = Asked::partial(request, whose)?;
    Ok(one(
        "bakeable.json",
        &inspect::bakeable_report(&asked.game(data, search_dirs), &asked.request(whose)?)?,
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
    #[derive(serde::Deserialize)]
    struct Split {
        palettes: usize,
    }
    let asked = Asked::partial(request, whose)?;
    let Split { palettes } = request::typed(request, whose)
        .map_err(|_| Bad::answer(format!("{whose}: no `palettes`, how many the split gets")))?;
    Ok(one(
        "split.json",
        &inspect::split_report(
            &asked.game(data, search_dirs),
            &asked.request(whose)?,
            palettes,
        )?,
    ))
}

/// `answer` as the file `name`, compact, as the questions always wrote it.
fn one(name: &str, answer: &Value) -> Files {
    Files::from([(name.to_string(), answer.to_string().into_bytes())])
}
