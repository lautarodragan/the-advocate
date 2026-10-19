//! The picture of a `ShowPicture` on the console's screen: where it lands
//! and what colour each pixel is.
//!
//! **RM2k's screen is 320x240 and the console's 256x224**, so the picture
//! is scaled like the title: the two corners of its rectangle go through
//! the same arithmetic and the picture is brought to the size between them.
//! **RM2k's position is the picture's centre**, not its corner
//! (`Sprite_Picture` does `SetOx(width / 2)`), so a picture centred near an
//! edge starts off the screen, and that is what the game shows.
//!
//! Its colours are the fifteen of a sprite palette —index 0 is the one not
//! drawn—, kept by use: the picture's fade is a tone, and the console tones
//! the palette, so no colour of it can be shared.
//!
//! Two more things a `ShowPicture` can ask for, and [`convert_shown`] does
//! them:
//!
//! * **its zoom**, a percentage the picture is drawn at before anything
//!   else: RM2k's sprite is the file scaled by it, about its centre;
//! * **that it go with the map** (`fixed_to_map`). Such a picture is part
//!   of the world and the map is not scaled to the console's screen —its
//!   tiles are sixteen pixels on both—, so it is not scaled either: only
//!   its zoom. Where it lands is then the console's, at run time, and the
//!   corner answered is relative to its centre.
//!
//! And a picture with its transparent colour —or with pixels its file
//! leaves transparent— keeps them as index 0: a pixel is the picture's if
//! the scaled alpha reaches half, as with a battler.

use crate::pixels::{most_used, rgb_to_15_bits, scaled_rgb, scaled_rgba, to_15_bits};
use adeleine::Color;
use rm2k_render::Picture;
use std::collections::HashMap;

/// The screens the picture goes between: RM2k's and the console's.
#[derive(Clone, Copy, Debug)]
pub struct Screens {
    pub rm: (i64, i64),
    pub console: (i64, i64),
}

impl Screens {
    /// A horizontal coordinate of RM2k's screen on the console's, rounded
    /// down **with negatives too**: a picture that starts at -16 has both
    /// its ends land on the same side of the rounding.
    fn x(&self, v: i64) -> i64 {
        (v * self.console.0).div_euclid(self.rm.0)
    }

    fn y(&self, v: i64) -> i64 {
        (v * self.console.1).div_euclid(self.rm.1)
    }

    /// Where a picture of `width` x `height` centred at `(cx, cy)` of RM2k's
    /// screen lands on the console's: `(x, y, width, height)`. Both corners
    /// go through the same arithmetic and the size is their difference;
    /// scaling the size on its own gives a pixel less on some pictures,
    /// and the two ends of the picture would not meet the comparison.
    pub fn place(&self, width: i64, height: i64, cx: i64, cy: i64) -> (i64, i64, i64, i64) {
        let (x0, y0) = (cx - width.div_euclid(2), cy - height.div_euclid(2));
        let (ex0, ey0) = (self.x(x0), self.y(y0));
        (
            ex0,
            ey0,
            self.x(x0 + width) - ex0,
            self.y(y0 + height) - ey0,
        )
    }
}

pub struct Converted {
    pub x: i64,
    pub y: i64,
    pub width: usize,
    pub height: usize,
    /// Its colours, fifteen bits each.
    pub palette: Vec<Color>,
    /// The picture as indices into `palette` **plus one**, row by row,
    /// which is how a sprite palette numbers them.
    pub indices: Vec<Vec<usize>>,
}

/// `picture` —as RM2k draws it: its alpha is not the console's and is
/// dropped— centred at `(cx, cy)`, scaled and down to `colors`.
pub fn convert(
    picture: &Picture,
    cx: i64,
    cy: i64,
    screens: Screens,
    colors: usize,
) -> crate::Result<Converted> {
    let (x, y, w, h) = screens.place(picture.width as i64, picture.height as i64, cx, cy);
    if w <= 0 || h <= 0 {
        return Err(crate::Bad::answer(format!(
            "a {}x{} picture centred at ({cx}, {cy}) is {w}x{h} on the console's screen",
            picture.width, picture.height
        )));
    }
    let (width, height) = (w as usize, h as usize);
    let pixels = rgb_to_15_bits(&scaled_rgb(picture, width, height));
    let (palette, mapping) = most_used(&pixels, colors);
    let slot: HashMap<Color, usize> = palette
        .iter()
        .enumerate()
        .map(|(i, &c)| (c, i + 1))
        .collect();
    let indices = pixels
        .chunks(width)
        .map(|row| row.iter().map(|c| slot[&mapping[c]]).collect())
        .collect();
    Ok(Converted {
        x,
        y,
        width,
        height,
        palette,
        indices,
    })
}

/// How a `ShowPicture` shows its picture, besides where.
#[derive(Clone, Copy, Debug)]
pub struct Shown {
    /// The zoom, in percent.
    pub zoom: i64,
    /// Whether it goes with the map instead of with the screen.
    pub map_fixed: bool,
    /// From what alpha a pixel is the picture's.
    pub alpha_min: u8,
}

impl Shown {
    /// A picture shown at its size and with the screen: nothing besides
    /// [`convert`].
    pub const PLAIN: Shown = Shown {
        zoom: 100,
        map_fixed: false,
        alpha_min: 128,
    };
}

/// `zoom` percent of `side`, rounded to the nearest pixel and never under
/// one.
pub fn zoomed(side: i64, zoom: i64) -> i64 {
    ((side * zoom + 50) / 100).max(1)
}

/// `picture` —as RM2k draws it, with its transparent colour— centred at
/// `(cx, cy)` and shown as `shown` says: zoomed, scaled to the console's
/// screen unless it goes with the map, and down to `colors` with what is
/// transparent at index 0.
///
/// A picture shown plainly and without a transparent pixel is exactly
/// [`convert`]'s, byte for byte: it was the only road until 2026-10-01, and
/// the cartridges that only had that picture come out the same.
pub fn convert_shown(
    picture: &Picture,
    cx: i64,
    cy: i64,
    screens: Screens,
    colors: usize,
    shown: Shown,
) -> crate::Result<Converted> {
    let opaque = picture.rgba.chunks_exact(4).all(|p| p[3] == 255);
    if shown.zoom == 100 && !shown.map_fixed && opaque {
        return convert(picture, cx, cy, screens, colors);
    }
    if !(1..=100).contains(&shown.zoom) {
        return Err(crate::Bad::answer(format!(
            "a picture at {}% zoom: only shrinking is done",
            shown.zoom
        )));
    }
    let (zw, zh) = (
        zoomed(picture.width as i64, shown.zoom),
        zoomed(picture.height as i64, shown.zoom),
    );
    let (x, y, w, h) = if shown.map_fixed {
        (-zw.div_euclid(2), -zh.div_euclid(2), zw, zh)
    } else {
        screens.place(zw, zh, cx, cy)
    };
    if w <= 0 || h <= 0 {
        return Err(crate::Bad::answer(format!(
            "a {}x{} picture centred at ({cx}, {cy}) is {w}x{h} on the console's screen",
            picture.width, picture.height
        )));
    }
    let (width, height) = (w as usize, h as usize);
    let scaled = scaled_rgba(picture, width, height);
    let pixels: Vec<Option<Color>> = scaled
        .rgba
        .chunks_exact(4)
        .map(|p| (p[3] >= shown.alpha_min).then(|| to_15_bits(p[0], p[1], p[2])))
        .collect();
    let opaque_pixels: Vec<Color> = pixels.iter().flatten().copied().collect();
    let (palette, mapping) = most_used(&opaque_pixels, colors);
    let slot: HashMap<Color, usize> = palette
        .iter()
        .enumerate()
        .map(|(i, &c)| (c, i + 1))
        .collect();
    let indices = pixels
        .chunks(width)
        .map(|row| {
            row.iter()
                .map(|c| c.map_or(0, |c| slot[&mapping[&c]]))
                .collect()
        })
        .collect();
    Ok(Converted {
        x,
        y,
        width,
        height,
        palette,
        indices,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    const SCREENS: Screens = Screens {
        rm: (320, 240),
        console: (256, 224),
    };

    #[test]
    fn a_picture_past_the_left_edge_starts_off_the_screen() {
        // "One year previously": 233x31 centred at (100, 175).
        assert_eq!(SCREENS.place(233, 31, 100, 175), (-13, 149, 186, 29));
    }

    /// A 4x2 picture with its left half transparent and two colours on the
    /// right.
    fn half_transparent() -> Picture {
        let mut p = Picture::transparent(4, 2);
        for (i, px) in p.rgba.chunks_mut(4).enumerate() {
            if i % 4 >= 2 {
                px.copy_from_slice(if i % 2 == 0 {
                    &[248, 0, 0, 255]
                } else {
                    &[0, 0, 248, 255]
                });
            }
        }
        p
    }

    #[test]
    fn what_is_transparent_is_index_zero() {
        let shown = Shown {
            map_fixed: true,
            ..Shown::PLAIN
        };
        let c = convert_shown(&half_transparent(), 0, 0, SCREENS, 15, shown).unwrap();
        assert_eq!((c.width, c.height), (4, 2));
        for row in &c.indices {
            assert_eq!(&row[..2], &[0, 0]);
            assert!(row[2] > 0 && row[3] > 0 && row[2] != row[3]);
        }
        // Black first, as in every palette `most_used` makes, and the two.
        assert_eq!(c.palette.len(), 3);
    }

    /// With the map, the picture keeps its pixels —only its zoom— and its
    /// corner is relative to its centre.
    #[test]
    fn with_the_map_only_the_zoom_scales() {
        let mut p = Picture::transparent(90, 181);
        p.rgba.iter_mut().for_each(|v| *v = 255);
        let shown = Shown {
            zoom: 35,
            map_fixed: true,
            ..Shown::PLAIN
        };
        let c = convert_shown(&p, 153, 154, SCREENS, 15, shown).unwrap();
        assert_eq!((c.width, c.height), (32, 63));
        // RM2k's origin is half the size, rounded down: 32 / 2 and 63 / 2.
        assert_eq!((c.x, c.y), (-16, -31));
    }

    /// Plain and opaque, it is the road there always was.
    #[test]
    fn plain_and_opaque_is_convert() {
        let mut p = half_transparent();
        p.rgba.iter_mut().skip(3).step_by(4).for_each(|a| *a = 255);
        let a = convert(&p, 100, 100, SCREENS, 15).unwrap();
        let b = convert_shown(&p, 100, 100, SCREENS, 15, Shown::PLAIN).unwrap();
        assert_eq!((a.x, a.y, a.width, a.height), (b.x, b.y, b.width, b.height));
        assert_eq!(a.indices, b.indices);
        assert_eq!(a.palette, b.palette);
    }
}
