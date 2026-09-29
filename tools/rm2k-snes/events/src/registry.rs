//! What the compiler numbers while it compiles: the songs and the sound
//! effects, the graphics a route changes to, the troops the battles ask
//! for; and the one picture the cartridge carries.
//!
//! The bytecode carries an index and not a name, and the index is given
//! here the first time something asks for it: so everything that compiles
//! pages for one cartridge has to go through the same registry, in the
//! same order.

use crate::game::Sound;
use serde_json::{json, Value};

/// Where what a page asks for plays: a map's audio package, by its index
/// in the cartridge, or the battle's, which is a package of its own that
/// the ROM loads when a battle opens.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Package {
    Map(usize),
    Battle,
}

impl Package {
    fn key(self) -> Value {
        match self {
            Package::Map(i) => json!(i),
            Package::Battle => json!("battle"),
        }
    }
}

/// What one package asks for: its songs, by index; its effects, by name;
/// and the maps its pages jump to.
#[derive(Debug, Clone, Default)]
pub struct Wants {
    pub songs: Vec<usize>,
    pub sounds: Vec<String>,
    pub destinations: Vec<usize>,
}

/// A list of `(key, value)` in the order the keys first appeared.
fn entry<K: PartialEq, V: Default>(list: &mut Vec<(K, V)>, key: K) -> &mut V {
    match list.iter().position(|(k, _)| *k == key) {
        Some(i) => &mut list[i].1,
        None => {
            list.push((key, V::default()));
            &mut list.last_mut().unwrap().1
        }
    }
}

fn push_new<T: PartialEq>(list: &mut Vec<T>, value: T) {
    if !list.contains(&value) {
        list.push(value);
    }
}

/// Each map a package jumps to, with the songs it can carry there.
pub type Jumps = Vec<(usize, Vec<Option<usize>>)>;

/// The songs the `PlayBGM`s ask for and the effects the `PlaySound`s ask
/// for, numbered in the order they appear; and which package asks for what.
#[derive(Debug, Clone, Default)]
pub struct Songs {
    pub names: Vec<String>,
    pub sounds: Vec<Sound>,
    /// The package being compiled: what is asked for is noted in its own.
    /// None notes nothing.
    pub current: Option<Package>,
    pub per_package: Vec<(Package, Wants)>,
    /// Per package, each song a `PlayBGM` of it turns on, and whether all of
    /// them are right before a jump to another map.
    pub exits: Vec<(Package, Vec<(usize, bool)>)>,
    /// Per package, each map it jumps to and with which song —None is
    /// whatever is playing—.
    pub jumps: Vec<(Package, Jumps)>,
    /// How many effects went into a package, so a page can see whether a
    /// command made one sound.
    pub requested: u64,
}

impl Songs {
    fn note(&mut self, what: impl FnOnce(&mut Wants)) {
        if let Some(current) = self.current {
            what(entry(&mut self.per_package, current));
        }
    }

    pub fn index(&mut self, name: &str) -> usize {
        if !self.names.iter().any(|n| n == name) {
            self.names.push(name.to_string());
        }
        let i = self.names.iter().position(|n| n == name).unwrap();
        self.note(|w| push_new(&mut w.songs, i));
        i
    }

    pub fn song(&self, name: &str) -> Option<usize> {
        self.names.iter().position(|n| n == name)
    }

    pub fn dest(&mut self, map: usize) {
        self.note(|w| push_new(&mut w.destinations, map));
    }

    pub fn jump(&mut self, dest: usize, song: Option<usize>) {
        if let Some(current) = self.current {
            let dests = entry(&mut self.jumps, current);
            push_new(entry(dests, dest), song);
        }
    }

    pub fn note_exit(&mut self, song: usize, is_exit: bool) {
        if let Some(current) = self.current {
            let noted = entry(&mut self.exits, current);
            match noted.iter_mut().find(|(s, _)| *s == song) {
                Some((_, e)) => *e = *e && is_exit,
                None => noted.push((song, is_exit)),
            }
        }
    }

    /// The effect's index. Without `in_package` it is not noted in the
    /// package and does not count in `requested`: it only sounds if
    /// something else puts it there.
    pub fn sound(&mut self, sound: Sound, in_package: bool) -> usize {
        if !self.sounds.contains(&sound) {
            self.sounds.push(sound.clone());
        }
        if in_package {
            self.requested += 1;
            let name = sound.0.clone();
            self.note(|w| push_new(&mut w.sounds, name));
        }
        self.sounds.iter().position(|s| *s == sound).unwrap()
    }

    pub fn to_json(&self) -> Value {
        json!({
            "names": self.names,
            "sounds": self.sounds.iter().map(|(n, v, t, b)| json!([n, v, t, b])).collect::<Vec<_>>(),
            "per_package": self.per_package.iter().map(|(p, w)| json!([p.key(), {
                "songs": w.songs, "sounds": w.sounds, "destinations": w.destinations,
            }])).collect::<Vec<_>>(),
            "exits": self.exits.iter().map(|(p, e)| json!([p.key(), e])).collect::<Vec<_>>(),
            "jumps": self.jumps.iter().map(|(p, j)| json!([p.key(), j])).collect::<Vec<_>>(),
            "requested": self.requested,
        })
    }
}

/// The graphics the routes change to and the ones actors can be given,
/// numbered **per map**: their poses live in each map's sprite bank. The
/// first ones are the same in every map —see `associations` in
/// [`crate::indices`]—, because the graphic an actor is given crosses the
/// teleport.
#[derive(Debug, Clone, Default)]
pub struct Graphics {
    pub pairs: Vec<(String, i32)>,
}

impl Graphics {
    pub fn new(associations: &[(String, i32)]) -> Graphics {
        Graphics {
            pairs: associations.to_vec(),
        }
    }

    pub fn index(&mut self, charset: &str, index: i32) -> usize {
        match self
            .pairs
            .iter()
            .position(|(c, i)| c == charset && *i == index)
        {
            Some(k) => k,
            None => {
                self.pairs.push((charset.to_string(), index));
                self.pairs.len() - 1
            }
        }
    }
}

/// The backdrop a troop fights on: a name, or the local one, which is not
/// known until the battle starts —it is the terrain the hero stands on—.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Backdrop {
    Named(String),
    Place,
}

/// The troops the battles ask for, to know which tables to emit. The
/// bytecode carries RM2k's number, so this changes no byte of any page.
#[derive(Debug, Clone, Default)]
pub struct Troops {
    pub ids: Vec<i32>,
    pub backdrops: Vec<(i32, Backdrop)>,
}

impl Troops {
    pub fn request(&mut self, number: i32, backdrop: Option<Backdrop>) {
        push_new(&mut self.ids, number);
        if let Some(b) = backdrop {
            if !self.backdrops.iter().any(|(n, _)| *n == number) {
                self.backdrops.push((number, b));
            }
        }
    }
}

/// The one picture the cartridge carries: which `ShowPicture` took its
/// place, which the caller decides —it has to convert the image to know
/// whether it fits—.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Picture {
    pub name: String,
    pub number: i32,
    pub x: i32,
    pub y: i32,
}

impl Picture {
    /// Whether this `ShowPicture` is the one that took the place.
    pub fn shows(&self, number: i32, name: &str, x: i32, y: i32) -> bool {
        self.name == name && self.number == number && (self.x, self.y) == (x, y)
    }

    /// Whether the picture this command names is this one and it does not
    /// move from where it is; `MovePicture` and `ErasePicture` do not carry
    /// the name.
    pub fn owns(&self, number: i32, at: Option<(i32, i32)>) -> bool {
        self.number == number && at.is_none_or(|a| a == (self.x, self.y))
    }
}
