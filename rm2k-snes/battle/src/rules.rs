//! What RM2k's battle says about the database, cut down to what this
//! battle does: which skills it knows how to offer and to whom, what each
//! enemy can do, which items go in the list, what an attack costs, what a
//! troop gives.
//!
//! Every rule comes from easyrpg-player, and each says from where. **What
//! is cut is declared where it is cut**: an enemy action the battle does not
//! do drops out of the list instead of being done wrong.

use crate::db::{
    self, Db, ITEM_MEDICINE, ITEM_SPECIAL, ITEM_WEAPON, SCOPE_ALLY, SCOPE_ENEMY, SKILL_NORMAL,
    SKILL_SWITCH,
};
use crate::fail::{Bad, Result};
use ditto::schema::{Actor, Item, Skill};
use rm2k_rules::actor;

/// The actor's own rules —its level, its curves, what equipment adds, what
/// it knows— are RM2k's and not this battle's: they live in `rm2k-rules`,
/// and the ones the other stages reach through this crate are re-exported.
pub use rm2k_rules::actor::{
    initial_equipment, learned_skills, level_learned, level_of, points, EQUIPMENT_SLOTS, PARAM_MAX,
};

/// How many actions an enemy can carry: the console weighs them in a list
/// that long (`BA_SKILL_LIST`). The answer is no if one carries more.
pub const ACTIONS_MAX: usize = 16;

/// The rating of the action an enemy gets when none of its own is left:
/// with a single one it does not matter which, because nothing is rolled.
pub const ACTION_RATING_ALONE: i64 = 50;

/// `lcf::rpg::EnemyAction`'s kinds, basic actions and conditions: the ones
/// this reads.
const ACTION_KIND_BASIC: i32 = 0;
const ACTION_KIND_SKILL: i32 = 1;
const ACTION_BASIC_ATTACK: i32 = 0;
const ACTION_CONDITION_ALWAYS: i32 = 0;

/// Python's `//`: division rounding toward minus infinity. RM2k's
/// formulas are C++ and truncate, but they were written against a model
/// that floored, and on every value they meet the two agree; where they
/// would not —a negative effect halved— the caller says so.
pub fn floor_div(a: i64, b: i64) -> i64 {
    let q = a / b;
    if (a % b != 0) && ((a < 0) != (b < 0)) {
        q - 1
    } else {
        q
    }
}

/// A curve of the actor at `level` —without it, the starting one—, by its
/// name: [`actor::curve_at`], and no if there is no such curve or no such
/// level in it.
pub fn param_of(actor: &Actor, which: &str, level: Option<i64>) -> Result<i64> {
    let values = actor::curve(actor, which)
        .ok_or_else(|| Bad::usage(format!("there is no curve {which:?}")))?;
    let level = level.unwrap_or_else(|| level_of(actor));
    actor::curve_at(values, level)
        .ok_or_else(|| Bad::answer(format!("there is no level {level} in a curve")))
}

/// Attack, defense, spirit and agility: the level's plus what the
/// equipment adds, clamped ([`actor::with_equipment`]). Without `level`,
/// the starting one; an item the database lacks is a no.
pub fn equipped_params(
    db: &Db,
    actor: i32,
    equipment: &[i32],
    level: Option<i64>,
) -> Result<[i64; 4]> {
    let a = db.actor(actor)?;
    let mut base = [0; 4];
    for (b, which) in base.iter_mut().zip(actor::EQUIPPED) {
        *b = param_of(a, which, level)?;
    }
    let mut items = Vec::new();
    for &item in equipment {
        if item != 0 {
            items.push(db.item(item)?);
        }
    }
    Ok(actor::with_equipment(base, items))
}

/// Whether this battle knows how to offer this skill: of type `normal` or
/// `switch` —`teleport` and `escape` do not exist here, and `subskill` is
/// RM2k3's—, and with a cost of two digits, which is what the list writes.
/// All five scopes are in. Offering it is not letting it be chosen: see
/// [`usable_in_battle`].
pub fn skill_usable(skill: &Skill) -> bool {
    matches!(skill.r#type.to_i32(), SKILL_NORMAL | SKILL_SWITCH) && skill.sp_cost <= 99
}

/// Whether the battle lets it be chosen at all, whoever uses it and with
/// whatever SP: `Algo::IsSkillUsable` in battle, which
/// `Window_Skill::CheckEnable` asks of every row. A `normal` skill always —it
/// has no occasion flags—, a `switch` one only with `occasion_battle`, and a
/// `teleport` or `escape` one never. RM2k 2000 lists the others anyway, grey,
/// and A on one only sounds the buzzer: Emily's Change Tape, a switch skill
/// for the map, is one. What the converter emits as `skill_in_battle`.
pub fn usable_in_battle(skill: &Skill) -> bool {
    match skill.r#type.to_i32() {
        SKILL_NORMAL => true,
        SKILL_SWITCH => skill.occasion_battle,
        _ => false,
    }
}

/// The attributes `skill` asks a weapon for, by index —`id - 1`—: its
/// physical ones, unless it has `affect_attr_defence`. RM2k's rule, in
/// `rm2k-rules` ([`rm2k_rules::skill::weapon_attributes_asked`]), with this
/// database's attributes: the converter's `skill_weapon` comes from here.
pub fn weapon_attributes_asked(db: &Db, skill: &Skill) -> Vec<bool> {
    let attributes: Vec<_> = db.attributes.values().cloned().collect();
    rm2k_rules::skill::weapon_attributes_asked(skill, &attributes)
}

/// Whether an actor wearing `equipment` —weapon, shield, armor, helmet,
/// accessory, by item number, 0 for empty— can use `skill` by its weapons:
/// `Game_Actor::IsSkillUsable`, which greys out, in battle and in the menu,
/// a skill whose physical attributes are not all on its weapon or its
/// second weapon. Not whether the battle offers it —[`skill_usable`]—, nor
/// the SP. An item the database lacks is a no.
pub fn weapons_allow(db: &Db, skill: &Skill, equipment: &[i32]) -> Result<bool> {
    let mut held = Vec::new();
    for &n in equipment.iter().take(2) {
        if n > 0 {
            held.push(db.item(n)?);
        }
    }
    let attributes: Vec<_> = db.attributes.values().cloned().collect();
    Ok(rm2k_rules::skill::weapons_allow(skill, &attributes, &held))
}

/// Whether choosing it asks for whom: only the single-target ones
/// —`enemy` and `ally`— and not a switch one, which
/// `Scene_Battle::AssignSkill` records on the one using it.
pub fn needs_target(skill: &Skill) -> bool {
    skill.r#type.to_i32() != SKILL_SWITCH
        && matches!(skill.scope.to_i32(), SCOPE_ENEMY | SCOPE_ALLY)
}

/// `EnemyAi::IsSkillEffectiveOn` for a living target without states: one
/// that targets enemies always is; one that targets its own side, only if
/// it touches HP, SP or one of the four parameters, or shifts the rank of
/// some attribute —`affect_attr_defence` with one it carries—, which is all
/// that exists here. It does not depend on the target, because a living one
/// without states is the same as any other: easyrpg does not ask whether
/// the rank can still move.
pub fn skill_works_alone(skill: &Skill) -> bool {
    db::targets_enemies(skill)
        || skill.affect_hp
        || skill.affect_sp
        || skill.affect_attack
        || skill.affect_defense
        || skill.affect_spirit
        || skill.affect_agility
        || (skill.affect_attr_defence && skill.attribute_effects.iter().any(|&a| a))
}

/// The skills this actor knows that the battle can offer, in the order the
/// menu puts them: `LearnSkill` sorts by number.
pub fn skills_of(db: &Db, actor: i32, level: Option<i64>) -> Result<Vec<i32>> {
    let mut out = Vec::new();
    for s in learned_skills(db.actor(actor)?, level) {
        if skill_usable(db.skill(s)?) {
            out.push(s);
        }
    }
    Ok(out)
}

/// What the actor's skill command is called: `Game_Actor::GetSkillName`,
/// its `skill_name` if it has `rename_skill`, and otherwise the terms'
/// `command_skill`.
pub fn skill_command_name(db: &Db, actor: i32) -> Result<String> {
    let a = db.actor(actor)?;
    Ok(if a.rename_skill && !a.skill_name.is_empty() {
        a.skill_name.clone()
    } else {
        db.terms.command_skill.clone()
    })
}

/// What attacking costs with this equipment: `CalculateWeaponSpCost`, the
/// weapon's `sp_cost` —only the first slot, and never the armor's, even
/// if it carries one—.
pub fn weapon_sp_of(db: &Db, equipment: &[i32]) -> Result<i64> {
    let Some(&weapon) = equipment.first() else {
        return Ok(0);
    };
    if weapon == 0 {
        return Ok(0);
    }
    Ok(match db.items.get(&weapon) {
        Some(item) if item.r#type.to_i32() == ITEM_WEAPON => item.sp_cost as i64,
        _ => 0,
    })
}

/// The critical hit chance the battle rolls against, as a whole
/// percentage: `GetCriticalHitChance` times a hundred and truncated, which
/// is what `Algo::CalcCriticalHitChance` does. `own` is the battler's
/// `critical_hit_chance` —once every so many hits— or None without
/// `critical_hit`, and zero counts as the database's default, 30; `bonus`
/// is what its weapons add, in percent, and an enemy has none.
///
/// **In single-precision floating point, as easyrpg adds them**, and it is
/// not a detail: `1 / 25` comes out a hair under 0.04, so a chance of 25 is
/// 3 % and not 4 %, and a 12 % weapon on an actor without `critical_hit`
/// is 11 %. That is why the console does not add the two parts: it reads
/// the result from a table the converter writes with this.
pub fn critical_percent(own: Option<i32>, bonus: i32) -> i64 {
    let own: f32 = match own {
        Some(every) => 1.0 / (if every == 0 { 30 } else { every }) as f32,
        None => 0.0,
    };
    let chance: f32 = own + bonus as f32 / 100.0;
    (f64::from(chance) * 100.0) as i64
}

/// An actor's own part of its critical hit: `critical_hit_chance` if it has
/// `critical_hit`.
pub fn actor_critical_own(actor: &Actor) -> Option<i32> {
    actor.critical_hit.then_some(actor.critical_hit_chance)
}

/// What the weapons add to an actor's critical hit: the highest
/// `critical_hit` of the weapons it has equipped —`ForEachEquipment` with
/// weapons and without armor, in `Game_Actor::GetCriticalHitChance`—. Only
/// the first two slots can hold one, and the second only with
/// `two_weapon`.
pub fn weapon_critical_bonus(db: &Db, equipment: &[i32]) -> i32 {
    equipment
        .iter()
        .filter_map(|id| db.items.get(id))
        .filter(|item| item.r#type.to_i32() == ITEM_WEAPON)
        .map(|item| item.critical_hit)
        .fold(0, i32::max)
}

/// An actor's critical hit with this equipment: see [`critical_percent`].
pub fn actor_critical(db: &Db, actor: i32, equipment: &[i32]) -> Result<i64> {
    Ok(critical_percent(
        actor_critical_own(db.actor(actor)?),
        weapon_critical_bonus(db, equipment),
    ))
}

/// Whether the item removes the dead state: the first of its `state_set`.
pub fn revives(item: &Item) -> bool {
    item.state_set.first() == Some(&true)
}

/// Whether a medicine goes in the battle's list: `Game_Party::IsItemUsable`
/// in battle —a medicine not marked "only outside battle"— cut down to the
/// ones that heal HP or SP, and of the `ko_only` ones, the ones that
/// revive. The ones left out only remove states, which the battle keeps
/// only on enemies —see `Held` in `simulate`—.
///
/// Until 2026-10-04 it was the ones that heal HP: it was written on
/// 2026-09-12, when the SP were not state yet, and stayed when the skills
/// made them so.
pub fn item_usable_in_battle(item: &Item) -> bool {
    item.r#type.to_i32() == ITEM_MEDICINE
        && !item.occasion_field1
        && (item.recover_hp != 0
            || item.recover_hp_rate != 0
            || item.recover_sp != 0
            || item.recover_sp_rate != 0)
        && (revives(item) || !item.ko_only)
}

/// The skill a special item casts in battle, if this battle offers it:
/// `Game_Party::IsItemUsable` of a `special` item in battle, which asks
/// `Algo::IsSkillUsable` of its skill —a `normal` one always, a `switch`
/// one with `occasion_battle`, `teleport` and `escape` never—; RM2k3's
/// `subskill` is not here, like everywhere else in this battle. It costs no
/// SP —`Skill::vStart` spends the item instead—, so the cost does not
/// matter. Whether the actor giving the command can use it is
/// [`item_usable_by`], and that RPG_RT also asks for some actor of the party
/// who can act and use it is that same actor, who is giving the command.
pub fn item_skill_in_battle(db: &Db, item: &Item) -> Option<i32> {
    if item.r#type.to_i32() != ITEM_SPECIAL {
        return None;
    }
    let skill = db.skills.get(&item.skill_id)?;
    usable_in_battle(skill).then_some(skill.id)
}

/// Whether the item goes in the battle's list: a medicine
/// ([`item_usable_in_battle`]) or a special item whose skill the battle
/// casts ([`item_skill_in_battle`]). What the converter emits as
/// `item_battle`; a special one goes only in the list of an actor its
/// `actor_set` lets use it, which the console looks at.
pub fn item_in_battle(db: &Db, item: &Item) -> bool {
    item_usable_in_battle(item) || item_skill_in_battle(db, item).is_some()
}

/// `Game_Actor::IsItemUsable`: whether actor `actor` of the database can
/// use the item, by its `actor_set`. A set shorter than the actor's number
/// says yes: the editor does not write the actors past the last one it
/// unchecked.
pub fn item_usable_by(item: &Item, actor: i64) -> bool {
    usize::try_from(actor - 1)
        .ok()
        .and_then(|k| item.actor_set.get(k).copied())
        .unwrap_or(true)
}

/// One action of an enemy's list: its rating, the skill or `None` for
/// the basic attack, and whether it is effective alone
/// (`skill_works_alone`), which the AI looks at after taking the maximum.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Action {
    pub rating: i64,
    pub skill: Option<i32>,
    pub effective: bool,
}

/// The enemy's actions this battle knows how to do, in the database's
/// order: the list `SelectEnemyAiActionRpgRtCompat` walks, cut down.
///
/// * the basic attack, and the `normal` skills the battle can offer —not
///   the switch ones: the AI would roll a target for them by their scope
///   and the battle would record them on the one using them—;
/// * only with the "always" condition: the others drop out, as if not met;
/// * and without switches turned on or off when chosen.
///
/// If none is left, the basic attack alone.
pub fn actions_of_enemy(db: &Db, enemy: i32) -> Result<Vec<Action>> {
    let mut out = Vec::new();
    for a in &db.enemy(enemy)?.actions {
        if a.condition_type.to_i32() != ACTION_CONDITION_ALWAYS || a.switch_on || a.switch_off {
            continue;
        }
        let kind = a.kind.to_i32();
        if kind == ACTION_KIND_BASIC && a.basic.to_i32() == ACTION_BASIC_ATTACK {
            out.push(Action {
                rating: a.rating as i64,
                skill: None,
                effective: true,
            });
            continue;
        }
        if kind != ACTION_KIND_SKILL {
            continue;
        }
        match db.skills.get(&a.skill_id) {
            Some(s) if s.r#type.to_i32() == SKILL_NORMAL && skill_usable(s) => {
                out.push(Action {
                    rating: a.rating as i64,
                    skill: Some(s.id),
                    effective: skill_works_alone(s),
                });
            }
            _ => {}
        }
    }
    if out.is_empty() {
        out.push(Action {
            rating: ACTION_RATING_ALONE,
            skill: None,
            effective: true,
        });
    }
    Ok(out)
}

/// `Game_EnemyParty::GetMoney` on winning: the `gold` of every member, up
/// to `ENEMIES_MAX`. The console subtracts the ones that stayed hidden.
pub fn troop_gold(db: &Db, troop: i32) -> Result<i64> {
    let mut sum = 0;
    for m in db.members(troop)? {
        sum += db.enemy(m.enemy_id)?.gold as i64;
    }
    Ok(sum)
}

/// `Game_EnemyParty::GetExp`, the same.
pub fn troop_exp(db: &Db, troop: i32) -> Result<i64> {
    let mut sum = 0;
    for m in db.members(troop)? {
        sum += db.enemy(m.enemy_id)?.exp as i64;
    }
    Ok(sum)
}

#[cfg(test)]
mod tests {
    use super::{critical_percent, floor_div};

    /// The numbers are easyrpg's, worked out apart in single precision:
    /// the ones that are not the integers they look like are the point.
    #[test]
    fn the_critical_hit_adds_in_floating_point() {
        assert_eq!(critical_percent(Some(30), 0), 3);
        assert_eq!(critical_percent(Some(10), 0), 10);
        assert_eq!(critical_percent(Some(1), 0), 100);
        assert_eq!(critical_percent(None, 0), 0);
        assert_eq!(critical_percent(Some(0), 0), 3, "zero is the default, 30");
        assert_eq!(
            critical_percent(Some(25), 0),
            3,
            "1 / 25 is a hair under 0.04"
        );
        assert_eq!(critical_percent(None, 12), 11, "0.12 is a hair under too");
        assert_eq!(critical_percent(Some(10), 25), 34);
        assert_eq!(critical_percent(Some(30), 10), 13);
    }

    #[test]
    fn floor_div_rounds_down() {
        assert_eq!(floor_div(7, 2), 3);
        assert_eq!(floor_div(-7, 2), -4);
        assert_eq!(floor_div(7, -2), -4);
        assert_eq!(floor_div(-8, 2), -4);
    }
}
