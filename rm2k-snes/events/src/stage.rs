//! The event compiler as a stage of a converter: what each of its two calls
//! answers, as the files the binary writes into `--out`, by name. The
//! converter calls these as functions —`scan` and `compile`—, and the binary
//! is a `main` over them that reads the request and writes the files.
//!
//! **They read nothing but the dump and the request they are given** —and
//! the map files the request names—: the converter keeps their answers in
//! its cache under the key of those, and a function that read anything else
//! would hand back a stale answer.

use crate::fail::Result;
use crate::{Game, Request, ANSWER_FILE};
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::Path;

/// What a command answers: every file it makes, by name.
pub type Files = BTreeMap<String, Vec<u8>>;

/// `scan`: the indices of the whole game, which pages of each map compile,
/// and each map's pages compiled without songs —see [`crate::scan`]—.
pub fn scan(data: &Path, request: &Value) -> Result<Files> {
    asked(data, request, crate::scan)
}

/// `compile`: every page of the cartridge —see [`crate::compile()`]—.
pub fn compile(data: &Path, request: &Value) -> Result<Files> {
    asked(data, request, crate::compile)
}

/// `answer` asked `request` about the game in `data`.
fn asked(
    data: &Path,
    request: &Value,
    answer: fn(&Game, &Request) -> Result<Value>,
) -> Result<Files> {
    let request = Request::from_json(request, "the request")?;
    let game = Game::from_dump(data, request.patches.clone())?;
    Ok(files(&answer(&game, &request)?))
}

/// The answer as the file it is written to, on one line.
fn files(answer: &Value) -> Files {
    let text = serde_json::to_string(answer).expect("an answer is JSON") + "\n";
    Files::from([(ANSWER_FILE.to_string(), text.into_bytes())])
}
