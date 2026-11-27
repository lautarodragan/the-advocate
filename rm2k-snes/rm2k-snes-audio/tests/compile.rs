//! A job compiled as its caller sees it —`stage::compile`, what the
//! converter calls through `cartridge`—: what it answers, and whether a no
//! is the answer or the call being wrong. And the small readers a game's
//! tests mirror: a sound effect's WAV, where a song is, an effect's pitch.
//!
//! Until 2026-11-27 these ran the binary's `compile`, `decode`, `wav`,
//! `find-song` and `pitch`, which went when nothing called them any more.

mod fixture;

use flate2::read::GzDecoder;
use rm2k_project::Project;
use rm2k_snes_audio::fail::Bad;
use rm2k_snes_audio::game::Game;
use rm2k_snes_audio::stage::{self, Compiled};
use rm2k_snes_audio::{effects, job, stream};
use serde_json::Value;
use std::path::{Path, PathBuf};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-snes-audio-compile-{name}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn game(dir: &Path) -> Game {
    Game {
        game_dir: fixture::write(dir),
        rtp_dir: Some(dir.join("rtp")),
        project: Project::open(&dir.join("project")).unwrap(),
    }
}

/// The fixture's game compiled with `job`, the ARAM up to `aram_end`.
fn compile(dir: &Path, job: &str, aram_end: i64) -> rm2k_snes_audio::fail::Result<Compiled> {
    let game = game(dir);
    let (job, emit) = job::parse(&serde_json::from_str(job).unwrap(), aram_end)?;
    stage::compile(&job, emit.as_ref(), &game, &dir.join("soundfont.sf2"))
}

#[test]
fn compile_answers_the_music_and_what_goes_with_it() {
    let dir = scratch("compile");
    let done = compile(&dir, fixture::JOB, fixture::ARAM_END).unwrap();
    let _ = std::fs::remove_dir_all(&dir);
    let inc = String::from_utf8(done.files["musicdata.inc"].clone()).unwrap();
    // The line the tools that read the cartridge look for.
    assert!(
        inc.lines()
            .nth(1)
            .unwrap()
            .starts_with("; Songs: alpha, beta, gamma, delta, no music"),
        "{inc}"
    );
    let songs = done.audio["songs"].as_array().unwrap();
    assert_eq!(songs.len(), 5);
    // Every sample a song plays is in the bank.
    let keys = done.audio["bank"]["keys"].as_array().unwrap().len();
    for s in songs {
        for i in s["samples"].as_array().unwrap() {
            assert!((i.as_u64().unwrap() as usize) < keys, "{s}");
        }
    }
}

/// A lone song whose samples do not fit even at the minimum is still a no:
/// there is nothing to relieve.
#[test]
fn samples_that_do_not_fit_even_at_the_minimum_are_an_answer() {
    let dir = scratch("tight");
    let done = compile(&dir, fixture::JOB, 0x0400 + 4 * 16 + 9 + 500);
    let _ = std::fs::remove_dir_all(&dir);
    match done {
        Err(Bad::Answer(e)) => assert!(e.contains("do not fit"), "{e}"),
        Err(e) => panic!("the call was taken as wrong: {e:?}"),
        Ok(_) => panic!("it fit"),
    }
}

/// A package whose sound effects do not leave room for its songs even at
/// the minimum —until 2026-10-15 the stop above— builds: its songs go
/// separate —all of them, since map 2 enters with none of its own— and its
/// last sound effects are left out, and both are said in `audio.json`, which
/// is where the converter reads them for `degradations.json`.
#[test]
fn a_package_that_does_not_fit_is_relieved_and_says_what_it_lost() {
    let dir = scratch("relieved");
    let done = compile(&dir, fixture::JOB, 0x0400 + 4 * 16 + 9 + 3000).unwrap();
    let _ = std::fs::remove_dir_all(&dir);
    let losses = done.audio["losses"].as_array().unwrap();
    let of_map_2: Vec<&Value> = losses.iter().filter(|l| l["map"] == 2).collect();
    assert_eq!(of_map_2[0]["kind"], "songs-uploaded-on-play", "{losses:?}");
    assert!(
        of_map_2[0]["text"]
            .as_str()
            .unwrap()
            .contains("its songs beta and gamma do not fit"),
        "{losses:?}"
    );
    assert_eq!(of_map_2[1]["kind"], "sound-effects-left-out", "{losses:?}");
    assert!(
        of_map_2[1]["text"]
            .as_str()
            .unwrap()
            .contains("of its 2 sound effects"),
        "{losses:?}"
    );
    // The ROM's package of map 2 carries no song, with beta and gamma
    // separate, and the sound effects that were left out are not in its list.
    let packages = done.audio["packages"].as_array().unwrap();
    let (songs, effects, _, separate) = (
        &packages[1][0],
        &packages[1][1],
        &packages[1][2],
        &packages[1][3],
    );
    assert_eq!(songs, &serde_json::json!([]), "{packages:?}");
    assert_eq!(separate, &serde_json::json!([1, 2]), "{packages:?}");
    assert!(effects.as_array().unwrap().len() < 2, "{packages:?}");
}

#[test]
fn a_broken_job_is_the_call_being_wrong() {
    let dir = scratch("broken");
    let done = compile(&dir, r#"{"songs": "alpha"}"#, fixture::ARAM_END);
    let _ = std::fs::remove_dir_all(&dir);
    match done {
        Err(Bad::Usage(e)) => assert!(e.contains("songs"), "{e}"),
        Err(e) => panic!("taken as a no: {e:?}"),
        Ok(_) => panic!("it compiled"),
    }
}

/// What the build leaves beside the ROM for each song —`song_writes`—: one
/// file per song, with what its stream writes, how long it is and its
/// repeats, the same as the stream decoded.
#[test]
fn each_song_s_writes_are_left_beside_the_rom() {
    let dir = scratch("writes");
    let done = compile(&dir, fixture::JOB, fixture::ARAM_END).unwrap();
    let _ = std::fs::remove_dir_all(&dir);
    let files = stage::song_writes(&done.music).unwrap();
    assert_eq!(files.len(), done.music.songs.len());
    for (i, song) in done.music.songs.iter().enumerate() {
        let gz = &files[&format!("{}/{i}.json.gz", stage::WRITES)];
        let left: Value = serde_json::from_reader(GzDecoder::new(gz.as_slice())).unwrap();
        assert_eq!(left["name"], song.name.as_str());
        assert_eq!(
            left["writes"],
            serde_json::json!(song.writes),
            "{}",
            song.name
        );
        if song.stream.is_empty() {
            assert_eq!(left["length"], 0, "{}", song.name);
            continue;
        }
        let (writes, length) = stream::decode_counting(&song.stream, &song.sounds).unwrap();
        assert_eq!(left["writes"], serde_json::json!(writes), "{}", song.name);
        assert_eq!(left["length"], length, "{}", song.name);
        assert_eq!(
            left["repeats"],
            serde_json::json!(stream::repeats(&song.stream).unwrap()),
            "{}",
            song.name
        );
    }
}

#[test]
fn a_wav_a_song_and_a_pitch_are_found_as_the_tests_find_them() {
    let dir = scratch("small");
    let game = game(&dir);
    let (samples, rate) = effects::wav_of(&game, "Rumble").unwrap();
    assert_eq!((rate, samples.len()), (11025, 20000));
    let zeta = game.song_path("ZETA").unwrap();
    assert!(zeta.ends_with("rtp/Music/zeta.mid"), "{}", zeta.display());
    assert!(game.song_path("nowhere").is_none());
    let _ = std::fs::remove_dir_all(&dir);
    assert_eq!(effects::pitch(22050, 100), 2822);
}
