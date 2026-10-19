//! A special item casts its skill in battle: easyrpg's
//! `Game_Party::IsItemUsable` for the list and `Scene_Battle::AssignSkill`
//! with the item, whose `Game_BattleAlgorithm::Skill` spends the item and
//! not the SP. On the small game of `tests/game/dump`, whose item 10 each
//! test turns into a special item.

use ditto::schema::{ItemType, SkillType};
use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::model;
use rm2k_snes_battle::rules::{item_in_battle, item_skill_in_battle};
use rm2k_snes_battle::simulate::{
    Battle, Combatant, Command, BATTLE_SEED, COMMAND_DEFEND, COMMAND_ITEM, COMMAND_SKILL,
};
use serde_json::json;
use std::collections::BTreeMap;
use std::path::Path;

/// Item 10 is a plain item, item 1 a medicine. Skill 9 targets one enemy
/// with power 12 and costs 7; skill 2 is a switch one; skill 7 a teleport;
/// skill 6 heals the party.
const ITEM: i32 = 10;
const MEDICINE: i32 = 1;
const SKILL: i32 = 9;
const SWITCH: i32 = 2;
const TELEPORT: i32 = 7;
const PARTY_HEAL: i32 = 6;

fn db_with(skill: i32) -> Db {
    let mut db = Db::from_dump(
        &Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/game/dump"),
        false,
    )
    .unwrap();
    let item = db.items.get_mut(&ITEM).unwrap();
    item.r#type = ItemType::Special;
    item.skill_id = skill;
    db
}

#[test]
fn a_special_item_casts_a_normal_skill_and_a_switch_one_with_occasion_battle() {
    let db = db_with(SKILL);
    assert_eq!(db.skill(SKILL).unwrap().r#type, SkillType::Normal);
    assert_eq!(
        item_skill_in_battle(&db, db.item(ITEM).unwrap()),
        Some(SKILL)
    );
    assert!(item_in_battle(&db, db.item(ITEM).unwrap()));

    let mut db = db_with(SWITCH);
    assert_eq!(db.skill(SWITCH).unwrap().r#type, SkillType::Switch);
    db.skills.get_mut(&SWITCH).unwrap().occasion_battle = false;
    assert_eq!(item_skill_in_battle(&db, db.item(ITEM).unwrap()), None);
    db.skills.get_mut(&SWITCH).unwrap().occasion_battle = true;
    assert_eq!(
        item_skill_in_battle(&db, db.item(ITEM).unwrap()),
        Some(SWITCH)
    );

    let db = db_with(TELEPORT);
    assert_eq!(db.skill(TELEPORT).unwrap().r#type, SkillType::Teleport);
    assert_eq!(item_skill_in_battle(&db, db.item(ITEM).unwrap()), None);
    assert!(!item_in_battle(&db, db.item(ITEM).unwrap()));
}

#[test]
fn neither_a_medicine_nor_a_plain_item_casts_anything() {
    let mut db = db_with(SKILL);
    assert_eq!(item_skill_in_battle(&db, db.item(MEDICINE).unwrap()), None);
    db.items.get_mut(&ITEM).unwrap().r#type = ItemType::Normal;
    assert_eq!(item_skill_in_battle(&db, db.item(ITEM).unwrap()), None);
    // Without a skill, or with one the database lacks.
    let mut db = db_with(0);
    assert_eq!(item_skill_in_battle(&db, db.item(ITEM).unwrap()), None);
    db.items.get_mut(&ITEM).unwrap().skill_id = 999;
    assert_eq!(item_skill_in_battle(&db, db.item(ITEM).unwrap()), None);
}

/// Actor 1 at full SP against enemy 1, with one command; the battle as it
/// ended the turn.
fn one_turn(db: &Db, command: Command) -> Battle {
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
    battle.play_turn(db, &[command]).unwrap();
    battle
}

#[test]
fn the_item_does_what_the_skill_does_without_the_sp() {
    let db = db_with(SKILL);
    let item = one_turn(
        &db,
        Command {
            command: COMMAND_ITEM,
            what: ITEM as i64,
            target: 0,
        },
    );
    let skill = one_turn(
        &db,
        Command {
            command: COMMAND_SKILL,
            what: SKILL as i64,
            target: 0,
        },
    );
    let defend = one_turn(
        &db,
        Command {
            command: COMMAND_DEFEND,
            what: 0,
            target: 0,
        },
    );
    let hp_max = defend.enemies[0].hp;
    assert!(item.enemies[0].hp < hp_max, "the item has to hurt");
    assert_eq!(
        item.enemies[0].hp, skill.enemies[0].hp,
        "the same rolls, the same damage"
    );
    assert_eq!(item.rng.state, skill.rng.state);
    let full = item.actors[0].sp_max;
    assert_eq!(item.actors[0].sp, full, "the item spends no SP");
    assert_eq!(skill.actors[0].sp, full - 7, "and the skill its 7");
}

#[test]
fn a_skill_on_the_party_asks_for_no_target() {
    let db = db_with(PARTY_HEAL);
    // A place past the party: a skill on the whole party does not read it.
    one_turn(
        &db,
        Command {
            command: COMMAND_ITEM,
            what: ITEM as i64,
            target: 5,
        },
    );
}

#[test]
fn an_actor_its_actor_set_leaves_out_cannot_use_it() {
    let mut db = db_with(SKILL);
    db.items.get_mut(&ITEM).unwrap().actor_set = vec![false];
    let mut actor = Combatant::actor(&db, 1, None, None).unwrap();
    actor.sp = actor.sp_max;
    let enemy = Combatant::enemy(&db, 1, 0, false).unwrap();
    let mut battle = Battle::new(
        vec![actor],
        vec![enemy],
        BATTLE_SEED,
        Vec::new(),
        BTreeMap::new(),
    );
    battle.start(&db).unwrap();
    let refused = battle
        .play_turn(
            &db,
            &[Command {
                command: COMMAND_ITEM,
                what: ITEM as i64,
                target: 0,
            }],
        )
        .unwrap_err();
    assert!(format!("{refused:?}").contains("actor_set"), "{refused:?}");
}

#[test]
fn the_model_carries_the_items_skill() {
    let db = db_with(SKILL);
    let request = json!({"actors": [1], "troops": [], "items": [MEDICINE, ITEM],
                         "skill_pairs": [], "item_name_width": 12});
    let answer = model::model(&db, &request).unwrap();
    assert_eq!(answer["item_battle"], json!([true, true]));
    assert_eq!(answer["item_skill"], json!([0, SKILL]));
    assert!(answer["skills"].as_array().unwrap().contains(&json!(SKILL)));
    assert_eq!(
        answer["texts"]["skills"][SKILL.to_string()]["name"],
        json!("Skill number 9")
    );
}
