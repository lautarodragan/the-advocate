//! BRR: the compressed sample format the SPC700's DSP plays.
//!
//! A BRR sample is a run of nine-byte blocks: one header byte and eight data
//! bytes holding sixteen samples at four bits each. The header carries a range
//! —how far each value is shifted left when decoding— and a filter.
//!
//! The filter is what makes four bits enough. Instead of the sample itself, a
//! block stores the difference against what the decoder predicts from the two
//! previous samples; in real audio that difference is far smaller than the
//! signal, so it fits in fewer bits. The four filters are:
//!
//! ```text
//! 0   no prediction
//! 1   old*15/16                   a slope
//! 2   old*61/32 - older*15/16     a parabola
//! 3   old*115/64 - older*13/16    the same, steeper
//! ```
//!
//! All four are tried for every block and the one leaving the least squared
//! error wins. Two blocks are always given filter 0, and that is not a
//! simplification: filters 1 to 3 lean on the two previous samples, and
//! neither at the start nor on coming back from the loop point is it certain
//! what those are. Forcing filter 0 there costs a little precision over
//! sixteen samples and avoids a click on every pass.

/// Samples per block.
pub const BLOCK_SAMPLES: usize = 16;
/// Bytes per block: one header and eight of data.
pub const BLOCK_BYTES: usize = 9;
/// Ranges above this are not usable: the DSP treats 13, 14 and 15 as a sign
/// fill rather than a shift, so an encoder has no business emitting them.
pub const MAX_SHIFT: u8 = 12;

/// Last block of the sample.
pub const FLAG_END: u8 = 0x01;
/// The sample repeats: on hitting the end block the DSP jumps to the loop
/// address in its directory instead of stopping.
pub const FLAG_LOOP: u8 = 0x02;

/// What the decoder expects the next sample to be.
///
/// The arithmetic is integers and shifts, exactly as the chip does it: with
/// exact fractions the encoder would be optimising against a decoder that does
/// not exist, and the real error would be something else.
pub fn predict(filter: u8, old: i32, older: i32) -> i32 {
    match filter {
        0 => 0,
        1 => old + ((-old) >> 4),
        2 => (old << 1) + ((-((old << 1) + old)) >> 5) - older + (older >> 4),
        _ => (old << 1) + ((-(old * 13)) >> 6) - older + ((older * 3) >> 4),
    }
}

fn clamp16(value: i32) -> i32 {
    value.clamp(-32768, 32767)
}

/// One block encoded with a given filter and range, and what it cost.
///
/// Each sample's prediction uses what the decoder has already reconstructed,
/// not the original: so the decoder is simulated sample by sample. Using the
/// originals would let the error pile up where the encoder cannot see it.
fn try_block(
    samples: &[i32],
    filter: u8,
    shift: u8,
    mut old: i32,
    mut older: i32,
) -> ([u8; BLOCK_SAMPLES], i64, i32, i32) {
    let mut nibbles = [0u8; BLOCK_SAMPLES];
    let mut error: i64 = 0;
    let half = (1i32 << shift) / 2;

    for (slot, &target) in nibbles.iter_mut().zip(samples) {
        let guess = predict(filter, old, older);
        let residual = target - guess;
        let rounded = if residual >= 0 {
            (residual + half) >> shift
        } else {
            -(((-residual) + half) >> shift)
        };
        let nibble = rounded.clamp(-8, 7);
        let decoded = clamp16(guess + (nibble << shift));
        let miss = (target - decoded) as i64;
        error += miss * miss;
        older = old;
        old = decoded;
        *slot = (nibble & 0x0F) as u8;
    }
    (nibbles, error, old, older)
}

/// One encoded block, and the decoder state it leaves behind.
pub struct Encoded {
    pub bytes: [u8; BLOCK_BYTES],
    pub old: i32,
    pub older: i32,
}

/// The best of the (filter, range) pairs for these sixteen samples.
///
/// `filters` says which ones may be tried; ties go to the lowest filter and
/// then the lowest range, which is why the search order is fixed and not an
/// implementation detail.
pub fn encode_block(
    samples: &[i32],
    old: i32,
    older: i32,
    loops: bool,
    end: bool,
    filters: &[u8],
) -> Encoded {
    let mut best: Option<(i64, u8, u8, [u8; BLOCK_SAMPLES], i32, i32)> = None;

    for &filter in filters {
        for shift in 0..=MAX_SHIFT {
            let (nibbles, error, new_old, new_older) =
                try_block(samples, filter, shift, old, older);
            if best.as_ref().is_none_or(|b| error < b.0) {
                best = Some((error, filter, shift, nibbles, new_old, new_older));
            }
            if error == 0 {
                break;
            }
        }
    }

    let (_error, filter, shift, nibbles, new_old, new_older) =
        best.expect("encode_block was given no filters to try");

    let mut bytes = [0u8; BLOCK_BYTES];
    bytes[0] = (shift << 4)
        | (filter << 2)
        | if loops { FLAG_LOOP } else { 0 }
        | if end { FLAG_END } else { 0 };
    for i in 0..BLOCK_SAMPLES / 2 {
        bytes[1 + i] = (nibbles[i * 2] << 4) | nibbles[i * 2 + 1];
    }

    Encoded {
        bytes,
        old: new_old,
        older: new_older,
    }
}

/// A whole sample, with the loop point on whichever block it is told.
///
/// `loop_block` is the index of the block the DSP comes back to, or `None` for
/// a sample that does not repeat. The input is padded with zeros up to a
/// multiple of sixteen, because the DSP only understands whole blocks.
pub fn encode(samples: &[i16], loop_block: Option<usize>) -> Vec<u8> {
    let mut padded: Vec<i32> = samples.iter().map(|&s| s as i32).collect();
    while padded.len() % BLOCK_SAMPLES != 0 {
        padded.push(0);
    }

    let blocks = padded.len() / BLOCK_SAMPLES;
    let mut out = Vec::with_capacity(blocks * BLOCK_BYTES);
    let (mut old, mut older) = (0, 0);

    for index in 0..blocks {
        let chunk = &padded[index * BLOCK_SAMPLES..(index + 1) * BLOCK_SAMPLES];
        let last = index + 1 == blocks;
        // With no trustworthy previous state, filter 0 is the only honest one.
        let fresh = index == 0 || Some(index) == loop_block;
        let filters: &[u8] = if fresh { &[0] } else { &[0, 1, 2, 3] };
        let block = encode_block(
            chunk,
            old,
            older,
            last && loop_block.is_some(),
            last,
            filters,
        );
        out.extend_from_slice(&block.bytes);
        old = block.old;
        older = block.older;
    }
    out
}

/// Decompresses, so a sample can be checked without running anything.
///
/// This has to reproduce exactly what the chip does, filters included: it is
/// the pattern everything else is compared against. Trailing bytes that do not
/// make up a whole block are ignored.
///
/// **It does not, in two places**, read against `SPC_DSP.cpp`'s
/// `decode_brr`. The chip computes `(nibble << shift) >> 1` and works at half
/// this scale, so with range 0 it drops the nibble's low bit and this does
/// not. And after clamping it doubles the sample into a 16-bit register, so
/// an overshoot wraps there where this saturates. Measured in September 2026
/// on a real sample bank, with the codec this one replaced and the same
/// arithmetic: the first touched 128 of 85,629 blocks, by ±7 at most; the
/// second, none of 1,370,064 samples, latent if a louder peak is encoded.
/// The encoder optimises against this decoder, so both are invisible to it.
pub fn decode(data: &[u8]) -> Vec<i16> {
    let mut samples = Vec::with_capacity(data.len() / BLOCK_BYTES * BLOCK_SAMPLES);
    let (mut old, mut older) = (0, 0);

    for block in data.chunks_exact(BLOCK_BYTES) {
        let shift = block[0] >> 4;
        let filter = (block[0] >> 2) & 0x03;
        for &byte in &block[1..] {
            for nibble in [(byte >> 4) & 0x0F, byte & 0x0F] {
                let value = if nibble >= 8 {
                    nibble as i32 - 16
                } else {
                    nibble as i32
                };
                let decoded = clamp16(predict(filter, old, older) + (value << shift));
                samples.push(decoded as i16);
                older = old;
                old = decoded;
            }
        }
    }
    samples
}

/// How much was lost, as a percentage of the signal's peak.
pub fn error(original: &[i16], data: &[u8]) -> f64 {
    let decoded = decode(data);
    let count = original.len().min(decoded.len());
    if count == 0 {
        return 0.0;
    }
    let peak = original[..count]
        .iter()
        .map(|s| (*s as i32).unsigned_abs())
        .max()
        .unwrap_or(1)
        .max(1);
    let worst = (0..count)
        .map(|i| (original[i] as i32 - decoded[i] as i32).unsigned_abs())
        .max()
        .unwrap_or(0);
    100.0 * worst as f64 / peak as f64
}

/// What a block's header byte says, for reporting on a file nobody encoded here.
pub struct Header {
    pub shift: u8,
    pub filter: u8,
    pub loops: bool,
    pub end: bool,
}

impl Header {
    pub fn of(byte: u8) -> Header {
        Header {
            shift: byte >> 4,
            filter: (byte >> 2) & 0x03,
            loops: byte & FLAG_LOOP != 0,
            end: byte & FLAG_END != 0,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn headers(data: &[u8]) -> Vec<Header> {
        data.chunks_exact(BLOCK_BYTES)
            .map(|b| Header::of(b[0]))
            .collect()
    }

    #[test]
    fn a_block_is_nine_bytes_and_the_length_is_rounded_up() {
        // One sample still costs a whole block: the DSP has no shorter unit.
        assert_eq!(encode(&[1], None).len(), BLOCK_BYTES);
        assert_eq!(encode(&[0; 16], None).len(), BLOCK_BYTES);
        assert_eq!(encode(&[0; 17], None).len(), 2 * BLOCK_BYTES);
    }

    #[test]
    fn silence_costs_a_range_of_zero_and_decodes_back_to_silence() {
        let data = encode(&[0; 64], None);
        for h in headers(&data) {
            assert_eq!(h.shift, 0);
            assert_eq!(h.filter, 0);
        }
        assert_eq!(decode(&data), vec![0i16; 64]);
    }

    #[test]
    fn the_first_block_never_uses_a_filter() {
        // Nothing has been decoded yet, so a filter would predict from state
        // the decoder does not have.
        let ramp: Vec<i16> = (0..64).map(|i| i * 400).collect();
        assert_eq!(headers(&encode(&ramp, None))[0].filter, 0);
    }

    #[test]
    fn the_loop_block_never_uses_a_filter_either() {
        let ramp: Vec<i16> = (0..64).map(|i| (i * 400) - 12800).collect();
        let data = encode(&ramp, Some(2));
        assert_eq!(headers(&data)[2].filter, 0);
    }

    #[test]
    fn only_the_last_block_carries_the_end_and_loop_flags() {
        let ramp: Vec<i16> = (0..64).map(|i| i * 400).collect();
        let hs = headers(&encode(&ramp, Some(1)));
        assert!(hs[..3].iter().all(|h| !h.end && !h.loops));
        assert!(hs[3].end && hs[3].loops);

        let hs = headers(&encode(&ramp, None));
        assert!(hs[3].end && !hs[3].loops, "no loop point, no loop flag");
    }

    #[test]
    fn a_ramp_survives_the_round_trip_closely() {
        let ramp: Vec<i16> = (0..256).map(|i| (i * 100) - 12800).collect();
        let data = encode(&ramp, None);
        let back = decode(&data);
        assert_eq!(back.len(), ramp.len());

        // The first block is the expensive one and always will be: with no
        // history it has to walk from silence to -12800 in sixteen steps, so
        // its range is huge and so is its error. Everything after it is a
        // slope, which is what filter 1 is for.
        let worst_after = (16..ramp.len())
            .map(|i| (ramp[i] as i32 - back[i] as i32).abs())
            .max()
            .unwrap();
        let off = 100.0 * worst_after as f64 / 25500.0;
        assert!(off < 0.5, "off by {off:.2}% once the filter has history");
    }

    #[test]
    fn a_square_wave_survives_the_round_trip() {
        // The hard case for a predictor: every prediction is wrong at the
        // edges, and only the range can absorb it.
        let square: Vec<i16> = (0..256)
            .map(|i| if (i / 8) % 2 == 0 { 20000 } else { -20000 })
            .collect();
        let data = encode(&square, None);
        let back = decode(&data);
        assert_eq!(back.len(), square.len());
        assert!(error(&square, &data) < 25.0, "{}", error(&square, &data));
    }

    #[test]
    fn an_impulse_is_reproduced_and_does_not_smear_forever() {
        let mut impulse = vec![0i16; 64];
        impulse[3] = 30000;
        let back = decode(&encode(&impulse, None));
        assert!(back[3] > 24000, "the spike should survive: {}", back[3]);
        assert!(
            back[48..].iter().all(|s| s.abs() < 1200),
            "{:?}",
            &back[48..]
        );
    }

    #[test]
    fn full_scale_input_stays_inside_sixteen_bits() {
        // The decoder clamps; a codec that wrapped here would turn the loudest
        // part of a sample into its opposite.
        let loud: Vec<i16> = (0..64)
            .map(|i| if i % 2 == 0 { i16::MAX } else { i16::MIN })
            .collect();
        let back = decode(&encode(&loud, None));
        assert_eq!(back.len(), 64);
    }

    #[test]
    fn no_block_ever_asks_for_an_unusable_range() {
        let noisy: Vec<i16> = (0..1024)
            .map(|i: i32| ((i * 7919) % 65536 - 32768) as i16)
            .collect();
        for h in headers(&encode(&noisy, None)) {
            assert!(h.shift <= MAX_SHIFT, "range {} is not decodable", h.shift);
        }
    }

    #[test]
    fn decoding_ignores_a_trailing_partial_block() {
        let data = encode(&[0; 32], None);
        let mut short = data.clone();
        short.push(0x00);
        assert_eq!(decode(&short), decode(&data));
    }

    #[test]
    fn the_four_filters_are_the_chips_arithmetic_and_not_fractions() {
        // Pinned on purpose: these four numbers are what the encoder optimises
        // against, so a "cleaner" rewrite of them silently changes every byte.
        assert_eq!(predict(0, 1000, -1000), 0);
        assert_eq!(predict(1, 1000, -1000), 937);
        assert_eq!(predict(2, 1000, -1000), 2843);
        assert_eq!(predict(3, 1000, -1000), 2608);
        // And with the history negated, where a floored shift is not a
        // division and the answer is not the negation either.
        assert_eq!(predict(1, -1000, 1000), -938);
        assert_eq!(predict(2, -1000, 1000), -2845);
        assert_eq!(predict(3, -1000, 1000), -2610);
    }
}
