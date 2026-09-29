//! A map's two tile layers, drawn the way RM2k stacks them around the hero.
//!
//! What goes behind the hero and what goes in front is not a property of the
//! layer a tile sits on but of the ChipSet's passability: a lower-layer tile
//! with the "above" bits, or an upper-layer one with the star bit, is drawn
//! over the hero. So a map comes out as two pictures, `lower` —opaque, black
//! where nothing is drawn— and `upper`, transparent except for those tiles.

use crate::chipset::{Atlas, ANIMATED, TERRAIN, TILE};
use crate::fail::{Bad, Result};
use crate::picture::Picture;
use rm2k_rules::chipset::passability_table;
use rm2k_rules::passability::{lower_above, upper_above};

/// What of a map reaches the drawing, and nothing else.
#[derive(Clone, Debug)]
pub struct Map {
    pub width: usize,
    pub height: usize,
    /// One tile id per cell, rows top to bottom.
    pub lower_layer: Vec<i64>,
    pub upper_layer: Vec<i64>,
    /// The ChipSet's passability, one byte per tile: 162 for the lower
    /// layer's families and plain tiles, 144 for the upper layer's.
    pub passable_lower: Vec<u8>,
    pub passable_upper: Vec<u8>,
}

/// The families of the ChipSet's animation, and how many drawings each has.
/// Drawing 0 is the one `lower` already shows.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Family {
    Water,
    Animated,
}

impl Family {
    pub const ALL: [Family; 2] = [Family::Water, Family::Animated];

    pub fn drawings(self) -> usize {
        match self {
            Family::Water => 3,
            Family::Animated => 4,
        }
    }

    pub fn name(self) -> &'static str {
        match self {
            Family::Water => "water",
            Family::Animated => "animated",
        }
    }

    /// The two steps that show drawing `d` of this family, and drawing 0 of
    /// the other.
    fn steps(self, d: usize) -> (i64, i64) {
        match self {
            Family::Water => (d as i64, 0),
            Family::Animated => (0, d as i64),
        }
    }
}

/// Everything drawn for a map.
pub struct Layers {
    pub lower: Picture,
    pub upper: Picture,
    /// Per family the map uses, its drawings other than 0, in order. Only
    /// the lower picture: `upper` is drawn at step 0 and nothing here draws
    /// it at any other, so an animated tile with the "above" bits stays on
    /// its first drawing.
    pub variants: Vec<(Family, Vec<Picture>)>,
}

impl Map {
    /// Checks what the drawing is going to index before it indexes it, so a
    /// broken map is an answer and not a panic.
    pub fn check(&self) -> Result<()> {
        let cells = self.width * self.height;
        for (name, layer) in [("lower", &self.lower_layer), ("upper", &self.upper_layer)] {
            if layer.len() != cells {
                return Err(Bad::answer(format!(
                    "the {name} layer has {} tiles for a {}x{} map",
                    layer.len(),
                    self.width,
                    self.height
                )));
            }
            if let Some(id) = layer.iter().find(|id| !(0..65536).contains(*id)) {
                return Err(Bad::answer(format!(
                    "the {name} layer has tile id {id}, and they go from 0 to 65535"
                )));
            }
        }
        if self.passable_lower.len() < 162 || self.passable_upper.len() < 144 {
            return Err(Bad::answer(format!(
                "the ChipSet's passability has {} lower and {} upper entries, and it takes \
                 162 and 144",
                self.passable_lower.len(),
                self.passable_upper.len()
            )));
        }
        Ok(())
    }

    /// The passability of every tile id: `rm2k_rules::chipset::passability_table`.
    pub fn passability(&self) -> Vec<u8> {
        passability_table(&self.passable_lower, &self.passable_upper)
    }

    /// The families the map can animate: a map without water or animated
    /// tiles pays for no other drawing.
    pub fn families(&self) -> Vec<Family> {
        let tiles = || self.lower_layer.iter().chain(&self.upper_layer);
        let mut families = Vec::new();
        if tiles().any(|&id| id < ANIMATED) {
            families.push(Family::Water);
        }
        if tiles().any(|&id| (ANIMATED..TERRAIN).contains(&id)) {
            families.push(Family::Animated);
        }
        families
    }

    /// Draws the tiles of both layers that belong on one side of the hero.
    fn draw(&self, dst: &mut Picture, atlas: &Atlas, flags: &[u8], above: bool, steps: (i64, i64)) {
        for y in 0..self.height {
            let row = y * self.width;
            for x in 0..self.width {
                let (xi, yi) = (x as i64, y as i64);
                let lower = self.lower_layer[row + x];
                if lower_above(flags, lower as i32) == above {
                    atlas.draw_tile(dst, xi, yi, lower, steps.0, steps.1);
                }
                let upper = self.upper_layer[row + x];
                if upper_above(flags, upper as i32) == above {
                    atlas.draw_tile(dst, xi, yi, upper, steps.0, steps.1);
                }
            }
        }
    }

    fn size(&self) -> (usize, usize) {
        (self.width * TILE as usize, self.height * TILE as usize)
    }

    /// The picture behind the hero, at those animation steps.
    pub fn lower(&self, atlas: &Atlas, flags: &[u8], steps: (i64, i64)) -> Picture {
        let (w, h) = self.size();
        let mut picture = Picture::filled(w, h, [0, 0, 0, 255]);
        self.draw(&mut picture, atlas, flags, false, steps);
        picture
    }

    /// The picture in front of the hero.
    pub fn upper(&self, atlas: &Atlas, flags: &[u8]) -> Picture {
        let (w, h) = self.size();
        let mut picture = Picture::transparent(w, h);
        self.draw(&mut picture, atlas, flags, true, (0, 0));
        picture
    }

    /// Both layers, and the other drawings of every family the map uses.
    pub fn render(&self, atlas: &Atlas) -> Result<Layers> {
        self.check()?;
        let flags = self.passability();
        let variants = self
            .families()
            .into_iter()
            .map(|family| {
                let drawings = (1..family.drawings())
                    .map(|d| self.lower(atlas, &flags, family.steps(d)))
                    .collect();
                (family, drawings)
            })
            .collect();
        Ok(Layers {
            lower: self.lower(atlas, &flags, (0, 0)),
            upper: self.upper(atlas, &flags),
            variants,
        })
    }
}
