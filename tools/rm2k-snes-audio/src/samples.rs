//! The SNES samples, from the SoundFont the game was composed with.
//!
//! The problem is one of budget: the SPC700 has 64 KB for everything. The
//! lever is the sample rate. The DSP resamples anyway to change the pitch of
//! the note, so storing at 8 or 12 kHz costs nothing extra at run time: it
//! only costs treble. It is exactly what the console's games did.
//!
//! Three constraints rule the result:
//!
//! * **The loop has to fall on a BRR block.** The DSP loops back to the start
//!   of a nine-byte block, that is, every 16 samples. If the loop point falls
//!   mid-block, it cannot be expressed; the resampling is adjusted so it
//!   lands exactly.
//! * **The loop is not shortened.** A long loop has beating between strings
//!   inside; cutting it shorter introduces an audible periodicity, so when
//!   room runs short the rate goes down, not the length.
//! * **The attacks are not touched.** They are what tells a piano from an
//!   organ, and they are short: trimming them saves little and costs a lot.
//!
//! Gunter does the two things that are about formats —reading the SoundFont
//! and encoding BRR—, as a library.

use crate::fail::{Bad, Result};
use crate::num;
use gunter::extract::{self, Contract, Selector};
use gunter::sf2::{SoundFont, VolumeEnvelope};
use std::cell::RefCell;
use std::collections::HashMap;
use std::path::Path;
use std::rc::Rc;

/// Samples per BRR block, and bytes per block: properties of the format.
pub const BLOCK: usize = 16;
pub const BLOCK_BYTES: usize = 9;
/// Middle C: the note a melodic zone is picked with.
pub const REFERENCE_KEY: u8 = 60;
/// What each sample is normalized to.
const PEAK: f64 = 0x6800 as f64;
/// A percussion hit is cut here, and the rest is done by the DSP envelope:
/// a ride cymbal can last 2.6 seconds, almost all of it a tail that dies
/// out, and storing it whole would cost more than all the melodic
/// instruments together.
const DRUM_SECONDS: f64 = 0.5;
const MIN_RATE: i64 = 4000;
const MAX_RATE: i64 = 24000;

/// An instrument ready for the SPC700.
#[derive(Clone, Debug)]
pub struct Voice {
    /// The program, or the key of a hit.
    pub program: i64,
    pub name: String,
    /// In BRR.
    pub data: Vec<u8>,
    /// The rate it was stored at, with the zone's tuning applied.
    pub rate: f64,
    /// Which note sounds at that rate.
    pub root: i64,
    /// Which block it loops back to.
    pub loop_block: usize,
    /// How many samples it has.
    pub frames: usize,
}

// How far the low-pass reaches before lowering the rate, as a fraction of
// half the new rate: a bit below, because the filter's roll-off is not
// vertical and what goes past half aliases. And how many cycles of the
// cutoff frequency its kernel spans: more is a steeper roll-off and a longer
// filter.
const CUTOFF: f64 = 0.9;
const CYCLES: f64 = 12.0;

/// numpy's Blackman window of `m` points.
fn blackman(m: usize) -> Vec<f64> {
    if m == 1 {
        return vec![1.0];
    }
    let mf = m as f64;
    (0..m)
        .map(|i| {
            let n = 1.0 - mf + 2.0 * i as f64;
            0.42 + 0.5 * (std::f64::consts::PI * n / (mf - 1.0)).cos()
                + 0.08 * (2.0 * std::f64::consts::PI * n / (mf - 1.0)).cos()
        })
        .collect()
}

/// numpy's normalised sinc.
fn sinc(x: f64) -> f64 {
    let y = std::f64::consts::PI * x;
    let y = if y == 0.0 { f64::EPSILON } else { y };
    y.sin() / y
}

/// `samples` without what goes past `fraction` of its rate (in cycles per
/// sample): a Blackman-windowed sinc.
///
/// `circular` is for the loop: the signal repeats, so the filter sees it as
/// periodic and the loop point is not left with a step. `after` is what
/// follows the signal —the loop, after the attack—, so that the end of the
/// attack is filtered with what really plays next and not against zeros.
fn low_pass(samples: &[f64], fraction: f64, circular: bool, after: &[f64]) -> Vec<f64> {
    let half = ((CYCLES / (2.0 * fraction)).ceil() as usize).max(8);
    let taps = 2 * half + 1;
    let window = blackman(taps);
    let mut kernel: Vec<f64> = (0..taps)
        .map(|i| {
            let n = i as f64 - half as f64;
            2.0 * fraction * sinc(2.0 * fraction * n) * window[i]
        })
        .collect();
    let total = num::numpy_sum(&kernel);
    for k in &mut kernel {
        *k /= total;
    }

    if circular {
        // The kernel folded onto the loop's length, then a circular
        // convolution with it.
        let length = samples.len();
        let mut folded = vec![0.0; length];
        for (i, k) in kernel.iter().enumerate() {
            let n = i as i64 - half as i64;
            folded[n.rem_euclid(length as i64) as usize] += k;
        }
        let taps: Vec<(usize, f64)> =
            folded.iter().enumerate().filter(|(_, k)| **k != 0.0).map(|(m, k)| (m, *k)).collect();
        return (0..length)
            .map(|i| {
                let mut sum = 0.0;
                for &(m, k) in &taps {
                    sum += k * samples[(i + length - m) % length];
                }
                sum
            })
            .collect();
    }

    let mut x: Vec<f64> = samples.to_vec();
    if !after.is_empty() {
        let repeats = (half as f64 / after.len() as f64).ceil() as usize + 1;
        let tail: Vec<f64> = after.iter().copied().cycle().take(after.len() * repeats).collect();
        x.extend_from_slice(&tail[..half.min(tail.len())]);
    }
    // numpy's `convolve(x, kernel, "same")`: the full convolution from the
    // middle of the shorter of the two, as long as the longer.
    let (n, m) = (x.len(), kernel.len());
    let offset = (n.min(m) - 1) / 2;
    (0..samples.len())
        .map(|i| {
            let k = i + offset;
            let lo = k.saturating_sub(m - 1);
            let hi = k.min(n - 1);
            let mut sum = 0.0;
            for j in lo..=hi {
                sum += x[j] * kernel[k - j];
            }
            sum
        })
        .collect()
}

/// Changes a signal's length: low-pass if the rate goes down, and then
/// linear interpolation.
///
/// Since each package has its own budget there are samples that go down
/// from 22 to 10 kHz, and there whatever goes past 5 kHz would alias onto
/// the lows as noise that is not in the instrument.
pub fn resample(samples: &[i64], count: usize, circular: bool, after: &[i64]) -> Vec<i64> {
    if count == 0 || samples.is_empty() {
        return Vec::new();
    }
    if count == samples.len() {
        return samples.to_vec();
    }
    let floats: Vec<f64> = samples.iter().map(|&s| s as f64).collect();
    let filtered = if count < samples.len() {
        let after: Vec<f64> = after.iter().map(|&s| s as f64).collect();
        low_pass(&floats, CUTOFF * 0.5 * count as f64 / samples.len() as f64, circular, &after)
    } else {
        floats
    };
    let len = filtered.len();
    let step = (len - 1) as f64 / count as f64;
    (0..count)
        .map(|i| {
            let position = i as f64 * step;
            let index = position as usize;
            let fraction = position - index as f64;
            let first = filtered[index];
            let second = filtered[(index + 1).min(len - 1)];
            num::round(first + (second - first) * fraction)
        })
        .collect()
}

/// Brings the sample to a known amplitude, so the volume is decided by the
/// note's velocity and not by how loud that instrument was recorded.
pub fn normalize(samples: &[i64]) -> Vec<i64> {
    let top = samples.iter().map(|s| s.abs()).max().unwrap_or(0);
    if top == 0 {
        return samples.to_vec();
    }
    let scale = PEAK / top as f64;
    samples.iter().map(|&s| num::round(s as f64 * scale)).collect()
}

/// At which rate to store to fit in the budget, in BRR bytes: the highest
/// that fits, between `MIN_RATE` and `MAX_RATE`.
pub fn plan_rate(attack_frames: usize, loop_frames: usize, source_rate: i64, budget: i64) -> i64 {
    let frames = attack_frames + loop_frames;
    if frames == 0 {
        return MIN_RATE;
    }
    let allowed = (budget * BLOCK as i64) as f64 / BLOCK_BYTES as f64;
    let rate = source_rate as f64 * allowed / frames as f64;
    rate.min(source_rate as f64).min(MAX_RATE as f64).max(MIN_RATE as f64) as i64
}

/// Encodes to BRR, with the loop at `loop_block`.
pub fn encode(samples: &[i64], loop_block: Option<usize>) -> Result<Vec<u8>> {
    let pcm: Vec<i16> = samples
        .iter()
        .map(|&s| {
            i16::try_from(s).map_err(|_| Bad::answer(format!("sample {s} does not fit in 16 bits")))
        })
        .collect::<Result<_>>()?;
    Ok(gunter::codec::encode(&pcm, loop_block))
}

/// A zone: the name of its sample and its root key. It is what tells one
/// zone from another without extracting it.
pub type Zone = (String, u8);

/// The SoundFont, and what has already been asked of it.
pub struct SoundFontSamples {
    font: RefCell<SoundFont>,
    contracts: RefCell<HashMap<Selector, Option<Contract>>>,
    pcm: RefCell<HashMap<Selector, Rc<Vec<i16>>>>,
    voices: RefCell<HashMap<(u8, i64, u8), Option<Rc<Voice>>>>,
    drums: RefCell<HashMap<(u8, i64), Option<Rc<Voice>>>>,
}

impl SoundFontSamples {
    pub fn open(path: &Path) -> Result<SoundFontSamples> {
        Ok(SoundFontSamples {
            font: RefCell::new(SoundFont::open(path)?),
            contracts: RefCell::default(),
            pcm: RefCell::default(),
            voices: RefCell::default(),
            drums: RefCell::default(),
        })
    }

    fn contract(&self, selector: &Selector) -> Option<Contract> {
        if let Some(c) = self.contracts.borrow().get(selector) {
            return c.clone();
        }
        let c = extract::contract(&self.font.borrow(), selector);
        self.contracts.borrow_mut().insert(selector.clone(), c.clone());
        c
    }

    fn extract(&self, selector: &Selector) -> Result<Option<(Contract, Rc<Vec<i16>>)>> {
        let Some(contract) = self.contract(selector) else { return Ok(None) };
        if let Some(pcm) = self.pcm.borrow().get(selector) {
            return Ok(Some((contract, pcm.clone())));
        }
        let pcm = Rc::new(self.font.borrow_mut().pcm(contract.sample.start, contract.sample.end)?);
        self.pcm.borrow_mut().insert(selector.clone(), pcm.clone());
        Ok(Some((contract, pcm)))
    }

    fn program(program: u8, key: u8) -> Selector {
        Selector::Program { program: program as u16, bank: 0, key }
    }

    /// The zone that covers `key` in `program`, or None.
    pub fn zone(&self, program: u8, key: u8) -> Option<Zone> {
        self.contract(&Self::program(program, key)).map(|c| (c.name, c.root_key))
    }

    /// The volume envelope of the zone that covers `key` in `program`.
    pub fn envelope(&self, program: u8, key: u8) -> Option<VolumeEnvelope> {
        self.contract(&Self::program(program, key)).and_then(|c| c.envelope)
    }

    /// An instrument from the SoundFont in BRR, in `budget` bytes, with the
    /// zone that covers `key`; None if the SoundFont does not have it.
    pub fn voice(&self, program: u8, budget: i64, key: u8) -> Result<Option<Rc<Voice>>> {
        if let Some(v) = self.voices.borrow().get(&(program, budget, key)) {
            return Ok(v.clone());
        }
        let v = self.build_voice(program, budget, key)?.map(Rc::new);
        self.voices.borrow_mut().insert((program, budget, key), v.clone());
        Ok(v)
    }

    /// The fine adjustment is in making the loop land exactly on a block.
    /// First it picks how many samples the loop will have —a multiple of
    /// 16— and from that comes the real rate, which may differ a bit from
    /// the one asked for. Then the attack is brought to the nearest multiple
    /// of 16 at that same rate.
    fn build_voice(&self, program: u8, budget: i64, key: u8) -> Result<Option<Voice>> {
        let Some((sample, pcm)) = self.extract(&Self::program(program, key))? else {
            return Ok(None);
        };
        let pcm: Vec<i64> = pcm.iter().map(|&s| s as i64).collect();
        // Which zone covers the note, whether the loop is valid and where
        // the root key comes from are decisions of the format, and Gunter
        // makes them: the loop comes in frames and relative to the audio.
        let looped = sample.loops();
        let loop_start = sample.loop_start.unwrap_or(0) as usize;
        let loop_end = sample.loop_end.unwrap_or(0) as usize;
        let frames = pcm.len();
        let attack_frames = if looped { loop_start } else { frames };
        let loop_frames = if looped { loop_end - loop_start } else { 0 };
        let source_rate = sample.rate as i64;

        let mut rate = plan_rate(attack_frames, loop_frames, source_rate, budget);
        let mut ratio = rate as f64 / source_rate as f64;
        let loop_out = if looped {
            // The loop first: its length has to be a multiple of 16, and
            // from that rounding comes the rate actually declared.
            let out = ((num::round(loop_frames as f64 * ratio / BLOCK as f64) as usize) * BLOCK).max(BLOCK);
            ratio = out as f64 / loop_frames as f64;
            rate = num::round(source_rate as f64 * ratio);
            out
        } else {
            0
        };
        let attack_out = num::round(attack_frames as f64 * ratio / BLOCK as f64) as usize * BLOCK;

        let loop_pcm: &[i64] = if looped { &pcm[loop_start..loop_end] } else { &[] };
        let mut audio = resample(&pcm[..attack_frames], attack_out, false, loop_pcm);
        if looped {
            audio.extend(resample(loop_pcm, loop_out, true, &[]));
        }
        let audio = normalize(&audio);
        let loop_block = if looped { Some(attack_out / BLOCK) } else { None };
        let data = encode(&audio, loop_block)?;
        Ok(Some(Voice {
            program: program as i64,
            name: sample.name.clone(),
            data,
            rate: rate as f64 * num::pow(2.0, -(sample.tuning_cents as f64) / 1200.0),
            root: sample.root_key as i64,
            loop_block: loop_block.unwrap_or(0),
            frames: audio.len(),
        }))
    }

    /// A percussion hit from the standard kit, in `budget` bytes; None if
    /// the SoundFont does not have it, or if what fits does not reach a
    /// block.
    ///
    /// In General MIDI percussion lives in bank 128 and each key is a
    /// different instrument. Nothing is transposed, so the sample is stored
    /// to play at its original rate.
    pub fn drum(&self, note: u8, budget: i64) -> Result<Option<Rc<Voice>>> {
        if let Some(v) = self.drums.borrow().get(&(note, budget)) {
            return Ok(v.clone());
        }
        let v = self.build_drum(note, budget)?.map(Rc::new);
        self.drums.borrow_mut().insert((note, budget), v.clone());
        Ok(v)
    }

    fn build_drum(&self, note: u8, budget: i64) -> Result<Option<Voice>> {
        let selector = Selector::Program { program: 0, bank: gunter::sf2::DRUM_BANK, key: note };
        let Some((sample, pcm)) = self.extract(&selector)? else { return Ok(None) };
        let source_rate = sample.rate as i64;
        let frames = pcm.len().min((DRUM_SECONDS * source_rate as f64) as usize);
        let rate = plan_rate(frames, 0, source_rate, budget);
        let out = (num::round(frames as f64 * rate as f64 / source_rate as f64) as f64 / BLOCK as f64)
            as i64
            * BLOCK as i64;
        if out < BLOCK as i64 {
            return Ok(None);
        }
        let pcm: Vec<i64> = pcm[..frames].iter().map(|&s| s as i64).collect();
        let audio = normalize(&resample(&pcm, out as usize, false, &[]));
        let data = encode(&audio, None)?;
        Ok(Some(Voice {
            program: note as i64,
            name: sample.name.clone(),
            data,
            rate: rate as f64,
            root: sample.root_key as i64,
            loop_block: 0,
            frames: out as usize,
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_rate_is_bounded_and_never_above_the_source() {
        assert_eq!(plan_rate(0, 0, 22050, 100), MIN_RATE);
        assert_eq!(plan_rate(1000, 0, 22050, 1 << 24), 22050);
        assert_eq!(plan_rate(100000, 0, 22050, 90), MIN_RATE);
    }

    #[test]
    fn normalizing_brings_the_peak_to_the_same_height() {
        assert_eq!(normalize(&[0, 100, -200]), [0, 13312, -26624]);
        assert_eq!(normalize(&[0, 0]), [0, 0]);
    }

    #[test]
    fn resampling_to_the_same_length_changes_nothing() {
        let x: Vec<i64> = (0..100).map(|i| i * 3 - 50).collect();
        assert_eq!(resample(&x, 100, false, &[]), x);
        assert!(resample(&x, 0, false, &[]).is_empty());
        assert_eq!(resample(&x, 50, false, &[]).len(), 50);
        assert_eq!(resample(&x, 50, true, &[]).len(), 50);
    }

    /// A loop filtered as a loop has no step where it comes back: a sine
    /// that repeats exactly stays a sine.
    #[test]
    fn a_loop_is_filtered_as_periodic() {
        let x: Vec<i64> = (0..256)
            .map(|i| (10000.0 * (2.0 * std::f64::consts::PI * i as f64 / 64.0).sin()) as i64)
            .collect();
        let y = resample(&x, 128, true, &[]);
        let (first, last) = (y[0], y[127]);
        assert!((first - last).abs() < 3000, "{first} {last}");
    }
}
