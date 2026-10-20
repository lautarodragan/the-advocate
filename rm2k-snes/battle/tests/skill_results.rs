//! The lines a skill writes on each target after its using lines, against
//! `Scene_Battle_Rpg2k` and `Skill::vExecute` worked out by hand, on the
//! small game of `tests/game/dump`: the damage, the HP recovered, a
//! parameter that moves, and the failure when it did nothing —and where
//! `vExecute` stops rolling, which decides that—.
//!
//! Skill 9 hits one enemy's HP, skill 3 heals one ally's, skill 10 raises
//! its user's attack and skill 14 hits every enemy's HP and defense at 95.

use rm2k_snes_battle::db::Db;
use rm2k_snes_battle::simulate::{Battle, Combatant, SkillResult, Who, BATTLE_SEED};
use std::collections::BTreeMap;
use std::path::Path;

fn db() -> Db {
    Db::from_dump(
        &Path::new(env!("CARGO_MANIFEST_DIR")).join("tests/game/dump"),
        false,
    )
    .unwrap()
}

fn battle(db: &Db) -> Battle {
    let actor = Combatant::actor(db, 1, None, None).unwrap();
    let enemy = Combatant::enemy(db, 1, 0, false).unwrap();
    Battle::new(vec![actor], vec![enemy], BATTLE_SEED, vec![], BTreeMap::new())
}

fn lines(b: &Battle) -> Vec<(String, &'static str, i64)> {
    b.results
        .iter()
        .map(|SkillResult { target, what, value, .. }| (target.clone(), *what, *value))
        .collect()
}

#[test]
fn a_damaging_skill_says_the_damage_on_its_target() {
    let db = db();
    let mut b = battle(&db);
    let before = b.enemies[0].hp;
    b.use_skill(&db, Who::Actor(0), 9, Who::Enemy(0)).unwrap();
    let lost = before - b.enemies[0].hp;
    assert!(lost > 0 && b.enemies[0].hp > 0, "the case wants a hit that does not kill");
    assert_eq!(lines(&b), [(b.enemies[0].name.clone(), "damage", lost)]);
}

#[test]
fn a_heal_says_what_it_really_recovered() {
    let db = db();
    let mut b = battle(&db);
    let max = b.actors[0].hp_max;
    // Short of less than the heal: the line says what was missing.
    b.actors[0].hp = max - 3;
    b.use_skill(&db, Who::Actor(0), 3, Who::Actor(0)).unwrap();
    assert_eq!(b.actors[0].hp, max);
    assert_eq!(lines(&b), [(b.actors[0].name.clone(), "hp", 3)]);
    // And at full HP it still writes it, with nothing: `ePreHp` looks at
    // the effect, which is not zero, and `ApplyHpEffect` recovers nothing.
    b.use_skill(&db, Who::Actor(0), 3, Who::Actor(0)).unwrap();
    assert_eq!(lines(&b)[1], (b.actors[0].name.clone(), "hp", 0));
}

#[test]
fn a_raised_parameter_says_how_much_the_modifier_moved() {
    let db = db();
    let mut b = battle(&db);
    b.use_skill(&db, Who::Actor(0), 10, Who::Actor(0)).unwrap();
    // It raises the attack and the spirit, one line each.
    let [attack, _, spirit, _] = b.actors[0].modifier;
    assert!(attack > 0 && spirit > 0);
    let name = b.actors[0].name.clone();
    assert_eq!(
        lines(&b),
        [(name.clone(), "attack", attack), (name, "spirit", spirit)]
    );
    // At the cap —the base— they move no more, and that is a failure.
    for _ in 0..20 {
        b.use_skill(&db, Who::Actor(0), 10, Who::Actor(0)).unwrap();
    }
    assert_eq!(b.actors[0].modifier[0], b.actors[0].base[0]);
    assert_eq!(b.actors[0].modifier[2], b.actors[0].base[2]);
    assert_eq!(lines(&b).last().unwrap().1, "miss");
}

/// "!IsPositive() && !IsSuccess() && (affect_hp || affect_sp)": `vExecute`
/// returns there, and the defense's line never comes even if its roll would
/// have hit. (The roll is still made here: see `Battle::skill_rolls`.)
#[test]
fn a_missed_hit_fails_and_says_nothing_of_the_defense() {
    let mut db = db();
    let skill = db.skills.get_mut(&14).unwrap();
    skill.hit = 0;
    let mut b = battle(&db);
    b.use_skill(&db, Who::Actor(0), 14, Who::Enemy(0)).unwrap();
    assert_eq!(lines(&b), [(b.enemies[0].name.clone(), "miss", 0)]);
}

/// "If target will be killed, no further affects are applied": the damage
/// line and nothing after it, though the defense's roll hits.
#[test]
fn a_hit_that_kills_says_nothing_after_it() {
    let mut db = db();
    db.skills.get_mut(&14).unwrap().hit = 100;
    let mut b = battle(&db);
    b.enemies[0].hp = 1;
    b.use_skill(&db, Who::Actor(0), 14, Who::Enemy(0)).unwrap();
    assert_eq!(b.enemies[0].hp, 0, "the case wants it to kill");
    assert_ne!(b.enemies[0].modifier[1], 0, "and the defense's roll to hit");
    assert_eq!(lines(&b).len(), 1, "{:?}", lines(&b));
    assert_eq!(lines(&b)[0].1, "damage");
}

/// One line per target, in the order `vExecute` walks them, each with its
/// own: skill 14 on the two enemies of a troop of two.
#[test]
fn a_skill_on_every_enemy_says_each_one() {
    let mut db = db();
    db.skills.get_mut(&14).unwrap().hit = 100;
    let actor = Combatant::actor(&db, 1, None, None).unwrap();
    let one = Combatant::enemy(&db, 1, 0, false).unwrap();
    let two = Combatant::enemy(&db, 1, 1, false).unwrap();
    let mut b = Battle::new(vec![actor], vec![one, two], BATTLE_SEED, vec![], BTreeMap::new());
    // Enough HP that the hit does not kill, which would leave the defense
    // unsaid.
    for e in &mut b.enemies {
        e.hp_max = 999;
        e.hp = 999;
    }
    b.use_skill(&db, Who::Actor(0), 14, Who::Enemy(0)).unwrap();
    let said: Vec<&str> = b.results.iter().map(|r| r.what).collect();
    assert_eq!(said, ["damage", "defense", "damage", "defense"]);
}
