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
use rm2k_snes_audio::{compile, emit, job, msu, pyjson, stream};
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};

fn sha(text: &[u8]) -> String {
    Sha256::digest(text)
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
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

/// The fixture's music: with one directory entry per key, as the Python
/// numbered it, or merged, as the cartridge gets it.
fn music_of(dir: &Path, merged: bool) -> (compile::Music, emit::Emit, Game) {
    let game_dir = fixture::write(dir);
    let game = Game {
        game_dir,
        rtp_dir: Some(dir.join("rtp")),
        project: Project::open(&dir.join("project")).unwrap(),
    };
    let samples = Samples {
        font: SoundFontSamples::open(&dir.join("soundfont.sf2")).unwrap(),
    };
    let (job, emit) = job::parse(
        &serde_json::from_str(fixture::JOB).unwrap(),
        fixture::ARAM_END,
    )
    .unwrap();
    let emit = emit.unwrap();
    let music = if merged {
        compile::build(&job, &game, &samples).unwrap()
    } else {
        compile::build_per_key(&job, &game, &samples).unwrap()
    };
    (music, emit, game)
}

/// (musicdata.inc, music.json, the MSU-1 sound effects as text, the boot),
/// with one directory entry per key: the identical samples merged since
/// 2026-10-14 are what [`identical_samples_are_one_entry_and_sound_the_same`]
/// looks at.
fn compile_fixture(dir: &Path) -> (String, String, String, (f64, i64)) {
    let (music, emit, game) = music_of(dir, false);
    let inc = emit::musicdata(&music, &emit).unwrap();
    let songs = pyjson::to_string(&emit::songs_json(&music.songs));
    let effects = msu::effects(&music, &emit, &game).unwrap();
    let mut quality = String::new();
    for v in &effects.versions {
        let hex: String = v.data.iter().map(|b| format!("{b:02x}")).collect();
        quality.push_str(&format!("{} {} {hex}\n", v.effect, v.rate));
    }
    for p in &effects.packages {
        let ints = |v: &[usize]| {
            v.iter()
                .map(|i| i.to_string())
                .collect::<Vec<_>>()
                .join(" ")
        };
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
    assert_eq!(
        sha(data_of(&inc).as_bytes()),
        "4d2bae8459dcd30e28377cdcdc8083df7703c1a04c3a261dacf6db86938a51f3",
        "musicdata.inc"
    );
    // Changed on 2026-10-13, when its keys went into English —`temas`,
    // `nombre`, `largo`, `huella`, `pista` are `songs`, `name`, `length`,
    // `fingerprint`, `track`—: with the five keys turned back, the text
    // gives the Python's c5feb36f38f182aa9dc1fc40dac8bf8e7ed208ca3b12e85fe0df83c23c240d66.
    assert_eq!(
        sha(songs.as_bytes()),
        "262e4f8f5175f63177b0af1ab84dc31a82ebe3b03455a681146de60103eb37d4",
        "music.json"
    );
    // **Not the Python's since 2026-09-30**, on purpose: that day each sound
    // effect got its own rate in the package (`effects::rates_per_package`),
    // where the Python gave all of them one. The Python's was
    // bd9599b5508c5c16…, and against it only package 3 changed —Boom@big
    // 16000 to 18000, Ping 9000 to 18000, Rumble 9000 to 7500, and so its
    // pitches— and package 1's Rumble, whose WAV is at 11025 Hz, is written
    // with that rate instead of 22050: the same bytes. Everything else came
    // out the same, the versions' bytes included.
    assert_eq!(
        sha(quality.as_bytes()),
        "409543a88da28c6fb38a3ca7d3e30995cf141f5b2bece7e3c4937bc8ae6d034a",
        "the MSU-1 sound effects"
    );
}

/// The fixture's bank has keys whose samples came out the same —its
/// SoundFont has two zones, and the copies of a key that reaches its native
/// rate come out as the key—: merged, they are one directory entry, and
/// every song writes the same to the DSP, but for SRCN, which points to the
/// same BRR and the same loop. That is what makes the merge safe to hash
/// against the Python per key, above.
#[test]
fn identical_samples_are_one_entry_and_sound_the_same() {
    let dir = scratch("merged");
    let (per_key, emit, _) = music_of(&dir, false);
    let (merged, _, _) = music_of(&dir, true);
    let _ = std::fs::remove_dir_all(&dir);
    let (before, after) = (per_key.all_samples(), merged.all_samples());
    assert!(
        after.len() < before.len(),
        "the fixture has no identical samples: {}",
        before.len()
    );
    let entries = merged.bank.entries();
    let distinct: std::collections::BTreeSet<_> = entries
        .iter()
        .map(|v| (v.data.clone(), v.loop_block))
        .collect();
    assert_eq!(distinct.len(), entries.len(), "a music sample stored twice");
    for (a, b) in per_key.songs.iter().zip(&merged.songs) {
        assert_eq!(a.stream, b.stream, "{}: the stream", a.name);
        let decode = |s: &compile::Built| stream::decode(&s.stream, &s.sounds).unwrap();
        let (wa, wb) = (decode(a), decode(b));
        assert_eq!(
            wb, b.writes,
            "{}: the writes are what the ROM writes",
            a.name
        );
        let sample = |all: &[(&'static [u8], usize)], i: u8| all.get(i as usize).copied();
        let (x, y) = (leak(&before), leak(&after));
        compile::sounds_the_same(&a.name, &wa, |i| sample(&x, i), &wb, |i| sample(&y, i)).unwrap();
        assert_eq!(a.fingerprint, b.fingerprint, "{}: the fingerprint", a.name);
    }
    // What the sound effects get is the same, numbered after fewer entries.
    for e in &merged.effects {
        let (x, y) = (
            per_key.srcn(&e.name).unwrap(),
            merged.srcn(&e.name).unwrap(),
        );
        assert_eq!(before[x], after[y], "{}", e.name);
    }
    // And the boot uploads each sample once: less than per key.
    let boot = |m: &compile::Music| {
        let rom = emit::rom_packages(m, &emit);
        emit::boot_frames(m, &rom[emit.start], emit.decompress_frames)
            .unwrap()
            .1
    };
    assert!(
        boot(&merged) < boot(&per_key),
        "{} against {}",
        boot(&merged),
        boot(&per_key)
    );
}

/// The samples with a life as long as the test's, for the comparison.
fn leak(all: &[(&[u8], usize)]) -> Vec<(&'static [u8], usize)> {
    all.iter()
        .map(|(d, l)| (&*Box::leak(d.to_vec().into_boxed_slice()), *l))
        .collect()
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
    let samples = Samples {
        font: SoundFontSamples::open(&dir.join("soundfont.sf2")).unwrap(),
    };
    let (job, emit) = job::parse(
        &serde_json::from_str(fixture::JOB).unwrap(),
        fixture::ARAM_END,
    )
    .unwrap();
    let emit = emit.unwrap();
    let mut music = compile::build(&job, &game, &samples).unwrap();
    let _ = std::fs::remove_dir_all(&dir);
    let mut song = music.songs[1].clone();
    song.sounds = (0..256).map(|i| [i as u8, 0, 0, 0, 0, 0]).collect();
    let before: usize = music.songs.iter().map(|t| t.sounds.len()).sum();
    let added = 30 - music.songs.len();
    music
        .songs
        .extend(std::iter::repeat(song.clone()).take(added));
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
    assert!(
        format!("{error:?}").contains("the music's sounds go over one bank"),
        "{error:?}"
    );
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
    std::fs::write(dir.join("rust-music.json"), songs).unwrap();
    std::fs::write(dir.join("rust-quality.txt"), quality).unwrap();
}
