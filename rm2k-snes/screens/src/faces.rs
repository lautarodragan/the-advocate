//! The faces the message window shows: each face a `ChangeFaceGraphic` of
//! the game names, cut from its FaceSet and turned into what the cartridge
//! stores —36 tiles of 4bpp, row by row, and fifteen colours—, in the order
//! the event compiler's indices list them, which is how `OP_FACE` names
//! one. The runtime copies the tiles into the window's text cells and puts
//! the colours in palette 1 on the window's lines: see `message_face.s`.
//!
//! What RM2k does with the picture is what is done here: the 48x48 square
//! of the FaceSet with its colour key —index 0 transparent—, mirrored if the
//! command asks, drawn over the window's background. A 4bpp cell is one
//! palette, so a transparent pixel cannot show the window's own cell under
//! it: it takes the colour the background has where RM2k draws the face,
//! and the gradient's step is the one the face's rows cross. The slot
//! screen's faces make black transparent —see `face_palette` in `slots.rs`—
//! because there the screen behind is black; here the map is behind, and a
//! hole would show it, so every colour is a colour and index 0 is unused.

use crate::cells::{self, rgb15, Color, Counts};
use crate::fail::{Bad, Result};
use crate::game::Game;
use crate::layout::{FACE, FACE_CELLS, MSG_FACE_X, MSG_FACE_Y, WINDOW_HEIGHT, WINDOW_WIDTH};
use crate::message_window::cgram_word;
use rm2k_render::picture::{self, Picture};
use rm2k_render::source::find_resource;
use serde_json::{json, Value};
use std::collections::HashMap;

/// The colours a face has, besides index 0, which the window never shows.
pub const FACE_COLORS: usize = 15;

/// A face as the cartridge stores it.
pub struct DrawnFace {
    /// The 36 tiles, 4bpp, the top row first and left to right.
    pub tiles: Vec<u8>,
    /// Its colours as colour-memory words, entries 1 to 15 of its palette.
    pub palette: Vec<u16>,
    /// Whether its FaceSet was nowhere, and this is the window's background
    /// alone where the face would be: the converter declares it.
    pub missing: bool,
}

/// A face as the request names it: the FaceSet, the index in it and
/// whether it is mirrored.
pub type Request = (String, i32, bool);

/// The `faces` of a request: `[[FaceSet, index, mirrored], ...]`.
pub fn requested(data: &Value, whose: &str) -> Result<Vec<Request>> {
    let bad = || Bad::answer(format!("{whose}: `faces` is not a list of [FaceSet, index, mirrored]"));
    data.get("faces")
        .and_then(Value::as_array)
        .ok_or_else(bad)?
        .iter()
        .map(|f| {
            let f = f.as_array().filter(|f| f.len() == 3).ok_or_else(bad)?;
            Ok((
                f[0].as_str().ok_or_else(bad)?.to_string(),
                f[1].as_i64().ok_or_else(bad)? as i32,
                f[2].as_bool().ok_or_else(bad)?,
            ))
        })
        .collect()
}

/// Each requested face drawn. One whose FaceSet is neither in the game's
/// `FaceSet/` nor in the RTP's comes out as the window's background alone,
/// `missing`: the box still makes room for it, and the converter says what
/// was lost.
pub fn draw(game: &Game, faces: &[Request]) -> Result<Vec<DrawnFace>> {
    let skin = game.skin()?;
    // What the face's transparent pixels show: the window's background,
    // where RM2k draws the face. The gradient is vertical, so the side the
    // face is on does not change it.
    let background = skin.window_background(WINDOW_WIDTH, WINDOW_HEIGHT);
    let mut dirs = vec![game.game_dir.clone()];
    dirs.extend(game.rtp_dir.iter().cloned());
    let mut sets: HashMap<&str, Picture> = HashMap::new();
    let mut out = Vec::with_capacity(faces.len());
    for (name, index, mirrored) in faces {
        if !sets.contains_key(name.as_str()) {
            if let Some(path) = find_resource(&dirs, "FaceSet", name) {
                sets.insert(name, picture::read_rm2k(&path)?);
            }
        }
        let (mut face, missing) = match sets.get(name.as_str()) {
            Some(set) => (rm2k_render::face::face(set, *index), false),
            None => (Picture::transparent(FACE, FACE), true),
        };
        if *mirrored {
            face = face.mirrored();
        }
        over_background(&mut face, &background);
        let mut drawn = one(&face)?;
        drawn.missing = missing;
        out.push(drawn);
    }
    Ok(out)
}

/// The face's transparent pixels take the window background's colour at
/// the same place.
fn over_background(face: &mut Picture, background: &Picture) {
    for y in 0..face.height {
        for x in 0..face.width {
            let at = (y * face.width + x) * 4;
            if face.rgba[at + 3] == 0 {
                let under = background.get((MSG_FACE_X + x) as i64, (MSG_FACE_Y + y) as i64);
                face.rgba[at..at + 3].copy_from_slice(&under[..3]);
                face.rgba[at + 3] = 255;
            }
        }
    }
}

/// Fifteen colours for a face, every pixel of which is opaque, and the
/// index each colour of the picture takes, from 1: the reduction is the
/// slot screen's, Adeleine's `merge_least_visible`, for the reason given
/// there —the fifteen most used colours of a face are fifteen skin tones—.
pub fn palette(face: &Picture) -> Result<(Vec<Color>, HashMap<Color, u8>)> {
    let mut used = Counts::default();
    for p in face.rgba.chunks_exact(4) {
        used.add(rgb15([p[0], p[1], p[2], p[3]]), 1);
    }
    let (colors, dest): (Vec<Color>, Vec<(Color, Color)>) = if used.len() > FACE_COLORS {
        let counts: Vec<([u8; 3], u64)> = used.in_order();
        let merged = adeleine::merge_least_visible(&counts, FACE_COLORS)?;
        let mut colors: Vec<Color> = merged.mapping.clone();
        colors.sort();
        colors.dedup();
        (colors, counts.iter().map(|(c, _)| *c).zip(merged.mapping).collect())
    } else {
        (used.by_use(), used.in_order().iter().map(|(c, _)| (*c, *c)).collect())
    };
    let index = dest
        .into_iter()
        .map(|(color, target)| {
            let at = colors.iter().position(|c| *c == target).expect("the target is in the palette");
            (color, at as u8 + 1)
        })
        .collect();
    Ok((colors, index))
}

/// One face, drawn: see [`DrawnFace`].
fn one(face: &Picture) -> Result<DrawnFace> {
    debug_assert_eq!((face.width, face.height), (FACE, FACE));
    let (colors, index) = palette(face)?;
    let mut tiles = Vec::with_capacity(FACE_CELLS * FACE_CELLS * voodoo::pack::tile_bytes(4));
    for row in 0..FACE_CELLS {
        for col in 0..FACE_CELLS {
            let cell = cells::cut(face, col, row, &index)?;
            tiles.extend(voodoo::pack::pack_tile(&cell, 4));
        }
    }
    let mut palette: Vec<u16> = colors.iter().map(|c| cgram_word(*c)).collect();
    palette.resize(FACE_COLORS, 0);
    Ok(DrawnFace { tiles, palette, missing: false })
}

/// The answer of `faces`: `{"faces": [face, ...]}`, see the command's help.
pub fn answer(drawn: &[DrawnFace]) -> Value {
    json!({
        "faces": drawn
            .iter()
            .map(|f| json!({"tiles": hex(&f.tiles), "palette": f.palette, "missing": f.missing}))
            .collect::<Vec<_>>(),
    })
}

fn hex(bytes: &[u8]) -> String {
    bytes.iter().map(|b| format!("{b:02x}")).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A face of more colours than a palette comes out with fifteen, none
    /// of them at index 0, and a transparent pixel is a colour: the
    /// background's.
    #[test]
    fn a_face_fills_fifteen_colours_and_no_hole() {
        let mut face = Picture::transparent(FACE, FACE);
        for y in 0..FACE {
            for x in 0..FACE {
                // A gradient: more than fifteen colours, by far.
                let at = (y * FACE + x) * 4;
                if (x, y) == (0, 0) {
                    continue; // left transparent
                }
                face.rgba[at..at + 4].copy_from_slice(&[(x * 5) as u8, (y * 5) as u8, 64, 255]);
            }
        }
        let background = Picture::filled(WINDOW_WIDTH, WINDOW_HEIGHT, [8, 16, 24, 255]);
        over_background(&mut face, &background);
        assert_eq!(face.get(0, 0), [8, 16, 24, 255]);
        let drawn = one(&face).unwrap();
        assert_eq!(drawn.tiles.len(), 36 * 32);
        assert_eq!(drawn.palette.len(), FACE_COLORS);
        // No pixel at index 0: unpack each tile and look.
        for tile in drawn.tiles.chunks_exact(32) {
            for row in voodoo::pack::unpack_tile(tile, 4) {
                assert!(row.iter().all(|&i| i != 0), "a face pixel at the transparent index");
            }
        }
    }

    /// Mirroring swaps the columns and nothing else.
    #[test]
    fn a_mirrored_face_is_the_face_backwards() {
        let mut face = Picture::transparent(4, 1);
        for x in 0..4u8 {
            face.rgba[x as usize * 4..x as usize * 4 + 4].copy_from_slice(&[x, 0, 0, 255]);
        }
        let mirrored = face.mirrored();
        assert_eq!(mirrored.rgba.chunks_exact(4).map(|p| p[0]).collect::<Vec<_>>(), [3, 2, 1, 0]);
    }
}
