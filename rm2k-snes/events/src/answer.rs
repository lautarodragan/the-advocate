//! What the compiler's two calls answer, as the types its caller reads:
//! [`Scan`] and [`Compiled`]. serde writes them as the JSON the binary
//! writes into `--out`, and reads them back from the converter's cache.
//!
//! **The fields go in the order the answer always wrote them**, and the
//! ones written only when there are some are skipped the same way: the
//! converter keeps the keys' order, so the files it writes from these
//! —`degradations.json`, the emission's request— stay what they were.
//!
//! What the caller only passes on to another stage stays a JSON value
//! here: the zooms (the pictures' stage reads them), the songs (the
//! audio's), the battle's audio (the emission's) and the losses
//! (`degradations.json`'s, with every other stage's). A picture is a
//! [`PictureKey`].

use crate::pages::hex;
use crate::registry::PictureKey;
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use serde_json::{Map, Value};
use std::collections::BTreeSet;

/// Bytes, written as a string of hex pairs: how bytecode travels in an
/// answer.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Hex(pub Vec<u8>);

impl Serialize for Hex {
    fn serialize<S: Serializer>(&self, s: S) -> Result<S::Ok, S::Error> {
        s.serialize_str(&hex(&self.0))
    }
}

impl<'de> Deserialize<'de> for Hex {
    fn deserialize<D: Deserializer<'de>>(d: D) -> Result<Hex, D::Error> {
        let text = String::deserialize(d)?;
        (0..text.len())
            .step_by(2)
            .map(|i| {
                text.get(i..i + 2)
                    .and_then(|p| u8::from_str_radix(p, 16).ok())
            })
            .collect::<Option<_>>()
            .map(Hex)
            .ok_or_else(|| serde::de::Error::custom(format!("{text:?} is not hex")))
    }
}

fn is_false(b: &bool) -> bool {
    !b
}

/// The indices both calls answer, the same in both.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Indices {
    /// `(variable, slot)`; the high words of the wide variables as the
    /// variable's number negated: see `indices::wide`.
    pub variables: Vec<(i64, i64)>,
    /// `(actor, skill, slot)`.
    pub skills: Vec<(i64, i64, i64)>,
    /// The highest switch the game names: the cartridge's table holds it.
    pub switch_top: i64,
    /// The switch the test pages can turn on, if they asked.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub test_switch: Option<i64>,
    /// The names `ChangeHeroName` gives, `(actor, name)`, in the order
    /// `OP_CHANGE_NAME` counts them.
    pub names: Vec<(i64, String)>,
    /// The faces the message window shows, `(FaceSet, index, mirrored)`, in
    /// the order `OP_FACE` counts them.
    pub faces: Vec<(String, i64, bool)>,
    pub associations: Vec<(String, i32)>,
}

/// One page of a map, as the console's page table needs it. What it draws
/// is the caller's.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Page {
    /// The event's and the page's indices in the map, not their ids.
    pub event: usize,
    pub page: usize,
    pub trigger: i32,
    pub switch_a: i32,
    pub switch_b: i32,
    pub actor: i32,
    /// `(slot, comparison, value)`, or the timer's in the variable's place:
    /// see `TIMER_SLOT`.
    pub variable: Option<(i64, i64, i64)>,
    pub item: i32,
    pub layer: i32,
    pub frequency: i32,
    pub speed: i32,
    pub route_targets: Vec<usize>,
    pub route_graphics: Vec<[usize; 2]>,
    pub route_turns: Vec<usize>,
    /// None if it does not compile.
    pub code: Option<Hex>,
    pub own_route: Option<OwnRoute>,
    pub turns: bool,
    pub pure: bool,
}

/// A page's own move route: see [`crate::route::own`].
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct OwnRoute {
    pub commands: Vec<i32>,
    pub frequency: i32,
    pub speed: i32,
    pub repeats: bool,
    pub skippable: bool,
    pub fixed_direction: bool,
    pub animation_continues: bool,
    /// Only on the one that spins, with its pattern.
    #[serde(default, skip_serializing_if = "is_false")]
    pub spin: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pattern: Option<i32>,
    /// Only on the one that walks by a type.
    #[serde(default, skip_serializing_if = "is_false")]
    pub by_type: bool,
}

/// The first call's answer: see [`crate::scan`].
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Scan {
    #[serde(flatten)]
    pub indices: Indices,
    pub maps: Vec<ScanMap>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub commons_pictures: Vec<CommonPictures>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub common_sets: Vec<CommonSet>,
}

impl Scan {
    /// A map's entry.
    pub fn map(&self, id: i32) -> Option<&ScanMap> {
        self.maps.iter().find(|m| m.id == id)
    }
}

/// A map in the scan.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct ScanMap {
    pub id: i32,
    /// `(event, page, code)` of each page that compiles on its own.
    pub compiled: Vec<(usize, usize, Hex)>,
    pub pages: Vec<Page>,
    /// The route graphics, `(CharSet, index)`, in the order the bytecode
    /// numbers them.
    pub graphics: Vec<(String, i64)>,
    /// The picture keys its pages and test pages can show.
    pub pictures: Vec<PictureKey>,
    /// `[number, zoom]` of each `MovePicture` that zooms.
    pub zooms: Vec<Value>,
    /// The numbers it tones.
    pub tinted: Vec<i64>,
    /// How many of `pictures` are its own, before the copies': only on a
    /// map with copies.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pictures_own: Option<usize>,
    /// Which of `graphics` a route gives an event.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub graphics_on_events: Vec<(String, i64)>,
}

/// The pictures a common event that runs anywhere can show.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommonPictures {
    pub common: i32,
    pub pictures: Vec<PictureKey>,
    pub zooms: Vec<Value>,
}

/// A set of the common events' small pictures: see
/// [`crate::commons::picture_sets`].
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CommonSet {
    pub parallel: bool,
    pub commons: Vec<i32>,
    pub pictures: Vec<PictureKey>,
    pub tinted: Vec<i64>,
}

/// The second call's answer: see [`crate::compile()`].
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Compiled {
    #[serde(flatten)]
    pub indices: Indices,
    pub degradations: Degradations,
    pub maps: Vec<CompiledMap>,
    /// Each test page's code, None if it does not compile.
    pub cases: Vec<Option<Hex>>,
    pub messages: Messages,
    pub songs: Value,
    pub troops: Troops,
    pub troop_pages: TroopPages,
    pub battle_audio: Value,
    /// `(number, switch, pure, code)` of each parallel common event; no
    /// code if it does not compile.
    pub parallel_commons: Vec<(i32, i32, bool, Option<Hex>)>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub commons: Option<Shared>,
}

impl Compiled {
    /// A map's entry.
    pub fn map(&self, id: i32) -> Option<&CompiledMap> {
        self.maps.iter().find(|m| m.id == id)
    }
}

/// Every loss, and how the common events they are in run: see
/// [`crate::losses`].
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Degradations {
    pub losses: Vec<Value>,
    pub commons: Map<String, Value>,
}

/// A map in the compilation.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct CompiledMap {
    pub id: i32,
    pub pages: Vec<Page>,
    /// The route graphics the pages numbered against.
    pub graphics: Vec<(String, i64)>,
    /// The commands its automatic pages accept without doing.
    pub debts: BTreeSet<i32>,
    /// `(upper, old, new)` of each substitution its pages asked for.
    pub substitutions: Vec<(bool, i64, i64)>,
    /// The route graphics the table had no room for.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub graphics_dropped: Vec<(String, i64)>,
}

/// The text block.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Messages {
    pub data: Hex,
    pub count: usize,
    pub pairs: Hex,
    pub pair_first: u8,
    /// The Latin-1 letters the boxes draw, in the order of their indices
    /// from 96 on.
    pub letters: Vec<String>,
}

/// The troops the battles ask for, and the backdrop each one names, if
/// it names one.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Troops {
    pub ids: Vec<i32>,
    pub backdrops: Vec<(i32, Option<String>)>,
}

/// The troops' pages: see [`crate::troops::TroopPages`].
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct TroopPages {
    pub pages: usize,
    pub left_out: usize,
    pub distinct: usize,
    /// Per troop, each page that got in: its trigger as `BA_COND` reads it
    /// —see `Trigger::row`—, where its code is and which page it is.
    pub per_troop: Vec<(i32, Vec<([i32; 13], usize, usize)>)>,
    pub code: Hex,
    pub messages: Hex,
    pub message_count: usize,
    /// Per command they accept without doing, `(troop, page)` of each.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub debts: Vec<(i32, Vec<(i32, usize)>)>,
}

/// The shared common event bodies: see [`crate::commons::Shared`].
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Shared {
    pub bodies: Vec<(i32, Hex)>,
    pub autostart: Vec<(i32, u8)>,
    pub depth: Option<usize>,
    pub left_out: Vec<i32>,
    pub menu_before: Vec<(i32, u8)>,
}
