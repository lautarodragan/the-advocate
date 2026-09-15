//! Colour, at the depth the hardware actually shows.
//!
//! A 15-bit PPU keeps five bits per channel, so two 24-bit colours that differ
//! in the low three bits of a channel are **the same colour** once they are on
//! screen. Everything downstream — counting colours, deciding what fits in a
//! palette, merging what does not — has to work on the quantised value, or it
//! counts colours the hardware cannot tell apart.

/// A colour as the PPU stores it: five bits per channel, 0..=31.
pub type Rgb15 = (u8, u8, u8);

/// A pixel: `None` is transparent and goes to index 0, which the PPU does not
/// draw.
pub type Pixel = Option<Rgb15>;

/// 8-bit channel to 5-bit, by dropping the low three bits.
///
/// Truncation and not rounding: rounding would push 0xFF past the top of the
/// range and would make the conversion non-monotonic at every boundary. Every
/// hardware description of this format writes it as a shift.
pub fn quantize_channel(value: u8) -> u8 {
    value >> 3
}

/// One RGBA pixel to a `Pixel`. Alpha is all-or-nothing: the PPU has no
/// per-pixel blending, a pixel is either drawn or it is index 0.
pub fn quantize_pixel(red: u8, green: u8, blue: u8, alpha: u8) -> Pixel {
    if alpha == 0 {
        None
    } else {
        Some((
            quantize_channel(red),
            quantize_channel(green),
            quantize_channel(blue),
        ))
    }
}

/// The 15-bit colour as the word a CGRAM entry holds: `0BBB BBGG GGGR RRRR`.
pub fn cgram_word(color: Rgb15) -> u16 {
    let (red, green, blue) = color;
    ((blue as u16) << 10) | ((green as u16) << 5) | (red as u16)
}

/// The word back to a colour, for reading a palette that already exists.
pub fn from_cgram_word(word: u16) -> Rgb15 {
    (
        (word & 0x1F) as u8,
        ((word >> 5) & 0x1F) as u8,
        ((word >> 10) & 0x1F) as u8,
    )
}

/// How far apart two colours look, weighted the way an eye weighs them.
///
/// The weights are the usual luma coefficients —0.30 / 0.59 / 0.11— times a
/// hundred so the whole thing is **integer**. The ordering it produces is the
/// same as with the fractional coefficients, and in exchange two equal
/// distances compare equal: this gets multiplied by a pixel count and sorted,
/// and a tie broken by the last bit of a float is exactly the kind of
/// difference that makes one run disagree with the next for no reason anyone
/// can see.
pub fn luma_distance(a: Rgb15, b: Rgb15) -> u64 {
    let d = |x: u8, y: u8| {
        let diff = x as i64 - y as i64;
        (diff * diff) as u64
    };
    30 * d(a.0, b.0) + 59 * d(a.1, b.1) + 11 * d(a.2, b.2)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_channel_keeps_its_top_five_bits() {
        assert_eq!(quantize_channel(0), 0);
        assert_eq!(quantize_channel(0xFF), 31);
        assert_eq!(quantize_channel(0b1010_1111), 0b10101);
    }

    #[test]
    fn a_fully_transparent_pixel_has_no_colour_at_all() {
        assert_eq!(quantize_pixel(255, 0, 0, 0), None);
        assert_eq!(quantize_pixel(255, 0, 0, 1), Some((31, 0, 0)));
    }

    #[test]
    fn a_cgram_word_round_trips() {
        for color in [(0, 0, 0), (31, 31, 31), (1, 2, 3), (31, 0, 17)] {
            assert_eq!(from_cgram_word(cgram_word(color)), color);
        }
        assert_eq!(cgram_word((31, 0, 0)), 0x001F);
        assert_eq!(cgram_word((0, 31, 0)), 0x03E0);
        assert_eq!(cgram_word((0, 0, 31)), 0x7C00);
    }

    #[test]
    fn distance_is_symmetric_zero_only_on_itself_and_integer() {
        assert_eq!(luma_distance((5, 6, 7), (5, 6, 7)), 0);
        assert_eq!(luma_distance((5, 6, 7), (7, 6, 5)), 30 * 4 + 11 * 4);
        assert_eq!(
            luma_distance((1, 2, 3), (9, 8, 7)),
            luma_distance((9, 8, 7), (1, 2, 3))
        );
    }
}
