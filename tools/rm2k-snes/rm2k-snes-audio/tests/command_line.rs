//! The binary as a caller sees it: what it writes, what it answers, and
//! with which exit code when it says no or the call is wrong.

mod fixture;

use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn binary() -> Command {
    Command::new(env!("CARGO_BIN_EXE_rm2k-snes-audio"))
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("rm2k-snes-audio-cli-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn compile(dir: &Path, aram_end: i64, extra: &[&str]) -> Output {
    binary()
        .arg("compile")
        .args(["--job", dir.join("job.json").to_str().unwrap()])
        .args(["--out", dir.join("out").to_str().unwrap()])
        .args(["--game-dir", dir.join("game").to_str().unwrap()])
        .args(["--rtp-dir", dir.join("rtp").to_str().unwrap()])
        .args(["--project", dir.join("project").to_str().unwrap()])
        .args(["--soundfont", dir.join("soundfont.sf2").to_str().unwrap()])
        .args(["--aram-end", &aram_end.to_string()])
        .args(extra)
        .output()
        .unwrap()
}

#[test]
fn compile_writes_the_music_and_what_goes_with_it() {
    let dir = scratch("compile");
    fixture::write(&dir);
    let out = compile(&dir, fixture::ARAM_END, &["--detail"]);
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let report = String::from_utf8_lossy(&out.stdout);
    assert!(report.contains("shared bank:"), "{report}");
    let inc = std::fs::read_to_string(dir.join("out/musicdata.inc")).unwrap();
    // The line the tools that read the cartridge look for.
    assert!(inc.lines().nth(1).unwrap().starts_with("; Songs: alpha, beta, gamma, delta, no music"), "{inc}");
    let audio: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("out/audio.json")).unwrap()).unwrap();
    let songs = audio["songs"].as_array().unwrap();
    assert_eq!(songs.len(), 5);
    // The detail: each song's writes and its voice allocation.
    assert!(!songs[0]["writes"].as_array().unwrap().is_empty());
    assert!(!songs[0]["allocation"].as_array().unwrap().is_empty());
    // Every sample a song plays is in the bank.
    let keys = audio["bank"]["keys"].as_array().unwrap().len();
    for s in songs {
        for i in s["samples"].as_array().unwrap() {
            assert!((i.as_u64().unwrap() as usize) < keys, "{s}");
        }
    }
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn samples_that_do_not_fit_even_at_the_minimum_are_an_answer() {
    let dir = scratch("tight");
    fixture::write(&dir);
    let out = compile(&dir, 0x0400 + 4 * 16 + 9 + 3000, &[]);
    assert_eq!(out.status.code(), Some(1), "{}", String::from_utf8_lossy(&out.stderr));
    let e = String::from_utf8_lossy(&out.stderr);
    assert!(e.contains("do not fit"), "{e}");
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn a_broken_job_is_the_call_being_wrong() {
    let dir = scratch("broken");
    fixture::write(&dir);
    std::fs::write(dir.join("job.json"), r#"{"songs": "alpha"}"#).unwrap();
    let out = compile(&dir, fixture::ARAM_END, &[]);
    assert_eq!(out.status.code(), Some(2));
    assert!(String::from_utf8_lossy(&out.stderr).contains("songs"));
    let _ = std::fs::remove_dir_all(&dir);
}

/// What `decode` gives for a stream is what `compile` said the song writes.
#[test]
fn decode_gives_what_the_song_writes() {
    let dir = scratch("decode");
    fixture::write(&dir);
    assert!(compile(&dir, fixture::ARAM_END, &["--detail"]).status.success());
    let audio: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("out/audio.json")).unwrap()).unwrap();
    // The stream is in musicdata.inc: `song_stream_1:` and its `.byte` lines.
    let inc = std::fs::read_to_string(dir.join("out/musicdata.inc")).unwrap();
    let mut stream = Vec::new();
    let mut inside = false;
    for line in inc.lines() {
        if line == "song_stream_1:" {
            inside = true;
        } else if inside && line.starts_with("    .byte ") {
            stream.extend(line[10..].split(',').map(|b| u8::from_str_radix(&b[1..], 16).unwrap()));
        } else if inside {
            break;
        }
    }
    let sounds_at = |label: &str| -> Vec<u8> {
        let mut out = Vec::new();
        let mut inside = false;
        for line in inc.lines() {
            if line == label {
                inside = true;
            } else if inside && line.starts_with("    .byte ") {
                out.extend(line[10..].split(',').map(|b| u8::from_str_radix(&b[1..], 16).unwrap()));
            } else if inside {
                break;
            }
        }
        out
    };
    let base: Vec<usize> = inc
        .lines()
        .skip_while(|l| *l != "song_sounds:")
        .nth(1)
        .unwrap()
        .trim()
        .trim_start_matches(".word ")
        .split(", ")
        .map(|n| n.parse().unwrap())
        .collect();
    let sounds = &sounds_at("music_sounds:")[base[1]..base[2]];
    std::fs::write(dir.join("stream"), &stream).unwrap();
    std::fs::write(dir.join("sounds"), sounds).unwrap();
    let out = binary()
        .args(["decode", "--stream", dir.join("stream").to_str().unwrap()])
        .args(["--sounds", dir.join("sounds").to_str().unwrap()])
        .output()
        .unwrap();
    assert!(out.status.success(), "{}", String::from_utf8_lossy(&out.stderr));
    let decoded: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!(decoded["writes"], audio["songs"][1]["writes"]);
    assert_eq!(decoded["length"].as_u64(), Some(stream.len() as u64));
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn wav_find_song_and_pitch_answer_what_they_are_asked() {
    let dir = scratch("small");
    fixture::write(&dir);
    let place = |cmd: &mut Command| {
        cmd.args(["--game-dir", dir.join("game").to_str().unwrap()])
            .args(["--rtp-dir", dir.join("rtp").to_str().unwrap()])
            .args(["--project", dir.join("project").to_str().unwrap()]);
    };
    let mut wav = binary();
    wav.args(["wav", "Rumble"]);
    place(&mut wav);
    let out = wav.output().unwrap();
    let w: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert_eq!((w["rate"].as_i64(), w["samples"].as_array().unwrap().len()), (Some(11025), 20000));

    let mut find = binary();
    find.args(["find-song", "ZETA"]);
    place(&mut find);
    let out = find.output().unwrap();
    assert!(String::from_utf8_lossy(&out.stdout).trim().ends_with("rtp/Music/zeta.mid"));
    let mut missing = binary();
    missing.args(["find-song", "nowhere"]);
    place(&mut missing);
    assert_eq!(missing.output().unwrap().status.code(), Some(1));

    let out = binary().args(["pitch", "--rate", "22050", "--tempo", "100"]).output().unwrap();
    assert_eq!(String::from_utf8_lossy(&out.stdout).trim(), "2822");
    let _ = std::fs::remove_dir_all(&dir);
}
