//! Every song of a cartridge, sharing a single sample bank: [`build`].
//!
//! **Every requested song goes in the cartridge, with all its samples.** An
//! index costs no ARAM: it costs its stream, which lives in the cartridge.
//! What competes for the ARAM is the samples, and that is allocated per
//! package —one per map—: see [`crate::bank`].

use crate::bank::{self, Assignment, Bank, Group, Key, Samples};
use crate::effects::{self, SoundEffect};
use crate::fail::{Bad, Result};
use crate::game::Game;
use crate::midi::{self, TICKS_PER_SECOND};
use rm2k_snes_bytecode::music::OP_END;
use crate::sdsp;
use crate::song::{self, Parsed};
use crate::spc700;
use crate::stream::{self, Sound, Write};
use crate::voices::{self, Allotted, Instruments, SampleInfo};
use sha2::{Digest, Sha256};
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet, HashMap};

/// An audio package, as the cartridge's compiler hands it over: its songs,
/// by index; its sound effects, by name, in the order the ROM uploads them;
/// its exit songs —which its `PlayBGM` uploads alone, silencing the rest—;
/// and its separate songs —which their `PlayBGM` uploads alone with the
/// package's sound effects—.
#[derive(Clone, Debug, Default)]
pub struct Package {
    pub name: String,
    pub songs: Vec<usize>,
    pub effects: Vec<String>,
    pub exits: Vec<usize>,
    pub separate: Vec<usize>,
}

/// What the music has to know to build a cartridge's music.
#[derive(Clone, Debug, Default)]
pub struct Job {
    /// The songs, in the order the bytecode already numbers them.
    pub songs: Vec<String>,
    /// The sound effects, from most to least requested.
    pub effects: Vec<String>,
    /// The packages; without them, each song is a package without sound
    /// effects.
    pub packages: Option<Vec<Package>>,
    /// (package, song that may be playing when it loads): the package's
    /// samples have to fit alongside that song's —the sound effects do not:
    /// they wait for the next `PlayBGM`—.
    pub inheritance: Vec<(String, usize)>,
    /// Every song's headroom, instead of its measured ceiling: what the
    /// ceilings are measured with.
    pub measuring_headroom: Option<f64>,
    /// The songs the database's `System` names, for the MSU-1 numbering.
    pub system_songs: Vec<String>,
    /// And every song the game's events and maps name: see
    /// [`crate::game::Game::track_numbers`].
    pub named_songs: Vec<String>,
    /// Up to where the ARAM holds samples. Only the tests change it.
    pub aram_end: i64,
}

/// A song, built.
#[derive(Clone, Debug)]
pub struct Built {
    pub name: String,
    pub stream: Vec<u8>,
    pub sounds: Vec<Sound>,
    pub writes: Vec<Write>,
    /// None for a song without a MIDI.
    pub headroom: Option<f64>,
    pub fingerprint: Option<String>,
    pub seconds: f64,
    /// The MSU-1 track, if it has something to come from.
    pub track: Option<u8>,
    /// What fraction of its notes has its sample, and what fraction of the
    /// note-time is lost for lack of voices —and would be lost with any rule—.
    pub notes_sound: Option<f64>,
    pub lost: Option<(f64, f64)>,
    pub allocation: Vec<Allotted>,
    pub parsed: Option<Parsed>,
}

impl Built {
    /// How long it lasts: one frame past its last write.
    pub fn length(&self) -> i64 {
        self.writes.last().map_or(0, |w| w.0 + 1)
    }

    /// Which samples it uses: the values its stream writes to SRCN.
    pub fn samples(&self) -> Result<Vec<u8>> {
        stream::samples_of(&self.stream, &self.sounds)
    }
}

/// The music of a cartridge.
pub struct Music {
    pub driver: Vec<u8>,
    pub bank: Bank,
    pub songs: Vec<Built>,
    /// The sound effects, in the order they were requested: each one's
    /// number is its place here.
    pub effects: Vec<SoundEffect>,
    /// Each sound effect's place among the directory entries they share.
    pub place: BTreeMap<String, usize>,
    /// How many places they share.
    pub places: usize,
    pub packages: Vec<Package>,
    /// Up to where the ARAM holds samples: the job's.
    pub aram_end: i64,
}

impl Music {
    /// A sound effect's SRCN: its place after the music's samples.
    pub fn srcn(&self, effect: &str) -> Option<usize> {
        self.place.get(effect).map(|p| self.bank.voices.len() + p)
    }

    /// A sound effect's number.
    pub fn effect_id(&self, effect: &str) -> Option<usize> {
        self.effects.iter().position(|e| e.name == effect)
    }

    /// Every sample of the cartridge, numbered: the music's, followed by the
    /// sound effects.
    pub fn all_samples(&self) -> Vec<(&[u8], usize)> {
        self.bank
            .voices
            .iter()
            .map(|v| (v.data.as_slice(), v.loop_block))
            .chain(self.effects.iter().map(|e| (e.data.as_slice(), e.loop_block)))
            .collect()
    }
}

/// A song's view of the bank: its programs and its hits point to the
/// samples it was given, copies included.
struct SongBank<'a> {
    bank: &'a Bank,
    samples: &'a Samples,
    melodic: BTreeMap<u8, usize>,
    hits: BTreeMap<u8, usize>,
    envelopes: &'a RefCell<HashMap<(u8, u8), (u8, u8, u8)>>,
}

impl Instruments for SongBank<'_> {
    fn sample(&self, index: usize) -> SampleInfo {
        let v = &self.bank.voices[index];
        SampleInfo { root: v.root as f64, rate: v.rate, frames: v.frames as i64 }
    }
    fn melodic(&self, program: u8) -> Option<usize> {
        self.melodic.get(&program).copied()
    }
    fn hit(&self, key: u8) -> Option<usize> {
        self.hits.get(&key).copied()
    }
    fn envelope(&self, program: u8, key: u8) -> Result<(u8, u8, u8)> {
        if let Some(e) = self.envelopes.borrow().get(&(program, key)) {
            return Ok(*e);
        }
        let e = self.samples.envelope(program, key)?;
        self.envelopes.borrow_mut().insert((program, key), e);
        Ok(e)
    }
}

/// What a song's peak depends on, summarized: what it writes to the DSP
/// —with its headroom already applied— and the samples it plays, with their
/// loop. Whatever changes this can move the peak, and the table of volume
/// ceilings stores it so the game knows whether what was measured is still
/// what plays. The driver does not count: it mixes nothing.
///
/// The writes go in as Python's `repr` of a list of tuples, because that is
/// how the fingerprints in that table were taken.
pub fn mix_fingerprint(writes: &[Write], bank: &Bank) -> String {
    let mut text = String::from("[");
    for (i, (f, r, v)) in writes.iter().enumerate() {
        if i > 0 {
            text.push_str(", ");
        }
        text.push_str(&format!("({f}, {r}, {v})"));
    }
    text.push(']');
    let mut h = Sha256::new();
    h.update(text.as_bytes());
    let used: BTreeSet<u8> = writes
        .iter()
        .filter(|(_, r, _)| *r < 0x80 && r & 0x0F == sdsp::V_SRCN)
        .map(|w| w.2)
        .collect();
    for i in used {
        if let Some(v) = bank.voices.get(i as usize) {
            h.update(format!("{i}:{}:", v.loop_block).as_bytes());
            h.update(&v.data);
        }
    }
    h.finalize().iter().map(|b| format!("{b:02x}")).collect::<String>()[..16].to_string()
}

/// That the extra space the whole sound effects take fits, in each package,
/// in what the music left free: the bank is already allocated without
/// counting it, so if it does not fit there is nobody to take it from
/// without lowering an instrument's rate, and this stops saying which one.
///
/// And it says —without stopping— with which song that may be playing a
/// package's sound effects used to fit alongside at their usual size and no
/// longer fit whole: there they wait for the next `PlayBGM`.
#[allow(clippy::too_many_arguments)]
fn whole_effects_fit(
    bank: &Bank,
    packages: &[Package],
    inheritance: &[(String, usize)],
    effects: &BTreeMap<String, SoundEffect>,
    budgeted: &BTreeMap<String, i64>,
    names: &[String],
    whole: &BTreeMap<String, i64>,
    paid: &BTreeSet<String>,
) -> Result<()> {
    let mut keys_of: HashMap<&str, BTreeSet<Key>> = HashMap::new();
    for p in packages {
        keys_of.insert(&p.name, p.songs.iter().flat_map(|&t| bank.keys_of(t)).collect());
    }
    fn own_effects<'a>(p: &'a Package, effects: &BTreeMap<String, SoundEffect>) -> BTreeSet<&'a String> {
        p.effects.iter().filter(|e| effects.contains_key(*e)).collect()
    }
    let mut not_fitting = Vec::new();
    for p in packages {
        let own = own_effects(p, effects);
        let whole_ones: Vec<&str> = own
            .iter()
            .filter(|e| whole.contains_key(**e) && !paid.contains(**e))
            .map(|e| e.as_str())
            .collect();
        if whole_ones.is_empty() {
            continue;
        }
        let effect_bytes: i64 = own.iter().map(|e| effects[*e].data.len() as i64).sum();
        // The package, and each of its separate songs, which is uploaded with
        // the same sound effects.
        let mut cases: Vec<Option<usize>> = vec![None];
        cases.extend(p.separate.iter().map(|&t| Some(t)));
        for case in cases {
            let music = match case {
                None => bank.takes(&keys_of[p.name.as_str()]),
                Some(t) => bank.takes(&bank.keys_of(t)),
            };
            if music + effect_bytes > bank.free {
                not_fitting.push(format!(
                    "{} in package {}{} ({} B over)",
                    whole_ones.join(", "),
                    p.name,
                    case.map_or(String::new(), |t| format!(">{}", names[t])),
                    music + effect_bytes - bank.free
                ));
            }
        }
    }
    if !not_fitting.is_empty() {
        return Err(Bad::answer(format!(
            "the whole sound effects do not fit without lowering an instrument's rate: {}. \
             Lower their rate in [sound_effects.whole], or remove them",
            not_fitting.join("; ")
        )));
    }
    let mut effects_of: HashMap<&str, BTreeSet<&String>> = HashMap::new();
    for p in packages {
        effects_of.insert(&p.name, own_effects(p, effects));
    }
    for (name, inherited) in inheritance {
        let own = &effects_of[name.as_str()];
        if !own.iter().any(|e| whole.contains_key(*e) && !paid.contains(*e)) {
            continue;
        }
        let keys: BTreeSet<Key> =
            keys_of[name.as_str()].iter().cloned().chain(bank.keys_of(*inherited)).collect();
        let music = bank.takes(&keys);
        let before = music + own.iter().map(|e| budgeted[*e]).sum::<i64>();
        let now = music + own.iter().map(|e| effects[*e].data.len() as i64).sum::<i64>();
        if before <= bank.free && bank.free < now {
            println!(
                "  with {} playing, the whole sound effects of package {name} do not fit \
                 alongside: they wait for the PlayBGM",
                names[*inherited]
            );
        }
    }
    Ok(())
}

/// The same stop, saying in its own line which song it is about and which
/// packages carry it —a map's is named by its number—: whoever reads it is
/// about to leave a map out of the cartridge, and which one is what they
/// need. A `compile` job without packages gives each song its own, named
/// as the song, and that says nothing more.
fn in_song(bad: Bad, packages: &[Package], i: usize, name: &str) -> Bad {
    let carry: Vec<String> = packages
        .iter()
        .filter(|p| p.name != name && (p.songs.contains(&i) || p.exits.contains(&i) || p.separate.contains(&i)))
        .map(|p| if p.name.parse::<i64>().is_ok() { format!("map {}", p.name) } else { format!("package {}", p.name) })
        .collect();
    let whose = if carry.is_empty() { format!("song {name:?}") } else { format!("song {name:?}, in {}", carry.join(", ")) };
    match bad {
        Bad::Answer(m) => Bad::Answer(format!("{whose}: {m}")),
        Bad::Usage(m) => Bad::Usage(format!("{whose}: {m}")),
    }
}

/// Every song of the cartridge, sharing a single sample bank.
pub fn build(job: &Job, game: &Game, samples: &Samples) -> Result<Music> {
    let names = &job.songs;
    let driver = spc700::driver();
    let ceilings = game.ceilings()?;
    let whole = game.whole_effects()?;
    let paid = game.paid_by_music()?;

    let parsed: Vec<Option<Parsed>> =
        names.iter().map(|n| song::read(n, game)).collect::<Result<_>>()?;
    let root_keys = bank::most_used_zones(&parsed, &samples.font);
    let keys_of: Vec<BTreeSet<Key>> =
        parsed.iter().map(|p| bank::song_keys(p.as_ref(), &root_keys)).collect();

    // **All** the sound effects go in: which ones fit is decided by the ROM
    // map by map, when it builds its audio package. They are built before
    // the bank because what each package's take is the first thing
    // subtracted.
    let mut effect_list: Vec<SoundEffect> = Vec::new();
    let mut wavs: HashMap<String, Option<(Vec<i64>, i64)>> = HashMap::new();
    for name in &job.effects {
        if effect_list.iter().any(|e| &e.name == name) || wavs.contains_key(name) {
            continue;
        }
        let wav = effects::wav_of(game, name);
        if let Some(e) = effects::build(name, wav.as_ref(), effects::SE_RATE, &whole)? {
            effect_list.push(e);
        }
        wavs.insert(name.clone(), wav);
    }
    let built_effects: BTreeMap<String, SoundEffect> =
        effect_list.iter().map(|e| (e.name.clone(), e.clone())).collect();
    // What the music budgets for each sound effect: the usual one, even if
    // it goes whole.
    let mut budgeted: BTreeMap<String, i64> =
        built_effects.iter().map(|(n, e)| (n.clone(), e.data.len() as i64)).collect();
    for n in built_effects.keys() {
        if whole.contains_key(n) && !paid.contains(n) {
            let usual = effects::build(n, wavs[n].as_ref(), effects::SE_RATE, &BTreeMap::new())?
                .expect("it was built once");
            budgeted.insert(n.clone(), usual.data.len() as i64);
        }
    }

    // The keys the SoundFont has; the rest do not play anywhere.
    let mut keys_of_present = Vec::new();
    for ks in &keys_of {
        let mut present = BTreeSet::new();
        for k in ks {
            if samples.sample(k, bank::NATIVE)?.is_some() {
                present.insert(k.clone());
            }
        }
        keys_of_present.push(present);
    }
    let packages: Vec<Package> = job.packages.clone().unwrap_or_else(|| {
        names
            .iter()
            .enumerate()
            .map(|(i, n)| Package { name: n.clone(), songs: vec![i], ..Default::default() })
            .collect()
    });

    // What has to fit together: each package with its sound effects; each
    // exit song alone; and each package with the song that may be playing
    // when it loads, without its sound effects. And the same ones with what
    // the sound effects really take, which is what the copies that lower no
    // one allocate with.
    let (mut groups, mut real) = (Vec::new(), Vec::new());
    let mut songs_of: HashMap<&str, Vec<usize>> = HashMap::new();
    for p in &packages {
        songs_of.insert(&p.name, p.songs.clone());
        let own: BTreeSet<&String> = p.effects.iter().filter(|e| built_effects.contains_key(*e)).collect();
        let effect_bytes: i64 = own.iter().map(|e| budgeted[*e]).sum();
        let real_bytes: i64 = own.iter().map(|e| built_effects[*e].data.len() as i64).sum();
        groups.push(Group { name: p.name.clone(), songs: p.songs.clone(), effect_bytes });
        real.push(Group { name: p.name.clone(), songs: p.songs.clone(), effect_bytes: real_bytes });
        for &t in &p.exits {
            let g = Group { name: format!("{}>{}", p.name, names[t]), songs: vec![t], effect_bytes: 0 };
            groups.push(g.clone());
            real.push(g);
        }
        for &t in &p.separate {
            let name = format!("{}>{}", p.name, names[t]);
            groups.push(Group { name: name.clone(), songs: vec![t], effect_bytes });
            real.push(Group { name, songs: vec![t], effect_bytes: real_bytes });
        }
    }
    for (name, inherited) in &job.inheritance {
        let mut songs = songs_of
            .get(name.as_str())
            .cloned()
            .ok_or_else(|| Bad::usage(format!("inheritance names package {name:?}, which is not one")))?;
        songs.push(*inherited);
        let g = Group { name: format!("{name}+{}", names[*inherited]), songs, effect_bytes: 0 };
        groups.push(g.clone());
        real.push(g);
    }
    let effect_names: Vec<String> = effect_list.iter().map(|e| e.name.clone()).collect();
    let place = bank::effect_places(
        &packages.iter().map(|p| p.effects.clone()).collect::<Vec<_>>(),
        &effect_names,
    );
    let places = place.values().max().map_or(0, |m| m + 1);
    // SRCN is one byte: what does not fit in the directory next to the
    // sound effects' places is left out, and it is silent like a key the
    // SoundFont lacks.
    let dropped = bank::drop_surplus(&mut keys_of_present, bank::DIRECTORY_MAX - places as i64);
    if !dropped.is_empty() {
        println!(
            "  WARNING, the directory holds {} samples and the music asks for {}: {} left out, so the \
             notes that use them are silent (the least used, ties by key order): {}",
            bank::DIRECTORY_MAX - places as i64,
            bank::DIRECTORY_MAX - places as i64 + dropped.len() as i64,
            dropped.len(),
            dropped.iter().map(|k| format!("{k:?}")).collect::<Vec<_>>().join(", ")
        );
    }
    // Never fewer than the places the effects really take: the copies
    // would fill the directory the sound effects need.
    let usual = (effect_list.len() as i64).min(game.effect_slots_of_first_copies()?).max(places as i64);
    let assignment: Assignment =
        bank::copies(samples, &keys_of_present, &groups, places as i64, usual, &real, job.aram_end)?;
    let all_keys: BTreeSet<Key> = assignment.iter().flat_map(|a| a.values().cloned()).collect();
    let free = bank::free_for(all_keys.len() as i64, places as i64, job.aram_end);
    let constraints = bank::constraints_for(&assignment, &real, free);
    let bank = Bank::new(samples, &all_keys, constraints, free, assignment)?;
    whole_effects_fit(&bank, &packages, &job.inheritance, &built_effects, &budgeted, names, &whole, &paid)?;

    let tracks = game.track_numbers(&job.system_songs, &job.named_songs)?;
    let envelopes = RefCell::new(HashMap::new());
    let mut songs = Vec::new();
    for (i, (name, parsed)) in names.iter().zip(parsed).enumerate() {
        let track = if name.is_empty() { None } else { tracks.get(&name.to_lowercase()).copied() };
        let Some(parsed) = parsed else {
            songs.push(Built {
                name: name.clone(),
                stream: vec![OP_END],
                sounds: Vec::new(),
                writes: Vec::new(),
                headroom: None,
                fingerprint: None,
                seconds: 0.0,
                track,
                notes_sound: None,
                lost: None,
                allocation: Vec::new(),
                parsed: None,
            });
            continue;
        };
        let headroom = job
            .measuring_headroom
            .filter(|h| *h != 0.0)
            .unwrap_or_else(|| *ceilings.get(name).unwrap_or(&sdsp::HEADROOM));
        let (melodic, hits) = bank.for_song(i);
        let view = SongBank { bank: &bank, samples, melodic, hits, envelopes: &envelopes };
        let mut allocation = Vec::new();
        let frames = voices::build_events(
            &parsed.notes,
            &parsed.voices,
            &parsed.programs,
            &view,
            &parsed.controls,
            Some(&mut allocation),
            headroom,
        )
        .map_err(|e| in_song(e, &packages, i, name))?;
        let init = stream::init_writes();
        let reference = stream::writes(&frames, parsed.length, &init);
        let (flat, sounds) = stream::pack(&frames, parsed.length, &init).map_err(|e| in_song(e, &packages, i, name))?;
        stream::check(name, &flat, &sounds, &reference)?;
        // The same, with what it repeats read from where it first said it:
        // the writes are checked again, following the repeats as the 65816
        // does, write by write and frame by frame.
        let bytes = stream::fold(&flat).map_err(|e| in_song(e, &packages, i, name))?;
        stream::check(name, &bytes, &sounds, &reference)?;
        let fingerprint = mix_fingerprint(&reference, &bank);
        // How many of its notes reach the stream. A note whose program is not
        // in the bank **does not play quieter: it does not exist**.
        let (mut total, mut sounding) = (0usize, 0usize);
        for note in &parsed.notes {
            if !parsed.voices.contains_key(&note.channel) {
                continue;
            }
            total += 1;
            let has = if note.channel == midi::DRUM_CHANNEL {
                view.hits.contains_key(&note.pitch)
            } else {
                view.melodic.contains_key(&parsed.program(note.channel))
            };
            sounding += has as usize;
        }
        songs.push(Built {
            name: name.clone(),
            stream: bytes,
            sounds,
            headroom: Some(headroom),
            fingerprint: Some(fingerprint),
            seconds: parsed.length as f64 / TICKS_PER_SECOND as f64,
            track,
            notes_sound: Some(sounding as f64 / total.max(1) as f64),
            lost: Some(voices::lost_time(&allocation, &parsed.notes)),
            writes: reference,
            allocation,
            parsed: Some(parsed),
        });
    }
    Ok(Music { driver, bank, songs, effects: effect_list, place, places, packages, aram_end: job.aram_end })
}

/// What the cartridge's compiler prints about the music: each song, the
/// shared bank, and what each package has left over.
pub fn report(music: &Music, boot: Option<usize>) -> Vec<String> {
    let mut out = Vec::new();
    for (i, song) in music.songs.iter().enumerate() {
        // The percentage of notes that reach the stream goes here and not
        // hidden: it is what is heard as "it's missing voices".
        let sound = song.notes_sound;
        // And how much of what does have a sample is lost for lack of
        // voices, against what would be lost with no remedy with eight.
        let (lost, floor) = song.lost.unwrap_or((0.0, 0.0));
        out.push(format!(
            "  {i}. {:<16} {:4.0} s, {:6} B of stream and {:4} of sounds, {} of the notes, \
             {:.0}% of note-time without a voice (floor {:.0}%){}",
            song.name,
            song.seconds,
            song.stream.len(),
            6 * song.sounds.len(),
            match sound {
                Some(s) if s <= 0.999 => format!("{:.0}%", 100.0 * s),
                _ => "all".to_string(),
            },
            100.0 * lost,
            100.0 * floor,
            if Some(i) == boot { ", plays from boot" } else { "" }
        ));
    }
    if music.songs.is_empty() {
        return out;
    }
    let bank = &music.bank;
    out.push(format!(
        "  shared bank: {} samples, {} B in the cartridge; each package has {} B of ARAM for its \
         samples",
        bank.voices.len(),
        bank.voices.iter().map(|v| v.data.len()).sum::<usize>(),
        bank.free
    ));
    // What rate each sample ended up at and which package limited it: it is
    // what is heard, and what says where to look for room if needed. A key
    // with copies comes out once per copy, with the songs that use it.
    let mut use_: HashMap<&Key, Vec<&str>> = HashMap::new();
    for (song, its) in music.songs.iter().zip(&bank.assignment) {
        for sample in its.values() {
            use_.entry(sample).or_default().push(&song.name);
        }
    }
    for (key, voice) in bank.keys.iter().zip(&bank.voices) {
        let copied = key.is_copy() || bank.keys.iter().any(|k| k != key && key.is_prefix_of(k));
        let name: String = voice.name.trim().chars().take(10).collect();
        out.push(format!(
            "    {} {:3} {:<10} {:5.1} kHz, {:5} B{}{}{}",
            if key.is_hit() { "hit     " } else { "program " },
            key.number(),
            name,
            voice.rate / 1000.0,
            voice.data.len(),
            if key.is_hit() { String::new() } else { format!(", root {}", voice.root) },
            bank.limited_by.get(key).map_or(String::new(), |n| format!(", limited by {n}")),
            if copied {
                format!(", for {}", use_.get(key).map_or(String::new(), |u| u.join(" ")))
            } else {
                String::new()
            }
        ));
    }
    // And how much each package has left over, with its sound effects: the
    // whole ones with what they really take.
    for r in &bank.constraints {
        let takes = bank.takes(&r.keys);
        let name: String = r.name.chars().take(28).collect();
        out.push(format!(
            "    package {name:<28} {takes:5} B of samples, {:5} left over",
            r.free - takes
        ));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_song_that_stops_says_which_maps_carry_it() {
        let package = |name: &str, songs: Vec<usize>, separate: Vec<usize>| Package {
            name: name.into(),
            songs,
            separate,
            ..Default::default()
        };
        let packages = [
            package("10", vec![0, 1], vec![]),
            package("12", vec![0], vec![]),
            package("63", vec![], vec![1]),
            package("pelea", vec![1], vec![]),
        ];
        assert_eq!(
            in_song(Bad::answer("too many"), &packages, 1, "Boss").to_string(),
            "song \"Boss\", in map 10, map 63, package pelea: too many"
        );
        // A `compile` job: each song its own package, named as the song.
        assert_eq!(
            in_song(Bad::usage("x"), &[package("Boss", vec![0], vec![])], 0, "Boss"),
            Bad::usage("song \"Boss\": x")
        );
    }
}
