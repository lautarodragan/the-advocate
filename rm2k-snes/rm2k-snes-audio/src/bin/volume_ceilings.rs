//! `rm2k-snes-volume-ceilings`: measures each song's volume ceiling and
//! writes the project's `music/ceilings.toml`, in its automatic patches.
//!
//!     rm2k-snes-volume-ceilings            measures, writes the table and
//!                                          rebuilds `release` with it
//!     rm2k-snes-volume-ceilings --measure  only measures the `release` that
//!                                          is built, and writes nothing
//!     rm2k-snes-volume-ceilings --play ROM --song N --frames F
//!                                          plays one song and says, as
//!                                          JSON, what it gave: what a test
//!                                          asks of a single song
//!
//! How it measures, in the library's `ceilings`. The songs are played in
//! separate processes —this same program, with `--play`—, because a
//! libretro core is one console per process.

use clap::{Arg, ArgAction, Command};
use rm2k_project::environment::{arguments, Environment};
use rm2k_project::{relative, Project};
use rm2k_snes_audio::ceilings::{self, Row, HEADROOM, MEASURING_HEADROOM};
use rm2k_snes_audio::Bad;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::io::Write as _;
use std::path::{Path, PathBuf};
use std::process::{ExitCode, Stdio};
use std::sync::Mutex;

/// What the cartridges' builder needs from the machine, which this passes
/// on to it.
const TO_CONVERTER: &[&str] = &["game_dir", "rtp_dir", "soundfont", "cache"];

const CARTRIDGES: &str = "rm2k-snes-cartridges";

fn command() -> Command {
    Command::new("rm2k-snes-volume-ceilings")
        .about("Measures each song's volume ceiling and writes the project's music/ceilings.toml")
        .arg(
            Arg::new("project")
                .long("project")
                .value_name("DIRECTORY")
                .help("the directory where rm2k-snes.toml is. Without this, it is looked up from the current directory upwards"),
        )
        .args(arguments(TO_CONVERTER))
        .arg(
            Arg::new("measure")
                .long("measure")
                .action(ArgAction::SetTrue)
                .help("only measure the built `release`: clipping, peak and LUFS of each song"),
        )
        .arg(
            Arg::new("play")
                .long("play")
                .value_name("ROM")
                .requires_all(["song", "frames"])
                .help("play one song of a built ROM and print, as JSON, how many samples clipped, its peak and in which frame"),
        )
        .arg(Arg::new("song").long("song").value_name("INDEX").value_parser(clap::value_parser!(u8)).help("with --play: the song's index in the cartridge"))
        .arg(Arg::new("frames").long("frames").value_name("N").value_parser(clap::value_parser!(i64)).help("with --play: how many frames from when the title starts it"))
        .arg(Arg::new("lufs").long("lufs").action(ArgAction::SetTrue).help("with --play: its level too, with ffmpeg"))
}

/// One song, in this process.
fn play_one(sfc: &Path, song: u8, frames: i64, lufs: bool) -> Result<Row, Bad> {
    let (samples, rate) = ceilings::play(sfc, song, frames)?;
    let mut row = ceilings::row(&samples, rate);
    if lufs {
        row.lufs = Some(ceilings::lufs(&samples, rate)?);
    }
    Ok(row)
}

fn row_json(row: &Row) -> Value {
    let mut v = json!({"recortes": row.clipped, "pico": row.peak, "cuadro": row.frame});
    if let Some(l) = row.lufs {
        v["lufs"] = json!(l);
    }
    v
}

/// One song, in a process of its own.
fn play_apart(sfc: &Path, song: usize, frames: i64, lufs: bool) -> Result<Row, Bad> {
    let exe = std::env::current_exe().map_err(|e| Bad::usage(format!("the running executable: {e}")))?;
    let mut cmd = std::process::Command::new(exe);
    cmd.arg("--play").arg(sfc).args(["--song", &song.to_string(), "--frames", &frames.to_string()]);
    if lufs {
        cmd.arg("--lufs");
    }
    let out = cmd.stderr(Stdio::inherit()).output().map_err(|e| Bad::usage(format!("--play: {e}")))?;
    if !out.status.success() {
        return Err(Bad::usage(format!("playing song {song} of {} failed", sfc.display())));
    }
    let v: Value = serde_json::from_slice(&out.stdout).map_err(|e| Bad::usage(format!("--play: {e}")))?;
    Ok(Row {
        clipped: v["recortes"].as_u64().unwrap_or(0) as usize,
        peak: v["pico"].as_i64().unwrap_or(0),
        frame: v["cuadro"].as_i64().unwrap_or(0),
        lufs: v["lufs"].as_f64(),
    })
}

/// {song: row}: each whole song of the cartridge in `directory`, once.
fn measure(directory: &Path, rom_name: &str, lufs: bool) -> Result<BTreeMap<String, Row>, Bad> {
    let names = ceilings::song_names(directory)?;
    let built = ceilings::built_songs(directory)?;
    let sfc = directory.join(format!("{rom_name}.sfc"));
    // One pass, from the writes the compiler emitted, plus one second.
    let jobs: Vec<(usize, i64)> = names
        .iter()
        .enumerate()
        .filter(|(i, n)| !n.is_empty() && built.get(*i).is_some_and(|b| b.length != 0))
        .map(|(i, _)| (i, built[i].length + 60))
        .collect();
    let workers: usize = std::env::var("PROCESSES").ok().and_then(|p| p.parse().ok()).unwrap_or(8).max(1);
    let next = Mutex::new(0usize);
    let results = Mutex::new(Vec::new());
    std::thread::scope(|scope| {
        for _ in 0..workers.min(jobs.len()) {
            scope.spawn(|| loop {
                let k = {
                    let mut n = next.lock().unwrap();
                    *n += 1;
                    *n - 1
                };
                let Some(&(song, frames)) = jobs.get(k) else { break };
                let got = play_apart(&sfc, song, frames, lufs);
                results.lock().unwrap().push((song, got));
            });
        }
    });
    let mut rows = BTreeMap::new();
    for (song, got) in results.into_inner().unwrap() {
        rows.insert(names[song].clone(), got?);
    }
    Ok(rows)
}

struct Run {
    project: Project,
    environment: Environment,
}

impl Run {
    /// Runs the cartridges' builder with this project and this machine's
    /// values.
    fn cartridges(&self, args: &[&str], capture: bool) -> Result<String, Bad> {
        let mut cmd = std::process::Command::new(CARTRIDGES);
        cmd.arg("--project").arg(self.project.directory()).args(self.environment.as_flags(TO_CONVERTER)).args(args);
        if capture {
            cmd.stderr(Stdio::inherit());
            let out = cmd.output().map_err(|e| Bad::usage(format!("{CARTRIDGES}: {e}")))?;
            if !out.status.success() {
                return Err(Bad::usage(format!("{CARTRIDGES} failed: {}", out.status)));
            }
            Ok(String::from_utf8_lossy(&out.stdout).into_owned())
        } else {
            let status = cmd.status().map_err(|e| Bad::usage(format!("{CARTRIDGES}: {e}")))?;
            if !status.success() {
                return Err(Bad::usage(format!("{CARTRIDGES} failed: {status}")));
            }
            Ok(String::new())
        }
    }

    fn ceilings_path(&self) -> Result<PathBuf, Bad> {
        rm2k_snes_audio::game::ceilings_path(&self.project)
    }

    fn write(&self, text: &str) -> Result<(), Bad> {
        let path = self.ceilings_path()?;
        if let Some(dir) = path.parent() {
            std::fs::create_dir_all(dir).map_err(|e| Bad::usage(format!("{}: {e}", dir.display())))?;
        }
        std::fs::write(&path, text).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))
    }
}

fn run() -> Result<(), Bad> {
    let matches = command().get_matches();
    if let Some(sfc) = matches.get_one::<String>("play") {
        let row = play_one(
            Path::new(sfc),
            *matches.get_one::<u8>("song").unwrap(),
            *matches.get_one::<i64>("frames").unwrap(),
            matches.get_flag("lufs"),
        )?;
        println!("{}", row_json(&row));
        return Ok(());
    }
    let project = Project::locate(matches.get_one::<String>("project").map(Path::new))?;
    let environment = Environment::from_matches(&matches, TO_CONVERTER);
    let rom_name = project.string(&["rom", "name"])?.to_string();
    let run = Run { project, environment };
    let listed: Value = serde_json::from_str(&run.cartridges(&["--list", "--json"], true)?)
        .map_err(|e| Bad::usage(format!("{CARTRIDGES} --list --json: {e}")))?;
    let release_name = listed["release"].as_str().ok_or_else(|| Bad::usage("no release cartridge".to_string()))?;
    let release = listed["cartridges"]
        .as_array()
        .and_then(|cs| cs.iter().find(|c| c["name"] == release_name))
        .and_then(|c| c["directory"].as_str())
        .map(PathBuf::from)
        .ok_or_else(|| Bad::usage(format!("{release_name} is not among the cartridges")))?;
    if matches.get_flag("measure") {
        print!("{}", ceilings::report(&measure(&release, &rom_name, true)?, None));
        return Ok(());
    }

    // The half-volume copy, in its own build directory.
    let measure_dir = run.project.build()?.join("ceilings");
    println!("a copy of release with the headroom at {MEASURING_HEADROOM:?}, in {}", measure_dir.display());
    let _ = std::io::stdout().flush();
    let measure_dir_text = measure_dir.to_string_lossy().into_owned();
    run.cartridges(
        &[release_name, "--convert-into", &measure_dir_text, "--", "--measure-headroom", &format!("{MEASURING_HEADROOM:?}")],
        false,
    )?;
    let at_half = measure(&measure_dir, &rom_name, false)?;
    let clipping: Vec<&str> = at_half.iter().filter(|(_, r)| r.clipped != 0).map(|(n, _)| n.as_str()).collect();
    if !clipping.is_empty() {
        return Err(Bad::answer(format!(
            "with the headroom at {MEASURING_HEADROOM:?} these clip: {}: lower MEASURING_HEADROOM",
            clipping.join(", ")
        )));
    }
    let mut ceilings: BTreeMap<String, f64> = at_half
        .iter()
        .map(|(n, r)| (n.clone(), ceilings::ceiling(r.peak as f64, MEASURING_HEADROOM, HEADROOM)))
        .collect();

    let mut measured = BTreeMap::new();
    let mut done = false;
    for attempt in 0..4 {
        let provisional: BTreeMap<String, Row> =
            at_half.iter().map(|(n, r)| (n.clone(), Row { lufs: Some(0.0), ..r.clone() })).collect();
        run.write(&ceilings::table(&ceilings, &provisional, &BTreeMap::new()))?;
        println!("release with the table, round {}", attempt + 1);
        let _ = std::io::stdout().flush();
        // Without the MSU-1 tracks: what is measured is the SPC700, and the
        // tracks do not depend on the headroom.
        run.cartridges(&[release_name, "--without-tracks"], false)?;
        measured = measure(&release, &rom_name, true)?;
        let clipping: Vec<(String, i64)> =
            measured.iter().filter(|(_, r)| r.clipped != 0).map(|(n, r)| (n.clone(), r.peak)).collect();
        if clipping.is_empty() {
            done = true;
            break;
        }
        for (name, peak) in clipping {
            let current = ceilings[&name];
            ceilings.insert(name, ceilings::lowered(current, peak));
        }
    }
    if !done {
        let still: Vec<&str> = measured.iter().filter(|(_, r)| r.clipped != 0).map(|(n, _)| n.as_str()).collect();
        return Err(Bad::answer(format!("after four rounds these still clip: {}", still.join(", "))));
    }
    let fingerprints: BTreeMap<String, String> = ceilings::built_songs(&release)?
        .into_iter()
        .filter(|b| b.length != 0)
        .map(|b| (b.name, b.fingerprint))
        .collect();
    // What is rewritten now —the peaks, the fingerprints— does not change
    // the headrooms, so the cartridge just measured is still up to date:
    // its stamp looks only at the table's headrooms.
    run.write(&ceilings::table(&ceilings, &measured, &fingerprints))?;
    print!("{}", ceilings::report(&measured, Some(&ceilings)));
    let here = std::env::current_dir().unwrap_or_default();
    println!("-> {}", relative(run.ceilings_path()?, here).display());
    Ok(())
}

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(bad) => {
            let _ = std::io::stdout().flush();
            eprintln!("rm2k-snes-volume-ceilings: {bad}");
            ExitCode::FAILURE
        }
    }
}
