//! How much of what is heard of a sound is lost when its rate is lowered:
//! what [`crate::effects::rates_per_package`] weighs to decide which sound
//! effect gives up its rate first.
//!
//! Lowering the rate takes away everything above what the resampler lets
//! through —[`crate::samples::CUTOFF`] of half the new rate—. What that
//! takes is measured on the sound's own spectrum, **weighted by the ear**
//! with the A curve (IEC 61672): a thunder's rumble below 200 Hz carries most
//! of its energy and is heard much less than the crack above 2 kHz, and
//! without the weighting the rumble would say that nothing is lost when the
//! crack goes.

use crate::samples::CUTOFF;

/// Width of the bands the spectrum is kept in, in Hz: fine enough for the
/// rates' steps, which are 500 Hz apart at the least.
const BAND: f64 = 10.0;

/// Below a thousandth of what is heard —30 dB under it— a loss counts as
/// none. What is left there is mostly the transform's own leakage, not the
/// sound; and counting it as zero lets two sound effects that lose nothing
/// tie, so that the heavier goes down first.
const INAUDIBLE: f64 = 0.001;

/// A sound's spectrum, weighted by the ear, accumulated band by band from
/// 0 Hz up to half its rate.
pub struct Audible {
    rate: i64,
    /// `below[b]`: the weighted power below `b * BAND` Hz, as a fraction of
    /// the whole.
    below: Vec<f64>,
}

impl Audible {
    /// `samples` at `rate` Hz, mono.
    pub fn new(samples: &[i64], rate: i64) -> Audible {
        let n = samples.len().max(1).next_power_of_two();
        let mut re: Vec<f64> = samples.iter().map(|&s| s as f64).collect();
        re.resize(n, 0.0);
        let mut im = vec![0.0; n];
        fft(&mut re, &mut im);
        let nyquist = rate as f64 / 2.0;
        let bands = (nyquist / BAND).ceil() as usize + 1;
        let mut power = vec![0.0; bands];
        for k in 1..=n / 2 {
            let f = k as f64 * rate as f64 / n as f64;
            power[((f / BAND) as usize).min(bands - 1)] += (re[k] * re[k] + im[k] * im[k]) * a_weighting(f);
        }
        let total: f64 = power.iter().sum();
        let mut below = Vec::with_capacity(bands + 1);
        let mut sum = 0.0;
        below.push(0.0);
        for p in &power {
            sum += p;
            below.push(if total > 0.0 { sum / total } else { 1.0 });
        }
        Audible { rate, below }
    }

    /// The fraction of what is heard of it that is lost at `rate`: 0 if it
    /// keeps all of it, 1 if nothing is left.
    pub fn lost_at(&self, rate: i64) -> f64 {
        let cutoff = CUTOFF * rate.min(self.rate) as f64 / 2.0;
        let band = ((cutoff / BAND) as usize).min(self.below.len() - 1);
        let lost = 1.0 - self.below[band];
        if lost < INAUDIBLE {
            0.0
        } else {
            lost
        }
    }
}

/// The A curve, as a power ratio (the square of R_A in IEC 61672), without
/// the +2 dB that puts 1 kHz at zero: only proportions are compared.
fn a_weighting(f: f64) -> f64 {
    let f2 = f * f;
    let ra = (12194.0f64.powi(2) * f2 * f2)
        / ((f2 + 20.6f64.powi(2))
            * ((f2 + 107.7f64.powi(2)) * (f2 + 737.9f64.powi(2))).sqrt()
            * (f2 + 12194.0f64.powi(2)));
    ra * ra
}

/// An in-place radix-2 FFT: `re` and `im` are as long as a power of two.
fn fft(re: &mut [f64], im: &mut [f64]) {
    let n = re.len();
    let mut j = 0;
    for i in 1..n {
        let mut bit = n >> 1;
        while j & bit != 0 {
            j ^= bit;
            bit >>= 1;
        }
        j |= bit;
        if i < j {
            re.swap(i, j);
            im.swap(i, j);
        }
    }
    let mut length = 2;
    while length <= n {
        let angle = -2.0 * std::f64::consts::PI / length as f64;
        for start in (0..n).step_by(length) {
            for k in 0..length / 2 {
                let (w_im, w_re) = (angle * k as f64).sin_cos();
                let (a, b) = (start + k, start + k + length / 2);
                let t_re = re[b] * w_re - im[b] * w_im;
                let t_im = re[b] * w_im + im[b] * w_re;
                re[b] = re[a] - t_re;
                im[b] = im[a] - t_im;
                re[a] += t_re;
                im[a] += t_im;
            }
        }
        length <<= 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tone(hz: f64, rate: i64, seconds: f64) -> Vec<i64> {
        let n = (rate as f64 * seconds) as usize;
        (0..n).map(|i| (10000.0 * (2.0 * std::f64::consts::PI * hz * i as f64 / rate as f64).sin()) as i64).collect()
    }

    #[test]
    fn a_tone_is_lost_only_below_the_rate_that_carries_it() {
        let a = Audible::new(&tone(3000.0, 22050, 0.5), 22050);
        assert!(a.lost_at(22050) < 0.01);
        assert!(a.lost_at(8000) < 0.01); // 0.9 × 4000 = 3600 Hz still carries it
        assert!(a.lost_at(6000) > 0.99); // 2700 Hz does not
    }

    #[test]
    fn a_rumble_is_heard_less_than_a_crack() {
        // As much energy at 100 Hz as at 5000: at 6000 Hz the crack goes,
        // and it is almost all of what is heard.
        let low = tone(100.0, 22050, 0.5);
        let high = tone(5000.0, 22050, 0.5);
        let both: Vec<i64> = low.iter().zip(&high).map(|(a, b)| a + b).collect();
        let lost = Audible::new(&both, 22050).lost_at(6000);
        assert!(lost > 0.9, "{lost}");
    }

    #[test]
    fn silence_loses_nothing() {
        assert_eq!(Audible::new(&[0; 64], 22050).lost_at(3000), 0.0);
    }
}
