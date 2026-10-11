//! The music of a small game against the music the Python gave for it.
//!
//! Until this crate existed, the same music was compiled by a Python
//! program. It was deleted once the two gave the same bytes for two whole
//! cartridges of a real game; what is left of it is here: the SHA-256 of
//! what it wrote for the game of `fixture/`, which is made inside the test
//! —two MIDIs and a song that is not one, sound effects of 8 and 16 bits,
//! mono and stereo, whole, paid by the music and trimmed with a loop, a
//! SoundFont with two zones, a bass and a kit—, compiled with an ARAM small
//! enough that the allocation and the copies have work to do.
//!
//! **If one of these changes, the music changed.** The hashes are not to be
//! regenerated to make a test pass: the Python that produced them is gone,
//! and with it the only independent answer.

mod fixture;

use rm2k_project::Project;
use rm2k_snes_audio::bank::Samples;
use rm2k_snes_audio::game::Game;
use rm2k_snes_audio::samples::SoundFontSamples;
use rm2k_snes_audio::{compile, emit, job, msu, pyjson};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

fn sha(text: &[u8]) -> String {
    Sha256::digest(text).iter().map(|b| format!("{b:02x}")).collect()
}

/// `musicdata.inc` without its comments: what the assembler reads, and the
/// one comment line that is data —`; Songs: `, which the tools that read a
/// cartridge look for—. The other comments explain the file, and are
/// free to change.
fn data_of(inc: &str) -> String {
    inc.split('\n')
        .filter(|l| !l.starts_with(';') || l.starts_with("; Songs: "))
        .collect::<Vec<_>>()
        .join("\n")
}

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("rm2k-snes-audio-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// (musicdata.inc, musica.json, the MSU-1 sound effects as text, the boot).
fn compile_fixture(dir: &Path) -> (String, String, String, (f64, i64)) {
    let game_dir = fixture::write(dir);
    let game = Game {
        game_dir,
        rtp_dir: Some(dir.join("rtp")),
        project: Project::open(&dir.join("project")).unwrap(),
    };
    let samples = Samples { font: SoundFontSamples::open(&dir.join("soundfont.sf2")).unwrap() };
    let (job, emit) =
        job::parse(&serde_json::from_str(fixture::JOB).unwrap(), fixture::ARAM_END).unwrap();
    let emit = emit.unwrap();
    let music = compile::build(&job, &game, &samples).unwrap();
    let inc = emit::musicdata(&music, &emit).unwrap();
    let songs = pyjson::to_string(&emit::songs_json(&music.songs));
    let effects = msu::effects(&music, &emit, &game).unwrap();
    let mut quality = String::new();
    for v in &effects.versions {
        let hex: String = v.data.iter().map(|b| format!("{b:02x}")).collect();
        quality.push_str(&format!("{} {} {hex}\n", v.effect, v.rate));
    }
    for p in &effects.packages {
        let ints = |v: &[usize]| v.iter().map(|i| i.to_string()).collect::<Vec<_>>().join(" ");
        let pitches: Vec<String> = p.pitches.iter().map(|(k, h)| format!("{k}:{h}")).collect();
        quality.push_str(&format!(
            "{} | {} | {} | {}\n",
            p.name,
            ints(&p.versions),
            ints(&p.rows),
            pitches.join(" ")
        ));
    }
    for (name, own) in &effects.rates {
        let own: Vec<String> = own.iter().map(|(e, r)| format!("{e}={r}")).collect();
        quality.push_str(&format!("{name}: {}\n", own.join(",")));
    }
    let rom = emit::rom_packages(&music, &emit);
    let boot = emit::boot_frames(&music, &rom[emit.start], emit.decompress_frames).unwrap();
    (inc, songs, quality, boot)
}

#[test]
fn the_music_is_the_one_the_python_wrote() {
    let dir = scratch("python");
    let (inc, songs, quality, boot) = compile_fixture(&dir);
    let _ = std::fs::remove_dir_all(&dir);
    assert_eq!(boot, (44.07861328125, 21420), "the boot's estimate");
    // Changed once on purpose, on 2026-09-30, when `song_lo`, `song_hi`,
    // `song_bk` and `song_msu` moved out of bank 0: the only difference with
    // what the Python wrote was those four tables going from `TABLES` to
    // `RODATA`, each behind its `.block`, with the same bytes. Measured with
    // `write_the_fixture` before and after.
    //
    // And a second time on 2026-10-01, when the streams started saying once
    // what they repeat —`OP_REPEAT`, "repeats" in `stream.rs`—: outside the
    // `song_stream_N` blocks the file is line by line the same, and each
    // stream, unfolded by a separate Python copy of `unfold`, is byte for
    // byte the one before (525 bytes to 515, 628 to 295). Before it was
    // 89ec531ef3d4f2ce….
    assert_eq!(sha(data_of(&inc).as_bytes()), "4d2bae8459dcd30e28377cdcdc8083df7703c1a04c3a261dacf6db86938a51f3", "musicdata.inc");
    assert_eq!(sha(songs.as_bytes()), "c5feb36f38f182aa9dc1fc40dac8bf8e7ed208ca3b12e85fe0df83c23c240d66", "musica.json");
    // **Not the Python's since 2026-09-30**, on purpose: that day each sound
    // effect got its own rate in the package (`effects::rates_per_package`),
    // where the Python gave all of them one. The Python's was
    // bd9599b5508c5c16…, and against it only package 3 changed —Boom@big
    // 16000 to 18000, Ping 9000 to 18000, Rumble 9000 to 7500, and so its
    // pitches— and package 1's Rumble, whose WAV is at 11025 Hz, is written
    // with that rate instead of 22050: the same bytes. Everything else came
    // out the same, the versions' bytes included.
    assert_eq!(sha(quality.as_bytes()), "409543a88da28c6fb38a3ca7d3e30995cf141f5b2bece7e3c4937bc8ae6d034a", "the MSU-1 sound effects");
}

/// The music's sounds of every song, in one table that goes over half a
/// bank: Vampires Dawn stopped at it with 41118 B, when the limit was the
/// LoROM bank's. The fixture's songs, copied with all 256 sounds a song can
/// ask for, until they need more than half a bank and then more than a
/// whole one.
#[test]
fn the_music_s_sounds_take_a_whole_bank_and_no_more() {
    let dir = scratch("banks");
    let game_dir = fixture::write(&dir);
    let game = Game {
        game_dir,
        rtp_dir: Some(dir.join("rtp")),
        project: Project::open(&dir.join("project")).unwrap(),
    };
    let samples = Samples { font: SoundFontSamples::open(&dir.join("soundfont.sf2")).unwrap() };
    let (job, emit) =
        job::parse(&serde_json::from_str(fixture::JOB).unwrap(), fixture::ARAM_END).unwrap();
    let emit = emit.unwrap();
    let mut music = compile::build(&job, &game, &samples).unwrap();
    let _ = std::fs::remove_dir_all(&dir);
    let mut song = music.songs[1].clone();
    song.sounds = (0..256).map(|i| [i as u8, 0, 0, 0, 0, 0]).collect();
    let before: usize = music.songs.iter().map(|t| t.sounds.len()).sum();
    let added = 30 - music.songs.len();
    music.songs.extend(std::iter::repeat(song.clone()).take(added));
    let size = 6 * (before + 256 * added);
    assert!(size > 0x8000);
    let inc = emit::musicdata(&music, &emit).unwrap();
    // One table, with its `.block`, which is what the packing keeps in one
    // bank.
    let lines: Vec<&str> = inc.lines().collect();
    let at = lines.iter().position(|l| *l == "music_sounds:").unwrap();
    assert_eq!(lines[at - 1], format!(".block {size}"));
    while 6 * music.songs.iter().map(|t| t.sounds.len()).sum::<usize>() <= 0x10000 {
        music.songs.push(song.clone());
    }
    let error = emit::musicdata(&music, &emit).unwrap_err();
    assert!(format!("{error:?}").contains("the music's sounds go over one bank"), "{error:?}");
}

/// Writes the game, and what this compiles from it, to `FIXTURE_OUT`: what
/// the hashes above were compared against.
#[test]
#[ignore]
fn write_the_fixture() {
    let dir = PathBuf::from(std::env::var("FIXTURE_OUT").expect("FIXTURE_OUT=<directory>"));
    std::fs::create_dir_all(&dir).unwrap();
    let (inc, songs, quality, _) = compile_fixture(&dir);
    std::fs::write(dir.join("rust-musicdata.inc"), inc).unwrap();
    std::fs::write(dir.join("rust-musica.json"), songs).unwrap();
    std::fs::write(dir.join("rust-quality.txt"), quality).unwrap();
}
