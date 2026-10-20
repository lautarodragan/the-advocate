//! The bank the slot screen and the menu share, with each screen's text
//! apart —`Order::Apart`—: the slot screen composes its leaders' names over
//! the menu's text, so nothing the slot screen shows may be one of those
//! tiles, not even a tile that is the same as one of the menu's; and the
//! menu composes over the slot screen's text, so nothing the menu shows may
//! be one of those.
//!
//! It is the order ABL's `release` takes since 2026-10-20, when its
//! leaders' names went whole: there the bank is the same, and what is
//! drawn is looked at by its suite. This is the rule the order rests on,
//! with the small game, where every order fits.

use rm2k_snes_screens::layout::SLOT_TILES_MAX;
use rm2k_snes_screens::slots::{slots_screen_with, Order, Slots};
use rm2k_snes_screens::Game;
use std::ops::Range;
use std::path::PathBuf;

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/game")
}

fn bank(order: Order) -> Slots {
    let game = Game::from_dump(&here().join("dump"), &here().join("pictures")).unwrap();
    let skin = game.skin().unwrap();
    let actors: Vec<i32> = (1..=8).collect();
    slots_screen_with(&game, &skin, 4, &actors, order, &[]).unwrap()
}

/// The tile each tilemap word points to: its low ten bits.
fn tiles<'a>(blocks: impl IntoIterator<Item = &'a Vec<u16>>) -> Vec<usize> {
    blocks
        .into_iter()
        .flatten()
        .map(|word| (word & 0x3FF) as usize)
        .collect()
}

/// What the slot screen shows: its headers and rows, the faces, and the
/// glyphs it writes the level with.
fn slot_shows(b: &Slots) -> Vec<usize> {
    let mut shown = tiles(&b.headers);
    shown.extend(tiles(b.rows.iter().flatten()));
    shown.extend(tiles(b.faces.values()));
    shown.extend(tiles(b.menu.glyphs.values()));
    shown
}

/// What the menu shows: its commands, the currency, the party row, the
/// experience term, the faces and the glyphs.
fn menu_shows(b: &Slots) -> Vec<usize> {
    let mut shown = tiles(b.menu.options.iter().flatten());
    shown.extend(tiles([&b.menu.currency, &b.menu.row, &b.menu.exp_term]));
    shown.extend(tiles(b.faces.values()));
    shown.extend(tiles(b.menu.glyphs.values()));
    shown
}

fn outside(shown: &[usize], names: Range<usize>, what: &str) {
    let inside: Vec<&usize> = shown.iter().filter(|t| names.contains(t)).collect();
    assert!(
        inside.is_empty(),
        "{what} shows tiles {inside:?}, which the names are composed over: {names:?}"
    );
}

#[test]
fn apart_each_screen_composes_over_what_only_the_other_shows() {
    let b = bank(Order::Apart);
    let (first, end) = b.slot_names;
    // The slot screen's names: over the menu's text, which ends where the
    // menu's tiles do.
    assert_eq!(end, b.menu_tiles);
    assert!(
        first < end,
        "the menu's text takes no tiles: {:?}",
        b.slot_names
    );
    outside(&slot_shows(&b), first..end, "the slot screen");
    // And the menu's: from the end of what it shows up to the tilemap.
    outside(&menu_shows(&b), b.menu_tiles..SLOT_TILES_MAX, "the menu");
}

#[test]
fn drawn_and_menu_first_compose_the_slot_screen_after_the_bank() {
    for order in [Order::Drawn, Order::MenuFirst] {
        let b = bank(order);
        assert_eq!(b.slot_names, (b.tiles.len(), SLOT_TILES_MAX), "{order:?}");
        outside(
            &slot_shows(&b),
            b.tiles.len()..SLOT_TILES_MAX,
            "the slot screen",
        );
        outside(&menu_shows(&b), b.menu_tiles..SLOT_TILES_MAX, "the menu");
    }
}
