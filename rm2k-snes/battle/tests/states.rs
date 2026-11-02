//! A skill's conditions on its target, against `Skill::vExecute` and
//! `GetStateProbability` worked out by hand, on the small game of
//! `tests/game/dump`: its two conditions, both persistent and doing
//! nothing, with rates 80, 60, 40 for ranks `A` to `C`.
//!
//! Skill 9 hits one enemy's HP; skill 3 heals one ally's. Each test gives
//! them the condition and the hit it needs.

use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::simulate::{Battle, Combatant, Rng, SkillResult, Who, BATTLE_SEED};
use rm2k_snes_battle::states;
use std::collections::BTreeMap;
use std::path::Path;

const HITS: i32 = 9;
const HEALS: i32 = 3;
const POISON: i64 = 2;
const ARMOR: i32 = 9;

fn db() -> Db {
    let mut db = Db::from_dump(
        &Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/game/dump"),
        false,
    )
    .unwrap();
    for skill in db.skills.values_mut() {
        skill.state_effects.clear();
        skill.sp_cost = 0;
    }
    // Neither condition restricts, so the battle goes on as usual.
    for state in db.states.values_mut() {
        state.restriction = ditto::schema::StateRestriction::from_i32(0);
    }
    db
}

fn battle(db: &Db) -> Battle {
    let actor = Combatant::actor(db, 1, None, None).unwrap();
    let enemy = Combatant::enemy(db, 1, 0, false).unwrap();
    Battle::new(
        vec![actor],
        vec![enemy],
        BATTLE_SEED,
        vec![],
        BTreeMap::new(),
    )
}

fn lines(b: &Battle) -> Vec<(&'static str, i64)> {
    b.results
        .iter()
        .map(|SkillResult { what, value, .. }| (*what, *value))
        .collect()
}

fn gives_poison(db: &mut Db, skill: i32) {
    db.skills.get_mut(&skill).unwrap().state_effects = vec![false, true];
}

/// An effect of zero, which rolls no variance, and nothing else touched:
/// only the critical and the condition are left to roll.
fn nothing_else(db: &mut Db, skill: i32) {
    let s = db.skills.get_mut(&skill).unwrap();
    s.affect_hp = false;
    s.affect_sp = false;
    s.affect_attack = false;
    s.affect_defense = false;
    s.affect_spirit = false;
    s.affect_agility = false;
    s.power = 0;
    s.physical_rate = 0;
    s.magical_rate = 0;
}

#[test]
fn the_odds_are_the_ranks_rate_and_the_armor_lowers_them() {
    let mut db = db();
    // An enemy's default rank is `B`, an actor's `C`.
    assert_eq!(states::enemy_odds(&db, 1, POISON).unwrap(), 60);
    assert_eq!(states::actor_odds(&db, 1, &[], POISON).unwrap(), 40);
    db.enemies.get_mut(&1).unwrap().state_ranks = vec![0, 0];
    assert_eq!(states::enemy_odds(&db, 1, POISON).unwrap(), 80);
    // Armor with the condition keeps `100 - state_chance` of it.
    let armor = db.items.get_mut(&ARMOR).unwrap();
    armor.state_set = vec![false, true];
    armor.state_chance = 75;
    assert_eq!(
        states::actor_odds(&db, 1, &[0, 0, ARMOR, 0, 0], POISON).unwrap(),
        10
    );
    // A weapon's `state_set` gives; it does not resist.
    assert_eq!(states::armor_keeps(&db, &[7], POISON).unwrap(), 100);
}

#[test]
fn a_hit_that_does_not_kill_gives_the_condition_after_two_rolls() {
    let mut db = db();
    gives_poison(&mut db, HITS);
    db.enemies.get_mut(&1).unwrap().state_ranks = vec![0, 0];
    db.states.get_mut(&2).unwrap().a_rate = 100;
    let mut b = battle(&db);
    b.enemies[0].hp = 9999;
    b.enemies[0].hp_max = 9999;
    b.use_skill(&db, Who::Actor(0), HITS, Who::Enemy(0))
        .unwrap();
    let lost = 9999 - b.enemies[0].hp;
    assert_eq!(lines(&b), [("damage", lost), ("inflicted", POISON)]);
    assert!(b.enemies[0].has_state(POISON));
    // Again: already held, its line after the damage's.
    b.results.clear();
    b.use_skill(&db, Who::Actor(0), HITS, Who::Enemy(0))
        .unwrap();
    assert_eq!(lines(&b)[1..], [("already", POISON)]);
}

#[test]
fn one_already_held_rolls_nothing() {
    let mut db = db();
    gives_poison(&mut db, HITS);
    nothing_else(&mut db, HITS);
    let mut b = battle(&db);
    b.add_state(&db, Who::Enemy(0), POISON).unwrap();
    b.use_skill(&db, Who::Actor(0), HITS, Who::Enemy(0))
        .unwrap();
    let mut rng = Rng { state: BATTLE_SEED };
    rng.percent(0); // the critical, and nothing else
    assert_eq!(b.rng.state, rng.state);
    assert_eq!(lines(&b), [("already", POISON)]);
}

#[test]
fn odds_of_zero_still_roll_both_and_give_nothing() {
    let mut db = db();
    gives_poison(&mut db, HITS);
    nothing_else(&mut db, HITS);
    db.states.get_mut(&2).unwrap().b_rate = 0;
    let mut b = battle(&db);
    b.use_skill(&db, Who::Actor(0), HITS, Who::Enemy(0))
        .unwrap();
    let mut rng = Rng { state: BATTLE_SEED };
    rng.percent(0); // the critical
    rng.percent(100); // the skill's hit for the condition
    rng.percent(0); // and its odds on the enemy
    assert_eq!(b.rng.state, rng.state);
    assert!(!b.enemies[0].has_state(POISON));
    assert_eq!(lines(&b), [("miss", 0)]);
}

#[test]
fn a_skill_on_its_own_side_takes_the_condition_away() {
    let mut db = db();
    gives_poison(&mut db, HEALS);
    nothing_else(&mut db, HEALS);
    let mut b = battle(&db);
    b.add_state(&db, Who::Actor(0), POISON).unwrap();
    assert!(b.actors[0].has_state(POISON));
    b.use_skill(&db, Who::Actor(0), HEALS, Who::Actor(0))
        .unwrap();
    assert!(!b.actors[0].has_state(POISON));
    assert_eq!(lines(&b), [("healed", POISON)]);
    // On one without it: one roll, nothing done, the failure.
    b.results.clear();
    b.use_skill(&db, Who::Actor(0), HEALS, Who::Actor(0))
        .unwrap();
    assert_eq!(lines(&b), [("miss", 0)]);
}

#[test]
fn a_turn_change_is_its_value_and_its_share_of_the_maximum() {
    use rm2k_snes_battle::simulate::TurnChange;
    // ABL's Poison: a loss of 5 % and 1.
    let poison = TurnChange {
        val: 1,
        max_pct: 5,
        sign: -1,
    };
    assert_eq!(poison.on(250), -13);
    assert_eq!(poison.on(19), -1, "5 % of 19 truncates to 0");
    let regen = TurnChange {
        val: 0,
        max_pct: 10,
        sign: 1,
    };
    assert_eq!(regen.on(999), 99);
    assert_eq!(TurnChange::default().on(999), 0);
}
