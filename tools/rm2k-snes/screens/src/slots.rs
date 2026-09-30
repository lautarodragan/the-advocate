//! The bank the slot screen and the pause menu share: the text that does
//! not depend on the save, drawn once; the loose glyphs the cartridge
//! composes names and numbers with; and the faces, each with its palette.
//!
//! It is a single bank and a single set of palettes, because the menu opens
//! the save screen and both show the faces: every variant is drawn before
//! deduplicating, so every block indexes the same tiles.

use crate::cells::{self, Bank, Color, Counts, BLACK, CELL, COLS};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::layout::*;
use crate::texts::{glyphs_of, ljust};
use adeleine::luma_distance;
use rm2k_render::picture::Picture;
use std::collections::{BTreeMap, HashMap};
use voodoo::pack::Indices;

/// The pause menu's blocks, in the bank of the slot screen.
#[derive(Debug, Clone, Default)]
pub struct MenuBlocks {
    /// `options[order][disabled]`: each command in white and, in the
    /// disabled palette, in gray.
    pub options: Vec<[Vec<u16>; 2]>,
    /// The ">", two cells.
    pub cursor: Vec<u16>,
    /// The two cells of each letter the cartridge composes.
    pub glyphs: BTreeMap<char, Vec<u16>>,
    /// The currency term, after the gold.
    pub currency: Vec<u16>,
    /// The text of a party row that does not depend on the actor: one for
    /// the four rows and every actor.
    pub row: Vec<u16>,
    /// The experience term, loose like a glyph: sprites draw it.
    pub exp_term: Vec<u16>,
}

/// The slot screen and the menu, cut.
#[derive(Debug, Clone, Default)]
pub struct Slots {
    pub tiles: Vec<Indices>,
    /// 0 the text's, 1 the disabled commands', and one per face after.
    pub palettes: Vec<Vec<Color>>,
    /// The screen's title, `[loading, saving]`.
    pub headers: Vec<Vec<u16>>,
    /// `rows[slot][full][cursor]`: a whole row, with the face, name and
    /// level cells blank.
    pub rows: Vec<[[Vec<u16>; 2]; 2]>,
    /// The 36 cells of each actor's face, with its palette set.
    pub faces: BTreeMap<i32, Vec<u16>>,
    pub menu: MenuBlocks,
    /// The actors whose face had to borrow another's palette.
    pub lent: Vec<i32>,
}

/// What each layer drawn is, so the second pass knows where to cut it.
enum Kind {
    Header(usize),
    Row(usize, usize, usize),
    Option(usize, usize),
    Cursor,
    Glyph(char),
    Currency,
    MenuRow,
    ExpTerm,
}

/// The level term, like `Window_SaveFile::Refresh`: `lvl_short` padded to
/// two characters and in system colour 1. The number does not go here: the
/// cartridge composes it with glyphs, because it depends on the actor.
fn level_term(game: &Game, skin: &Skin, dest: &mut Picture, x: usize, y: usize) -> Result<()> {
    let term: String = game.term("lvl_short")?.chars().take(2).collect();
    skin.draw_line(dest, x as i64, y as i64, &ljust(&term, 2), 1, game.font_id());
    Ok(())
}

/// Fifteen colours for a face, and where each colour of the picture goes.
///
/// A face can have more colours than a 4bpp palette's fifteen. Index 0 is
/// the transparent one, and black goes there: over the screen's black
/// background it makes no difference and does not spend an entry.
///
/// The reduction is Adeleine's `merge_least_visible`, and not keeping the
/// fifteen most used: at 48x48 a face has a handful of skin tones covering
/// almost all of it and a dozen details of two or three pixels each —the
/// glint of an eye, the edge of a lock of hair—, and the fifteen most used
/// were fifteen variants of the same tone: the face came out flat.
fn face_palette(face: &Picture) -> Result<(Vec<Color>, HashMap<Color, u8>)> {
    let mut used = Counts::default();
    for p in face.rgba.chunks_exact(4) {
        let color = if p[3] != 0 { cells::rgb15([p[0], p[1], p[2], p[3]]) } else { BLACK };
        if color != BLACK {
            used.add(color, 1);
        }
    }
    let (palette, dest): (Vec<Color>, Vec<(Color, Color)>) = if used.len() > 15 {
        let counts: Vec<([u8; 3], u64)> = used.in_order();
        let merged = adeleine::merge_least_visible(&counts, 15)?;
        let mut palette: Vec<Color> = merged.mapping.clone();
        palette.sort();
        palette.dedup();
        let dest = counts.iter().map(|(c, _)| *c).zip(merged.mapping).collect();
        (palette, dest)
    } else {
        let palette = used.by_use();
        let dest = used.in_order().iter().map(|(c, _)| (*c, *c)).collect();
        (palette, dest)
    };
    let mut colors = vec![BLACK];
    colors.extend(palette);
    let mut index = HashMap::from([(BLACK, 0u8)]);
    for (color, target) in dest {
        let at = colors.iter().position(|c| *c == target).expect("the target is in the palette");
        index.insert(color, at as u8);
    }
    Ok((colors, index))
}

/// Which of the existing palettes a face that did not get its own hangs on
/// to, and for each colour of the face which index of that palette it goes
/// to.
///
/// The palette missing the fewest colours is chosen —counting distinct
/// colours, not pixels— and each colour goes to the nearest by luma. The
/// first two palettes are the text's and are not touched: painting the face
/// over the text would make it illegible, which is worse than a face with
/// its tone changed.
fn lend(
    colors: &[Color],
    face_index: &HashMap<Color, u8>,
    palettes: &[Vec<Color>],
) -> (usize, HashMap<Color, u8>) {
    let which = (2..palettes.len())
        .min_by_key(|&n| (colors.iter().filter(|c| !palettes[n].contains(c)).count(), n))
        .expect("there are palettes to lend");
    let dest = &palettes[which];
    let position = |c: &Color| dest.iter().position(|p| p == c).expect("in the palette");
    let offset: HashMap<Color, u8> = colors
        .iter()
        .map(|c| {
            let at = if dest.contains(c) {
                position(c)
            } else {
                let nearest = dest
                    .iter()
                    .min_by_key(|p| (luma_distance(**p, *c), **p))
                    .expect("a palette is not empty");
                position(nearest)
            };
            (*c, at as u8)
        })
        .collect();
    let index = face_index
        .iter()
        .map(|(c, k)| (*c, offset[&colors[*k as usize]]))
        .collect();
    (which, index)
}

/// The slot screen's and the menu's bank, for `slots` save slots, the
/// `actors` that can be in the party —their faces and the letters of their
/// names— and the letters of `extra`, which the actor choice writes.
///
/// A face that finds no free palette **borrows one**: without it, a game
/// with more actors that can join than palettes would have to leave some
/// out, and they can be the path of the story.
pub fn slots_screen(game: &Game, skin: &Skin, slots: usize, actors: &[i32], extra: &str) -> Result<Slots> {
    let font_id = game.font_id();
    let write = |dest: &mut Picture, x: usize, y: usize, text: &str, color: i32| {
        skin.draw_line(dest, x as i64, y as i64, text, color, font_id);
    };

    // First all the text layers, so the colours can be gathered at once.
    let mut layers: Vec<(Kind, Picture)> = Vec::new();
    for (mode, term) in ["load_game_message", "save_game_message"].iter().enumerate() {
        let mut image = cells::layer();
        write(&mut image, SLOT_X, HEADER_Y, &game.term(term)?, 0);
        layers.push((Kind::Header(mode), image));
    }
    let file = game.term("file")?;
    for number in 0..slots {
        for full in 0..2 {
            for cursor in 0..2 {
                let mut image = cells::layer();
                let y = SLOT_Y + number * SLOT_STEP;
                if cursor == 1 {
                    write(&mut image, SLOT_X - 16, y + 2, ">", 0);
                }
                let second = if full == 1 { "" } else { EMPTY };
                for (n, line) in [format!("{file} {}", number + 1), second.to_string()]
                    .iter()
                    .enumerate()
                {
                    write(&mut image, SLOT_X, y + 2 + n * LINE, line, 0);
                }
                if full == 1 {
                    // The level term goes in the row: it is the same for
                    // everyone, and a slot without a save does not show it.
                    level_term(game, skin, &mut image, SLOT_X, y + 2 + 2 * LINE)?;
                }
                layers.push((Kind::Row(number, full, cursor), image));
            }
        }
    }
    // The pause menu's, in the same bank. Each on the topmost row it gets:
    // the blocks work on any other because they are aligned.
    let menu_terms = ["command_item", "command_skill", "menu_equipment", "menu_save", "menu_quit"];
    for (option, term) in menu_terms.iter().enumerate() {
        let text = game.term(term)?;
        for disabled in 0..2 {
            let mut image = cells::layer();
            let color = if disabled == 1 { 3 } else { 0 };
            write(&mut image, MENU_OPT_COL * CELL, MENU_OPT_Y + option * MENU_OPT_STEP + 2, &text, color);
            layers.push((Kind::Option(option, disabled), image));
        }
    }
    let mut image = cells::layer();
    write(&mut image, MENU_CURSOR_COL * CELL, MENU_OPT_Y + 2, ">", 0);
    layers.push((Kind::Cursor, image));
    for letter in glyphs_of(game, actors, extra)? {
        let mut image = cells::layer();
        write(&mut image, GLYPH_COL * CELL + GLYPH_DX, GLYPH_ROW * CELL + GLYPH_DY, &letter.to_string(), 0);
        layers.push((Kind::Glyph(letter), image));
    }
    let mut image = cells::layer();
    write(&mut image, MENU_CURRENCY_COL * CELL, MENU_GOLD_Y + 2, &game.term("gold")?, 1);
    layers.push((Kind::Currency, image));
    // The text of a party row that **does not depend on the actor**: the
    // level term, the status and the HP term. The name, the level number,
    // the maximum and the current HP are composed by the cartridge.
    let mut image = cells::layer();
    level_term(game, skin, &mut image, MENU_TEXT_X, 2 + LINE)?;
    write(&mut image, MENU_TEXT_X + MENU_STATUS_DX, 2 + LINE, &game.term("normal_status")?, 0);
    write(&mut image, MENU_TEXT_X, 2 + 2 * LINE, &game.term("hp_short")?, 1);
    layers.push((Kind::MenuRow, image));
    // The experience term: up to two letters, the twelve pixels
    // `DrawActorExp` leaves it before the digits.
    let mut image = cells::layer();
    let exp: String = game.term("exp_short")?.chars().take(2).collect();
    write(&mut image, GLYPH_COL * CELL, GLYPH_ROW * CELL + GLYPH_DY, &exp, 1);
    layers.push((Kind::ExpTerm, image));

    // The disabled commands go in **their own palette**, number 1: system
    // colour 3 is a gradient that, added to the text's, does not fit in a
    // 4bpp palette. It costs the faces one palette.
    let mut seen = Counts::default();
    let mut seen_gray = Counts::default();
    for (kind, image) in &layers {
        match kind {
            Kind::Option(_, 1) => seen_gray.add_picture(image),
            _ => seen.add_picture(image),
        }
    }
    for (count, what) in [
        (seen.len(), "the text of the slots and the menu"),
        (seen_gray.len(), "the disabled commands"),
    ] {
        if count > 15 {
            return Err(Bad::answer(format!("{what} uses {count} colours and 4bpp fits 15")));
        }
    }
    let mut palette = vec![BLACK];
    palette.extend(seen.by_use());
    let index = cells::index_of(&palette);
    let mut gray_palette = vec![BLACK];
    gray_palette.extend(seen_gray.by_use());
    let gray_index = cells::index_of(&gray_palette);

    let mut bank = Bank::default();
    let mut out = Slots {
        headers: vec![Vec::new(); 2],
        rows: vec![Default::default(); slots],
        menu: MenuBlocks {
            options: vec![Default::default(); MENU_OPTIONS],
            ..Default::default()
        },
        ..Default::default()
    };
    for (kind, image) in &layers {
        let mut block = |row0: usize, rows: usize, index, col0: usize, cols: usize, palette: u16| {
            cells::cell_block(image, row0, rows, &mut bank, index, col0, cols, palette)
        };
        match kind {
            Kind::Option(option, disabled) => {
                let (idx, pal) = if *disabled == 1 { (&gray_index, 1) } else { (&index, 0) };
                out.menu.options[*option][*disabled] = block(
                    (MENU_OPT_Y + option * MENU_OPT_STEP) / CELL,
                    2,
                    idx,
                    MENU_OPT_COL,
                    MENU_OPT_COLS,
                    pal,
                )?;
            }
            Kind::Cursor => out.menu.cursor = block(MENU_OPT_Y / CELL, 2, &index, MENU_CURSOR_COL, 1, 0)?,
            Kind::Glyph(letter) => {
                let cells = block(GLYPH_ROW, 2, &index, GLYPH_COL, 1, 0)?;
                out.menu.glyphs.insert(*letter, cells);
            }
            Kind::Currency => {
                out.menu.currency =
                    block(MENU_GOLD_Y / CELL, 2, &index, MENU_CURRENCY_COL, MENU_CURRENCY_COLS, 0)?
            }
            Kind::MenuRow => {
                out.menu.row = block(0, MENU_ACTOR_ROWS, &index, MENU_ACTOR_COL, MENU_ACTOR_COLS, 0)?
            }
            Kind::ExpTerm => {
                out.menu.exp_term = block(GLYPH_ROW, 2, &index, GLYPH_COL, MENU_EXP_TERM_CELLS, 0)?
            }
            Kind::Header(mode) => {
                out.headers[*mode] = block(HEADER_Y / CELL, HEADER_ROWS, &index, 0, COLS, 0)?
            }
            Kind::Row(number, full, cursor) => {
                let row0 = (SLOT_Y + number * SLOT_STEP) / CELL;
                out.rows[*number][*full][*cursor] = block(row0, SLOT_ROWS, &index, 0, COLS, 0)?;
            }
        }
    }

    // And the faces, each with its palette, put at the top left of the
    // first row to cut them into cells with the same function.
    let mut palettes = vec![palette, gray_palette];
    for &actor in actors {
        let face = match game.face(actor)? {
            Some(face) => face,
            None => continue,
        };
        let (colors, face_index) = face_palette(&face)?;
        let (which, face_index) = if palettes.len() > FACE_PALETTES_MAX {
            // No BG2 palette left: **one is lent to it**, and the face shows
            // with colours that are not its own.
            out.lent.push(actor);
            lend(&colors, &face_index, &palettes)
        } else {
            palettes.push(colors);
            (palettes.len() - 1, face_index)
        };
        let mut image = cells::layer();
        image.put(FACE_COL * CELL, SLOT_Y, &face);
        let cells = cells::cell_block(
            &image,
            SLOT_Y / CELL,
            FACE_CELLS,
            &mut bank,
            &face_index,
            FACE_COL,
            FACE_CELLS,
            which as u16,
        )?;
        out.faces.insert(actor, cells);
    }
    if bank.len() > SLOT_TILES_MAX {
        return Err(Bad::answer(format!(
            "the slot screen and the menu gather {} tiles and their bank fits {SLOT_TILES_MAX}",
            bank.len()
        )));
    }
    out.tiles = bank.tiles;
    out.palettes = palettes;
    Ok(out)
}
