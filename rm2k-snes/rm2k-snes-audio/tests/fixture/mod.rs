//! A small game made inside the test: two MIDIs, a song that is a WAV, a
//! few sound effects, a SoundFont with a piano in two zones, a bass and a
//! drum kit, and the project file that decides about them.
//!
//! Everything is generated from formulas, so the same bytes come out on any
//! machine and nothing here needs the game, the RTP or a real SoundFont.

#![allow(dead_code)]

use std::path::{Path, PathBuf};

pub const DIVISION: u16 = 96;

fn varlen(mut n: u32) -> Vec<u8> {
    let mut b = vec![(n & 0x7F) as u8];
    n >>= 7;
    while n != 0 {
        b.insert(0, (n & 0x7F) as u8 | 0x80);
        n >>= 7;
    }
    b
}

/// A track from (absolute tick, event bytes), in order.
fn track(events: &[(u32, Vec<u8>)]) -> Vec<u8> {
    let mut sorted = events.to_vec();
    sorted.sort_by_key(|e| e.0);
    let mut out = Vec::new();
    let mut now = 0;
    for (tick, bytes) in sorted {
        out.extend(varlen(tick - now));
        out.extend(bytes);
        now = tick;
    }
    out.extend([0x00, 0xFF, 0x2F, 0x00]);
    let mut chunk = b"MTrk".to_vec();
    chunk.extend((out.len() as u32).to_be_bytes());
    chunk.extend(out);
    chunk
}

fn midi(tracks: &[Vec<(u32, Vec<u8>)>]) -> Vec<u8> {
    let mut data = b"MThd".to_vec();
    data.extend(6u32.to_be_bytes());
    data.extend(1u16.to_be_bytes());
    data.extend((tracks.len() as u16).to_be_bytes());
    data.extend(DIVISION.to_be_bytes());
    for t in tracks {
        data.extend(track(t));
    }
    data
}

fn note(
    events: &mut Vec<(u32, Vec<u8>)>,
    channel: u8,
    start: u32,
    length: u32,
    key: u8,
    velocity: u8,
) {
    events.push((start, vec![0x90 | channel, key, velocity]));
    // Note-off as a note-on at zero, half the time: both are read.
    if key % 2 == 0 {
        events.push((start + length, vec![0x80 | channel, key, 64]));
    } else {
        events.push((start + length, vec![0x90 | channel, key, 0]));
    }
}

/// Chords on the piano with the pedal, a bass with volume, pan and a bend
/// whose range is set to 12, drums, and a tempo change.
fn alpha() -> Vec<u8> {
    let tempo = vec![
        (0, vec![0xFF, 0x51, 0x03, 0x07, 0xA1, 0x20]),
        (960, vec![0xFF, 0x51, 0x03, 0x06, 0x1A, 0x80]),
    ];
    let mut piano = vec![
        (0, vec![0xC0, 0x00]),
        (0, vec![0xB0, 64, 127]),
        (400, vec![0xB0, 64, 0]),
    ];
    for bar in 0..8u32 {
        let root = [48u8, 53, 55, 60, 64, 57, 50, 62][bar as usize];
        for k in [0u8, 4, 7, 12] {
            note(
                &mut piano,
                0,
                bar * 192,
                150 + (k as u32) * 3,
                root + k,
                60 + 8 * k,
            );
        }
        note(&mut piano, 0, bar * 192 + 96, 40, root + 19, 110);
    }
    let mut bass = vec![
        (0, vec![0xC1, 33]),
        (0, vec![0xB1, 101, 0]),
        (0, vec![0xB1, 100, 0]),
        (0, vec![0xB1, 6, 12]),
        (0, vec![0xB1, 10, 20]),
    ];
    for i in 0..24u32 {
        note(&mut bass, 1, i * 64, 50, 36 + (i % 5) as u8 * 2, 100);
    }
    bass.push((300, vec![0xB1, 7, 60]));
    bass.push((330, vec![0xE1, 0x00, 0x50]));
    bass.push((420, vec![0xE1, 0x00, 0x40]));
    bass.push((700, vec![0xB1, 11, 90]));
    bass.push((710, vec![0xB1, 10, 100]));
    let mut drums = Vec::new();
    for i in 0..32u32 {
        note(
            &mut drums,
            9,
            i * 48,
            10,
            [36u8, 42, 38, 42][(i % 4) as usize],
            120,
        );
        if i % 8 == 0 {
            note(&mut drums, 9, i * 48, 10, 35, 127);
        }
    }
    midi(&[tempo, piano, bass, drums])
}

/// High notes on the piano —the other zone—, a bass, and more notes at once
/// than there are voices, so some are stolen and some do not play.
fn beta() -> Vec<u8> {
    let mut events = vec![
        (0, vec![0xFF, 0x51, 0x03, 0x09, 0x27, 0xC0]),
        (0, vec![0xC0, 0x00]),
        (0, vec![0xC2, 33]),
    ];
    for i in 0..12u32 {
        for k in 0..5u8 {
            note(
                &mut events,
                0,
                i * 96,
                90,
                70 + k * 3 + (i % 3) as u8,
                50 + k * 10,
            );
        }
        note(&mut events, 2, i * 96, 80, 40 + (i % 4) as u8, 90);
        note(&mut events, 2, i * 96 + 48, 20, 43, 70);
        note(&mut events, 9, i * 96, 20, 36, 100);
        note(&mut events, 9, i * 96, 20, 40, 100);
        note(&mut events, 9, i * 96 + 48, 20, 46, 80);
    }
    events.push((500, vec![0xB0, 7, 127]));
    events.push((900, vec![0xB0, 7, 40]));
    midi(&[events])
}

fn wav(channels: u16, bits: u16, rate: u32, samples: &[i32]) -> Vec<u8> {
    let data: Vec<u8> = if bits == 8 {
        samples
            .iter()
            .map(|&s| ((s >> 8) + 128).clamp(0, 255) as u8)
            .collect()
    } else {
        samples
            .iter()
            .flat_map(|&s| (s.clamp(-32768, 32767) as i16).to_le_bytes())
            .collect()
    };
    let mut out = b"RIFF".to_vec();
    out.extend(((36 + data.len()) as u32).to_le_bytes());
    out.extend(b"WAVEfmt ");
    out.extend(16u32.to_le_bytes());
    out.extend(1u16.to_le_bytes());
    out.extend(channels.to_le_bytes());
    out.extend(rate.to_le_bytes());
    out.extend((rate * channels as u32 * bits as u32 / 8).to_le_bytes());
    out.extend((channels * bits / 8).to_le_bytes());
    out.extend(bits.to_le_bytes());
    out.extend(b"data");
    out.extend((data.len() as u32).to_le_bytes());
    out.extend(data);
    out
}

/// A deterministic waveform, in integers only so it is the same on any
/// machine: a triangle with a third of its overtone, decaying as
/// `decay / (decay + t)`, plus a little noise from a linear congruential
/// generator.
fn tone(frames: usize, period: usize, decay: usize, seed: u64) -> Vec<i32> {
    let mut state = seed;
    let triangle = |t: usize, p: usize| -> i64 {
        let x = (t % p) as i64 * 4 * 10000 / p as i64;
        if x < 20000 {
            x - 10000
        } else {
            30000 - x
        }
    };
    (0..frames)
        .map(|i| {
            state = state
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            let noise = (state >> 40) as i64 % 2001 - 1000;
            let v = triangle(i, period) + triangle(i, (period / 3).max(2)) / 3 + noise;
            (v * decay as i64 / (decay + i) as i64) as i32
        })
        .collect()
}

// --- the SoundFont -----------------------------------------------------------

fn name(text: &str, len: usize) -> Vec<u8> {
    let mut b = text.as_bytes().to_vec();
    b.resize(len, 0);
    b
}

fn chunk(tag: &[u8; 4], body: &[u8]) -> Vec<u8> {
    let mut out = tag.to_vec();
    out.extend((body.len() as u32).to_le_bytes());
    out.extend_from_slice(body);
    if body.len() % 2 == 1 {
        out.push(0);
    }
    out
}

fn list(kind: &[u8; 4], chunks: &[Vec<u8>]) -> Vec<u8> {
    let mut body = kind.to_vec();
    for c in chunks {
        body.extend(c);
    }
    chunk(b"LIST", &body)
}

struct SampleSpec {
    name: &'static str,
    pcm: Vec<i32>,
    rate: u32,
    root: u8,
    correction: i8,
    /// Relative to the sample.
    loop_points: (u32, u32),
}

/// A zone: its generators, in order.
type Zone = Vec<(u16, u16)>;

fn range(low: u8, high: u8) -> (u16, u16) {
    (43, low as u16 | (high as u16) << 8)
}

fn signed(v: i32) -> u16 {
    v as i16 as u16
}

fn soundfont() -> Vec<u8> {
    let samples = vec![
        SampleSpec {
            name: "PIANO60",
            pcm: tone(3000, 84, 1500, 1),
            rate: 22050,
            root: 60,
            correction: 0,
            loop_points: (2000, 2900),
        },
        SampleSpec {
            name: "PIANO72",
            pcm: tone(2500, 42, 1400, 2),
            rate: 22050,
            root: 72,
            correction: 3,
            loop_points: (1800, 2400),
        },
        SampleSpec {
            name: "BASS40",
            pcm: tone(1500, 267, 900, 3),
            rate: 22050,
            root: 40,
            correction: -5,
            loop_points: (0, 0),
        },
        SampleSpec {
            name: "KICK",
            pcm: tone(4000, 400, 600, 4),
            rate: 22050,
            root: 60,
            correction: 0,
            loop_points: (0, 0),
        },
        SampleSpec {
            name: "SNARE",
            pcm: tone(12000, 31, 3000, 5),
            rate: 22050,
            root: 60,
            correction: 0,
            loop_points: (0, 0),
        },
        SampleSpec {
            name: "HAT",
            pcm: tone(800, 7, 200, 6),
            rate: 32000,
            root: 60,
            correction: 0,
            loop_points: (0, 0),
        },
    ];
    let mut smpl = Vec::new();
    let mut shdr = Vec::new();
    let mut at = 0u32;
    for s in &samples {
        let start = at;
        for v in &s.pcm {
            smpl.extend((*v.clamp(&-32768, &32767) as i16).to_le_bytes());
        }
        at += s.pcm.len() as u32;
        let mut r = name(s.name, 20);
        r.extend(start.to_le_bytes());
        r.extend(at.to_le_bytes());
        r.extend((start + s.loop_points.0).to_le_bytes());
        r.extend((start + s.loop_points.1).to_le_bytes());
        r.extend(s.rate.to_le_bytes());
        r.push(s.root);
        r.push(s.correction as u8);
        r.extend(0u16.to_le_bytes());
        r.extend(1u16.to_le_bytes());
        shdr.extend(r);
        // The 46 zero points the specification asks after each sample.
        smpl.extend([0u8; 92]);
        at += 46;
    }
    shdr.extend(name("EOS", 46));

    let piano_env = [
        (36, signed(3000)),
        (37, 1440),
        (38, signed(-1000)),
        (40, 30),
    ];
    let instruments: Vec<(&str, Vec<Zone>)> = vec![
        (
            "Piano",
            vec![
                [
                    vec![range(0, 65)],
                    piano_env.to_vec(),
                    vec![(54, 1), (53, 0)],
                ]
                .concat(),
                [
                    vec![range(66, 127)],
                    piano_env.to_vec(),
                    vec![(52, signed(-7)), (54, 1), (53, 1)],
                ]
                .concat(),
            ],
        ),
        // Its root, 28, is outside its range: the key it is asked with is
        // the one it plays the most.
        (
            "Bass",
            vec![vec![
                range(32, 127),
                (34, signed(-8000)),
                (36, signed(2000)),
                (37, 100),
                (38, signed(-6000)),
                (58, 28),
                (53, 2),
            ]],
        ),
        (
            "Kit",
            vec![
                vec![range(35, 36), (53, 3)],
                vec![range(38, 40), (38, signed(2000)), (53, 4)],
                vec![range(42, 46), (58, 70), (53, 5)],
            ],
        ),
    ];
    let (mut inst, mut ibag, mut igen) = (Vec::new(), Vec::new(), Vec::new());
    let mut bags = 0u16;
    let mut gens = 0u16;
    for (n, zones) in &instruments {
        let mut r = name(n, 20);
        r.extend(bags.to_le_bytes());
        inst.extend(r);
        for z in zones {
            ibag.extend(gens.to_le_bytes());
            ibag.extend(0u16.to_le_bytes());
            bags += 1;
            for (op, amount) in z {
                igen.extend(op.to_le_bytes());
                igen.extend(amount.to_le_bytes());
                gens += 1;
            }
        }
    }
    let mut r = name("EOI", 20);
    r.extend(bags.to_le_bytes());
    inst.extend(r);
    ibag.extend(gens.to_le_bytes());
    ibag.extend(0u16.to_le_bytes());
    igen.extend([0u8; 4]);

    // (name, program, bank, instrument, the preset zone's other generators)
    let presets: Vec<(&str, u16, u16, u16, Vec<(u16, u16)>)> = vec![
        ("Piano", 0, 0, 0, vec![]),
        ("Bass", 33, 0, 1, vec![(38, signed(200))]),
        ("Kit", 0, 128, 2, vec![]),
    ];
    let (mut phdr, mut pbag, mut pgen) = (Vec::new(), Vec::new(), Vec::new());
    let (mut bags, mut gens) = (0u16, 0u16);
    for (n, program, bank, instrument, extra) in &presets {
        let mut r = name(n, 20);
        r.extend(program.to_le_bytes());
        r.extend(bank.to_le_bytes());
        r.extend(bags.to_le_bytes());
        r.extend([0u8; 12]);
        phdr.extend(r);
        pbag.extend(gens.to_le_bytes());
        pbag.extend(0u16.to_le_bytes());
        bags += 1;
        for (op, amount) in extra.iter().chain(&[(41u16, *instrument)]) {
            pgen.extend(op.to_le_bytes());
            pgen.extend(amount.to_le_bytes());
            gens += 1;
        }
    }
    let mut r = name("EOP", 20);
    r.extend(0u16.to_le_bytes());
    r.extend(0u16.to_le_bytes());
    r.extend(bags.to_le_bytes());
    r.extend([0u8; 12]);
    phdr.extend(r);
    pbag.extend(gens.to_le_bytes());
    pbag.extend(0u16.to_le_bytes());
    pgen.extend([0u8; 4]);

    let body = [
        b"sfbk".to_vec(),
        list(b"INFO", &[chunk(b"ifil", &[2, 0, 1, 0])]),
        list(b"sdta", &[chunk(b"smpl", &smpl)]),
        list(
            b"pdta",
            &[
                chunk(b"phdr", &phdr),
                chunk(b"pbag", &pbag),
                chunk(b"pmod", &[0u8; 10]),
                chunk(b"pgen", &pgen),
                chunk(b"inst", &inst),
                chunk(b"ibag", &ibag),
                chunk(b"imod", &[0u8; 10]),
                chunk(b"igen", &igen),
                chunk(b"shdr", &shdr),
            ],
        ),
    ]
    .concat();
    chunk(b"RIFF", &body)
}

pub const PROJECT: &str = r#"[paths]
data = "data"
patches = "patches"
build = "build"
cases = "cases"

[sound_effects]
paid_by_music = ["Boom@big"]

[sound_effects.whole]
Chime = 11025
"Boom@big" = 16000

[music]
effect_slots_of_first_copies = 3
"#;

pub const CEILINGS: &str = r#"[songs.alpha]
headroom = 0.4
peak = -3.0
"#;

/// The job the tests compile.
pub const JOB: &str = r#"{
 "songs": ["alpha", "beta", "gamma", "delta", ""],
 "effects": ["Ping", "Rumble", "Chime", "Boom@big", "Missing", "Ping"],
 "packages": [
  {"name": "1", "songs": [0], "effects": ["Ping", "Rumble"], "exits": [1], "separate": []},
  {"name": "2", "songs": [1, 2], "effects": ["Chime", "Ping", "Missing"], "exits": [], "separate": []},
  {"name": "3", "songs": [0], "effects": ["Boom@big", "Rumble", "Ping"], "exits": [], "separate": [3]},
  {"name": "titulo", "songs": [4, 0], "effects": ["Ping", "Rumble"]}
 ],
 "inheritance": [["2", 0], ["1", 1]],
 "measuring_headroom": null,
 "system_songs": ["alpha", "Zeta", "Other"],
 "emit": {
  "packages": 3,
  "boot": 0,
  "title": 4,
  "game_over": [255, 65535],
  "map_song": [0, 255, 1],
  "sounds": [["Ping", 100, 100, 50], ["Rumble", 80, 120, 20], ["Chime", 100, 90, 70],
             ["Boom@big", 100, 100, 50], ["Nope", 100, 100, 50], ["Ping", 60, 150, 100]],
  "start": 0,
  "decompress_frames": 3.5
 }
}"#;

/// Up to where the ARAM holds samples in the tests: little enough that the
/// packages do not fit untrimmed and the allocation has work to do.
pub const ARAM_END: i64 = 0x0400 + 4 * 16 + 9 + 22000;

/// Writes the game into `dir`: `game/`, `rtp/`, `project/` and
/// `soundfont.sf2`.
pub fn write(dir: &Path) -> PathBuf {
    let game = dir.join("game");
    for d in [
        "game/Music",
        "game/Sound",
        "rtp/Music",
        "project/patches/auto/music",
    ] {
        std::fs::create_dir_all(dir.join(d)).unwrap();
    }
    std::fs::write(game.join("Music/alpha.mid"), alpha()).unwrap();
    std::fs::write(game.join("Music/Beta.MID"), beta()).unwrap();
    std::fs::write(
        game.join("Music/gamma.wav"),
        wav(1, 16, 22050, &tone(100, 50, 100, 9)),
    )
    .unwrap();
    std::fs::write(dir.join("rtp/Music/zeta.mid"), beta()).unwrap();
    std::fs::write(dir.join("rtp/Music/other.wav"), b"").unwrap();
    std::fs::write(
        game.join("Sound/Ping.wav"),
        wav(1, 16, 22050, &tone(3000, 20, 1000, 10)),
    )
    .unwrap();
    let stereo: Vec<i32> = tone(40000, 100, 30000, 11);
    std::fs::write(game.join("Sound/Rumble.wav"), wav(2, 8, 11025, &stereo)).unwrap();
    std::fs::write(
        game.join("Sound/chime.WAV"),
        wav(1, 16, 22050, &tone(30000, 30, 12000, 12)),
    )
    .unwrap();
    std::fs::write(
        game.join("Sound/Boom.wav"),
        wav(1, 16, 22050, &tone(26000, 150, 9000, 13)),
    )
    .unwrap();
    std::fs::write(dir.join("project/rm2k-snes.toml"), PROJECT).unwrap();
    std::fs::write(
        dir.join("project/patches/auto/music/ceilings.toml"),
        CEILINGS,
    )
    .unwrap();
    std::fs::write(dir.join("soundfont.sf2"), soundfont()).unwrap();
    std::fs::write(dir.join("job.json"), JOB).unwrap();
    game
}
