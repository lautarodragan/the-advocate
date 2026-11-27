//! The voice allocation and the samples' budgets over songs made in the
//! test, compiled whole —from the MIDI to the stream— with the fixture's
//! SoundFont: the shapes A Blurred Line's songs showed, when the rules were
//! written, that the hand-built notes of `voices/tests.rs` and the bank's
//! own tests do not go through the MIDI and the packages.
//!
//! Until 2026-11-27 these were A Blurred Line's tests, over its songs
//! —`escape_newyork`, the battle's `T_VGFighterMAX_Masako`, `evilrhys`,
//! `lufsorr`, `Fantasia_Of_The_Wind`—, asking `rm2k-snes-audio compile`
//! and `keys`. **What moving them stops catching**: an allocation or a
//! budget that only those songs reach; the rules are the same.

mod fixture;

use fixture::{midi, note};
use rm2k_project::Project;
use rm2k_snes_audio::bank::{self, Key, Samples};
use rm2k_snes_audio::compile::{self, Built, Music};
use rm2k_snes_audio::game::Game;
use rm2k_snes_audio::samples::SoundFontSamples;
use rm2k_snes_audio::{job, sdsp, song};
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-snes-audio-shapes-{name}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// The fixture's game with `songs` —(name, MIDI)— added to its `Music/`.
fn game(dir: &Path, songs: &[(&str, Vec<u8>)]) -> (Game, Samples) {
    let game_dir = fixture::write(dir);
    for (name, data) in songs {
        std::fs::write(game_dir.join("Music").join(format!("{name}.mid")), data).unwrap();
    }
    let game = Game {
        game_dir,
        rtp_dir: Some(dir.join("rtp")),
        project: Project::open(&dir.join("project")).unwrap(),
    };
    let samples = Samples {
        font: SoundFontSamples::open(&dir.join("soundfont.sf2")).unwrap(),
    };
    (game, samples)
}

fn compile(game: &Game, samples: &Samples, job: serde_json::Value, aram_end: i64) -> Music {
    let (job, _) = job::parse(&job, aram_end).unwrap();
    compile::build(&job, game, samples).unwrap()
}

/// A program change on `channel`.
fn program(channel: u8, number: u8) -> (u32, Vec<u8>) {
    (0, vec![0xC0 | channel, number])
}

// One beat is 96 ticks: half a second, 30 frames, at the MIDI's default
// tempo.
const BEAT: u32 = 96;

/// The crowded song: on every beat an organ's three-note chord on channel
/// 0, two basses (channels 1 and 3) and five hits —two bass drums, two
/// snares and the hi-hat—, eleven notes for eight voices, all at the same
/// velocity, as `T_VGFighterMAX_Masako` has them; a three-note chord on
/// channel 2 once a bar, as `escape_newyork`'s strings; and
/// channels 5 and 7, which play little, as its clavinet and square wave.
fn crowd() -> Vec<u8> {
    let mut organ = vec![program(0, 0)];
    let mut basses = vec![program(1, 33), program(3, 33)];
    let mut strings = vec![program(2, 0)];
    let mut rare = vec![program(5, 33), program(7, 0)];
    let mut drums = Vec::new();
    for beat in 0..32u32 {
        let t = beat * BEAT;
        let root = [48u8, 53, 55, 50][(beat / 4 % 4) as usize];
        for k in [0u8, 4, 7] {
            note(&mut organ, 0, t, 80, root + 12 + k, 127);
        }
        note(&mut basses, 1, t, 80, root - 12, 127);
        note(&mut basses, 3, t, 80, root - 5, 127);
        for key in [35u8, 36, 38, 40, 42] {
            note(&mut drums, 9, t, 20, key, 127);
        }
        // Between two beats, so that nothing else starts with it.
        if beat % 4 == 1 {
            for k in [0u8, 3, 7] {
                note(&mut strings, 2, t + BEAT / 2, 300, root + k, 127);
            }
        }
        if beat % 8 == 3 {
            note(&mut rare, 5, t + 48, 40, root, 127);
            note(&mut rare, 7, t + 48, 40, root + 24, 127);
        }
    }
    midi(&[organ, basses, strings, rare, drums])
}

/// Each note as the compiler read it, by index.
fn notes(song: &Built) -> &[rm2k_snes_audio::midi::Note] {
    &song.parsed.as_ref().unwrap().notes
}

fn crowd_compiled(name: &str, headroom: Option<f64>) -> Music {
    let dir = scratch(name);
    let (game, samples) = game(&dir, &[("crowd", crowd())]);
    let music = compile(
        &game,
        &samples,
        serde_json::json!({"songs": ["crowd"], "measuring_headroom": headroom}),
        bank::ARAM_END,
    );
    let _ = std::fs::remove_dir_all(&dir);
    music
}

/// The first frame in which channel 2 starts three notes together has to
/// trigger at least three voices: until 2026-09-26 each MIDI channel had
/// its fixed voices, and `escape_newyork`'s strings got one for their
/// three-note chords.
#[test]
fn the_string_chord_sounds_whole() {
    let music = crowd_compiled("chord", None);
    let song = &music.songs[0];
    let mut starts: BTreeMap<i64, usize> = BTreeMap::new();
    for n in notes(song).iter().filter(|n| n.channel == 2) {
        *starts.entry(n.start).or_default() += 1;
    }
    let frame = *starts.iter().find(|(_, &k)| k >= 3).unwrap().0;
    let kon = song
        .writes
        .iter()
        .filter(|w| w.0 == frame && w.1 == sdsp::KON)
        .fold(0u8, |k, w| k | w.2);
    assert!(
        kon.count_ones() >= 3,
        "on frame {frame} three string notes start and KON is ${kon:02X}"
    );
}

/// The top voice of the organ's chords —channel 0— gets a voice on every
/// beat and nobody steals it before its end, with five hits and two basses
/// starting with it: what taro heard in the battle song on 2026-09-26 with
/// the allocation of that day, which gave the eight voices to the hits and
/// the basses before the melody arrived. The order of each frame is
/// `frame_order`, in `voices.rs`. With the usual headroom: it is the
/// allocation that is looked at.
#[test]
fn the_top_voice_of_the_chords_loses_no_notes() {
    let music = crowd_compiled("melody", Some(sdsp::HEADROOM));
    let song = &music.songs[0];
    let notes = notes(song);
    let mut top: BTreeMap<i64, &rm2k_snes_audio::voices::Allotted> = BTreeMap::new();
    for a in &song.allocation {
        let n = &notes[a.note];
        if n.channel == 0
            && top
                .get(&n.start)
                .is_none_or(|b| n.pitch > notes[b.note].pitch)
        {
            top.insert(n.start, a);
        }
    }
    assert_eq!(top.len(), 32, "the melody's notes");
    let lost: Vec<i64> = top
        .values()
        .filter(|a| a.voice.is_none() || a.stolen.is_some_and(|s| s < a.end))
        .map(|a| notes[a.note].start)
        .collect();
    assert!(
        lost.is_empty(),
        "{} notes of the melody do not sound whole, starting on frames {lost:?}",
        lost.len()
    );
}

/// Channels 5 and 7, which play little: some voice plays them, and their
/// samples are in the bank. With the fixed allocation `escape_newyork`'s
/// clavinet and square wave never sounded, and their programs did not even
/// get into the bank.
#[test]
fn the_channels_that_play_little_sound() {
    let music = crowd_compiled("rare", None);
    let song = &music.songs[0];
    let parsed = song.parsed.as_ref().unwrap();
    let srcn: BTreeSet<u8> = song
        .writes
        .iter()
        .filter(|w| w.1 < 0x80 && w.1 & 0x0F == sdsp::V_SRCN)
        .map(|w| w.2)
        .collect();
    let melodic = music.bank.melodic();
    for channel in [5u8, 7] {
        let played = song
            .allocation
            .iter()
            .any(|a| notes(song)[a.note].channel == channel && a.voice.is_some());
        assert!(played, "no note of channel {channel} got a voice");
        let program = parsed.program(channel);
        let index = *melodic
            .get(&program)
            .unwrap_or_else(|| panic!("program {program} of channel {channel} is not in the bank"));
        assert!(
            srcn.contains(&(music.bank.directory[index] as u8)),
            "no voice plays program {program} of channel {channel}"
        );
    }
}

/// The keys each song asks for and what each whole sample weighs: what
/// everything weighs before sharing out the ARAM.
fn keys(
    game: &Game,
    samples: &Samples,
    names: &[&str],
) -> (Vec<BTreeSet<Key>>, BTreeMap<Key, i64>) {
    let parsed: Vec<_> = names.iter().map(|n| song::read(n, game).unwrap()).collect();
    let roots = bank::most_used_zones(&parsed, &samples.font);
    let keys: Vec<BTreeSet<Key>> = parsed
        .iter()
        .map(|p| bank::song_keys(p.as_ref(), &roots))
        .collect();
    let mut natives = BTreeMap::new();
    for k in keys.iter().flatten() {
        if let Some(v) = samples.sample(k, bank::NATIVE).unwrap() {
            natives.insert(k.clone(), v.data.len() as i64);
        }
    }
    (keys, natives)
}

/// What the samples of those keys —the bank's own, copies included— take.
fn takes(bank: &bank::Bank, keys: &BTreeSet<&Key>) -> i64 {
    bank.keys
        .iter()
        .zip(&bank.voices)
        .filter(|(k, _)| keys.contains(k))
        .map(|(_, v)| v.data.len() as i64)
        .sum()
}

/// Each song's own samples: a key can have copies.
fn own(bank: &bank::Bank, song: usize) -> BTreeSet<&Key> {
    bank.assignment[song].values().collect()
}

/// A song for the budgets: `beats` beats of `melodic` (channel, program,
/// key) notes and `hits`.
fn plain(melodic: &[(u8, u8, u8)], hits: &[u8]) -> Vec<u8> {
    let mut events = Vec::new();
    for &(channel, number, _) in melodic {
        events.push(program(channel, number));
    }
    for beat in 0..8u32 {
        for &(channel, _, key) in melodic {
            note(&mut events, channel, beat * BEAT, 60, key, 100);
        }
        for &key in hits {
            note(&mut events, 9, beat * BEAT, 20, key, 100);
        }
    }
    midi(&[events])
}

/// Every song with all its samples, and each sample limited only by the
/// packages it is in: three songs and the ARAM shrunk by hand, so that the
/// package of two of them does not fit untrimmed and the third's does.
///
/// Until 2026-09-26 the whole bank had to fit in the ARAM, and the songs
/// that did not fit stopped contributing programs —a note whose program is
/// not in the bank does not reach the stream—. And the inheritance: a
/// package also has to fit with the song that may come playing, without
/// its effects.
#[test]
fn each_samples_budget_is_that_of_its_worst_package() {
    let dir = scratch("budget");
    let names = ["low", "deep", "high"];
    let (game, samples) = game(
        &dir,
        &[
            ("low", plain(&[(0, 0, 55)], &[35])),
            ("deep", plain(&[(1, 33, 40)], &[38])),
            ("high", plain(&[(0, 0, 84)], &[42])),
        ],
    );
    let (keys, native) = keys(&game, &samples, &names);
    let squeezed: BTreeSet<Key> = keys[0].union(&keys[1]).cloned().collect();
    let only_the_thirds: BTreeSet<&Key> = keys[2].difference(&squeezed).collect();
    assert!(
        !only_the_thirds.is_empty(),
        "the third song has no samples of its own"
    );
    // The ARAM is measured, not written: half of what the first two's
    // samples would take whole, plus the directory.
    let free = squeezed.iter().map(|k| native[k]).sum::<i64>() / 2;
    assert!(
        free > keys[2].iter().map(|k| native[k]).sum::<i64>(),
        "the whole third song does not fit in the shrunk ARAM"
    );
    let music = compile(
        &game,
        &samples,
        serde_json::json!({
            "songs": names,
            "packages": [{"name": "full", "songs": [0, 1]}, {"name": "roomy", "songs": [2]}],
            "inheritance": [["roomy", 0]],
        }),
        bank::SAMPLES_ADDR + free + 4 * native.len() as i64 + bank::SILENCE.len() as i64,
    );
    let _ = std::fs::remove_dir_all(&dir);
    let bank = &music.bank;
    for song in &music.songs {
        assert_eq!(
            song.notes_sound,
            Some(1.0),
            "{} is missing notes: every song contributes its samples to the bank",
            song.name
        );
    }
    let full: BTreeSet<&Key> = own(bank, 0).union(&own(bank, 1)).copied().collect();
    assert!(
        takes(bank, &full) <= bank.free,
        "the first two's package takes {} B and there are {}",
        takes(bank, &full),
        bank.free
    );
    assert!(
        takes(bank, &full) < squeezed.iter().map(|k| native[k]).sum::<i64>(),
        "the full package trimmed nothing: the ARAM did not shrink"
    );
    let with_the_first: BTreeSet<&Key> = own(bank, 0).union(&own(bank, 2)).copied().collect();
    assert!(
        takes(bank, &with_the_first) <= bank.free,
        "the third's package does not fit with the first playing"
    );
    for k in &keys[2] {
        let its = &bank.assignment[2][k];
        assert_ne!(
            bank.limited_by.get(its).map(String::as_str),
            Some("full"),
            "the third's sample {k} is limited by the full package, where it is not"
        );
    }
}

/// A song that shares a program with that of a full package is not limited
/// by that package: its own is another sample, a copy. Until 2026-09-26
/// there was one sample per program in the whole cartridge with the budget
/// of its worst package, so a map's effects left the drums of every song of
/// the game at 10 kHz.
#[test]
fn a_program_does_not_pay_for_a_package_where_it_does_not_play() {
    let dir = scratch("copies");
    let names = ["busy", "light"];
    let (game, samples) = game(
        &dir,
        &[
            ("busy", plain(&[(0, 0, 55)], &[35, 38])),
            ("light", plain(&[(0, 0, 55)], &[35])),
        ],
    );
    let (keys, native) = keys(&game, &samples, &names);
    let shared: BTreeSet<&Key> = keys[0].intersection(&keys[1]).collect();
    assert!(!shared.is_empty(), "the two songs share no sample");
    let free = keys[0].iter().map(|k| native[k]).sum::<i64>() / 2;
    assert!(
        free > keys[1].iter().map(|k| native[k]).sum::<i64>(),
        "the whole second song does not fit in the shrunk ARAM"
    );
    let music = compile(
        &game,
        &samples,
        serde_json::json!({
            "songs": names,
            "packages": [{"name": "full", "songs": [0]}, {"name": "roomy", "songs": [1]}],
        }),
        bank::SAMPLES_ADDR
            + free
            + 4 * (native.len() + shared.len()) as i64
            + bank::SILENCE.len() as i64,
    );
    let _ = std::fs::remove_dir_all(&dir);
    let bank = &music.bank;
    let bytes = |k: &Key| {
        let i = bank.keys.iter().position(|x| x == k).unwrap();
        bank.voices[i].data.len() as i64
    };
    let mut trimmed = Vec::new();
    for k in shared {
        assert!(
            bytes(&bank.assignment[0][k]) < native[k],
            "the busy song's sample {k} was not trimmed: the ARAM did not shrink enough"
        );
        let other = &bank.assignment[1][k];
        if bytes(other) < native[k] {
            trimmed.push(format!(
                "{k} ({} of {} B, limited by {})",
                bytes(other),
                native[k],
                bank.limited_by.get(other).map_or("nobody", String::as_str)
            ));
        }
    }
    assert!(
        trimmed.is_empty(),
        "the light song pays for the busy one's full package, where it is not: {}",
        trimmed.join(", ")
    );
}
