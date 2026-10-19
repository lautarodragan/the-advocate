//! A healing skill used from the pause menu, outside battle: easyrpg's
//! `Scene_ActorTarget::UpdateSkill`, `Game_Party::UseSkill` and the part of
//! `Game_Battler::UseSkill` that is not the battle's (`game_battler.cpp`,
//! `game_party.cpp`, `scene_actortarget.cpp`).
//!
//! It is here, next to the battle, because the console computes it with the
//! battle's code —`ba_skill_effect` and `ba_variance`, see
//! `skills_screen.s` in the runtime— and draws from the battle's
//! randomness: whoever compares a console's heal asks this for **the exact
//! number** with the seed the console had. Like the battle, it rolls the
//! critical before the variance, always at zero percent: RPG_RT's map
//! never doubles a heal, and the roll is there only so the two sides stay
//! in phase.
//!
//! **Outside battle the console keeps no states**, so a fallen actor is one
//! at 0 HP and a skill that cures any other state finds nothing to cure: it
//! is of no use, as an Antidote on the map is of none.

use crate::db::{SCOPE_ALLY, SCOPE_PARTY, SCOPE_SELF, SKILL_NORMAL};
use crate::simulate::{apply_variance, skill_effect, Combatant, Rng};
use ditto::schema::Skill;
use rm2k_rules::skill::cures_death;

/// Skill `skill` used by party member `user` on `target` —ignored by the
/// scopes that do not choose: self and party—. Whether it was of use, which
/// is what spends its SP and what RM2k sounds the buzzer by. `party` is
/// left as the use leaves it.
///
/// * A user without the SP for it: nothing, not even a roll —the
///   `GetSp() < CalculateSkillCost` before `UseSkill`—.
/// * Each target, in party order: the effect, `CalcSkillEffect` with the
///   variance; death cured if the skill cures it and the target is down
///   —the `SetHp(1)` of `RemoveStates`—; and then the HP and the SP go up
///   only if they are not full and the target is standing, the revived one
///   by `effect - 1`. A skill that revives without touching HP heals the
///   revived one `effect` percent of its maximum, minus that one.
/// * If it was of use to anyone, the SP, once.
pub fn use_skill(
    skill: &Skill,
    party: &mut [Combatant],
    user: usize,
    target: usize,
    rng: &mut Rng,
) -> bool {
    if skill.r#type.to_i32() != SKILL_NORMAL || party[user].sp < skill.sp_cost as i64 {
        return false;
    }
    let targets: Vec<usize> = match skill.scope.to_i32() {
        SCOPE_SELF => vec![user],
        SCOPE_ALLY => vec![target],
        SCOPE_PARTY => (0..party.len()).collect(),
        _ => return false,
    };
    let mut used = false;
    for t in targets {
        let source = party[user].clone();
        let critical = rng.percent(0);
        let effect = apply_variance(
            skill_effect(&source, &party[t], skill, critical),
            skill.variance as i64,
            rng,
        );
        let one = &mut party[t];
        let mut revived = 0;
        if cures_death(skill) && one.hp == 0 {
            revived = 1;
            used = true;
            one.hp = 1;
        }
        if effect > 0 && skill.affect_hp && one.hp < one.hp_max && one.hp > 0 {
            used = true;
            one.change_hp(effect - revived, false);
        } else if effect > 0 && revived == 1 && !skill.affect_hp {
            used = true;
            one.change_hp(one.hp_max * effect / 100 - revived, false);
        }
        if effect > 0 && skill.affect_sp && one.sp < one.sp_max && one.hp > 0 {
            used = true;
            one.sp = (one.sp + effect).min(one.sp_max);
        }
    }
    if used {
        let u = &mut party[user];
        u.sp = (u.sp - skill.sp_cost as i64).max(0);
    }
    used
}
