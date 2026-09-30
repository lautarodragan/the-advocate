//! A battle animation's frames: its cells, cut from the sheet and placed
//! the way RM2k places them.
//!
//! A frame is a list of cells, and a cell is a square of the animation's
//! sheet —see [`rm2k_rules::battle_animation`]— drawn centred on `(x, y)`
//! of the animation's anchor, zoomed by `zoom` percent and faded by
//! `transparency` percent, with a tone. The cells marked not `valid` are
//! the holes the editor leaves when one in the middle is deleted, and are
//! not drawn; nor is a cell the sheet does not have.
//!
//! **What comes out is the cells, not the frame.** Each one is cut, zoomed
//! and faded, and said where it goes; stacking them, in their order, is
//! the caller's. That is because of the tone: RM2k tones each cell before
//! stacking it, and the tone is done at the depth the pictures are shown
//! at —eight bits a channel on a PC, fewer on other screens—, which is
//! the caller's to know. So the tone of each cell goes out with it, not
//! applied.
//!
//! Where a cell goes is relative to the corner of the **animation's box**:
//! the smallest rectangle that holds every valid cell of every frame,
//! whether the sheet has it or not. A frame that shifts to one side and
//! another that does not are then in the same coordinates, and the anchor
//! —the point RM2k puts over the target— is at minus the box's corner.

use crate::fail::{Bad, Result};
use crate::picture::{self, Picture};
use crate::resample::bilinear_resize;
use ditto::schema::{Animation, AnimationCellData};
use rm2k_rules::battle_animation::{cell_origin, cell_side};
use std::path::{Path, PathBuf};

/// A cell as RM2k places it, before its tone.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Piece {
    /// Cut from the sheet, zoomed and faded.
    pub picture: Picture,
    /// Its corner, relative to the corner of the animation's box.
    pub x: i64,
    pub y: i64,
    /// `tone_red`, `tone_green`, `tone_blue`, `tone_gray`: 0 to 200, 100
    /// leaves the colour as it is.
    pub tone: [i32; 4],
}

/// The smallest rectangle holding every valid cell of every frame,
/// relative to the anchor: `(x, y, width, height)`.
pub type Bounds = (i64, i64, i64, i64);

/// The cells RM2k draws of a frame, in their order.
fn live(cells: &[AnimationCellData]) -> impl Iterator<Item = &AnimationCellData> {
    cells.iter().filter(|c| c.valid != 0)
}

/// How big a cell is with its zoom: the sheet's side times `zoom` percent,
/// rounded down, and never less than a pixel.
fn side(large: bool, cell: &AnimationCellData) -> i64 {
    ((cell_side(large) as i64 * cell.zoom as i64).div_euclid(100)).max(1)
}

/// The animation's box, or None if no frame has a valid cell.
pub fn bounds(animation: &Animation) -> Option<Bounds> {
    let mut found: Option<(i64, i64, i64, i64)> = None;
    for frame in &animation.frames {
        for cell in live(&frame.cells) {
            let side = side(animation.large, cell);
            let x = cell.x as i64 - side / 2;
            let y = cell.y as i64 - side / 2;
            found = Some(match found {
                None => (x, y, x + side, y + side),
                Some((x0, y0, x1, y1)) => {
                    (x0.min(x), y0.min(y), x1.max(x + side), y1.max(y + side))
                }
            });
        }
    }
    found.map(|(x0, y0, x1, y1)| (x0, y0, x1 - x0, y1 - y0))
}

/// One cell, cut from `sheet`, zoomed and faded, or None if the sheet does
/// not have it.
///
/// The fade is the alpha times `100 - transparency` percent, rounded down,
/// with the transparency clamped to 0..100.
pub fn cell(sheet: &Picture, large: bool, cell: &AnimationCellData) -> Option<Picture> {
    let full = cell_side(large) as i64;
    let (sx, sy) = cell_origin(cell.cell_id, large);
    let (sx, sy) = (sx as i64, sy as i64);
    if sx + full > sheet.width as i64 || sy + full > sheet.height as i64 {
        return None;
    }
    let mut piece = Picture::transparent(full as usize, full as usize);
    for y in 0..full {
        for x in 0..full {
            let at = ((y * full + x) * 4) as usize;
            piece.rgba[at..at + 4].copy_from_slice(&sheet.get(sx + x, sy + y));
        }
    }
    let side = side(large, cell) as usize;
    if side != full as usize {
        piece = bilinear_resize(&piece, side, side);
    }
    let opacity = 100 - cell.transparency.clamp(0, 100) as u32;
    if opacity != 100 {
        for px in piece.rgba.chunks_exact_mut(4) {
            px[3] = (px[3] as u32 * opacity / 100) as u8;
        }
    }
    Some(piece)
}

/// Every frame of `animation`, as the cells RM2k draws of each, placed in
/// the animation's box; or no box, and no cells, if no frame has one.
pub fn frames(animation: &Animation, sheet: &Picture) -> (Option<Bounds>, Vec<Vec<Piece>>) {
    let Some(bounds) = bounds(animation) else {
        return (None, animation.frames.iter().map(|_| Vec::new()).collect());
    };
    let (x0, y0, _, _) = bounds;
    let frames = animation
        .frames
        .iter()
        .map(|frame| {
            live(&frame.cells)
                .filter_map(|c| {
                    let picture = cell(sheet, animation.large, c)?;
                    let half = side(animation.large, c) / 2;
                    Some(Piece {
                        picture,
                        x: c.x as i64 - half - x0,
                        y: c.y as i64 - half - y0,
                        tone: [c.tone_red, c.tone_green, c.tone_blue, c.tone_gray],
                    })
                })
                .collect()
        })
        .collect();
    (Some(bounds), frames)
}

/// One animation a request asks for: its sheet, and the animation as
/// Ditto reads it.
#[derive(Debug, Clone)]
pub struct Wanted {
    pub sheet: PathBuf,
    pub animation: Animation,
}

/// A request: a JSON list, one entry per animation, each
/// `{"sheet_file": path, "animation": {...}}`, the animation named as in
/// Ditto's dump —only `large` and `frames` are read—. A relative path is
/// relative to the request's directory.
pub fn request(path: &Path) -> Result<Vec<Wanted>> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    let whose = path.display().to_string();
    let bad = |what: String| Bad::answer(format!("{whose}: {what}"));
    let data: serde_json::Value = serde_json::from_str(&text).map_err(|e| bad(e.to_string()))?;
    let base = path.parent().unwrap_or(Path::new(""));
    let entries = data
        .as_array()
        .ok_or_else(|| bad("not a list".to_string()))?;
    let mut wanted = Vec::with_capacity(entries.len());
    for (i, entry) in entries.iter().enumerate() {
        let sheet = entry
            .get("sheet_file")
            .and_then(|v| v.as_str())
            .ok_or_else(|| bad(format!("entry {i}: `sheet_file` is not a path")))?;
        let animation = entry
            .get("animation")
            .ok_or_else(|| bad(format!("entry {i}: no `animation`")))?;
        let animation: Animation = serde_json::from_value(animation.clone())
            .map_err(|e| bad(format!("entry {i}: `animation`: {e}")))?;
        wanted.push(Wanted {
            sheet: base.join(sheet),
            animation,
        });
    }
    Ok(wanted)
}

/// The file cell `k` of frame `f` of animation `i` is written to.
pub fn piece_file(i: usize, f: usize, k: usize) -> String {
    format!("{i}-{f}-{k}.png")
}

/// Draws every animation of a request into `dir`, which is created if it
/// is not there: for animation `i`, `<i>.json` with its box and where each
/// cell goes, and each cell as `<i>-<frame>-<cell>.png`. A sheet several
/// entries share is read once.
pub fn write(dir: &Path, wanted: &[Wanted]) -> Result<()> {
    std::fs::create_dir_all(dir).map_err(|e| Bad::usage(format!("{}: {e}", dir.display())))?;
    let mut read: std::collections::HashMap<PathBuf, Picture> = Default::default();
    for (i, w) in wanted.iter().enumerate() {
        if !read.contains_key(&w.sheet) {
            read.insert(w.sheet.clone(), picture::read_rm2k(&w.sheet)?);
        }
        let (bounds, frames) = frames(&w.animation, &read[&w.sheet]);
        let mut listed = Vec::with_capacity(frames.len());
        for (f, pieces) in frames.iter().enumerate() {
            let mut cells = Vec::with_capacity(pieces.len());
            for (k, piece) in pieces.iter().enumerate() {
                picture::write_png(&dir.join(piece_file(i, f, k)), &piece.picture)?;
                cells.push(serde_json::json!({"x": piece.x, "y": piece.y, "tone": piece.tone}));
            }
            listed.push(serde_json::Value::Array(cells));
        }
        let manifest = serde_json::json!({
            "box": bounds.map(|(x, y, w, h)| [x, y, w, h]),
            "frames": listed,
        });
        let path = dir.join(format!("{i}.json"));
        std::fs::write(&path, manifest.to_string())
            .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    }
    Ok(())
}
