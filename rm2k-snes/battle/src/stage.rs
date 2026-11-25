//! The battle as a stage of a converter: what each of its commands answers,
//! as the files it makes, by name. The converter calls these as functions
//! —`tables`, `model` and `layout`—, and the binary is a `main` over the
//! last two, which the tests ask, that reads the request and writes the
//! files into `--out`.
//!
//! **They read nothing but the dump and the request they are given**: the
//! converter keeps their answers in its cache under the key of those two,
//! and a function that read anything else would hand back a stale answer.

use crate::db::Db;
use crate::fail::Result;
use crate::model::{self, ModelRequest, MODEL_FILE};
use crate::{Game, Request, Tables};
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::Path;

/// What a command answers: every file it makes, by name.
pub type Files = BTreeMap<String, Vec<u8>>;

/// `tables`: the experience and encounter tables of the game in `data`,
/// for the cartridge `request` describes —see [`Request`]—.
pub fn tables(data: &Path, request: &Request) -> Result<Files> {
    let mut game = Game::from_dump(data)?;
    request.put_nodes("the request", &mut game)?;
    Ok(Tables::new(&game, request)?.files())
}

/// `model`: what the rest of the conversion writes of the battle.
pub fn model(data: &Path, request: &ModelRequest) -> Result<Files> {
    // The troops are most of a database: only a request that names one
    // reads them.
    let db = Db::from_dump(data, !request.troops.is_empty())?;
    Ok(one(MODEL_FILE, &model::model(&db, request)?))
}

/// One of the commands that answer a JSON from the database: `answer` asked
/// `request` about the game in `data`, as the file `name`.
pub fn asked(
    data: &Path,
    request: &Value,
    name: &str,
    answer: fn(&Db, &Value) -> Result<Value>,
) -> Result<Files> {
    // The troops are most of a database: only a request that names one
    // reads them.
    let db = Db::from_dump(data, model::needs_troops(request))?;
    Ok(one(name, &answer(&db, request)?))
}

/// `answer` as the file `name`, as every JSON of this crate is written.
fn one(name: &str, answer: &impl serde::Serialize) -> Files {
    let text = serde_json::to_string_pretty(answer).expect("an answer is JSON") + "\n";
    Files::from([(name.to_string(), text.into_bytes())])
}
