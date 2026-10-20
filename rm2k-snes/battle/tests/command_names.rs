//! What each actor's battle commands are called: a 2000 game's terms, and
//! a 2003 game's battle commands, by type, from the actor's own list first
//! —easyrpg's `Game_Actor::GetBattleCommands` and
//! `Scene_Battle_Rpg2k3::GetBattleCommandNames`—. On the small game of
//! `tests/game/dump`, which is a 2000 one; the 2003 tests make it one by
//! hand, as Zounds is: Kazar's item command is "Tirar-Usar" and its escape a
//! special command.

use ditto::schema::{BattleCommand, BattleCommandType};
use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::rules::command_names;
use std::path::Path;

fn db() -> Db {
    Db::from_dump(
        &Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/game/dump"),
        false,
    )
    .unwrap()
}

fn command(id: i32, name: &str, ty: i32) -> (i32, BattleCommand) {
    (
        id,
        BattleCommand {
            id,
            name: name.to_string(),
            r#type: BattleCommandType::from_i32(ty),
            ..Default::default()
        },
    )
}

/// Zounds' database's commands, with the editor's Japanese left in the 2000
/// terms the 2003 battle never shows.
fn zounds_like() -> Db {
    let mut db = db();
    db.is_2003 = true;
    db.terms.command_attack = "\u{8d}U\u{152}\u{201a}".to_string();
    db.terms.command_defend = "\u{2013}h\u{152}\u{e4}".to_string();
    db.battle_commands = [
        command(1, "Atacar", 0),
        command(2, "Técnica", 1),
        command(3, "Defender", 3),
        command(4, "Objeto", 4),
        command(5, "Escapar", 5),
        command(6, "Robar", 2),
        command(8, "Tirar-Usar", 4),
        command(9, "Escapar", 6),
        command(10, "", 0),
    ]
    .into_iter()
    .collect();
    db.actors.get_mut(&1).unwrap().battle_commands = vec![1, 2, 4, 3, 9, 0, -1];
    db.actors.get_mut(&2).unwrap().battle_commands = vec![1, 2, 8, 3, 9, 0, -1];
    db.actors.get_mut(&3).unwrap().battle_commands = vec![10, 2, -1, -1, -1, -1, -1];
    db
}

#[test]
fn a_2000_game_names_them_with_its_terms() {
    let db = db();
    // Actor 1 renames its skill command: `skill_command_name`.
    let names = command_names(&db, 1).unwrap();
    assert_eq!(
        names,
        [" Strike", "Arts1", "Guard  ", "Items", "   Run away now"].map(String::from)
    );
}

#[test]
fn a_2003_game_names_them_with_the_actors_own_commands() {
    let db = zounds_like();
    assert_eq!(
        command_names(&db, 1).unwrap(),
        ["Atacar", "Técnica", "Defender", "Objeto", "Escapar"].map(String::from)
    );
    // Kazar's item command is his own.
    assert_eq!(command_names(&db, 2).unwrap()[3], "Tirar-Usar");
}

#[test]
fn what_the_actor_lacks_comes_from_the_database_by_type() {
    let db = zounds_like();
    // Actor 3 carries only an unnamed attack and the skill: the rest are
    // the database's first of each type, and the unnamed one does not
    // count.
    assert_eq!(
        command_names(&db, 3).unwrap(),
        ["Atacar", "Técnica", "Defender", "Objeto", "Escapar"].map(String::from)
    );
}

#[test]
fn what_the_database_lacks_is_the_2000_term() {
    let mut db = zounds_like();
    db.battle_commands.retain(|_, c| c.r#type.to_i32() != 5);
    assert_eq!(command_names(&db, 1).unwrap()[4], "   Run away now");
}
