//! `[graphics] system`: the project draws with another System than the
//! one the database names, by name —looked for as the database's is— or
//! as a picture of its own.

use rm2k_snes_screens::Game;
use std::path::PathBuf;

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/game")
}

/// The small game, in a folder of its own with a second System, `Other`,
/// which is the FaceSet's picture: anything that is not `Skin`.
fn game_with_another_system(name: &str) -> (Game, PathBuf) {
    let dir = PathBuf::from(env!("CARGO_TARGET_TMPDIR")).join(format!("system-choice-{name}"));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(dir.join("System")).unwrap();
    std::fs::copy(here().join("pictures/System/Skin.png"), dir.join("System/Skin.png")).unwrap();
    let other = dir.join("System/Other.png");
    std::fs::copy(here().join("pictures/FaceSet/Faces.png"), &other).unwrap();
    (Game::from_dump(&here().join("dump"), &dir).unwrap(), other)
}

#[test]
fn without_a_choice_it_is_the_databases() {
    let (game, _) = game_with_another_system("none");
    assert!(game.skin().unwrap().path.ends_with("System/Skin.png"));
}

#[test]
fn a_name_is_looked_for_like_the_databases() {
    let (mut game, other) = game_with_another_system("name");
    game.use_system("other");
    assert_eq!(game.skin().unwrap().path, other);
}

#[test]
fn a_path_is_read_as_is() {
    let (mut game, _) = game_with_another_system("path");
    let own = here().join("pictures/FaceSet/Faces.png");
    game.use_system(own.to_str().unwrap());
    assert_eq!(game.skin().unwrap().path, own);
}
