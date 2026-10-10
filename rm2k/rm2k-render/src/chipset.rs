//! A ChipSet expanded into an atlas of tiles ready to draw.
//!
//! An RM2k ChipSet is a 480x256 picture whose left half is not tiles but
//! **autotiles**: edge pieces the engine combines according to the
//! neighbours. The editor stores in the map the id of the combination
//! already chosen, so drawing a map is indexing a table of every combination
//! there can be —1419 of them, in a 32x45-tile atlas—, and that table is
//! built here once per ChipSet.
//!
//! It is a port of EasyRPG Tools' `lmu2png/src/chipset.cpp`, by way of the
//! Python this replaced. The offsets are theirs: the original says it was
//! easier to write them down than to work out the rule behind them, and
//! there is no reason to doubt it. Changing one changes pixels.

use crate::picture::Picture;

use rm2k_rules::chipset as rules;

// The ChipSet's geometry is RM2k's and lives in `rm2k-rules`; it is
// restated here only in the types the drawing computes in.

/// A tile is 16x16 pixels, and an autotile piece a quarter of one.
pub const TILE: i64 = rules::TILE as i64;
const HALF: i64 = TILE / 2;

pub const ATLAS_COLUMNS: i64 = 32;
pub const ATLAS_ROWS: i64 = 45;

/// What a ChipSet measures. A smaller one is drawn as if padded with
/// transparency to this; a bigger one is cut.
pub const CHIPSET_WIDTH: usize = rules::CHIPSET_WIDTH as usize;
pub const CHIPSET_HEIGHT: usize = rules::CHIPSET_HEIGHT as usize;

/// Where each family of tile ids starts: see `rm2k_rules::chipset`.
pub const ANIMATED: i64 = rules::ANIMATED as i64;
pub const TERRAIN: i64 = rules::TERRAIN as i64;
pub const LOWER: i64 = rules::LOWER as i64;
pub const UPPER: i64 = rules::UPPER as i64;

/// Where, in the ChipSet, the 48x64 block of terrain autotile `n` starts.
fn terrain_origin(n: i64) -> (i64, i64) {
    let (x, y) = rules::terrain_origin(n as i32);
    (x as i64, y as i64)
}

/// Where plain tile `i` starts.
fn common_origin(i: i64) -> (i64, i64) {
    let (x, y) = rules::common_origin(i as i32);
    (x as i64, y as i64)
}

/// Every tile a ChipSet can draw, already combined.
pub struct Atlas {
    base: Picture,
    pub picture: Picture,
}

impl Atlas {
    /// Expands a ChipSet, already read with its colour key applied.
    pub fn new(chipset: &Picture) -> Self {
        let mut base = Picture::transparent(CHIPSET_WIDTH, CHIPSET_HEIGHT);
        base.paste(chipset);
        let picture = Picture::transparent(
            (ATLAS_COLUMNS * TILE) as usize,
            (ATLAS_ROWS * TILE) as usize,
        );
        let mut atlas = Atlas { base, picture };

        let mut tile = 0;
        // The waters A, B and C: 3 frames of 47 edge combinations each.
        for kind in 0..3 {
            let border = i64::from(kind == 1);
            let water = if kind == 2 { 3 } else { 0 };
            for frame in 0..3 {
                for comb in 0..47 {
                    atlas.water_tile(tile, frame, border, water, comb);
                    tile += 1;
                }
            }
        }
        // The depth edges of the water, 2 levels of 48.
        for depth in [1, 3] {
            for i in 0..48 {
                atlas.depth_tile(tile, i, depth);
                tile += 1;
            }
        }
        // The animated tiles: 3 groups of 4 frames, copied as they are.
        for j in 0..3 {
            for i in 0..4 {
                atlas.full(tile, 48 + j * TILE, 64 + i * TILE, 0, 0);
                tile += 1;
            }
        }
        // The terrains: 12 autotiles of 50 combinations.
        for terrain in 0..12 {
            for comb in 0..50 {
                atlas.terrain_tile(tile, terrain, comb);
                tile += 1;
            }
        }
        // The plain tiles: the 3 pages of 96, not combined.
        for i in 0..288 {
            let (x, y) = common_origin(i);
            atlas.full(tile, x, y, 0, 0);
            tile += 1;
        }
        atlas
    }

    /// Draws the tile the map layer names with `id` at cell `(x, y)` of
    /// `dst`.
    ///
    /// The two steps are the ChipSet's two animations, which run at their own
    /// pace over different families: `water_step` —0, 1 or 2— picks the
    /// drawing of the water autotiles, and `animated_step` —0 to 3— that of
    /// the animated tiles. Which one is due when is not decided here.
    pub fn draw_tile(
        &self,
        dst: &mut Picture,
        x: i64,
        y: i64,
        id: i64,
        water_step: i64,
        animated_step: i64,
    ) {
        let index = cell(id, water_step, animated_step);
        dst.blit(
            x * TILE,
            y * TILE,
            &self.picture,
            (index & 0x1F) * TILE,
            (index >> 5) * TILE,
            TILE,
            TILE,
        );
    }

    // --- drawing on the atlas -----------------------------------------

    #[allow(clippy::too_many_arguments)]
    fn draw(&mut self, t: i64, sx: i64, sy: i64, w: i64, h: i64, dx: i64, dy: i64) {
        let x = (t % ATLAS_COLUMNS) * TILE + dx;
        let y = (t / ATLAS_COLUMNS) * TILE + dy;
        self.picture.blit(x, y, &self.base, sx, sy, w, h);
    }

    fn full(&mut self, t: i64, sx: i64, sy: i64, dx: i64, dy: i64) {
        self.draw(t, sx, sy, TILE, TILE, dx, dy);
    }

    fn quarter(&mut self, t: i64, sx: i64, sy: i64, dx: i64, dy: i64) {
        self.draw(t, sx, sy, HALF, HALF, dx, dy);
    }

    fn wide(&mut self, t: i64, sx: i64, sy: i64, dx: i64, dy: i64) {
        self.draw(t, sx, sy, TILE, HALF, dx, dy);
    }

    fn tall(&mut self, t: i64, sx: i64, sy: i64, dx: i64, dy: i64) {
        self.draw(t, sx, sy, HALF, TILE, dx, dy);
    }

    /// The 4 inner corners, one per bit of the combination.
    fn edges(&mut self, t: i64, sx: i64, sy: i64, comb: i64) {
        if comb & 1 != 0 {
            self.quarter(t, sx, sy, 0, 0); // top left
        }
        if comb & 2 != 0 {
            self.quarter(t, sx + HALF, sy, HALF, 0); // top right
        }
        if comb & 4 != 0 {
            self.quarter(t, sx + HALF, sy + HALF, HALF, HALF); // bottom right
        }
        if comb & 8 != 0 {
            self.quarter(t, sx, sy + HALF, 0, HALF); // bottom left
        }
    }

    // --- the autotiles --------------------------------------------------

    fn water_tile(&mut self, t: i64, frame: i64, border: i64, water: i64, comb: i64) {
        let sx = frame * 16 + border * 48;
        let comb = comb & 0x3F;

        // The background: the plain water of this frame.
        self.full(t, frame * 16, 64 + water * 16, 0, 0);

        if comb & 0x20 != 0 {
            if comb > 0x29 {
                // Several edges at once.
                match comb {
                    0x2A => {
                        self.wide(t, sx, 0, 0, 0);
                        self.wide(t, sx, 24, 0, HALF);
                    }
                    0x2B => {
                        self.tall(t, sx, 0, 0, 0);
                        self.tall(t, sx + HALF, 32, HALF, 0);
                    }
                    0x2C => {
                        self.wide(t, sx, 8, 0, HALF);
                        self.wide(t, sx, 16, 0, 0);
                    }
                    0x2D => {
                        self.tall(t, sx + HALF, 0, HALF, 0);
                        self.tall(t, sx, 32, 0, 0);
                    }
                    0x2E => self.full(t, sx, 0, 0, 0),
                    _ => {}
                }
            } else {
                // A wall and inner corners.
                match (comb >> 1) & 0x07 {
                    0 => self.full(t, sx, if comb & 1 != 0 { 32 } else { 16 }, 0, 0),
                    1 => {
                        self.quarter(t, sx, 0, 0, 0);
                        self.quarter(t, sx, 24, 0, HALF);
                        self.quarter(t, sx + HALF, 32, HALF, 0);
                        if comb & 1 != 0 {
                            self.quarter(t, sx + HALF, 48 + HALF, HALF, HALF);
                        }
                    }
                    2 => {
                        self.quarter(t, sx + HALF, 0, HALF, 0);
                        self.quarter(t, sx + HALF, 24, HALF, HALF);
                        self.quarter(t, sx, 32, 0, 0);
                        if comb & 1 != 0 {
                            self.quarter(t, sx, 48 + HALF, 0, HALF);
                        }
                    }
                    3 => {
                        self.quarter(t, sx + HALF, HALF, HALF, HALF);
                        self.quarter(t, sx + HALF, TILE, HALF, 0);
                        self.quarter(t, sx, 40, 0, HALF);
                        if comb & 1 != 0 {
                            self.quarter(t, sx, 48, 0, 0);
                        }
                    }
                    4 => {
                        self.quarter(t, sx, HALF, 0, HALF);
                        self.quarter(t, sx, TILE, 0, 0);
                        self.quarter(t, sx + HALF, 40, HALF, HALF);
                        if comb & 1 != 0 {
                            self.quarter(t, sx + HALF, 48, HALF, 0);
                        }
                    }
                    _ => {}
                }
            }
        } else if comb & 0x10 != 0 {
            // One wall, and the corners on the other side.
            match (comb >> 2) & 0x03 {
                0 => {
                    // left wall
                    self.tall(t, sx, 16, 0, 0);
                    if comb & 1 != 0 {
                        self.quarter(t, sx + HALF, 48, HALF, 0);
                    }
                    if comb & 2 != 0 {
                        self.quarter(t, sx + HALF, 48 + HALF, HALF, HALF);
                    }
                }
                1 => {
                    // top wall
                    self.wide(t, sx, 32, 0, 0);
                    if comb & 1 != 0 {
                        self.quarter(t, sx + HALF, 48 + HALF, HALF, HALF);
                    }
                    if comb & 2 != 0 {
                        self.quarter(t, sx, 48 + HALF, 0, HALF);
                    }
                }
                2 => {
                    // right wall
                    self.tall(t, sx + HALF, 16, HALF, 0);
                    if comb & 1 != 0 {
                        self.quarter(t, sx, 48 + HALF, 0, HALF);
                    }
                    if comb & 2 != 0 {
                        self.quarter(t, sx, 48, 0, 0);
                    }
                }
                _ => {
                    // bottom wall
                    self.wide(t, sx, 32 + HALF, 0, HALF);
                    if comb & 1 != 0 {
                        self.quarter(t, sx, 48, 0, 0);
                    }
                    if comb & 2 != 0 {
                        self.quarter(t, sx + HALF, 48, HALF, 0);
                    }
                }
            }
        } else {
            self.edges(t, sx, 48, comb);
        }
    }

    fn depth_tile(&mut self, t: i64, number: i64, depth: i64) {
        let frame = number / 16;
        self.edges(t, frame * 16, 64 + depth * 16, number % 16);
    }

    fn terrain_tile(&mut self, t: i64, terrain: i64, comb: i64) {
        let (sx, sy) = terrain_origin(terrain);

        // The background: the terrain's plain fill.
        self.full(t, sx + 16, sy + 32, 0, 0);

        if comb & 0x20 != 0 {
            if comb > 0x29 {
                match comb {
                    0x2A => {
                        self.tall(t, sx, sy + 16, 0, 0);
                        self.tall(t, sx + 40, sy + 16, HALF, 0);
                    }
                    0x2B => {
                        self.wide(t, sx, sy + 16, 0, 0);
                        self.wide(t, sx, sy + 56, 0, HALF);
                    }
                    0x2C => {
                        self.tall(t, sx, sy + 48, 0, 0);
                        self.tall(t, sx + 40, sy + 48, HALF, 0);
                    }
                    0x2D => {
                        self.wide(t, sx + 32, sy + 16, 0, 0);
                        self.wide(t, sx + 32, sy + 56, 0, HALF);
                    }
                    0x2E => {
                        self.quarter(t, sx, sy + 16, 0, 0);
                        self.quarter(t, sx + 40, sy + 16, HALF, 0);
                        self.quarter(t, sx, sy + 56, 0, HALF);
                        self.quarter(t, sx + 40, sy + 56, HALF, HALF);
                    }
                    0x31 => self.full(t, sx, sy, 0, 0),
                    _ => {}
                }
            } else {
                match (comb >> 1) & 0x07 {
                    0 => {
                        if comb & 1 != 0 {
                            self.wide(t, sx + 16, sy + 16, 0, 0);
                            self.wide(t, sx + 16, sy + 56, 0, HALF);
                        } else {
                            self.tall(t, sx, sy + 32, 0, 0);
                            self.tall(t, sx + 40, sy + 32, HALF, 0);
                        }
                    }
                    1 => {
                        self.full(t, sx, sy + 16, 0, 0);
                        if comb & 1 != 0 {
                            self.quarter(t, sx + 40, sy + HALF, HALF, HALF);
                        }
                    }
                    2 => {
                        self.full(t, sx + 32, sy + 16, 0, 0);
                        if comb & 1 != 0 {
                            self.quarter(t, sx + 32, sy + HALF, 0, HALF);
                        }
                    }
                    3 => {
                        self.full(t, sx + 32, sy + 48, 0, 0);
                        if comb & 1 != 0 {
                            self.quarter(t, sx + 32, sy, 0, 0);
                        }
                    }
                    4 => {
                        self.full(t, sx, sy + 48, 0, 0);
                        if comb & 1 != 0 {
                            self.quarter(t, sx + 40, sy, HALF, 0);
                        }
                    }
                    _ => {}
                }
            }
        } else if comb & 0x10 != 0 {
            match (comb >> 2) & 0x03 {
                0 => {
                    // left wall
                    self.full(t, sx, sy + 32, 0, 0);
                    if comb & 1 != 0 {
                        self.quarter(t, sx + 40, sy, HALF, 0);
                    }
                    if comb & 2 != 0 {
                        self.quarter(t, sx + 40, sy + HALF, HALF, HALF);
                    }
                }
                1 => {
                    // top wall
                    self.full(t, sx + 16, sy + 16, 0, 0);
                    if comb & 1 != 0 {
                        self.quarter(t, sx + 40, sy + HALF, HALF, HALF);
                    }
                    if comb & 2 != 0 {
                        self.quarter(t, sx + 32, sy + HALF, 0, HALF);
                    }
                }
                2 => {
                    // right wall
                    self.full(t, sx + 32, sy + 32, 0, 0);
                    if comb & 1 != 0 {
                        self.quarter(t, sx + 32, sy + HALF, 0, HALF);
                    }
                    if comb & 2 != 0 {
                        self.quarter(t, sx + 32, sy, 0, 0);
                    }
                }
                _ => {
                    // bottom wall
                    self.full(t, sx + 16, sy + 48, 0, 0);
                    if comb & 1 != 0 {
                        self.quarter(t, sx + 32, sy, 0, 0);
                    }
                    if comb & 2 != 0 {
                        self.quarter(t, sx + 40, sy, HALF, 0);
                    }
                }
            }
        } else {
            self.edges(t, sx + 32, sy, comb);
        }
    }
}

/// The atlas cell a map tile id draws, at those animation steps.
///
/// The water's `id % 50` can reach 49 and the atlas only has 47 combinations
/// per frame: those land on the next frame's cells, as they always did. A
/// cell past the end of the atlas draws nothing.
pub fn cell(id: i64, water_step: i64, animated_step: i64) -> i64 {
    if id >= UPPER {
        id - UPPER + 0x04FB
    } else if id >= LOWER {
        id - LOWER + 0x046B
    } else if id >= TERRAIN {
        id - TERRAIN + 0x0213
    } else if id >= ANIMATED {
        0x0207 + (((id - ANIMATED) / 50) << 2) + animated_step % 4
    } else {
        (id / 50 / 20) * 141 + id % 50 + (water_step % 3) * 47
    }
}
