//! A map whose ChipSet animation does not fit in WRAM is carried with the
//! tiles that cover the fewest cells standing still, and says so; one that
//! fits comes out as it always did.

use rm2k_snes_mapdata::materials::LZ2_CAP_ANIM;
use rm2k_snes_mapdata::request::{self, Map, Maps};
use rm2k_snes_mapdata::{animation, record};
use std::path::Path;

fn maps() -> Maps {
    request::read(&Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json")).unwrap()
}

/// The test's map 7 with a bank of 64 tiles, fifty of them water —tiles
/// 10 to 59— and four animated —60 to 63—: 166 tiles' worth of drawings,
/// where 128 fit. Its three blocks draw tiles 10 to 13, 60 to 63 and 0 to
/// 3, on 200, 50 and 50 cells.
fn too_much_water() -> Vec<Map> {
    let mut maps = maps().maps;
    let map = &mut maps[0];
    map.tiles = vec![0; 64 * 64];
    for (block, first) in [(0usize, 10u16), (1, 60), (2, 0)] {
        for k in 0..4 {
            let at = block * 16 + 2 * k;
            map.blocks[at..at + 2].copy_from_slice(&(first + k as u16).to_le_bytes());
        }
    }
    map.cells = (0..300u16)
        .map(|n| if n < 200 { 0 } else if n < 250 { 1 } else { 2 })
        .flat_map(|b: u16| b.to_le_bytes())
        .collect();
    for (family, base, tiles) in [("water", 10, 50), ("animated", 60, 4)] {
        let run = map.runs.iter_mut().find(|r| r.family == family).unwrap();
        run.base = base;
        run.tiles = tiles;
        for (d, drawing) in run.drawings.iter_mut().enumerate() {
            *drawing = vec![d as u8 + 1; tiles as usize * 64];
        }
    }
    maps
}

#[test]
fn an_animation_that_does_not_fit_loses_the_tiles_that_cover_the_least() {
    let mut maps = too_much_water();
    let notes = animation::fit_all(&mut maps);
    assert_eq!(
        notes,
        ["  map 7: WARNING, the ChipSet animation's drawings are 10624 bytes and 8192 fit in \
          WRAM: 13 of its 50 water tiles (0 of 800 cells) stand still on their first drawing"]
    );
    let water = maps[0].runs.iter().find(|r| r.family == "water").unwrap();
    assert_eq!(water.tiles, 37);
    // What is left of each drawing is its beginning, as it was.
    assert!(water.drawings.iter().enumerate().all(|(d, w)| *w == vec![d as u8 + 1; 37 * 64]));
    let written = record::maps(&maps).unwrap();
    assert!(record::anim_bytes(&maps[0]).len() <= LZ2_CAP_ANIM);
    assert!(written.tables.contains("    .byte 37, 0   ; 37 tile(s)"));
}

#[test]
fn without_the_cut_the_map_is_refused() {
    let bad = record::maps(&too_much_water()).err().unwrap();
    assert_eq!(
        bad.message(),
        "map 7: a stream of anim_tiles is 10624 bytes and 8192 fit in WRAM: see the LZ2 \
         reservation in tools/runtime/far_ram.s"
    );
}

#[test]
fn a_map_that_fits_is_not_touched() {
    let mut mine = maps().maps;
    let before = record::maps(&maps().maps).unwrap();
    assert!(animation::fit_all(&mut mine).is_empty());
    let after = record::maps(&mine).unwrap();
    assert_eq!((before.maps, before.tables), (after.maps, after.tables));
}
