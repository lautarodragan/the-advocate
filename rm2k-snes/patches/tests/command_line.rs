//! The binary as its callers see it —the converter, and whoever copies and
//! checks what is versioned—, and what the tests of a cartridge carry that is
//! not the game's.

use rm2k_snes_patches::{only_for_tests, Key, Kind};
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};
use std::process::{Command, Output};

fn scratch(name: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!(
        "rm2k-snes-patches-cli-{name}-{}",
        std::process::id()
    ));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    dir
}

fn run(dir: &Path, args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_rm2k-snes-patches"))
        .current_dir(dir)
        .args(args)
        .output()
        .unwrap()
}

fn text(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

fn game(name: &str) -> String {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/game")
        .join(name)
        .display()
        .to_string()
}

/// A project whose test maps are `[52]`, with its patches in `patches/`.
fn project(dir: &Path) {
    std::fs::write(
        dir.join("rm2k-snes.toml"),
        "[paths]\npatches = \"patches\"\nbuild = \"build\"\n\n[maps]\ntest = [52]\n",
    )
    .unwrap();
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
    let out = run(&dir, &["--request", "empty.json", "build"]);
    assert!(out.status.success(), "{}", text(&out.stderr));
    assert_eq!(
        text(&out.stdout),
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
fn the_converter_writes_one_build_and_only_one() {
    let dir = scratch("one");
    let out = run(&dir, &["--request", &game("release.json"), "a", "b"]);
    assert_eq!(out.status.code(), Some(1));
    assert!(
        text(&out.stderr).contains("one build's patches"),
        "{}",
        text(&out.stderr)
    );
    std::fs::write(dir.join("broken.json"), "{\"maps\": [{\"id\": 1}]}").unwrap();
    let out = run(&dir, &["--request", "broken.json", "build"]);
    assert_eq!(out.status.code(), Some(1));
    assert!(
        text(&out.stderr).starts_with("broken.json: "),
        "{}",
        text(&out.stderr)
    );
    let out = run(&dir, &["--request", "broken.json", "--check"]);
    assert_eq!(out.status.code(), Some(2), "a wrong call is 2");
}

#[test]
fn what_is_copied_is_checked_and_what_is_touched_fails() {
    let dir = scratch("check");
    project(&dir);
    let out = run(&dir, &["--request", &game("release.json"), "build/release"]);
    assert!(out.status.success(), "{}", text(&out.stderr));
    std::fs::copy(
        game("uses.json"),
        dir.join("build/release/patches/uses.json"),
    )
    .unwrap();
    let out = run(&dir, &["build/release"]);
    assert!(out.status.success(), "{}", text(&out.stderr));
    assert_eq!(
        text(&out.stdout),
        "3 patch(es) in patches/auto/maps, 2933 B\n\
         2 patch(es) in patches/auto/animations, 1599 B\n\
         2 patch(es) in patches/auto/battlers, 1775 B\n\
         0 patch(es) in patches/auto/windows, 0 B\n"
    );
    // A directory with cartridges inside is the same as naming them.
    let out = run(&dir, &["--check", "build"]);
    assert!(out.status.success(), "{}", text(&out.stderr));
    assert_eq!(
        text(&out.stdout),
        "the game's 3 patch(es) of map(s) match what 1 cartridge(s) decided\n  \
         and 1 that only exist for the suite, which decide on their own: 52\n\
         the game's 2 patch(es) of animation(s) match what 1 cartridge(s) decided\n  \
         and 1 that only exist for the suite, which decide on their own: 91\n\
         the game's 2 patch(es) of battler(s) match what 1 cartridge(s) decided\n  \
         and 1 that only exist for the suite, which decide on their own: ghost\n\
         the game's 0 patch(es) of window(s) match what 1 cartridge(s) decided\n"
    );
    let versioned = dir.join("patches/auto/animations/0001.toml");
    let touched = std::fs::read_to_string(&versioned)
        .unwrap()
        .replace("size = [56, 64]", "size = [56, 63]");
    std::fs::write(&versioned, touched).unwrap();
    let out = run(&dir, &["--check", "build/release"]);
    assert_eq!(out.status.code(), Some(1));
    assert_eq!(
        text(&out.stderr),
        "  patches/auto/animations/0001.toml is stale (cartridge «release» says so), and \
         what changed in animation 1 is this:\n    it was drawn at 56x63 and now it is drawn \
         at 56x64\n  If the change is the one intended, run `rm2k-snes-patches` on the \
         playable ROM's build and commit; if not, something moved what is seen.\n1 patch(es) do not match what the converter decides\n"
    );
    // And copying twice is what the playable ROM gives, and nothing else.
    let out = run(&dir, &["build/release", "build/release"]);
    assert_eq!(out.status.code(), Some(1));
    assert!(
        text(&out.stderr).contains("not 2 cartridges"),
        "{}",
        text(&out.stderr)
    );
}

#[test]
fn a_window_that_lost_colours_is_written_and_checked() {
    let dir = scratch("window");
    project(&dir);
    std::fs::write(
        dir.join("window.json"),
        r#"{"windows": [{"system": "Gold Skin", "colors": 17, "kept": 15,
             "merges": [[[1, 2, 3], [1, 2, 4], 40], [[9, 9, 9], [8, 8, 8], 7]]}]}"#,
    )
    .unwrap();
    let out = run(&dir, &["--request", "window.json", "build/release"]);
    assert!(out.status.success(), "{}", text(&out.stderr));
    let out = run(&dir, &["build/release"]);
    assert!(out.status.success(), "{}", text(&out.stderr));
    let versioned = dir.join("patches/auto/windows/Gold_Skin.toml");
    let written = std::fs::read_to_string(&versioned).unwrap();
    assert!(written.contains("system = \"Gold Skin\"\n"), "{written}");
    assert!(
        written.contains("  { from = [9, 9, 9], to = [8, 8, 8], pixels = 7 },\n"),
        "{written}"
    );
    let out = run(&dir, &["--check", "build/release"]);
    assert!(out.status.success(), "{}", text(&out.stderr));

    std::fs::write(
        &versioned,
        written.replace("to = [8, 8, 8]", "to = [7, 7, 7]"),
    )
    .unwrap();
    let out = run(&dir, &["--check", "build/release"]);
    assert_eq!(out.status.code(), Some(1));
    let said = text(&out.stderr);
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
