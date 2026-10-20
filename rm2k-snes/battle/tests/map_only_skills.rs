//! A skill the battle lists and never lets be chosen: easyrpg's
//! `Algo::IsSkillUsable` in battle, which `Window_Skill::CheckEnable` asks of
//! every row and `Scene_Battle` buzzes by. A `switch` skill without
//! `occasion_battle` —Emily's Change Tape in A Blurred Line— is grey for
//! everyone; a `normal` one has no occasion flags. On the small game of
//! `tests/game/dump`.

use ditto::schema::SkillType;
use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::rules::{skill_usable, usable_in_battle};
use rm2k_snes_battle::simulate::{Battle, Combatant, Command, BATTLE_SEED, COMMAND_SKILL};
use std::collections::BTreeMap;
use std::path::Path;

/// Skill 9 targets one enemy; skill 2 is a switch one; skill 7 a teleport.
const NORMAL: i32 = 9;
const SWITCH: i32 = 2;
const TELEPORT: i32 = 7;

fn db() -> Db {
    Db::from_dump(
        &Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/game/dump"),
        false,
    )
    .unwrap()
}

#[test]
fn a_switch_skill_for_the_map_is_listed_and_not_usable() {
    let mut db = db();
    let s = db.skills.get_mut(&SWITCH).unwrap();
    assert_eq!(s.r#type, SkillType::Switch);
    s.occasion_field = true;
    s.occasion_battle = false;
    let s = db.skill(SWITCH).unwrap();
    assert!(skill_usable(s), "the list still carries it, grey");
    assert!(!usable_in_battle(s));
    db.skills.get_mut(&SWITCH).unwrap().occasion_battle = true;
    assert!(usable_in_battle(db.skill(SWITCH).unwrap()));
}

#[test]
fn a_normal_skill_is_usable_whatever_its_occasion_flags_say() {
    let mut db = db();
    let s = db.skills.get_mut(&NORMAL).unwrap();
    assert_eq!(s.r#type, SkillType::Normal);
    s.occasion_field = false;
    s.occasion_battle = false;
    assert!(usable_in_battle(db.skill(NORMAL).unwrap()));
}

#[test]
fn a_teleport_skill_is_never_usable_in_battle() {
    let db = db();
    let s = db.skill(TELEPORT).unwrap();
    assert_eq!(s.r#type, SkillType::Teleport);
    assert!(!usable_in_battle(s));
}

#[test]
fn the_battle_refuses_an_order_for_one() {
    let mut db = db();
    db.skills.get_mut(&SWITCH).unwrap().occasion_battle = false;
    let fight = |db: &Db| {
        let mut actor = Combatant::actor(db, 1, None, None).unwrap();
        actor.sp = actor.sp_max;
        let enemy = Combatant::enemy(db, 1, 0, false).unwrap();
        let mut battle = Battle::new(
            vec![actor],
            vec![enemy],
            BATTLE_SEED,
            Vec::new(),
            BTreeMap::new(),
        );
        battle.start(db).unwrap();
        battle.play_turn(
            db,
            &[Command {
                command: COMMAND_SKILL,
                what: SWITCH as i64,
                target: 0,
            }],
        )
    };
    let refused = fight(&db).unwrap_err();
    assert!(
        format!("{refused:?}").contains("not usable in battle"),
        "{refused:?}"
    );
    db.skills.get_mut(&SWITCH).unwrap().occasion_battle = true;
    fight(&db).unwrap();
}
