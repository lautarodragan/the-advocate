//! What is drawn from the System: a window, its cursor, the blocks the text
//! and its shadow take their colours from, and the timer's digits.
//!
//! Which piece of the System is which is `rm2k_rules::system`'s; this puts
//! them together as easyrpg's `Window` does. A window is its background,
//! stretched or tiled to its size as the database's `message_stretch` says,
//! and the frame on top: the 8x8 corners, and the edges repeated between
//! them. The cursor is laid out like the frame, over a transparent picture,
//! with its middle repeated inside.
//!
//! Where a window goes, what is written in it, and with which letters, is
//! the caller's.
//!
//! **The edges repeat from where they start**, the way the drawings this
//! replaces did: pixel 0 of an edge is at 8, next to the corner. easyrpg
//! `TiledBlit`s them from the window's corner instead, so its pattern is
//! shifted by 8, half an edge. The two only differ with an edge that does
//! not repeat every 8 pixels.

use crate::fail::Result;
use crate::picture::{self, Picture};
use crate::request::{self, Files, Request};
use ditto::schema::SystemStretch;
use rm2k_rules::system::{self as rules, Background, COLOR_BLOCK, EDGE, PIECE};
use std::path::Path;

/// `src` repeated from its corner until it fills `width` x `height`.
pub fn tiled(src: &Picture, width: usize, height: usize) -> Picture {
    let mut out = Picture::transparent(width, height);
    if src.width == 0 || src.height == 0 {
        return out;
    }
    for y in 0..height {
        for x in 0..width {
            let at = (y * width + x) * 4;
            let pixel = src.get((x % src.width) as i64, (y % src.height) as i64);
            out.rgba[at..at + 4].copy_from_slice(&pixel);
        }
    }
    out
}

/// `src` scaled to `width` x `height`, each pixel the nearest one.
///
/// The nearest is found the way the drawing this replaces found it —
/// Pillow's `NEAREST`—: the source column of column `x` is the whole part
/// of `(x + 0.5) * src.width / width`, **added up column by column in a
/// double** and not computed one by one. The two ways differ by one pixel
/// on some sizes, and the pixels have to be those.
pub fn stretched(src: &Picture, width: usize, height: usize) -> Picture {
    fn nearest(from: usize, to: usize) -> Vec<i64> {
        let scale = from as f64 / to as f64;
        let mut at = scale * 0.5;
        let mut out = Vec::with_capacity(to);
        for _ in 0..to {
            out.push(at as i64);
            at += scale;
        }
        out
    }
    let columns = nearest(src.width, width);
    let rows = nearest(src.height, height);
    let mut out = Picture::transparent(width, height);
    for (y, sy) in rows.iter().enumerate() {
        for (x, sx) in columns.iter().enumerate() {
            let at = (y * width + x) * 4;
            out.rgba[at..at + 4].copy_from_slice(&src.get(*sx, *sy));
        }
    }
    out
}

/// A piece of the System's `w`x`h` rectangle at `(x, y)` of `origin`.
fn piece(system: &Picture, origin: (i32, i32), x: i32, y: i32, w: i32, h: i32) -> Picture {
    system.crop(
        (origin.0 + x) as i64,
        (origin.1 + y) as i64,
        w as usize,
        h as usize,
    )
}

/// The frame laid out from the 32x32 square at `origin` over `out`: the
/// middle repeated inside, if `middle`, then the edges, then the corners,
/// each through its alpha. The corners go last because they cover the
/// edges' ends.
fn frame(out: &mut Picture, system: &Picture, origin: (i32, i32), middle: bool) {
    let (w, h) = (out.width as i64, out.height as i64);
    let edge = EDGE as i64;
    let inner_w = (w - 2 * edge).max(0) as usize;
    let inner_h = (h - 2 * edge).max(0) as usize;
    let long = PIECE - 2 * EDGE;
    let put = |out: &mut Picture, src: Picture, x: i64, y: i64| {
        out.blit(x, y, &src, 0, 0, src.width as i64, src.height as i64);
    };
    if middle && inner_w > 0 && inner_h > 0 {
        let src = piece(system, origin, EDGE, EDGE, long, long);
        put(out, tiled(&src, inner_w, inner_h), edge, edge);
    }
    let top = piece(system, origin, EDGE, 0, long, EDGE);
    let bottom = piece(system, origin, EDGE, PIECE - EDGE, long, EDGE);
    let left = piece(system, origin, 0, EDGE, EDGE, long);
    let right = piece(system, origin, PIECE - EDGE, EDGE, EDGE, long);
    put(out, tiled(&top, inner_w, EDGE as usize), edge, 0);
    put(out, tiled(&bottom, inner_w, EDGE as usize), edge, h - edge);
    put(out, tiled(&left, EDGE as usize, inner_h), 0, edge);
    put(out, tiled(&right, EDGE as usize, inner_h), w - edge, edge);
    for (x, y, to_x, to_y) in [
        (0, 0, 0, 0),
        (PIECE - EDGE, 0, w - edge, 0),
        (0, PIECE - EDGE, 0, h - edge),
        (PIECE - EDGE, PIECE - EDGE, w - edge, h - edge),
    ] {
        put(out, piece(system, origin, x, y, EDGE, EDGE), to_x, to_y);
    }
}

/// An empty window of `width` x `height`: the background filling it the
/// way `background` says, and the frame on top.
pub fn window(system: &Picture, width: usize, height: usize, background: Background) -> Picture {
    let square = piece(system, rules::BACKGROUND, 0, 0, PIECE, PIECE);
    let mut out = match background {
        Background::Stretched => stretched(&square, width, height),
        Background::Tiled => tiled(&square, width, height),
    };
    frame(&mut out, system, rules::FRAME, false);
    out
}

/// Drawing `drawing`, 0 or 1, of the cursor, `width` x `height`, over
/// transparency.
pub fn cursor(system: &Picture, width: usize, height: usize, drawing: usize) -> Picture {
    let mut out = Picture::transparent(width, height);
    frame(&mut out, system, rules::CURSOR[drawing], true);
    out
}

/// The 16x16 block text colour `number`, 0 to 19, takes its pixels from.
pub fn text_color(system: &Picture, number: i32) -> Picture {
    let block = COLOR_BLOCK;
    piece(system, rules::text_color_origin(number), 0, 0, block, block)
}

/// The 16x16 block the text's shadow takes its pixels from.
pub fn shadow(system: &Picture) -> Picture {
    piece(system, rules::SHADOW, 0, 0, COLOR_BLOCK, COLOR_BLOCK)
}

/// The timer's glyphs in a row, the digits 0 to 9 and the colon: glyph `n`
/// is at `n * TIMER_GLYPH_WIDTH`.
pub fn timer(system: &Picture) -> Picture {
    piece(
        system,
        rules::TIMER,
        0,
        0,
        rules::TIMER_GLYPHS * rules::TIMER_GLYPH_WIDTH,
        rules::TIMER_GLYPH_HEIGHT,
    )
}

/// Draws a request. Each entry has `system_file` and `draw`, which is one
/// of:
///
/// * `"window"`, with `width`, `height` and `message_stretch` —0 stretched,
///   1 tiled, as the database says it—;
/// * `"cursor"`, with `width`, `height` and, optionally, `drawing`, 0 or 1;
/// * `"text_color"`, with `color`, 0 to 19;
/// * `"shadow"`;
/// * `"timer"`.
///
/// Picture `i` is written as `<i>.png`, RGBA.
pub fn write(dir: &Path, request_path: &Path) -> Result<()> {
    let request = Request::read(request_path)?;
    let mut files = Files::new(picture::read_rm2k);
    request::write(dir, &request, |r, i| {
        let size = |r: &Request| -> Result<(usize, usize)> {
            Ok((
                r.number_in(i, "width", None, 1..4096)? as usize,
                r.number_in(i, "height", None, 1..4096)? as usize,
            ))
        };
        let what = r.text(i, "draw")?.to_string();
        let system = files.get(&r.file(i, "system_file")?)?;
        Ok(match what.as_str() {
            "window" => {
                let (w, h) = size(r)?;
                let stretch = SystemStretch::from_i32(r.number(i, "message_stretch")? as i32);
                let background = rules::background(stretch).ok_or_else(|| {
                    r.bad(
                        i,
                        format!("`message_stretch` {stretch:?} is not one RM2k draws"),
                    )
                })?;
                window(system, w, h, background)
            }
            "cursor" => {
                let (w, h) = size(r)?;
                let drawing = r.number_in(i, "drawing", Some(0), 0..rules::CURSOR.len() as i64)?;
                cursor(system, w, h, drawing as usize)
            }
            "text_color" => {
                let color = r.number_in(i, "color", None, 0..rules::TEXT_COLORS as i64)?;
                text_color(system, color as i32)
            }
            "shadow" => shadow(system),
            "timer" => timer(system),
            other => {
                return Err(r.bad(
                    i,
                    format!(
                        "`draw` is {other:?}, and it is window, cursor, text_color, shadow \
                         or timer"
                    ),
                ))
            }
        })
    })
}
