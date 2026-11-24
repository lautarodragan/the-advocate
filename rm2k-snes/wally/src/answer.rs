//! What [`crate::stage::map`] answers of a map, as types: `map.json` is a
//! [`Map`], `layers.json` a [`Layers`], and the binaries they name go
//! beside them, by name. Wally builds these and serde writes them; the
//! converter reads them back with [`Answer::read`] —a field renamed here
//! does not compile there—.
//!
//! **The fields are in the files' key order**, which is what the
//! conversion cache keeps: reordering a field changes the cached answers'
//! bytes, not what the converter makes of them. Some of these types the
//! emission's request holds as they are —a slot's owner, a route's graphic,
//! the cache, the shared slots, the battle animation's box, a still event
//! drawn into the cells—, and the rest the converter turns into the
//! emission's with plain Rust, where the emission takes the bytes of the
//! files these name: see `emit.rs` in rm2k-snes-convert.

use crate::fail::{Bad, Result};
use crate::sprites::character::Key;
use crate::sprites::npc::Npc;
use crate::stage::Files;
use adeleine::Color;
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;

/// Both files of a map's answer, read.
pub struct Answer {
    pub map: Map,
    pub layers: Layers,
}

impl Answer {
    /// The two files of `files`, which is what [`crate::stage::map`]
    /// answered.
    pub fn read(files: &Files) -> Result<Answer> {
        Ok(Answer {
            map: read(files, crate::map::ANSWER_FILE)?,
            layers: read(files, crate::layers::ANSWER_FILE)?,
        })
    }
}

fn read<T: for<'de> Deserialize<'de>>(files: &Files, name: &str) -> Result<T> {
    let bytes = files
        .get(name)
        .ok_or_else(|| Bad::answer(format!("no {name} in the answer")))?;
    serde_json::from_slice(bytes).map_err(|e| Bad::answer(format!("{name}: {e}")))
}

/// `map.json`: everything of the map but its layers.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Map {
    /// The events painted into the background, by index: no longer events.
    pub decorative: Vec<usize>,
    /// The events the RAM's trim left out that are painted in, by RM2k id.
    pub painted_trimmed: Vec<i32>,
    /// Each event baked into the layers: its index, its CharSet index and
    /// its tile.
    pub baked: Vec<(usize, usize, i32)>,
    /// What the conversion said, in order.
    pub notes: Vec<Note>,
    /// The table of drawn events: the objects' rows, then the still ones
    /// drawn into the background's cells.
    pub npcs: Vec<Row>,
    pub posed: Vec<crate::posed::Placed>,
    pub palette_cap: usize,
    /// The hero's cell.
    pub start: (i32, i32),
    /// The objects, as the sprite bank carries them.
    pub sprite: Option<Sprite>,
    pub movable: BTreeSet<usize>,
    pub animates_still: BTreeSet<usize>,
    /// The still ones that animate in another one's slot: `(event, whose)`.
    pub animates_with: Vec<(usize, usize)>,
    pub substitutions: Substitutions,
    /// The ones that turn toward the hero, with the graphics they turn.
    pub turning: Vec<(usize, Vec<Key>)>,
    /// Whether the pictures that went in are the map's own and not the
    /// copied common events' too: see [`crate::map::MapRequest`]. Only
    /// written when it is so.
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub pictures_own: bool,
}

/// Which way a [`Note`] goes.
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum Kind {
    /// Said, and the conversion goes on.
    #[default]
    Note,
    /// An event left undrawn: said, or the build stops if it is a
    /// mechanism (`stop`).
    Discard,
    /// The map cannot be converted.
    Stop,
}

/// A note of the conversion, and what the map lost, if it says a loss.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Note {
    pub kind: Kind,
    pub text: String,
    pub stop: bool,
    #[serde(flatten)]
    pub loss: Option<Loss>,
}

/// What a [`Note`] says the map lost: a stable slug and the events it is
/// about, by RM2k id.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Loss {
    pub loss: String,
    pub events: Vec<i32>,
}

/// A row of the table of drawn events, and for one drawn into the
/// background's cells, its number among those and the graphic it starts
/// with.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Row {
    #[serde(flatten)]
    pub npc: Npc,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub posed: Option<(usize, usize)>,
}

/// The objects: what the sprite bank and its tables carry.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Sprite {
    /// The file of the bank's tiles.
    pub tiles: String,
    pub palettes: Vec<Vec<Color>>,
    /// Each slot: whose it is, its block and its palette.
    pub place: Vec<(Slot, usize, usize)>,
    /// Per leader candidate: its palette, its pose bank and its colours.
    pub actors: Vec<(i32, usize, Option<usize>, Vec<u16>)>,
    pub timer: Option<(usize, usize)>,
    pub timer_mask: u16,
    pub animated: Vec<Key>,
    pub animated_palettes: Vec<usize>,
    pub banks: Vec<Bank>,
    pub route_gfx: Vec<RouteGraphic>,
    pub rain: (usize, usize),
    pub sand: Option<(usize, usize, usize)>,
    pub turn_block: Option<usize>,
    /// The pictures' first tile and palette; 0 if none went in.
    pub image: (usize, usize),
    pub animation: Option<Animation>,
    pub characters: usize,
    pub shared: Option<crate::map::SharedObjects>,
    pub cache: Option<Cache>,
}

/// A character's twelve poses: its CharSet and index, the file of their
/// tiles, and which of them the map can show.
pub type Bank = (String, i32, String, BTreeSet<i32>);

/// Whose a slot of the sprite bank is, as [`crate::sprites::bank::Slot`],
/// written as an object whose key says which.
#[derive(Clone, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Slot {
    Hero {
        hero: bool,
    },
    Event {
        event: usize,
    },
    Still {
        charset: String,
        index: i32,
        pose: i32,
    },
    Turn {
        turn: bool,
    },
    Shared {
        shared: usize,
    },
    Cache {
        cache: usize,
    },
}

impl From<&crate::sprites::bank::Slot> for Slot {
    fn from(slot: &crate::sprites::bank::Slot) -> Self {
        use crate::sprites::bank::Slot as S;
        match slot {
            S::Hero => Slot::Hero { hero: true },
            S::Event(event) => Slot::Event { event: *event },
            S::Still(charset, index, pose) => Slot::Still {
                charset: charset.clone(),
                index: *index,
                pose: *pose,
            },
            S::Turn => Slot::Turn { turn: true },
            S::Shared(shared) => Slot::Shared { shared: *shared },
            S::Cache(cache) => Slot::Cache { cache: *cache },
        }
    }
}

/// A graphic of command 34: its entry in the pose table or $FF, its
/// palette, and the colours the console uploads when the hero takes it, if
/// it uploads any.
#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(untagged)]
pub enum RouteGraphic {
    Uploads(usize, usize, Vec<u16>),
    Plain(usize, usize),
}

impl RouteGraphic {
    /// Its entry in the pose table, or $FF.
    pub fn entry(&self) -> usize {
        match self {
            RouteGraphic::Uploads(k, ..) | RouteGraphic::Plain(k, _) => *k,
        }
    }

    pub fn palette(&self) -> usize {
        match self {
            RouteGraphic::Uploads(_, p, _) | RouteGraphic::Plain(_, p) => *p,
        }
    }

    /// The colours the console uploads into the leaders' palette when the
    /// hero takes it; none for one with a palette of its own in the map.
    pub fn colors(&self) -> &[u16] {
        match self {
            RouteGraphic::Uploads(_, _, c) => c,
            RouteGraphic::Plain(..) => &[],
        }
    }
}

/// The box battle animations are drawn in: how many tiles the map spends,
/// its first tile and its palette.
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct Animation {
    pub count: usize,
    pub base: usize,
    pub palette: usize,
}

/// The cache of slots, as [`crate::map::CacheObjects`], with the still ones
/// routes only turn.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Cache {
    pub events: Vec<(usize, Option<usize>, usize)>,
    /// Each still pose: its CharSet, index and pose, its character's entry
    /// in the pose table and its palette.
    pub stills: Vec<(String, i32, i32, usize, usize)>,
    pub slots: Vec<usize>,
    pub turners: BTreeSet<usize>,
}

/// Each substitution the map can run, `(upper, old, new)` with its block
/// pairs, and the ones whose blocks could not be built.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Substitutions {
    pub table: Vec<(bool, i32, i32, Option<Vec<(u16, u16)>>)>,
    pub missing: Vec<(bool, i32, i32)>,
}

/// `layers.json`: the two background layers, the panorama and the blocks.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Layers {
    pub panorama: Option<Panorama>,
    /// How it shows its panorama, by [`crate::background::panorama::Way`]'s
    /// name.
    pub panorama_way: Option<String>,
    pub panorama_tried: Vec<String>,
    /// Each picture a `ChangePBG` names that the map does not carry, and
    /// why.
    pub panorama_dropped: Vec<(String, String)>,
    pub panorama_unseen: bool,
    pub panorama_above_lost: usize,
    pub pictures_in_front: Option<InFront>,
    pub background: Background,
    pub above: Above,
    pub pictures: Vec<Picture>,
    pub passability: Vec<u8>,
    pub blocks: Blocks,
}

/// The panorama the map shows, converted, and the others its `ChangePBG`s
/// swap in.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Panorama {
    pub images: Vec<PanoramaImage>,
    pub none_first: bool,
    pub name: String,
    pub mode: u8,
    pub size: (usize, usize),
    pub stretch: (usize, usize),
    #[serde(rename = "loop")]
    pub looped: (bool, bool),
    pub auto: (i32, i32),
    pub tiles: usize,
    pub tilemap: Vec<Vec<u16>>,
    pub first: usize,
    pub cgram: Vec<u16>,
    pub backdrop: Option<u16>,
    pub distinct: usize,
    pub colors: usize,
    pub kept: usize,
    pub merges: Vec<Merge>,
    pub above_bg1: bool,
}

/// Another picture a `ChangePBG` swaps in, with the file of its tiles.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct PanoramaImage {
    pub name: String,
    pub size: (usize, usize),
    pub stretch: (usize, usize),
    pub tiles: usize,
    pub file: String,
    pub tilemap: Vec<Vec<u16>>,
    pub first: usize,
    pub cgram: Vec<u16>,
    pub backdrop: Option<u16>,
    pub distinct: usize,
    pub colors: usize,
    pub kept: usize,
    pub merges: Vec<Merge>,
}

/// The map's pictures' pixels in front of the hero, and how many of them
/// are on the wrong side of him.
#[derive(Clone, Copy, Debug, Serialize, Deserialize)]
pub struct InFront {
    pub wrong: usize,
    pub pixels: usize,
}

/// The layer behind the hero; its tiles are a file of their own.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Background {
    pub bpp: usize,
    pub tiles: usize,
    pub cgram: Vec<u16>,
    pub tilemap: Vec<Vec<u16>>,
    pub colors: usize,
    pub used: usize,
    pub budget: usize,
    pub merges: Vec<Merge>,
    pub cells: usize,
    pub runs: Vec<Run>,
}

/// One family of the ChipSet's animation, each drawing a file.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Run {
    pub family: String,
    pub base: usize,
    pub tiles: usize,
    pub drawings: Vec<String>,
}

/// The layer in front of the hero; its tiles and colours are files.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Above {
    pub tilemap: Vec<Vec<u16>>,
    pub first: usize,
    pub merges: Vec<Merge>,
}

/// What Adeleine decided, as a picture: `background`, `above`, `panorama`
/// or a family's drawing, and its PNG's file.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Picture {
    pub name: String,
    pub file: String,
}

/// The map in blocks; the table is a file.
#[derive(Clone, Debug, Serialize, Deserialize)]
pub struct Blocks {
    pub cells: Vec<u16>,
    /// Which block each `(lower tile, upper tile)` pair ended up in.
    pub combos: Vec<(i32, i32, u16)>,
}

/// A colour change, as [`crate::background::Merge`]: a palette-local one
/// says its palette first.
#[derive(Clone, Debug, PartialEq, Eq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Merge {
    Local(usize, Color, Color, u64),
    Global(Color, Color, u64),
}

impl From<&crate::background::Merge> for Merge {
    fn from(m: &crate::background::Merge) -> Self {
        match m.palette {
            Some(palette) => Merge::Local(palette, m.victim, m.target, m.pixels),
            None => Merge::Global(m.victim, m.target, m.pixels),
        }
    }
}

/// Each merge of `merges`, as the answer says them.
pub fn merges(merges: &[crate::background::Merge]) -> Vec<Merge> {
    merges.iter().map(Merge::from).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The untagged ones read back as what they were written as.
    #[test]
    fn the_shapes_read_back_as_written() {
        let slots = vec![
            Slot::Hero { hero: true },
            Slot::Event { event: 3 },
            Slot::Still {
                charset: "Hero".into(),
                index: 1,
                pose: 7,
            },
            Slot::Turn { turn: true },
            Slot::Shared { shared: 2 },
            Slot::Cache { cache: 0 },
        ];
        let text = serde_json::to_string(&slots).unwrap();
        assert_eq!(
            text,
            r#"[{"hero":true},{"event":3},{"charset":"Hero","index":1,"pose":7},{"turn":true},{"shared":2},{"cache":0}]"#
        );
        assert_eq!(serde_json::from_str::<Vec<Slot>>(&text).unwrap(), slots);
        let merges = vec![
            Merge::Local(2, [1, 2, 3], [4, 5, 6], 9),
            Merge::Global([1, 2, 3], [4, 5, 6], 9),
        ];
        let text = serde_json::to_string(&merges).unwrap();
        assert_eq!(text, "[[2,[1,2,3],[4,5,6],9],[[1,2,3],[4,5,6],9]]");
        assert_eq!(serde_json::from_str::<Vec<Merge>>(&text).unwrap(), merges);
        let routes = vec![
            RouteGraphic::Plain(1, 2),
            RouteGraphic::Uploads(1, 2, vec![5]),
        ];
        let text = serde_json::to_string(&routes).unwrap();
        assert_eq!(text, "[[1,2],[1,2,[5]]]");
        let back: Vec<RouteGraphic> = serde_json::from_str(&text).unwrap();
        assert_eq!(serde_json::to_string(&back).unwrap(), text);
    }

    /// A note says its loss only when it has one.
    #[test]
    fn a_note_without_a_loss_says_none() {
        let note = Note {
            kind: Kind::Discard,
            text: "x".into(),
            stop: false,
            loss: None,
        };
        let text = serde_json::to_string(&note).unwrap();
        assert_eq!(text, r#"{"kind":"discard","text":"x","stop":false}"#);
        assert!(serde_json::from_str::<Note>(&text).unwrap().loss.is_none());
        let lost = Note {
            loss: Some(Loss {
                loss: "event-not-drawn".into(),
                events: vec![4],
            }),
            ..note
        };
        let text = serde_json::to_string(&lost).unwrap();
        assert_eq!(
            text,
            r#"{"kind":"discard","text":"x","stop":false,"loss":"event-not-drawn","events":[4]}"#
        );
        assert_eq!(
            serde_json::from_str::<Note>(&text)
                .unwrap()
                .loss
                .unwrap()
                .events,
            [4]
        );
    }
}
