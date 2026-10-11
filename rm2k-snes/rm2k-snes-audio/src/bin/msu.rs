//! `rm2k-snes-msu`: the MSU-1 tracks of a built cartridge, next to its ROM.
//!
//!     rm2k-snes-msu build/release/game.sfc --game-dir … --soundfont …
//!
//! What a track is and where its audio comes from, in the library's
//! `tracks`. Its last line is always "MSU-1 tracks, N made and M that were
//! already there": whoever builds the cartridges recognizes it by its start
//! and prints it in its place.

use clap::{Arg, ArgAction, Command};
use rm2k_project::environment::{arguments, Environment};
use rm2k_project::{cache, Project};
use rm2k_snes_audio::game::Game;
use rm2k_snes_audio::tracks::{Tracks, GAIN};
use rm2k_snes_audio::Bad;
use std::io::Write as _;
use std::path::{Path, PathBuf};
use std::process::ExitCode;

/// What it uses from the machine: the RTP, because a song can come from
/// there; and the cache, where it remembers which tracks are already there.
const FROM_ENVIRONMENT: &[&str] = &["game_dir", "rtp_dir", "soundfont", "replacements", "cache"];

fn command() -> Command {
    Command::new("rm2k-snes-msu")
        .about("A built cartridge's MSU-1 tracks, rendered from each song's MIDI with fluidsynth, next to its ROM")
        .arg(
            Arg::new("rom")
                .required(true)
                .value_name("ROM")
                .help("the ROM: the tracks go next to it, with its name and the track number"),
        )
        .arg(
            Arg::new("project")
                .long("project")
                .value_name("DIRECTORY")
                .help("the directory where rm2k-snes.toml is. Without this, it is looked up from the current directory upwards"),
        )
        .args(arguments(FROM_ENVIRONMENT))
        .arg(Arg::new("gain").long("gain").value_name("GAIN").value_parser(clap::value_parser!(f64)))
        .arg(
            Arg::new("quiet")
                .long("quiet")
                .action(ArgAction::SetTrue)
                .help("do not list the tracks that were already there: the cartridges' builder runs this on every build"),
        )
}

fn run() -> Result<(), Bad> {
    let matches = command().get_matches();
    let project = Project::locate(matches.get_one::<String>("project").map(Path::new))?;
    let mut environment = Environment::from_matches(&matches, FROM_ENVIRONMENT);
    environment.unpack(&project)?;
    let game = Game {
        game_dir: environment.game()?.to_path_buf(),
        rtp_dir: environment.rtp().ok().map(Path::to_path_buf),
        project,
    };
    let soundfont = environment.soundfont()?.to_path_buf();
    let replacements = environment.msu_replacements().map(Path::to_path_buf);
    let cache_dir = if cache::disabled() { None } else { Some(environment.cache(&game.project)?) };
    let gain = matches.get_one::<f64>("gain").copied().unwrap_or(GAIN);
    let rom = PathBuf::from(matches.get_one::<String>("rom").unwrap());
    let tracks = Tracks::new(game, soundfont, gain, replacements, cache_dir);
    let mut stdout = std::io::stdout();
    let (made, already) = tracks.build(&rom, !matches.get_flag("quiet"), &mut |line| {
        let _ = writeln!(stdout, "{line}");
        let _ = stdout.flush();
    })?;
    // The last line, always, and with this shape.
    println!("MSU-1 tracks, {made} made and {already} that were already there");
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            let _ = std::io::stdout().flush();
            eprintln!("rm2k-snes-msu: {bad}");
            ExitCode::FAILURE
        }
    }
}
