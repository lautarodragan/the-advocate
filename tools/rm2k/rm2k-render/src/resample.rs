//! Resizing a picture with the bilinear filter: how a battle animation's
//! cell is zoomed.
//!
//! It is the arithmetic of the drawings this replaces, which zoomed with
//! Pillow's `resize(..., BILINEAR)`, and it is copied to the bit because
//! the point is that the pixels are those:
//!
//! * the colour is **premultiplied by the alpha** before resizing and
//!   divided back after, so a transparent pixel does not bleed its colour
//!   into its neighbours;
//! * it is two passes, across and then down, each a weighted sum with the
//!   weights as integers of 22 fractional bits;
//! * shrinking widens the filter by the same factor, so every source pixel
//!   weighs in; growing does not.

use crate::picture::Picture;

/// The fractional bits of a weight: 32 minus the 8 of a sample, minus 2 of
/// headroom for the sum.
const PRECISION_BITS: u32 = 32 - 8 - 2;

/// The bilinear filter: a triangle of half-width 1.
fn bilinear(x: f64) -> f64 {
    let x = x.abs();
    if x < 1.0 {
        1.0 - x
    } else {
        0.0
    }
}

/// For each output pixel along one axis: the first source pixel it reads,
/// and the weights of it and the ones after it.
struct Weights {
    first: Vec<usize>,
    weights: Vec<Vec<i32>>,
}

fn weights(in_size: usize, out_size: usize) -> Weights {
    let scale = in_size as f64 / out_size as f64;
    let filter_scale = scale.max(1.0);
    let support = filter_scale;
    let ss = 1.0 / filter_scale;
    let mut first = Vec::with_capacity(out_size);
    let mut all = Vec::with_capacity(out_size);
    for xx in 0..out_size {
        let center = (xx as f64 + 0.5) * scale;
        // Truncated toward zero, then clamped: a C cast.
        let xmin = ((center - support + 0.5) as i64).max(0);
        let xmax = ((center + support + 0.5) as i64).min(in_size as i64) - xmin;
        let mut k: Vec<f64> = (0..xmax.max(0))
            .map(|x| bilinear(((x + xmin) as f64 - center + 0.5) * ss))
            .collect();
        let total: f64 = k.iter().sum();
        if total != 0.0 {
            for w in &mut k {
                *w /= total;
            }
        }
        let one = (1u32 << PRECISION_BITS) as f64;
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

/// A weighted sum back to a byte: rounded, and clamped to 0..255.
fn clip(sum: i32) -> u8 {
    (sum >> PRECISION_BITS).clamp(0, 255) as u8
}

/// `v * a / 255`, rounded the way the premultiplying this copies does.
fn times_alpha(v: u8, a: u8) -> u8 {
    let tmp = v as u32 * a as u32 + 128;
    (((tmp >> 8) + tmp) >> 8) as u8
}

/// Resizes `src` to `width` x `height`. The same size gives a copy.
pub fn bilinear_resize(src: &Picture, width: usize, height: usize) -> Picture {
    if src.width == width && src.height == height {
        return src.clone();
    }
    // Premultiplied.
    let mut pre = src.clone();
    for px in pre.rgba.chunks_exact_mut(4) {
        let a = px[3];
        for c in &mut px[..3] {
            *c = times_alpha(*c, a);
        }
    }
    let across = weights(src.width, width);
    let down = weights(src.height, height);
    // Only the source rows some output row reads are resized across.
    let top = down.first[0];
    let bottom = down.first[height - 1] + down.weights[height - 1].len();
    let mut middle = pre;
    if width != src.width {
        let rows = bottom - top;
        let mut out = Picture::transparent(width, rows);
        for y in 0..rows {
            let line = &middle.rgba[(y + top) * src.width * 4..(y + top + 1) * src.width * 4];
            for xx in 0..width {
                let mut sums = [1i32 << (PRECISION_BITS - 1); 4];
                let from = across.first[xx];
                for (x, w) in across.weights[xx].iter().enumerate() {
                    let at = (from + x) * 4;
                    for (c, sum) in sums.iter_mut().enumerate() {
                        *sum += line[at + c] as i32 * w;
                    }
                }
                let at = (y * width + xx) * 4;
                for (c, sum) in sums.iter().enumerate() {
                    out.rgba[at + c] = clip(*sum);
                }
            }
        }
        middle = out;
    } else {
        middle = Picture {
            width,
            height: bottom - top,
            rgba: middle.rgba[top * width * 4..bottom * width * 4].to_vec(),
        };
    }
    let mut out = if height != src.height {
        let mut out = Picture::transparent(width, height);
        for yy in 0..height {
            let from = down.first[yy] - top;
            for xx in 0..width {
                let mut sums = [1i32 << (PRECISION_BITS - 1); 4];
                for (y, w) in down.weights[yy].iter().enumerate() {
                    let at = ((from + y) * width + xx) * 4;
                    for (c, sum) in sums.iter_mut().enumerate() {
                        *sum += middle.rgba[at + c] as i32 * w;
                    }
                }
                let at = (yy * width + xx) * 4;
                for (c, sum) in sums.iter().enumerate() {
                    out.rgba[at + c] = clip(*sum);
                }
            }
        }
        out
    } else {
        middle
    };
    // And back from premultiplied.
    for px in out.rgba.chunks_exact_mut(4) {
        let a = px[3] as u32;
        if a != 0 && a != 255 {
            for c in &mut px[..3] {
                *c = (255 * *c as u32 / a).min(255) as u8;
            }
        }
    }
    out
}
