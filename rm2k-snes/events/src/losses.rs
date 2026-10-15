//! What the cartridge does with less than RM2k: each command accepted
//! without being done, or done without part of what it asks for, noted
//! **where it is compiled**, so the list is complete by construction and
//! not kept by hand.
//!
//! A page that is left out whole is not here: that is `culprits`. This is
//! the other kind, a page that runs and is missing something —a fade-in, a
//! route that should repeat, an animation not drawn—. Each loss is a
//! `kind`, a stable slug the converter and whoever reads its list can
//! count by, and a line of text that says what is lost.
//!
//! **Where** is a stack, because a `CallEvent` pastes the body it calls
//! into the page: the outermost frame is what runs —a map's page, a common
//! event's shared body, a troop's page— and the inner ones the bodies
//! pasted into it, each with the index of its command. A page that does
//! not compile takes its losses back, as it takes its texts back —see
//! `judged_page`—, so what is listed is what reaches the cartridge.

use ditto::schema::EventCommandCode;
use serde_json::{json, Value};

/// What runs, or what a `CallEvent` pasted into it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Origin {
    /// A map's event: its page, by RM2k's number —None is the whole
    /// event—, and its cell.
    Page { map: i32, event: i32, page: Option<i32>, x: i32, y: i32 },
    /// A common event, by number.
    Common(i32),
    /// A troop's page, by RM2k's numbers: the troop, and the page from 1.
    Troop { troop: i32, page: i32 },
    /// A map event's page another page calls by number: its id and the page.
    Called { event: i32, page: i32 },
}

impl Origin {
    fn to_json(&self) -> Value {
        match self {
            Origin::Page { map, event, page, x, y } => {
                json!({"map": map, "event": event, "page": page, "x": x, "y": y})
            }
            Origin::Common(n) => json!({"common": n}),
            Origin::Troop { troop, page } => json!({"troop": troop, "page": page}),
            Origin::Called { event, page } => json!({"event": event, "page": page}),
        }
    }
}

/// One loss: the frames it is under, with the command each one was at.
#[derive(Debug, Clone)]
pub struct Loss {
    pub path: Vec<(Origin, Option<usize>)>,
    pub code: Option<i32>,
    pub kind: &'static str,
    pub text: String,
    /// What it is about, by name, when someone downstream has to tell it
    /// apart: a picture's, which the converter may have drawn into the map.
    pub subject: Option<String>,
}

impl Loss {
    pub fn to_json(&self) -> Value {
        let mut out = match self.path.first() {
            Some((origin, _)) => origin.to_json(),
            None => json!({}),
        };
        if let Some((_, at)) = self.path.first() {
            out["command"] = json!(at);
        }
        if self.path.len() > 1 {
            out["via"] = json!(self
                .path
                .iter()
                .skip(1)
                .map(|(o, at)| {
                    let mut v = o.to_json();
                    v["command"] = json!(at);
                    v
                })
                .collect::<Vec<_>>());
        }
        if let Some(code) = self.code {
            out["code"] = json!(code);
            out["name"] = json!(name(code));
        }
        out["kind"] = json!(self.kind);
        out["text"] = json!(self.text);
        if let Some(subject) = &self.subject {
            out["subject"] = json!(subject);
        }
        out
    }
}

/// A command's name as liblcf spells it, or its number.
pub fn name(code: i32) -> String {
    EventCommandCode::from_i32(code)
        .json_name()
        .map_or_else(|| code.to_string(), str::to_string)
}

/// Where the compiler is, and what it found lost there.
#[derive(Debug, Clone, Default)]
pub struct Losses {
    frames: Vec<(Origin, Option<usize>)>,
    pub found: Vec<Loss>,
}

/// How far to take back: see [`Losses::mark`].
#[derive(Debug, Clone, Copy)]
pub struct Mark {
    found: usize,
    frames: usize,
}

impl Losses {
    /// Into a page, or a body pasted into one.
    pub fn enter(&mut self, origin: Origin) {
        self.frames.push((origin, None));
    }

    pub fn leave(&mut self) {
        self.frames.pop();
    }

    /// The command the innermost frame is at.
    pub fn at(&mut self, i: usize) {
        if let Some(top) = self.frames.last_mut() {
            top.1 = Some(i);
        }
    }

    pub fn mark(&self) -> Mark {
        Mark { found: self.found.len(), frames: self.frames.len() }
    }

    /// Back to `mark`: what was found after it was in a page that does not
    /// run, or in a compilation that was only a question.
    pub fn rewind(&mut self, mark: Mark) {
        self.found.truncate(mark.found);
        self.frames.truncate(mark.frames);
    }

    /// Notes a loss where the compiler is. Outside any frame —a test, the
    /// scan's questions— it is noted without a place, and nobody reads it.
    pub fn lose(&mut self, code: Option<i32>, kind: &'static str, text: impl Into<String>) {
        self.found.push(Loss { path: self.frames.clone(), code, kind, text: text.into(), subject: None });
    }

    /// [`Losses::lose`], saying what it is about: see [`Loss::subject`].
    pub fn lose_about(&mut self, code: Option<i32>, kind: &'static str, text: impl Into<String>, subject: &str) {
        self.lose(code, kind, text);
        self.found.last_mut().unwrap().subject = Some(subject.to_string());
    }

    /// The command indices of the outermost frame through `index`: a troop
    /// page's boxes are rebuilt before compiling, so its indices are the
    /// rebuilt list's and not RM2k's.
    pub fn reindex_from(&mut self, mark: Mark, index: impl Fn(usize) -> usize) {
        for loss in &mut self.found[mark.found..] {
            if let Some((_, Some(at))) = loss.path.first_mut() {
                *at = index(*at);
            }
        }
    }

    pub fn take(&mut self) -> Vec<Loss> {
        std::mem::take(&mut self.found)
    }
}
