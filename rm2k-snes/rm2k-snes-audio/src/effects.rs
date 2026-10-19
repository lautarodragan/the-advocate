//! The sound effects: the WAVs of `PlaySound`, from the game or the RTP.
//!
//! They go in the same ARAM as the music bank, with **what the music leaves
//! free**: the music comes first. A sound effect is trimmed to
//! `SE_MAX_SECONDS` at `SE_RATE`, and one longer than that repeats its last
//! `SE_LOOP_SECONDS` until it lasts as long as it does in RM2k; the ones the
//! game lists as whole go whole, at their own rate.
//!
//! And their MSU-1 versions: with MSU-1 the SPC700 plays no music, so the
//! ARAM is left for the sound effects, and each package gets its own version
//! of each, whole and at the highest rates that fit —see
//! [`rates_per_package`]—. The cartridge cannot carry that many, so they go
//! in the `.msu`, which has no cap.

use crate::audible::Audible;
use crate::fail::Result;
use crate::num;
use crate::samples::{self, BLOCK, BLOCK_BYTES};
use crate::sdsp;
use std::collections::{BTreeMap, HashMap};
use std::path::Path;

pub const SE_RATE: i64 = 6000;
const SE_MAX_SECONDS: f64 = 0.75;
const SE_LOOP_SECONDS: f64 = 0.4;

/// A sound effect ready for the SPC700: `data` in BRR, at `rate`, which goes
/// back to block `loop_block` if it repeats, and lasts `seconds` in RM2k.
#[derive(Clone, Debug)]
pub struct SoundEffect {
    pub name: String,
    pub data: Vec<u8>,
    pub rate: i64,
    pub loop_block: usize,
    pub repeats: bool,
    pub seconds: f64,
}

/// A WAV's samples as 16-bit integers, mixed down to mono, and its rate.
/// None if it is not a WAV that can be understood: PCM of 8 or 16 bits.
///
/// It reads them the way Python's `wave` module did until 2026-09-29,
/// odd cases included —a data chunk cut short, a RIFF size that ends before
/// the file—, because the samples it gives go into the cartridge.
pub fn read_wav_bytes(data: &[u8]) -> Option<(Vec<i64>, i64)> {
    // The RIFF chunk bounds everything read inside it.
    if data.len() < 8 || &data[..4] != b"RIFF" {
        return None;
    }
    let riff_size = u32::from_le_bytes(data[4..8].try_into().ok()?) as usize;
    let riff_end = 8usize.saturating_add(riff_size);
    // What the outer chunk lets be read, from `at`, up to `n` bytes.
    let outer = |at: usize, n: usize| -> &[u8] {
        let end = at.saturating_add(n).min(riff_end).min(data.len());
        if at >= end {
            &[]
        } else {
            &data[at..end]
        }
    };
    if outer(8, 4) != b"WAVE" {
        return None;
    }
    let mut pos = 12;
    let mut format: Option<(u16, u32, usize)> = None; // channels, rate, width
    loop {
        let name = outer(pos, 4);
        if name.len() < 4 {
            return None; // no data chunk
        }
        let size_bytes = outer(pos + 4, 4);
        if size_bytes.len() < 4 {
            return None;
        }
        let size = u32::from_le_bytes(size_bytes.try_into().ok()?) as usize;
        let body = pos + 8;
        let chunk = |at: usize, n: usize| -> &[u8] {
            let limit = body.saturating_add(size);
            outer(body + at, n.min(limit.saturating_sub(body + at)))
        };
        if name == b"fmt " {
            let head = chunk(0, 14);
            if head.len() < 14 {
                return None;
            }
            let tag = u16::from_le_bytes([head[0], head[1]]);
            let channels = u16::from_le_bytes([head[2], head[3]]);
            let rate = u32::from_le_bytes([head[4], head[5], head[6], head[7]]);
            if tag != 1 && tag != 0xFFFE {
                return None;
            }
            let bits = chunk(14, 2);
            if bits.len() < 2 {
                return None;
            }
            let bits = u16::from_le_bytes([bits[0], bits[1]]) as usize;
            if tag == 0xFFFE {
                let ext = chunk(16, 24);
                // The PCM subformat's GUID.
                const PCM: [u8; 16] = [
                    0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10, 0x00, 0x80, 0x00, 0x00, 0xAA, 0x00,
                    0x38, 0x9B, 0x71,
                ];
                if ext.len() < 24 || ext[8..24] != PCM {
                    return None;
                }
            }
            let width = bits.div_ceil(8);
            if width == 0 || channels == 0 {
                return None;
            }
            format = Some((channels, rate, width));
        } else if name == b"data" {
            let (channels, rate, width) = format?;
            let frame = channels as usize * width;
            let frames = size / frame;
            let bytes = chunk(0, frames * frame);
            let raw: Vec<i64> = match width {
                1 => bytes.iter().map(|&b| (b as i64 - 128) << 8).collect(),
                2 => bytes
                    .chunks(2)
                    .map(|c| {
                        if c.len() == 2 {
                            i16::from_le_bytes([c[0], c[1]]) as i64
                        } else {
                            c[0] as i8 as i64
                        }
                    })
                    .collect(),
                _ => return None,
            };
            let channels = channels as usize;
            let raw = if channels > 1 {
                raw.chunks(channels)
                    .map(|c| num::floor_div(c.iter().sum(), channels as i64))
                    .collect()
            } else {
                raw
            };
            return Some((raw, rate as i64));
        }
        // Skip the chunk, with its pad byte if its size is odd; past the end
        // of the RIFF is a file that is not understood.
        let next = body + size + (size & 1);
        if next > riff_end {
            return None;
        }
        pos = next;
    }
}

pub fn read_wav(path: &Path) -> Option<(Vec<i64>, i64)> {
    read_wav_bytes(&std::fs::read(path).ok()?)
}

/// The WAV of a sound effect by its name —what goes before an `@` is the
/// file, what goes after tells two versions of it apart—.
pub fn wav_of(game: &crate::game::Game, name: &str) -> Option<(Vec<i64>, i64)> {
    read_wav(&game.sound_path(name.split('@').next().unwrap())?)
}

/// Builds a sound effect at `rate`, or whole at its own if `whole` has it;
/// None if its WAV is missing or empty.
pub fn build(
    name: &str,
    wav: Option<&(Vec<i64>, i64)>,
    rate: i64,
    whole: &BTreeMap<String, i64>,
) -> Result<Option<SoundEffect>> {
    let Some((raw, source)) = wav else {
        return Ok(None);
    };
    if raw.is_empty() {
        return Ok(None);
    }
    let source = *source;
    let seconds = raw.len() as f64 / source as f64;
    let mut keep = raw.len().min((SE_MAX_SECONDS * source as f64) as usize);
    let mut rate = rate;
    if let Some(&r) = whole.get(name) {
        rate = r;
        keep = raw.len();
    }
    let out = ((num::round((keep as i64 * rate) as f64 / source as f64) / BLOCK as i64)
        * BLOCK as i64)
        .max(BLOCK as i64) as usize;
    let audio = samples::normalize(&samples::resample(&raw[..keep], out, false, &[]));
    let mut loop_block = None;
    if keep < raw.len() {
        let loop_length = (SE_LOOP_SECONDS * rate as f64) as i64 / BLOCK as i64;
        loop_block = Some(((out / BLOCK) as i64 - loop_length.max(1)).max(0) as usize);
    }
    Ok(Some(SoundEffect {
        name: name.to_string(),
        data: samples::encode(&audio, loop_block)?,
        rate,
        loop_block: loop_block.unwrap_or(0),
        repeats: loop_block.is_some(),
        seconds,
    }))
}

/// The DSP pitch register: 4096 is the 32 kHz rate, and RM2k's tempo —from
/// 50 to 150— stretches it.
pub fn pitch(rate: i64, tempo: i64) -> i64 {
    num::round(rate as f64 * 4096.0 / 32000.0 * tempo as f64 / 100.0).min(0x3FFF)
}

/// How long it lasts, in 60 Hz frames, with the tempo applied.
pub fn frames(seconds: f64, tempo: i64) -> i64 {
    num::round(seconds * 60.0 * 100.0 / tempo.max(1) as f64).max(1)
}

/// DSP left and right, from 0 to 127, from RM2k's volume and pan: pan at
/// 50 is the center, and toward each side the other one drops.
pub fn volume(volume: i64, balance: i64) -> (i64, i64) {
    // The $60 was chosen with the master volume at $60, which also applies to
    // the sound effects. With the headroom the master went up, and the sound
    // effect's ceiling goes down by the same amount so it sounds the same.
    let v = num::floor_div(
        volume.clamp(0, 100) * num::round((0x60 * 0x60) as f64 / sdsp::master() as f64),
        100,
    );
    let left = num::floor_div(v * (100 - balance).min(50), 50);
    let right = num::floor_div(v * balance.min(50), 50);
    (left.clamp(0, 0x7F), right.clamp(0, 0x7F))
}

// --- the MSU-1 versions ----------------------------------------------------

/// The rates to choose from, highest to lowest. 22,050 Hz is the rate of
/// the RTP's WAVs, so there is no resampling; stepped so that the same
/// version serves more than one package.
const RATES: [i64; 20] = [
    22050, 20000, 18000, 16000, 14000, 12000, 11025, 10000, 9000, 8000, 7500, 7000, 6500, 6000,
    5500, 5000, 4500, 4000, 3500, 3000,
];

/// What a sound effect of `length` samples at `source_rate` Hz takes in BRR,
/// whole at `rate`: the same arithmetic as [`build_msu`], without building
/// it.
fn msu_size(length: usize, source_rate: i64, rate: i64) -> i64 {
    let rate = rate.min(source_rate);
    let count =
        ((num::round((length as i64 * rate) as f64 / source_rate as f64) / 16) * 16).max(16);
    count / 16 * BLOCK_BYTES as i64
}

/// The whole sound effect, without a loop, at `rate` —or at its WAV's rate,
/// if lower—, in BRR, and the rate it ended at. The normalization is the
/// cartridge's: it sounds as loud.
pub fn build_msu(wav: &(Vec<i64>, i64), rate: i64) -> Result<(i64, Vec<u8>)> {
    let (raw, source) = wav;
    let rate = rate.min(*source);
    let count = ((num::round((raw.len() as i64 * rate) as f64 / *source as f64) / BLOCK as i64)
        * BLOCK as i64)
        .max(BLOCK as i64) as usize;
    let audio = samples::normalize(&samples::resample(raw, count, false, &[]));
    Ok((rate, samples::encode(&audio, None)?))
}

/// A package, as [`rates_per_package`] sees it: its name, its sound effects
/// in order, and the bytes of the music that does get uploaded with MSU-1
/// —that of its songs that have no track—.
pub struct MsuPackage {
    pub name: String,
    pub effects: Vec<String>,
    pub music_bytes: i64,
}

/// What [`rates_per_package`] needs of a sound effect's WAV: how many
/// samples it has, at which rate, and how much of what is heard of it each
/// rate loses.
pub struct MsuSource {
    pub length: usize,
    pub rate: i64,
    pub audible: Audible,
}

impl MsuSource {
    pub fn new(wav: &(Vec<i64>, i64)) -> MsuSource {
        MsuSource {
            length: wav.0.len(),
            rate: wav.1,
            audible: Audible::new(&wav.0, wav.1),
        }
    }

    fn size(&self, rate: i64) -> i64 {
        msu_size(self.length, self.rate, rate)
    }
}

/// {package: [(sound effect, rate)]}: at which rate each sound effect of
/// each package goes in the `.msu`.
///
/// **Always whole, and each one at its own rate**: all of them start at the
/// highest, and while the package does not fit, one of them goes down a
/// step —see [`fit`]—. A sound effect the cartridge already carries whole
/// ends up no worse than without MSU-1: its rate is the floor. One the
/// cartridge carries trimmed may end up at a lower rate than there, but
/// whole.
///
/// Until 2026-09-30 it was a single rate per package, the highest at which
/// all of them fit: a two-second thunder took the battle's sound effects to
/// 12,000 Hz, and the sword's `Attack2`, which is almost all above 5 kHz,
/// lost more than half of what is heard of it so that the thunder, which is
/// almost all rumble, could fit.
///
/// `effects` are the cartridge's; `free` is what the ARAM has for samples,
/// of which `margin` is left.
pub fn rates_per_package(
    packages: &[MsuPackage],
    effects: &BTreeMap<String, SoundEffect>,
    sources: &HashMap<String, MsuSource>,
    free: i64,
    margin: i64,
) -> Vec<(String, Vec<(String, i64)>)> {
    let mut out = Vec::new();
    for p in packages {
        let mut own: Vec<&String> = Vec::new();
        for e in &p.effects {
            if effects.contains_key(e) && !own.contains(&e) {
                own.push(e);
            }
        }
        if own.is_empty() {
            continue;
        }
        let room = free - margin - p.music_bytes;
        let bottom = || {
            own.iter()
                .map(|e| RATES[RATES.len() - 1].max(floor(effects, e)))
                .collect()
        };
        let rates = fit(&own, effects, sources, room).unwrap_or_else(|| {
            println!(
                "  high-quality sound effects: package {} does not fit even at {} Hz; the \
                 ones that do not fit do not play with MSU-1",
                p.name,
                RATES[RATES.len() - 1]
            );
            bottom()
        });
        out.push((
            p.name.clone(),
            own.iter().map(|e| e.to_string()).zip(rates).collect(),
        ));
    }
    out
}

/// The rate a sound effect cannot go below: the cartridge's, if it carries
/// it whole.
fn floor(effects: &BTreeMap<String, SoundEffect>, e: &str) -> i64 {
    if effects[e].repeats {
        0
    } else {
        effects[e].rate
    }
}

/// Each sound effect's rate so that all of them fit in `room`, or None if
/// not even all of them at the bottom do.
///
/// **The one that goes down a step is the one that loses the least of what
/// is heard for each byte it frees**, as [`Audible`] measures it; if two
/// lose the same, the heavier. The obvious rule —the heaviest goes down
/// first, since it frees the most— was measured against this one on
/// `release`'s packages on 2026-09-30, and in five of them it left the
/// package's worst sound effect worse off than the single rate did: the
/// long ones are often the ones whose sound is all up high, and a breaking
/// glass went to 7,500 Hz and lost four fifths of what is heard of it. With
/// this one, no package's worst ended up worse. Measuring what each one
/// loses is what that rule was trying to guess: a low rumble like the
/// thunder loses little, so it goes down, and the glass does not.
///
/// What it does not look at is how the sum is split: it minimizes what the
/// package loses in all, so in a crowded one —18 and 20 sound effects in
/// maps 2 and 3— some end up lower than with the single rate so that
/// others end up much higher.
///
/// And once it fits, what is left over goes back, a step at a time, to the
/// one that gets the most back for each byte: the steps down are greedy and
/// the last one may have freed more than was missing. **Only while it gets
/// something back**: a step up that sounds the same is only more bytes to
/// upload on every load of the package.
fn fit(
    own: &[&String],
    effects: &BTreeMap<String, SoundEffect>,
    sources: &HashMap<String, MsuSource>,
    room: i64,
) -> Option<Vec<i64>> {
    let source = |i: usize| &sources[own[i].as_str()];
    let floors: Vec<i64> = own.iter().map(|e| floor(effects, e)).collect();
    // A step of RATES, raised to the floor. Each starts at the first rate its
    // WAV has, so that a step down is always a lower rate.
    let rate = |i: usize, step: usize| RATES[step].max(floors[i]);
    let top: Vec<usize> = (0..own.len())
        .map(|i| {
            RATES
                .iter()
                .position(|&r| r <= source(i).rate)
                .unwrap_or(RATES.len() - 1)
        })
        .collect();
    let mut steps = top.clone();
    let size = |i: usize, step: usize| source(i).size(rate(i, step));
    let lost = |i: usize, step: usize| source(i).audible.lost_at(rate(i, step));
    let used = |steps: &[usize]| -> i64 { (0..own.len()).map(|i| size(i, steps[i])).sum() };

    while used(&steps) > room {
        let mut best: Option<(f64, i64, usize)> = None;
        for i in 0..own.len() {
            let s = steps[i];
            if s + 1 >= RATES.len() || rate(i, s) <= floors[i] {
                continue;
            }
            let freed = size(i, s) - size(i, s + 1);
            let cost = (lost(i, s + 1) - lost(i, s)) / freed.max(1) as f64;
            let heavy = size(i, s);
            if best.is_none_or(|(c, h, _)| cost < c || (cost == c && heavy > h)) {
                best = Some((cost, heavy, i));
            }
        }
        let (_, _, i) = best?;
        steps[i] += 1;
    }

    loop {
        let spare = room - used(&steps);
        let mut best: Option<(f64, usize)> = None;
        for i in 0..own.len() {
            let s = steps[i];
            if s == top[i] {
                continue;
            }
            let more = size(i, s - 1) - size(i, s);
            if more > spare {
                continue;
            }
            let gain = (lost(i, s) - lost(i, s - 1)) / more.max(1) as f64;
            if gain > 0.0 && best.is_none_or(|(g, _)| gain > g) {
                best = Some((gain, i));
            }
        }
        let Some((_, i)) = best else { break };
        steps[i] -= 1;
    }
    Some((0..own.len()).map(|i| rate(i, steps[i])).collect())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn wav(channels: u16, bits: u16, data: &[u8]) -> Vec<u8> {
        let mut out = b"RIFF".to_vec();
        out.extend(((36 + data.len()) as u32).to_le_bytes());
        out.extend(b"WAVEfmt ");
        out.extend(16u32.to_le_bytes());
        out.extend(1u16.to_le_bytes());
        out.extend(channels.to_le_bytes());
        out.extend(22050u32.to_le_bytes());
        out.extend((22050 * channels as u32 * bits as u32 / 8).to_le_bytes());
        out.extend((channels * bits / 8).to_le_bytes());
        out.extend(bits.to_le_bytes());
        out.extend(b"data");
        out.extend((data.len() as u32).to_le_bytes());
        out.extend_from_slice(data);
        out
    }

    #[test]
    fn eight_bits_are_unsigned_and_stereo_is_averaged_down() {
        let (raw, rate) = read_wav_bytes(&wav(1, 8, &[128, 255, 0])).unwrap();
        assert_eq!((raw, rate), (vec![0, 127 << 8, -128 << 8], 22050));
        let data: Vec<u8> = [100i16, -101, 7, 8]
            .iter()
            .flat_map(|s| s.to_le_bytes())
            .collect();
        let (raw, _) = read_wav_bytes(&wav(2, 16, &data)).unwrap();
        // -1 // 2 floors to -1.
        assert_eq!(raw, [-1, 7]);
    }

    #[test]
    fn what_is_not_pcm_is_not_read() {
        let mut w = wav(1, 16, &[0, 0]);
        w[20] = 3; // IEEE float
        assert!(read_wav_bytes(&w).is_none());
        assert!(read_wav_bytes(b"RIFX").is_none());
    }

    fn tone(hz: f64, seconds: f64) -> (Vec<i64>, i64) {
        let n = (22050.0 * seconds) as usize;
        (
            (0..n)
                .map(|i| {
                    (8000.0 * (2.0 * std::f64::consts::PI * hz * i as f64 / 22050.0).sin()) as i64
                })
                .collect(),
            22050,
        )
    }

    fn rates_of(wavs: &[(&str, (Vec<i64>, i64))], floor: i64, room: i64) -> Vec<(String, i64)> {
        let effects: BTreeMap<String, SoundEffect> = wavs
            .iter()
            .map(|(n, _)| {
                let e = SoundEffect {
                    name: n.to_string(),
                    data: vec![],
                    rate: floor,
                    loop_block: 0,
                    repeats: floor == 0,
                    seconds: 1.0,
                };
                (n.to_string(), e)
            })
            .collect();
        let sources = wavs
            .iter()
            .map(|(n, w)| (n.to_string(), MsuSource::new(w)))
            .collect();
        let package = MsuPackage {
            name: "p".into(),
            effects: wavs.iter().map(|(n, _)| n.to_string()).collect(),
            music_bytes: 0,
        };
        rates_per_package(&[package], &effects, &sources, room, 0)
            .remove(0)
            .1
    }

    #[test]
    fn the_crack_keeps_what_is_heard_even_if_it_weighs_more() {
        // Two seconds of a 7 kHz tone and one of a 60 Hz one: 24,804 and
        // 12,402 bytes at 22050 Hz. The tone goes down while it loses
        // nothing —to 16,000 Hz, which lets up to 7,200 through— and the
        // rumble after it. Lowering the heaviest first would have taken the
        // tone to 14,000, where it is gone.
        let wavs = [("crack", tone(7000.0, 2.0)), ("rumble", tone(60.0, 1.0))];
        assert_eq!(
            rates_of(&wavs, 0, 30000),
            [("crack".into(), 16000), ("rumble".into(), 20000)]
        );
    }

    #[test]
    fn what_is_left_over_goes_back_only_if_it_is_heard() {
        // Everything fits at the top: nothing goes down.
        let wavs = [("a", tone(440.0, 0.2)), ("b", tone(880.0, 0.2))];
        assert_eq!(
            rates_of(&wavs, 0, 100_000),
            [("a".into(), 22050), ("b".into(), 22050)]
        );
        // A floor of the cartridge's is kept even if the rest does not fit.
        let wavs = [("a", tone(440.0, 2.0))];
        assert_eq!(rates_of(&wavs, 6000, 10), [("a".into(), 6000)]);
    }

    #[test]
    fn the_pitch_and_the_volume_of_a_sound_effect() {
        assert_eq!(pitch(22050, 100), 2822);
        assert_eq!(pitch(32000, 150), 6144);
        assert_eq!(volume(100, 50), (73, 73));
        assert_eq!(volume(100, 0), (73, 0));
        assert_eq!(frames(1.0, 100), 60);
    }
}
