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
        "patches of 0 map(s) -> parches/auto/mapas (0 B)\n\
         patches of 0 animation(s) -> parches/auto/animaciones (0 B)\n\
         patches of 0 battler(s) -> parches/auto/battlers (0 B)\n"
    );
    let left: Vec<_> = old.iter().filter(|p| p.exists()).collect();
    assert!(left.is_empty(), "patches of a previous run were left: {left:?}");
}

#[test]
fn the_converter_writes_one_build_and_only_one() {
    let dir = scratch("one");
    let out = run(&dir, &["--request", &game("release.json"), "a", "b"]);
    assert_eq!(out.status.code(), Some(1));
    assert!(text(&out.stderr).contains("one build's patches"), "{}", text(&out.stderr));
    std::fs::write(dir.join("broken.json"), "{\"maps\": [{\"id\": 1}]}").unwrap();
    let out = run(&dir, &["--request", "broken.json", "build"]);
    assert_eq!(out.status.code(), Some(1));
    assert!(text(&out.stderr).starts_with("broken.json: "), "{}", text(&out.stderr));
    let out = run(&dir, &["--request", "broken.json", "--check"]);
    assert_eq!(out.status.code(), Some(2), "a wrong call is 2");
}

#[test]
fn what_is_copied_is_checked_and_what_is_touched_fails() {
    let dir = scratch("check");
    project(&dir);
    let out = run(&dir, &["--request", &game("release.json"), "build/release"]);
    assert!(out.status.success(), "{}", text(&out.stderr));
    std::fs::copy(game("uses.json"), dir.join("build/release/parches/usos.json")).unwrap();
    let out = run(&dir, &["build/release"]);
    assert!(out.status.success(), "{}", text(&out.stderr));
    assert_eq!(
        text(&out.stdout),
        "3 patch(es) in patches/auto/mapas, 2898 B\n\
         2 patch(es) in patches/auto/animaciones, 1577 B\n\
         2 patch(es) in patches/auto/battlers, 1757 B\n"
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
         and 1 that only exist for the suite, which decide on their own: ghost\n"
    );
    let versioned = dir.join("patches/auto/animaciones/0001.toml");
    let touched = std::fs::read_to_string(&versioned)
        .unwrap()
        .replace("tamano = [56, 64]", "tamano = [56, 63]");
    std::fs::write(&versioned, touched).unwrap();
    let out = run(&dir, &["--check", "build/release"]);
    assert_eq!(out.status.code(), Some(1));
    assert_eq!(
        text(&out.stderr),
        "  patches/auto/animaciones/0001.toml is stale (cartridge «release» says so), and \
         what changed in animation 1 is this:\n    it was drawn at 56x63 and now it is drawn \
         at 56x64\n  If the change is the one intended, `just parches` and commit; if not, \
         something moved what is seen.\n1 patch(es) do not match what the converter decides\n"
    );
    // And copying twice is what the playable ROM gives, and nothing else.
    let out = run(&dir, &["build/release", "build/release"]);
    assert_eq!(out.status.code(), Some(1));
    assert!(text(&out.stderr).contains("not 2 cartridges"), "{}", text(&out.stderr));
}

#[test]
fn what_only_the_tests_ask_for_needs_no_patch() {
    // The ROM that is played also carries the maps and the pages of the
    // tests, and that is not versioned: a test map, and an animation or a
    // battler that only the test maps or the test pages ask for. What a map
    // of the game also asks for, or what says nothing of who asked, is.
    let dir = scratch("uses");
    std::fs::create_dir_all(dir.join("parches")).unwrap();
    std::fs::write(
        dir.join("parches/usos.json"),
        r#"{"animacion": {"91": ["caso"], "92": [52, "caso"], "93": [3, 52]},
            "battler": {"only-test": [52], "both": ["caso", 3]}}"#,
    )
    .unwrap();
    let tests: BTreeSet<i64> = [52].into();
    let of_tests = |kind, which| only_for_tests(&dir, kind, &which, &tests).unwrap();
    assert!(of_tests(Kind::Map, Key::Number(52)));
    assert!(!of_tests(Kind::Map, Key::Number(3)));
    assert!(of_tests(Kind::Animation, Key::Number(91)));
    assert!(of_tests(Kind::Animation, Key::Number(92)));
    assert!(!of_tests(Kind::Animation, Key::Number(93)));
    assert!(!of_tests(Kind::Animation, Key::Number(94)), "without an origin it is the game's");
    assert!(of_tests(Kind::Battler, Key::Text("only-test".into())));
    assert!(!of_tests(Kind::Battler, Key::Text("both".into())));
    let nowhere = dir.join("without-uses");
    assert!(!only_for_tests(&nowhere, Kind::Animation, &Key::Number(91), &tests).unwrap());
}
