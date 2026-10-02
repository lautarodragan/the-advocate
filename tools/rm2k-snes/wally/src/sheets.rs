//! The CharSet sheets a map's characters are cut from, by the name the port
//! gives them.
//!
//! RM2k's drawings are `rm2k-render`'s: a CharSet with its colour key, the
//! made-up sheet of an event drawn with a tile, and a translucent one
//! blended over what is behind it. What the port adds is here: which
//! background a translucent one is baked against —the lower layer of the
//! map it stands in, which is the only thing left behind the sprite—, the
//! dithered sheet of a translucent one, and the copy with a palette of its
//! own, which is the same drawing.

use crate::events::{unbaked, BAKED_SUFFIX};
use crate::fail::Result;
use crate::game::Game;
use crate::layers::{draw, Drawn};
use crate::request::LayersRequest;
use rm2k_render::charset::{tile_sheet, translucent};
use rm2k_render::{picture, Picture};
use crate::sprites::character::Sheets;
use crate::sprites::split::{DITHER_SUFFIX, TILE_PREFIX};
use std::collections::HashMap;

/// The same drawing, counted as another graphic so it gets a palette of its
/// own.
pub const COPY_SUFFIX: &str = "~aparte";

/// The sheets drawn so far, and the lower layers they were baked against.
pub struct Drawer<'a> {
    game: &'a Game,
    /// Which pixels a dithered sheet drops: see [`drops`].
    dither: String,
    sheets: Sheets,
    lower: HashMap<i32, Option<Picture>>,
}

/// Whether a dither drops the pixel at (x, y). RM2k draws a translucent
/// page at 160 of 255, and `five_of_eight` is the closest; the others are
/// there to compare on a real TV.
pub fn drops(pattern: &str, x: usize, y: usize) -> bool {
    match pattern {
        "checkerboard" => (x + y) % 2 == 1,
        "columns" => x % 2 == 1,
        "rows" => y % 2 == 1,
        "three_of_four" => x % 2 == 1 && y % 2 == 1,
        _ => matches!((y % 2) * 4 + x % 4, 1 | 4 | 7),
    }
}

/// `(base, (map, x, y))` of a baked name, or `None`.
fn baked_parts(name: &str) -> Option<(&str, (i32, i64, i64))> {
    let mark = format!("{BAKED_SUFFIX}:");
    let at = name.find(&mark)?;
    let mut rest = name[at + mark.len()..].split(':').map(|n| n.parse::<i64>().ok());
    let (m, x, y) = (rest.next()??, rest.next()??, rest.next()??);
    Some((&name[..at], (m as i32, x, y)))
}

impl<'a> Drawer<'a> {
    pub fn new(game: &'a Game, dither: &str) -> Self {
        Drawer {
            game,
            dither: dither.to_string(),
            sheets: Sheets::new(),
            lower: HashMap::new(),
        }
    }

    /// Every sheet drawn so far.
    pub fn sheets(&self) -> &Sheets {
        &self.sheets
    }

    /// Draws `name` if it was not drawn yet; `None` if its picture is
    /// missing.
    pub fn draw(&mut self, name: &str) -> Result<Option<Picture>> {
        if let Some(done) = self.sheets.get(name) {
            return Ok(done.clone());
        }
        let done = if let Some(base) = name.strip_suffix(COPY_SUFFIX) {
            self.draw(base)?
        } else if let Some(base) = name.strip_suffix(DITHER_SUFFIX) {
            self.draw(base)?.map(|mut sheet| {
                for y in 0..sheet.height {
                    for x in 0..sheet.width {
                        if drops(&self.dither, x, y) {
                            let at = (y * sheet.width + x) * 4;
                            sheet.rgba[at..at + 4].fill(0);
                        }
                    }
                }
                sheet
            })
        } else if let Some((base, (map, x, y))) = baked_parts(name) {
            match (self.source(base)?, self.lower_layer(map)?) {
                (Some(sheet), Some(behind)) => Some(translucent(&sheet, &behind, x, y)),
                // Nothing to bake it against: the sheet as it is.
                _ => self.draw(unbaked(name))?,
            }
        } else {
            self.source(name)?
        };
        self.sheets.insert(name.to_string(), done.clone());
        Ok(done)
    }

    /// A CharSet's sheet, or a tile's.
    fn source(&self, name: &str) -> Result<Option<Picture>> {
        if let Some(rest) = name.strip_prefix(TILE_PREFIX) {
            let Some((chipset, index)) = rest.rsplit_once(':') else {
                return Ok(None);
            };
            let Ok(index) = index.parse::<i32>() else {
                return Ok(None);
            };
            return Ok(match self.game.resource("ChipSet", chipset) {
                Some(path) => Some(tile_sheet(&picture::read_rm2k(&path)?, index)),
                None => None,
            });
        }
        Ok(match self.game.resource("CharSet", name) {
            Some(path) => Some(picture::read_rm2k(&path)?),
            None => None,
        })
    }

    /// A map's lower layer as the game draws it, unbaked: what is behind a
    /// translucent event of that map.
    fn lower_layer(&mut self, map: i32) -> Result<Option<Picture>> {
        if let Some(done) = self.lower.get(&map) {
            return Ok(done.clone());
        }
        let request = LayersRequest { map, baked: Vec::new() };
        let done = match draw(self.game, &request) {
            Ok(Drawn { layers, .. }) => Some(layers.lower),
            Err(_) => None,
        };
        self.lower.insert(map, done.clone());
        Ok(done)
    }
}
