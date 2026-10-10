//! A battle animation's frames in the box the console draws them in.
//!
//! RM2k's part —which cells each frame has, cut from the sheet, zoomed,
//! faded, and where they go in the animation's box— is
//! `rm2k_render::battle_animation`'s. What is the console's is here:
//!
//! * **each cell is toned with the console's arithmetic**, at fifteen bits
//!   —[`tint`](crate::tint)—, and only then stacked over the ones before
//!   it, which is RM2k's order;
//! * **the whole animation is shrunk until it fits in the box**, keeping
//!   its proportions, and centred in it; an animation that already fits is
//!   not enlarged;
//! * **a pixel is drawn or not**: an object on the console has no
//!   translucency, so from half the alpha up it is drawn;
//! * **the colours are chosen over all the frames at once**, because the
//!   palette is uploaded once when the animation starts: the most used,
//!   black first.

use crate::composite::over_at;
use crate::pixels::{most_used, scaled_rgba, to_15_bits};
use crate::tint;
use adeleine::Color;
use ditto::schema::Animation;
use rm2k_render::battle_animation::{frames, Piece};
use rm2k_render::Picture;
use std::collections::HashMap;

/// The box, its colours and the alpha from which a pixel is drawn, which
/// the caller also emits for the console.
#[derive(Clone, Copy, Debug)]
pub struct Geometry {
    pub side: usize,
    pub colors: usize,
    pub alpha_min: u8,
}

pub struct Converted {
    /// For each of RM2k's frames, the box as indices into `palette` plus
    /// one: 0 is not drawn.
    pub frames: Vec<Vec<Vec<usize>>>,
    pub palette: Vec<Color>,
    /// Where inside the box the point RM2k puts over the target lands.
    pub anchor: (i64, i64),
    /// What it was shrunk to, and what from.
    pub size: (usize, usize),
    pub rm_box: (usize, usize),
}

/// The size an animation of `width` x `height` is shrunk to so it fits in
/// a box of `side`, keeping its proportions: the side that overflows the
/// most decides, and never less than the box, so nothing is enlarged.
pub fn fit_size(width: usize, height: usize, side: usize) -> (usize, usize) {
    let den = width.max(height).max(side);
    ((width * side / den).max(1), (height * side / den).max(1))
}

/// A cell toned: each pixel's colour at fifteen bits through the tone, and
/// back to eight with its low bits at zero; the alpha as it was.
fn toned(piece: &Picture, tone: [i32; 4]) -> Picture {
    let mut out = piece.clone();
    let mut memo: HashMap<[u8; 3], [u8; 3]> = HashMap::new();
    for px in out.rgba.chunks_exact_mut(4) {
        let key = to_15_bits(px[0], px[1], px[2]);
        let c = *memo.entry(key).or_insert_with(|| tint::apply(key, tone));
        px[0] = c[0] << 3;
        px[1] = c[1] << 3;
        px[2] = c[2] << 3;
    }
    out
}

/// A frame in RM2k's pixels, the size of the animation's box: its cells
/// toned and stacked in order.
fn paint(pieces: &[Piece], width: usize, height: usize) -> Picture {
    let mut canvas = Picture::transparent(width, height);
    for piece in pieces {
        if piece.tone == [tint::NEUTRAL; 4] {
            over_at(&mut canvas, &piece.picture, piece.x, piece.y);
        } else {
            over_at(
                &mut canvas,
                &toned(&piece.picture, piece.tone),
                piece.x,
                piece.y,
            );
        }
    }
    canvas
}

/// `animation`, whose cells are cut from `sheet`, in the box; or None if
/// no frame has a cell, or no pixel of any is drawn.
pub fn convert(animation: &Animation, sheet: &Picture, g: &Geometry) -> Option<Converted> {
    let (bounds, cells) = frames(animation, sheet);
    let (x0, y0, width, height) = bounds?;
    let (width, height) = (width as usize, height as usize);
    let (bw, bh) = fit_size(width, height, g.side);
    let (ox, oy) = ((g.side - bw) / 2, (g.side - bh) / 2);
    let boxes: Vec<Picture> = cells
        .iter()
        .map(|pieces| {
            let small = scaled_rgba(&paint(pieces, width, height), bw, bh);
            let mut whole = Picture::transparent(g.side, g.side);
            whole.put(ox, oy, &small);
            whole
        })
        .collect();
    let drawn: Vec<Color> = boxes
        .iter()
        .flat_map(|b| b.rgba.chunks_exact(4))
        .filter(|p| p[3] >= g.alpha_min)
        .map(|p| to_15_bits(p[0], p[1], p[2]))
        .collect();
    if drawn.is_empty() {
        return None;
    }
    let (palette, mapping) = most_used(&drawn, g.colors);
    let slot: HashMap<Color, usize> = palette
        .iter()
        .enumerate()
        .map(|(i, &c)| (c, i + 1))
        .collect();
    let frames = boxes
        .iter()
        .map(|b| {
            b.rgba
                .chunks_exact(4)
                .map(|p| {
                    if p[3] >= g.alpha_min {
                        slot[&mapping[&to_15_bits(p[0], p[1], p[2])]]
                    } else {
                        0
                    }
                })
                .collect::<Vec<_>>()
                .chunks(g.side)
                .map(|row| row.to_vec())
                .collect()
        })
        .collect();
    // Rounded down, also when the box starts right of the anchor and `-x0`
    // is negative: that is what the anchor always was.
    let anchor = (
        ox as i64 + (-x0 * bw as i64).div_euclid(width as i64),
        oy as i64 + (-y0 * bh as i64).div_euclid(height as i64),
    );
    Some(Converted {
        frames,
        palette,
        anchor,
        size: (bw, bh),
        rm_box: (width, height),
    })
}
