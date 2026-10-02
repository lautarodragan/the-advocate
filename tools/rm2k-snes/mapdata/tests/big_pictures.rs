//! A big picture's tilemap as VRAM holds it: two 32x32 screens, side by side
//! with the picture's edges mirrored on the second when it is as tall as the
//! screen, one under the other when it is taller.

use rm2k_snes_mapdata::emit::big_tilemap;

const SCREEN: usize = 32;
const HFLIP: u16 = 0x4000;

/// A picture of `rows` rows whose cell (r, c) is tile `1 + r * 32 + c`.
fn cells(rows: usize) -> Vec<u16> {
    (0..rows * SCREEN).map(|k| 1 + k as u16).collect()
}

#[test]
fn as_tall_as_the_screen_it_is_two_screens_side_by_side() {
    let (map, size) = big_tilemap(28, &cells(28), true).unwrap();
    assert_eq!(size, 1, "64x32");
    assert_eq!(map.len(), 2 * SCREEN * SCREEN);
    let right = SCREEN * SCREEN;
    for r in 0..28 {
        let row = r * SCREEN;
        assert_eq!(map[row + 5], 1 + (row + 5) as u16, "the left screen is the picture");
        // What a wave brings in on the right: column 31, then 30, mirrored.
        assert_eq!(map[right + row], (1 + (row + 31) as u16) ^ HFLIP);
        assert_eq!(map[right + row + 1], (1 + (row + 30) as u16) ^ HFLIP);
        // And on the left, from the right screen's end: column 0, then 1.
        assert_eq!(map[right + row + 31], (1 + row as u16) ^ HFLIP);
        assert_eq!(map[right + row + 30], (1 + (row + 1) as u16) ^ HFLIP);
        assert_eq!(map[right + row + 10], 0, "the middle of the right screen is empty");
    }
    assert!(map[28 * SCREEN..SCREEN * SCREEN].iter().all(|&e| e == 0));
}

#[test]
fn one_that_does_not_go_past_the_sides_has_nothing_beyond_them() {
    let (map, _) = big_tilemap(28, &cells(28), false).unwrap();
    assert!(map[SCREEN * SCREEN..].iter().all(|&e| e == 0));
}

#[test]
fn a_blank_cell_stays_blank_when_mirrored() {
    let mut picture = cells(28);
    picture[31] = 0;
    let (map, _) = big_tilemap(28, &picture, true).unwrap();
    assert_eq!(map[SCREEN * SCREEN], 0, "blank is tile 0, flipped or not");
}

#[test]
fn taller_than_the_screen_it_is_two_screens_one_under_the_other() {
    let (map, size) = big_tilemap(35, &cells(35), true).unwrap();
    assert_eq!(size, 2, "32x64");
    assert_eq!(&map[..35 * SCREEN], &cells(35)[..]);
    assert!(map[35 * SCREEN..].iter().all(|&e| e == 0));
}

#[test]
fn more_than_two_screens_is_an_error() {
    assert!(big_tilemap(65, &cells(65), false).is_err());
    assert!(big_tilemap(28, &cells(27), false).is_err());
}
