//! The event compiler as a stage of a converter: its two calls, `scan` and
//! `compile`, from a dump and a request to the typed answer —see
//! [`crate::answer`]—. The converter calls these as functions, and the
//! binary is a `main` over them that reads the request and writes
//! [`files`].
//!
//! **They read nothing but the dump and the request they are given** —and
//! the map files the request names—: the converter keeps their answers in
//! its cache under the key of those, and a function that read anything else
//! would hand back a stale answer.

use crate::answer;
use crate::fail::Result;
use crate::request::Asked;
use crate::{Game, Request, ANSWER_FILE};
use serde::Serialize;
use std::collections::BTreeMap;
use std::path::Path;

/// What a command answers: every file it makes, by name.
pub type Files = BTreeMap<String, Vec<u8>>;

/// `scan`: the indices of the whole game, which pages of each map compile,
/// and each map's pages compiled without songs —see [`crate::scan`]—.
pub fn scan(data: &Path, request: &Asked) -> Result<answer::Scan> {
    let (game, request) = asked(data, request)?;
    crate::scan(&game, &request)
}

/// `compile`: every page of the cartridge —see [`crate::compile()`]—.
pub fn compile(data: &Path, request: &Asked) -> Result<answer::Compiled> {
    let (game, request) = asked(data, request)?;
    crate::compile(&game, &request)
}

/// The game in `data`, and `request` read.
fn asked(data: &Path, request: &Asked) -> Result<(Game, Request)> {
    let request = Request::from_asked(request, "the request")?;
    let game = Game::from_dump(data, request.patches.clone())?;
    Ok((game, request))
}

/// An answer as the file it is written to, on one line. Through a JSON
/// value, whose keys serde_json sorts unless the binary that links it keeps
/// their order —the converter does—: the binary's file has the keys sorted,
/// as it always had.
pub fn files(answer: &impl Serialize) -> Files {
    let value = serde_json::to_value(answer).expect("an answer is JSON");
    let text = serde_json::to_string(&value).expect("an answer is JSON") + "\n";
    Files::from([(ANSWER_FILE.to_string(), text.into_bytes())])
}
