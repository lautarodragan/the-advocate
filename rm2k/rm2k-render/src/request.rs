//! A request of the subcommands that draw a list of pictures —`face`,
//! `system`, `picture`—: a JSON list with an entry per picture, and picture
//! `i` is written as `<i>.png`. Reading an entry's fields, with the message
//! that says which one is wrong, and writing what was drawn, is the same
//! for all of them.

use crate::fail::{Bad, Result};
use crate::picture::{self, Picture};
use serde_json::Value;
use std::collections::HashMap;
use std::path::{Path, PathBuf};

/// The entries of a request, and where its relative paths start.
pub struct Request {
    pub entries: Vec<Value>,
    base: PathBuf,
    whose: String,
}

impl Request {
    /// Reads the request at `path`. A request that is not a JSON list is
    /// answered no; one that cannot be read is the call being wrong.
    pub fn read(path: &Path) -> Result<Request> {
        let text = std::fs::read_to_string(path)
            .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
        let whose = path.display().to_string();
        let data: Value =
            serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{whose}: {e}")))?;
        let Value::Array(entries) = data else {
            return Err(Bad::answer(format!("{whose}: not a list")));
        };
        Ok(Request {
            entries,
            base: path.parent().unwrap_or(Path::new("")).to_path_buf(),
            whose,
        })
    }

    /// "Entry `i` is wrong", as an answer no.
    pub fn bad(&self, i: usize, what: impl std::fmt::Display) -> Bad {
        Bad::answer(format!("{}: entry {i}: {what}", self.whose))
    }

    /// The path in `key`, relative to the request's directory.
    pub fn file(&self, i: usize, key: &str) -> Result<PathBuf> {
        match self.entries[i].get(key) {
            Some(Value::String(s)) => Ok(self.base.join(s)),
            Some(_) => Err(self.bad(i, format!("`{key}` is not a path"))),
            None => Err(self.bad(i, format!("`{key}` is missing"))),
        }
    }

    /// The whole number in `key`, which has to be there.
    pub fn number(&self, i: usize, key: &str) -> Result<i64> {
        self.entries[i]
            .get(key)
            .and_then(Value::as_i64)
            .ok_or_else(|| self.bad(i, format!("`{key}` is not a number")))
    }

    /// The whole number in `key`, or `default` when it is not there.
    pub fn number_or(&self, i: usize, key: &str, default: i64) -> Result<i64> {
        match self.entries[i].get(key) {
            None => Ok(default),
            Some(_) => self.number(i, key),
        }
    }

    /// The whole number in `key`, which has to be in `range`.
    pub fn number_in(
        &self,
        i: usize,
        key: &str,
        default: Option<i64>,
        range: std::ops::Range<i64>,
    ) -> Result<i64> {
        let n = match default {
            Some(d) => self.number_or(i, key, d)?,
            None => self.number(i, key)?,
        };
        if !range.contains(&n) {
            return Err(self.bad(
                i,
                format!(
                    "`{key}` is {n}, and it goes from {} to {}",
                    range.start,
                    range.end - 1
                ),
            ));
        }
        Ok(n)
    }

    /// The boolean in `key`, or false when it is not there.
    pub fn flag(&self, i: usize, key: &str) -> Result<bool> {
        match self.entries[i].get(key) {
            None => Ok(false),
            Some(Value::Bool(b)) => Ok(*b),
            Some(_) => Err(self.bad(i, format!("`{key}` is not true or false"))),
        }
    }

    /// The string in `key`, which has to be there.
    pub fn text(&self, i: usize, key: &str) -> Result<&str> {
        self.entries[i]
            .get(key)
            .and_then(Value::as_str)
            .ok_or_else(|| self.bad(i, format!("`{key}` is missing or not a string")))
    }
}

/// The pictures a request reads, each read once however many entries
/// share it. `read` says how: with the colour key or without.
pub struct Files {
    read: fn(&Path) -> Result<Picture>,
    seen: HashMap<PathBuf, Picture>,
}

impl Files {
    pub fn new(read: fn(&Path) -> Result<Picture>) -> Self {
        Files {
            read,
            seen: HashMap::new(),
        }
    }

    pub fn get(&mut self, path: &Path) -> Result<&Picture> {
        if !self.seen.contains_key(path) {
            let picture = (self.read)(path)?;
            self.seen.insert(path.to_path_buf(), picture);
        }
        Ok(&self.seen[path])
    }
}

/// Draws entry `i` of `request` with `draw`, for every entry, and writes it
/// as `<i>.png` into `dir`, which is created if it is not there. **Every
/// entry is checked and drawn before the first file is written**: a
/// request with a bad entry leaves nothing half done.
pub fn write(
    dir: &Path,
    request: &Request,
    mut draw: impl FnMut(&Request, usize) -> Result<Picture>,
) -> Result<()> {
    let drawn = (0..request.entries.len())
        .map(|i| draw(request, i))
        .collect::<Result<Vec<_>>>()?;
    std::fs::create_dir_all(dir).map_err(|e| Bad::usage(format!("{}: {e}", dir.display())))?;
    for (i, picture) in drawn.iter().enumerate() {
        picture::write_png(&dir.join(format!("{i}.png")), picture)?;
    }
    Ok(())
}
