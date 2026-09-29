//! The music from the command line: a job in, `musicdata.inc` and what
//! goes with it out; and the questions the tests ask about it.
//!
//! Where the game, the RTP and the SoundFont are is the caller's to say,
//! with the same flags the rest of the suite takes: nothing here has a
//! default path.

use clap::{Args as ClapArgs, Parser, Subcommand};
use rm2k_project::Project;
use rm2k_snes_audio::bank::{self, Key, Samples};
use rm2k_snes_audio::compile;
use rm2k_snes_audio::emit;
use rm2k_snes_audio::fail::{Bad, Result};
use rm2k_snes_audio::game::Game;
use rm2k_snes_audio::samples::SoundFontSamples;
use rm2k_snes_audio::{effects, job, msu, pyjson, sdsp, stream};
use serde_json::{json, Map, Value};
use std::collections::BTreeMap;
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
    /// A cartridge's music, from a job: musicdata.inc, musica.json and audio.json
    Compile(CompileArgs),
    /// The samples each song asks for, and what each weighs untrimmed
    Keys(KeysArgs),
    /// What a stream writes to the DSP: (frame, register, value)
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
    let text = std::fs::read_to_string(path).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
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
    let samples = Samples { font: SoundFontSamples::open(&args.soundfont)? };
    let music = compile::build(&job, &game, &samples)?;
    std::fs::create_dir_all(&args.out).map_err(|e| Bad::usage(format!("{}: {e}", args.out.display())))?;

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
                if args.detail {
                    let m = s.as_object_mut().unwrap();
                    m.insert("writes".into(), json!(t.writes));
                    if let Some(p) = &t.parsed {
                        m.insert(
                            "notes".into(),
                            json!(p.notes.iter().map(|n| (n.start, n.end, n.channel, n.pitch, n.velocity)).collect::<Vec<_>>()),
                        );
                        m.insert(
                            "programs".into(),
                            Value::Object(p.programs.iter().map(|(c, p)| (c.to_string(), json!(p))).collect()),
                        );
                    }
                    m.insert(
                        "allocation".into(),
                        json!(t.allocation.iter().map(|a| (a.note, a.voice, a.stolen, a.end)).collect::<Vec<_>>()),
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
    out.insert("music_samples".into(), json!(bank.voices.len()));
    let key_map = |m: &BTreeMap<Key, Key>| -> Value {
        Value::Object(m.iter().map(|(b, s)| (b.to_string(), json!(s.to_string()))).collect())
    };
    out.insert(
        "bank".into(),
        json!({
            "keys": bank.keys.iter().map(|k| k.to_string()).collect::<Vec<_>>(),
            "voices": bank.voices.iter().map(|v| json!({
                "name": v.name, "rate": v.rate, "bytes": v.data.len(), "root": v.root,
                "loop_block": v.loop_block})).collect::<Vec<_>>(),
            "melodic": Value::Object(bank.melodic().iter().map(|(p, i)| (p.to_string(), json!(i))).collect()),
            "hits": Value::Object(bank.hits().iter().map(|(p, i)| (p.to_string(), json!(i))).collect()),
            "assignment": bank.assignment.iter().map(key_map).collect::<Vec<_>>(),
            "limited_by": Value::Object(bank.limited_by.iter().map(|(k, n)| (k.to_string(), json!(n))).collect()),
            "constraints": bank.constraints.iter().map(|r| json!({
                "name": r.name, "keys": r.keys.iter().map(|k| k.to_string()).collect::<Vec<_>>(),
                "free": r.free})).collect::<Vec<_>>(),
        }),
    );

    if let Some(emit) = &emit {
        let text = emit::musicdata(&music, emit)?;
        write_file(&args.out.join("musicdata.inc"), &text)?;
        write_file(&args.out.join("musica.json"), &pyjson::to_string(&emit::songs_json(&music.songs)))?;
        let rom = emit::rom_packages(&music, emit);
        out.insert("packages".into(), json!(rom));
        let (frames, bytes) = emit::boot_frames(&music, &rom[emit.start], emit.decompress_frames)?;
        out.insert("boot".into(), json!({"frames": frames, "bytes": bytes}));
        let effects = msu::effects(&music, emit, &game)?;
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
    }
    write_file(&args.out.join("audio.json"), &serde_json::to_string(&Value::Object(out)).unwrap())
}

fn do_keys(args: &KeysArgs) -> Result<()> {
    let game = args.place.game()?;
    let samples = Samples { font: SoundFontSamples::open(&args.soundfont)? };
    let parsed = args
        .songs
        .iter()
        .map(|n| rm2k_snes_audio::song::read(n, &game))
        .collect::<Result<Vec<_>>>()?;
    let roots = bank::most_used_zones(&parsed, &samples.font);
    let keys: Vec<Vec<Key>> =
        parsed.iter().map(|p| bank::song_keys(p.as_ref(), &roots).into_iter().collect()).collect();
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
    let bytes = |p: &Path| std::fs::read(p).map_err(|e| Bad::usage(format!("{}: {e}", p.display())));
    let stream_bytes = bytes(&args.stream)?;
    let sounds: Vec<stream::Sound> =
        bytes(&args.sounds)?.chunks_exact(6).map(|c| c.try_into().unwrap()).collect();
    println!("{}", json!(stream::decode(&stream_bytes, &sounds)?));
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
    let path = game
        .song_path(&args.name)
        .ok_or_else(|| Bad::answer(format!("{:?} is neither in the game nor in the RTP", args.name)))?;
    println!("{}", path.display());
    Ok(())
}

fn main() -> ExitCode {
    let cli = Cli::parse();
    let done = match &cli.command {
        Command::Compile(a) => do_compile(a),
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
