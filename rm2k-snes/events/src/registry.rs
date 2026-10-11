//! What the compiler numbers while it compiles: the songs and the sound
//! effects, the graphics a route changes to, the troops the battles ask
//! for; and the pictures each map carries.
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
    /// runtime/audio_package.s. And which ROM maps each one jumps to
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
    /// The songs a troop page's `PlayBGM` starts, which are also in the
    /// battle's package: they play instead of the battle song and not next
    /// to it, and the cartridge's plan puts them apart so they do not lower
    /// its rate.
    pub troop_songs: Vec<usize>,
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
        let mut out = json!({
            "names": self.names,
            "sounds": self.sounds.iter().map(|(n, v, t, b)| json!([n, v, t, b])).collect::<Vec<_>>(),
            "per_package": self.per_package.iter().map(|(p, w)| json!([p.key(), {
                "songs": w.songs, "sounds": w.sounds, "destinations": w.destinations,
            }])).collect::<Vec<_>>(),
            "exits": self.exits.iter().map(|(p, e)| json!([p.key(), e])).collect::<Vec<_>>(),
            "jumps": self.jumps.iter().map(|(p, j)| json!([p.key(), j])).collect::<Vec<_>>(),
            "requested": self.requested,
        });
        // Only when there are some: without them the answer stays the one
        // `tests/python.rs` holds the hashes of, and the reader takes a
        // missing list as an empty one.
        if !self.troop_songs.is_empty() {
            out["troop_songs"] = json!(self.troop_songs);
        }
        out
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
    /// The graphics that did not fit in [`ROUTE_GFX_MAX`] and were left
    /// out, so the converter can say what was lost.
    pub dropped: Vec<(String, i32)>,
}

/// How many graphics a map's table holds in the ROM. It is the same number
/// as `ROUTE_GFX_MAX` in `rm2k-snes-mapdata`, which this crate cannot see;
/// if they disagree, the emission refuses the map instead of losing it
/// silently. A graphic that does not fit is ignored, not the map left out.
pub const ROUTE_GFX_MAX: usize = 8;

impl Graphics {
    pub fn new(associations: &[(String, i32)]) -> Graphics {
        // The associations take the table's first slots in every map; past
        // its end they are dropped too, and noted.
        let kept = associations.len().min(ROUTE_GFX_MAX);
        Graphics {
            pairs: associations[..kept].to_vec(),
            dropped: associations[kept..].to_vec(),
        }
    }

    /// Like [`Graphics::index`], but `None` if the graphic would be past
    /// the table's end: it is not added and it is noted in `dropped`.
    pub fn index_capped(&mut self, charset: &str, index: i32) -> Option<usize> {
        let known = self.pairs.iter().position(|(c, i)| c == charset && *i == index);
        match known {
            Some(k) if k < ROUTE_GFX_MAX => Some(k),
            None if self.pairs.len() < ROUTE_GFX_MAX => Some(self.index(charset, index)),
            _ => {
                let g = (charset.to_string(), index);
                if !self.dropped.contains(&g) {
                    self.dropped.push(g);
                }
                None
            }
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
    /// `scene.rs` in rm2k-snes-convert.
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

/// What a `ShowPicture` shows, as far as the cartridge has to carry it:
/// everything that changes the picture's pixels, and its number.
///
/// * The **position** is in it only for a picture that goes with the
///   screen and is placed by a constant: scaling RM2k's screen to the
///   console's rounds both corners, so the same file comes out a pixel
///   wider or narrower depending on where it is. One placed by variables is
///   converted once, at a corner on the grid; one that goes with the map is
///   not scaled at all.
/// * The **number** is not a matter of pixels, but it is what the console
///   keeps a picture by —see [`Pictures`]—, and the same file shown under two
///   numbers is two pictures for it.
/// * The tone and the transparency are not in it: the console changes them
///   while the picture is shown.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PictureKey {
    pub number: i32,
    pub name: String,
    pub zoom: i32,
    pub transparent_color: bool,
    pub map_fixed: bool,
    pub by_variable: bool,
    pub at: Option<(i32, i32)>,
}

impl PictureKey {
    pub fn to_json(&self) -> Value {
        json!({
            "number": self.number,
            "name": self.name,
            "zoom": self.zoom,
            "transparent_color": self.transparent_color,
            "map_fixed": self.map_fixed,
            "by_variable": self.by_variable,
            "at": self.at.map(|(x, y)| json!([x, y])),
        })
    }
}

/// A picture too big for the sprites, which the cartridge carries as a
/// background layer —BG1 in mode 1, while it is shown—: its key, its entry
/// in the cartridge's table of them, and the centre it was drawn at on
/// RM2k's screen, which is where a `MovePicture` has to leave it sideways.
///
/// The centre is the key's, or, for one that goes with the map —which
/// covers the whole screen, or it would not be here—, the screen's.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct BigPicture {
    pub key: PictureKey,
    pub image: u8,
    pub center: (i32, i32),
    /// Whether the cartridge carries it with a mode 7 texture too, which is
    /// what lets a `MovePicture` zoom it: see [`Pictures::zooms`].
    pub texture: bool,
}

/// The pictures of one map: which ones the caller put into its sprite bank,
/// each with the slot the console keeps it in.
///
/// It goes **per map** because the pictures' tiles are part of the map's
/// sprite bank, which is uploaded with the map: the same file shown on two
/// maps is in both. And the caller decides it, because to know whether a
/// picture fits it has to be converted and the bank built. What the
/// compiler is told is the table; a `ShowPicture` whose picture is not in
/// it is accepted without being done, as all of them were until 2026-09-12.
///
/// The first call, the scan, does not have the table yet: it **gathers**
/// what each map's pages and test pages can show, in the order they are
/// met, and that is what the caller converts.
#[derive(Debug, Clone, Default)]
pub struct Pictures {
    /// The pictures, in the order the cartridge numbers them, and each
    /// one's slot.
    pub table: Vec<(PictureKey, u8)>,
    /// The big ones the map can show, which the cartridge carries as a
    /// background layer and not in the map's sprite bank: see
    /// [`BigPicture`].
    pub big: Vec<BigPicture>,
    /// Whether this compilation is gathering instead: then `table` fills up
    /// with every picture met, with slot 0, and nothing is emitted.
    pub gathering: bool,
    /// What the gathering also writes down: each `MovePicture` that the
    /// console could show, as its number and the size it goes to. The caller
    /// gives a big picture shown under that number a mode 7 texture if the
    /// size is not the one it was shown at —see [`BigPicture::texture`]—:
    /// which picture the number names is not known here, and an extra
    /// texture costs only cartridge.
    pub zooms: Vec<(i32, i32)>,
}

impl Pictures {
    /// A registry that gathers.
    pub fn gathering() -> Pictures {
        Pictures {
            table: Vec::new(),
            big: Vec::new(),
            gathering: true,
            zooms: Vec::new(),
        }
    }

    /// The big picture `key` is, if the cartridge carries it as one.
    pub fn big_of(&self, key: &PictureKey) -> Option<&BigPicture> {
        self.big.iter().find(|b| b.key == *key)
    }

    /// The big pictures shown under `number`.
    pub fn numbered_big(&self, number: i32) -> impl Iterator<Item = &BigPicture> {
        self.big.iter().filter(move |b| b.key.number == number)
    }

    /// The image and the slot of `key`, if the map carries it.
    pub fn image(&self, key: &PictureKey) -> Option<(u8, u8)> {
        self.table
            .iter()
            .position(|(k, _)| k == key)
            .map(|i| (i as u8, self.table[i].1))
    }

    /// The map's pictures shown under `number`: what a `MovePicture` or an
    /// `ErasePicture` can be acting on, since in RM2k the number is all that
    /// ties them to their `ShowPicture`.
    pub fn numbered(&self, number: i32) -> impl Iterator<Item = &(PictureKey, u8)> {
        self.table.iter().filter(move |(k, _)| k.number == number)
    }

    /// Gathers `key`, once.
    pub fn gather(&mut self, key: PictureKey) {
        if !self.table.iter().any(|(k, _)| *k == key) {
            self.table.push((key, 0));
        }
    }

    /// Gathers a move of `number` to `zoom` percent, once.
    pub fn gather_zoom(&mut self, number: i32, zoom: i32) {
        if !self.zooms.contains(&(number, zoom)) {
            self.zooms.push((number, zoom));
        }
    }

    pub fn zooms_json(&self) -> Value {
        json!(self.zooms.iter().map(|(n, z)| json!([n, z])).collect::<Vec<_>>())
    }

    pub fn keys_json(&self) -> Value {
        json!(self.table.iter().map(|(k, _)| k.to_json()).collect::<Vec<_>>())
    }
}

#[cfg(test)]
mod graphics_cap_tests {
    use super::*;

    #[test]
    fn the_graphics_past_the_table_are_dropped_and_noted() {
        let mut g = Graphics::default();
        for k in 0..ROUTE_GFX_MAX {
            assert_eq!(g.index_capped("A", k as i32), Some(k));
        }
        assert_eq!(g.index_capped("A", 3), Some(3), "a known one still resolves");
        assert_eq!(g.index_capped("B", 0), None);
        assert_eq!(g.index_capped("B", 0), None);
        assert_eq!(g.pairs.len(), ROUTE_GFX_MAX, "the table did not grow");
        assert_eq!(g.dropped, vec![("B".to_string(), 0)], "noted once");
    }
}
