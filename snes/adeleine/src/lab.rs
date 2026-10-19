//! How far apart two colours of the console look: in CIE Lab.
//!
//! [`luma_distance`](crate::luma_distance) weighs the three channels as the
//! eye weighs their brightness, and that is what a merge wants: two colours
//! that are almost the same light. But it barely sees blue —eleven of a
//! hundred—, so to it an olive is nearer a grey of its light than a grey a
//! little darker, and a colour drawn with one it is not lands on a hue it
//! never had. CIE Lab measures lightness and the two axes of hue —green to
//! red, blue to yellow— in a space where equal steps look about equal.
//!
//! **It was measured against Oklab**, which is newer and meant to be more
//! even, as the nearest colour of a character drawn with someone else's
//! palette, over every game's maps that lend one, judged in CIEDE2000 —a
//! third measure, so that neither judges itself—: with Lab more maps came
//! out better and fewer characters worse. See "The palette a character is
//! lent" in the book.
//!
//! **This one is for 15-bit colours**, five bits a channel, which is what
//! the console draws: unlike the luma distance, Lab is not the same
//! function of the channels at every depth. A channel is brought to eight
//! bits the way the console's colour is usually read, `v << 3 | v >> 2`,
//! and white is D65's.
//!
//! The answer is an integer, like the luma distance's: the coordinates are
//! rounded to tenths before subtracting, so two equal distances compare
//! equal and a tie is broken by whoever calls, never by the last bit of a
//! float.

use crate::Color;

/// A channel of five bits, linear light from 0 to 1.
fn linear(v: u8) -> f64 {
    debug_assert!(v < 32, "a 15-bit colour has five bits a channel: {v}");
    let v = f64::from((v << 3) | (v >> 2)) / 255.0;
    if v <= 0.04045 {
        v / 12.92
    } else {
        ((v + 0.055) / 1.055).powf(2.4)
    }
}

/// The colour in CIE Lab, in tenths: lightness from 0 to 1000, and the two
/// hue axes around 0.
pub fn lab(color: Color) -> [i64; 3] {
    let (r, g, b) = (linear(color[0]), linear(color[1]), linear(color[2]));
    let x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047;
    let y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
    let z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
    let f = |t: f64| {
        if t > 0.008856 {
            t.cbrt()
        } else {
            7.787 * t + 16.0 / 116.0
        }
    };
    let (fx, fy, fz) = (f(x), f(y), f(z));
    [116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz)].map(|v| (v * 10.0).round() as i64)
}

/// How far apart two 15-bit colours look, squared, in tenths of Lab: CIE76.
pub fn lab_distance(a: Color, b: Color) -> i64 {
    let (p, q) = (lab(a), lab(b));
    (0..3).map(|k| (p[k] - q[k]) * (p[k] - q[k])).sum()
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::luma_distance;

    #[test]
    fn white_is_a_thousand_and_black_is_zero() {
        assert_eq!(lab([31, 31, 31]), [1000, 0, 0]);
        assert_eq!(lab([0, 0, 0]), [0, 0, 0]);
    }

    #[test]
    fn a_grey_is_nearer_a_grey_than_an_olive_of_its_light() {
        // A grey, an olive of nearly its light and a grey three steps
        // darker: to the luma distance the olive is nearer.
        let grey = [16, 16, 16];
        let (olive, other) = ([17, 17, 8], [13, 13, 13]);
        assert!(
            luma_distance(grey, olive) < luma_distance(grey, other),
            "the luma distance's mistake"
        );
        assert!(lab_distance(grey, other) < lab_distance(grey, olive));
    }

    #[test]
    fn it_is_symmetric_and_zero_only_for_the_same_colour() {
        let (a, b) = ([3, 20, 7], [9, 2, 30]);
        assert_eq!(lab_distance(a, b), lab_distance(b, a));
        assert_eq!(lab_distance(a, a), 0);
        assert!(lab_distance(a, b) > 0);
    }
}
