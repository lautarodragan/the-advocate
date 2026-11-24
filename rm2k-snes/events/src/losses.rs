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
use serde::{Deserialize, Deserializer, Serialize};

/// What runs, or what a `CallEvent` pasted into it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Origin {
    /// A map's event: its page, by RM2k's number —None is the whole
    /// event—, and its cell.
    Page {
        map: i32,
        event: i32,
        page: Option<i32>,
        x: i32,
        y: i32,
    },
    /// A common event, by number.
    Common(i32),
    /// A troop's page, by RM2k's numbers: the troop, and the page from 1.
    Troop { troop: i32, page: i32 },
    /// A map event's page another page calls by number: its id and the page.
    Called { event: i32, page: i32 },
}

impl Origin {
    /// Where it is, as an entry says it.
    pub fn place(&self) -> Where {
        match *self {
            Origin::Page {
                map,
                event,
                page,
                x,
                y,
            } => Where {
                map: Some(map.into()),
                event: Some(event.into()),
                page: Some(page.map(i64::from)),
                x: Some(x.into()),
                y: Some(y.into()),
                ..Where::default()
            },
            Origin::Common(n) => Where {
                common: Some(n.into()),
                ..Where::default()
            },
            Origin::Troop { troop, page } => Where {
                troop: Some(troop.into()),
                page: Some(Some(page.into())),
                ..Where::default()
            },
            Origin::Called { event, page } => Where {
                event: Some(event.into()),
                page: Some(Some(page.into())),
                ..Where::default()
            },
        }
    }
}

/// Where a loss is, as `degradations.json` writes it: a map's event page
/// with its cell, a common event, a troop's page, a page called by number,
/// a whole map —or none of them, the whole cartridge—, and the command's
/// index. `page` and `command` can be written as null —an event left out
/// whole, a frame not yet at a command—, which is not the same as not
/// written.
///
/// **The fields go in the order the entries have always been written**,
/// every kind of place in one: the converter keeps the keys' order, and
/// `degradations.json` stays what it was.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Where {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub map: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub event: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub troop: Option<i64>,
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        deserialize_with = "written"
    )]
    pub page: Option<Option<i64>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub x: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub y: Option<i64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub common: Option<i64>,
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        deserialize_with = "written"
    )]
    pub command: Option<Option<i64>>,
}

/// A field that is written, null or not: `Some`. One that is not written
/// takes the default, `None`.
fn written<'de, D: Deserializer<'de>>(d: D) -> Result<Option<Option<i64>>, D::Error> {
    Option::<i64>::deserialize(d).map(Some)
}

/// One entry of `degradations.json`: where —and, for a loss inside a
/// common event pasted into a page, `via`, the pasted bodies with the
/// command each was at—, the command's code and name, `kind`, a stable
/// slug to count by, `text`, what is lost, and `subject`, what it is about
/// by name. `events`, for a loss of some of a map's events, their ids.
///
/// The compiler answers its losses as these, and the converter adds the
/// other stages' and its own and writes them: one type both ends see, so
/// the converter filters by field. The compiler's is the richest place of
/// all the stages', and the others' —a map, or the cartridge, a kind and a
/// text— are this with fewer fields.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Entry {
    #[serde(flatten)]
    pub place: Where,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub via: Vec<Where>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub code: Option<i32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub name: Option<String>,
    pub kind: String,
    pub text: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub subject: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub events: Vec<i64>,
}

/// How a common event a loss is in runs: its trigger —`automatic`,
/// `parallel` or `called`—, its switch if it has one, and the pages and
/// common events that call it.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct CommonRun {
    pub trigger: String,
    pub switch: Option<i32>,
    pub called_from: Vec<Where>,
}

/// The kinds someone downstream tells apart: the converter takes some of
/// them back when the conversion did on its own what was lost.
///
/// An event the RAM left out, or a page that names one.
pub const EVENT_LEFT_OUT: &str = "event-left-out";
/// A picture the map's sprite bank does not carry.
pub const PICTURE_NOT_SHOWN: &str = "picture-not-shown";
/// A `ChangePBG` to a panorama the map does not carry.
pub const PANORAMA_NOT_CHANGED: &str = "panorama-not-changed";
/// Letters a box does not draw, shown as plain ASCII: the screens say it
/// too, of the letters only they write, under the same word.
pub const LETTER_PLAIN: &str = "letter-plain";

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
    /// As `degradations.json` writes it.
    pub fn entry(&self) -> Entry {
        let place = |(origin, at): &(Origin, Option<usize>)| Where {
            command: Some(at.map(|a| a as i64)),
            ..origin.place()
        };
        Entry {
            place: self.path.first().map(place).unwrap_or_default(),
            via: self.path.iter().skip(1).map(place).collect(),
            code: self.code,
            name: self.code.map(name),
            kind: self.kind.to_string(),
            text: self.text.clone(),
            subject: self.subject.clone(),
            events: Vec::new(),
        }
    }

    /// [`Loss::entry`] as JSON, for the tests that look at one field.
    #[cfg(test)]
    pub fn to_json(&self) -> serde_json::Value {
        serde_json::to_value(self.entry()).expect("an entry is JSON")
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
        Mark {
            found: self.found.len(),
            frames: self.frames.len(),
        }
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
        self.found.push(Loss {
            path: self.frames.clone(),
            code,
            kind,
            text: text.into(),
            subject: None,
        });
    }

    /// The frames the compiler is in, with the command each one is at: to
    /// note a loss later with [`Losses::lose_on`], once it is known —a call
    /// to a page whose code is compiled after the call—.
    pub fn path(&self) -> Vec<(Origin, Option<usize>)> {
        self.frames.clone()
    }

    /// [`Losses::lose`] at a place the compiler was: see [`Losses::path`].
    pub fn lose_on(
        &mut self,
        path: Vec<(Origin, Option<usize>)>,
        code: Option<i32>,
        kind: &'static str,
        text: impl Into<String>,
    ) {
        self.found.push(Loss {
            path,
            code,
            kind,
            text: text.into(),
            subject: None,
        });
    }

    /// [`Losses::lose`], saying what it is about: see [`Loss::subject`].
    pub fn lose_about(
        &mut self,
        code: Option<i32>,
        kind: &'static str,
        text: impl Into<String>,
        subject: &str,
    ) {
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

#[cfg(test)]
mod tests {
    use super::*;

    /// A loss inside a common event pasted into a map's page, the page's
    /// number not known and the common event's command not yet reached:
    /// written in the order the entries always were, its nulls written, and
    /// read back as itself.
    #[test]
    fn an_entry_goes_and_comes_back_the_same() {
        let loss = Loss {
            path: vec![
                (
                    Origin::Page {
                        map: 3,
                        event: 7,
                        page: None,
                        x: 4,
                        y: 5,
                    },
                    Some(2),
                ),
                (Origin::Common(9), None),
            ],
            code: Some(11330),
            kind: PICTURE_NOT_SHOWN,
            text: "lost".into(),
            subject: Some("Pic".into()),
        };
        let entry = loss.entry();
        let text = serde_json::to_string(&entry).unwrap();
        assert_eq!(
            text,
            r#"{"map":3,"event":7,"page":null,"x":4,"y":5,"command":2,"via":[{"common":9,"command":null}],"code":11330,"name":"MoveEvent","kind":"picture-not-shown","text":"lost","subject":"Pic"}"#
        );
        assert_eq!(serde_json::from_str::<Entry>(&text).unwrap(), entry);
        let troop: Entry =
            serde_json::from_str(r#"{"troop":2,"page":null,"kind":"k","text":""}"#).unwrap();
        assert_eq!((troop.place.troop, troop.place.page), (Some(2), Some(None)));
        assert_eq!(troop.place.command, None);
    }
}
