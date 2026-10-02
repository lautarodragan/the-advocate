//! The pictures' tables, which the console walks with nothing but offsets:
//! a map without pictures is a zero, and a map's block is its base, its
//! count and an entry per picture that says where its objects and its
//! colours are.

use rm2k_snes_mapdata::emit::{picture_tables, PICTURE_ENTRY};
use rm2k_snes_mapdata::request::{self, MapPictures, Maps, PictureImage};
use std::path::Path;

fn maps() -> Maps {
    request::read(&Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json")).unwrap()
}

fn word(data: &[u8], at: usize) -> u16 {
    u16::from_le_bytes([data[at], data[at + 1]])
}

#[test]
fn a_map_carries_its_pictures_and_the_others_a_zero() {
    let mut maps = maps().maps;
    assert!(maps.len() >= 2);
    maps[1].pictures = Some(MapPictures {
        base: 192,
        images: vec![
            PictureImage {
                half: [93, 15],
                first: 0,
                objects: vec![[0, 0], [32, 0]],
                palette: vec![[31, 0, 0], [0, 31, 0]],
            },
            PictureImage {
                half: [-1, 4],
                first: 2,
                objects: vec![[0, 32]],
                palette: vec![[1, 2, 3]],
            },
        ],
    });
    let (starts, data) = picture_tables(&maps).unwrap();
    assert_eq!(starts.len(), 2 * maps.len());
    assert_eq!(word(&starts, 0), 0, "the first map carries none");
    let start = word(&starts, 2) as usize;
    assert_ne!(start, 0);
    assert_eq!(word(&data, start), 192, "the base");
    assert_eq!(data[start + 2], 2, "how many");
    let first = start + 3;
    let second = first + PICTURE_ENTRY;
    assert_eq!((word(&data, first), word(&data, first + 2)), (93, 15));
    assert_eq!((data[first + 4], data[first + 5]), (2, 0));
    assert_eq!(word(&data, second) as i16, -1, "a half is signed");
    assert_eq!((data[second + 4], data[second + 5]), (1, 2));
    assert_eq!(word(&data, first + 10), 192, "the base, again in the entry");
    // Its objects, and its colours: black first, then its own, sixteen.
    let objects = word(&data, first + 6) as usize;
    assert_eq!(&data[objects..objects + 4], &[0, 0, 32, 0]);
    let colors = word(&data, first + 8) as usize;
    assert_eq!(word(&data, colors), 0);
    assert_eq!(word(&data, colors + 2), 31, "red, in the low five bits");
    assert_eq!(word(&data, second + 8) as usize, colors + 32 + 2);
}
