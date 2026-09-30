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
///
/// The battle's is not a map: it is **an audio package of its own**, which
/// the ROM loads when opening the battle and unloads when closing it. It
/// goes separately and not ahead of the map's package, and that is
/// measured: the battle song is 18 samples and 51,480 B of ARAM's 64,512, so
/// putting it in map 2's package the 24 effects of that map —49,068 B, which
/// all fit today— dropped almost entirely. With its own package the map pays
/// nothing while there is no battle.
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
///
/// It is the sibling of `Messages`: the bytecode carries an index and not a
/// name, and the compiler is the one that resolves the index. The ROM
/// carries **the first `SONG_TOTAL`**, which are the ones that fit in ARAM:
/// all of them share the samples and the shared bank lives in the SPC700's
/// 64 KB, which are uploaded only once at boot. A higher index is a song
/// that did not fit and does not sound.
///
/// Numbering all of them and not only the ones that fit is what keeps the
/// bytecode from depending on which were chosen. Until 2026-09-06 only one
/// fit and this was already written this way; the day four fit nothing
/// different had to be recompiled.
#[derive(Debug, Clone, Default)]
pub struct Songs {
    pub names: Vec<String>,
    /// And the `PlaySound` effects, the same way: each combination of effect,
    /// volume, tempo and pan is an entry, and the bytecode carries its index.
    /// They live here and not apart because this is what already passes from
    /// compilation to compilation.
    pub sounds: Vec<Sound>,
    /// The package being compiled: what is asked for is noted in its own.
    /// None notes nothing.
    pub current: Option<Package>,
    /// And who asks for what: each song and each effect is noted in the
    /// package being compiled, in the order they appear. It is what builds
    /// each map's audio package: see `package_load` in
    /// tools/runtime/audio_package.s. And which ROM maps each one jumps to
    /// —`destinations`, indices into the map table—, which is where it comes
    /// from which song may be playing when a package is loaded: see
    /// `inherited_songs` in music.py.
    pub per_package: Vec<(Package, Wants)>,
    /// Per package, each song a `PlayBGM` of it turns on, and whether all of
    /// them are right before a jump to another map. A song is an exit song
    /// on a map if **all** its `PlayBGM`s there are: see `exit_songs` in the
    /// converter's `Songs`.
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

    /// Notes a jump from the package being compiled to `dest`: with `song`
    /// if it goes right after a `PlayBGM` of that song, with no branches or
    /// effects in between —the one it surely carries—, or with None if it
    /// carries whatever is playing. The page notes it when it compiles, and
    /// `recalled_destination` that of a `RecallToLocation`, always with None.
    /// See `inherited_songs` in music.py.
    pub fn jump(&mut self, dest: usize, song: Option<usize>) {
        if let Some(current) = self.current {
            let dests = entry(&mut self.jumps, current);
            push_new(entry(dests, dest), song);
        }
    }

    /// Notes a `PlayBGM` of the song in the package being compiled: `is_exit`
    /// if after it, with no branches or effects in between, the page jumps
    /// to another map. A song is an exit song on a map if **all** its
    /// `PlayBGM`s there are.
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
    /// something else puts it there —see `route_left_out`—. One that is not
    /// in the package does not sound, so it does not keep a song from being
    /// an exit song.
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

/// The graphics the routes change to with command 34 and the ones actors
/// can be given, numbered in the order they appear.
///
/// Sibling of `Songs` and `Messages`, with a difference that matters: it is
/// **per map**. What the ROM needs from a graphic —its twelve poses and its
/// palette— lives in the sprite bank, and the bank belongs to each map; two
/// maps that change to the same CharSet number it each on their own.
///
/// The bytecode carries the index and not the name, as with songs and maps:
/// the compiler is the one that resolves it, and the ROM does not look at
/// the LCF again.
///
/// `associations` half breaks the "per map", and it is worth understanding
/// why: they are the graphics `ChangeSpriteAssociation` can give an actor,
/// and that **survives the map change** —every time the game uses it, the
/// command is right next to a teleport and what shows is the graphic on the
/// other side—. So its index cannot mean one thing here and another there.
/// It is solved by reserving the first slots of the table of **every** ROM
/// map for them, in the same order: see `associations` in
/// [`crate::indices`], which is the prior pass that gathers them, and the
/// converter's `Pictures.choose`, which is the same pattern.
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

/// The troops the battles ask for, to know which tables to emit.
///
/// Sibling of `Songs`, with a difference that matters: **the bytecode does
/// not depend on it**. `Songs` numbers and the opcode carries the number;
/// here the opcode carries the RM2k id and this only gathers the list, so a
/// registry with other troops inside does not change a single byte of any
/// page. It is what allows compiling a loose page without knowing which
/// tables the cartridge has.
#[derive(Debug, Clone, Default)]
pub struct Troops {
    pub ids: Vec<i32>,
    /// And which backdrop each one fights with, which is the text of the
    /// `EnemyEncounter` itself —`SJBackdropABL04` on map 2— and not
    /// something to look up in the LDB. It goes here and not in a separate
    /// registry because it is a fact of the battle, like the troop. See
    /// tools/port/scene.py.
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
///
/// **A single one per ROM**, and that is the decision that bounds the
/// scope: see the converter's `Pictures`, which chooses it.
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
    /// move from where it is. `MovePicture` and `ErasePicture` ask it, since
    /// they do not carry the name: in RM2k the picture number is all that
    /// ties them to their `ShowPicture`.
    pub fn owns(&self, number: i32, at: Option<(i32, i32)>) -> bool {
        self.number == number && at.is_none_or(|a| a == (self.x, self.y))
    }
}
