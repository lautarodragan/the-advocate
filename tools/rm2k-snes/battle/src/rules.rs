//! What RM2k's battle says about the database, cut down to what this
//! battle does: which skills it knows how to offer and to whom, what each
//! enemy can do, which items go in the list, what an attack costs, what a
//! troop gives.
//!
//! Every rule comes from easyrpg-player, and each says from where. **What
//! is cut is declared where it is cut**: an enemy action the battle does not
//! do drops out of the list instead of being done wrong.

use crate::db::{
    self, Db, ITEM_MEDICINE, ITEM_WEAPON, SCOPE_ALLY, SCOPE_ENEMY, SKILL_NORMAL, SKILL_SWITCH,
};
use crate::fail::{Bad, Result};
use ditto::schema::{Actor, Item, Skill};

/// The cap of a parameter, like `Game_Actor::GetAtk` and its siblings.
pub const PARAM_MAX: i64 = 999;

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

/// The level an actor starts at: `Game_Actor::Setup`, which calls
/// `ChangeLevel(initial_level)`. A 0 in the database is 1.
pub fn level_of(actor: &Actor) -> i64 {
    match actor.initial_level {
        0 => 1,
        level => level as i64,
    }
}

/// A curve of the actor at `level`: the database's table starts at level
/// 1, so the index is the level minus one, and past its end it is 0. A
/// level of 0 or less counts from the end, which is how the model this
/// replaces indexed it; it is not a level RM2k has.
fn curve_at(values: &[i16], level: i64) -> Result<i64> {
    let at = level - 1;
    if at >= values.len() as i64 {
        return Ok(0);
    }
    let at = if at < 0 { values.len() as i64 + at } else { at };
    values
        .get(at as usize)
        .map(|&v| v as i64)
        .ok_or_else(|| Bad::answer(format!("there is no level {level} in a curve")))
}

/// The six curves by name.
pub fn param_of(actor: &Actor, which: &str, level: Option<i64>) -> Result<i64> {
    let p = &actor.parameters;
    let values = match which {
        "maxhp" => &p.maxhp,
        "maxsp" => &p.maxsp,
        "attack" => &p.attack,
        "defense" => &p.defense,
        "spirit" => &p.spirit,
        "agility" => &p.agility,
        _ => return Err(Bad::usage(format!("there is no curve {which:?}"))),
    };
    curve_at(values, level.unwrap_or_else(|| level_of(actor)))
}

/// What an item adds when equipped: attack, defense, spirit, agility.
pub fn points(item: &Item) -> [i64; 4] {
    [
        item.atk_points1 as i64,
        item.def_points1 as i64,
        item.spi_points1 as i64,
        item.agi_points1 as i64,
    ]
}

/// Attack, defense, spirit and agility: the level's plus what the
/// equipment adds, clamped to 1..999 like `Game_Actor::GetAtk` and its
/// siblings. Without `level`, the starting one.
pub fn equipped_params(
    db: &Db,
    actor: i32,
    equipment: &[i32],
    level: Option<i64>,
) -> Result<[i64; 4]> {
    let a = db.actor(actor)?;
    let mut base = [0; 4];
    for (b, which) in base
        .iter_mut()
        .zip(["attack", "defense", "spirit", "agility"])
    {
        *b = param_of(a, which, level)?;
    }
    for &item in equipment {
        if item != 0 {
            for (b, p) in base.iter_mut().zip(points(db.item(item)?)) {
                *b += p;
            }
        }
    }
    Ok(base.map(|b| b.clamp(1, PARAM_MAX)))
}

/// An actor's starting equipment: weapon, shield, armor, helmet and
/// accessory, by item number, 0 for none.
pub fn initial_equipment(actor: &Actor) -> Vec<i32> {
    let e = &actor.initial_equipment;
    vec![
        e.weapon_id,
        e.shield_id,
        e.armor_id,
        e.helmet_id,
        e.accessory_id,
    ]
}

/// The skills this actor **knows**, usable or not, sorted:
/// `Game_Actor::LearnLevelSkills`, the ones with a level lower than or
/// equal to its own. Without `level`, the starting one.
pub fn learned_skills(actor: &Actor, level: Option<i64>) -> Vec<i32> {
    let level = level.unwrap_or_else(|| level_of(actor));
    let mut out: Vec<i32> = actor
        .skills
        .iter()
        .filter(|l| l.skill_id != 0 && l.level as i64 <= level)
        .map(|l| l.skill_id)
        .collect();
    out.sort_unstable();
    out.dedup();
    out
}

/// Whether this battle knows how to offer this skill: of type `normal` or
/// `switch` —`teleport` and `escape` do not exist here, and `subskill` is
/// RM2k3's—, and with a cost of two digits, which is what the list writes.
/// All five scopes are in.
pub fn skill_usable(skill: &Skill) -> bool {
    matches!(skill.r#type.to_i32(), SKILL_NORMAL | SKILL_SWITCH) && skill.sp_cost <= 99
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
/// it touches HP, SP or one of the four parameters, which is all that
/// exists here. It does not depend on the target, because a living one
/// without states is the same as any other.
pub fn skill_works_alone(skill: &Skill) -> bool {
    db::targets_enemies(skill)
        || skill.affect_hp
        || skill.affect_sp
        || skill.affect_attack
        || skill.affect_defense
        || skill.affect_spirit
        || skill.affect_agility
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

/// At which level this actor learns this skill: the lowest of the rows of
/// its table that name it, or 0 if none does —that one only a
/// `ChangeSkills` teaches—.
pub fn level_learned(actor: &Actor, skill: i32) -> i64 {
    actor
        .skills
        .iter()
        .filter(|l| l.skill_id == skill)
        .map(|l| l.level as i64)
        .min()
        .unwrap_or(0)
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

/// Whether the item removes the dead state: the first of its `state_set`.
pub fn revives(item: &Item) -> bool {
    item.state_set.first() == Some(&true)
}

/// Whether the item goes in the battle's list: `Game_Party::IsItemUsable`
/// in battle —a medicine not marked "only outside battle"— cut down to the
/// ones that heal HP, and of the `ko_only` ones, the ones that revive.
pub fn item_usable_in_battle(item: &Item) -> bool {
    item.r#type.to_i32() == ITEM_MEDICINE
        && !item.occasion_field1
        && (item.recover_hp != 0 || item.recover_hp_rate != 0)
        && (revives(item) || !item.ko_only)
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
    use super::floor_div;

    #[test]
    fn floor_div_rounds_down() {
        assert_eq!(floor_div(7, 2), 3);
        assert_eq!(floor_div(-7, 2), -4);
        assert_eq!(floor_div(7, -2), -4);
        assert_eq!(floor_div(-8, 2), -4);
    }
}
