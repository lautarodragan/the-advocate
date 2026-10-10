//! `face`, `system` and `picture` from the command line: a request with
//! relative paths, one picture per entry, and how they say no.

use rm2k_render::{picture, Picture};
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-render-screens-cli-{}-{name}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// `rm2k-render <command>` with `entries` as the request, written in `dir`,
/// and the pictures into `dir/out`.
fn draw(dir: &Path, command: &str, entries: serde_json::Value) -> Output {
    let path = dir.join("request.json");
    std::fs::write(&path, entries.to_string()).unwrap();
    Command::new(env!("CARGO_BIN_EXE_rm2k-render"))
        .args([
            command,
            "--request",
            path.to_str().unwrap(),
            "--out",
            dir.join("out").to_str().unwrap(),
        ])
        .output()
        .unwrap()
}

fn drawn(dir: &Path, i: usize) -> Picture {
    picture::read_rgba(&dir.join("out").join(format!("{i}.png"))).unwrap()
}

/// An indexed picture of `width` x `height` in `dir/<file>`: index 0 is
/// red, and every other pixel is index 1, green, except pixel `(x, y)`
/// with `x % 8 == 0 && y % 8 == 0`, which is 0.
fn sheet(dir: &Path, file: &str, width: u32, height: u32) {
    let path = dir.join(file);
    std::fs::create_dir_all(path.parent().unwrap()).unwrap();
    let mut encoder = png::Encoder::new(std::fs::File::create(&path).unwrap(), width, height);
    encoder.set_color(png::ColorType::Indexed);
    encoder.set_depth(png::BitDepth::Eight);
    encoder.set_palette(vec![255, 0, 0, 0, 255, 0]);
    let pixels: Vec<u8> = (0..height)
        .flat_map(|y| (0..width).map(move |x| u8::from(x % 8 != 0 || y % 8 != 0)))
        .collect();
    let mut writer = encoder.write_header().unwrap();
    writer.write_image_data(&pixels).unwrap();
}

const RED: [u8; 4] = [255, 0, 0, 255];
const GREEN: [u8; 4] = [0, 255, 0, 255];
const KEY: [u8; 4] = [255, 0, 0, 0];

#[test]
fn a_face_request_draws_one_face_per_entry() {
    let dir = scratch("face");
    sheet(&dir, "FaceSet/Faces.png", 192, 192);
    let done = draw(
        &dir,
        "face",
        serde_json::json!([
            {"faceset_file": "FaceSet/Faces.png", "index": 0},
            {"faceset_file": "FaceSet/Faces.png", "index": 15},
        ]),
    );
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    for i in 0..2 {
        let face = drawn(&dir, i);
        assert_eq!((face.width, face.height), (48, 48));
        assert_eq!(face.get(0, 0), KEY, "the colour key");
        assert_eq!(face.get(1, 0), GREEN);
    }
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_system_request_draws_each_kind_of_piece() {
    let dir = scratch("system");
    sheet(&dir, "System/Skin.png", 160, 80);
    let system = "System/Skin.png";
    let done = draw(
        &dir,
        "system",
        serde_json::json!([
            {"system_file": system, "draw": "window", "width": 100, "height": 40,
             "message_stretch": 0},
            {"system_file": system, "draw": "window", "width": 100, "height": 40,
             "message_stretch": 1},
            {"system_file": system, "draw": "cursor", "width": 50, "height": 16},
            {"system_file": system, "draw": "cursor", "width": 50, "height": 16,
             "drawing": 1},
            {"system_file": system, "draw": "text_color", "color": 19},
            {"system_file": system, "draw": "shadow"},
            {"system_file": system, "draw": "timer"},
        ]),
    );
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    let sizes: Vec<(usize, usize)> = (0..7)
        .map(|i| drawn(&dir, i))
        .map(|p| (p.width, p.height))
        .collect();
    assert_eq!(
        sizes,
        [
            (100, 40),
            (100, 40),
            (50, 16),
            (50, 16),
            (16, 16),
            (16, 16),
            (88, 16)
        ]
    );
    // Tiled, the background's key pixels repeat every 8 inside the window;
    // stretched from 32 to 100 across, column 32 of the window is not one.
    assert_eq!(drawn(&dir, 1).get(32, 16), KEY);
    assert_eq!(drawn(&dir, 0).get(32, 16), GREEN);
    // The frame's corner is drawn over the background through its colour
    // key: where the corner has the key, the background shows, and the
    // stretched background's pixel (0, 0) is the System's, the key too.
    assert_eq!(drawn(&dir, 0).get(0, 0), KEY);
    assert_eq!(drawn(&dir, 0).get(1, 1), GREEN);
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn a_picture_request_honours_the_transparent_colour_and_the_transparency() {
    let dir = scratch("picture");
    sheet(&dir, "Picture/Sign.png", 30, 20);
    let done = draw(
        &dir,
        "picture",
        serde_json::json!([
            {"picture_file": "Picture/Sign.png"},
            {"picture_file": "Picture/Sign.png", "use_transparent_color": true},
            {"picture_file": "Picture/Sign.png", "use_transparent_color": true,
             "top_trans": 50},
        ]),
    );
    assert!(
        done.status.success(),
        "{}",
        String::from_utf8_lossy(&done.stderr)
    );
    assert_eq!(
        drawn(&dir, 0).get(0, 0),
        RED,
        "without it, index 0 is drawn"
    );
    assert_eq!(drawn(&dir, 1).get(0, 0), KEY);
    assert_eq!(drawn(&dir, 1).get(1, 0), GREEN);
    assert_eq!(drawn(&dir, 2).get(0, 0), KEY);
    assert_eq!(drawn(&dir, 2).get(1, 0), [0, 255, 0, 127]);
    std::fs::remove_dir_all(&dir).unwrap();
}

#[test]
fn an_entry_that_makes_no_sense_is_an_answer_and_writes_nothing() {
    let dir = scratch("bad");
    sheet(&dir, "Skin.png", 160, 80);
    for (command, entries, says) in [
        (
            "face",
            serde_json::json!([{"faceset_file": "Skin.png", "index": 16}]),
            "`index` is 16",
        ),
        (
            "face",
            serde_json::json!([{"index": 1}]),
            "`faceset_file` is missing",
        ),
        (
            "system",
            serde_json::json!([{"system_file": "Skin.png", "draw": "window", "width": 20,
                                "height": 20, "message_stretch": 2}]),
            "not one RM2k draws",
        ),
        (
            "system",
            serde_json::json!([{"system_file": "Skin.png", "draw": "frame"}]),
            "`draw` is \"frame\"",
        ),
        (
            "system",
            serde_json::json!([{"system_file": "Skin.png", "draw": "cursor", "width": 20,
                                "height": 20, "drawing": 2}]),
            "`drawing` is 2",
        ),
        (
            "picture",
            serde_json::json!([{"picture_file": "Skin.png", "top_trans": 101}]),
            "`top_trans` is 101",
        ),
        (
            "picture",
            serde_json::json!([{"picture_file": "Skin.png"},
                               {"picture_file": "Skin.png",
                                "use_transparent_color": 1}]),
            "entry 1: `use_transparent_color` is not true or false",
        ),
        (
            "picture",
            serde_json::json!({"picture_file": "Skin.png"}),
            "not a list",
        ),
    ] {
        let done = draw(&dir, command, entries);
        assert_eq!(done.status.code(), Some(1), "{command} {says}");
        assert!(
            String::from_utf8_lossy(&done.stderr).contains(says),
            "{}",
            String::from_utf8_lossy(&done.stderr)
        );
        assert!(
            !dir.join("out").exists(),
            "{command} {says} wrote something"
        );
    }
    // A picture that is not there is the call being wrong.
    let done = draw(
        &dir,
        "picture",
        serde_json::json!([{"picture_file": "Nobody.png"}]),
    );
    assert_eq!(done.status.code(), Some(2));
    std::fs::remove_dir_all(&dir).unwrap();
}
