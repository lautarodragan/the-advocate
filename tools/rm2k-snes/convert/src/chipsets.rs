//! The image of a ChipSet the project adds: its recipe applied to the
//! original PNG.
//!
//! **The ChipSet's image is not versioned: it is built.** The game's art is
//! not the project's to redistribute, so the patch keeps the *recipe*
//! —which block is copied where— and it is applied here on the original
//! PNG, leaving the result in `parches-manual/ChipSet/` of the project's
//! build, which goes first in the resource search: `wally` finds it there.
//!
//! The recipe has five operations. Two copy from inside the ChipSet itself
//! —`bloques_bajos` and `tiles_altos`—, two **bring pixels from outside**
//! —`desde_charset` puts a CharSet pose into two upper tiles, so an NPC
//! that only stands there becomes map; `desde_imagen` puts in a PNG that
//! is neither, scaled and cut into 16x16 cells—, and `podar` **erases what
//! the map does not use**: a fork's ChipSet is private to its map, and
//! what is gained is **palette indices**, which the PNG has 256 of.
//!
//! Both PNGs are indexed and **their indices do not mean the same thing**,
//! so what comes from outside is copied by colour: a colour that is not
//! there takes an index the ChipSet does not use.

use crate::fail::{io, Result, Stop};
use crate::game::Game;
use rm2k_rules::chipset::{common_origin, terrain_origin, TILE};
use serde_json::Value;
use std::collections::{BTreeSet, HashMap};
use std::path::{Path, PathBuf};

/// The commands that pick a tile **at run time**: with one of these the
/// map's layers no longer say what is drawn, and pruning cannot know what
/// to keep. It stops instead of guessing.
const TILE_PICKING_COMMANDS: [(i32, &str); 2] = [(11710, "ChangeMapTileset"), (11750, "TileSubstitution")];

/// The water and the animated tiles share this rectangle of the ChipSet.
const WATER_BOX: (usize, usize, usize, usize) = (0, 0, 96, 128);

/// An indexed picture: its indices, row by row, and its palette.
#[derive(Clone)]
struct Indexed {
    width: usize,
    height: usize,
    pixels: Vec<u8>,
    palette: Vec<[u8; 3]>,
}

impl Indexed {
    fn blank(width: usize, height: usize) -> Indexed {
        Indexed { width, height, pixels: vec![0; width * height], palette: Vec::new() }
    }

    fn read(path: &Path) -> Result<Indexed> {
        let file = std::fs::File::open(path).map_err(|e| io(path, e))?;
        let mut decoder = png::Decoder::new(std::io::BufReader::new(file));
        decoder.set_transformations(png::Transformations::IDENTITY);
        let mut reader = decoder.read_info().map_err(|e| Stop::new(format!("{}: {e}", path.display())))?;
        let mut buffer = vec![0; reader.output_buffer_size()];
        let frame = reader.next_frame(&mut buffer).map_err(|e| Stop::new(format!("{}: {e}", path.display())))?;
        if frame.color_type != png::ColorType::Indexed {
            crate::stop!("{}: not an indexed PNG", path.display());
        }
        let depth = frame.bit_depth as usize;
        let (width, height) = (frame.width as usize, frame.height as usize);
        let mut pixels = Vec::with_capacity(width * height);
        for y in 0..height {
            let line = &buffer[y * frame.line_size..(y + 1) * frame.line_size];
            for x in 0..width {
                let per_byte = 8 / depth;
                let byte = line[x / per_byte];
                let shift = 8 - depth * (x % per_byte + 1);
                pixels.push((byte >> shift) & ((1u16 << depth) - 1) as u8);
            }
        }
        let raw = reader.info().palette.as_deref().unwrap_or(&[]).to_vec();
        let palette = raw.chunks(3).filter(|c| c.len() == 3).map(|c| [c[0], c[1], c[2]]).collect();
        Ok(Indexed { width, height, pixels, palette })
    }

    fn write(&self, path: &Path) -> Result<()> {
        let file = std::fs::File::create(path).map_err(|e| io(path, e))?;
        let mut encoder = png::Encoder::new(std::io::BufWriter::new(file), self.width as u32, self.height as u32);
        encoder.set_color(png::ColorType::Indexed);
        encoder.set_depth(png::BitDepth::Eight);
        encoder.set_palette(self.palette.iter().flatten().copied().collect::<Vec<u8>>());
        let mut writer = encoder.write_header().map_err(|e| Stop::new(format!("{}: {e}", path.display())))?;
        writer
            .write_image_data(&self.pixels)
            .map_err(|e| Stop::new(format!("{}: {e}", path.display())))
    }

    fn get(&self, x: usize, y: usize) -> u8 {
        self.pixels[y * self.width + x]
    }

    fn crop(&self, (x0, y0, x1, y1): (usize, usize, usize, usize)) -> Indexed {
        let mut out = Indexed::blank(x1 - x0, y1 - y0);
        for y in y0..y1 {
            for x in x0..x1 {
                out.pixels[(y - y0) * out.width + (x - x0)] =
                    if x < self.width && y < self.height { self.get(x, y) } else { 0 };
            }
        }
        out
    }

    fn paste(&mut self, other: &Indexed, (x0, y0): (usize, usize)) {
        for y in 0..other.height {
            for x in 0..other.width {
                if x0 + x < self.width && y0 + y < self.height {
                    self.pixels[(y0 + y) * self.width + x0 + x] = other.get(x, y);
                }
            }
        }
    }
}

fn terrain_box(n: i32) -> (usize, usize, usize, usize) {
    let (x, y) = terrain_origin(n);
    (x as usize, y as usize, x as usize + 48, y as usize + 64)
}

fn common_box(i: i32) -> (usize, usize, usize, usize) {
    let (x, y) = common_origin(i);
    let t = TILE as usize;
    (x as usize, y as usize, x as usize + t, y as usize + t)
}

fn corner(b: (usize, usize, usize, usize)) -> (usize, usize) {
    (b.0, b.1)
}

/// Which parts of the ChipSet the map draws: water, autotiles and common
/// slots. It comes from the **already forked** map, so a slot the fork
/// starts drawing is respected without anyone noting it down. And an event
/// without a CharSet is drawn with a tile from the upper page, which does
/// not appear on any layer: pruning without counting them once lost a
/// slot, and the byte-for-byte comparison caught it, not a test.
fn what_it_draws(game: &Game, map_id: i32) -> Result<(bool, BTreeSet<i32>, BTreeSet<i32>)> {
    let map = game.map(map_id)?;
    let mut water = false;
    let (mut terrains, mut commons) = (BTreeSet::new(), BTreeSet::new());
    for layer in [&map.lower_layer, &map.upper_layer] {
        for &tile in layer.iter() {
            let tile = tile as i32;
            if tile < 4000 {
                water = true;
            } else if tile < 5000 {
                terrains.insert((tile - 4000) / 50);
            } else if tile < 10000 {
                commons.insert(tile - 5000);
            } else {
                commons.insert(144 + tile - 10000);
            }
        }
    }
    for event in &map.events {
        for page in &event.pages {
            if page.dump_name.is_empty() {
                commons.insert(144 + page.character_index);
            }
            for command in &page.commands {
                if let Some((_, name)) = TILE_PICKING_COMMANDS.iter().find(|(c, _)| *c == command.code) {
                    crate::stop!(
                        "map {map_id} uses {name}, which picks a tile at run time: with that the \
                         layers do not say what is drawn and pruning the ChipSet would erase art \
                         the map does use"
                    );
                }
            }
        }
    }
    Ok((water, terrains, commons))
}

/// Erases from the ChipSet everything that map does not draw. It cannot
/// change what is seen —it erases tiles the map does not name—.
fn prune(game: &Game, image: &mut Indexed, map_id: i32) -> Result<()> {
    let (water, terrains, commons) = what_it_draws(game, map_id)?;
    if !water {
        image.paste(&Indexed::blank(WATER_BOX.2, WATER_BOX.3), (WATER_BOX.0, WATER_BOX.1));
    }
    for n in 0..12 {
        if !terrains.contains(&n) {
            image.paste(&Indexed::blank(48, 64), corner(terrain_box(n)));
        }
    }
    for i in 0..288 {
        if !commons.contains(&i) {
            image.paste(&Indexed::blank(16, 16), corner(common_box(i)));
        }
    }
    Ok(())
}

/// The ChipSet's palette while colours from outside are added to it.
/// Index 0 is left out of the search **at both ends**: it is the colour
/// key, and a colour that happens to equal the ChipSet's index 0 has to
/// take an index of its own or the drawing would come out with a hole.
struct Palette {
    colors: Vec<[u8; 3]>,
    where_: HashMap<[u8; 3], u8>,
    free: Vec<u8>,
}

impl Palette {
    fn new(image: &Indexed) -> Palette {
        let mut colors = image.palette.clone();
        while colors.len() < 256 {
            colors.push([0, 0, 0]);
        }
        let used: BTreeSet<u8> = image.pixels.iter().copied().collect();
        let mut where_ = HashMap::new();
        for &index in &used {
            if index != 0 {
                where_.entry(colors[index as usize]).or_insert(index);
            }
        }
        let free = (1..=255u8).filter(|i| !used.contains(i)).collect();
        Palette { colors, where_, free }
    }

    fn index(&mut self, color: [u8; 3]) -> Result<u8> {
        if let Some(&i) = self.where_.get(&color) {
            return Ok(i);
        }
        if self.free.is_empty() {
            crate::stop!(
                "the ChipSet ran out of palette indices: all 256 are already used and the \
                 incoming drawing brings colors it does not have. If the ChipSet is not being \
                 pruned, `podar` is what frees the indices the map does not use"
            );
        }
        let i = self.free.remove(0);
        self.where_.insert(color, i);
        self.colors[i as usize] = color;
        Ok(i)
    }
}

/// The colour rounded to the 15 bits the console really shows: it loses
/// nothing the cartridge could draw, and it is what makes the drawing fit.
fn to_15_bits(c: [u8; 3]) -> [u8; 3] {
    [(c[0] >> 3) << 3, (c[1] >> 3) << 3, (c[2] >> 3) << 3]
}

fn int(v: &Value) -> i64 {
    v.as_i64().unwrap_or(0)
}

/// Builds the PNG of a ChipSet the project adds and returns its path.
/// `find(folder, name)` finds the originals.
fn build(game: &Game, data: &Value, out_dir: &Path, find: &dyn Fn(&str, &str) -> Option<PathBuf>) -> Result<PathBuf> {
    let recipe = &data["imagen"];
    let number = int(&data["chipset"]["id"]);
    let base = recipe["base"].as_str().unwrap_or("");
    let source = find("ChipSet", base).ok_or_else(|| {
        Stop::new(format!("ChipSet {}, which {number} comes from, is missing", crate::text::repr(base)))
    })?;
    let mut image = Indexed::read(&source)?;
    // The pruning first, because it frees palette indices the operations
    // below need, and because it reads the **forked** map.
    if let Some(map) = recipe.get("podar") {
        prune(game, &mut image, int(map) as i32)?;
    }
    for pair in recipe["bloques_bajos"].as_array().cloned().unwrap_or_default() {
        let block = image.crop(terrain_box(int(&pair[0]) as i32));
        image.paste(&block, corner(terrain_box(int(&pair[1]) as i32)));
    }
    for pair in recipe["tiles_altos"].as_array().cloned().unwrap_or_default() {
        // Upper tile `u` is common tile 144 + u.
        let tile = image.crop(common_box(144 + int(&pair[0]) as i32));
        image.paste(&tile, corner(common_box(144 + int(&pair[1]) as i32)));
    }
    // The slots `desde_imagen` overwrites are emptied **before** looking at
    // the palette, or their colours would keep the indices the new drawing
    // needs.
    let from_image = recipe.get("desde_imagen").filter(|v| !v.is_null());
    if let Some(item) = from_image {
        for entry in item["celdas"].as_array().cloned().unwrap_or_default() {
            if entry.as_array().map_or(0, Vec::len) <= 3 {
                image.paste(&Indexed::blank(16, 16), corner(common_box(144 + int(&entry[2]) as i32)));
            }
        }
    }
    let from_charset = recipe.get("desde_charset").and_then(Value::as_array).filter(|a| !a.is_empty()).cloned();
    // The two operations that bring pixels from outside share **a single**
    // palette.
    let mut palette = (from_charset.is_some() || from_image.is_some()).then(|| Palette::new(&image));
    if let Some(items) = &from_charset {
        let palette = palette.as_mut().unwrap();
        for item in items {
            let name = item["charset"].as_str().unwrap_or("");
            let sheet = find("CharSet", name).ok_or_else(|| {
                Stop::new(format!("CharSet {}, which ChipSet {number} bakes, is missing", crate::text::repr(name)))
            })?;
            let source = Indexed::read(&sheet)?;
            // A pose's 24x32 frame: a CharSet is eight characters in 4x2,
            // each with three patterns by four directions.
            let character = int(&item["personaje"]) as usize;
            let x = (character % 4) * 72 + int(&item["patron"]) as usize * 24;
            let y = (character / 4) * 128 + int(&item["direccion"]) as usize * 32;
            let pose = source.crop((x, y, x + 24, y + 32));
            // The sprite is drawn at `(x*16 - 4, y*16 - 16)`, so its
            // columns 4 to 19 land on the cell and its upper half on the
            // cell above.
            let column = (-rm2k_rules::charset::OFFSET_X) as usize;
            for (half, slot) in [("cabeza", &item["cabeza"]), ("cuerpo", &item["cuerpo"])] {
                let top = if half == "cabeza" { 0 } else { 16 };
                let mut tile = Indexed::blank(16, 16);
                for row in top..top + 16 {
                    for x in column..column + 16 {
                        let index = pose.get(x, row);
                        tile.pixels[(row - top) * 16 + (x - column)] = if index == 0 {
                            0
                        } else {
                            palette.index(source.palette[index as usize])?
                        };
                    }
                }
                image.paste(&tile, corner(common_box(144 + int(slot) as i32)));
            }
        }
    }
    if let Some(item) = from_image {
        let palette = palette.as_mut().unwrap();
        let folder = item["carpeta"].as_str().unwrap_or("");
        let name = item["imagen"].as_str().unwrap_or("");
        let path = find(folder, name).ok_or_else(|| {
            Stop::new(format!("{folder}/{name}, which ChipSet {number} bakes, is missing"))
        })?;
        let source = Indexed::read(&path)?;
        // RM2k scales images with **nearest neighbour**, and so does this,
        // sampling each pixel at its centre.
        let scale = item.get("escala").map_or(100, int) as usize;
        let width = source.width * scale / 100;
        let height = source.height * scale / 100;
        let (ax, ay) = (source.width as f64 / width as f64, source.height as f64 / height as f64);
        let xin: Vec<usize> = (0..width).map(|x| (ax * (x as f64 + 0.5)) as usize).collect();
        let yin: Vec<usize> = (0..height).map(|y| (ay * (y as f64 + 0.5)) as usize).collect();
        let small = |x: usize, y: usize| source.get(xin[x], yin[y]);
        // Where the drawing's pixel (0,0) lands inside its first cell.
        let (dx, dy) = item
            .get("desfase")
            .and_then(Value::as_array)
            .map_or((0, 0), |d| (int(&d[0]), int(&d[1])));
        // Colours of the drawing treated as transparent besides index 0:
        // defects of the original art, declared in the recipe.
        let transparent: Vec<[u8; 3]> = item
            .get("transparentes")
            .and_then(Value::as_array)
            .map(|list| list.iter().map(|c| [int(&c[0]) as u8, int(&c[1]) as u8, int(&c[2]) as u8]).collect())
            .unwrap_or_default();
        for entry in item["celdas"].as_array().cloned().unwrap_or_default() {
            let (column, row, slot) = (int(&entry[0]), int(&entry[1]), int(&entry[2]));
            // A fourth element is the slot the background comes from: the
            // drawing is composed **on top** of it.
            let mut tile = match entry.get(3) {
                Some(under) => image.crop(common_box(144 + int(under) as i32)),
                None => Indexed::blank(16, 16),
            };
            for y in 0..16i64 {
                for x in 0..16i64 {
                    let (px, py) = (column * 16 + x - dx, row * 16 + y - dy);
                    if !(0 <= px && (px as usize) < width && 0 <= py && (py as usize) < height) {
                        continue;
                    }
                    let index = small(px as usize, py as usize);
                    if index != 0 && !transparent.contains(&source.palette[index as usize]) {
                        tile.pixels[(y * 16 + x) as usize] = palette.index(to_15_bits(source.palette[index as usize]))?;
                    }
                }
            }
            image.paste(&tile, corner(common_box(144 + slot as i32)));
        }
    }
    if let Some(palette) = palette {
        image.palette = palette.colors;
    }
    let name = data["chipset"]["chipset_name"].as_str().unwrap_or("");
    let target = out_dir.join("ChipSet").join(format!("{name}.png"));
    std::fs::create_dir_all(target.parent().unwrap()).map_err(|e| io(&target, e))?;
    // Moved into place in one go, so two builds at once do not leave each
    // other a half-written PNG.
    let temp = target.with_extension(format!("png.{}.png", std::process::id()));
    image.write(&temp)?;
    std::fs::rename(&temp, &target).map_err(|e| io(&target, e))?;
    Ok(target)
}

/// Builds the images of every ChipSet the project adds, into `out_dir`,
/// which then goes first in the resource search. The originals are looked
/// for in `search_dirs` only: never among the images built before.
pub fn build_images(game: &Game, out_dir: &Path, search_dirs: &[PathBuf]) -> Result<()> {
    let find = |folder: &str, name: &str| crate::resources::find(search_dirs, folder, name, &[".png", ".bmp"]);
    for (_path, data) in game.forks.chipsets.values() {
        build(game, data, out_dir, &find)?;
    }
    Ok(())
}
