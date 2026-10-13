//! A cartridge's music, as a stage of its converter: from what the
//! cartridge's event compiler asked for to the job [`crate::compile`]
//! builds, and the `.msu` behind it.
//!
//! What this decides and `compile` does not: which songs the cartridge
//! carries besides the ones its pages start —the boot map's, the title's,
//! the Game Over's and each map's own—, which audio package each map gets,
//! and which song can already be playing when each one loads. And what the
//! `.msu` carries besides the quality sound effects: the backdrops, which
//! come made.
//!
//! Until 2026-09-30 this was the converter's Python (`music.py`, and the
//! part of the old `snes_convert.py` that built the packages), and what it writes
//! into a cartridge has to keep coming out byte for byte the same.

use crate::compile::Music;
use crate::fail::{Bad, Result};
use crate::msu::Effects;
use crate::msu_data;
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

/// "No song": entering does not change what is playing, or there is none.
/// A `PlayBGM` carries the index in one byte, so a song numbered $FF could
/// not be started either.
pub const NONE: usize = 0xFF;

/// A package the event compiler noted: a map, by its index in the map
/// table, or the battle.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum Key {
    Map(usize),
    Battle,
}

/// What one package's pages ask for: songs by index, sound effects by name,
/// and the maps they jump to, by index in the map table.
#[derive(Debug, Clone, Default)]
pub struct Wants {
    pub songs: Vec<usize>,
    pub sounds: Vec<String>,
    pub destinations: Vec<usize>,
}

/// The songs and sounds the event compiler numbered, as it hands them over.
#[derive(Debug, Clone, Default)]
pub struct Songs {
    pub names: Vec<String>,
    /// Each sound: its effect, volume, tempo and pan.
    pub sounds: Vec<(String, i64, i64, i64)>,
    pub per_package: HashMap<Key, Wants>,
    /// Per package, each song a `PlayBGM` of it turns on, and whether it only
    /// turns it on to leave: see [`Songs::exit_songs`].
    pub exits: HashMap<Key, Vec<(usize, bool)>>,
    /// Per package, each map it jumps to and with which songs —None is
    /// whatever is playing—.
    pub jumps: HashMap<Key, Vec<(usize, Vec<Option<usize>>)>>,
    /// The songs a troop page's `PlayBGM` starts: in the battle's package,
    /// they go apart. A request without them has none.
    pub troop_songs: Vec<usize>,
}

impl Songs {
    /// The songs a map turns on only to leave: each of its `PlayBGM`s is
    /// followed by a jump to another map, with no effects or branches in
    /// between. In the game it is `lufsorr` on map 3: it plays after the
    /// sequence of effects, when none is left to play, and the map is left
    /// right away. So it has no reason to fit in ARAM with those effects: it
    /// goes in the **separate** package, it is uploaded if there is room,
    /// and if not its `PlayBGM` uploads it —see `exit_extra` in
    /// runtime/audio_package.s—. It is from 2026-09-26.
    pub fn exit_songs(&self, map: usize) -> Vec<usize> {
        self.exits
            .get(&Key::Map(map))
            .map(|e| e.iter().filter(|(_, is_exit)| *is_exit).map(|(t, _)| *t).collect())
            .unwrap_or_default()
    }

    fn wants(&self, map: usize) -> Option<&Wants> {
        self.per_package.get(&Key::Map(map))
    }

    /// The event compiler's answer, `songs` of it.
    pub fn from_json(v: &Value) -> Result<Songs> {
        let bad = |what: &str| Bad::usage(format!("the request's songs: {what} is not what it should be"));
        let key = |k: &Value| -> Result<Key> {
            match k {
                Value::String(s) if s == "battle" => Ok(Key::Battle),
                k => k.as_u64().map(|i| Key::Map(i as usize)).ok_or_else(|| bad("a package")),
            }
        };
        let index = |v: &Value, what: &str| v.as_u64().map(|i| i as usize).ok_or_else(|| bad(what));
        let list = |v: Option<&Value>, what: &str| -> Result<Vec<Value>> {
            v.and_then(Value::as_array).cloned().ok_or_else(|| bad(what))
        };
        let indices = |v: Option<&Value>, what: &str| -> Result<Vec<usize>> {
            list(v, what)?.iter().map(|i| index(i, what)).collect()
        };
        let pairs = |what: &str| -> Result<Vec<(Key, Value)>> {
            list(v.get(what), what)?
                .iter()
                .map(|p| Ok((key(p.get(0).ok_or_else(|| bad(what))?)?, p.get(1).cloned().ok_or_else(|| bad(what))?)))
                .collect()
        };
        let names = list(v.get("names"), "names")?
            .iter()
            .map(|n| n.as_str().map(String::from).ok_or_else(|| bad("names")))
            .collect::<Result<_>>()?;
        let sounds = list(v.get("sounds"), "sounds")?
            .iter()
            .map(|s| {
                let int = |k: usize| s.get(k).and_then(Value::as_i64).ok_or_else(|| bad("sounds"));
                Ok((s.get(0).and_then(Value::as_str).ok_or_else(|| bad("sounds"))?.to_string(), int(1)?, int(2)?, int(3)?))
            })
            .collect::<Result<_>>()?;
        let mut per_package = HashMap::new();
        for (k, w) in pairs("per_package")? {
            let wants = Wants {
                songs: indices(w.get("songs"), "songs")?,
                sounds: list(w.get("sounds"), "sounds")?
                    .iter()
                    .map(|s| s.as_str().map(String::from).ok_or_else(|| bad("sounds")))
                    .collect::<Result<_>>()?,
                destinations: indices(w.get("destinations"), "destinations")?,
            };
            per_package.insert(k, wants);
        }
        let mut exits = HashMap::new();
        for (k, e) in pairs("exits")? {
            let theirs = list(Some(&e), "exits")?
                .iter()
                .map(|p| {
                    Ok((
                        index(p.get(0).ok_or_else(|| bad("exits"))?, "exits")?,
                        p.get(1).and_then(Value::as_bool).ok_or_else(|| bad("exits"))?,
                    ))
                })
                .collect::<Result<_>>()?;
            exits.insert(k, theirs);
        }
        let mut jumps = HashMap::new();
        for (k, j) in pairs("jumps")? {
            let theirs = list(Some(&j), "jumps")?
                .iter()
                .map(|p| {
                    let dest = index(p.get(0).ok_or_else(|| bad("jumps"))?, "jumps")?;
                    let songs = list(p.get(1), "jumps")?
                        .iter()
                        .map(|s| if s.is_null() { Ok(None) } else { index(s, "jumps").map(Some) })
                        .collect::<Result<_>>()?;
                    Ok((dest, songs))
                })
                .collect::<Result<_>>()?;
            jumps.insert(k, theirs);
        }
        let troop_songs = match v.get("troop_songs") {
            None => Vec::new(),
            some => indices(some, "troop_songs")?,
        };
        Ok(Songs { names, sounds, per_package, exits, jumps, troop_songs })
    }
}

/// What the cartridge decided, and what the game says, that the plan needs.
#[derive(Debug, Clone, Default)]
pub struct Cartridge {
    pub songs: Songs,
    /// The maps, by number, in the order of the map table.
    pub maps: Vec<i64>,
    /// The name of the song each map gets from the tree, or "" if entering
    /// it does not change what is playing: see `Tree::music`.
    pub map_music: Vec<String>,
    /// Which one it boots in, by index.
    pub start: usize,
    /// The title screen's song and the Game Over's, if the cartridge has
    /// those screens and the database names one.
    pub title: Option<String>,
    pub game_over: Option<String>,
    /// `[music] apart_themes`: {map number: its separate songs}.
    pub apart: HashMap<i64, HashSet<String>>,
    /// `[music] jumps_that_never_happen`, as (map, destination) numbers.
    pub not_given: Vec<(i64, i64)>,
    /// The songs the database's `System` names, for the MSU-1 numbering.
    pub system_songs: Vec<String>,
    /// And every song the game's events and maps name, for the same.
    pub named_songs: Vec<String>,
    pub measuring_headroom: Option<f64>,
    /// How many frames decompressing the boot map takes.
    pub decompress_frames: f64,
    /// Whether the samples may travel in the `.msu`: in a cartridge that
    /// needs the MSU-1. See `Emit::msu_samples`.
    pub msu_samples: bool,
}

/// What was decided, which the rest of the stage prints.
#[derive(Debug, Clone)]
pub struct Plan {
    /// The job, as `compile` reads it and in the order of its keys.
    pub job: Value,
    /// Each ROM package's separate songs.
    pub separate: Vec<Vec<usize>>,
    /// The songs of the battle's package, if the cartridge has battles.
    pub battle_songs: Option<usize>,
}

/// Adds `name` at the end if it is not there, and says where it is.
fn number(names: &mut Vec<String>, name: &str) -> usize {
    match names.iter().position(|n| n == name) {
        Some(i) => i,
        None => {
            names.push(name.to_string());
            names.len() - 1
        }
    }
}

/// The job for `compile`, from what the cartridge asks for.
///
/// **All the songs** go, sharing a single sample bank: the ones the
/// compiled `PlayBGM`s name, plus that of the map where the ROM boots,
/// which is the one that plays without anything happening. **And all of
/// them fit**: the index is given by the list and costs no ARAM. What the
/// ARAM limits is the samples, and that is allocated per package: at the
/// rate the worst package of each one gives, but all of them.
///
/// The indices are those of the event compiler and aren't touched: the
/// bytecode already carries them. That is why the boot map's is added **at
/// the end**, which is the only thing that doesn't renumber the others; then
/// the title's —`title_music`, which in ABL is Fantasia_Of_The_Wind—, the
/// Game Over's —`gameover_music`, `GameOver3`, from the RTP—, and each
/// map's own, in the order of the map table, which is easyrpg's
/// `Game_Map::PlayBgm`: what plays when entering through a teleport.
pub fn plan(c: &Cartridge) -> Result<Plan> {
    let s = &c.songs;
    let n = c.maps.len();
    let mut names = s.names.clone();
    let own = &c.map_music[c.start];
    let boot = if own.is_empty() { NONE } else { number(&mut names, own) };
    let title_song = match c.title.as_deref() {
        Some(t) if !t.is_empty() => number(&mut names, t),
        _ => NONE,
    };
    let game_over_song = match c.game_over.as_deref() {
        Some(t) if !t.is_empty() => number(&mut names, t),
        _ => NONE,
    };
    let mut map_song = Vec::with_capacity(n);
    for name in &c.map_music {
        let index = if name.is_empty() { NONE } else { number(&mut names, name) };
        if index > 0xFF {
            return Err(Bad::answer(format!("song {name:?} doesn't fit in a byte")));
        }
        map_song.push(index);
    }

    // The sound effects, in the order the compiled pages ask for them: the
    // maps are compiled in ROM order, so those of the map where it boots go
    // first —in the demo, the rain and the thunder of the opening—. Only the
    // ones that are in some package: one that isn't in any doesn't sound
    // anywhere —its row of `sound_table` stays at $FF— and building it would
    // cost the music, because the copies count the cartridge's sound
    // effects. It happens with the route ones of `[sound_effects]
    // route_effects_left_out`.
    let packed: HashSet<&str> =
        s.per_package.values().flat_map(|w| w.sounds.iter().map(String::as_str)).collect();
    let mut effects: Vec<&str> = Vec::new();
    for (name, ..) in &s.sounds {
        if !effects.contains(&name.as_str()) && packed.contains(name.as_str()) {
            effects.push(name);
        }
    }

    // Each map's audio package, in the order of the map table: the songs its
    // pages can start —plus, in the boot one, the one that plays from the
    // start, and in all the map's own— and its sound effects, in the order
    // they appear, which is the priority the ROM uploads them with if they
    // don't all fit. See `package_load` in runtime/audio_package.s.
    let empty = Wants::default();
    let mut packages: Vec<(Vec<usize>, Vec<String>, Vec<usize>)> = Vec::new();
    let mut separate_ones: Vec<Vec<usize>> = Vec::new();
    for i in 0..n {
        let wants = s.wants(i).unwrap_or(&empty);
        let mut owned = wants.songs.clone();
        let booting = |t: usize| i == c.start && t == boot;
        if i == c.start && boot != NONE && !owned.contains(&boot) {
            owned.insert(0, boot);
        }
        // And the map's own song, **in front**: it is the only one on the
        // list that surely plays on entering, so if the ARAM isn't enough
        // for everything it is the last one that has to fall. Without it in
        // the package, its samples would have to be uploaded by
        // `song_ensure` when starting it, rebuilding the whole package a
        // second time.
        if map_song[i] != NONE {
            owned.retain(|&t| t != map_song[i]);
            owned.insert(0, map_song[i]);
        }
        // And the exit ones, separate and after the sound effects: the ones
        // the map starts only to leave have no reason to go in with its
        // sound effects. Not the map's own nor the boot one: those play on
        // entering.
        let out: Vec<usize> = s
            .exit_songs(i)
            .into_iter()
            .filter(|&t| owned.contains(&t) && t != map_song[i] && !booting(t))
            .collect();
        owned.retain(|t| !out.contains(t));
        // And the separate ones, which don't go with the other songs either:
        // their `PlayBGM` uploads them with the package's sound effects —see
        // `extra_separate` in runtime/audio_package.s—.
        let apart = c.apart.get(&c.maps[i]);
        let separate: Vec<usize> = owned
            .iter()
            .copied()
            .filter(|&t| apart.is_some_and(|a| a.contains(&names[t])) && t != map_song[i] && !booting(t))
            .collect();
        owned.retain(|t| !separate.contains(t));
        separate_ones.push(separate);
        packages.push((owned, wants.sounds.clone(), out));
    }
    // And the battle's package, after the maps: the battle song and its
    // sound effects, which the ROM uploads when opening the battle and
    // unloads when closing it. It goes separately and not inside the map's
    // package because the battle song alone fills the ARAM.
    //
    // The songs a troop page starts —`troop_songs`, `Play Radio`'s three in
    // the game— are **separate**, like `[music] apart_themes` on a map: they
    // play instead of the battle song, never next to it, so they do not have
    // to fit alongside it and do not lower its rate. Their `PlayBGM` uploads
    // them with the package's sound effects. Until 2026-09-30 they were not
    // done at all.
    let battle = s.per_package.get(&Key::Battle);
    if let Some(w) = battle {
        let (apart, owned): (Vec<usize>, Vec<usize>) =
            w.songs.iter().partition(|t| s.troop_songs.contains(t));
        packages.push((owned, w.sounds.clone(), Vec::new()));
        separate_ones.push(apart);
    }
    let mut package_names: Vec<String> = c.maps.iter().map(|m| m.to_string()).collect();
    if battle.is_some() {
        package_names.push("pelea".into());
    }
    // And the Game Over screen's, last: its song alone and no sound
    // effects. The ROM uploads it with the screen black, before the fade in
    // —see `game_over_black` in runtime/game_over.s—, and with a
    // package of its own it uploads only that: arriving with `song_ensure`
    // would rebuild the whole map package behind it, which is one more
    // second of black. For the allocation it is a one-song package, which
    // doesn't lower anyone's rate: its samples fit alone in the ARAM.
    let mut game_over_package = 0xFFFF;
    if game_over_song != NONE {
        game_over_package = packages.len();
        packages.push((vec![game_over_song], Vec::new(), Vec::new()));
        separate_ones.push(Vec::new());
        package_names.push("gameover".into());
    }
    let mut job_packages: Vec<Value> = packages
        .iter()
        .zip(&package_names)
        .zip(&separate_ones)
        .map(|(((owned, theirs, out), name), separate)| {
            json!({"name": name, "songs": owned, "effects": theirs, "exits": out, "separate": separate})
        })
        .collect();
    // And the title screen's, which isn't in the table: `song_ensure`
    // uploads its song with the boot map's package behind.
    if title_song != NONE {
        let (owned, theirs, _) = &packages[c.start];
        let mut songs = vec![title_song];
        songs.extend(owned);
        job_packages.push(json!({"name": "titulo", "songs": songs, "effects": theirs}));
    }
    let in_package: Vec<Vec<usize>> = packages.iter().map(|(owned, ..)| owned.clone()).collect();
    let inheritance =
        inherited_songs(s, &map_song, c.start, title_song, &package_names, Some(&in_package), &separate_ones, &c.not_given);

    let mut emit = Map::new();
    emit.insert("packages".into(), json!(packages.len()));
    emit.insert("boot".into(), json!(boot));
    emit.insert("title".into(), json!(title_song));
    emit.insert("game_over".into(), json!([game_over_song, game_over_package]));
    emit.insert("map_song".into(), json!(map_song));
    emit.insert("sounds".into(), json!(s.sounds.iter().map(|(n, v, t, b)| json!([n, v, t, b])).collect::<Vec<_>>()));
    emit.insert("start".into(), json!(c.start));
    emit.insert("decompress_frames".into(), json!(c.decompress_frames));
    // Only when it is so: a job without it is the one it always was.
    if c.msu_samples {
        emit.insert("msu_samples".into(), json!(true));
    }
    let mut job = Map::new();
    job.insert("songs".into(), json!(names));
    job.insert("effects".into(), json!(effects));
    job.insert("packages".into(), Value::Array(job_packages));
    job.insert("inheritance".into(), json!(inheritance.iter().map(|(p, t)| json!([p, t])).collect::<Vec<_>>()));
    job.insert("measuring_headroom".into(), json!(c.measuring_headroom));
    job.insert("system_songs".into(), json!(c.system_songs));
    // Only when there are some: a job without them is the one it always was.
    if !c.named_songs.is_empty() {
        job.insert("named_songs".into(), json!(c.named_songs));
    }
    job.insert("emit".into(), Value::Object(emit));
    Ok(Plan {
        job: Value::Object(job),
        separate: separate_ones,
        battle_songs: battle.map(|w| w.songs.len()),
    })
}

/// [(package name, index of a song that can be already playing when it
/// loads)], for the job.
///
/// Almost no map of the game brings its own song: a page starts it, and
/// until then the previous map's keeps going, and `package_load_done`
/// doesn't move its samples. So the package of a map without its own song
/// has to fit next to whatever can be already playing.
///
/// The teleports of the compiled pages are followed —`destinations`—
/// without looking at conditions, with a rule that is what makes the count
/// realistic and not "any song to any map" (4 is the game's router): **a map
/// with `PlayBGM` leaves with one of its own**, because the page that jumps
/// is almost always the one that started the song before. A map with its
/// own song silences what plays before loading its own —`map_song_mute`—,
/// so it inherits nothing; and the boot map is reached with the title's
/// playing.
///
/// `in_package` are the songs each map's package uploads on entering
/// —without the exit ones, see [`Songs::exit_songs`]—: a song that arrives
/// playing and isn't there has to fit next to it. Without it, the ones its
/// pages start. What leaves a map is still any of the ones they start, exit
/// ones included: they are precisely the ones that leave with it.
///
/// **Except in a map whose `PlayBGM`s are all exit ones**: there the rule
/// above doesn't hold, because each one goes stuck to its jump and the map's
/// other jumps carry none. Each jump carries what the compiler noted: the
/// exit song that precedes it, or whatever came into the map. It is the
/// game's 41 and 40: `Kfmus5` comes into 41 from the page of 37 and goes on
/// through 40, 42, 43, 44 and 45, while `golden_axe-turtlevillage2` and
/// `tsmedit` play only to leave. From 2026-09-27; until then those maps
/// inherited only their exit songs. The boot one keeps the rule above: see
/// `carries`.
///
/// `separate` are the separate songs of each package —`[music]
/// apart_themes`—: they don't leave the map, so they don't count in what
/// goes out.
///
/// `not_given` are the jumps of compiled pages that can't happen, as (map,
/// destination) numbers: a jump that never happens makes it reserve room
/// for a song that never arrives, at the expense of the ones that do. The
/// game declares them, in `[music] jumps_that_never_happen` of the project
/// file.
#[allow(clippy::too_many_arguments)]
pub fn inherited_songs(
    songs: &Songs,
    map_song: &[usize],
    initial: usize,
    title: usize,
    package_names: &[String],
    in_package: Option<&[Vec<usize>]>,
    separate: &[Vec<usize>],
    not_given: &[(i64, i64)],
) -> Vec<(String, usize)> {
    let n = map_song.len();
    let empty = Wants::default();
    let wants: Vec<&Wants> = (0..n).map(|i| songs.wants(i).unwrap_or(&empty)).collect();
    let no_separate = Vec::new();
    let separate_of = |i: usize| separate.get(i).unwrap_or(&no_separate);
    let index: HashMap<&str, usize> =
        package_names[..n.min(package_names.len())].iter().enumerate().map(|(i, name)| (name.as_str(), i)).collect();
    let not_given: HashSet<(usize, usize)> = not_given
        .iter()
        .filter_map(|(a, b)| Some((*index.get(a.to_string().as_str())?, *index.get(b.to_string().as_str())?)))
        .collect();
    let mut fits: Vec<BTreeSet<usize>> = vec![BTreeSet::new(); n];
    if title != NONE {
        fits[initial].insert(title);
    }

    let carries = |fits: &[BTreeSet<usize>], i: usize, dest: usize| -> BTreeSet<usize> {
        if map_song[i] != NONE {
            return BTreeSet::from([map_song[i]]);
        }
        let theirs: BTreeSet<usize> =
            wants[i].songs.iter().copied().filter(|t| !separate_of(i).contains(t)).collect();
        let exits: BTreeSet<usize> = songs.exit_songs(i).into_iter().collect();
        // Not the boot one: it is the router, which jumps to mid-game
        // according to variables, and without looking at conditions
        // whatever comes in there would go out anywhere.
        if !theirs.is_empty() && theirs.is_subset(&exits) && i != initial {
            // A destination no noted jump names —that of a page that didn't
            // compile whole— carries what came in.
            let with_it: Vec<Option<usize>> = songs
                .jumps
                .get(&Key::Map(i))
                .and_then(|j| j.iter().find(|(d, _)| *d == dest))
                .map(|(_, s)| s.clone())
                .unwrap_or_else(|| vec![None]);
            let mut out: BTreeSet<usize> = with_it.iter().flatten().copied().collect();
            if with_it.contains(&None) {
                out.extend(&fits[i]);
            }
            return out;
        }
        if theirs.is_empty() {
            fits[i].clone()
        } else {
            theirs
        }
    };

    let mut change = true;
    while change {
        change = false;
        for i in 0..n {
            for &dest in &wants[i].destinations {
                if not_given.contains(&(i, dest)) {
                    continue;
                }
                let leaves = carries(&fits, i, dest);
                if dest != i && map_song[dest] == NONE && !leaves.is_subset(&fits[dest]) {
                    fits[dest].extend(leaves);
                    change = true;
                }
            }
        }
    }
    let mut out = Vec::new();
    for i in 0..n {
        let uploaded: &[usize] = match in_package {
            Some(p) => &p[i],
            None => &wants[i].songs,
        };
        for &t in &fits[i] {
            if !uploaded.contains(&t) && t != map_song[i] {
                out.push((package_names[i].clone(), t));
            }
        }
    }
    out
}

/// A labelled block of bytes, as the converter's emission writes them: a
/// `.block` with its size in front, sixteen bytes a line.
fn block(label: &str, data: &[u8]) -> String {
    let mut out = format!(".block {}\n{label}:", data.len());
    for chunk in data.chunks(16) {
        out.push_str("\n    .byte ");
        out.push_str(&chunk.iter().map(|b| format!("${b:02X}")).collect::<Vec<_>>().join(","));
    }
    out
}

/// The `.msu` and what the ROM needs to read it.
pub struct Msu {
    pub blob: Vec<u8>,
    /// What goes at the end of `musicdata.inc`: the signature, where each
    /// backdrop is and, per package, where each sound effect is and at
    /// which pitch each sound plays.
    pub inc: String,
    pub backdrops: usize,
    pub effects: usize,
}

/// The `.msu`, with the backdrops first —`backdrops` are the `(tiles,
/// colors)` of **all the game's**, by number, each in its fixed place: see
/// [`msu_data::backdrop_offset`]— and behind them the quality sound effects
/// of each package, in the order of the package table and each package with
/// its own in order of place in the directory —their SRCN—: it is the order
/// `upload_placed` uploads them in, so the ROM reads them in one go, with a
/// single seek per package. A sound effect that is in two packages goes
/// twice even if at the same rate: a seek costs Mednafen one or two frames,
/// and the file has no cap.
///
/// Which version of each sound effect goes in each package, and at which
/// pitch it plays there, is [`crate::msu::effects`]'s. This puts them in the
/// file.
pub fn msu(backdrops: &[(Vec<u8>, Vec<u8>)], quality: &Effects, magic: &[u8; 4]) -> Result<Msu> {
    let mut entries: Vec<&[u8]> = backdrops.iter().flat_map(|(t, c)| [t.as_slice(), c.as_slice()]).collect();
    // Which entry each sound effect of each package is, in SRCN order: two
    // of the same package never share a place.
    let mut first = Vec::new();
    for package in &quality.packages {
        first.push(entries.len());
        entries.extend(package.versions.iter().map(|&v| quality.versions[v].data.as_slice()));
    }
    let (blob, offset) = msu_data::build(&entries, backdrops.len(), magic)?;
    let signature = blob[..msu_data::SIGNATURE_SIZE].to_vec();

    // Per package, one row per sound effect of its list —in the order the
    // ROM walks it—: where it is in the `.msu`, how long it is and where it
    // loops back, which is always to the start because they go whole.
    let (mut rows, mut from_rows) = (Vec::new(), Vec::new());
    let (mut heights, mut from_heights) = (Vec::new(), Vec::new());
    let mut already_done: HashMap<Vec<u8>, usize> = HashMap::new();
    for (package, &start) in quality.packages.iter().zip(&first) {
        from_rows.extend_from_slice(&(rows.len() as u16).to_le_bytes());
        for &j in &package.rows {
            let data = &quality.versions[package.versions[j]].data;
            rows.extend_from_slice(&(offset[start + j] as u32).to_le_bytes());
            rows.extend_from_slice(&(data.len() as u16).to_le_bytes());
            rows.extend_from_slice(&[0, 0]);
        }
        // And the pitch of each sound of `sound_table` with this package's
        // version: with that the ROM does no arithmetic, not even in the
        // interrupt. **Only the sounds whose sound effect is from here**, as
        // (index, pitch) pairs sorted by index and closed with $FFFF, which
        // `msu_pitch` walks: until 2026-09-27 it was one row per package
        // with all the sounds, almost all zeros, and with the whole world
        // chapter it went over a bank. Two packages with the same list share
        // it.
        let mut values = Vec::new();
        for &(k, height) in &package.pitches {
            values.extend_from_slice(&(k as u16).to_le_bytes());
            values.extend_from_slice(&(height as u16).to_le_bytes());
        }
        values.extend_from_slice(&[0xFF, 0xFF]);
        let at = *already_done.entry(values.clone()).or_insert_with(|| {
            let at = heights.len();
            heights.extend_from_slice(&values);
            at
        });
        from_heights.extend_from_slice(&(at as u16).to_le_bytes());
    }
    for table in [&rows, &heights] {
        if table.len() > 0x8000 {
            return Err(Bad::answer(format!("the .msu sound effect tables go over a bank: {} B", table.len())));
        }
    }
    let mut backdrop_pos = Vec::new();
    for k in 0..backdrops.len() {
        backdrop_pos.extend_from_slice(&(offset[2 * k] as u32).to_le_bytes());
        backdrop_pos.extend_from_slice(&(offset[2 * k + 1] as u32).to_le_bytes());
    }
    if backdrop_pos.is_empty() {
        backdrop_pos = vec![0; 8];
    }
    let effects = entries.len() - 2 * backdrops.len();
    let empty = vec![0u8; 2];
    let or_two = |d: &Vec<u8>| if d.is_empty() { empty.clone() } else { d.clone() };
    let blocks: Vec<String> = [
        ("msu_data_signature", or_two(&signature)),
        ("msu_backdrop_pos", backdrop_pos),
        ("se_msu_pkg", or_two(&from_rows)),
        ("se_msu_rows", or_two(&rows)),
        ("se_msu_pitch_pkg", or_two(&from_heights)),
        ("se_msu_pitch", or_two(&heights)),
    ]
    .iter()
    .map(|(label, data)| block(label, data))
    .collect();
    let inc = format!(
        "\n; The `.msu`: see `msu` in rm2k-snes-audio's cartridge.rs.\n\
         ; How many entries of the .msu are backdrops —two per backdrop,\n\
         ; the first ones— and how many are sound effects, behind: for\n\
         ; the tests.\n\
         MSU_BACKDROPS_N = {}\n\
         MSU_EFFECTS_N = {}\n\
         .segment \"RODATA\"\n{}\n",
        backdrops.len(),
        effects,
        blocks.join("\n")
    );
    Ok(Msu { blob, inc, backdrops: backdrops.len(), effects })
}

/// `effects.json`: which sound each row of `sound_table` is and at which
/// rate each sound effect of each package goes in the `.msu`. The ROM
/// doesn't read it; it is for the tools that touch a sound effect from
/// outside and to look at what the allocation decided.
pub fn effects_json(music: &Music, sounds: &[(String, i64, i64, i64)], rates: &Value) -> Value {
    let mut srcn = Map::new();
    for e in &music.effects {
        srcn.insert(e.name.clone(), json!(music.srcn(&e.name)));
    }
    json!({
        "sounds": sounds.iter().map(|(n, v, t, b)| json!([n, v, t, b])).collect::<Vec<_>>(),
        "srcn": srcn,
        "rates": rates,
    })
}

/// What `[music] apart_themes` says: {map: its separate songs}.
pub fn apart_themes(list: &[toml::Value]) -> Result<HashMap<i64, HashSet<String>>> {
    let bad = || Bad::usage("[music] apart_themes: each one is {map = N, themes = [...]}".to_string());
    let mut out = HashMap::new();
    for entry in list {
        let map = entry.get("map").and_then(toml::Value::as_integer).ok_or_else(bad)?;
        let themes = entry
            .get("themes")
            .and_then(toml::Value::as_array)
            .ok_or_else(bad)?
            .iter()
            .map(|t| t.as_str().map(String::from).ok_or_else(bad))
            .collect::<Result<HashSet<_>>>()?;
        out.insert(map, themes);
    }
    Ok(out)
}

/// What `[music] jumps_that_never_happen` says: (map, destination) pairs.
pub fn never_happen(list: &[toml::Value]) -> Result<Vec<(i64, i64)>> {
    let bad = || Bad::usage("[music] jumps_that_never_happen: each one is [map, destination]".to_string());
    list.iter()
        .map(|p| {
            let pair = p.as_array().ok_or_else(bad)?;
            let n = |k: usize| pair.get(k).and_then(toml::Value::as_integer).ok_or_else(bad);
            Ok((n(0)?, n(1)?))
        })
        .collect()
}

/// The ROM's `BOOT_FRAMES_FLOOR`, read from its source: it belongs to the
/// ROM and not here. The ROM waits until `BOOT_FRAMES` so that the loop
/// always starts on the same frame, and each cartridge carries its own:
/// this floor or the boot estimate, whichever is larger —see
/// `boot_frames`—. See the comment on it in `far_ram.s`.
pub fn boot_frames_floor(far_ram: &str) -> Option<i64> {
    far_ram.lines().find_map(|l| {
        let rest = l.strip_prefix("BOOT_FRAMES_FLOOR")?;
        let value = rest.trim_start().strip_prefix('=')?.trim_start();
        let digits: String = value.chars().take_while(char::is_ascii_digit).collect();
        digits.parse().ok()
    })
}

/// The cartridge's `BOOT_FRAMES`: the floor, or the estimate rounded up if
/// it goes over. `None` if it doesn't fit in the byte the ROM compares it
/// with —`boot_frames`, in `low_ram.s`—.
///
/// Until 2026-10-11 it was a constant of the ROM and the converter stopped
/// if the estimate went over it: raising it for one game's boot map moved
/// the loop's frame in every cartridge.
pub fn boot_frames(floor: i64, estimate: f64) -> Option<i64> {
    let frames = floor.max(estimate.ceil() as i64);
    (frames <= 255).then_some(frames)
}

/// The sound effects of one package's quality versions, by rate, from the
/// highest: "16000 Hz: 2, 6500 Hz: 18".
pub fn rates_line(theirs: &Map<String, Value>) -> String {
    let mut count: BTreeMap<i64, usize> = BTreeMap::new();
    for v in theirs.values() {
        *count.entry(v.as_i64().unwrap_or(0)).or_default() += 1;
    }
    count.iter().rev().map(|(t, n)| format!("{t} Hz: {n}")).collect::<Vec<_>>().join(", ")
}

#[cfg(test)]
mod tests {
    use super::*;

    const K: usize = 0; // Kfmus5
    const G: usize = 1; // golden_axe
    const T: usize = 2; // tsmedit
    const V: usize = 3; // vswar

    fn songs(per_map: &[(usize, &[usize], &[usize])], exits: &[(usize, &[usize])], jumps: &[(usize, &[(usize, &[Option<usize>])])]) -> Songs {
        Songs {
            names: vec!["K".into(), "G".into(), "T".into(), "V".into()],
            per_package: per_map
                .iter()
                .map(|&(m, s, d)| (Key::Map(m), Wants { songs: s.to_vec(), sounds: vec![], destinations: d.to_vec() }))
                .collect(),
            exits: exits.iter().map(|&(m, e)| (Key::Map(m), e.iter().map(|&t| (t, true)).collect())).collect(),
            jumps: jumps
                .iter()
                .map(|&(m, j)| (Key::Map(m), j.iter().map(|&(d, s)| (d, s.to_vec())).collect()))
                .collect(),
            ..Songs::default()
        }
    }

    fn inheritance(s: &Songs, n: usize, separate: &[Vec<usize>]) -> BTreeSet<(usize, usize)> {
        let names: Vec<String> = (0..n).map(|i| i.to_string()).collect();
        inherited_songs(s, &vec![NONE; n], 0, NONE, &names, None, separate, &[])
            .into_iter()
            .map(|(p, t)| (p.parse().unwrap(), t))
            .collect()
    }

    /// 37 (1) starts K and jumps to 41 (2). 41 starts G only to go back to
    /// 37, and with no song jumps to 40 (3); 40 starts T only to go back to
    /// 41, and with no song jumps to the vidcasts (4), which go back to 40.
    /// K arrives playing at 40 and at the vidcasts; G leaves 41 only for 37;
    /// T arrives at 41. It happened with `Kfmus5`: the rule "a map with
    /// `PlayBGM` leaves with one of its own" carried G and T to all the
    /// destinations of 41 and 40 instead of what was playing.
    #[test]
    fn a_map_that_only_starts_exit_songs_lets_the_previous_through() {
        let s = songs(
            &[(0, &[], &[1]), (1, &[K], &[2]), (2, &[G], &[1, 3]), (3, &[T], &[2, 4]), (4, &[], &[3])],
            &[(2, &[G]), (3, &[T])],
            &[
                (2, &[(1, &[Some(G)]), (3, &[None])]),
                (3, &[(2, &[Some(T), None]), (4, &[None])]),
                (4, &[(3, &[None])]),
            ],
        );
        let got = inheritance(&s, 5, &[]);
        for map in [3, 4] {
            assert!(got.contains(&(map, K)), "K is playing on arrival at map {map} and the package does not count it");
        }
        assert!(!got.contains(&(3, G)), "G only plays to go back to 37 and 40 inherits it anyway");
        assert!(got.contains(&(2, T)) && got.contains(&(1, G)));
    }

    /// The same 41 as the starting map —the router— leaves only with its
    /// exit song: whatever enters there would go out anywhere.
    #[test]
    fn the_boot_map_keeps_the_usual_rule() {
        let s = songs(
            &[(0, &[G], &[1, 2]), (1, &[K], &[0]), (2, &[], &[])],
            &[(0, &[G])],
            &[(0, &[(1, &[Some(G)]), (2, &[None])]), (1, &[(0, &[None])])],
        );
        let got = inheritance(&s, 3, &[]);
        assert!(!got.contains(&(2, K)) && got.contains(&(2, G)));
    }

    /// 38 (1) starts V in a scene and G before leaving: with V separate, G
    /// and not V reaches the maps it exits to.
    #[test]
    fn a_separate_song_does_not_leave_its_map() {
        let s = songs(&[(0, &[], &[1]), (1, &[V, G], &[2]), (2, &[], &[])], &[], &[(1, &[(2, &[None])])]);
        assert!(inheritance(&s, 3, &[]).contains(&(2, V)));
        let got = inheritance(&s, 3, &[vec![], vec![V], vec![]]);
        assert!(!got.contains(&(2, V)) && got.contains(&(2, G)));
    }

    #[test]
    fn the_floor_is_read_from_the_source() {
        assert_eq!(boot_frames_floor("X = 1\nBOOT_FRAMES_FLOOR = 40   ; why\n"), Some(40));
        assert_eq!(boot_frames_floor("; BOOT_FRAMES_FLOOR = 40\n"), None);
        assert_eq!(boot_frames_floor("BOOT_FRAMES = 40\n"), None);
    }

    /// A small package keeps the floor, so a cartridge like that starts on
    /// the frame it always did; a large one gets its estimate, rounded up.
    #[test]
    fn boot_frames_is_the_floor_or_the_estimate() {
        assert_eq!(boot_frames(44, 34.2), Some(44));
        assert_eq!(boot_frames(44, 44.0), Some(44));
        assert_eq!(boot_frames(44, 45.1), Some(46));
        assert_eq!(boot_frames(44, 255.0), Some(255));
        assert_eq!(boot_frames(44, 255.5), None);
    }
}
