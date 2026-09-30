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
    assert_eq!(sha(data_of(&inc).as_bytes()), "d2a34be276994b01a5a73339058b1bda9fb0ce3b71b1fd197fec05b6636dca14", "musicdata.inc");
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
