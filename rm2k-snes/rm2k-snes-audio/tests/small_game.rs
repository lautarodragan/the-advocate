//! The music of a small game made inside the test —see `fixture/`—: two
//! MIDIs and a song that is not one, sound effects of 8 and 16 bits, mono
//! and stereo, whole, paid by the music and trimmed with a loop, a
//! SoundFont with two zones, a bass and a kit—, compiled with an ARAM small
//! enough that the allocation and the copies have work to do.
//!
//! **The path it guards**: those edges, which a game's music may not have.
//! What a song sounds like is not checked here: the compiler checks every
//! stream against its own writes as it builds it, A Blurred Line's
//! `test_music_writes.py` holds the console's decoder against those writes,
//! and taro listens.

mod fixture;

use rm2k_project::Project;
use rm2k_snes_audio::bank::Samples;
use rm2k_snes_audio::game::Game;
use rm2k_snes_audio::samples::SoundFontSamples;
use rm2k_snes_audio::{compile, emit, job, msu, stream};
use std::path::{Path, PathBuf};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("rm2k-snes-audio-{name}-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// The fixture's music: with one directory entry per key, or merged, as
/// the cartridge gets it.
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

/// Everything a cartridge takes of the fixture's music, merged as the
/// cartridge gets it: `musicdata.inc`, `music.json`, the MSU-1 sound
/// effects and the boot.
#[test]
fn the_fixture_compiles_into_everything_a_cartridge_takes() {
    let dir = scratch("whole");
    let (music, emit, game) = music_of(&dir, true);
    let inc = emit::musicdata(&music, &emit).unwrap();
    assert!(inc.contains("\n; Songs: "), "the line the tools read");
    let songs = emit::songs_json(&music.songs);
    assert_eq!(
        songs["songs"].as_array().unwrap().len(),
        music.songs.len(),
        "music.json has every song"
    );
    let effects = msu::effects(&music, &emit, &game).unwrap();
    let _ = std::fs::remove_dir_all(&dir);
    for p in &effects.packages {
        assert!(
            p.versions.iter().all(|&v| v < effects.versions.len()),
            "{}: a version that is not there",
            p.name
        );
    }
    let rom = emit::rom_packages(&music, &emit);
    let (frames, bytes) =
        emit::boot_frames(&music, &rom[emit.start], emit.decompress_frames).unwrap();
    assert!(
        frames > 0.0 && bytes > 0,
        "the boot: {frames} frames, {bytes} B"
    );
}

/// The fixture's bank has keys whose samples came out the same —its
/// SoundFont has two zones, and the copies of a key that reaches its native
/// rate come out as the key—: merged, they are one directory entry, and
/// every song writes the same to the DSP, but for SRCN, which points to the
/// same BRR and the same loop.
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
    music.songs.extend(std::iter::repeat_n(song.clone(), added));
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
