//! The cartridge carries of each character only the poses some map can
//! show, and the build stops when a row could ask for one it left out.

use rm2k_snes_mapdata::record::{self, poses, requested, stand_in, NpcRow};
use rm2k_snes_mapdata::request::{self, Bank, Map, Maps};
use std::collections::BTreeSet;
use std::path::Path;
use wally::answer::Cache;

fn maps() -> Vec<Map> {
    let maps: Maps =
        request::read(&Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/maps.json")).unwrap();
    maps.maps
}

/// The bank of `charset` in `map` showing only `shows`.
fn showing(map: &mut Map, charset: &str, shows: &[i64]) {
    let sprite = map.sprite.as_mut().unwrap();
    for bank in &mut sprite.banks {
        if bank.charset() == charset {
            *bank = Bank::Shows(
                bank.charset().to_string(),
                bank.index(),
                bank.poses().to_vec(),
                Some(shows.to_vec()),
            );
        }
    }
}

fn rows(maps: &[Map]) -> Vec<Vec<NpcRow>> {
    maps.iter().map(|m| record::npc_table(m).unwrap()).collect()
}

fn defined(text: &str) -> usize {
    text.lines()
        .filter(|l| l.starts_with("pose_") && l.ends_with(':'))
        .count()
}

#[test]
fn a_pose_no_map_shows_is_left_out_and_its_pointer_aims_at_one_that_is() {
    let all = maps();
    let before = poses(&all, &rows(&all)).unwrap();
    // Map 8 quantizes Chubby2:2 its own way and nothing in it walks or
    // turns: its bank only needs the pose a still one would show.
    let mut some = maps();
    showing(&mut some[1], "Chubby2", &[7]);
    let after = poses(&some, &rows(&some)).unwrap();
    assert!(
        after
            .notes
            .iter()
            .any(|n| n.contains("11 of 36 never shown")),
        "{:?}",
        after.notes
    );
    assert!(defined(&after.text) < defined(&before.text));
    let labels = &after.per_map[1][&("Chubby2".to_string(), 2)];
    assert_eq!(labels.len(), 12);
    assert!(labels.iter().all(|l| *l == labels[7]), "{labels:?}");
    // Map 7's, another quantization, keeps its twelve.
    assert_eq!(after.per_map[0], before.per_map[0]);
}

#[test]
fn a_still_one_that_only_turns_needs_the_four_facings_of_its_column() {
    // Map 7's event 2, People1:1 facing down, with a page that turns toward
    // the hero: made still, and without the command 34 that also dresses
    // the hero with it.
    let mut still = maps();
    still[0].movable.clear();
    still[0].sprite.as_mut().unwrap().route_gfx.clear();
    let none = vec![Vec::new(), Vec::new()];
    showing(&mut still[0], "People1", &[1, 4, 7, 10]);
    showing(&mut still[1], "People1", &[1, 4, 7, 10]);
    assert!(poses(&still, &none).is_ok());
    showing(&mut still[0], "People1", &[7]);
    showing(&mut still[1], "People1", &[7]);
    let Err(e) = poses(&still, &none) else {
        panic!("a turn would show a pose the cartridge left out");
    };
    assert!(
        e.to_string()
            .contains("People1:1 can show poses [1, 4, 10]"),
        "{e}"
    );
}

#[test]
fn one_that_walks_needs_all_twelve() {
    let mut walks = maps();
    showing(&mut walks[0], "People1", &[1, 4, 7, 10]);
    showing(&mut walks[1], "People1", &[1, 4, 7, 10]);
    let Err(e) = poses(&walks, &rows(&walks)) else {
        panic!("a walker would show a pose the cartridge left out");
    };
    assert!(
        e.to_string()
            .contains("People1:1 can show poses [0, 2, 3, 5, 6, 8, 9, 11]"),
        "{e}"
    );
}

#[test]
fn a_stand_in_faces_the_same_way() {
    let facings = BTreeSet::from([1, 4, 7, 10]);
    assert_eq!(stand_in(6, &facings), 7);
    assert_eq!(stand_in(11, &facings), 10);
    assert_eq!(stand_in(4, &facings), 4);
    // Without its direction, its column; without either, the first.
    let two = BTreeSet::from([3, 7]);
    assert_eq!(stand_in(0, &two), 3);
    assert_eq!(stand_in(1, &BTreeSet::from([5])), 5);
}

#[test]
fn in_a_cache_only_the_turners_need_their_facings() {
    // El Dorado's map 12: pressure plates a route turns, and arrowheads of
    // the same character that never turn, in other columns. Here map 7's
    // People1:1, entry 1, as two still ones of a cache: event 2 a turner
    // facing right in the middle column, event 3 facing down on the left.
    let mut map = maps().remove(0);
    map.movable.clear();
    map.turning.clear();
    let sprite = map.sprite.as_mut().unwrap();
    sprite.route_gfx.clear();
    sprite.cache = Some(Cache {
        events: vec![(2, Some(0), 0), (3, Some(1), 0)],
        stills: vec![
            ("People1".into(), 1, 4, 1, 0),
            ("People1".into(), 1, 6, 1, 0),
        ],
        slots: vec![],
        turners: [2].into(),
    });
    let asked = requested(&map, &[]).unwrap();
    assert_eq!(asked[&1], BTreeSet::from([1, 4, 6, 7, 10]));
}
