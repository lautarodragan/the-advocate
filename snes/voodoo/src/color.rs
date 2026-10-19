//! Colour, at the depth the hardware actually shows.
//!
//! A 15-bit PPU keeps five bits per channel, so two 24-bit colours that differ
//! in the low three bits of a channel are **the same colour** once they are on
//! screen. Colour-memory words are built from the quantised value.

/// A colour as the PPU stores it: five bits per channel, 0..=31.
pub type Rgb15 = (u8, u8, u8);

/// 8-bit channel to 5-bit, by dropping the low three bits.
///
/// Truncation and not rounding: rounding would push 0xFF past the top of the
/// range and would make the conversion non-monotonic at every boundary. Every
/// hardware description of this format writes it as a shift.
pub fn quantize_channel(value: u8) -> u8 {
    value >> 3
}

/// An 8-bit colour to a 15-bit one.
pub fn quantize(red: u8, green: u8, blue: u8) -> Rgb15 {
    (
        quantize_channel(red),
        quantize_channel(green),
        quantize_channel(blue),
    )
}

/// A 15-bit colour back to 8 bits a channel, with the five bits on top.
pub fn expand(color: Rgb15) -> (u8, u8, u8) {
    (color.0 << 3, color.1 << 3, color.2 << 3)
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
    fn expanding_and_quantising_round_trips() {
        for color in [(0, 0, 0), (31, 31, 31), (1, 2, 3), (31, 0, 17)] {
            let (r, g, b) = expand(color);
            assert_eq!(quantize(r, g, b), color);
        }
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
}
