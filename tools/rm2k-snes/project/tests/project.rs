//! The project, its settings, the machine values and the cache key.
//!
//! Most of these are error messages: a setting that is missing has to say
//! which one, because the fix is in a file the tool does not own.

use std::fs;
use std::path::{Path, PathBuf};

use rm2k_project::environment::{arguments, Environment};
use rm2k_project::{cache, Project, FILENAME};

/// A fresh directory under the target dir, one per test.
fn scratch(name: &str) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR")).join(name);
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

const SETTINGS: &str = r#"
[paths]
data = "data"
patches = "decided"
build = "../out"
cases = "tests/cases"

[rom]
name = "game"
title = "A GAME"
flag = true

[maps]
below = 10
excluded = [3, 4]
"#;

fn project() -> Project {
    Project::from_text(Path::new("/games/one"), SETTINGS).unwrap()
}

#[test]
fn the_project_is_found_from_below() {
    let root = scratch("found_from_below");
    fs::write(root.join(FILENAME), "").unwrap();
    let deep = root.join("a/b/c");
    fs::create_dir_all(&deep).unwrap();
    assert_eq!(Project::find(&deep), Some(root.clone()));
    assert_eq!(Project::open(&root).unwrap().directory(), root);
}

#[test]
fn a_directory_without_the_file_says_what_project_means() {
    let root = scratch("without_the_file");
    let error = Project::open(&root).unwrap_err().to_string();
    assert!(error.contains("has no rm2k-snes.toml"), "{error}");
    assert!(error.contains("--project is the directory"), "{error}");
}

#[test]
fn a_missing_key_is_named_up_to_where_it_is_missing() {
    let p = project();
    let error = p.int(&["cartridges", "release", "start_map"]).unwrap_err();
    assert_eq!(
        error.to_string(),
        "/games/one/rm2k-snes.toml: missing key cartridges"
    );
    let error = p.string(&["rom", "nombre"]).unwrap_err();
    assert!(error.to_string().ends_with("missing key rom.nombre"));
}

#[test]
fn a_key_of_another_type_says_both() {
    let p = project();
    let error = p.int(&["rom", "name"]).unwrap_err().to_string();
    assert!(error.ends_with("rom.name must be int and is \"game\""), "{error}");
    // TOML keeps booleans and integers apart, so `true` is not 1.
    assert!(p.int(&["rom", "flag"]).is_err());
    assert!(p.boolean(&["rom", "flag"]).unwrap());
    assert!(p.strings(&["maps", "excluded"]).is_err());
    assert_eq!(p.ints(&["maps", "excluded"]).unwrap(), vec![3, 4]);
}

#[test]
fn ascii_settings_refuse_what_the_rom_cannot_carry() {
    let p = Project::from_text(
        Path::new("/g"),
        "[rom]\ntitle = \"OK TITLE\"\nquoted = 'A \"B\"'\nsign = \"ABLS\"\n",
    )
    .unwrap();
    assert_eq!(p.ascii(&["rom", "title"], None, Some(21)).unwrap(), "OK TITLE");
    assert!(p.ascii(&["rom", "quoted"], None, None).is_err());
    assert!(p.ascii(&["rom", "sign"], Some(4), None).is_ok());
    let error = p.ascii(&["rom", "sign"], Some(5), None).unwrap_err();
    assert!(error.to_string().contains("must have 5 characters, and has 4"));
}

#[test]
fn the_paths_are_relative_to_the_file() {
    let p = project();
    assert_eq!(p.data().unwrap(), PathBuf::from("/games/one/data"));
    assert_eq!(p.build().unwrap(), PathBuf::from("/games/out"));
    assert_eq!(
        p.manual_patches().unwrap(),
        PathBuf::from("/games/one/decided/manual")
    );
    assert_eq!(p.cases().unwrap(), PathBuf::from("/games/one/tests/cases"));
}

#[test]
fn keys_keep_the_order_of_the_file() {
    let p = Project::from_text(Path::new("/g"), "[t]\nzeta = 1\nalpha = 2\nmid = 3\n")
        .unwrap();
    let keys: Vec<_> = p.table(&["t"]).unwrap().keys().cloned().collect();
    assert_eq!(keys, ["zeta", "alpha", "mid"]);
}

#[test]
fn a_machine_value_nobody_passed_is_an_error_with_its_flag() {
    let environment = Environment::default();
    let error = environment.game().unwrap_err().to_string();
    assert!(error.starts_with("missing --game-dir: the original RM2k project"), "{error}");
    assert!(error.contains("whoever runs this passes it"));
}

#[test]
fn the_cache_and_the_test_cartridges_hang_off_the_build() {
    let p = project();
    let mut environment = Environment::default();
    assert_eq!(environment.cache(&p).unwrap(), PathBuf::from("/games/out/cache"));
    assert_eq!(
        environment.test_cartridges(&p).unwrap(),
        PathBuf::from("/games/out/tests")
    );
    environment.set("cache", "/elsewhere/../cache");
    assert_eq!(environment.cache(&p).unwrap(), PathBuf::from("/cache"));
}

#[test]
fn the_flags_come_back_absolute_and_only_the_ones_asked_for() {
    let command = clap::Command::new("x").args(arguments(&["game_dir", "cache", "soundfont"]));
    let matches = command
        .try_get_matches_from(["x", "--cache", "/c", "--game-dir", "/g/./game"])
        .unwrap();
    let environment = Environment::from_matches(&matches, &["game_dir", "cache", "soundfont"]);
    let flags: Vec<String> = environment
        .as_flags(&["cache", "game_dir", "soundfont"])
        .into_iter()
        .map(|f| f.into_string().unwrap())
        .collect();
    assert_eq!(flags, ["--game-dir", "/g/game", "--cache", "/c"]);
    assert!(environment.as_flags(&["rtp_dir"]).is_empty());
}

#[test]
fn the_cache_key_is_the_converters() {
    // Computed with the converter's own `disk_cache.key`, so a value one
    // side stores is found by the other.
    assert_eq!(
        cache::key(&[&b"capas"[..], &[0, 1], "ñ".as_bytes()]),
        "126ed228f1b1020345ba691224793f59cef4f5c5c7b07bffe54b193d1bd844e9"
    );
    assert_eq!(
        cache::key::<&[u8]>(&[]),
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
}

#[test]
fn a_version_is_the_hash_of_its_files_in_order() {
    let dir = scratch("version_of");
    fs::write(dir.join("a"), "one").unwrap();
    fs::write(dir.join("b"), "two").unwrap();
    let ab = cache::version_of(&dir, &["a", "b"]).unwrap();
    assert_eq!(ab, cache::version_of(&dir, &["a", "b"]).unwrap());
    assert_ne!(ab, cache::version_of(&dir, &["b", "a"]).unwrap());
    assert!(cache::version_of(&dir, &["missing"]).is_err());
}

#[test]
fn resolved_has_the_paths_the_suite_and_every_setting_in_order() {
    let out = rm2k_project::resolved(&project()).unwrap();
    assert_eq!(out["project"]["file"], "/games/one/rm2k-snes.toml");
    assert_eq!(out["project"]["build"], "/games/out");
    assert_eq!(out["project"]["manual_patches"], "/games/one/decided/manual");
    assert_eq!(out["project"]["auto_patches"], "/games/one/decided/auto");
    assert_eq!(out["project"]["cases"], "/games/one/tests/cases");
    assert!(out["suite"]["runtime"].as_str().unwrap().ends_with("/runtime"));
    let rom: Vec<_> = out["settings"]["rom"].as_object().unwrap().keys().cloned().collect();
    assert_eq!(rom, ["name", "title", "flag"]);
    // TOML's booleans and integers stay apart in JSON too.
    assert_eq!(out["settings"]["rom"]["flag"], true);
    assert_eq!(out["settings"]["maps"]["excluded"], serde_json::json!([3, 4]));
}

#[test]
fn resolved_refuses_a_project_without_its_paths() {
    let p = Project::from_text(Path::new("/g"), "[paths]\ndata = \"d\"\n").unwrap();
    let error = rm2k_project::resolved(&p).unwrap_err().to_string();
    assert!(error.ends_with("missing key paths.build"), "{error}");
}

/// The binary itself, as a game's tests run it: by `--project`, and with an
/// error on stderr and a failing status when there is no project.
#[test]
fn the_binary_prints_it_and_fails_with_the_librarys_message() {
    let root = scratch("binary");
    fs::write(root.join(FILENAME), SETTINGS).unwrap();
    let binary = env!("CARGO_BIN_EXE_rm2k-snes-project");
    let done = std::process::Command::new(binary)
        .arg("--project")
        .arg(&root)
        .output()
        .unwrap();
    assert!(done.status.success(), "{}", String::from_utf8_lossy(&done.stderr));
    let out: serde_json::Value = serde_json::from_slice(&done.stdout).unwrap();
    assert_eq!(out["project"]["data"], root.join("data").to_str().unwrap());
    assert_eq!(out["settings"]["rom"]["name"], "game");

    let empty = scratch("binary_without_project");
    let done = std::process::Command::new(binary)
        .arg("--project")
        .arg(&empty)
        .output()
        .unwrap();
    assert!(!done.status.success());
    let error = String::from_utf8_lossy(&done.stderr);
    assert!(error.starts_with("rm2k-snes-project: "), "{error}");
    assert!(error.contains("has no rm2k-snes.toml"), "{error}");
}
