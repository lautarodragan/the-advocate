//! Each song's volume ceiling, measured by playing it in the ROM.
//!
//! The S-DSP adds up the eight voices and saturates the sum before the
//! master volume, so what keeps a song from clipping is each voice's
//! ceiling —its headroom—; this measures, per song, the highest one that
//! does not clip. The reason for the table is in `ceilings`, in [`game`],
//! which is what reads it; how it is measured, here:
//!
//! 1. **A copy of the cartridge with every song at half the headroom**
//!    ([`MEASURING_HEADROOM`]). With that none clips, so the peak measured is
//!    the true one, and since each voice's volume is linear in the ceiling,
//!    each song's with the full headroom is double.
//! 2. **Each whole song on the title screen**, in a libretro core without
//!    MSU-1, and its peak. Each one's headroom is the highest that keeps
//!    that peak [`MARGIN`] below the cap, without going past the usual
//!    [`HEADROOM`]: the ones that do not clip stay as they were.
//! 3. **The table is written, the cartridge rebuilt and measured again.**
//!    Each voice's volume is rounded to an integer, so the arithmetic is
//!    approximate: if some song still clipped, it is lowered by as much as
//!    it went over and the round repeats.
//!
//! What stays in the table, besides the headroom: each song's peak and
//! level (LUFS) with it, **up to which frame it has to be played to go
//! through its peak** —with that a test does not play the whole songs— and
//! the fingerprint of its mix, which is how a test knows the table is
//! stale.
//!
//! [`game`]: crate::game

use crate::fail::{Bad, Result};
use crate::num;
use crate::retro::Console;
use crate::sdsp;
use serde_json::Value;
use std::collections::BTreeMap;
use std::path::{Path, PathBuf};
use std::process::Command;

/// The usual headroom: what a song that does not clip keeps.
pub const HEADROOM: f64 = sdsp::HEADROOM;

/// Half the usual headroom: measured on 2026-09-26, with 0.25 none of the
/// 32 songs of the game's cartridge clips, and the loudest one stays 3.9 dB
/// below the cap.
pub const MEASURING_HEADROOM: f64 = HEADROOM / 2.0;

/// How far the peak is allowed to go: 0.5 dB below the cap. What it absorbs
/// is the rounding of each voice's volume to an integer, which makes the
/// peak not scale exactly with the headroom.
pub fn margin() -> f64 {
    num::pow(10.0, -0.5 / 20.0)
}

/// Where the cap lies in what comes out of the console: the DSP saturates
/// the sum of the voices at 16 bits and then multiplies it by the master
/// volume, MVOL/128.
pub fn cap() -> i64 {
    32767 * sdsp::master() >> 7
}

/// How many frames before the end of boot —`BOOT_FRAMES`, read from the
/// ROM— recording starts: the title screen starts its song afterwards, so
/// it is slack. A fixed number from power-on would cut off the start of
/// each song whenever boot got shorter.
pub const BEFORE_TITLE: i64 = 22;

/// How many frames past the peak a test plays.
pub const AFTER_PEAK: i64 = 60;

/// The core the songs are played in. It is the suite's, and the fastest by
/// far; any other would need the options the harness forces on it.
pub const CORE: &str = "/usr/lib/libretro/snes9x_libretro.so";

fn io(path: &Path, e: std::io::Error) -> Bad {
    Bad::usage(format!("{}: {e}", path.display()))
}

/// The names of the cartridge's songs, in the order of their indices, from
/// the `; Songs:` line of its `musicdata.inc`: "" for "no music".
pub fn song_names(directory: &Path) -> Result<Vec<String>> {
    let path = directory.join("musicdata.inc");
    let text = std::fs::read_to_string(&path).map_err(|e| io(&path, e))?;
    let line = text
        .lines()
        .find_map(|l| l.strip_prefix("; Songs: "))
        .ok_or_else(|| Bad::usage(format!("{}: no \"; Songs:\" line", path.display())))?;
    Ok(line.split(", ").map(|n| if n == "no music" { String::new() } else { n.to_string() }).collect())
}

/// One song as the compiler built it: from the `music.json` next to
/// `musicdata.inc`.
pub struct Built {
    pub name: String,
    /// One pass, in frames; 0 for a song without a stream.
    pub length: i64,
    pub fingerprint: String,
}

/// The cartridge's songs as the compiler built them, in the order of their
/// indices.
pub fn built_songs(directory: &Path) -> Result<Vec<Built>> {
    let path = directory.join("music.json");
    let text = std::fs::read_to_string(&path).map_err(|e| io(&path, e))?;
    let json: Value = serde_json::from_str(&text).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let songs = json["songs"].as_array().ok_or_else(|| Bad::usage(format!("{}: no \"songs\"", path.display())))?;
    Ok(songs
        .iter()
        .map(|t| Built {
            name: t["name"].as_str().unwrap_or_default().to_string(),
            length: t["length"].as_i64().unwrap_or(0),
            fingerprint: t["fingerprint"].as_str().unwrap_or_default().to_string(),
        })
        .collect())
}

/// {symbol: value}, from the `.sym` next to the ROM.
fn symbols_of(sfc: &Path) -> Result<BTreeMap<String, i64>> {
    let path = PathBuf::from(format!("{}.sym", sfc.display()));
    let text = std::fs::read_to_string(&path).map_err(|e| io(&path, e))?;
    let mut table = BTreeMap::new();
    for line in text.lines() {
        let mut parts = line.split_whitespace();
        if let (Some(name), Some(value)) = (parts.next(), parts.next()) {
            let value = value.parse().map_err(|_| Bad::usage(format!("{}: {line:?}", path.display())))?;
            table.insert(name.to_string(), value);
        }
    }
    Ok(table)
}

fn symbol(symbols: &BTreeMap<String, i64>, name: &str) -> Result<i64> {
    symbols.get(name).copied().ok_or_else(|| Bad::usage(format!("the ROM has no {name}")))
}

/// How far apart the two copies of the code are in an 8 MB ExHiROM: the
/// console runs it from the first 4 MB and takes the vectors from the
/// second, so the cartridge carries it in both.
const CODE_COPY: usize = 0x400000;

/// The ROM with the title screen playing `song`: the immediate of the
/// `lda #SONG_TITLE` it starts it with is changed —in each copy of the
/// code, if there are two—. It is the only way for a song to play on its
/// own, with its samples uploaded, without playing anything.
pub fn with_song_on_title(rom: &[u8], song_title: u8, song: u8) -> Result<Vec<u8>> {
    let pattern = [0xA9, song_title, 0xC9, 0xFF, 0xF0];
    let found: Vec<usize> =
        rom.windows(pattern.len()).enumerate().filter(|(_, w)| *w == pattern).map(|(i, _)| i).collect();
    let one_place = match found[..] {
        [_] => true,
        [a, b] => b - a == CODE_COPY,
        _ => false,
    };
    if !one_place {
        return Err(Bad::usage(
            "cannot find the title screen's `lda #SONG_TITLE`: how it starts its song has changed, \
             and this has to change too"
                .to_string(),
        ));
    }
    let mut patched = rom.to_vec();
    for at in found {
        patched[at + 1] = song;
    }
    Ok(patched)
}

/// (the samples, stereo interleaved, and the rate): `frames` frames of the
/// song from when the title starts it, without MSU-1. One per process: see
/// [`Console`].
pub fn play(sfc: &Path, song: u8, frames: i64) -> Result<(Vec<i16>, f64)> {
    let symbols = symbols_of(sfc)?;
    let rom = std::fs::read(sfc).map_err(|e| io(sfc, e))?;
    let rom = with_song_on_title(&rom, symbol(&symbols, "SONG_TITLE")? as u8, song)?;
    // A directory of its own, with nothing but the ROM: the core looks for
    // the `.msu` and the tracks next to it.
    let dir = std::env::temp_dir().join(format!("rm2k-snes-ceilings-{}", std::process::id()));
    std::fs::create_dir_all(&dir).map_err(|e| io(&dir, e))?;
    let path = dir.join("tema.sfc");
    let played = (|| {
        std::fs::write(&path, &rom).map_err(|e| io(&path, e))?;
        let mut console = Console::open(Path::new(CORE), &path)?;
        let rate = console.sample_rate();
        console.run((symbol(&symbols, "BOOT_FRAMES")? - BEFORE_TITLE).max(0) as usize);
        console.take_audio();
        console.run(frames.max(0) as usize);
        Ok((console.take_audio(), rate))
    })();
    let _ = std::fs::remove_dir_all(&dir);
    played
}

/// How many samples ended up at the cap.
pub fn clipped(samples: &[i16]) -> usize {
    let cap = cap();
    samples.iter().filter(|&&s| s as i64 >= cap || (s as i64) <= -cap - 1).count()
}

/// What one song gave: the samples at the cap, the peak and in which frame.
#[derive(Clone, Debug, PartialEq)]
pub struct Row {
    pub clipped: usize,
    pub peak: i64,
    pub frame: i64,
    pub lufs: Option<f64>,
}

/// The row of what was played.
pub fn row(samples: &[i16], rate: f64) -> Row {
    let mut peak = 0i64;
    let mut at = 0usize;
    for (i, &s) in samples.iter().enumerate() {
        let m = (s as i64).abs();
        // The first of the loudest, as `argmax` gives it.
        if m > peak {
            peak = m;
            at = i;
        }
    }
    // The samples are left/right pairs.
    let frame = (at / 2) as i64 * 60 / num::round(rate);
    Row { clipped: clipped(samples), peak, frame, lufs: None }
}

/// The integrated loudness, from ffmpeg's `ebur128`.
pub fn lufs(samples: &[i16], rate: f64) -> Result<f64> {
    let dir = std::env::temp_dir().join(format!("rm2k-snes-lufs-{}", std::process::id()));
    std::fs::create_dir_all(&dir).map_err(|e| io(&dir, e))?;
    let path = dir.join("t.wav");
    let rate = num::round(rate) as u32;
    let data_len = (samples.len() * 2) as u32;
    let mut wav = Vec::with_capacity(44 + samples.len() * 2);
    wav.extend_from_slice(b"RIFF");
    wav.extend_from_slice(&(36 + data_len).to_le_bytes());
    wav.extend_from_slice(b"WAVEfmt ");
    wav.extend_from_slice(&16u32.to_le_bytes());
    wav.extend_from_slice(&1u16.to_le_bytes());
    wav.extend_from_slice(&2u16.to_le_bytes());
    wav.extend_from_slice(&rate.to_le_bytes());
    wav.extend_from_slice(&(rate * 4).to_le_bytes());
    wav.extend_from_slice(&4u16.to_le_bytes());
    wav.extend_from_slice(&16u16.to_le_bytes());
    wav.extend_from_slice(b"data");
    wav.extend_from_slice(&data_len.to_le_bytes());
    for s in samples {
        wav.extend_from_slice(&s.to_le_bytes());
    }
    let measured = (|| {
        std::fs::write(&path, &wav).map_err(|e| io(&path, e))?;
        let out = Command::new("ffmpeg")
            .args(["-nostats", "-i"])
            .arg(&path)
            .args(["-af", "ebur128", "-f", "null", "-"])
            .output()
            .map_err(|e| Bad::usage(format!("ffmpeg: {e}")))?;
        last_integrated(&String::from_utf8_lossy(&out.stderr))
            .ok_or_else(|| Bad::usage("ffmpeg's ebur128 said no integrated loudness".to_string()))
    })();
    let _ = std::fs::remove_dir_all(&dir);
    measured
}

/// The last `I: <number> LUFS` of ebur128's report, which is the summary.
fn last_integrated(text: &str) -> Option<f64> {
    let mut last = None;
    let mut rest = text;
    while let Some(i) = rest.find("I:") {
        rest = &rest[i + 2..];
        let after = rest.trim_start();
        let end = after.find(|c: char| !(c.is_ascii_digit() || c == '.' || c == '-')).unwrap_or(after.len());
        let (number, tail) = after.split_at(end);
        if tail.trim_start().starts_with("LUFS") && tail.starts_with(char::is_whitespace) {
            if let Ok(v) = number.parse() {
                last = Some(v);
            }
        }
    }
    last
}

/// The peak in dB against the cap.
pub fn db(peak: i64) -> f64 {
    20.0 * (peak.max(1) as f64 / cap() as f64).log10()
}

/// The headroom that leaves a peak `peak` measured at `measured_with` at
/// [`margin`] below the cap, in thousandths and rounded down, and never
/// more than `limit`.
pub fn ceiling(peak: f64, measured_with: f64, limit: f64) -> f64 {
    let full = peak * HEADROOM / measured_with;
    let c = (1000.0 * HEADROOM * cap() as f64 * margin() / full.max(1.0)).floor() / 1000.0;
    c.min(limit)
}

/// A song that still clipped with `current`, lowered by as much as it went
/// over.
pub fn lowered(current: f64, peak: i64) -> f64 {
    (1000.0 * current * cap() as f64 * margin() / peak as f64).floor() / 1000.0
}

/// Python's `str()` of a float, for the one number the table writes that
/// way: the shortest text that reads back the same.
fn python_float(x: f64) -> String {
    format!("{x:?}")
}

/// The table, with its reason on top.
pub fn table(ceilings: &BTreeMap<String, f64>, measured: &BTreeMap<String, Row>, fingerprints: &BTreeMap<String, String>) -> String {
    let mut lines: Vec<String> = [
        "# The volume ceiling of each song of `release`: the headroom the",
        "# converter builds its stream with, instead of `sdsp::HEADROOM`.",
        "#",
        "# **Not edited by hand**: `rm2k-snes-volume-ceilings` writes it,",
        "# playing each song in the ROM and giving it the highest headroom",
        "# that does not clip; the reason and how it is measured are in it.",
        "# The table is stale if any song clips or if the mix of any of them",
        "# is no longer the one measured: the fingerprint. Any change to the",
        "# mix —the samples, the envelopes, the allocation— calls for running",
        "# it again.",
        "#",
        "# Per song: `headroom`, the ceiling; `peak`, in dB against the cap, and",
        "# `lufs`, the level, both measured with that headroom; `until`, how",
        "# many frames from the start it has to be played to go through its",
        "# peak; and `fingerprint`, that of `mix_fingerprint`.",
        "",
        "[measurement]",
    ]
    .iter()
    .map(|s| s.to_string())
    .collect();
    lines.push(format!("measuring_headroom = {}", python_float(MEASURING_HEADROOM)));
    lines.push("margin_db = -0.5".to_string());
    lines.push(String::new());
    for (name, headroom) in ceilings {
        let row = &measured[name];
        lines.push(format!("[songs.\"{name}\"]"));
        lines.push(format!("headroom = {headroom:.3}"));
        lines.push(format!("peak = {:.1}", db(row.peak)));
        lines.push(format!("lufs = {:.1}", row.lufs.unwrap_or(0.0)));
        lines.push(format!("until = {}", row.frame + AFTER_PEAK));
        lines.push(format!("fingerprint = \"{}\"", fingerprints.get(name).map(String::as_str).unwrap_or("")));
        lines.push(String::new());
    }
    lines.join("\n")
}

/// One line per song: its headroom if there is one, its peak, how many
/// samples clipped and its level.
pub fn report(measured: &BTreeMap<String, Row>, ceilings: Option<&BTreeMap<String, f64>>) -> String {
    let mut out = String::new();
    for (name, row) in measured {
        let short: String = name.chars().take(45).collect();
        let headroom = ceilings.map(|c| format!("headroom {:.3},", c[name])).unwrap_or_default();
        let level = row.lufs.map(|l| format!(", {l:.1} LUFS")).unwrap_or_default();
        out.push_str(&format!(
            "  {short:<45} {headroom} peak {:+5.1} dB, {:5} clipped{level}\n",
            db(row.peak),
            row.clipped
        ));
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_title_song_is_found_once_and_patched() {
        let rom = [0u8, 0xA9, 7, 0xC9, 0xFF, 0xF0, 3];
        assert_eq!(with_song_on_title(&rom, 7, 12).unwrap(), vec![0, 0xA9, 12, 0xC9, 0xFF, 0xF0, 3]);
        let twice = [0xA9, 7, 0xC9, 0xFF, 0xF0, 0xA9, 7, 0xC9, 0xFF, 0xF0];
        assert!(with_song_on_title(&twice, 7, 12).is_err());
        assert!(with_song_on_title(&rom, 8, 12).is_err());
    }

    #[test]
    fn both_copies_of_the_code_are_patched() {
        let mut rom = vec![0u8; 2 * CODE_COPY];
        for base in [0x9000, 0x9000 + CODE_COPY] {
            rom[base..base + 5].copy_from_slice(&[0xA9, 7, 0xC9, 0xFF, 0xF0]);
        }
        let patched = with_song_on_title(&rom, 7, 12).unwrap();
        assert_eq!((patched[0x9001], patched[0x9001 + CODE_COPY]), (12, 12));
        rom[0x9000 + CODE_COPY..0x9005 + CODE_COPY].fill(0);
        rom[0x9100..0x9105].copy_from_slice(&[0xA9, 7, 0xC9, 0xFF, 0xF0]);
        assert!(with_song_on_title(&rom, 7, 12).is_err(), "two places that are not the copies");
    }

    #[test]
    fn the_peak_is_the_first_loudest_and_its_frame() {
        // 32040 samples per second: 534 per frame, a pair each.
        let mut x = vec![0i16; 2 * 534 * 3];
        x[2 * 534 * 2 + 1] = -900;
        x[2 * 534 * 2 + 9] = 900;
        let r = row(&x, 32040.0);
        assert_eq!((r.peak, r.frame, r.clipped), (900, 2, 0));
    }

    #[test]
    fn ebur128s_summary_is_the_last_integrated_loudness() {
        let text = "t: 0.4  M: -40.1 S:-120.7  I: -40.1 LUFS  LRA: 0.0 LU\n\
                    Summary:\n\n  Integrated loudness:\n    I:         -20.5 LUFS\n    Threshold: -30.6 LUFS\n";
        assert_eq!(last_integrated(text), Some(-20.5));
    }

    #[test]
    fn the_report_keeps_its_columns() {
        let mut m = BTreeMap::new();
        m.insert("song".to_string(), Row { clipped: 3, peak: cap(), frame: 0, lufs: Some(-20.46) });
        let line = report(&m, None);
        assert_eq!(line, format!("  {:<45}  peak  +0.0 dB,     3 clipped, -20.5 LUFS\n", "song"));
    }
}
