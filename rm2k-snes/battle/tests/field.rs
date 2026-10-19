//! A healing skill used from the pause menu, against easyrpg's
//! `Game_Battler::UseSkill` outside battle worked out by hand, on the small
//! game of `tests/game/dump`. The randomness is the battle's xorshift: each
//! expected number names the rolls it takes.

use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::field::use_skill;
use rm2k_snes_battle::model;
use rm2k_snes_battle::simulate::{apply_variance, skill_effect, Combatant, Rng, BATTLE_SEED};
use serde_json::{json, Value};
use std::path::Path;

fn db() -> Db {
    Db::from_dump(
        &Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/game/dump"),
        false,
    )
    .unwrap()
}

fn actor(db: &Db, id: i32, hp: i64, sp: i64) -> Combatant {
    let mut a = Combatant::actor(db, id, None, None).unwrap();
    a.hp = hp.min(a.hp_max);
    a.sp = sp.min(a.sp_max);
    a
}

/// What `skill` from `source` heals with the seed `rng` has: the critical's
/// roll, then the variance's.
fn effect(db: &Db, skill: i32, source: &Combatant, rng: &mut Rng) -> i64 {
    let s = db.skill(skill).unwrap();
    let critical = rng.percent(0);
    assert!(!critical, "a critical at zero percent");
    apply_variance(
        skill_effect(source, source, s, false),
        s.variance as i64,
        rng,
    )
}

#[test]
fn a_heal_on_an_ally_adds_the_effect_and_spends_the_sp_once() {
    let db = db();
    let mut party = vec![actor(&db, 1, 10, 30), actor(&db, 2, 3, 0)];
    let mut expected_rng = Rng { state: BATTLE_SEED };
    let heal = effect(&db, 3, &party[0], &mut expected_rng);
    assert!(heal > 0);
    let mut rng = Rng { state: BATTLE_SEED };
    assert!(use_skill(db.skill(3).unwrap(), &mut party, 0, 1, &mut rng));
    assert_eq!(party[1].hp, (3 + heal).min(party[1].hp_max));
    assert_eq!(party[0].sp, 30.min(party[0].sp_max) - 8);
    assert_eq!(party[0].hp, 10, "the user is not the target");
    assert_eq!(
        rng.state, expected_rng.state,
        "two rolls: the critical and the variance"
    );
}

#[test]
fn on_a_full_target_it_is_of_no_use_and_spends_nothing_but_rolls() {
    let db = db();
    let full = Combatant::actor(&db, 2, None, None).unwrap().hp_max;
    let mut party = vec![actor(&db, 1, 10, 30), actor(&db, 2, full, 0)];
    let mut rng = Rng { state: BATTLE_SEED };
    assert!(!use_skill(db.skill(3).unwrap(), &mut party, 0, 1, &mut rng));
    assert_eq!(party[0].sp, 30.min(party[0].sp_max));
    assert_eq!(party[1].hp, full);
    assert_ne!(
        rng.state, BATTLE_SEED,
        "`CalcSkillEffect` runs before it knows"
    );
}

#[test]
fn without_the_sp_nothing_happens_and_nothing_is_rolled() {
    let db = db();
    let mut party = vec![actor(&db, 1, 10, 7), actor(&db, 2, 3, 0)];
    let mut rng = Rng { state: BATTLE_SEED };
    assert!(!use_skill(db.skill(3).unwrap(), &mut party, 0, 1, &mut rng));
    assert_eq!((party[0].sp, party[1].hp), (7, 3));
    assert_eq!(rng.state, BATTLE_SEED);
}

#[test]
fn on_the_party_each_one_rolls_in_order_and_the_fallen_get_nothing() {
    let db = db();
    let mut party = vec![
        actor(&db, 1, 10, 30),
        actor(&db, 2, 0, 0),
        actor(&db, 3, 5, 1),
    ];
    let mut expected_rng = Rng { state: BATTLE_SEED };
    let first = effect(&db, 6, &party[0], &mut expected_rng);
    let _second = effect(&db, 6, &party[0], &mut expected_rng);
    let third = effect(&db, 6, &party[0], &mut expected_rng);
    let (max0, spmax0, sp0) = (party[0].hp_max, party[0].sp_max, party[0].sp);
    let (max2, spmax2) = (party[2].hp_max, party[2].sp_max);
    let mut rng = Rng { state: BATTLE_SEED };
    assert!(use_skill(db.skill(6).unwrap(), &mut party, 0, 2, &mut rng));
    assert_eq!(party[0].hp, (10 + first).min(max0));
    assert_eq!(
        party[0].sp,
        (sp0 + first).min(spmax0) - 4,
        "its SP go up too, and then it pays"
    );
    assert_eq!(
        (party[1].hp, party[1].sp),
        (0, 0),
        "a fallen one is neither healed nor given SP"
    );
    assert_eq!(party[2].hp, (5 + third).min(max2));
    assert_eq!(party[2].sp, (1 + third).min(spmax2));
    assert_eq!(rng.state, expected_rng.state);
}

#[test]
fn a_skill_on_oneself_ignores_the_target() {
    let db = db();
    let mut skill = db.skill(3).unwrap().clone();
    skill.scope = ditto::schema::SkillScope::Self_;
    let mut party = vec![actor(&db, 1, 10, 30), actor(&db, 2, 3, 0)];
    let mut expected_rng = Rng { state: BATTLE_SEED };
    let heal = effect(&db, 3, &party[0], &mut expected_rng);
    let mut rng = Rng { state: BATTLE_SEED };
    assert!(use_skill(&skill, &mut party, 0, 1, &mut rng));
    assert_eq!(party[0].hp, (10 + heal).min(party[0].hp_max));
    assert_eq!(party[1].hp, 3);
}

#[test]
fn reviving_with_hp_gives_the_effect_and_without_a_percentage() {
    let db = db();
    let mut with_hp = db.skill(3).unwrap().clone();
    with_hp.state_effects = vec![true];
    let mut party = vec![actor(&db, 1, 10, 30), actor(&db, 2, 0, 0)];
    let mut expected_rng = Rng { state: BATTLE_SEED };
    let heal = effect(&db, 3, &party[0], &mut expected_rng);
    let mut rng = Rng { state: BATTLE_SEED };
    assert!(use_skill(&with_hp, &mut party, 0, 1, &mut rng));
    assert_eq!(
        party[1].hp,
        heal.min(party[1].hp_max),
        "1 from the revive, then the effect minus that one"
    );

    // RM2k's Raise: no HP of its own, so `effect` percent of the maximum.
    let mut raise = db.skill(5).unwrap().clone();
    raise.scope = ditto::schema::SkillScope::Ally;
    raise.state_effects = vec![true];
    let mut party = vec![actor(&db, 1, 10, 30), actor(&db, 2, 0, 0)];
    let max = party[1].hp_max;
    let mut rng = Rng { state: BATTLE_SEED };
    assert!(use_skill(&raise, &mut party, 0, 1, &mut rng));
    assert_eq!(party[1].hp, (max * 30 / 100).max(1));
    let paid = party[0].sp;
    assert_eq!(paid, 30.min(party[0].sp_max) - 6);
    // And on one standing, of no use: it has no HP to give.
    assert!(!use_skill(&raise, &mut party, 0, 1, &mut rng));
    assert_eq!(party[0].sp, paid);
}

#[test]
fn the_stage_answers_the_same_as_the_function() {
    let db = db();
    let request = json!({"skill": 3, "user": 0, "target": 1,
                         "party": [{"id": 1, "hp": 10, "sp": 30}, {"id": 2, "hp": 3}]});
    let answer = model::field_skill(&db, &request).unwrap();
    let mut party = vec![
        actor(&db, 1, 10, 30),
        Combatant::actor(&db, 2, None, None).unwrap(),
    ];
    party[1].hp = 3;
    let mut rng = Rng { state: BATTLE_SEED };
    let used = use_skill(db.skill(3).unwrap(), &mut party, 0, 1, &mut rng);
    assert_eq!(answer["used"], Value::Bool(used));
    assert_eq!(answer["party"][1]["hp"], json!(party[1].hp));
    assert_eq!(answer["party"][0]["sp"], json!(party[0].sp));
    assert_eq!(answer["seed"], json!(rng.state));
}
