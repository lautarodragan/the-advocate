//! The bank the slot screen and the pause menu share: the text that does
//! not depend on the save, drawn once; the loose glyphs the cartridge
//! writes numbers with; the font precomposed for the bank's text palette,
//! which the cartridge composes names with; and the faces, each with its
//! palette.
//!
//! It is a single bank and a single set of palettes, because the menu opens
//! the save screen and both show the faces: every variant is drawn before
//! deduplicating, so every block indexes the same tiles.

use crate::cells::{self, Bank, Color, Counts, BLACK, CELL, COLS};
use crate::fail::{Bad, Result};
use crate::game::{Game, Skin};
use crate::items::ink_colors;
use crate::layout::*;
use crate::message_window;
use crate::texts::{ljust, NUMBER_GLYPHS};
use adeleine::luma_distance;
use rm2k_render::picture::Picture;
use rm2k_snes_text::font;
use std::collections::{BTreeMap, HashMap};
use voodoo::pack::Indices;

/// The pause menu's blocks, in the bank of the slot screen.
#[derive(Debug, Clone, Default)]
pub struct MenuBlocks {
    /// `options[order][disabled]`: each command in white and, in the
    /// disabled palette, in gray.
    pub options: Vec<[Vec<u16>; 2]>,
    /// The two cells of each letter of the numbers, which the cartridge
    /// writes one per cell.
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
    /// `rows[slot][full]`: a whole row, with the face, name and level
    /// cells blank. The cursor is not in them: it is the System's, on BG1.
    pub rows: Vec<[Vec<u16>; 2]>,
    /// The 36 cells of each actor's face, with its palette set.
    pub faces: BTreeMap<i32, Vec<u16>>,
    pub menu: MenuBlocks,
    /// The actors whose face had to borrow another's palette.
    pub lent: Vec<i32>,
    /// The font precomposed for palette 0, one table per phase: what the
    /// cartridge's `tl_strip` composes names with —see `text_layer.s`—.
    pub prerender: Vec<Vec<u8>>,
    /// How many of `tiles`, from the first, the menu and the actor choice
    /// show: their names are composed from the first even tile after
    /// these. All of them unless the bank went [`Order::MenuFirst`].
    pub menu_tiles: usize,
}

/// The order the bank gathers its tiles in. The slot screen and the menu
/// upload it whole, and each composes its names in the tiles after it; but
/// the menu does not show the slot screen's headers and rows, so with
/// those last, it may compose over them.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Order {
    /// The text in the order it is drawn, and the faces after it: what the
    /// bank has always been, and what it stays while the names fit.
    Drawn,
    /// The menu's text and the faces first, and the slot screen's after:
    /// the menu's names then start where its own tiles end. Since
    /// 2026-10-03, for a `[text] letter_spacing` that leaves the bank short:
    /// spaced, the baked text takes more tiles and the names more columns.
    MenuFirst,
}

/// What each layer drawn is, so the second pass knows where to cut it.
enum Kind {
    Header(usize),
    Row(usize, usize),
    Option(usize, usize),
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
    skin.draw_line(dest, x as i64, y as i64, &ljust(&term, 2), 1, &game.font);
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
///
/// The message window's faces do not come through here: there a black
/// pixel is a colour and not a hole —the map would show through—, see
/// `faces::palette`.
fn face_palette(face: &Picture) -> Result<(Vec<Color>, HashMap<Color, u8>)> {
    let mut used = Counts::default();
    for p in face.rgba.chunks_exact(4) {
        let color = if p[3] != 0 {
            cells::rgb15([p[0], p[1], p[2], p[3]])
        } else {
            BLACK
        };
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
        let at = colors
            .iter()
            .position(|c| *c == target)
            .expect("the target is in the palette");
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
        .min_by_key(|&n| {
            (
                colors.iter().filter(|c| !palettes[n].contains(c)).count(),
                n,
            )
        })
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

impl Slots {
    /// Whether the bank fits its VRAM: see the VRAM checks.
    pub fn fits(&self) -> bool {
        self.tiles.len() <= SLOT_TILES_MAX
    }

    /// The error a bank that does not fit is reported with.
    pub fn too_many(&self) -> Bad {
        Bad::answer(format!(
            "the slot screen and the menu gather {} tiles and their bank fits {SLOT_TILES_MAX}",
            self.tiles.len()
        ))
    }
}

/// The slot screen's and the menu's bank, for `slots` save slots and the
/// `actors` that can be in the party, whose faces it carries; an error if
/// it does not fit its VRAM.
///
/// A face that finds no free palette **borrows one**: without it, a game
/// with more actors that can join than palettes would have to leave some
/// out, and they can be the path of the story.
pub fn slots_screen(
    game: &Game,
    skin: &Skin,
    slots: usize,
    actors: &[i32],
    order: Order,
) -> Result<Slots> {
    let bank = slots_screen_with(game, skin, slots, actors, order, &[])?;
    if !bank.fits() {
        return Err(bank.too_many());
    }
    Ok(bank)
}

/// The same, with the pause menu's options the custom menus add: their
/// labels, which go after the five of RM2k as commands 5 and on —see
/// `custom_menu`—. **It does not check that the bank fits**: the caller
/// does, with [`Slots::fits`], because the converter leaves faces out
/// until it does —see `slots_with_room` in `convert`— and needs the bank
/// that was too big to say by how much.
pub fn slots_screen_with(
    game: &Game,
    skin: &Skin,
    slots: usize,
    actors: &[i32],
    order: Order,
    custom: &[String],
) -> Result<Slots> {
    let font = &game.font;
    let write = |dest: &mut Picture, x: usize, y: usize, text: &str, color: i32| {
        skin.draw_line(dest, x as i64, y as i64, text, color, font);
    };

    // First all the text layers, so the colours can be gathered at once.
    let mut layers: Vec<(Kind, Picture)> = Vec::new();
    for (mode, term) in ["load_game_message", "save_game_message"]
        .iter()
        .enumerate()
    {
        let mut image = cells::layer();
        write(&mut image, SLOT_X, HEADER_Y, &game.term(term)?, 0);
        layers.push((Kind::Header(mode), image));
    }
    let file = game.term("file")?;
    for number in 0..slots {
        for full in 0..2 {
            let mut image = cells::layer();
            let y = SLOT_Y + number * SLOT_STEP;
            // The term, and the number half a space after it in two places,
            // `"%2d"`: `Window_SaveFile::Refresh`. The slot cursor's width
            // counts on it.
            write(&mut image, SLOT_X, y + 2, &file, 0);
            let number_x = SLOT_X + font.width(&file) + font.width(" ") / 2;
            write(&mut image, number_x, y + 2, &format!("{:2}", number + 1), 0);
            if full == 0 {
                write(&mut image, SLOT_X, y + 2 + LINE, EMPTY, 0);
            } else {
                // The level term goes in the row: it is the same for
                // everyone, and a slot without a save does not show it.
                level_term(game, skin, &mut image, SLOT_X, y + 2 + 2 * LINE)?;
            }
            layers.push((Kind::Row(number, full), image));
        }
    }
    // The pause menu's, in the same bank. Each on the topmost row it gets:
    // the blocks work on any other because they are aligned.
    let menu_terms = [
        "command_item",
        "command_skill",
        "menu_equipment",
        "menu_save",
        "menu_quit",
    ];
    let mut labels: Vec<String> = menu_terms
        .iter()
        .map(|t| game.term(t))
        .collect::<Result<_>>()?;
    labels.extend(custom.iter().cloned());
    for (option, text) in labels.iter().enumerate() {
        for disabled in 0..2 {
            let mut image = cells::layer();
            let color = if disabled == 1 { 3 } else { 0 };
            // On the first row: a block works on any row, because they are
            // aligned, and the custom ones are drawn at any.
            write(&mut image, MENU_OPT_COL * CELL, MENU_OPT_Y + 2, text, color);
            layers.push((Kind::Option(option, disabled), image));
        }
    }
    for letter in NUMBER_GLYPHS.chars() {
        let mut image = cells::layer();
        write(
            &mut image,
            GLYPH_COL * CELL + GLYPH_DX,
            GLYPH_ROW * CELL + GLYPH_DY,
            &letter.to_string(),
            0,
        );
        layers.push((Kind::Glyph(letter), image));
    }
    let mut image = cells::layer();
    write(
        &mut image,
        MENU_CURRENCY_COL * CELL,
        MENU_GOLD_Y + 2,
        &game.term("gold")?,
        1,
    );
    layers.push((Kind::Currency, image));
    // The text of a party row that **does not depend on the actor**: the
    // level term, the status and the HP term. The name, the level number,
    // the maximum and the current HP are composed by the cartridge.
    let mut image = cells::layer();
    level_term(game, skin, &mut image, MENU_TEXT_X, 2 + LINE)?;
    write(
        &mut image,
        MENU_TEXT_X + MENU_STATUS_DX,
        2 + LINE,
        &game.term("normal_status")?,
        0,
    );
    write(
        &mut image,
        MENU_TEXT_X,
        2 + 2 * LINE,
        &game.term("hp_short")?,
        1,
    );
    layers.push((Kind::MenuRow, image));
    // The experience term: up to two letters, the twelve pixels
    // `DrawActorExp` leaves it before the digits.
    let mut image = cells::layer();
    let exp: String = game.term("exp_short")?.chars().take(2).collect();
    write(
        &mut image,
        GLYPH_COL * CELL,
        GLYPH_ROW * CELL + GLYPH_DY,
        &exp,
        1,
    );
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
    // And every row of the white ink and its shadow, which the composed
    // names paint even if no baked text uses them all.
    let (ink_rows, ink_shadow) = ink_colors(skin, 0)?;
    for &color in ink_rows.iter().chain([&ink_shadow]) {
        seen.add(color, 1);
    }
    for (count, what) in [
        (seen.len(), "the text of the slots and the menu"),
        (seen_gray.len(), "the disabled commands"),
    ] {
        if count > 15 {
            return Err(Bad::answer(format!(
                "{what} uses {count} colours and 4bpp fits 15"
            )));
        }
    }
    let mut palette = vec![BLACK];
    palette.extend(seen.by_use());
    let index = cells::index_of(&palette);
    let at = |color: &Color| palette.iter().position(|c| c == color).expect("seen") as u8;
    let rows: Vec<u8> = ink_rows.iter().map(at).collect();
    let prerender = message_window::font_prerender(
        &message_window::font_bytes(&game.font)?,
        &rows,
        at(&ink_shadow),
    );
    debug_assert_eq!(rows.len(), font::HEIGHT);
    let mut gray_palette = vec![BLACK];
    gray_palette.extend(seen_gray.by_use());
    let gray_index = cells::index_of(&gray_palette);

    let mut bank = Bank::default();
    let mut out = Slots {
        headers: vec![Vec::new(); 2],
        rows: vec![Default::default(); slots],
        menu: MenuBlocks {
            options: vec![Default::default(); MENU_OPTIONS + custom.len()],
            ..Default::default()
        },
        ..Default::default()
    };
    // Every block takes a tile of the bank flipped when it is one: since
    // 2026-10-14, when ABL with every map was three tiles short for the
    // slot screen's names. **But the loose glyphs and the experience
    // term**, which `menu_exp_paint` also draws as sprites and passes only
    // the tile's number on to the OAM: a flip there would draw the tile
    // unflipped.
    let place = |kind: &Kind, image: &Picture, bank: &mut Bank, out: &mut Slots| -> Result<()> {
        let mirror = !matches!(kind, Kind::Glyph(_) | Kind::ExpTerm);
        let mut block =
            |row0: usize, rows: usize, index, col0: usize, cols: usize, palette: u16| {
                cells::cell_block(image, row0, rows, bank, index, col0, cols, palette, mirror)
            };
        match kind {
            Kind::Option(option, disabled) => {
                let (idx, pal) = if *disabled == 1 {
                    (&gray_index, 1)
                } else {
                    (&index, 0)
                };
                out.menu.options[*option][*disabled] =
                    block(MENU_OPT_Y / CELL, 2, idx, MENU_OPT_COL, MENU_OPT_COLS, pal)?;
            }
            Kind::Glyph(letter) => {
                let cells = block(GLYPH_ROW, 2, &index, GLYPH_COL, 1, 0)?;
                out.menu.glyphs.insert(*letter, cells);
            }
            Kind::Currency => {
                out.menu.currency = block(
                    MENU_GOLD_Y / CELL,
                    2,
                    &index,
                    MENU_CURRENCY_COL,
                    MENU_CURRENCY_COLS,
                    0,
                )?
            }
            Kind::MenuRow => {
                out.menu.row = block(
                    0,
                    MENU_ACTOR_ROWS,
                    &index,
                    MENU_ACTOR_COL,
                    MENU_ACTOR_COLS,
                    0,
                )?
            }
            Kind::ExpTerm => {
                out.menu.exp_term = block(GLYPH_ROW, 2, &index, GLYPH_COL, MENU_EXP_TERM_CELLS, 0)?
            }
            Kind::Header(mode) => {
                out.headers[*mode] = block(HEADER_Y / CELL, HEADER_ROWS, &index, 0, COLS, 0)?
            }
            Kind::Row(number, full) => {
                let row0 = (SLOT_Y + number * SLOT_STEP) / CELL;
                out.rows[*number][*full] = block(row0, SLOT_ROWS, &index, 0, COLS, 0)?;
            }
        }
        Ok(())
    };
    let slot_only = |kind: &Kind| matches!(kind, Kind::Header(_) | Kind::Row(..));
    let (before, after): (Vec<_>, Vec<_>) = match order {
        Order::Drawn => (layers.iter().collect(), Vec::new()),
        Order::MenuFirst => layers.iter().partition(|(kind, _)| !slot_only(kind)),
    };
    for (kind, image) in before {
        place(kind, image, &mut bank, &mut out)?;
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
            true,
        )?;
        out.faces.insert(actor, cells);
    }
    out.menu_tiles = bank.len();
    for (kind, image) in after {
        place(kind, image, &mut bank, &mut out)?;
    }
    out.tiles = bank.tiles;
    out.palettes = palettes;
    out.prerender = prerender;
    Ok(out)
}
