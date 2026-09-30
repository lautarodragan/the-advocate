//! The executable: the map it reads —the dump's, the project's, with what
//! was baked into it—, what it writes, and how it says no.
//!
//! A small game —one map, one ChipSet entry and its picture— is generated
//! inside each test, so none of this needs a game. What the executable
//! writes is checked against the libraries it is made of, called here
//! directly on the map the test knows it should have read.

use rm2k_render::{picture, Atlas, Map, Picture};
use rm2k_snes_map_background::convert;
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("rm2k-snes-maps-cli-{}-{name}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn run(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_rm2k-snes-maps"))
        .args(args)
        .output()
        .unwrap()
}

/// A ChipSet whose pixels come from a formula, written as
/// `<dir>/ChipSet/<file>`.
fn chipset_picture(dir: &Path, file: &str, seed: usize) -> PathBuf {
    let folder = dir.join("ChipSet");
    std::fs::create_dir_all(&folder).unwrap();
    let rgba = (0..256usize)
        .flat_map(|y| {
            (0..480usize).flat_map(move |x| {
                let k = (x / 3 + y / 5 * 7 + seed) % 37;
                [(k * 7) as u8, (k * 29 % 256) as u8, ((x ^ y) & 0xF8) as u8, 255]
            })
        })
        .collect();
    let path = folder.join(file);
    picture::write_png(&path, &Picture { width: 480, height: 256, rgba }).unwrap();
    path
}

const WIDTH: usize = 6;
const HEIGHT: usize = 4;

/// Water, an animated tile, terrain and plain tiles below; a few tiles
/// above, one of them over the hero.
fn lower() -> Vec<i64> {
    (0..WIDTH * HEIGHT)
        .map(|i| match i % 6 {
            0 => 0,
            1 => 3050,
            2 => 4000 + (i as i64 % 3),
            _ => 5000 + i as i64,
        })
        .collect()
}

fn upper() -> Vec<i64> {
    (0..WIDTH * HEIGHT)
        .map(|i| if i % 5 == 0 { 10001 + i as i64 % 3 } else { 10000 })
        .collect()
}

fn passability() -> (Vec<u8>, Vec<u8>) {
    let mut upper = vec![15u8; 144];
    upper[1] = 0x1F; // the star: above the hero
    (vec![15u8; 162], upper)
}

fn chipset_entry(id: i64, name: &str) -> Value {
    let (lower, upper) = passability();
    json!({"id": id, "chipset_name": name,
           "passable_data_lower": lower, "passable_data_upper": upper})
}

fn tiles_file(lower: &[i64], upper: &[i64]) -> String {
    let rows = |layer: &[i64]| {
        layer
            .chunks(WIDTH)
            .map(|r| r.iter().map(|t| format!("{t:6}")).collect::<String>())
            .collect::<Vec<_>>()
            .join("\n")
    };
    format!("# {WIDTH}x{HEIGHT}\n# lower\n{}\n# upper\n{}\n", rows(lower), rows(upper))
}

/// A Ditto dump in `<dir>/dump` with map 7 and ChipSet 2, and the game's
/// pictures in `<dir>/game`.
fn game(dir: &Path) -> (PathBuf, PathBuf) {
    let dump = dir.join("dump");
    let maps = dump.join("maps");
    let db = dump.join("db");
    std::fs::create_dir_all(&maps).unwrap();
    std::fs::create_dir_all(&db).unwrap();
    std::fs::write(dump.join("ditto.json"), json!({"ditto": 2, "view": "resolved"}).to_string())
        .unwrap();
    map_file(&maps.join("Map0007.json"), 2, &lower(), &upper());
    std::fs::write(db.join("chipsets.json"), json!([chipset_entry(2, "tiles")]).to_string())
        .unwrap();
    let pictures = dir.join("game");
    chipset_picture(&pictures, "Tiles.png", 0);
    (dump, pictures)
}

fn map_file(path: &Path, chipset: i64, lower: &[i64], upper: &[i64]) {
    std::fs::write(
        path,
        json!({"chipset_id": chipset, "width": WIDTH, "height": HEIGHT}).to_string(),
    )
    .unwrap();
    std::fs::write(path.with_extension("tiles"), tiles_file(lower, upper)).unwrap();
}

fn request(dir: &Path, body: Value) -> PathBuf {
    let path = dir.join("request.json");
    std::fs::write(&path, body.to_string()).unwrap();
    path
}

fn layers(dump: &Path, search: &[&Path], request: &Path, out: &Path) -> Output {
    let mut args = vec![
        "layers".to_string(),
        "--data".to_string(),
        dump.display().to_string(),
        "--request".to_string(),
        request.display().to_string(),
        "--out".to_string(),
        out.display().to_string(),
    ];
    for dir in search {
        args.push("--search-dir".to_string());
        args.push(dir.display().to_string());
    }
    run(&args.iter().map(String::as_str).collect::<Vec<_>>())
}

/// What the libraries make of this map, to hold the executable's files
/// against.
fn expected(chipset: &Path, lower: Vec<i64>, upper: Vec<i64>) -> rm2k_snes_map_background::Converted {
    let (passable_lower, passable_upper) = passability();
    let map = Map {
        width: WIDTH,
        height: HEIGHT,
        lower_layer: lower,
        upper_layer: upper,
        passable_lower,
        passable_upper,
    };
    let atlas = Atlas::new(&picture::read_rm2k(chipset).unwrap());
    convert(&map.render(&atlas).unwrap()).unwrap()
}

fn check(out: &Path, want: &rm2k_snes_map_background::Converted) {
    assert_eq!(std::fs::read(out.join("background.bin")).unwrap(), want.background.tiles);
    assert_eq!(std::fs::read(out.join("above.bin")).unwrap(), want.above.tiles);
    assert_eq!(std::fs::read(out.join("above-cgram.bin")).unwrap(), want.above.cgram);
    let answer: Value =
        serde_json::from_str(&std::fs::read_to_string(out.join("layers.json")).unwrap()).unwrap();
    assert_eq!(answer["background"]["cgram"], json!(want.background.cgram));
    assert_eq!(answer["background"]["tilemap"], json!(want.background.tilemap));
    assert_eq!(answer["above"]["tilemap"], json!(want.above.tilemap));
    assert_eq!(answer["above"]["first"], json!(want.above.first));
    let runs = answer["background"]["runs"].as_array().unwrap();
    assert_eq!(runs.len(), want.background.runs.len());
    for (run, wanted) in runs.iter().zip(&want.background.runs) {
        assert_eq!(run["family"], json!(wanted.family.name()));
        for (file, drawing) in run["drawings"].as_array().unwrap().iter().zip(&wanted.drawings) {
            assert_eq!(&std::fs::read(out.join(file.as_str().unwrap())).unwrap(), drawing);
        }
    }
    let pictures: Vec<&str> = answer["pictures"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| p["name"].as_str().unwrap())
        .collect();
    let wanted: Vec<&str> = want.pictures.iter().map(|p| p.name.as_str()).collect();
    assert_eq!(pictures, wanted);
    for p in answer["pictures"].as_array().unwrap() {
        let read = voodoo::image::read(&out.join(p["file"].as_str().unwrap())).unwrap();
        let decided = &want.pictures.iter().find(|d| d.name == p["name"]).unwrap().picture;
        assert_eq!(read.pixels, decided.pixels);
    }
}

#[test]
fn the_dumps_map_is_drawn_and_converted() {
    let dir = scratch("dump");
    let (dump, pictures) = game(&dir);
    let req = request(&dir, json!({"map": 7, "map_files": {}, "chipset_files": {}, "baked": []}));
    let out = dir.join("out");
    let done = layers(&dump, &[&dir.join("nowhere"), &pictures], &req, &out);
    assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
    let want = expected(&pictures.join("ChipSet/Tiles.png"), lower(), upper());
    assert!(!want.background.runs.is_empty(), "the map should animate");
    check(&out, &want);
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn the_projects_map_and_chipset_win_over_the_dumps() {
    let dir = scratch("fork");
    let (dump, pictures) = game(&dir);
    // The project's map 7, drawn with a ChipSet only the project has, whose
    // picture is in a search directory that comes first.
    let mut changed = lower();
    changed.reverse();
    let forked = dir.join("fork").join("Map0007.json");
    std::fs::create_dir_all(forked.parent().unwrap()).unwrap();
    map_file(&forked, 53, &changed, &upper());
    let added = dir.join("fork").join("0053.json");
    std::fs::write(&added, json!({"chipset": chipset_entry(53, "Other")}).to_string()).unwrap();
    let built = dir.join("built");
    chipset_picture(&built, "other.png", 11);
    let req = request(
        &dir,
        json!({"map": 7, "map_files": {"7": forked}, "chipset_files": {"53": added},
               "baked": []}),
    );
    let out = dir.join("out");
    let done = layers(&dump, &[&built, &pictures], &req, &out);
    assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
    check(&out, &expected(&built.join("ChipSet/other.png"), changed, upper()));
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_baked_cell_is_painted_into_the_upper_layer() {
    let dir = scratch("baked");
    let (dump, pictures) = game(&dir);
    let req = request(
        &dir,
        json!({"map": 7, "map_files": {}, "chipset_files": {},
               "baked": [[3, 10004], [8, 10006]]}),
    );
    let out = dir.join("out");
    let done = layers(&dump, &[&pictures], &req, &out);
    assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
    let mut baked = upper();
    baked[3] = 10004;
    baked[8] = 10006;
    check(&out, &expected(&pictures.join("ChipSet/Tiles.png"), lower(), baked));
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn what_cannot_be_done_is_an_answer_and_a_wrong_call_is_misuse() {
    let dir = scratch("errors");
    let (dump, pictures) = game(&dir);
    let out = dir.join("out");
    let plain = json!({"map": 7, "map_files": {}, "chipset_files": {}, "baked": []});

    // No picture for the ChipSet anywhere.
    let req = request(&dir, plain.clone());
    let done = layers(&dump, &[&dir.join("nowhere")], &req, &out);
    assert_eq!(done.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&done.stderr).contains("chipset of map 7"));

    // A ChipSet the project adds that the dump already has.
    let added = dir.join("0002.json");
    std::fs::write(&added, json!({"chipset": chipset_entry(2, "tiles")}).to_string()).unwrap();
    let mut both = plain.clone();
    both["chipset_files"] = json!({"2": added});
    let done = layers(&dump, &[&pictures], &request(&dir, both), &out);
    assert_eq!(done.status.code(), Some(1));
    assert!(String::from_utf8_lossy(&done.stderr).contains("does not replace"));

    // A baked cell past the map.
    let mut past = plain.clone();
    past["baked"] = json!([[WIDTH * HEIGHT, 10001]]);
    let done = layers(&dump, &[&pictures], &request(&dir, past), &out);
    assert_eq!(done.status.code(), Some(1));

    // A request without what it has to say.
    let done = layers(&dump, &[&pictures], &request(&dir, json!({"map": 7})), &out);
    assert_eq!(done.status.code(), Some(1));

    // No request file, and no --out.
    let done = layers(&dump, &[&pictures], &dir.join("missing.json"), &out);
    assert_eq!(done.status.code(), Some(2));
    let done = run(&["layers", "--data", dump.to_str().unwrap()]);
    assert_eq!(done.status.code(), Some(2));
    std::fs::remove_dir_all(&dir).unwrap();
}
