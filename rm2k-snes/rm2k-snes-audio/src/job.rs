//! The job: what the cartridge's compiler hands the music, as JSON.
//!
//! ```text
//!   songs               the songs, in the order the bytecode numbers them
//!   effects             the sound effects, from most to least requested
//!   packages            [{name, songs, effects, exits, separate}]; without
//!                       it, each song is a package
//!   inheritance         [[package, song that may be playing when it loads]]
//!   measuring_headroom  every song's headroom, instead of its ceiling
//!   system_songs        the songs the database's `System` names
//!   named_songs         every song the game's events and maps name
//!   emit                {packages, boot, title, title_level, game_over,
//!                       map_song, map_level, sounds, start,
//!                       decompress_frames, msu_samples}: what goes into
//!                       `musicdata.inc` besides the music
//! ```

use crate::compile::{Job, Package};
use crate::emit::{Emit, SoundRequest};
use crate::fail::{Bad, Result};
use rm2k_snes_bytecode::level::Level;
use serde_json::Value;

fn bad_job(what: &str) -> Bad {
    Bad::usage(format!("the job's {what} is not what it should be"))
}

fn strings(v: Option<&Value>, what: &str) -> Result<Vec<String>> {
    match v {
        None | Some(Value::Null) => Ok(Vec::new()),
        Some(Value::Array(items)) => items
            .iter()
            .map(|i| i.as_str().map(String::from).ok_or_else(|| bad_job(what)))
            .collect(),
        _ => Err(bad_job(what)),
    }
}

fn indices(v: Option<&Value>, what: &str) -> Result<Vec<usize>> {
    match v {
        None | Some(Value::Null) => Ok(Vec::new()),
        Some(Value::Array(items)) => items
            .iter()
            .map(|i| i.as_u64().map(|n| n as usize).ok_or_else(|| bad_job(what)))
            .collect(),
        _ => Err(bad_job(what)),
    }
}

fn int(v: Option<&Value>, what: &str) -> Result<i64> {
    v.and_then(Value::as_i64).ok_or_else(|| bad_job(what))
}

pub fn parse(v: &Value, aram_end: i64) -> Result<(Job, Option<Emit>)> {
    let songs = strings(v.get("songs"), "songs")?;
    let packages = match v.get("packages") {
        None | Some(Value::Null) => None,
        Some(Value::Array(items)) => Some(
            items
                .iter()
                .map(|p| {
                    Ok(Package {
                        name: p
                            .get("name")
                            .and_then(Value::as_str)
                            .ok_or_else(|| bad_job("package name"))?
                            .into(),
                        songs: indices(p.get("songs"), "package songs")?,
                        effects: strings(p.get("effects"), "package effects")?,
                        exits: indices(p.get("exits"), "package exits")?,
                        separate: indices(p.get("separate"), "package separate songs")?,
                    })
                })
                .collect::<Result<Vec<_>>>()?,
        ),
        _ => return Err(bad_job("packages")),
    };
    let inheritance = match v.get("inheritance") {
        None | Some(Value::Null) => Vec::new(),
        Some(Value::Array(items)) => items
            .iter()
            .map(|pair| {
                let name = pair
                    .get(0)
                    .and_then(Value::as_str)
                    .ok_or_else(|| bad_job("inheritance"))?;
                let song = pair
                    .get(1)
                    .and_then(Value::as_u64)
                    .ok_or_else(|| bad_job("inheritance"))?;
                Ok((name.to_string(), song as usize))
            })
            .collect::<Result<_>>()?,
        _ => return Err(bad_job("inheritance")),
    };
    for (_, t) in &inheritance {
        if *t >= songs.len() {
            return Err(bad_job("inheritance"));
        }
    }
    let mut job = Job {
        songs,
        effects: strings(v.get("effects"), "effects")?,
        packages,
        inheritance,
        measuring_headroom: v.get("measuring_headroom").and_then(Value::as_f64),
        system_songs: strings(v.get("system_songs"), "system songs")?,
        named_songs: strings(v.get("named_songs"), "named songs")?,
        aram_end,
        enters: Vec::new(),
    };
    let emit = match v.get("emit") {
        None | Some(Value::Null) => None,
        Some(e) => {
            let byte = |key: &str| -> Result<u8> {
                u8::try_from(int(e.get(key), key)?).map_err(|_| bad_job(key))
            };
            let game_over = e
                .get("game_over")
                .and_then(Value::as_array)
                .ok_or_else(|| bad_job("game_over"))?;
            let sounds = e
                .get("sounds")
                .and_then(Value::as_array)
                .ok_or_else(|| bad_job("sounds"))?
                .iter()
                .map(|s| {
                    Ok(SoundRequest {
                        effect: s
                            .get(0)
                            .and_then(Value::as_str)
                            .ok_or_else(|| bad_job("sounds"))?
                            .into(),
                        volume: int(s.get(1), "sounds")?,
                        tempo: int(s.get(2), "sounds")?,
                        balance: int(s.get(3), "sounds")?,
                    })
                })
                .collect::<Result<_>>()?;
            Some(Emit {
                packages: int(e.get("packages"), "emit packages")? as usize,
                boot: byte("boot")?,
                title: byte("title")?,
                game_over: (
                    u8::try_from(int(game_over.first(), "game_over")?)
                        .map_err(|_| bad_job("game_over"))?,
                    u16::try_from(int(game_over.get(1), "game_over")?)
                        .map_err(|_| bad_job("game_over"))?,
                ),
                map_song: indices(e.get("map_song"), "map_song")?
                    .into_iter()
                    .map(|m| u8::try_from(m).map_err(|_| bad_job("map_song")))
                    .collect::<Result<_>>()?,
                map_level: match e.get("map_level") {
                    None | Some(Value::Null) => Vec::new(),
                    Some(Value::Array(levels)) => levels
                        .iter()
                        .map(|l| {
                            let bytes: Vec<u8> = l
                                .as_array()
                                .into_iter()
                                .flatten()
                                .filter_map(Value::as_u64)
                                .filter_map(|b| u8::try_from(b).ok())
                                .collect();
                            bytes.try_into().map_err(|_| bad_job("map_level"))
                        })
                        .collect::<Result<_>>()?,
                    Some(_) => return Err(bad_job("map_level")),
                },
                title_level: match e.get("title_level") {
                    None | Some(Value::Null) => Level::WHOLE.bytes(),
                    Some(l) => l
                        .as_array()
                        .into_iter()
                        .flatten()
                        .filter_map(Value::as_u64)
                        .filter_map(|b| u8::try_from(b).ok())
                        .collect::<Vec<u8>>()
                        .try_into()
                        .map_err(|_| bad_job("title_level"))?,
                },
                sounds,
                start: int(e.get("start"), "start")? as usize,
                decompress_frames: e
                    .get("decompress_frames")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0),
                msu_samples: e
                    .get("msu_samples")
                    .and_then(Value::as_bool)
                    .unwrap_or(false),
            })
        }
    };
    if let (Some(e), Some(p)) = (&emit, &job.packages) {
        if e.packages > p.len() || e.start >= e.packages.max(1) {
            return Err(bad_job("emit packages"));
        }
        // Whether each package's first song plays on entering: a map's own
        // song, or the boot's in the boot map —`plan` puts them in front—;
        // the battle's, the Game Over's and the title's always. A map whose
        // songs are all started by its pages' `PlayBGM`s enters with none.
        // It is not in the job because the job is the Python's, byte for
        // byte: see `the_job_is_the_one_the_python_built`.
        job.enters = (0..p.len())
            .map(|i| match e.map_song.get(i) {
                Some(&song) => song != 0xFF || (i == e.start && e.boot != 0xFF),
                None => true,
            })
            .collect();
    }
    Ok((job, emit))
}
