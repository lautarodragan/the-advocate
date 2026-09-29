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
//! of each, whole and at the highest rate that fits —see
//! [`rates_per_package`]—. The cartridge cannot carry that many, so they go
//! in the `.msu`, which has no cap.

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
    let Some((raw, source)) = wav else { return Ok(None) };
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
    let out = ((num::round((keep as i64 * rate) as f64 / source as f64) / BLOCK as i64) * BLOCK as i64)
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
/// the RTP's WAVs, so there is no resampling; one fixed rate for all the
/// sound effects of a package, and stepped so that the same version serves
/// more than one package.
const RATES: [i64; 20] = [
    22050, 20000, 18000, 16000, 14000, 12000, 11025, 10000, 9000, 8000, 7500, 7000, 6500, 6000,
    5500, 5000, 4500, 4000, 3500, 3000,
];

/// What a sound effect of `length` samples at `source_rate` Hz takes in BRR,
/// whole at `rate`: the same arithmetic as [`build_msu`], without building
/// it.
fn msu_size(length: usize, source_rate: i64, rate: i64) -> i64 {
    let rate = rate.min(source_rate);
    let count = ((num::round((length as i64 * rate) as f64 / source_rate as f64) / 16) * 16).max(16);
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

/// {package: [(sound effect, rate)]}: at which rate each sound effect of
/// each package goes in the `.msu`.
///
/// **Always whole, and at the highest rate that fits**: the same for all the
/// sound effects of the package unless the cartridge's is higher. A sound
/// effect the cartridge already carries whole ends up no worse than without
/// MSU-1: its rate is the floor. One the cartridge carries trimmed may end
/// up at a lower rate than there, but whole.
///
/// `effects` are the cartridge's; `free` is what the ARAM has for samples,
/// of which `margin` is left.
pub fn rates_per_package(
    packages: &[MsuPackage],
    effects: &BTreeMap<String, SoundEffect>,
    wavs: &HashMap<String, (usize, i64)>,
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
        let floor = |e: &String| if effects[e].repeats { 0 } else { effects[e].rate };
        let room = free - margin - p.music_bytes;
        let mut chosen = Vec::new();
        let mut fits = false;
        for rate in RATES {
            chosen = own.iter().map(|e| ((*e).clone(), rate.max(floor(e)))).collect();
            let total: i64 = chosen.iter().map(|(e, r)| {
                let (length, source) = wavs[e];
                msu_size(length, source, *r)
            }).sum();
            if total <= room {
                fits = true;
                break;
            }
        }
        if !fits {
            println!(
                "  high-quality sound effects: package {} does not fit even at {} Hz; the \
                 ones that do not fit do not play with MSU-1",
                p.name,
                RATES[RATES.len() - 1]
            );
        }
        out.push((p.name.clone(), chosen));
    }
    out
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
        let data: Vec<u8> = [100i16, -101, 7, 8].iter().flat_map(|s| s.to_le_bytes()).collect();
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

    #[test]
    fn the_pitch_and_the_volume_of_a_sound_effect() {
        assert_eq!(pitch(22050, 100), 2822);
        assert_eq!(pitch(32000, 150), 6144);
        assert_eq!(volume(100, 50), (73, 73));
        assert_eq!(volume(100, 0), (73, 0));
        assert_eq!(frames(1.0, 100), 60);
    }
}
