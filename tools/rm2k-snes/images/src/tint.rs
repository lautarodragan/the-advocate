//! RM2k's tone applied to a fifteen-bit colour, the way the console does
//! it.
//!
//! It is easyrpg's `ToneBlit` brought to five bits a channel, and **the
//! ROM does the same arithmetic** when it uploads a tinted palette —the
//! screen tint—; the converter emits its constants (`port/color.py`). Here
//! it tones the cells of a battle animation, which RM2k tones one by one
//! before stacking them: doing it at the console's fifteen bits, and not
//! at the PNG's twenty-four, is what makes a cell come out as the screen
//! tint would paint the same colour.
//!
//! A tone is `[red, green, blue, gray]`, 0 to 200, 100 leaving the colour
//! as it is.

/// The tone that changes nothing.
pub const NEUTRAL: i32 = 100;

/// RM2k's luminance weights, those of Y' in Y'CbCr: easyrpg's
/// `saturation_tone` is `(7471*b + 38470*g + 19595*r) >> 16`. They add up
/// to 65536, so on five-bit channels they give a five-bit luminance.
const LUMA_R: i32 = 19595;
const LUMA_G: i32 = 38470;
const LUMA_B: i32 = 7471;
const LUMA_TOTAL: i32 = 65536;

fn luminance(c: [i32; 3]) -> i32 {
    (LUMA_R * c[0] + LUMA_G * c[1] + LUMA_B * c[2]) / LUMA_TOTAL
}

/// A channel moved toward gray or away from it, `s` in RM2k's units: 0 is
/// gray, 100 nothing, 200 triples the distance to gray. Above 100 it is
/// done with the sign split off and truncating, which is what the 65816
/// can do cheaply; easyrpg's arithmetic shift rounds a negative down, one
/// step of 31 apart, and only when oversaturating.
fn saturate(channel: i32, luma: i32, s: i32) -> i32 {
    if s <= NEUTRAL {
        return (luma * (NEUTRAL - s) + channel * s) / NEUTRAL;
    }
    let m = s - NEUTRAL;
    if channel >= luma {
        (channel + (channel - luma) * m / NEUTRAL).min(31)
    } else {
        (channel - (luma - channel) * m / NEUTRAL).max(0)
    }
}

/// A five-bit channel through RM2k's tint, which is a hard light: below
/// 100 it scales the channel, above it screens it toward white. Within one
/// step of 31 of easyrpg's eight-bit arithmetic for every tint.
fn tint_channel(channel: i32, value: i32) -> i32 {
    if value <= NEUTRAL {
        (channel * value / NEUTRAL).min(31)
    } else {
        (31 - (2 * NEUTRAL - value) * (31 - channel) / NEUTRAL).min(31)
    }
}

/// A fifteen-bit colour —`[r, g, b]`, five bits each— through `tone`.
/// **Saturation first and colour second**, the order of `ToneBlit`; the
/// other order computes the gray over the tinted colour and gives
/// something else. The saturation only when it is not neutral, like
/// easyrpg's `apply_sat`.
pub fn apply(color: [u8; 3], tone: [i32; 4]) -> [u8; 3] {
    let mut channels = color.map(i32::from);
    if tone[3] != NEUTRAL {
        let luma = luminance(channels);
        channels = channels.map(|c| saturate(c, luma, tone[3]));
    }
    [0, 1, 2].map(|k| tint_channel(channels[k], tone[k]) as u8)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_neutral_tone_changes_nothing() {
        for c in [[0, 0, 0], [31, 31, 31], [3, 17, 29]] {
            assert_eq!(apply(c, [100; 4]), c);
        }
    }

    #[test]
    fn full_gray_is_the_luminance() {
        // (19595*31 + 38470*0 + 7471*0) >> 16 = 9.
        assert_eq!(apply([31, 0, 0], [100, 100, 100, 0]), [9, 9, 9]);
    }

    #[test]
    fn brightening_screens_toward_white() {
        assert_eq!(apply([0, 10, 31], [200, 150, 0, 100]), [31, 21, 0]);
    }
}
