//! A skill with a physical attribute asks for a weapon that carries it:
//! `Game_Actor::IsSkillUsable`, on the small game of `tests/game/dump`. That
//! game brings a physical Sword and a magical Flame, and nothing that
//! carries them: each test gives the weapon and the skill what it needs.

use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::model;
use rm2k_snes_battle::rules::{weapon_attributes_asked, weapons_allow};
use rm2k_snes_battle::simulate::{Battle, Combatant, Command, BATTLE_SEED, COMMAND_SKILL};
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::Path;

const SWORD: usize = 0;
const FLAME: usize = 1;
/// Item 7 is a weapon, actor 1's from the start; skill 9 targets one enemy
/// and skill 3 heals an ally.
const WEAPON: i32 = 7;
const SKILL: i32 = 9;
const HEAL: i32 = 3;

fn db() -> Db {
    Db::from_dump(
        &Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/game/dump"),
        false,
    )
    .unwrap()
}

fn set(of: &[usize]) -> Vec<bool> {
    let mut out = vec![false; 2];
    for &k in of {
        out[k] = true;
    }
    out
}

fn equipment(db: &Db) -> Vec<i32> {
    let e = Combatant::actor(db, 1, None, None).unwrap().equipment;
    assert_eq!(e[0], WEAPON, "the test game's actor 1 holds item 7");
    e
}

#[test]
fn a_sword_skill_asks_for_a_sword() {
    let mut db = db();
    db.skills.get_mut(&SKILL).unwrap().attribute_effects = set(&[SWORD]);
    let e = equipment(&db);
    assert_eq!(
        weapon_attributes_asked(&db, db.skill(SKILL).unwrap()),
        set(&[SWORD])
    );
    assert!(!weapons_allow(&db, db.skill(SKILL).unwrap(), &e).unwrap());
    assert!(!weapons_allow(&db, db.skill(SKILL).unwrap(), &[0, 0, 0, 0, 0]).unwrap());
    db.items.get_mut(&WEAPON).unwrap().attribute_set = set(&[SWORD]);
    assert!(weapons_allow(&db, db.skill(SKILL).unwrap(), &e).unwrap());
}

#[test]
fn a_flame_skill_and_a_barrier_ask_for_nothing() {
    let mut db = db();
    let e = equipment(&db);
    db.skills.get_mut(&SKILL).unwrap().attribute_effects = set(&[FLAME]);
    assert!(weapons_allow(&db, db.skill(SKILL).unwrap(), &e).unwrap());
    assert_eq!(
        weapon_attributes_asked(&db, db.skill(SKILL).unwrap()),
        set(&[])
    );
    let s = db.skills.get_mut(&SKILL).unwrap();
    s.attribute_effects = set(&[SWORD]);
    s.affect_attr_defence = true;
    assert!(weapons_allow(&db, db.skill(SKILL).unwrap(), &e).unwrap());
}

#[test]
fn a_sword_heal_from_the_menu_is_grey_and_spends_nothing() {
    let mut db = db();
    db.skills.get_mut(&HEAL).unwrap().attribute_effects = set(&[SWORD]);
    let request = json!({"skill": HEAL, "user": 0, "target": 1,
                         "party": [{"id": 1, "hp": 10, "sp": 30}, {"id": 2, "hp": 3}]});
    let answer = model::field_skill(&db, &request).unwrap();
    assert_eq!(answer["used"], Value::Bool(false));
    assert_eq!(answer["party"][1]["hp"], json!(3));
    assert_eq!(
        answer["seed"],
        json!(BATTLE_SEED),
        "a grey one rolls nothing"
    );
    db.items.get_mut(&WEAPON).unwrap().attribute_set = set(&[SWORD]);
    let answer = model::field_skill(&db, &request).unwrap();
    assert_eq!(answer["used"], Value::Bool(true));
}

#[test]
fn the_battle_refuses_an_order_for_a_grey_one() {
    let mut db = db();
    db.skills.get_mut(&SKILL).unwrap().attribute_effects = set(&[SWORD]);
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
                what: SKILL as i64,
                target: 0,
            }],
        )
    };
    let refused = fight(&db).unwrap_err();
    assert!(format!("{refused:?}").contains("weapons"), "{refused:?}");
    db.items.get_mut(&WEAPON).unwrap().attribute_set = set(&[SWORD]);
    fight(&db).unwrap();
}
