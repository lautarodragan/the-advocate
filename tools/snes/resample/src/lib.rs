//! Pillow's LANCZOS resize, to the bit.
//!
//! `Image.resize(size, Image.LANCZOS)` is a convolution done in two passes,
//! across and then down, and every step of it rounds somewhere: the weights
//! are computed in `double`, normalised, turned into integers of 22
//! fractional bits, summed in 32-bit integers and clipped back to a byte
//! after **each** pass. A resampler that is merely correct gives pixels one
//! step away from those, and one step is enough to change which colours a
//! picture keeps after it. So this is `libImaging/Resample.c` and the
//! handful of lines of `Image.resize` around it, copied down to the order of
//! the operations, and its tests compare against what Pillow wrote.
//!
//! Only what LANCZOS on 8-bit pictures needs is here:
//!
//! * **RGB**: three channels, each convolved on its own;
//! * **RGBA**: Pillow premultiplies the colour by the alpha first —`RGBa`—,
//!   convolves the four channels and divides back, so a transparent pixel
//!   does not bleed its colour into its neighbours. Both conversions round
//!   the way Pillow's `Convert.c` does.
//!
//! What Pillow does with `reducing_gap` and `box` is left out: a plain
//! `resize(size, LANCZOS)` uses neither.

/// The fractional bits of a weight: 32 minus the 8 of a sample, minus 2 of
/// headroom for the sum, whose weights can add past one and dip below
/// zero. It is Pillow's `PRECISION_BITS`.
const PRECISION_BITS: u32 = 32 - 8 - 2;

/// Pillow's Lanczos: a sinc windowed by a wider sinc, three lobes a side.
const SUPPORT: f64 = 3.0;

fn sinc(x: f64) -> f64 {
    if x == 0.0 {
        return 1.0;
    }
    let x = x * std::f64::consts::PI;
    x.sin() / x
}

fn lanczos(x: f64) -> f64 {
    if (-SUPPORT..SUPPORT).contains(&x) {
        sinc(x) * sinc(x / 3.0)
    } else {
        0.0
    }
}

/// For each output pixel along one axis: the first source pixel it reads,
/// and the integer weights of it and the ones after it. It is
/// `precompute_coeffs` followed by `normalize_coeffs_8bpc`.
struct Weights {
    first: Vec<usize>,
    weights: Vec<Vec<i32>>,
}

fn weights(in_size: usize, out_size: usize) -> Weights {
    // `(double)(in1 - in0) / outSize`, with `in0` and `in1` floats: exact
    // for any size a picture has.
    let scale = in_size as f64 / out_size as f64;
    // Shrinking widens the filter by the same factor, so every source pixel
    // weighs in; growing does not.
    let filter_scale = scale.max(1.0);
    let support = SUPPORT * filter_scale;
    let inv_filter_scale = 1.0 / filter_scale;
    let one = (1u32 << PRECISION_BITS) as f64;
    let mut first = Vec::with_capacity(out_size);
    let mut all = Vec::with_capacity(out_size);
    for xx in 0..out_size {
        let center = (xx as f64 + 0.5) * scale;
        // `(int)` in C truncates toward zero, and `as` does too; the clamp
        // comes after, as there.
        let xmin = ((center - support + 0.5) as i64).max(0);
        let xmax = ((center + support + 0.5) as i64).min(in_size as i64) - xmin;
        let mut k: Vec<f64> = (0..xmax.max(0))
            .map(|x| lanczos(((x + xmin) as f64 - center + 0.5) * inv_filter_scale))
            .collect();
        // Summed in order, as the C loop does: a different order can change
        // the last bit of the total, and with it a weight.
        let mut total = 0.0;
        for w in &k {
            total += w;
        }
        if total != 0.0 {
            for w in &mut k {
                *w /= total;
            }
        }
        all.push(
            k.iter()
                .map(|w| {
                    if *w < 0.0 {
                        (-0.5 + w * one) as i32
                    } else {
                        (0.5 + w * one) as i32
                    }
                })
                .collect(),
        );
        first.push(xmin as usize);
    }
    Weights {
        first,
        weights: all,
    }
}

/// A weighted sum back to a byte: Pillow's `clip8`, the sum shifted down
/// —arithmetically, so a negative one stays negative— and clamped.
fn clip(sum: i32) -> u8 {
    (sum >> PRECISION_BITS).clamp(0, 255) as u8
}

/// A picture of `channels` bytes a pixel, rows top to bottom.
struct Plane<'a> {
    data: &'a [u8],
    width: usize,
    channels: usize,
}

/// The pass across: rows `top..top + rows` of `src`, each resized to
/// `width`.
fn across(src: &Plane, top: usize, rows: usize, width: usize, w: &Weights) -> Vec<u8> {
    let c = src.channels;
    let mut out = vec![0u8; rows * width * c];
    for y in 0..rows {
        let line = &src.data[(y + top) * src.width * c..(y + top + 1) * src.width * c];
        for xx in 0..width {
            let from = w.first[xx];
            for ch in 0..c {
                let mut sum = 1i32 << (PRECISION_BITS - 1);
                for (x, k) in w.weights[xx].iter().enumerate() {
                    sum += line[(from + x) * c + ch] as i32 * k;
                }
                out[(y * width + xx) * c + ch] = clip(sum);
            }
        }
    }
    out
}

/// The pass down: `src` resized to `height` rows, with `w.first` counted
/// from row `top` of the picture `src` was cut from.
fn down(src: &Plane, top: usize, height: usize, w: &Weights) -> Vec<u8> {
    let c = src.channels;
    let width = src.width;
    let mut out = vec![0u8; height * width * c];
    for yy in 0..height {
        let from = w.first[yy] - top;
        for xx in 0..width {
            for ch in 0..c {
                let mut sum = 1i32 << (PRECISION_BITS - 1);
                for (y, k) in w.weights[yy].iter().enumerate() {
                    sum += src.data[((from + y) * width + xx) * c + ch] as i32 * k;
                }
                out[(yy * width + xx) * c + ch] = clip(sum);
            }
        }
    }
    out
}

/// `ImagingResampleInner`: across only if the width changes, down only if
/// the height does, and the pass across only over the rows the pass down
/// will read.
fn convolve(
    data: &[u8],
    channels: usize,
    width: usize,
    height: usize,
    out_width: usize,
    out_height: usize,
) -> Vec<u8> {
    let vertical = weights(height, out_height);
    let top = vertical.first[0];
    let bottom = vertical.first[out_height - 1] + vertical.weights[out_height - 1].len();
    let src = Plane {
        data,
        width,
        channels,
    };
    let (middle, middle_top);
    let middle_plane = if out_width != width {
        let horizontal = weights(width, out_width);
        middle = across(&src, top, bottom - top, out_width, &horizontal);
        middle_top = top;
        Plane {
            data: &middle,
            width: out_width,
            channels,
        }
    } else {
        middle_top = 0;
        src
    };
    if out_height != height {
        down(&middle_plane, middle_top, out_height, &vertical)
    } else {
        middle_plane.data.to_vec()
    }
}

/// `Image.resize` on a picture of `channels` bytes a pixel, already in the
/// form that is convolved. A picture a hundred times taller than wide that
/// shrinks in height is done in two calls, down and then across —Pillow's
/// guard for them—; any other, in one.
fn resize(
    data: &[u8],
    channels: usize,
    width: usize,
    height: usize,
    out_width: usize,
    out_height: usize,
) -> Vec<u8> {
    if height > width * 100 && out_height < height {
        let tall = convolve(data, channels, width, height, width, out_height);
        return convolve(&tall, channels, width, out_height, out_width, out_height);
    }
    convolve(data, channels, width, height, out_width, out_height)
}

fn check(data: &[u8], channels: usize, width: usize, height: usize, out: (usize, usize)) {
    assert_eq!(
        data.len(),
        width * height * channels,
        "a {width}x{height} picture of {channels} bytes a pixel"
    );
    assert!(
        width > 0 && height > 0 && out.0 > 0 && out.1 > 0,
        "resizing to or from an empty picture"
    );
}

/// An RGB picture —three bytes a pixel, rows top to bottom— resized to
/// `out_width` x `out_height` as `resize(..., Image.LANCZOS)` does. The same
/// size gives a copy, as there.
pub fn lanczos_rgb(
    data: &[u8],
    width: usize,
    height: usize,
    out_width: usize,
    out_height: usize,
) -> Vec<u8> {
    check(data, 3, width, height, (out_width, out_height));
    if (width, height) == (out_width, out_height) {
        return data.to_vec();
    }
    resize(data, 3, width, height, out_width, out_height)
}

/// `v * a / 255`, rounded as Pillow's `MULDIV255`.
fn times_alpha(v: u8, a: u8) -> u8 {
    let tmp = v as u32 * a as u32 + 128;
    (((tmp >> 8) + tmp) >> 8) as u8
}

/// An RGBA picture —four bytes a pixel— resized as `resize(...,
/// Image.LANCZOS)` does: premultiplied, convolved on the four channels, and
/// divided back. The same size gives a copy, without the round trip, as
/// there.
pub fn lanczos_rgba(
    data: &[u8],
    width: usize,
    height: usize,
    out_width: usize,
    out_height: usize,
) -> Vec<u8> {
    check(data, 4, width, height, (out_width, out_height));
    if (width, height) == (out_width, out_height) {
        return data.to_vec();
    }
    // `convert("RGBa")`: `rgbA2rgba`.
    let mut pre = data.to_vec();
    for px in pre.chunks_exact_mut(4) {
        let a = px[3];
        for c in &mut px[..3] {
            *c = times_alpha(*c, a);
        }
    }
    let mut out = resize(&pre, 4, width, height, out_width, out_height);
    // `convert("RGBA")`: `rgba2rgbA`, which leaves alone what is fully
    // opaque or fully transparent.
    for px in out.chunks_exact_mut(4) {
        let a = px[3] as u32;
        if a != 0 && a != 255 {
            for c in &mut px[..3] {
                *c = (255 * *c as u32 / a).min(255) as u8;
            }
        }
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_same_size_is_a_copy() {
        let rgba = [1, 2, 3, 100, 4, 5, 6, 0];
        assert_eq!(lanczos_rgba(&rgba, 2, 1, 2, 1), rgba);
        assert_eq!(lanczos_rgb(&rgba[..6], 2, 1, 2, 1), &rgba[..6]);
    }

    #[test]
    fn a_flat_picture_stays_flat() {
        let rgb: Vec<u8> = [9u8, 120, 250].repeat(37 * 23);
        assert_eq!(lanczos_rgb(&rgb, 37, 23, 11, 7), [9u8, 120, 250].repeat(11 * 7));
        assert_eq!(lanczos_rgb(&rgb, 37, 23, 80, 50), [9u8, 120, 250].repeat(80 * 50));
    }

    #[test]
    fn the_weights_of_a_row_add_up_to_one() {
        for (from, to) in [(320, 256), (256, 320), (536, 64), (7, 3), (3, 7)] {
            let w = weights(from, to);
            for k in &w.weights {
                let sum: i64 = k.iter().map(|&v| v as i64).sum();
                assert!((sum - (1 << PRECISION_BITS)).abs() <= k.len() as i64);
            }
        }
    }
}
