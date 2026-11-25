//! Copying and checking what is versioned, as `advocate build` does it
//! —with `--write-patches`, and on every build—, over builds written as the
//! converter writes them; and what the tests of a cartridge carry that is
//! not the game's. Until 2026-11-25 this ran the `rm2k-snes-patches`
//! binary, which did both.

use rm2k_snes_patches::{
    check, copy, only_for_tests, put, report, stage, Checked, Key, Kind, Request,
};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-snes-patches-copy-{name}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

/// The project's test maps, in every test here.
fn tests() -> BTreeSet<i64> {
    [52].into()
}

/// Writes `build`'s decisions over `dir`'s `patches/auto/`, and says what it
/// wrote, a line per kind, as `advocate build --write-patches` prints it.
fn write(dir: &Path, build: &str) -> String {
    let auto = dir.join("patches/auto");
    Kind::ALL
        .into_iter()
        .map(|kind| {
            let (count, bytes, removed) = copy(&auto, &dir.join(build), kind, &tests()).unwrap();
            assert!(removed.is_empty(), "{removed:?}");
            format!(
                "{count} patch(es) in patches/auto/{}, {bytes} B\n",
                kind.directory()
            )
        })
        .collect()
}

/// `dir`'s `patches/auto/` against what the `builds` decided.
fn checked(dir: &Path, builds: &[&str]) -> Checked {
    let builds: Vec<PathBuf> = builds.iter().map(|b| dir.join(b)).collect();
    check(&dir.join("patches/auto"), &builds, &tests(), dir).unwrap()
}

/// What only some cartridge decided, by kind, with its keys.
fn own(checked: &Checked) -> Vec<(Kind, Vec<String>)> {
    checked
        .own
        .iter()
        .map(|(kind, keys)| (*kind, keys.keys().map(|k| k.to_string()).collect()))
        .collect()
}

/// What the converter leaves in `build`, inside `dir`, for the request in
/// the file `file`, as it does it: `stage::patches` and `put`. What `put`
/// reports, a line each.
fn convert(dir: &Path, file: &str, build: &str) -> String {
    let request: Request =
        serde_json::from_str(&std::fs::read_to_string(dir.join(file)).unwrap()).unwrap();
    put(&dir.join(build), &stage::patches(&request))
        .unwrap()
        .iter()
        .map(|written| report(written) + "\n")
        .collect()
}

fn game(name: &str) -> String {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/game")
        .join(name)
        .display()
        .to_string()
}

#[test]
fn writing_a_build_again_leaves_nothing_from_the_previous_run() {
    // A cartridge that stops carrying a map, an animation or a battler cannot
    // keep its patch next to the ROM: the check looks at what is in the
    // directory, and an old `.toml` counts as converted.
    let dir = scratch("again");
    let mut old = Vec::new();
    for kind in Kind::ALL {
        let folder = dir.join("build").join(kind.in_build());
        std::fs::create_dir_all(&folder).unwrap();
        old.push(folder.join("9999.toml"));
        std::fs::write(old.last().unwrap(), "from the previous run\n").unwrap();
    }
    std::fs::write(dir.join("empty.json"), "{}").unwrap();
    assert_eq!(
        convert(&dir, "empty.json", "build"),
        "patches of 0 map(s) -> patches/auto/maps (0 B)\n\
         patches of 0 animation(s) -> patches/auto/animations (0 B)\n\
         patches of 0 battler(s) -> patches/auto/battlers (0 B)\n\
         patches of 0 window(s) -> patches/auto/windows (0 B)\n"
    );
    let left: Vec<_> = old.iter().filter(|p| p.exists()).collect();
    assert!(
        left.is_empty(),
        "patches of a previous run were left: {left:?}"
    );
}

#[test]
fn what_is_copied_is_checked_and_what_is_touched_fails() {
    let dir = scratch("check");
    convert(&dir, &game("release.json"), "build/release");
    std::fs::copy(
        game("uses.json"),
        dir.join("build/release/patches/uses.json"),
    )
    .unwrap();
    assert_eq!(
        write(&dir, "build/release"),
        "3 patch(es) in patches/auto/maps, 2933 B\n\
         2 patch(es) in patches/auto/animations, 1599 B\n\
         2 patch(es) in patches/auto/battlers, 1775 B\n\
         0 patch(es) in patches/auto/windows, 0 B\n"
    );
    let matching = checked(&dir, &["build/release"]);
    assert_eq!(matching.complaints, Vec::<String>::new());
    assert_eq!(
        own(&matching),
        [
            (Kind::Map, vec!["52".to_string()]),
            (Kind::Animation, vec!["91".to_string()]),
            (Kind::Battler, vec!["ghost".to_string()]),
        ]
    );
    let versioned = dir.join("patches/auto/animations/0001.toml");
    let touched = std::fs::read_to_string(&versioned)
        .unwrap()
        .replace("size = [56, 64]", "size = [56, 63]");
    std::fs::write(&versioned, touched).unwrap();
    assert_eq!(
        checked(&dir, &["build/release"]).complaints,
        [
            "patches/auto/animations/0001.toml is stale (cartridge «release» says so), and \
         what changed in animation 1 is this:\n    it was drawn at 56x63 and now it is drawn \
         at 56x64\n  If the change is the one intended, run `advocate build --write-patches` \
         and commit; if not, something moved what is seen."
        ]
    );
}

#[test]
fn a_window_that_lost_colours_is_written_and_checked() {
    let dir = scratch("window");
    std::fs::write(
        dir.join("window.json"),
        r#"{"windows": [{"system": "Gold Skin", "colors": 17, "kept": 15,
             "merges": [[[1, 2, 3], [1, 2, 4], 40], [[9, 9, 9], [8, 8, 8], 7]]}]}"#,
    )
    .unwrap();
    convert(&dir, "window.json", "build/release");
    write(&dir, "build/release");
    let versioned = dir.join("patches/auto/windows/Gold_Skin.toml");
    let written = std::fs::read_to_string(&versioned).unwrap();
    assert!(written.contains("system = \"Gold Skin\"\n"), "{written}");
    assert!(
        written.contains("  { from = [9, 9, 9], to = [8, 8, 8], pixels = 7 },\n"),
        "{written}"
    );
    assert_eq!(
        checked(&dir, &["build/release"]).complaints,
        Vec::<String>::new()
    );

    std::fs::write(
        &versioned,
        written.replace("to = [8, 8, 8]", "to = [7, 7, 7]"),
    )
    .unwrap();
    let said = checked(&dir, &["build/release"]).complaints.join("\n");
    assert!(said.contains("in window Gold Skin is this:"), "{said}");
    assert!(
        said.contains("merges [9, 9, 9] -> [8, 8, 8], which it did not"),
        "{said}"
    );
    assert!(
        said.contains("no longer merges [9, 9, 9] -> [7, 7, 7]"),
        "{said}"
    );
}

#[test]
fn what_only_the_tests_ask_for_needs_no_patch() {
    // The ROM that is played also carries the maps and the pages of the
    // tests, and that is not versioned: a test map, and an animation or a
    // battler that only the test maps or the test pages ask for. What a map
    // of the game also asks for, or what says nothing of who asked, is.
    let dir = scratch("uses");
    std::fs::create_dir_all(dir.join("patches")).unwrap();
    std::fs::write(
        dir.join("patches/uses.json"),
        r#"{"animation": {"91": ["case"], "92": [52, "case"], "93": [3, 52]},
            "battler": {"only-test": [52], "both": ["case", 3]}}"#,
    )
    .unwrap();
    let tests: BTreeSet<i64> = [52].into();
    let of_tests = |kind, which| only_for_tests(&dir, kind, &which, &tests).unwrap();
    assert!(of_tests(Kind::Map, Key::Number(52)));
    assert!(!of_tests(Kind::Map, Key::Number(3)));
    assert!(of_tests(Kind::Animation, Key::Number(91)));
    assert!(of_tests(Kind::Animation, Key::Number(92)));
    assert!(!of_tests(Kind::Animation, Key::Number(93)));
    assert!(
        !of_tests(Kind::Animation, Key::Number(94)),
        "without an origin it is the game's"
    );
    assert!(of_tests(Kind::Battler, Key::Text("only-test".into())));
    assert!(!of_tests(Kind::Battler, Key::Text("both".into())));
    let nowhere = dir.join("without-uses");
    assert!(!only_for_tests(&nowhere, Kind::Animation, &Key::Number(91), &tests).unwrap());
}
