//! The Super Nintendo's sound chip: registers, envelopes and volume.
//!
//! The S-DSP synthesizes nothing on its own: it plays samples. Eight voices,
//! each reading a sample from the SPC700's memory at whatever speed it is
//! asked, with an ADSR envelope and a volume per side. The pitch of the note
//! comes from the reading speed, so a single sample serves for every note.
//!
//! The envelopes come from the SoundFont: [`envelope`] translates each
//! zone's into what the DSP's ADSR and GAIN can do.

use crate::num;
use gunter::sf2::VolumeEnvelope;

pub const VOICES: usize = 8;
/// What the DSP reads at with a 1:1 step.
pub const SAMPLE_RATE: i64 = 32000;
pub const MAX_PITCH: i64 = 0x3FFF;

// --- registers --------------------------------------------------------------
// The per-voice ones come in groups of 16: voice v uses v*$10 + the number.
pub const V_VOL_L: u8 = 0x00;
pub const V_VOL_R: u8 = 0x01;
pub const V_PITCH_L: u8 = 0x02;
pub const V_PITCH_H: u8 = 0x03;
pub const V_SRCN: u8 = 0x04;
pub const V_ADSR1: u8 = 0x05;
pub const V_ADSR2: u8 = 0x06;
pub const V_GAIN: u8 = 0x07;

// The global ones live in columns $xC and $xD.
pub const MVOL_L: u8 = 0x0C;
pub const MVOL_R: u8 = 0x1C;
pub const EVOL_L: u8 = 0x2C;
pub const EVOL_R: u8 = 0x3C;
pub const KON: u8 = 0x4C;
pub const KOF: u8 = 0x5C;
pub const FLG: u8 = 0x6C;
pub const PMON: u8 = 0x2D;
pub const NON: u8 = 0x3D;
pub const EON: u8 = 0x4D;
pub const DIR: u8 = 0x5D;

/// Echo off; the five low bits are the noise.
pub const FLG_BASE: u8 = 0x20;

// --- the envelopes ----------------------------------------------------------
//
// What the DSP can do, and why the translation is not direct: each phase
// advances one step every so many samples out of the 32,000 per second, and
// how many is given by `PERIOD` for the 5-bit rate number (0 is "never").
// The attack is linear and reaches the top in 64 steps; decay, sustain and
// exponential GAIN subtract 1/256 of the level per step; linear GAIN
// subtracts 1/64.
pub const PERIOD: [i64; 32] = [
    0, 2048, 1536, 1280, 1024, 768, 640, 512, 384, 320, 256, 192, 160, 128, 96, 80, 64, 48, 40, 32,
    24, 20, 16, 12, 10, 8, 6, 5, 4, 3, 2, 1,
];

// The DSP's ADSR release cannot be configured: on writing KOF the envelope
// drops to zero in about 8 ms, which sounds like an abrupt cut. That is why
// releasing a note is not done with KOF but by clearing the ADSR bit —so
// GAIN takes over— and asking it for a decrease, whose speed can be chosen.
// The envelope continues from where it was, so the note fades out.
/// Bit 7: custom mode; bits 5-6: linear.
pub const GAIN_LINEAR_DECREASE: u8 = 0x80;
/// Bits 5-6: exponential.
pub const GAIN_EXP_DECREASE: u8 = 0xA0;

/// **The DSP's exponential decrease is not exponential all the way down**:
/// below 1/8 of the level it subtracts one at a time, and from the top it
/// reaches zero in about 790 steps. Matching its slope to the SoundFont's
/// silences it too early —a piano went quiet at 1.4 s instead of continuing
/// at -26 dB—, so it is made to reach zero where the SoundFont is at about
/// -40 dB, which is "no longer audible".
pub const STEPS_TO_ZERO: i64 = 790;
const DOWN_TO_DB: f64 = 40.0;
/// A release shorter than this uses linear GAIN: the fastest exponential
/// takes 25 ms to reach zero and is not enough for a 30 ms release.
const LINEAR_RELEASE: f64 = 0.1;
/// An attack shorter than this is instantaneous (A = 15): the fastest of
/// the others, A = 14, already takes 4 ms.
const INSTANT_ATTACK: f64 = 0.004;
/// Below how much the note is considered to die out on its own while held:
/// then there is no sustain level to imitate, but a decay to follow.
const MUTED_SUSTAIN_DB: f64 = 30.0;

/// dB an exponential step drops: 20·log10(256/255).
fn db_per_step() -> f64 {
    20.0 * (256.0 / 255.0f64).log10()
}

/// The SoundFont's timecents: 1200 per octave, 0 is one second and -12000
/// is "nothing".
fn seconds(timecents: i32) -> f64 {
    if timecents > -12000 {
        num::pow(2.0, timecents as f64 / 1200.0)
    } else {
        0.0
    }
}

/// From `rates`, the one that makes the phase last closest to `seconds` on
/// a logarithmic scale; the first on a tie.
fn closest_rate(seconds: f64, duration: impl Fn(i64) -> f64, rates: std::ops::Range<i64>) -> i64 {
    let mut best: Option<(f64, i64)> = None;
    for r in rates {
        let d = (duration(r).max(1e-9) / seconds.max(1e-9)).ln().abs();
        if best.is_none_or(|(b, _)| d < b) {
            best = Some((d, r));
        }
    }
    best.unwrap().1
}

/// How long an exponential decrease at rate `r` takes to reach zero.
fn time_to_zero(r: i64) -> f64 {
    (STEPS_TO_ZERO * PERIOD[r as usize]) as f64 / SAMPLE_RATE as f64
}

/// (ADSR1, ADSR2, release GAIN) for a note, from the volume envelope of its
/// zone in the SoundFont.
pub fn envelope(sf2: &VolumeEnvelope, key: i64) -> (u8, u8, u8) {
    let attack = seconds(sf2.attack) + seconds(sf2.hold);
    // The decay shortens with the key, around middle C.
    let decay = seconds(sf2.decay + sf2.key_to_decay * (60 - key as i32));
    let sustain_db = sf2.sustain as f64 / 10.0;
    let release = seconds(sf2.release);
    let rate = SAMPLE_RATE as f64;

    // Attack: A from 0 to 14 uses rate 2A+1 and rises in 64 steps.
    let ar = if attack < INSTANT_ATTACK {
        15
    } else {
        closest_rate(
            attack,
            |a| (64 * PERIOD[(2 * a + 1) as usize]) as f64 / rate,
            0..15,
        )
    };

    // The SoundFont drops 100 dB in `decay` seconds, in a straight line in dB.
    let (sl, dr, sr) = if sustain_db >= MUTED_SUSTAIN_DB {
        // It dies out on its own: the sustain level at the very top —the
        // decay phase ends immediately— and the sustain goes down with the
        // SoundFont's decay, reaching zero where it reaches -40 dB.
        (
            7,
            0,
            closest_rate(decay * DOWN_TO_DB / 100.0, time_to_zero, 1..32),
        )
    } else {
        // It goes down to a level and stays: SL in eighths, and the decay
        // (rate 2D+16) with the SoundFont's slope. Above 1/8 the DSP's
        // decrease is exponential, so here the slope is what matters.
        let level = num::pow(10.0, -sustain_db / 20.0);
        let sl = (num::round(8.0 * level) - 1).clamp(0, 7);
        let period = db_per_step() * rate / (100.0 / decay.max(1e-3));
        let dr = closest_rate(period, |d| PERIOD[(2 * d + 16) as usize] as f64, 0..8);
        (sl, dr, 0)
    };

    let gain = if release < LINEAR_RELEASE {
        let r = closest_rate(release, |r| (64 * PERIOD[r as usize]) as f64 / rate, 1..32);
        GAIN_LINEAR_DECREASE | r as u8
    } else {
        let r = closest_rate(release * DOWN_TO_DB / 100.0, time_to_zero, 1..32);
        GAIN_EXP_DECREASE | r as u8
    };
    (
        0x80 | (dr << 4) as u8 | ar as u8,
        ((sl << 5) | sr) as u8,
        gain,
    )
}

// --- notes ------------------------------------------------------------------

/// The reading step to play a note with a recorded sample.
///
/// The sample sounds at its original tuning when the DSP reads it at the
/// same rate it was recorded at, and from there it is transposed by the
/// difference in semitones against its reference note. The register has 14
/// bits, that is, at most four times the base rate; when that is not
/// enough the note is dropped an octave, which is less out of tune than
/// sticking at the cap.
pub fn pitch_for(mut note: f64, root: f64, rate: f64) -> i64 {
    loop {
        let step = rate * 4096.0 / SAMPLE_RATE as f64 * num::pow(2.0, (note - root) / 12.0);
        let value = num::round(step);
        if value <= MAX_PITCH {
            return value.max(1);
        }
        note -= 12.0;
    }
}

// The DSP adds up the eight voices and only then applies the master volume,
// with no limiting in between: if the sum overflows, it clips. **And the
// clipping happens before the master volume**: the sum of the voices
// saturates at 16 bits and only then is multiplied by MASTER, so what
// prevents clipping is each voice's ceiling, and MASTER only decides at what
// level it comes out. So each voice gets **headroom**: its ceiling HEADROOM
// times what it used to be (96 and 84), and MASTER that much higher, as far
// as it goes: the register is signed and does not go past $7F.
//
// **It is the ceiling, not everyone's**: a song that would clip at 0.5 gets
// a lower one, its own, measured and versioned by the game —see
// `game::read_ceilings`—. What does not clip stays at 0.5. Measured against
// one game: an assumption of the engine, not data from any game.
pub const HEADROOM: f64 = 0.5;

/// The master volume: `$60` raised by the headroom, as far as $7F.
pub fn master() -> i64 {
    num::round(0x60 as f64 / HEADROOM).min(0x7F)
}

/// A melodic voice's ceiling.
pub fn ceiling() -> i64 {
    num::round(96.0 * HEADROOM)
}

/// A percussion voice's: it hits hard and is short, so it can take more.
pub fn ceiling_drum() -> i64 {
    num::round(84.0 * HEADROOM)
}

/// The floor: a note the calculation does not leave at zero is heard at
/// least at 2.
const VOLUME_FLOOR: i64 = 2;

/// Left and right of a voice, from 0 to 127 (the register is signed), with
/// the note's velocity and its channel's controllers.
///
/// Each one lowers the level as fluidsynth does with the SoundFont —which
/// is what the result is compared against—: velocity, volume (CC7, against
/// its GM default of 100) and expression (CC11) squared, which is
/// 40·log10 dB each; and pan (CC10) with sine and cosine, the center at the
/// ceiling, so a hard pan exceeds it by 1.41.
pub fn volume(velocity: f64, ceiling: f64, cc7: f64, cc11: f64, pan: f64) -> (i64, i64) {
    let amplitude = ceiling
        * num::pow(velocity / 127.0, 2.0)
        * num::pow(cc7 / 100.0, 2.0)
        * num::pow(cc11 / 127.0, 2.0);
    // fluidsynth maps GM pan to an angle with 128 steps, not 127: 64 is the
    // exact center and 127 does not quite reach the right.
    let angle = pan.clamp(0.0, 127.0) / 128.0 * std::f64::consts::PI / 2.0;
    let center = (std::f64::consts::PI / 4.0).cos();
    let side = |x: f64| -> i64 {
        if x < 0.5 {
            0
        } else {
            num::round(x).clamp(VOLUME_FLOOR, 0x7F)
        }
    };
    (
        side(amplitude * angle.cos() / center),
        side(amplitude * angle.sin() / center),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    fn flat(release: i32) -> VolumeEnvelope {
        VolumeEnvelope {
            delay: -12000,
            attack: -12000,
            hold: -12000,
            decay: 0,
            sustain: 0,
            release,
            key_to_hold: 0,
            key_to_decay: 0,
        }
    }

    /// The DSP's exponential decrease is not exponential below 1/8: if its
    /// slope were matched to the SoundFont's, it would fade out much sooner
    /// than the SoundFont. A one-second release —100 dB in one second— goes
    /// to zero in ~0.4 s.
    #[test]
    fn a_long_release_reaches_zero_where_the_soundfont_is_near_40_db() {
        let (_adsr1, _adsr2, gain) = envelope(&flat(0), 60);
        assert_eq!(gain & 0xE0, GAIN_EXP_DECREASE, "GAIN ${gain:02X}");
        let to_zero = time_to_zero((gain & 0x1F) as i64);
        assert!(
            0.3 < to_zero && to_zero < 0.55,
            "reaches zero in {to_zero:.3} s"
        );
    }

    #[test]
    fn a_short_release_is_linear() {
        // -6000 timecents is 31 ms: the fastest exponential cannot.
        let (_, _, gain) = envelope(&flat(-6000), 60);
        assert_eq!(gain & 0xE0, GAIN_LINEAR_DECREASE, "GAIN ${gain:02X}");
    }

    #[test]
    fn the_constants_are_the_headroom_applied() {
        assert_eq!((master(), ceiling(), ceiling_drum()), (0x7F, 48, 42));
    }

    #[test]
    fn a_hard_pan_exceeds_the_ceiling_by_the_square_root_of_two() {
        let c = ceiling() as f64;
        let (l, r) = volume(127.0, c, 100.0, 127.0, 0.0);
        assert_eq!((l, r), (num::round(c * 2f64.sqrt()), 0));
        let (l, r) = volume(127.0, c, 100.0, 127.0, 64.0);
        assert_eq!((l, r), (48, 48));
    }
}
