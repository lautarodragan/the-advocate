//! The music from the command line: a job in, `musicdata.inc` and what
//! goes with it out; and the questions the tests ask about it.
//!
//! Where the game, the RTP and the SoundFont are is the caller's to say,
//! with the same flags the rest of the suite takes: nothing here has a
//! default path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use ditto::dump::Dump;
use ditto::schema::System;
use rm2k_project::{suite, Project};
use rm2k_rules::tree::Tree;
use rm2k_snes_audio::bank::{self, Key, Samples};
use rm2k_snes_audio::cartridge::{self, Cartridge};
use rm2k_snes_audio::compile;
use rm2k_snes_audio::emit;
use rm2k_snes_audio::fail::{Bad, Result};
use rm2k_snes_audio::game::Game;
use rm2k_snes_audio::samples::SoundFontSamples;
use rm2k_snes_audio::{effects, job, msu, msu_data, pyjson, sdsp, stream};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::io::Write as _;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

/// "The samples do not fit" is this tool answering no; "that flag makes no
/// sense" is the call being wrong.
const NO: u8 = 1;
const MISUSE: u8 = 2;

#[derive(Parser)]
#[command(
    name = "rm2k-snes-audio",
    about = "Compile an rm2k-snes game's music for the SPC700: the shared sample bank, a stream \
             per song, an audio package per map",
    after_help = "Exit codes: 1 the answer is no (the samples do not fit, a stream does not \
                  write what it has to), 2 bad usage.",
    version
)]
struct Cli {
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// A cartridge's music, from a job: musicdata.inc, music.json and audio.json
    Compile(CompileArgs),
    /// A cartridge's music as a stage of its converter: from what the event compiler asked for
    /// to musicdata.inc, the .msu and what goes with them
    Cartridge(CartridgeArgs),
    /// The entries of a .msu with data, as JSON: [where, length] each; refuses one that is not
    /// valid
    MsuIndex(MsuFileArgs),
    /// A .msu with data, signed again: what a changed one needs to pass as another build's
    MsuSign(MsuSignArgs),
    /// The samples each song asks for, and what each weighs untrimmed
    Keys(KeysArgs),
    /// What a stream writes to the DSP —(frame, register, value)— and how long it is
    Decode(DecodeArgs),
    /// A sound effect's WAV, as it is read: its samples and its rate
    Wav(WavArgs),
    /// Where a song's file is
    FindSong(FindSongArgs),
    /// The DSP pitch of a sound effect at a rate and a tempo
    Pitch(PitchArgs),
    /// The engine's numbers other tools compute with, as JSON
    Constants,
}

/// Where the game, its RTP and its SoundFont are.
#[derive(ClapArgs)]
struct Where {
    /// The original RM2k project: where the MIDIs and the WAVs are
    #[arg(long, value_name = "PATH")]
    game_dir: PathBuf,

    /// The RTP the game was built with: what the game does not ship is
    /// looked up there
    #[arg(long, value_name = "PATH")]
    rtp_dir: Option<PathBuf>,

    /// The directory where rm2k-snes.toml is. Without this, it is looked up
    /// from the current directory upwards
    #[arg(long, value_name = "DIRECTORY")]
    project: Option<PathBuf>,
}

impl Where {
    fn game(&self) -> Result<Game> {
        Ok(Game {
            game_dir: self.game_dir.clone(),
            rtp_dir: self.rtp_dir.clone(),
            project: Project::locate(self.project.as_deref())?,
        })
    }
}

#[derive(ClapArgs)]
#[command(after_help = "The job is a JSON object:\n  \
    songs               the songs, in the order the bytecode numbers them\n  \
    effects             the sound effects, from most to least requested\n  \
    packages            [{name, songs, effects, exits, separate}]; without it, each song \
                        is a package\n  \
    inheritance         [[package, song that may be playing when it loads]]\n  \
    measuring_headroom  every song's headroom, instead of its measured ceiling\n  \
    system_songs        the songs the database's System names\n  \
    named_songs         every song the game's events and maps name\n  \
    emit                {packages, boot, title, game_over, map_song, sounds, start, \
                        decompress_frames}: without it, no musicdata.inc\n\n\
    It writes audio.json always: the bank, each song and each sound effect.")]
struct CompileArgs {
    /// The job, as JSON
    #[arg(long, value_name = "PATH")]
    job: PathBuf,

    /// The directory to write to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,

    #[command(flatten)]
    place: Where,

    /// The bank the samples come from
    #[arg(long, value_name = "PATH")]
    soundfont: PathBuf,

    /// Up to where the ARAM holds samples; only for tests that squeeze it
    #[arg(long, value_name = "ADDRESS", default_value_t = bank::ARAM_END)]
    aram_end: i64,

    /// Also each song's notes, writes and voice allocation, in audio.json
    #[arg(long)]
    detail: bool,
}

#[derive(ClapArgs)]
#[command(after_help = "The request is a JSON object:\n  \
    songs               the event compiler's `songs`, as it answers them\n  \
    maps                the cartridge's maps, by number, in the order of the map table\n  \
    start               the index of the one it boots in\n  \
    title, game_over    whether it has those screens: their songs come from the System\n  \
    decompress_frames   how many frames decompressing the boot map takes\n  \
    measuring_headroom  every song's headroom, instead of its ceiling, or null\n  \
    backdrops           [[tiles, colors]] in hex: every quality battle backdrop, by number\n  \
    tree_nodes          map tree nodes in the dump's shape, over the dump's\n\n\
    It writes into --out musicdata.inc, music.json, audio.json, audio-job.json and \
    effects.json, and the .msu to --msu.")]
struct CartridgeArgs {
    /// What the cartridge decided, as JSON
    #[arg(long, value_name = "PATH")]
    request: PathBuf,

    /// The directory to write to
    #[arg(long, value_name = "DIRECTORY")]
    out: PathBuf,

    /// Where the .msu goes
    #[arg(long, value_name = "PATH")]
    msu: PathBuf,

    /// The game's Ditto dump: the map tree and the database's System
    #[arg(long, value_name = "DIRECTORY")]
    data: PathBuf,

    #[command(flatten)]
    place: Where,

    /// The bank the samples come from
    #[arg(long, value_name = "PATH")]
    soundfont: PathBuf,
}

#[derive(ClapArgs)]
struct MsuFileArgs {
    /// The .msu
    msu: PathBuf,

    /// The directory where rm2k-snes.toml is, which says the game's signature. Without this,
    /// it is looked up from the current directory upwards
    #[arg(long, value_name = "DIRECTORY")]
    project: Option<PathBuf>,
}

#[derive(ClapArgs)]
struct MsuSignArgs {
    /// The .msu
    msu: PathBuf,

    /// Where the signed one goes
    #[arg(long, value_name = "PATH")]
    out: PathBuf,
}

#[derive(ClapArgs)]
struct KeysArgs {
    /// The songs, by name
    songs: Vec<String>,

    #[command(flatten)]
    place: Where,

    /// The bank the samples come from
    #[arg(long, value_name = "PATH")]
    soundfont: PathBuf,
}

#[derive(ClapArgs)]
struct DecodeArgs {
    /// The stream, from its first byte; what follows its OP_END is ignored
    #[arg(long, value_name = "PATH")]
    stream: PathBuf,

    /// Its sounds: six bytes each
    #[arg(long, value_name = "PATH")]
    sounds: PathBuf,

    /// Decode it with each OP_REPEAT replaced by the events it reads, which
    /// is the stream as it was before they were folded; `length` and
    /// `repeats` —each OP_REPEAT, as [where it is, where it goes back to],
    /// offsets from the stream's start— are still the stream's as given
    #[arg(long)]
    unfold: bool,
}

#[derive(ClapArgs)]
struct WavArgs {
    /// The sound effect's name
    name: String,

    #[command(flatten)]
    place: Where,
}

#[derive(ClapArgs)]
struct FindSongArgs {
    /// The song's name
    name: String,

    #[command(flatten)]
    place: Where,
}

#[derive(ClapArgs)]
struct PitchArgs {
    #[arg(long)]
    rate: i64,
    #[arg(long)]
    tempo: i64,
}

fn read_json(path: &Path) -> Result<Value> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    serde_json::from_str(&text).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))
}

fn write_file(path: &Path, text: &str) -> Result<()> {
    std::fs::write(path, text).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))
}

fn hex(data: &[u8]) -> String {
    data.iter().map(|b| format!("{b:02x}")).collect()
}

fn do_compile(args: &CompileArgs) -> Result<()> {
    let game = args.place.game()?;
    let (job, emit) = job::parse(&read_json(&args.job)?, args.aram_end)?;
    let done = compile_into(
        &job,
        emit.as_ref(),
        &game,
        &args.soundfont,
        &args.out,
        args.detail,
    )?;
    write_file(
        &args.out.join("audio.json"),
        &serde_json::to_string(&Value::Object(done.audio)).unwrap(),
    )
}

/// A job's music, compiled: what `audio.json` says, and with `emit`, the
/// sound effects' MSU-1 versions.
struct Compiled {
    music: compile::Music,
    audio: Map<String, Value>,
    quality: Option<msu::Effects>,
}

/// Compiles a job into `out`: `musicdata.inc` and `music.json` with
/// `emit`, and what each song and the bank came out as, to standard output.
/// `audio.json` is the caller's to write, with whatever it adds.
fn compile_into(
    job: &compile::Job,
    emit: Option<&emit::Emit>,
    game: &Game,
    soundfont: &Path,
    out_dir: &Path,
    detail: bool,
) -> Result<Compiled> {
    let samples = Samples {
        font: SoundFontSamples::open(soundfont)?,
    };
    let music = compile::build(job, game, &samples)?;
    std::fs::create_dir_all(out_dir)
        .map_err(|e| Bad::usage(format!("{}: {e}", out_dir.display())))?;
    // What a package lost to fit in the ARAM, said here and in `audio.json`
    // —`losses`—, which is where the converter takes it from for
    // `degradations.json`: this runs after the converter, so it cannot hand
    // them over any other way. See `relief`.
    for loss in &music.losses {
        println!("  WARNING, {}", loss.text);
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

    let mut quality = None;
    if let Some(emit) = emit {
        let text = emit::musicdata(&music, emit)?;
        write_file(&out_dir.join("musicdata.inc"), &text)?;
        write_file(
            &out_dir.join("music.json"),
            &pyjson::to_string(&emit::songs_json(&music.songs)),
        )?;
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
        let mut stdout = std::io::stdout().lock();
        for line in compile::report(&music, boot) {
            let _ = writeln!(stdout, "{line}");
        }
        quality = Some(effects);
    }
    Ok(Compiled {
        music,
        audio: out,
        quality,
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
fn msu_magic(project: &Project) -> Result<[u8; 4]> {
    let text = project.ascii(&["rom", "msu_data_signature"], Some(4), None)?;
    Ok(text
        .as_bytes()
        .try_into()
        .expect("four ASCII characters are four bytes"))
}

fn do_cartridge(args: &CartridgeArgs) -> Result<()> {
    let game = args.place.game()?;
    let request = read_json(&args.request)?;
    let whose = args.request.display().to_string();
    let bad = |what: &str| Bad::usage(format!("{whose}: `{what}` is not what it should be"));

    // The game, from the dump, with the nodes the project added on top.
    let answer = |e: ditto::lcf::Error| Bad::answer(e.0);
    let dump = Dump::open(&args.data).map_err(answer)?;
    let mut tree = Tree::from(&dump.tree().map_err(answer)?);
    for node in request
        .get("tree_nodes")
        .and_then(Value::as_array)
        .ok_or_else(|| bad("tree_nodes"))?
    {
        tree.insert(
            serde_json::from_value(node.clone())
                .map_err(|e| Bad::usage(format!("{whose}: tree_nodes: {e}")))?,
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

    let maps: Vec<i64> = request
        .get("maps")
        .and_then(Value::as_array)
        .ok_or_else(|| bad("maps"))?
        .iter()
        .map(|m| m.as_i64().ok_or_else(|| bad("maps")))
        .collect::<Result<_>>()?;
    let start = request
        .get("start")
        .and_then(Value::as_u64)
        .ok_or_else(|| bad("start"))? as usize;
    if start >= maps.len() {
        return Err(bad("start"));
    }
    let flag = |key: &str| {
        request
            .get(key)
            .and_then(Value::as_bool)
            .ok_or_else(|| bad(key))
    };
    let backdrops: Vec<(Vec<u8>, Vec<u8>)> = request
        .get("backdrops")
        .and_then(Value::as_array)
        .ok_or_else(|| bad("backdrops"))?
        .iter()
        .map(|pair| {
            let part = |k: usize| {
                pair.get(k)
                    .and_then(Value::as_str)
                    .and_then(unhex)
                    .ok_or_else(|| bad("backdrops"))
            };
            Ok((part(0)?, part(1)?))
        })
        .collect::<Result<_>>()?;
    let project = &game.project;
    let c = Cartridge {
        songs: cartridge::Songs::from_json(request.get("songs").ok_or_else(|| bad("songs"))?)?,
        map_music: maps
            .iter()
            .map(|&m| {
                tree.music(m as i32)
                    .map(|music| music.name.clone())
                    .unwrap_or_default()
            })
            .collect(),
        maps,
        start,
        title: flag("title")?.then(|| system.title_music.name.clone()),
        game_over: flag("game_over")?.then(|| system.gameover_music.name.clone()),
        apart: cartridge::apart_themes(project.list(&["music", "apart_themes"])?)?,
        not_given: cartridge::never_happen(project.list(&["music", "jumps_that_never_happen"])?)?,
        system_songs: system_songs.into_iter().collect(),
        named_songs: named_songs.into_iter().collect(),
        measuring_headroom: request.get("measuring_headroom").and_then(Value::as_f64),
        decompress_frames: request
            .get("decompress_frames")
            .and_then(Value::as_f64)
            .ok_or_else(|| bad("decompress_frames"))?,
        msu_samples: request
            .get("msu_samples")
            .and_then(Value::as_bool)
            .unwrap_or(false),
    };
    let magic = msu_magic(project)?;

    // The job stays next to what it makes, so the music of a cartridge can
    // be rebuilt alone with `compile`.
    let plan = cartridge::plan(&c)?;
    std::fs::create_dir_all(&args.out)
        .map_err(|e| Bad::usage(format!("{}: {e}", args.out.display())))?;
    write_file(
        &args.out.join("audio-job.json"),
        &pyjson::to_string(&plan.job),
    )?;
    let (job, emit) = job::parse(&plan.job, bank::ARAM_END)?;
    let emit = emit.expect("the plan always says what to emit");
    let done = compile_into(&job, Some(&emit), &game, &args.soundfont, &args.out, false)?;
    write_file(
        &args.out.join("audio.json"),
        &serde_json::to_string(&Value::Object(done.audio.clone())).unwrap(),
    )?;
    let music = &done.music;
    let rom = emit::rom_packages(music, &emit);
    let mut stdout = std::io::stdout().lock();
    let mut say = |line: String| {
        let _ = writeln!(stdout, "{line}");
    };
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
    let written = cartridge::msu(&backdrops, quality, &magic)?;
    let fresh = PathBuf::from(format!("{}.nuevo", args.msu.display()));
    std::fs::write(&fresh, &written.blob)
        .map_err(|e| Bad::usage(format!("{}: {e}", fresh.display())))?;
    std::fs::rename(&fresh, &args.msu)
        .map_err(|e| Bad::usage(format!("{}: {e}", args.msu.display())))?;
    say(format!(
        "  .msu: {} backdrop(s) and {} sound effect(s) in {} B, signature {} -> {}",
        written.backdrops,
        written.effects,
        written.blob.len(),
        hex(&written.blob[..msu_data::SIGNATURE_SIZE]),
        args.msu.display()
    ));
    let musicdata = args.out.join("musicdata.inc");
    let mut text = std::fs::read_to_string(&musicdata)
        .map_err(|e| Bad::usage(format!("{}: {e}", musicdata.display())))?;
    text.push_str(&written.inc);
    // With the header and not at the end: from the first `.segment` on,
    // `rm2k-snes-assemble` packs the file into banks and the comments do
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
    write_file(&musicdata, &text)?;
    let rates = &done.audio["msu"]["rates"];
    write_file(
        &args.out.join("effects.json"),
        &pyjson::to_string(&cartridge::effects_json(music, &c.songs.sounds, rates)),
    )?;
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
    Ok(())
}

fn unhex(text: &str) -> Option<Vec<u8>> {
    if text.len() % 2 != 0 {
        return None;
    }
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(text.get(i..i + 2)?, 16).ok())
        .collect()
}

fn do_msu_index(args: &MsuFileArgs) -> Result<()> {
    let project = Project::locate(args.project.as_deref())?;
    let blob =
        std::fs::read(&args.msu).map_err(|e| Bad::usage(format!("{}: {e}", args.msu.display())))?;
    let entries = msu_data::index(&blob, &msu_magic(&project)?)?;
    println!("{}", json!(entries));
    Ok(())
}

fn do_msu_sign(args: &MsuSignArgs) -> Result<()> {
    let blob =
        std::fs::read(&args.msu).map_err(|e| Bad::usage(format!("{}: {e}", args.msu.display())))?;
    std::fs::write(&args.out, msu_data::sign(&blob)?)
        .map_err(|e| Bad::usage(format!("{}: {e}", args.out.display())))
}

fn do_keys(args: &KeysArgs) -> Result<()> {
    let game = args.place.game()?;
    let samples = Samples {
        font: SoundFontSamples::open(&args.soundfont)?,
    };
    let parsed = args
        .songs
        .iter()
        .map(|n| rm2k_snes_audio::song::read(n, &game))
        .collect::<Result<Vec<_>>>()?;
    let roots = bank::most_used_zones(&parsed, &samples.font);
    let keys: Vec<Vec<Key>> = parsed
        .iter()
        .map(|p| bank::song_keys(p.as_ref(), &roots).into_iter().collect())
        .collect();
    let mut natives = Map::new();
    for k in keys.iter().flatten() {
        if let Some(v) = samples.sample(k, bank::NATIVE)? {
            natives.insert(k.to_string(), json!(v.data.len()));
        }
    }
    println!(
        "{}",
        json!({
            "songs": keys.iter().map(|ks| ks.iter().map(|k| k.to_string()).collect::<Vec<_>>()).collect::<Vec<_>>(),
            "natives": natives,
        })
    );
    Ok(())
}

fn do_decode(args: &DecodeArgs) -> Result<()> {
    let bytes =
        |p: &Path| std::fs::read(p).map_err(|e| Bad::usage(format!("{}: {e}", p.display())));
    let stream_bytes = bytes(&args.stream)?;
    let sounds: Vec<stream::Sound> = bytes(&args.sounds)?
        .chunks_exact(6)
        .map(|c| c.try_into().unwrap())
        .collect();
    let (mut writes, length) = stream::decode_counting(&stream_bytes, &sounds)?;
    let repeats = stream::repeats(&stream_bytes)?;
    if args.unfold {
        writes = stream::decode(&stream::unfold(&stream_bytes)?, &sounds)?;
    }
    println!(
        "{}",
        json!({"writes": writes, "length": length, "repeats": repeats})
    );
    Ok(())
}

fn do_wav(args: &WavArgs) -> Result<()> {
    let game = args.place.game()?;
    let (samples, rate) = effects::wav_of(&game, &args.name)
        .ok_or_else(|| Bad::answer(format!("no WAV that can be read for {:?}", args.name)))?;
    println!("{}", json!({"samples": samples, "rate": rate}));
    Ok(())
}

fn do_find_song(args: &FindSongArgs) -> Result<()> {
    let game = args.place.game()?;
    let path = game.song_path(&args.name).ok_or_else(|| {
        Bad::answer(format!(
            "{:?} is neither in the game nor in the RTP",
            args.name
        ))
    })?;
    println!("{}", path.display());
    Ok(())
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Compile(a) => do_compile(a),
        Command::Cartridge(a) => do_cartridge(a),
        Command::MsuIndex(a) => do_msu_index(a),
        Command::MsuSign(a) => do_msu_sign(a),
        Command::Keys(a) => do_keys(a),
        Command::Decode(a) => do_decode(a),
        Command::Wav(a) => do_wav(a),
        Command::FindSong(a) => do_find_song(a),
        Command::Pitch(a) => {
            println!("{}", effects::pitch(a.rate, a.tempo));
            Ok(())
        }
        Command::Constants => {
            println!(
                "{}",
                json!({
                    "headroom": sdsp::HEADROOM,
                    "master": sdsp::master(),
                    "directory_max": bank::DIRECTORY_MAX,
                    "ticks_per_second": rm2k_snes_audio::midi::TICKS_PER_SECOND,
                    "kon": sdsp::KON,
                    "v_srcn": sdsp::V_SRCN,
                    "block_bytes": rm2k_snes_audio::samples::BLOCK_BYTES,
                    "samples_addr": bank::SAMPLES_ADDR,
                    "silence_bytes": bank::SILENCE.len(),
                    "msu_signature_size": msu_data::SIGNATURE_SIZE,
                    "msu_backdrops_start": msu_data::BACKDROPS_START,
                    "msu_colors_at": msu_data::COLORS_AT,
                    "msu_backdrop_span": msu_data::BACKDROP_SPAN,
                })
            );
            Ok(())
        }
    };
    match done {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            let _ = std::io::stdout().flush();
            eprintln!("rm2k-snes-audio: {bad}");
            ExitCode::from(match bad {
                Bad::Answer(_) => NO,
                Bad::Usage(_) => MISUSE,
            })
        }
    }
}
