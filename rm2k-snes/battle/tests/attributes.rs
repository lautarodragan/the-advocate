//! The attributes in battle, against easyrpg's `ApplyAttributeMultiplier`
//! worked out by hand, on the small game of `tests/game/dump`. That game
//! brings two attributes, a physical Sword and a magical Flame, with the
//! rates RM2k's editor gives a new attribute of each kind —150, 125, 100,
//! 75, 50 and 200, 150, 100, 50, 0—, and nothing that carries them: each
//! test gives the weapon, the armor, the skill and the ranks it needs.

use ditto::schema::AttributeType;
use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::simulate::{
    apply_variance, normal_damage, skill_effect, Battle, Combatant, Rng, Who, BATTLE_SEED,
};
use std::collections::BTreeMap;
use std::path::Path;

const SWORD: usize = 0;
const FLAME: usize = 1;
/// The ranks, `A` to `E`.
const B: u8 = 1;
const C: u8 = 2;
const D: u8 = 3;

/// Item 7 is a weapon and item 9 armor; skill 9 targets one enemy with
/// power 12, physical rate 15 and magical rate 5, ignoring defense.
const WEAPON: i32 = 7;
const ARMOR: i32 = 9;
const SKILL: i32 = 9;

fn db() -> Db {
    let db = Db::from_dump(
        &Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/game/dump"),
        false,
    )
    .unwrap();
    assert_eq!(db.attributes[&1].r#type, AttributeType::Physical);
    assert_eq!(db.attributes[&2].r#type, AttributeType::Magical);
    db
}

fn set(of: &[usize]) -> Vec<bool> {
    let mut out = vec![false; 2];
    for &k in of {
        out[k] = true;
    }
    out
}

fn enemy_with(db: &mut Db, id: i32, ranks: [u8; 2]) -> Combatant {
    db.enemies.get_mut(&id).unwrap().attribute_ranks = ranks.to_vec();
    Combatant::enemy(db, id, 0, false).unwrap()
}

#[test]
fn a_flame_skill_on_a_flame_weak_enemy_does_half_again() {
    let mut db = db();
    db.skills.get_mut(&SKILL).unwrap().attribute_effects = set(&[FLAME]);
    let source = Combatant::actor(&db, 1, None, None).unwrap();
    let neutral = enemy_with(&mut db, 1, [C, C]);
    let weak = enemy_with(&mut db, 1, [C, B]);
    // `CalcSkillEffect` by hand: the skill ignores the defense.
    let base = 12 + 15 * source.attack() / 20 + 5 * source.spirit() / 40;
    assert!(base > 0);
    let skill = db.skill(SKILL).unwrap();
    assert_eq!(skill_effect(&source, &neutral, skill, false), base);
    assert_eq!(skill_effect(&source, &weak, skill, false), 150 * base / 100);
    // The critical triples what the attribute left.
    assert_eq!(
        skill_effect(&source, &weak, skill, true),
        3 * (150 * base / 100)
    );
}

#[test]
fn a_resisted_sword_does_three_quarters_and_rolls_the_same_variance() {
    let mut db = db();
    db.items.get_mut(&WEAPON).unwrap().attribute_set = set(&[SWORD]);
    let source = Combatant::actor(&db, 1, None, None).unwrap();
    assert_eq!(source.equipment[0], WEAPON);
    let target = enemy_with(&mut db, 1, [D, C]);
    let base = (source.attack() / 2 - 12 / 4).max(0);
    assert!(base > 4, "the variance has to have room");
    let expected = apply_variance(75 * base / 100, 4, &mut Rng { state: BATTLE_SEED });
    assert_eq!(
        normal_damage(&source, &target, false, &mut Rng { state: BATTLE_SEED }),
        expected
    );
}

#[test]
fn an_enemys_attack_carries_no_attribute() {
    let mut db = db();
    let source = enemy_with(&mut db, 1, [C, C]);
    // Actor 3 is unarmed, and its ranks do not matter for an enemy's attack.
    db.actors.get_mut(&3).unwrap().attribute_ranks = vec![0, 0];
    let target = Combatant::actor(&db, 3, None, None).unwrap();
    let base = (source.attack() / 2 - target.defense() / 4).max(0);
    let expected = apply_variance(base, 4, &mut Rng { state: BATTLE_SEED });
    assert_eq!(
        normal_damage(&source, &target, false, &mut Rng { state: BATTLE_SEED }),
        expected
    );
}

#[test]
fn armor_carrying_an_attribute_moves_the_actor_one_rank_up() {
    let mut db = db();
    db.items.get_mut(&ARMOR).unwrap().attribute_set = set(&[FLAME]);
    db.skills.get_mut(&SKILL).unwrap().attribute_effects = set(&[FLAME]);
    // Actor 1 wears item 9; actor 2 does not. Both are `C` in Flame.
    let with = Combatant::actor(&db, 1, None, None).unwrap();
    let without = Combatant::actor(&db, 1, Some(&[WEAPON, 0, 0, 0, 0]), None).unwrap();
    assert_eq!(with.received[FLAME].rate, 50, "C and the armor's step: D");
    assert_eq!(without.received[FLAME].rate, 100);
    assert_eq!(with.received[SWORD].rate, 100, "the armor carries no Sword");
    // From `D` of its own, the armor leaves it at `E`: immune.
    db.actors.get_mut(&1).unwrap().attribute_ranks = vec![C, D];
    let immune = Combatant::actor(&db, 1, None, None).unwrap();
    assert_eq!(immune.received[FLAME].rate, 0);
    let source = enemy_with(&mut db, 1, [C, C]);
    assert_eq!(
        skill_effect(&source, &immune, db.skill(SKILL).unwrap(), false),
        0
    );
}

#[test]
fn a_weapons_attribute_does_not_protect_and_armors_does_not_hit() {
    let mut db = db();
    db.items.get_mut(&WEAPON).unwrap().attribute_set = set(&[FLAME]);
    db.items.get_mut(&ARMOR).unwrap().attribute_set = set(&[SWORD]);
    let actor = Combatant::actor(&db, 1, None, None).unwrap();
    assert_eq!(actor.received[FLAME].rate, 100);
    assert_eq!(actor.weapon_attributes, set(&[FLAME]));
}

// --- the skills that shift a rank: `affect_attr_defence` ---------------------

/// Skill 11 targets the party with power 0 and touches nothing; skill 5
/// targets one enemy and touches nothing either. With `affect_attr_defence`
/// and Flame they are a barrier and a curse.
const BARRIER: i32 = 11;
const CURSE: i32 = 5;

fn with_shift(db: &mut Db, skill: i32, hit: i32) {
    let s = db.skills.get_mut(&skill).unwrap();
    s.affect_attr_defence = true;
    s.attribute_effects = set(&[FLAME]);
    s.hit = hit;
    s.sp_cost = 0;
}

/// An effect of zero, which rolls no variance, and nothing else touched:
/// only the critical and the steps are left to roll.
fn no_effect(db: &mut Db, skill: i32) {
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

fn battle(db: &mut Db) -> Battle {
    let actor = Combatant::actor(db, 1, Some(&[WEAPON, 0, 0, 0, 0]), None).unwrap();
    let enemy = enemy_with(db, 1, [C, C]);
    Battle::new(
        vec![actor],
        vec![enemy],
        BATTLE_SEED,
        vec![],
        BTreeMap::new(),
    )
}

#[test]
fn a_barrier_makes_the_party_one_step_more_resistant_for_the_battle() {
    let mut db = db();
    with_shift(&mut db, BARRIER, 100);
    db.skills.get_mut(&SKILL).unwrap().attribute_effects = set(&[FLAME]);
    let mut b = battle(&mut db);
    let before = skill_effect(&b.enemies[0], &b.actors[0], db.skill(SKILL).unwrap(), false);
    assert!(before > 1);
    b.use_skill(&db, Who::Actor(0), BARRIER, Who::Actor(0))
        .unwrap();
    assert_eq!(b.actors[0].received[FLAME].shift, 1);
    assert_eq!(b.actors[0].received[FLAME].rate, 50, "C and a step up: D");
    assert_eq!(
        b.actors[0].received[SWORD].shift, 0,
        "the barrier carries no Sword"
    );
    // The Flame skill the enemy throws afterwards reads the shifted rank.
    let after = skill_effect(&b.enemies[0], &b.actors[0], db.skill(SKILL).unwrap(), false);
    assert_eq!(after, 50 * before / 100);
    // It is shown in the answer, and only where there is one.
    assert_eq!(
        b.actors[0].to_json()["attribute_shift"],
        serde_json::json!([0, 1])
    );
    assert!(b.enemies[0].to_json().get("attribute_shift").is_none());
}

#[test]
fn a_curse_makes_an_enemy_one_step_weaker_and_rolls_once_per_attribute() {
    let mut db = db();
    with_shift(&mut db, CURSE, 100);
    no_effect(&mut db, CURSE);
    let mut b = battle(&mut db);
    let mut rng = Rng { state: BATTLE_SEED };
    b.use_skill(&db, Who::Actor(0), CURSE, Who::Enemy(0))
        .unwrap();
    rng.percent(0); // the critical
    rng.percent(100); // and the step
    assert_eq!(b.rng.state, rng.state);
    assert_eq!(b.enemies[0].received[FLAME].shift, -1);
    assert_eq!(
        b.enemies[0].received[FLAME].rate, 150,
        "C and a step down: B"
    );
    // A second one finds it at the bound, and **rolls nothing** for it:
    // only the critical.
    b.use_skill(&db, Who::Actor(0), CURSE, Who::Enemy(0))
        .unwrap();
    rng.percent(0);
    assert_eq!(b.rng.state, rng.state);
    assert_eq!(b.enemies[0].received[FLAME].rate, 150);
}

#[test]
fn a_missed_step_leaves_the_rank_and_still_rolled() {
    let mut db = db();
    with_shift(&mut db, CURSE, 0);
    no_effect(&mut db, CURSE);
    let mut b = battle(&mut db);
    let mut rng = Rng { state: BATTLE_SEED };
    b.use_skill(&db, Who::Actor(0), CURSE, Who::Enemy(0))
        .unwrap();
    rng.percent(0);
    rng.percent(0);
    assert_eq!(b.rng.state, rng.state);
    assert_eq!(b.enemies[0].received[FLAME].shift, 0);
}

#[test]
fn a_skill_without_affect_attr_defence_shifts_nothing() {
    let mut db = db();
    with_shift(&mut db, BARRIER, 100);
    db.skills.get_mut(&BARRIER).unwrap().affect_attr_defence = false;
    let mut b = battle(&mut db);
    b.use_skill(&db, Who::Actor(0), BARRIER, Who::Actor(0))
        .unwrap();
    assert_eq!(b.actors[0].received[FLAME].shift, 0);
}

#[test]
fn getting_up_brings_the_ranks_back() {
    let mut db = db();
    with_shift(&mut db, BARRIER, 100);
    let mut b = battle(&mut db);
    b.use_skill(&db, Who::Actor(0), BARRIER, Who::Actor(0))
        .unwrap();
    assert_eq!(b.actors[0].received[FLAME].rate, 50);
    b.actors[0].unshift();
    assert_eq!(b.actors[0].received[FLAME].shift, 0);
    assert_eq!(b.actors[0].received[FLAME].rate, 100);
}
