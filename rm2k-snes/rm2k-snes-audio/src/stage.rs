//! The music as a stage of a converter: what `cartridge` answers, as the
//! files it makes, by name. The converter calls [`cartridge`] as a
//! function; `compile`, which only a person or a test runs, goes through
//! the same [`compile`].
//!
//! **It writes nothing**: what goes beside the cartridge and the `.msu`
//! come back as [`Files`], and whoever called it writes them where they go. **What it
//! says goes to standard output**, as it did when it was a process whose
//! output went out with the converter's: the lines `compile`'s library
//! prints while it decides —a package that does not fit, a directory that
//! drops samples— are printed from deep inside it, and are not an answer.
//!
//! The converter does not keep its answer in its cache: it is one per
//! cartridge, and it reads the runtime's `far_ram.s` (see
//! `cartridge::boot_frames_floor`), which its flags do not name.

use crate::bank::{self, Key, Samples};
use crate::cartridge::{self, Cartridge};
use crate::fail::{Bad, Result};
use crate::game::Game;
use crate::relief::Loss;
use crate::samples::SoundFontSamples;
use crate::{compile as compiler, emit, job, msu, msu_data};
use ditto::dump::Dump;
use ditto::schema::System;
use rm2k_project::{outln, suite, Project};
use rm2k_rules::tree::Tree;
use rm2k_snes_bytecode::level::Level;
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// What a command answers: every file it makes, by name.
pub type Files = BTreeMap<String, Vec<u8>>;

/// The name the `.msu` goes by among [`cartridge`]'s files: it does not go
/// into `--out` with the rest, but where `--msu` says.
pub const MSU: &str = ".msu";

/// Where the game, its RTP and its project are, as the binary's flags give
/// them.
#[derive(Debug, Clone, Default)]
pub struct Place {
    pub game_dir: PathBuf,
    pub rtp_dir: Option<PathBuf>,
    /// The directory where `advocate.toml` is; without it, it is looked up
    /// from the current directory upwards.
    pub project: Option<PathBuf>,
}

impl Place {
    pub fn game(&self) -> Result<Game> {
        Ok(Game {
            game_dir: self.game_dir.clone(),
            rtp_dir: self.rtp_dir.clone(),
            project: Project::locate(self.project.as_deref())?,
        })
    }
}

/// What [`cartridge`] reads besides its request: the binary's flags.
#[derive(Debug, Clone)]
pub struct Flags {
    pub place: Place,
    /// The game's Ditto dump: the map tree and the database's System.
    pub data: PathBuf,
    /// The bank the samples come from.
    pub soundfont: PathBuf,
    /// Where the files and the `.msu` are going to be written. Only what it
    /// prints names them: it writes nothing there.
    pub out: PathBuf,
    pub msu: PathBuf,
}

/// What a person may open: indented, with a newline at the end.
pub fn pretty(value: &Value) -> String {
    serde_json::to_string_pretty(value).expect("a value is JSON") + "\n"
}

fn hex(data: &[u8]) -> String {
    data.iter().map(|b| format!("{b:02x}")).collect()
}

/// A job's music, compiled: what `audio.json` says, and with `emit`, the
/// sound effects' MSU-1 versions.
pub struct Compiled {
    pub music: compiler::Music,
    pub audio: Map<String, Value>,
    pub quality: Option<msu::Effects>,
    /// With `emit`, `musicdata.inc` and `music.json`. `audio.json` is the
    /// caller's to write, with whatever it adds.
    pub files: Files,
}

/// Compiles a job: `musicdata.inc` and `music.json` with `emit`, and what
/// each song and the bank came out as, to standard output.
pub fn compile(
    job: &compiler::Job,
    emit: Option<&emit::Emit>,
    game: &Game,
    soundfont: &Path,
    detail: bool,
) -> Result<Compiled> {
    let samples = Samples {
        font: SoundFontSamples::open(soundfont)?,
    };
    let music = compiler::build(job, game, &samples)?;
    // What a package lost to fit in the ARAM, said here and in `audio.json`
    // —`losses`—; `cartridge` also answers them, for `degradations.json`.
    // See `relief`.
    for loss in &music.losses {
        outln!("  WARNING, {}", loss.text);
    }

    let bank = &music.bank;
    let mut out = Map::new();
    out.insert(
        "songs".into(),
        music
            .songs
            .iter()
            .map(|t| {
                let mut s = json!({
                    "name": t.name,
                    "track": t.track,
                    "samples": t.samples()?,
                    "seconds": t.seconds,
                    "stream": t.stream.len(),
                    "sounds": t.sounds.len(),
                    "headroom": t.headroom,
                    "fingerprint": t.fingerprint,
                    "notes_sound": t.notes_sound,
                    "lost": t.lost.map(|(l, f)| vec![l, f]),
                    "length": t.length(),
                });
                if detail {
                    let m = s.as_object_mut().unwrap();
                    m.insert("writes".into(), json!(t.writes));
                    if let Some(p) = &t.parsed {
                        m.insert(
                            "notes".into(),
                            json!(p
                                .notes
                                .iter()
                                .map(|n| (n.start, n.end, n.channel, n.pitch, n.velocity))
                                .collect::<Vec<_>>()),
                        );
                        m.insert(
                            "programs".into(),
                            Value::Object(
                                p.programs
                                    .iter()
                                    .map(|(c, p)| (c.to_string(), json!(p)))
                                    .collect(),
                            ),
                        );
                    }
                    m.insert(
                        "allocation".into(),
                        json!(t
                            .allocation
                            .iter()
                            .map(|a| (a.note, a.voice, a.stolen, a.end))
                            .collect::<Vec<_>>()),
                    );
                }
                Ok(s)
            })
            .collect::<Result<Vec<Value>>>()?
            .into(),
    );
    out.insert(
        "effects".into(),
        music
            .effects
            .iter()
            .map(|e| {
                json!({"name": e.name, "srcn": music.srcn(&e.name), "bytes": e.data.len(),
                       "rate": e.rate, "repeats": e.repeats})
            })
            .collect::<Vec<_>>()
            .into(),
    );
    out.insert("free".into(), json!(bank.free));
    out.insert("places".into(), json!(music.places));
    out.insert(
        "losses".into(),
        music
            .losses
            .iter()
            .map(|l| json!({"map": l.map, "kind": l.kind, "text": l.text}))
            .collect::<Vec<_>>()
            .into(),
    );
    out.insert("music_samples".into(), json!(bank.entries().len()));
    let key_map = |m: &BTreeMap<Key, Key>| -> Value {
        Value::Object(
            m.iter()
                .map(|(b, s)| (b.to_string(), json!(s.to_string())))
                .collect(),
        )
    };
    out.insert(
        "bank".into(),
        json!({
            "keys": bank.keys.iter().map(|k| k.to_string()).collect::<Vec<_>>(),
            "voices": bank.voices.iter().map(|v| json!({
                "name": v.name, "rate": v.rate, "bytes": v.data.len(), "root": v.root,
                "loop_block": v.loop_block})).collect::<Vec<_>>(),
            // By directory entry, which is what the writes say.
            "melodic": Value::Object(bank.melodic().iter().map(|(p, i)| (p.to_string(), json!(bank.directory[*i]))).collect()),
            "hits": Value::Object(bank.hits().iter().map(|(p, i)| (p.to_string(), json!(bank.directory[*i]))).collect()),
            "assignment": bank.assignment.iter().map(key_map).collect::<Vec<_>>(),
            "limited_by": Value::Object(bank.limited_by.iter().map(|(k, n)| (k.to_string(), json!(n))).collect()),
            "constraints": bank.constraints.iter().map(|r| json!({
                "name": r.name, "keys": r.keys.iter().map(|k| k.to_string()).collect::<Vec<_>>(),
                "free": r.free})).collect::<Vec<_>>(),
        }),
    );

    let mut files = Files::new();
    let mut quality = None;
    if let Some(emit) = emit {
        let text = emit::musicdata(&music, emit)?;
        files.insert("musicdata.inc".into(), text.into_bytes());
        files.insert(
            "music.json".into(),
            pretty(&emit::songs_json(&music.songs)).into_bytes(),
        );
        let rom = emit::rom_packages(&music, emit);
        out.insert("packages".into(), json!(rom));
        let (frames, bytes) = emit::boot_frames(&music, &rom[emit.start], emit.decompress_frames)?;
        out.insert("boot".into(), json!({"frames": frames, "bytes": bytes}));
        let effects = msu::effects(&music, emit, game)?;
        out.insert(
            "msu".into(),
            json!({
                "versions": effects.versions.iter().map(|v| json!({
                    "effect": v.effect, "rate": v.rate, "brr": hex(&v.data)})).collect::<Vec<_>>(),
                "packages": effects.packages.iter().map(|p| json!({
                    "name": p.name, "versions": p.versions, "rows": p.rows,
                    "pitches": p.pitches})).collect::<Vec<_>>(),
                "rates": Value::Object(effects.rates.iter().map(|(n, own)| (n.clone(), Value::Object(
                    own.iter().map(|(e, r)| (e.clone(), json!(r))).collect()))).collect()),
            }),
        );
        let boot = (emit.boot != 0xFF).then_some(emit.boot as usize);
        for line in compiler::report(&music, boot) {
            outln!("{line}");
        }
        quality = Some(effects);
    }
    Ok(Compiled {
        music,
        audio: out,
        quality,
        files,
    })
}

/// Every song the game names: each `PlayBGM` and `ChangeSystemBGM` of its
/// maps, its common events and its troops, and each map's song in the tree.
/// Read as plain JSON and not through the schema's types: only two fields
/// matter, and the walk is the same in the three kinds of file.
///
/// `ChangeSystemBGM` is accepted undone, so its songs do not play yet; they
/// are counted anyway so that doing it does not renumber the tracks of a game
/// whose `Music/` does not fit in the byte: see `Game::track_numbers`.
fn named_songs(dump: &Dump) -> Result<BTreeSet<String>> {
    const PLAY_BGM: i64 = 11510;
    const CHANGE_SYSTEM_BGM: i64 = 10660;
    fn walk(v: &Value, out: &mut BTreeSet<String>) {
        match v {
            Value::Object(o) => {
                let code = o.get("code").and_then(Value::as_i64);
                if code == Some(PLAY_BGM) || code == Some(CHANGE_SYSTEM_BGM) {
                    if let Some(name) = o.get("string").and_then(Value::as_str) {
                        out.insert(name.to_string());
                    }
                }
                // The tree's nodes: `music` is the song a map plays.
                if let Some(name) = o
                    .get("music")
                    .and_then(|m| m.get("name"))
                    .and_then(Value::as_str)
                {
                    out.insert(name.to_string());
                }
                o.values().for_each(|x| walk(x, out));
            }
            Value::Array(a) => a.iter().for_each(|x| walk(x, out)),
            _ => {}
        }
    }
    let answer = |e: ditto::lcf::Error| Bad::answer(e.0);
    let mut out = BTreeSet::new();
    for path in dump.map_files().map_err(answer)? {
        let text = std::fs::read_to_string(&path)
            .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
        let map: Value = serde_json::from_str(&text)
            .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
        walk(&map, &mut out);
    }
    for section in ["commonevents", "troops"] {
        walk(&dump.section::<Value>(section).map_err(answer)?, &mut out);
    }
    let tree = serde_json::to_value(dump.tree().map_err(answer)?)
        .map_err(|e| Bad::usage(e.to_string()))?;
    walk(&tree, &mut out);
    Ok(out)
}

/// The game's four bytes for the `.msu`: `[rom] msu_data_signature`.
pub fn msu_magic(project: &Project) -> Result<[u8; 4]> {
    let text = project.ascii(&["rom", "msu_data_signature"], Some(4), None)?;
    Ok(text
        .as_bytes()
        .try_into()
        .expect("four ASCII characters are four bytes"))
}

/// What [`cartridge`] is asked: what the cartridge decided. The binary
/// reads it from `--request`; the converter builds it.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Request {
    /// The event compiler's `songs`, as it answers them.
    pub songs: cartridge::Songs,
    /// The cartridge's maps, by number, in the order of the map table.
    pub maps: Vec<i64>,
    /// The index of the one it boots in.
    pub start: usize,
    /// Whether it has those screens: their songs come from the System.
    pub title: bool,
    pub game_over: bool,
    /// How many frames decompressing the boot map takes.
    pub decompress_frames: f64,
    /// Every song's headroom, instead of its ceiling.
    #[serde(default)]
    pub measuring_headroom: Option<f64>,
    /// Every quality battle backdrop, by number: its tiles and its colours,
    /// in hex in the JSON.
    #[serde(with = "hex_pairs")]
    pub backdrops: Vec<(Vec<u8>, Vec<u8>)>,
    /// Map tree nodes in the dump's shape, over the dump's.
    pub tree_nodes: Vec<Value>,
    /// Whether the samples may travel in the `.msu`: see
    /// `Emit::msu_samples`.
    #[serde(default)]
    pub msu_samples: bool,
}

/// The backdrops' bytes as `[[tiles, colors]]` of hex strings.
mod hex_pairs {
    use serde::de::Error;
    use serde::{Deserialize, Deserializer, Serialize, Serializer};

    type Pairs = Vec<(Vec<u8>, Vec<u8>)>;

    pub fn serialize<S: Serializer>(pairs: &Pairs, s: S) -> Result<S::Ok, S::Error> {
        let text: Vec<(String, String)> = pairs
            .iter()
            .map(|(t, c)| (super::hex(t), super::hex(c)))
            .collect();
        text.serialize(s)
    }

    pub fn deserialize<'de, D: Deserializer<'de>>(d: D) -> Result<Pairs, D::Error> {
        let bytes = |text: &str| super::unhex(text).ok_or_else(|| D::Error::custom("not hex"));
        Vec::<(String, String)>::deserialize(d)?
            .iter()
            .map(|(t, c)| Ok((bytes(t)?, bytes(c)?)))
            .collect()
    }
}

/// What [`cartridge`] answers: its files, and what the music lost to fit in
/// the ARAM —a package's songs that its `PlayBGM` uploads, its sound effects
/// left out—, which `audio.json` also says.
pub struct Answer {
    pub files: Files,
    pub losses: Vec<Loss>,
}

/// `cartridge`: a cartridge's music, from what the event compiler asked
/// for, as `musicdata.inc`, `music.json`, `audio.json`, `audio-job.json`,
/// `effects.json` and the `.msu` —under [`MSU`]—.
pub fn cartridge(flags: &Flags, request: &Request) -> Result<Answer> {
    let game = flags.place.game()?;

    // The game, from the dump, with the nodes the project added on top.
    let answer = |e: ditto::lcf::Error| Bad::answer(e.0);
    let dump = Dump::open(&flags.data).map_err(answer)?;
    let mut tree = Tree::from(&dump.tree().map_err(answer)?);
    for node in &request.tree_nodes {
        tree.insert(
            serde_json::from_value(node.clone())
                .map_err(|e| Bad::usage(format!("the request: tree_nodes: {e}")))?,
        );
    }
    let system: System = dump.section("system").map_err(answer)?;
    // Every song the System names —the title's, the battle's, Game Over's,
    // the vehicles'...—, for the MSU-1 numbering. Song names are ASCII: the
    // Shift-JIS leftovers of the RTP are in four messages of the database.
    let system_songs: BTreeSet<String> = [
        &system.title_music,
        &system.battle_music,
        &system.battle_end_music,
        &system.inn_music,
        &system.boat_music,
        &system.ship_music,
        &system.airship_music,
        &system.gameover_music,
    ]
    .iter()
    .map(|m| m.name.clone())
    .collect();

    // And every song the game names anywhere, for the same numbering: see
    // `Game::track_numbers`.
    let named_songs = named_songs(&dump)?;

    let maps = request.maps.clone();
    let start = request.start;
    if start >= maps.len() {
        return Err(Bad::usage("the request: `start` is not one of its maps"));
    }
    let project = &game.project;
    let c = Cartridge {
        songs: request.songs.clone(),
        map_music: maps
            .iter()
            .map(|&m| {
                tree.music(m as i32)
                    .map(|music| music.name.clone())
                    .unwrap_or_default()
            })
            .collect(),
        map_levels: maps
            .iter()
            .map(|&m| {
                tree.music(m as i32)
                    .map(|music| {
                        Level::new(
                            music.fadein.into(),
                            music.volume.into(),
                            music.tempo.into(),
                            music.balance.into(),
                        )
                    })
                    .unwrap_or_default()
            })
            .collect(),
        maps,
        start,
        title: request.title.then(|| system.title_music.name.clone()),
        game_over: request
            .game_over
            .then(|| system.gameover_music.name.clone()),
        title_level: Level::new(
            system.title_music.fadein.into(),
            system.title_music.volume.into(),
            system.title_music.tempo.into(),
            system.title_music.balance.into(),
        ),
        apart: cartridge::apart_themes(project.list(&["music", "apart_themes"])?)?,
        not_given: cartridge::never_happen(project.list(&["music", "jumps_that_never_happen"])?)?,
        system_songs: system_songs.into_iter().collect(),
        named_songs: named_songs.into_iter().collect(),
        measuring_headroom: request.measuring_headroom,
        decompress_frames: request.decompress_frames,
        msu_samples: request.msu_samples,
    };
    let magic = msu_magic(project)?;

    // The job stays next to what it makes, so the music of a cartridge can
    // be rebuilt alone with `compile`.
    let plan = cartridge::plan(&c)?;
    let job_text = pretty(&plan.job);
    let (job, emit) = job::parse(&plan.job, bank::ARAM_END)?;
    let emit = emit.expect("the plan always says what to emit");
    let done = compile(&job, Some(&emit), &game, &flags.soundfont, false)?;
    let mut files = done.files;
    files.insert("audio-job.json".into(), job_text.into_bytes());
    files.insert(
        "audio.json".into(),
        serde_json::to_string(&Value::Object(done.audio.clone()))
            .unwrap()
            .into_bytes(),
    );
    let music = &done.music;
    let rom = emit::rom_packages(music, &emit);
    let say = |line: String| outln!("{line}");
    if let Some(songs) = plan.battle_songs {
        // The battle's package goes right after the maps'. Until 2026-09-30
        // this counted the last ROM package's sound effects, which is the
        // Game Over's when there is one, and said 0.
        say(format!(
            "  battle audio package: {songs} song(s), {} sound effect(s)",
            rom[c.maps.len()].1.len()
        ));
    }
    // **And how long the boot waits**: this cartridge's `BOOT_FRAMES`, the
    // ROM's floor or the estimate if it goes over. See
    // `cartridge::boot_frames`.
    let boot = &done.audio["boot"];
    let (frames, bytes) = (
        boot["frames"].as_f64().unwrap_or(0.0),
        boot["bytes"].as_i64().unwrap_or(0),
    );
    let far_ram = suite::runtime().join("far_ram.s");
    let source = std::fs::read_to_string(&far_ram)
        .map_err(|e| Bad::usage(format!("{}: {e}", far_ram.display())))?;
    let floor = cartridge::boot_frames_floor(&source)
        .ok_or_else(|| Bad::usage(format!("{}: no BOOT_FRAMES_FLOOR", far_ram.display())))?;
    let boot_frames = cartridge::boot_frames(floor, frames).ok_or_else(|| {
        Bad::answer(format!(
            "the boot doesn't fit in a byte of frames: the boot map's package is {bytes} B and with the map, \
             the driver and the directory the computation gives {frames:.0} frames, against 255. Shrink \
             that package"
        ))
    })?;
    say(format!(
        "  boot: the boot map's package is {bytes} B, {frames:.0} frames; BOOT_FRAMES = {boot_frames} (the floor is {floor})"
    ));

    // The `.msu`: the quality backdrops and the quality sound effects, to
    // read them through the MSU-1 when it is there. It is always written,
    // even if the cartridge carries neither, because it is also the file
    // that turns on the MSU-1 for the tracks.
    let quality = done
        .quality
        .as_ref()
        .expect("with emit there are quality sound effects");
    let written = cartridge::msu(&request.backdrops, quality, &magic)?;
    say(format!(
        "  .msu: {} backdrop(s) and {} sound effect(s) in {} B, signature {} -> {}",
        written.backdrops,
        written.effects,
        written.blob.len(),
        hex(&written.blob[..msu_data::SIGNATURE_SIZE]),
        flags.msu.display()
    ));
    let musicdata = flags.out.join("musicdata.inc");
    let mut text = String::from_utf8(files["musicdata.inc"].clone())
        .expect("musicdata.inc was made from a String");
    text.push_str(&written.inc);
    // With the header and not at the end: from the first `.segment` on,
    // the assembling packs the file into banks and the comments do
    // not survive it.
    let header = text.find("\n\n").map_or(text.len(), |i| i + 1);
    text.insert_str(
        header,
        &format!(
            "\n; On which frame boot ends: the runtime's BOOT_FRAMES_FLOOR, or the\n\
             ; estimate for the boot map's package ({frames:.1} frames) rounded up\n\
             ; if it goes over. See `boot_frames` in rm2k-snes-audio's cartridge.rs.\n\
             BOOT_FRAMES = {boot_frames}\n"
        ),
    );
    files.insert("musicdata.inc".into(), text.into_bytes());
    files.insert(MSU.into(), written.blob);
    let rates = &done.audio["msu"]["rates"];
    files.insert(
        "effects.json".into(),
        pretty(&cartridge::effects_json(music, &c.songs.sounds, rates)).into_bytes(),
    );
    for package in &quality.packages {
        if let Some(theirs) = rates
            .get(&package.name)
            .and_then(Value::as_object)
            .filter(|t| !t.is_empty())
        {
            say(format!(
                "  quality sound effects of package {}: {}",
                package.name,
                cartridge::rates_line(theirs)
            ));
        }
    }
    let names = |songs: &[usize]| {
        songs
            .iter()
            .map(|&t| music.songs[t].name.as_str())
            .collect::<Vec<_>>()
            .join(", ")
    };
    // The separate songs are the music's and not the plan's: a package that
    // did not fit in the ARAM has more than the project file declared. See
    // `relief`.
    for (i, (owned, theirs, out, separate)) in rom[..c.maps.len()].iter().enumerate() {
        if !owned.is_empty() || !theirs.is_empty() || !out.is_empty() || !separate.is_empty() {
            say(format!(
                "  audio package of map {}: {} song(s), {} sound effect(s){}{}",
                c.maps[i],
                owned.len(),
                theirs.len(),
                if out.is_empty() {
                    String::new()
                } else {
                    format!(", and for exit {}", names(out))
                },
                if separate.is_empty() {
                    String::new()
                } else {
                    format!(", and separate {}", names(separate))
                },
            ));
        }
    }
    if !job.effects.is_empty() {
        let unique: BTreeMap<&str, usize> = music
            .effects
            .iter()
            .map(|e| (e.name.as_str(), e.data.len()))
            .collect();
        say(format!(
            "  sound effects: {}, {} B in the cartridge",
            unique.len(),
            unique.values().sum::<usize>()
        ));
    }
    let all: Vec<usize> = (0..music.songs.len()).collect();
    say(format!(
        "music -> {}: {}",
        musicdata.display(),
        if all.is_empty() {
            "none, it comes out silent".to_string()
        } else {
            names(&all)
        }
    ));
    Ok(Answer {
        files,
        losses: music.losses.clone(),
    })
}

fn unhex(text: &str) -> Option<Vec<u8>> {
    if !text.len().is_multiple_of(2) {
        return None;
    }
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(text.get(i..i + 2)?, 16).ok())
        .collect()
}
