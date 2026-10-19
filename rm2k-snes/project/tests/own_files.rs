//! A port's own files in front of the game's: `patches/manual/files/`,
//! merged by `Environment::unpack` into one directory every reader sees.

use std::fs;
use std::path::{Path, PathBuf};

use rm2k_project::environment::Environment;
use rm2k_project::own_files::OwnFiles;
use rm2k_project::Project;

fn scratch(name: &str) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR"))
        .join("own_files")
        .join(name);
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

fn write(path: &Path, content: &str) {
    fs::create_dir_all(path.parent().unwrap()).unwrap();
    fs::write(path, content).unwrap();
}

fn project(dir: &Path) -> Project {
    Project::from_text(dir, "[paths]\nbuild = \"build\"\npatches = \"patches\"\n").unwrap()
}

/// A game and an RTP, below `dir`.
fn layout(dir: &Path) -> (PathBuf, PathBuf) {
    let game = dir.join("game");
    write(&game.join("RPG_RT.ldb"), "database");
    write(&game.join("picture/Menu.bmp"), "theirs, as a BMP");
    write(&game.join("picture/Other.png"), "another of theirs");
    write(&game.join("CharSet/Hero.png"), "hero");
    let rtp = dir.join("rtp");
    write(&rtp.join("System/Base.png"), "the RTP's");
    (game, rtp)
}

fn environment(game: &Path, rtp: &Path) -> Environment {
    let mut e = Environment::default();
    e.set("game_dir", game);
    e.set("rtp_dir", rtp);
    e
}

fn read(path: &Path) -> String {
    fs::read_to_string(path).unwrap()
}

#[test]
fn a_file_of_ours_replaces_the_games_by_name_without_regard_to_case_or_extension() {
    let dir = scratch("replaces");
    let (game, rtp) = layout(&dir);
    write(&dir.join("patches/manual/files/Picture/MENU.png"), "ours");
    let mut e = environment(&game, &rtp);
    e.unpack(&project(&dir)).unwrap();
    let merged = e.game().unwrap().to_path_buf();
    assert!(merged.starts_with(dir.join("build/cache/own-files")));
    // Ours goes into the game's folder, with the game's spelling, and the
    // game's of the same name is gone: a lookup can only find ours.
    let mut pictures: Vec<_> = fs::read_dir(merged.join("picture"))
        .unwrap()
        .map(|e| e.unwrap().file_name().into_string().unwrap())
        .collect();
    pictures.sort();
    assert_eq!(pictures, ["MENU.png", "Other.png"]);
    assert!(!merged.join("Picture").exists());
    assert_eq!(read(&merged.join("picture/MENU.png")), "ours");
    // The rest is the game's.
    assert_eq!(read(&merged.join("picture/Other.png")), "another of theirs");
    assert_eq!(read(&merged.join("CharSet/Hero.png")), "hero");
    assert_eq!(read(&merged.join("RPG_RT.ldb")), "database");
    // The tools it runs receive the merged directory.
    assert_eq!(e.as_flags(&["game_dir"])[1], merged.as_os_str());
    let own = e.own_files().unwrap();
    assert_eq!(
        own.lines(),
        ["Picture/MENU.png replaces the game's picture/Menu.bmp"]
    );
    // A tool that receives the merged directory keeps it, and knows.
    let mut again = Environment::default();
    again.set("game_dir", &merged);
    again.unpack(&project(&dir)).unwrap();
    assert_eq!(again.game().unwrap(), merged);
    assert_eq!(again.own_files().unwrap().lines(), own.lines());
    // Changing our file is another directory, and the old one keeps ours.
    write(
        &dir.join("patches/manual/files/Picture/MENU.png"),
        "ours, redrawn",
    );
    let mut changed = environment(&game, &rtp);
    changed.unpack(&project(&dir)).unwrap();
    assert_ne!(changed.game().unwrap(), merged);
    assert_eq!(
        read(&changed.game().unwrap().join("picture/MENU.png")),
        "ours, redrawn"
    );
    assert_eq!(read(&merged.join("picture/MENU.png")), "ours");
}

#[test]
fn one_the_game_lacks_replaces_the_rtps() {
    let dir = scratch("rtp");
    let (game, rtp) = layout(&dir);
    write(&dir.join("patches/manual/files/System/base.png"), "ours");
    let mut e = environment(&game, &rtp);
    e.unpack(&project(&dir)).unwrap();
    assert_eq!(read(&e.game().unwrap().join("System/base.png")), "ours");
    assert_eq!(
        e.own_files().unwrap().lines(),
        ["System/base.png replaces the RTP's"]
    );
}

fn error_with(file: &str) -> String {
    let dir = scratch(&file.replace('/', "-"));
    let (game, rtp) = layout(&dir);
    write(&dir.join("patches/manual/files").join(file), "ours");
    if file == "Picture/Menu.bmp" {
        write(&dir.join("patches/manual/files/Picture/Menu.png"), "ours");
    }
    environment(&game, &rtp)
        .unpack(&project(&dir))
        .unwrap_err()
        .to_string()
}

#[test]
fn a_name_that_replaces_nothing_is_an_error() {
    let error = error_with("Picture/Mneu.png");
    assert!(error.contains("would replace nothing"), "{error}");
}

#[test]
fn a_folder_that_is_not_rm2ks_is_an_error() {
    let error = error_with("Pictures/Menu.png");
    assert!(error.contains("not one of RM2k's folders"), "{error}");
}

#[test]
fn a_file_outside_a_folder_is_an_error() {
    let error = error_with("Menu.png");
    assert!(error.contains("only RM2k's folders go here"), "{error}");
}

#[test]
fn two_of_ours_with_the_same_name_are_an_error() {
    let error = error_with("Picture/Menu.bmp");
    assert!(error.contains("same name"), "{error}");
}

#[test]
fn without_files_the_game_is_read_as_it_is() {
    let dir = scratch("none");
    let (game, rtp) = layout(&dir);
    // The other hand-made patches are not files of ours.
    write(&dir.join("patches/manual/forks/Map0001.json"), "{}");
    let mut e = environment(&game, &rtp);
    e.unpack(&project(&dir)).unwrap();
    assert_eq!(e.game().unwrap(), game);
    assert!(e.own_files().is_none());
    assert!(OwnFiles::read(&game).unwrap().is_none());
}
