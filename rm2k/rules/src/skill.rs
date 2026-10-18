//! What a skill can do outside battle, as RM2k decides it.
//!
//! easyrpg-player's `Algo::IsSkillUsable` with `require_states_persist` and
//! outside battle, which is what `Game_Battler::IsSkillUsable` asks after
//! the cost and the states, and what `Window_Skill` greys a skill by on the
//! map. What it leaves out depends on the moment, not on the database: the
//! SP the actor has and the states it carries. The weapon a skill with
//! physical attributes asks for (`Game_Actor::IsSkillUsable`), which
//! depends on what the actor holds, is [`weapons_allow`].

use ditto::schema::{Attribute, AttributeType, Item, ItemType, Skill, SkillScope, SkillType, State, StatePersistence};

/// Whether the map can use `skill`, by its data alone. `states` are the
/// database's, which a skill's `state_effects` index from state 1.
///
/// * a **switch** skill, if it says it can be used on the map
///   (`occasion_field`);
/// * a **normal** one —or a subskill, which RM2k reads as normal—, if it
///   does not target enemies and it touches HP or SP, or cures a state that
///   persists after battle;
/// * **teleport and escape** depend on where the party is and what the game
///   allowed —`Main_Data::game_targets`, `GetAllowTeleport`—, and this does
///   not know: they answer no. No game this was measured on teaches one.
pub fn usable_on_the_map(skill: &Skill, states: &[State]) -> bool {
    match skill.r#type {
        SkillType::Switch => skill.occasion_field,
        SkillType::Teleport | SkillType::Escape => false,
        _ => {
            if matches!(skill.scope, SkillScope::Enemy | SkillScope::Enemies) {
                return false;
            }
            if skill.affect_hp || skill.affect_sp {
                return true;
            }
            skill.state_effects.iter().enumerate().any(|(i, &on)| {
                on && states
                    .iter()
                    .find(|s| s.id == i as i32 + 1)
                    .is_some_and(|s| s.r#type == StatePersistence::Persists)
            })
        }
    }
}

/// Whether `skill` raises the fallen: it cures state 1, death. It is the
/// first state of `Game_Battler::UseSkill`'s loop, the one that sets
/// `revived`. RM2003's `reverse_state_effect`, which turns the cure into an
/// infliction, is not RM2k's, and the schema does not read it.
pub fn cures_death(skill: &Skill) -> bool {
    skill.state_effects.first().copied().unwrap_or(false)
}

/// The attributes `skill` asks a weapon for, by index —`id - 1`—: its
/// physical ones, unless it has `affect_attr_defence`, which shifts ranks
/// instead of hitting with them. The first half of
/// `Game_Actor::IsSkillUsable`; `attributes` are the database's, in id
/// order. An attribute past the database's end asks for nothing: easyrpg
/// would read past its array, and no game carries one.
pub fn weapon_attributes_asked(skill: &Skill, attributes: &[Attribute]) -> Vec<bool> {
    if skill.affect_attr_defence {
        return Vec::new();
    }
    skill
        .attribute_effects
        .iter()
        .enumerate()
        .map(|(i, &on)| on && attributes.get(i).is_some_and(|a| a.r#type == AttributeType::Physical))
        .collect()
}

/// Whether an actor holding `held` —the items in its first two slots,
/// weapon and shield, in either order; a shield or an empty slot counts for
/// nothing— can use `skill` by its weapons: `Game_Actor::IsSkillUsable`.
/// **Each** physical attribute the skill carries has to be on one of the
/// two weapons —not necessarily the same one—; a skill without any is
/// always usable by this rule. RPG Maker 2000 and 2003 ask the same, and a
/// two-weapon actor's second weapon is the one in the shield's slot
/// (`Get2ndWeapon`). The SP and the states are asked elsewhere.
pub fn weapons_allow(skill: &Skill, attributes: &[Attribute], held: &[&Item]) -> bool {
    let weapons: Vec<&Item> = held.iter().copied().filter(|i| i.r#type == ItemType::Weapon).collect();
    weapon_attributes_asked(skill, attributes)
        .iter()
        .enumerate()
        .all(|(i, &asked)| !asked || weapons.iter().any(|w| w.attribute_set.get(i).copied().unwrap_or(false)))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn attribute(id: i32, physical: bool) -> Attribute {
        Attribute {
            id,
            r#type: if physical { AttributeType::Physical } else { AttributeType::Magical },
            ..Default::default()
        }
    }

    fn weapon(t: ItemType, set: &[bool]) -> Item {
        Item { r#type: t, attribute_set: set.to_vec(), ..Default::default() }
    }

    /// Sword physical, Flame magical, Martial physical.
    fn three() -> Vec<Attribute> {
        vec![attribute(1, true), attribute(2, false), attribute(3, true)]
    }

    #[test]
    fn a_physical_attribute_asks_for_a_weapon_that_carries_it() {
        let mut s = skill(SkillType::Normal, SkillScope::Enemy);
        s.attribute_effects = vec![false, false, true];
        let staff = weapon(ItemType::Weapon, &[true]);
        let gloves = weapon(ItemType::Weapon, &[false, false, true]);
        assert!(!weapons_allow(&s, &three(), &[]));
        assert!(!weapons_allow(&s, &three(), &[&staff]));
        assert!(weapons_allow(&s, &three(), &[&gloves]));
        assert!(weapons_allow(&s, &three(), &[&staff, &gloves]));
    }

    #[test]
    fn a_magical_one_asks_for_nothing_and_neither_does_none() {
        let mut s = skill(SkillType::Normal, SkillScope::Enemy);
        assert!(weapons_allow(&s, &three(), &[]));
        s.attribute_effects = vec![false, true];
        assert!(weapons_allow(&s, &three(), &[]));
    }

    #[test]
    fn affect_attr_defence_asks_for_nothing() {
        let mut s = skill(SkillType::Normal, SkillScope::Enemy);
        s.attribute_effects = vec![true];
        s.affect_attr_defence = true;
        assert!(weapons_allow(&s, &three(), &[]));
        assert!(weapon_attributes_asked(&s, &three()).is_empty());
    }

    #[test]
    fn each_one_on_either_weapon_and_a_shield_carries_nothing() {
        let mut s = skill(SkillType::Normal, SkillScope::Enemy);
        s.attribute_effects = vec![true, false, true];
        let sword = weapon(ItemType::Weapon, &[true]);
        let gloves = weapon(ItemType::Weapon, &[false, false, true]);
        let shield = weapon(ItemType::Shield, &[false, false, true]);
        assert!(!weapons_allow(&s, &three(), &[&sword]));
        assert!(weapons_allow(&s, &three(), &[&sword, &gloves]));
        assert!(weapons_allow(&s, &three(), &[&gloves, &sword]));
        assert!(!weapons_allow(&s, &three(), &[&sword, &shield]));
    }

    #[test]
    fn past_the_database_asks_for_nothing() {
        let mut s = skill(SkillType::Normal, SkillScope::Enemy);
        s.attribute_effects = vec![false, false, false, true];
        assert!(weapons_allow(&s, &three(), &[]));
    }

    #[test]
    fn death_is_the_first_state() {
        let mut s = skill(SkillType::Normal, SkillScope::Ally);
        assert!(!cures_death(&s));
        s.state_effects = vec![false, true];
        assert!(!cures_death(&s));
        s.state_effects = vec![true];
        assert!(cures_death(&s));
    }

    fn skill(t: SkillType, scope: SkillScope) -> Skill {
        Skill { r#type: t, scope, ..Default::default() }
    }

    fn state(id: i32, persists: bool) -> State {
        State {
            id,
            r#type: if persists { StatePersistence::Persists } else { StatePersistence::Ends },
            ..Default::default()
        }
    }

    #[test]
    fn a_switch_skill_goes_by_its_occasion() {
        let mut s = skill(SkillType::Switch, SkillScope::Enemy);
        s.occasion_field = true;
        assert!(usable_on_the_map(&s, &[]));
        s.occasion_field = false;
        assert!(!usable_on_the_map(&s, &[]));
    }

    #[test]
    fn a_heal_on_an_ally_is_usable_and_on_an_enemy_is_not() {
        let mut s = skill(SkillType::Normal, SkillScope::Ally);
        s.affect_hp = true;
        assert!(usable_on_the_map(&s, &[]));
        s.scope = SkillScope::Enemy;
        assert!(!usable_on_the_map(&s, &[]));
    }

    #[test]
    fn curing_a_state_counts_only_if_it_persists() {
        let states = [state(1, false), state(2, true), state(3, false)];
        let mut s = skill(SkillType::Normal, SkillScope::Party);
        s.state_effects = vec![false, false, true];
        assert!(!usable_on_the_map(&s, &states));
        s.state_effects = vec![false, true];
        assert!(usable_on_the_map(&s, &states));
    }

    #[test]
    fn a_buff_alone_is_not_and_teleport_is_not() {
        let mut s = skill(SkillType::Normal, SkillScope::Self_);
        s.affect_attack = true;
        assert!(!usable_on_the_map(&s, &[]));
        let mut t = skill(SkillType::Teleport, SkillScope::Self_);
        t.affect_hp = true;
        assert!(!usable_on_the_map(&t, &[]));
    }
}
