//! The music from the command line: a job in, `musicdata.inc` and what
//! goes with it out; and the questions the tests ask about it.
//!
//! Where the game, the RTP and the SoundFont are is the caller's to say,
//! with the same flags the rest of the suite takes: nothing here has a
//! default path.

use clap::{Args as ClapArgs, CommandFactory, FromArgMatches, Parser, Subcommand};
use rm2k_project::Project;
use rm2k_snes_audio::bank::{self, Key, Samples};
use rm2k_snes_audio::fail::{Bad, Result};
use rm2k_snes_audio::game::Game;
use rm2k_snes_audio::samples::SoundFontSamples;
use rm2k_snes_audio::{effects, job, msu_data, sdsp, stage, stream};
use serde_json::{json, Map, Value};
use std::io::Write as _;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

/// The subcommands written with clap's builder and not its derive, like
/// the flags of the machine they take —`arguments` in `rm2k-project`—.
mod commands {
    pub mod volume_ceilings;
}

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

    /// The directory where advocate.toml is. Without this, it is looked up
    /// from the current directory upwards
    #[arg(long, value_name = "DIRECTORY")]
    project: Option<PathBuf>,
}

impl Where {
    fn place(&self) -> stage::Place {
        stage::Place {
            game_dir: self.game_dir.clone(),
            rtp_dir: self.rtp_dir.clone(),
            project: self.project.clone(),
        }
    }

    fn game(&self) -> Result<Game> {
        self.place().game()
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
struct MsuFileArgs {
    /// The .msu
    msu: PathBuf,

    /// The directory where advocate.toml is, which says the game's signature. Without this,
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

fn do_compile(args: &CompileArgs) -> Result<()> {
    let game = args.place.place().game()?;
    let (job, emit) = job::parse(&read_json(&args.job)?, args.aram_end)?;
    let done = stage::compile(&job, emit.as_ref(), &game, &args.soundfont, args.detail)?;
    let mut files = done.files;
    files.insert(
        "audio.json".into(),
        serde_json::to_string(&Value::Object(done.audio))
            .unwrap()
            .into_bytes(),
    );
    write_files(&args.out, &files)
}

/// Each of `files` into `dir`, which is made if it is not there.
fn write_files(dir: &Path, files: &stage::Files) -> Result<()> {
    std::fs::create_dir_all(dir).map_err(|e| Bad::usage(format!("{}: {e}", dir.display())))?;
    for (name, bytes) in files {
        let path = dir.join(name);
        std::fs::write(&path, bytes).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    }
    Ok(())
}

fn do_msu_index(args: &MsuFileArgs) -> Result<()> {
    let project = Project::locate(args.project.as_deref())?;
    let blob =
        std::fs::read(&args.msu).map_err(|e| Bad::usage(format!("{}: {e}", args.msu.display())))?;
    let entries = msu_data::index(&blob, &stage::msu_magic(&project)?)?;
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
    let matches = Cli::command()
        .subcommand(commands::volume_ceilings::command())
        .get_matches();
    let builder = match matches.subcommand() {
        Some(("volume-ceilings", sub)) => {
            Some(("volume-ceilings", commands::volume_ceilings::run(sub)))
        }
        _ => None,
    };
    if let Some((name, done)) = builder {
        return match done {
            Ok(()) => ExitCode::SUCCESS,
            Err(bad) => {
                let _ = std::io::stdout().flush();
                eprintln!("rm2k-snes-audio {name}: {bad}");
                ExitCode::FAILURE
            }
        };
    }
    let cli = Cli::from_arg_matches(&matches).unwrap_or_else(|e| e.exit());
    let done = match &cli.command {
        Command::Compile(a) => do_compile(a),
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
