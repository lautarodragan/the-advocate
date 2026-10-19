//! The picture of a `ShowPicture` too big for the sprites, as a background
//! layer: 4bpp tiles, a tilemap and a few palettes.
//!
//! It is drawn where the `ShowPicture` puts it on the console's screen —the
//! same arithmetic as [`crate::show_picture`]— onto a **canvas the width of
//! the screen**, cut into 8x8 cells. What the picture leaves empty, inside
//! the canvas or outside its rectangle, is index 0: the layer draws
//! nothing there and the screen's backdrop shows.
//!
//! **The canvas is the screen, or taller.** A picture that hangs past the
//! top or the bottom of the screen is kept whole if its tiles fit, because
//! a `MovePicture` can scroll it into view —RM2k does not clip what it
//! keeps—; if they do not fit, it is cut to the screen. Sideways it is
//! always cut to the screen: nothing here scrolls a picture across.
//!
//! **Or it is cropped, if the request says from where**: not scaled at all,
//! the console's screen cut out of the picture with its corner at that
//! pixel, wherever the `ShowPicture` puts it. It is for a picture that is a
//! capture of RM2k's screen —a map, at RM2k's 320x240—: the console does
//! not scale the map, so a scaled capture no longer matches it, and the
//! console's window of it does. The canvas is the screen and nothing more.
//!
//! **The colours are Adeleine's**: cells are grouped by colour and each
//! group chooses its palette, so the choice of what is lost happens before
//! the tiles are cut. Voodoo cuts them, numbers the distinct ones and
//! reuses the mirrored ones.

use crate::pixels::{counts, scaled_rgba, to_15_bits};
use crate::show_picture::{zoomed, Screens};
use adeleine::{reduce_colors, Color, Colors, USABLE_COLORS};
use rm2k_render::Picture;
use std::collections::{BTreeSet, HashMap};

/// The side of a cell.
const CELL: usize = 8;

/// What the caller grants the picture.
#[derive(Clone, Copy, Debug)]
pub struct Room {
    /// How many palettes, and the first one: the ones below it belong to
    /// something else on screen.
    pub palettes: usize,
    pub first_palette: usize,
    /// How many distinct tiles the layer's VRAM holds, the blank one
    /// included.
    pub tiles: usize,
    /// How many rows of cells the tilemap holds.
    pub rows: usize,
}

/// The picture as a layer.
pub struct Background {
    /// Where the canvas starts, in the console's pixels from the top of the
    /// screen: 0, or less if the picture hangs over the top. A multiple of
    /// eight.
    pub top: i64,
    /// Its rows of cells; its columns are the screen's.
    pub rows: usize,
    pub columns: usize,
    /// Whether the picture goes past the screen's sides, so that something
    /// of it is cut off there: what a wave would bring into view.
    pub wider: bool,
    /// The tiles, 32 bytes each, tile 0 blank.
    pub tiles: Vec<u8>,
    pub tile_count: usize,
    /// One entry per cell, row by row.
    pub tilemap: Vec<u16>,
    /// The palettes it draws with, from `first_palette` on, sixteen colours
    /// each; entry 0 of each is never drawn and goes black.
    pub palettes: Vec<Vec<Color>>,
    /// The canvas as colour-memory entries, a byte a pixel row by row —0
    /// where nothing is drawn—, and each entry's colour: what a mode 7
    /// texture is cut from. See [`crate::mode7`].
    pub pixels: Vec<u8>,
    pub colors: Vec<Color>,
    /// The point of the console's screen a zoom shrinks the picture
    /// towards: the picture's centre where it was drawn, as RM2k zooms it;
    /// for a cropped one, the screen's —the picture is wider than what is
    /// seen of it, and its own centre falls off the screen's—.
    pub center: (i64, i64),
}

/// `picture` —as RM2k draws it— centred at `(cx, cy)` of RM2k's screen at
/// `zoom` percent, as a layer that fits `room`; `None` if not even cut to
/// the screen do its tiles fit. With `crop`, the console's screen cut out
/// of it from that pixel instead, unscaled; with `for_console`, the
/// picture unscaled where its centre lands —see [`crate::show_picture`]—.
#[allow(clippy::too_many_arguments)]
pub fn convert(
    picture: &Picture,
    cx: i64,
    cy: i64,
    screens: Screens,
    zoom: i64,
    crop: Option<(i64, i64)>,
    for_console: bool,
    room: Room,
) -> crate::Result<Option<Background>> {
    if !(1..=100).contains(&zoom) {
        return Err(crate::Bad::answer(format!(
            "a picture at {zoom}% zoom: only shrinking is done"
        )));
    }
    let (width, height) = (screens.console.0, screens.console.1);
    let (x, y, w, h, drawn) = match crop {
        Some((left, top)) => {
            // The crop is in the file's pixels: at another zoom they would
            // be somewhere else, and nothing asks for it.
            if zoom != 100 {
                return Err(crate::Bad::answer(format!(
                    "a picture cropped from ({left}, {top}) at {zoom}% zoom: a crop is of the picture as it is"
                )));
            }
            let (pw, ph) = (picture.width as i64, picture.height as i64);
            if left < 0 || top < 0 || left + width > pw || top + height > ph {
                return Err(crate::Bad::answer(format!(
                    "the console's {width}x{height} screen from ({left}, {top}) goes past the {pw}x{ph} picture"
                )));
            }
            (-left, -top, pw, ph, picture.clone())
        }
        None if for_console => {
            if zoom != 100 {
                return Err(crate::Bad::answer(format!(
                    "a picture drawn for the console at {zoom}% zoom: zooming it would scale it"
                )));
            }
            let (pw, ph) = (picture.width as i64, picture.height as i64);
            let (x, y, w, h) = screens.place_unscaled(pw, ph, cx, cy);
            (x, y, w, h, picture.clone())
        }
        None => {
            let (zw, zh) = (
                zoomed(picture.width as i64, zoom),
                zoomed(picture.height as i64, zoom),
            );
            let (x, y, w, h) = screens.place(zw, zh, cx, cy);
            if w <= 0 || h <= 0 {
                return Err(crate::Bad::answer(format!(
                    "a {}x{} picture centred at ({cx}, {cy}) is {w}x{h} on the console's screen",
                    picture.width, picture.height
                )));
            }
            (x, y, w, h, scaled_rgba(picture, w as usize, h as usize))
        }
    };
    let pixels: Vec<Option<Color>> = drawn
        .rgba
        .chunks_exact(4)
        .map(|p| (p[3] >= 128).then(|| to_15_bits(p[0], p[1], p[2])))
        .collect();
    let screen = (0, height);
    // A cropped one is the screen: what hangs past it is what the crop
    // leaves out.
    let whole = match crop {
        Some(_) => screen,
        None => (
            y.min(0).div_euclid(CELL as i64) * CELL as i64,
            (y + h).max(height),
        ),
    };
    let mut tried = Vec::new();
    for (top, bottom) in [whole, screen] {
        if tried.contains(&(top, bottom)) {
            continue;
        }
        tried.push((top, bottom));
        let rows = ((bottom - top) as usize).div_ceil(CELL);
        if rows > room.rows {
            continue;
        }
        let canvas = Canvas {
            width: width as usize,
            height: rows * CELL,
            top,
        };
        let drawn = canvas.draw(&pixels, x, y, w as usize, h as usize);
        if let Some(mut layer) = layer(&canvas, &drawn, room)? {
            layer.wider = x < 0 || x + w > width;
            layer.center = match crop {
                Some(_) => (width / 2, height / 2),
                None => (x + w / 2, y + h / 2),
            };
            return Ok(Some(layer));
        }
    }
    Ok(None)
}

struct Canvas {
    width: usize,
    height: usize,
    top: i64,
}

impl Canvas {
    /// The picture's pixels, `w` x `h` with their corner at `(x, y)` of the
    /// screen, on the canvas: `None` where it draws nothing.
    fn draw(
        &self,
        pixels: &[Option<Color>],
        x: i64,
        y: i64,
        w: usize,
        h: usize,
    ) -> Vec<Option<Color>> {
        let mut out = vec![None; self.width * self.height];
        for row in 0..self.height {
            let py = row as i64 + self.top - y;
            if !(0..h as i64).contains(&py) {
                continue;
            }
            for column in 0..self.width {
                let px = column as i64 - x;
                if (0..w as i64).contains(&px) {
                    out[row * self.width + column] = pixels[py as usize * w + px as usize];
                }
            }
        }
        out
    }

    /// The colours of each cell, row by row.
    fn cells(&self, pixels: &[Option<Color>]) -> Vec<Colors> {
        let mut out = Vec::new();
        for cy in 0..self.height / CELL {
            for cx in 0..self.width / CELL {
                let mut set = BTreeSet::new();
                for y in 0..CELL {
                    for x in 0..CELL {
                        if let Some(c) = pixels[(cy * CELL + y) * self.width + cx * CELL + x] {
                            set.insert(c);
                        }
                    }
                }
                out.push(set);
            }
        }
        out
    }
}

/// The canvas as tiles, or `None` if they are more than `room` holds.
fn layer(
    canvas: &Canvas,
    drawn: &[Option<Color>],
    room: Room,
) -> crate::Result<Option<Background>> {
    let opaque: Vec<Color> = drawn.iter().flatten().copied().collect();
    let totals = counts(&opaque);
    let cells = canvas.cells(drawn);
    let reduced = reduce_colors(&totals, &cells, room.palettes, USABLE_COLORS)?;
    let palettes: Vec<Vec<Color>> = reduced
        .palettes
        .into_iter()
        .map(|p| p.into_iter().collect())
        .collect();

    // Each cell uses the palette Adeleine chose for its group, and each
    // colour uses that cell's local mapping.
    let columns = canvas.width / CELL;
    let mut indices = vec![0u8; drawn.len()];
    for (k, (set, decided)) in cells.iter().zip(&reduced.tiles).enumerate() {
        let Some(p) = decided.palette else {
            continue;
        };
        let mapping: HashMap<Color, Color> = set
            .iter()
            .copied()
            .zip(decided.mapping.iter().copied())
            .collect();
        let entry = (room.first_palette + p) * 16;
        let (cx, cy) = (k % columns, k / columns);
        for y in 0..CELL {
            for x in 0..CELL {
                let at = (cy * CELL + y) * canvas.width + cx * CELL + x;
                if let Some(c) = drawn[at] {
                    let target = mapping[&c];
                    let i = palettes[p]
                        .iter()
                        .position(|q| *q == target)
                        .expect("in its palette");
                    indices[at] = (entry + 1 + i) as u8;
                }
            }
        }
    }
    let mut colors: Vec<Option<voodoo::Rgb15>> = vec![Some((0, 0, 0)); voodoo::ENTRIES];
    for (p, pal) in palettes.iter().enumerate() {
        for (i, c) in pal.iter().enumerate() {
            colors[(room.first_palette + p) * 16 + 1 + i] = Some((c[0], c[1], c[2]));
        }
    }
    let indexed = voodoo::Picture {
        width: canvas.width,
        height: canvas.height,
        pixels: indices,
        colors,
    };
    let options = voodoo::Options {
        max_tiles: room.tiles,
        ..voodoo::Options::at(4)
    };
    let Ok(cut) = voodoo::convert(&indexed, &[], &options) else {
        return Ok(None);
    };
    let mut out_palettes = Vec::new();
    for pal in &palettes {
        let mut sixteen = vec![[0, 0, 0]];
        sixteen.extend(pal.iter().copied());
        sixteen.resize(16, [0, 0, 0]);
        out_palettes.push(sixteen);
    }
    let colors = indexed
        .colors
        .iter()
        .map(|c| c.map_or([0, 0, 0], |(r, g, b)| [r, g, b]))
        .collect();
    Ok(Some(Background {
        top: canvas.top,
        rows: canvas.height / CELL,
        columns,
        wider: false,
        tile_count: cut.report.tiles,
        tiles: cut.tiles,
        tilemap: cut.tilemap.into_iter().flatten().collect(),
        palettes: out_palettes,
        pixels: indexed.pixels,
        colors,
        center: (0, 0),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    const SCREENS: Screens = Screens {
        rm: (320, 240),
        console: (256, 224),
    };

    const ROOM: Room = Room {
        palettes: 7,
        first_palette: 1,
        tiles: 1024,
        rows: 64,
    };

    /// A `width` x `height` picture of stripes in `colors` greys, a column
    /// each: every cell draws with eight of them.
    fn stripes(width: usize, height: usize, colors: usize) -> Picture {
        let mut p = Picture::transparent(width, height);
        for (i, px) in p.rgba.chunks_mut(4).enumerate() {
            let v = ((i % width) % colors * 255 / colors) as u8;
            px.copy_from_slice(&[v, v, v, 255]);
        }
        p
    }

    #[test]
    fn a_picture_inside_the_screen_leaves_the_rest_blank() {
        // 80x60 of RM2k's, in the middle: 64x56 of the console's, from
        // (96, 84).
        let layer = convert(
            &stripes(80, 60, 4),
            160,
            120,
            SCREENS,
            100,
            None,
            false,
            ROOM,
        )
        .unwrap()
        .unwrap();
        assert_eq!((layer.top, layer.rows, layer.columns), (0, 28, 32));
        assert!(!layer.wider);
        assert_eq!(layer.tilemap.len(), 28 * 32);
        assert_eq!(layer.tilemap[0], 0, "the corner is blank: tile 0");
        let drawn = layer.tilemap[(84 / 8 + 1) * 32 + 96 / 8 + 1];
        assert_ne!(drawn & 0x3FF, 0);
        assert_eq!(drawn >> 10 & 7, 1, "in the first palette it was given");
        assert_eq!(layer.palettes.len(), 1);
        assert_eq!(layer.palettes[0][0], [0, 0, 0], "entry 0 is never drawn");
    }

    #[test]
    fn a_taller_picture_keeps_what_hangs_past_the_screen() {
        // 320x300 centred at (160, 150): its rows go past the bottom, and a
        // `MovePicture` can bring them up.
        let layer = convert(
            &stripes(320, 300, 2),
            160,
            150,
            SCREENS,
            100,
            None,
            false,
            ROOM,
        )
        .unwrap()
        .unwrap();
        assert_eq!(layer.top, 0);
        assert_eq!(layer.rows, 35, "280 of the console's lines");
        assert!(!layer.wider);
    }

    /// A `width` x `height` picture that goes from black at the top to white
    /// at the bottom: every row of cells is a tile of its own.
    fn ramp(width: usize, height: usize) -> Picture {
        let mut p = Picture::transparent(width, height);
        for (i, px) in p.rgba.chunks_mut(4).enumerate() {
            let v = (i / width * 255 / height) as u8;
            px.copy_from_slice(&[v, v, v, 255]);
        }
        p
    }

    #[test]
    fn one_whose_tiles_do_not_fit_whole_is_cut_to_the_screen() {
        // 400 of RM2k's lines are 373 of the console's, 47 rows of cells
        // and 47 tiles: they do not fit in 40, and the screen's 28 do.
        let room = Room { tiles: 40, ..ROOM };
        let layer = convert(&ramp(400, 400), 160, 120, SCREENS, 100, None, false, room)
            .unwrap()
            .unwrap();
        assert_eq!((layer.top, layer.rows), (0, 28));
        assert!(layer.wider, "400 of RM2k's pixels go past both sides");
        // And in ten, not even the screen.
        let room = Room { tiles: 10, ..ROOM };
        assert!(
            convert(&ramp(400, 400), 160, 120, SCREENS, 100, None, false, room)
                .unwrap()
                .is_none()
        );
    }

    #[test]
    fn a_cropped_picture_is_the_screen_cut_out_of_it_unscaled() {
        // RM2k's screen, transparent but for one 8x8 square at (24, 24):
        // cut from (8, 16), it is the cell at (16, 8) of the screen, and
        // nothing else is drawn. Scaled, it would not even be whole cells.
        let mut p = Picture::transparent(320, 240);
        for y in 24..32 {
            for x in 24..32 {
                let at = (y * 320 + x) * 4;
                p.rgba[at..at + 4].copy_from_slice(&[255, 255, 255, 255]);
            }
        }
        let layer = convert(&p, 160, 120, SCREENS, 100, Some((8, 16)), false, ROOM)
            .unwrap()
            .unwrap();
        assert_eq!((layer.top, layer.rows, layer.columns), (0, 28, 32));
        assert!(layer.wider, "what is cut off at the sides is the picture's");
        let drawn: Vec<usize> = (0..layer.tilemap.len())
            .filter(|&k| layer.tilemap[k] & 0x3FF != 0)
            .collect();
        assert_eq!(drawn, [32 + 2], "only the cell at (16, 8)");
        assert_eq!(layer.tile_count, 2, "the blank tile and the square");
        // Wherever the `ShowPicture` puts it, the crop is the same.
        let elsewhere = convert(&p, 40, 200, SCREENS, 100, Some((8, 16)), false, ROOM)
            .unwrap()
            .unwrap();
        assert_eq!(elsewhere.tilemap, layer.tilemap);
    }

    #[test]
    fn a_crop_has_to_fit_the_picture_and_be_at_its_size() {
        let p = stripes(320, 240, 2);
        let past = convert(&p, 160, 120, SCREENS, 100, Some((65, 0)), false, ROOM);
        assert!(past.is_err(), "256 from 65 goes past 320");
        let zoomed = convert(&p, 160, 120, SCREENS, 50, Some((0, 0)), false, ROOM);
        assert!(zoomed.is_err(), "a crop is of the file's pixels");
        assert!(convert(&p, 160, 120, SCREENS, 100, Some((64, 16)), false, ROOM).is_ok());
    }
}
