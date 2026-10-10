//! A battle's backdrop and its battlers, as the console composes them into
//! one layer at 8 bits a pixel.
//!
//! RM2k's backdrop is 320x160 at the top of a 320x240 screen; here the
//! scene is smaller, so the backdrop goes in scaled, and the battlers at
//! the same scale, so the troop's positions map by the same arithmetic.
//!
//! * **The quality backdrop** keeps its most used colours, black first.
//! * **The light fallback** —the one a cartridge carries for a console
//!   without the data file— is the same picture at a fraction of the size,
//!   and its colours are merged by what shows the least: kept by use, the
//!   few most used of a backdrop are all floor and wall, and the accents go.
//! * **A battler** is either drawn or not, pixel by pixel, cut at half its
//!   alpha, and its colours merged by what shows the least into the fifteen
//!   of a palette.

use crate::pixels::{
    least_visible, most_used, rgb_to_15_bits, scaled_rgb, scaled_rgba, to_15_bits,
};
use adeleine::{Color, Merge};
use rm2k_render::Picture;
use std::collections::HashMap;

/// The scene's size and colours, which the caller also emits for the
/// console.
#[derive(Clone, Copy, Debug)]
pub struct Geometry {
    /// The scene, in pixels.
    pub width: usize,
    pub height: usize,
    /// How many colours the quality backdrop keeps, and the CGRAM entry
    /// they start at: its indices come out shifted by it.
    pub colors: usize,
    pub cgram_base: usize,
    /// How many times smaller the light fallback is on each side, and how
    /// many colours it keeps. They go at `cgram_base` too.
    pub light_scale: usize,
    pub light_colors: usize,
    /// RM2k's lengths on the scene's: `value * num / den`, rounded, and
    /// never under a pixel.
    pub scale: (i64, i64),
    /// A battler's colours, and the alpha from which a pixel is its.
    pub battler_colors: usize,
    pub alpha_min: u8,
}

impl Geometry {
    pub fn scale(&self, value: i64) -> i64 {
        let (num, den) = self.scale;
        ((value * num + den / 2).div_euclid(den)).max(1)
    }
}

/// A backdrop in quality: CGRAM indices, row by row, and its colours.
pub struct Backdrop {
    pub indices: Vec<Vec<usize>>,
    pub palette: Vec<Color>,
}

pub fn backdrop(picture: &Picture, g: &Geometry) -> Backdrop {
    let pixels = rgb_to_15_bits(&scaled_rgb(picture, g.width, g.height));
    let (palette, mapping) = most_used(&pixels, g.colors);
    let at: HashMap<Color, usize> = palette
        .iter()
        .enumerate()
        .map(|(i, &c)| (c, i + g.cgram_base))
        .collect();
    let indices = pixels
        .chunks(g.width)
        .map(|row| row.iter().map(|c| at[&mapping[c]]).collect())
        .collect();
    Backdrop { indices, palette }
}

/// A backdrop's light fallback.
pub struct Light {
    /// Its CGRAM indices at its own size: what travels.
    pub small: Vec<Vec<usize>>,
    /// The same, each pixel repeated to the scene's size, as the console
    /// leaves it in memory.
    pub indices: Vec<Vec<usize>>,
    /// Most used first, ties by the colour.
    pub palette: Vec<Color>,
}

pub fn light_backdrop(picture: &Picture, g: &Geometry) -> crate::Result<Light> {
    let (w, h) = (g.width / g.light_scale, g.height / g.light_scale);
    let pixels = rgb_to_15_bits(&scaled_rgb(picture, w, h));
    let reduced = least_visible(&pixels, g.light_colors)?;
    let at: HashMap<Color, usize> = reduced
        .palette
        .iter()
        .enumerate()
        .map(|(i, &c)| (c, i + g.cgram_base))
        .collect();
    let small: Vec<Vec<usize>> = pixels
        .chunks(w)
        .map(|row| row.iter().map(|c| at[&reduced.mapping[c]]).collect())
        .collect();
    let indices = (0..g.height)
        .map(|y| {
            (0..g.width)
                .map(|x| small[y / g.light_scale][x / g.light_scale])
                .collect()
        })
        .collect();
    Ok(Light {
        small,
        indices,
        palette: reduced.palette,
    })
}

/// A battler ready for the console.
pub struct Battler {
    /// At the scene's scale, and cut to the scene: a battler taller than it
    /// is clamped at the top, and its bottom rows are not seen.
    pub width: usize,
    pub height: usize,
    /// Row by row: 0 is not drawn, and the others are the colour in
    /// `palette` plus one.
    pub pixels: Vec<Vec<usize>>,
    /// Its height in RM2k, which is what sorts the troop's drawing order.
    pub rm_height: usize,
    /// Its colours, most used first and ties by the colour.
    pub palette: Vec<Color>,
    /// How many colours it had once shrunk, and what was merged into what.
    pub colors: usize,
    pub merges: Vec<Merge>,
}

pub fn battler(picture: &Picture, g: &Geometry) -> crate::Result<Battler> {
    let w = g.scale(picture.width as i64) as usize;
    let h = g.scale(picture.height as i64) as usize;
    let small = scaled_rgba(picture, w, h);
    let opaque: Vec<Option<Color>> = small
        .rgba
        .chunks_exact(4)
        .map(|p| (p[3] >= g.alpha_min).then(|| to_15_bits(p[0], p[1], p[2])))
        .collect();
    let drawn: Vec<Color> = opaque.iter().flatten().copied().collect();
    let reduced = least_visible(&drawn, g.battler_colors)?;
    let slot: HashMap<Color, usize> = reduced
        .palette
        .iter()
        .enumerate()
        .map(|(i, &c)| (c, i + 1))
        .collect();
    let (width, height) = (w.min(g.width), h.min(g.height));
    let pixels = (0..height)
        .map(|y| {
            (0..width)
                .map(|x| opaque[y * w + x].map_or(0, |c| slot[&reduced.mapping[&c]]))
                .collect()
        })
        .collect();
    Ok(Battler {
        width,
        height,
        pixels,
        rm_height: picture.height,
        palette: reduced.palette,
        colors: reduced.colors,
        merges: reduced.merges,
    })
}
