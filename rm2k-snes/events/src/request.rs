//! The request both calls read, as the caller writes it: [`Asked`]. The
//! converter builds it as this type and the compiler reads it back with
//! serde, so a field renamed on one side does not compile on the other.
//! [`crate::Request`] is what the compiler makes of it —the windows
//! measured, the pictures sorted by plane, the tables keyed for lookup—.
//!
//! **The fields go in the order the request file writes them**, which is
//! the order the converter used to insert them by hand: the file the
//! converter leaves beside the cartridge, `events-request.json`, is the
//! same byte for byte, and what `rm2k-snes-events culprits` read until
//! 2026-11-27.

use crate::game::Command;
use crate::registry::PictureKey;
use serde::de::{Deserializer, MapAccess, Visitor};
use serde::ser::{SerializeMap, Serializer};
use serde::{Deserialize, Serialize};
use std::marker::PhantomData;
use std::path::PathBuf;

/// A request, for `scan` or for `compile`: one type, because most of it is
/// the same. What only one of the calls reads is optional, and a request
/// leaves out what it does not say. The ones every request carries are
/// required.
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Asked {
    /// The maps read from the project's files and not from the dump.
    pub map_files: ByMap<PathBuf>,
    /// The events each map leaves out: see `Patches::dropped`. Not
    /// required: a request that leaves nothing out does not have to say it.
    #[serde(default, rename = "dropped_events")]
    pub dropped: ByMap<Vec<i32>>,
    /// See `Patches::boxed_exits`.
    #[serde(default, skip_serializing_if = "ByMap::is_empty")]
    pub boxed_exits: ByMap<Vec<i32>>,
    /// The text boxes rebuilt for the console's window, as `rm2k-snes-screens
    /// boxes` answers them.
    pub boxes: Vec<MessageBox>,
    /// The graphics that go by another name: `(map, event, page, name)`.
    pub names: Vec<(i32, i32, i32, String)>,
    pub window: Window,
    /// The battle's: see [`crate::Request::troop_window`].
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub troop_window: Option<Window>,
    pub maps: Vec<i32>,
    pub test_commands: Vec<Command>,
    pub extra_variables: Vec<i32>,
    #[serde(default)]
    pub extra_switches: Vec<i32>,
    /// Null when the cartridge has no test pages.
    pub test_event_map: Option<i32>,
    /// Each custom menu, in the order the cartridge numbers them.
    #[serde(default)]
    pub menus: Vec<MenuHooks>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub common_pages: Option<CommonPages>,
    /// The pictures of the common events without a map: the big ones, then
    /// the small ones of the common table. See
    /// [`crate::Request::common_pictures`].
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub common_pictures: Vec<Picture>,
    /// Each set of the common table kept, by its index.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub common_sets: Vec<CommonSet>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub systems: Vec<String>,
    // What only `compile` reads, but for `counters`, `cases`,
    // `messages_step` and `test_switch`, which the scan reads too.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub substitutions: Option<ByMap<Vec<Substitution>>>,
    /// Per map, the pictures it carries: see [`crate::Request::pictures`].
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub pictures: Option<ByMap<Vec<Picture>>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub route_graphics: Option<ByMap<Vec<(String, i32)>>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub panoramas: Option<ByMap<Vec<String>>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tilesets: Option<ByMap<Vec<i32>>>,
    /// `[events] counters`: see `Patches::counters`.
    #[serde(default)]
    pub counters: Vec<Counter>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub sound_effects: Option<SoundEffects>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cases: Option<Vec<Case>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub test_graphics: Option<ByMap<Vec<(String, i32)>>>,
    /// 1 if it does not say.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub messages_step: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub encounter_troops: Option<Vec<i32>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub test_switch: Option<i32>,
}

/// A text box the port rebuilds: its lines as they are in the dump, and
/// the boxes that go in their place.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct MessageBox {
    pub from: Vec<String>,
    pub to: Vec<Vec<String>>,
}

/// A message window: `width`, a line's pixels, `lines`, and `advances`,
/// the advance of each glyph of the console's font from the space on; or,
/// without `width`, `columns` letters of RM2k's fixed-width font, which is
/// how it was asked until 2026-10-03. And, optional, `letters`: the Latin-1
/// letters the font draws, each a pair of the letter and its advance —see
/// `Font::latin_letters`—, and after them the halves of the ExFont's icons.
/// See [`crate::Request::from_asked`], which checks them.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Window {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub width: Option<usize>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub columns: Option<usize>,
    pub lines: usize,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub advances: Option<Vec<u8>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub letters: Option<Vec<(char, usize)>>,
}

/// What a custom menu asks of the events: see `Patches::menus`.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct MenuHooks {
    #[serde(default)]
    pub replaces_common: Option<i32>,
    #[serde(default)]
    pub before: Vec<i32>,
}

/// The automatic common events copied into maps, and into which: see
/// [`crate::Request::common_pages`].
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct CommonPages {
    pub commons: Vec<i32>,
    pub maps: Vec<i32>,
}

/// A set of the common table: whether its bodies are parallel ones', and
/// their numbers. See [`crate::Request::common_sets`].
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct CommonSet {
    pub parallel: bool,
    pub commons: Vec<i32>,
}

/// A `TileSubstitution` as the map's blocks translate it: see
/// `SubstitutionTable`. `pairs` is null for one that cannot be built.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Substitution {
    pub upper: bool,
    pub old: i64,
    pub new: i64,
    pub pairs: Option<Vec<(i64, i64)>>,
}

/// One of `[events] counters`: the common event, and the variable its
/// digits show.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Counter {
    pub common_event: i32,
    pub variable: i32,
}

/// `[sound_effects]`, the part the compiler reads: see [`SoundSettings`].
///
/// [`SoundSettings`]: crate::compile::SoundSettings
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct SoundEffects {
    pub per_map: Vec<EffectOnMap>,
    pub route_effects_left_out: Vec<RouteEffectsLeftOut>,
    pub troop_effects_in_package: Vec<String>,
}

/// A sound effect that plays another sample on a map.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EffectOnMap {
    pub effect: String,
    pub map: i64,
    pub sample: String,
}

/// The route effects a map leaves out of its package.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RouteEffectsLeftOut {
    pub map: i64,
    pub effects: Effects,
}

/// `"all"`, or the effects by name.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Effects {
    All(All),
    These(Vec<String>),
}

/// The word `"all"`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum All {
    #[serde(rename = "all")]
    All,
}

/// A test page and the map it runs in.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Case {
    pub map: i32,
    pub commands: Vec<Command>,
}

/// A picture as the scan answers it —its [`PictureKey`], whose fields read
/// through this one—, and what the converter learns of it on the map that
/// shows it: `path` and `with_map` for a part, `behind_map`,
/// `screen_on_map`. It goes on in the tables, to the compiler and the
/// emission, as the key's fields and then these, only when they say
/// something. The compiler reads `with_map` and `screen_on_map`; `path`
/// and `behind_map` are the converter's and the emission's, and travel
/// here because the converter keeps the key whole.
#[derive(Debug, Clone, Default, PartialEq, Serialize, Deserialize)]
pub struct Key {
    #[serde(flatten)]
    pub key: PictureKey,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    #[serde(default, skip_serializing_if = "is_false")]
    pub with_map: bool,
    #[serde(default, skip_serializing_if = "is_false")]
    pub behind_map: bool,
    #[serde(default, skip_serializing_if = "is_false")]
    pub screen_on_map: bool,
}

impl From<PictureKey> for Key {
    fn from(key: PictureKey) -> Key {
        Key {
            key,
            ..Key::default()
        }
    }
}

impl std::ops::Deref for Key {
    type Target = PictureKey;
    fn deref(&self) -> &PictureKey {
        &self.key
    }
}

fn is_false(b: &bool) -> bool {
    !b
}

/// An entry of a table of pictures: its key, and where the cartridge
/// carries it.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Picture {
    #[serde(flatten)]
    pub key: Key,
    #[serde(flatten)]
    pub place: Place,
}

/// Where a picture is carried: in the map's sprite bank, with its slot; in
/// the background layer —`"plane": "background"`—, with its entry in the
/// cartridge's table of big ones, its centre and whether it has a mode 7
/// texture; or in the common events' table —`"plane": "common"`—, with its
/// entry, its slot and its set. See [`crate::registry::Pictures`].
///
/// A small one carries the sprite palette the converter put it in too,
/// which the compiler does not read: the converter keeps the entry whole.
/// The fields go in the order the converter has always written them: a
/// common one was a sprite one first, so its slot and palette come before
/// its plane.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(untagged)]
pub enum Place {
    Common {
        slot: u8,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        palette: Option<usize>,
        plane: CommonPlane,
        image: u8,
        set: usize,
    },
    Background {
        plane: BackgroundPlane,
        image: u8,
        center: (i32, i32),
        #[serde(default, skip_serializing_if = "is_false")]
        texture: bool,
    },
    Sprite {
        slot: u8,
        #[serde(default, skip_serializing_if = "Option::is_none")]
        palette: Option<usize>,
    },
}

/// The word `"common"`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum CommonPlane {
    #[serde(rename = "common")]
    Common,
}

/// The word `"background"`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum BackgroundPlane {
    #[serde(rename = "background")]
    Background,
}

/// Something per map, as an object keyed by the map's number, in the order
/// the caller gives the maps: the cartridge's, which is not the numbers'.
/// A map given twice is one key, where it was first given, with the last
/// value: as an object keeps it. ABL's release lists five maps twice.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ByMap<T>(pub Vec<(i32, T)>);

impl<T> Default for ByMap<T> {
    fn default() -> ByMap<T> {
        ByMap(Vec::new())
    }
}

impl<T> ByMap<T> {
    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    /// `value` for `map`: in its place if the map is there already, last
    /// if not.
    pub fn insert(&mut self, map: i32, value: T) {
        match self.0.iter_mut().find(|(m, _)| *m == map) {
            Some((_, v)) => *v = value,
            None => self.0.push((map, value)),
        }
    }
}

impl<T> FromIterator<(i32, T)> for ByMap<T> {
    fn from_iter<I: IntoIterator<Item = (i32, T)>>(iter: I) -> ByMap<T> {
        let mut out = ByMap::default();
        for (map, value) in iter {
            out.insert(map, value);
        }
        out
    }
}

impl<T: Serialize> Serialize for ByMap<T> {
    fn serialize<S: Serializer>(&self, serializer: S) -> Result<S::Ok, S::Error> {
        let mut map = serializer.serialize_map(Some(self.0.len()))?;
        for (k, v) in &self.0 {
            map.serialize_entry(&k.to_string(), v)?;
        }
        map.end()
    }
}

impl<'de, T: Deserialize<'de>> Deserialize<'de> for ByMap<T> {
    fn deserialize<D: Deserializer<'de>>(deserializer: D) -> Result<ByMap<T>, D::Error> {
        struct Each<T>(PhantomData<T>);
        impl<'de, T: Deserialize<'de>> Visitor<'de> for Each<T> {
            type Value = ByMap<T>;
            fn expecting(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
                f.write_str("an object keyed by map numbers")
            }
            fn visit_map<A: MapAccess<'de>>(self, mut access: A) -> Result<ByMap<T>, A::Error> {
                let mut out = ByMap::default();
                while let Some((k, v)) = access.next_entry::<String, T>()? {
                    let map = k
                        .parse::<i32>()
                        .map_err(|_| serde::de::Error::custom(format!("{k} is not a map")))?;
                    out.insert(map, v);
                }
                Ok(out)
            }
        }
        deserializer.deserialize_map(Each(PhantomData))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The three planes, each as the converter has always written it, read
    /// back as itself and written again the same.
    #[test]
    fn a_picture_entry_goes_and_comes_back_the_same() {
        let key = r#"{"number":3,"name":"Pic","zoom":100,"transparent_color":false,"map_fixed":false,"by_variable":false,"at":[160,120]"#;
        for rest in [
            r#","with_map":true,"slot":2,"palette":1}"#,
            r#","slot":2}"#,
            r#","plane":"background","image":1,"center":[160,120]}"#,
            r#","plane":"background","image":1,"center":[160,120],"texture":true}"#,
            r#","slot":15,"palette":0,"plane":"common","image":129,"set":0}"#,
        ] {
            let entry = format!("{key}{rest}");
            let picture: Picture = serde_json::from_str(&entry).unwrap();
            assert_eq!(serde_json::to_string(&picture).unwrap(), entry);
        }
        let sprite: Picture = serde_json::from_str(&format!("{key},\"slot\":2}}")).unwrap();
        assert_eq!(
            sprite.place,
            Place::Sprite {
                slot: 2,
                palette: None
            }
        );
    }

    /// The maps go in the caller's order, not the numbers'.
    #[test]
    fn by_map_keeps_the_order_it_is_given() {
        let m: ByMap<i32> = serde_json::from_str(r#"{"5": 1, "2": 2}"#).unwrap();
        assert_eq!(m.0, vec![(5, 1), (2, 2)]);
        assert_eq!(serde_json::to_string(&m).unwrap(), r#"{"5":1,"2":2}"#);
        // A map given twice is one, where it was first, with the last value.
        let m: ByMap<i32> = [(5, 1), (2, 2), (5, 3)].into_iter().collect();
        assert_eq!(m.0, vec![(5, 3), (2, 2)]);
    }
}
