//! What a skill can do outside battle, as RM2k decides it.
//!
//! easyrpg-player's `Algo::IsSkillUsable` with `require_states_persist` and
//! outside battle, which is what `Game_Battler::IsSkillUsable` asks after
//! the cost and the states, and what `Window_Skill` greys a skill by on the
//! map. What it leaves out depends on the moment, not on the database: the
//! SP the actor has, the states it carries, and the weapon a skill with
//! physical attributes asks for (`Game_Actor::IsSkillUsable`).

use ditto::schema::{Skill, SkillScope, SkillType, State, StatePersistence};

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

#[cfg(test)]
mod tests {
    use super::*;

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
