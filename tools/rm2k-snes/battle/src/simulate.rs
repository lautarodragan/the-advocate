//! RM2k's turn-based battle, played with the same rules and the same
//! randomness as the console, so that whoever compares a console's battle
//! can know **the exact number** it has to put in each HP, turn by turn.
//!
//! **None of the numbers here was written from memory.** They all come
//! from easyrpg-player, and each one says where from:
//!
//! ```text
//! src/algo.cpp                CalcNormalAttackEffect, CalcNormalAttackToHit,
//!                             CalcCriticalHitChance, VarianceAdjustEffect,
//!                             AdjustDamageForDefend, CalcSkillEffect,
//!                             CalcSkillToHit, CalcSkillCost
//! src/scene_battle_rpg2k.cpp  CreateExecutionOrder, CreateEnemyActions
//! src/scene_battle.cpp        InitEscapeChance, TryEscape
//! src/game_enemy.cpp          GetHitChance, GetCriticalHitChance
//! src/game_actor.cpp          GetHitChance, GetCriticalHitChance,
//!                             LearnSkill, LearnLevelSkills,
//!                             CalculateWeaponSpCost
//! src/rand.cpp                PercentChance
//! src/game_battlealgorithm.cpp  Skill::vStart, Skill::vExecute
//! src/game_battler.cpp        CanChangeAtkModifier and its siblings, AdjustParam
//! src/enemyai.cpp             SelectEnemyAiActionRpgRtCompat, MakeSkillAction,
//!                             IsSkillEffectiveOn
//! ```
//!
//! Three things are **not** RM2k's, and all three are on purpose:
//!
//! * **The randomness.** RPG_RT draws from a generator nobody can
//!   reproduce. Here it is a sixteen-bit xorshift —the one the console
//!   already uses for `ControlVars`— with **its own seed**, [`BATTLE_SEED`]:
//!   a battle does not advance the map's randomness, so a random
//!   `ControlVars` gives the same with or without a battle in between.
//! * **The divisions.** Where easyrpg does the math in floating point and
//!   truncates on return, here it is integer. In the agility adjustment
//!   that matters, and it divides **rounding up**: see
//!   [`hit_rate_by_agility`].
//! * **What is missing.** States, attributes, rows and the double attack.
//!   Of a troop's event pages this knows **when they run and what they do
//!   to who fights** —[`TroopPage`]—: whom they bring in or take out and
//!   what they do to their HP. None of the rest draws battle randomness.

use crate::db::{
    self, Db, SCOPE_ALLY, SCOPE_ENEMIES, SCOPE_ENEMY, SCOPE_PARTY, SCOPE_SELF, SKILL_SWITCH,
};
use crate::fail::{Bad, Result};
use crate::rules::{self, floor_div, Action, ACTION_RATING_ALONE, PARAM_MAX};
use ditto::schema::{Item, Skill, TroopPageCondition};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};

/// The seed of the battle's randomness. It means nothing: it only has to
/// be nonzero —the xorshift gets stuck at zero— and the same on both
/// sides.
pub const BATTLE_SEED: i64 = 0x2B1D;

/// The three outcomes, in the order the console's bytecode carries their
/// destinations.
pub const VICTORY: i64 = 0;
pub const ESCAPE: i64 = 1;
pub const DEFEAT: i64 = 2;

/// The commands an actor can be given: attack asks for a target, defend
/// and escape do not. Escaping is a **per-actor** command, resolved the
/// moment it is chosen —see [`Battle::flee`]—; in the turn it does
/// nothing. Item and skill come after, so as not to renumber.
pub const COMMAND_ATTACK: i64 = 0;
pub const COMMAND_DEFEND: i64 = 1;
pub const COMMAND_ESCAPE: i64 = 2;
pub const COMMAND_ITEM: i64 = 3;
pub const COMMAND_SKILL: i64 = 4;

/// The damage's cap: `Game_BattleAlgorithm::MaxDamageValue()` for RM2k.
pub const DAMAGE_MAX: i64 = 999;

/// The hit chance of an actor: `Game_Actor::GetHitChance` with a weapon
/// without its own `hit`. **The weapon's `hit` is not read**: it is
/// declared debt.
const ACTOR_HIT: i64 = 90;

/// `ConditionalBranchB` and `ElseBranchB`, and the commands a troop page
/// runs here: see [`TroopPage::run`].
const BRANCH: i32 = 13310;
const ELSE_BRANCH: i32 = 23310;
const CONTROL_SWITCHES: i32 = 10210;
const CONTROL_VARS: i32 = 10220;
const CHANGE_PARTY_MEMBERS: i32 = 10330;
const CHANGE_EQUIPMENT: i32 = 10450;
const CHANGE_HP: i32 = 10460;
const CHANGE_CONDITION: i32 = 10480;
const FULL_HEAL: i32 = 10490;
const CHANGE_MONSTER_HP: i32 = 13110;
const CHANGE_MONSTER_MP: i32 = 13120;
const SHOW_HIDDEN_MONSTER: i32 = 13150;

/// How many the party holds: `Game_Party::AddActor` does not add a fifth.
const PARTY_MAX: usize = 4;
/// RM2k's death state, `State::kDeathID`.
const DEATH_STATE: i64 = 1;

/// The xorshift step, in sixteen bits.
pub fn next_random(x: i64) -> i64 {
    let mut x = x & 0xFFFF;
    x ^= (x << 7) & 0xFFFF;
    x ^= x >> 9;
    x ^= (x << 8) & 0xFFFF;
    x
}

/// The battle's randomness.
#[derive(Debug, Clone)]
pub struct Rng {
    pub state: i64,
}

impl Rng {
    /// A number from 0 to `n` **inclusive**, which is the range of
    /// easyrpg's `Rand::GetRandomNumber(0, n)`. The remainder is not
    /// uniform and it does not matter: what matters is that the console,
    /// which does the same with its hardware divider, gets the same.
    pub fn up_to(&mut self, n: i64) -> i64 {
        self.state = next_random(self.state);
        if n >= 0 {
            self.state % (n + 1)
        } else {
            0
        }
    }

    /// `Rand::PercentChance`: `GetRandomNumber(0, 99) < percent`. **It is
    /// always rolled**, even at zero: `Normal::vExecute` does so with the
    /// critical, and skipping it would put the two sides out of phase.
    pub fn percent(&mut self, percent: i64) -> bool {
        self.up_to(99) < percent
    }
}

/// `Algo::VarianceAdjustEffect`: `adj = max(1, var * base / 10)`, and
/// `base += rand(0, adj) - adj / 2`. **It only rolls if `var > 0` and
/// `base > 0`**, which is what easyrpg's `if` says.
pub fn apply_variance(base: i64, var: i64, rng: &mut Rng) -> i64 {
    if var > 0 && base > 0 {
        let adjust = (var * base / 10).max(1);
        base + rng.up_to(adjust) - adjust / 2
    } else {
        base
    }
}

/// C++'s division by two, which **truncates toward zero**:
/// `AdjustDamageForDefend` divides a skill's effect, which can be negative,
/// and -25/2 is -12 there.
fn half(n: i64) -> i64 {
    n / 2
}

/// `Game_Battler::CanChangeAtkModifier` and its three siblings: the new
/// modifier is `clamp(mod + delta, -base / 2, base)`, and this returns how
/// much it actually moved.
pub fn modifier_change(modifier: i64, base: i64, delta: i64) -> i64 {
    let new = (modifier + delta).min(base).max(-floor_div(base, 2));
    new - modifier
}

/// `CalcToHitAgiAdjustment`:
/// `to_hit = 100 - (100 - to_hit) * (1 + (tgt_agi / src_agi - 1) / 2)`,
/// which is subtracting from 100 the product by `(src + tgt) / (2 src)`.
/// easyrpg does it in `float` and truncates, and `trunc(100 - x)` is
/// `100 - ceil(x)` while the result is positive: that is why this divides
/// **rounding up**.
pub fn hit_rate_by_agility(base: i64, agi_source: i64, agi_target: i64) -> i64 {
    let source = agi_source.max(1);
    let subtract = (100 - base) * (source + agi_target);
    100 + floor_div(-subtract, 2 * source)
}

/// `Game_BattleAlgorithm::Item::vExecute`: `recover_hp_rate * max / 100 +
/// recover_hp`, capped by `ChangeHp` at what is missing.
pub fn healing(item: &Item, target: &Combatant) -> i64 {
    let hp = floor_div(item.recover_hp_rate as i64 * target.hp_max, 100) + item.recover_hp as i64;
    hp.min(target.hp_max - target.hp).max(0)
}

/// The HP the target of a medicine is left with, and whether it got up:
/// standing and `ko_only`, nothing; standing, the healing; down and it does
/// not revive, nothing —`ApplyHpEffect` does not touch a dead one—; down
/// and it revives, `RemoveStates`' `SetHp(1)` and then the healing minus
/// one, which is `max(1, healing)`.
pub fn item_effect(item: &Item, target: &Combatant) -> (i64, bool) {
    if target.alive() {
        if item.ko_only {
            return (target.hp, false);
        }
        return (target.hp + healing(item, target), false);
    }
    if !rules::revives(item) {
        return (target.hp, false);
    }
    (healing(item, target).max(1), true)
}

/// `Algo::CalcSkillEffect` **without the variance**, which goes apart:
/// the power, plus `physical_rate * atk / 20` and `magical_rate * spi /
/// 40`; against enemies and not ignoring defense, minus `physical_rate *
/// def / 40` and `magical_rate * spi / 80` of the target; never below
/// zero, and times three if critical.
pub fn skill_effect(source: &Combatant, target: &Combatant, skill: &Skill, critical: bool) -> i64 {
    let phys = skill.physical_rate as i64;
    let mag = skill.magical_rate as i64;
    let mut effect = skill.power as i64;
    effect += floor_div(phys * source.attack(), 20);
    effect += floor_div(mag * source.spirit(), 40);
    if db::targets_enemies(skill) && !skill.ignore_defense {
        effect -= floor_div(phys * target.defense(), 40);
        effect -= floor_div(mag * target.spirit(), 80);
    }
    effect = effect.max(0);
    if critical {
        effect *= 3;
    }
    effect
}

/// `CalcNormalAttackEffect` and the variance at 4: `max(0, atk / 2 - def /
/// 4)`, times three if critical. Rows, weapon attributes and the charged
/// attack are not here.
pub fn normal_damage(source: &Combatant, target: &Combatant, critical: bool, rng: &mut Rng) -> i64 {
    let mut damage = (floor_div(source.attack(), 2) - floor_div(target.defense(), 4)).max(0);
    if critical {
        damage *= 3;
    }
    apply_variance(damage, 4, rng)
}

/// One of those who fight, on either side. Whether it is an actor decides
/// which side it counts on when choosing a target.
#[derive(Debug, Clone)]
pub struct Combatant {
    pub name: String,
    /// The database's actor, or the place in the troop.
    pub number: i64,
    pub is_actor: bool,
    pub hp_max: i64,
    pub hp: i64,
    pub sp_max: i64,
    pub sp: i64,
    /// The four **base** parameters: a skill changes the modifier next to
    /// them, and the math uses the sum, clamped (`AdjustParam`).
    pub base: [i64; 4],
    pub modifier: [i64; 4],
    pub hit_rate: i64,
    /// In percent, already an integer.
    pub critical: i64,
    /// An actor's skills, those of its menu.
    pub skills: Vec<i32>,
    /// An enemy's actions: see [`rules::actions_of_enemy`].
    pub actions: Vec<Action>,
    /// What attacking costs it: [`rules::weapon_sp_of`].
    pub weapon_sp: i64,
    /// An actor's equipment —weapon, shield, armor, helmet, accessory— and
    /// its level, None the starting one: what its `base` comes from, for a
    /// `ChangeEquipment` in a troop page. An enemy has neither.
    pub equipment: Vec<i32>,
    pub level: Option<i64>,
    pub defending: bool,
    /// The last turn's `agi + rand`: see [`Battle::execution_order`].
    pub command: i64,
    /// A hidden enemy is there but does not fight: `Exists()` is
    /// `!IsHidden() && !IsDead()`.
    pub hidden: bool,
    pub exp: i64,
    pub gold: i64,
    pub drop_item: i64,
    pub drop_chance: i64,
}

impl Combatant {
    /// `Exists()`: it has HP left and is not hidden. An actor a troop page
    /// took out of the party is hidden too: see [`Battle::leave`].
    pub fn alive(&self) -> bool {
        self.hp > 0 && !self.hidden
    }

    /// `Game_Battler::ChangeHp`: a dead one does not change, it does not go
    /// past the maximum, and a loss that is not lethal leaves it at 1.
    pub fn change_hp(&mut self, amount: i64, lethal: bool) {
        if self.hp == 0 {
            return;
        }
        let mut hp = self.hp + amount;
        if !lethal {
            hp = hp.max(1);
        }
        self.hp = hp.clamp(0, self.hp_max);
    }

    fn param(&self, k: usize) -> i64 {
        (self.base[k] + self.modifier[k]).clamp(1, PARAM_MAX)
    }

    pub fn attack(&self) -> i64 {
        self.param(0)
    }

    pub fn defense(&self) -> i64 {
        self.param(1)
    }

    pub fn spirit(&self) -> i64 {
        self.param(2)
    }

    pub fn agility(&self) -> i64 {
        self.param(3)
    }

    /// An actor of the database with what it has equipped, at `level` or
    /// its starting one. The parameters are the level's plus the
    /// equipment's, clamped; the HP are the level's and carry no equipment,
    /// as in RM2k.
    ///
    /// **An actor has no critical hit here**, whatever its `critical_hit`
    /// says: the model this replaced never read the field, and the console
    /// carries none for actors. It is kept so; see the task that moved this.
    pub fn actor(
        db: &Db,
        number: i32,
        equipment: Option<&[i32]>,
        level: Option<i64>,
    ) -> Result<Combatant> {
        let actor = db.actor(number)?;
        let equipment = match equipment {
            Some(e) => e.to_vec(),
            None => rules::initial_equipment(actor),
        };
        let base = rules::equipped_params(db, number, &equipment, level)?;
        let hp_max = rules::param_of(actor, "maxhp", level)?;
        let sp_max = rules::param_of(actor, "maxsp", level)?;
        Ok(Combatant {
            name: actor.name.clone(),
            number: number as i64,
            is_actor: true,
            hp_max,
            hp: hp_max,
            sp_max,
            sp: sp_max,
            base,
            modifier: [0; 4],
            hit_rate: ACTOR_HIT,
            critical: 0,
            skills: rules::skills_of(db, number, level)?,
            actions: vec![Action {
                rating: ACTION_RATING_ALONE,
                skill: None,
                effective: true,
            }],
            weapon_sp: rules::weapon_sp_of(db, &equipment)?,
            equipment,
            level,
            defending: false,
            command: 0,
            hidden: false,
            exp: 0,
            gold: 0,
            drop_item: 0,
            drop_chance: 0,
        })
    }

    /// An enemy of the database at `place` of its troop; `hidden` is the
    /// troop's `invisible`. The hit chance is `Game_Enemy::GetHitChance`,
    /// 70 with `miss` and 90 otherwise; the critical,
    /// `GetCriticalHitChance` times a hundred, truncated.
    pub fn enemy(db: &Db, id: i32, place: i64, hidden: bool) -> Result<Combatant> {
        let e = db.enemy(id)?;
        let every = if e.critical_hit_chance != 0 {
            e.critical_hit_chance as i64
        } else {
            30
        };
        Ok(Combatant {
            name: e.name.clone(),
            number: place,
            is_actor: false,
            hp_max: e.max_hp as i64,
            hp: e.max_hp as i64,
            sp_max: e.max_sp as i64,
            sp: e.max_sp as i64,
            base: [
                e.attack as i64,
                e.defense as i64,
                e.spirit as i64,
                e.agility as i64,
            ],
            modifier: [0; 4],
            hit_rate: if e.miss { 70 } else { 90 },
            critical: if e.critical_hit {
                floor_div(100, every)
            } else {
                0
            },
            skills: Vec::new(),
            actions: rules::actions_of_enemy(db, id)?,
            weapon_sp: 0,
            equipment: Vec::new(),
            level: None,
            defending: false,
            command: 0,
            hidden,
            exp: e.exp as i64,
            gold: e.gold as i64,
            drop_item: e.drop_id as i64,
            drop_chance: e.drop_prob as i64,
        })
    }

    pub fn to_json(&self) -> Value {
        json!({
            "name": self.name,
            "number": self.number,
            "is_actor": self.is_actor,
            "hp": self.hp,
            "hp_max": self.hp_max,
            "sp": self.sp,
            "sp_max": self.sp_max,
            "attack": self.attack(),
            "defense": self.defense(),
            "spirit": self.spirit(),
            "agility": self.agility(),
            "base_attack": self.base[0],
            "base_defense": self.base[1],
            "base_spirit": self.base[2],
            "base_agility": self.base[3],
            "mod_attack": self.modifier[0],
            "mod_defense": self.modifier[1],
            "mod_spirit": self.modifier[2],
            "mod_agility": self.modifier[3],
            "hit_rate": self.hit_rate,
            "critical": self.critical,
            "skills": self.skills,
            "actions": self.actions.iter().map(action_json).collect::<Vec<_>>(),
            "weapon_sp": self.weapon_sp,
            "defending": self.defending,
            "command": self.command,
            "hidden": self.hidden,
            "alive": self.alive(),
            "exp": self.exp,
            "gold": self.gold,
            "drop_item": self.drop_item,
            "drop_chance": self.drop_chance,
        })
    }
}

/// An action as the answers write it: `[rating, skill or null,
/// effective]`.
pub fn action_json(a: &Action) -> Value {
    json!([a.rating, a.skill, a.effective])
}

/// `Game_Battle::CheckTurns(turn, base, multiple)`.
pub fn check_turns(turn: i64, base: i64, multiple: i64) -> bool {
    if multiple == 0 {
        return turn == base;
    }
    turn >= base && (turn - base).rem_euclid(multiple) == 0
}

/// The comparison of a `ConditionalBranch` on a variable: `==`, `>=`,
/// `<=`, `>`, `<` and `!=`, in RM2k's order.
fn compare(a: i64, op: i64, b: i64) -> Result<bool> {
    Ok(match op {
        0 => a == b,
        1 => a >= b,
        2 => a <= b,
        3 => a > b,
        4 => a < b,
        5 => a != b,
        _ => return Err(Bad::answer(format!("there is no comparison {op}"))),
    })
}

/// Which side, and which place on it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Who {
    Actor(usize),
    Enemy(usize),
}

/// What an action goes against.
#[derive(Debug, Clone, Copy)]
enum Target {
    None,
    One(Who),
    Item(i32, Who),
    Skill(i32, Who),
}

/// A command as the caller gives it, one per living actor in party order:
/// `(COMMAND_ATTACK, enemy's place)`, `(COMMAND_DEFEND, 0)`,
/// `(COMMAND_ITEM, item, actor's place)`, `(COMMAND_SKILL, skill, place on
/// the side its scope points to)`.
#[derive(Debug, Clone, Copy)]
pub struct Command {
    pub command: i64,
    pub what: i64,
    pub target: i64,
}

/// A troop's event page, **with what the battle needs**: when it is met
/// —`AreConditionsMet`— and what it does to who fights. Of its commands it
/// runs `ShowHiddenMonster`, `ChangePartyMembers`, `ChangeHP`, `FullHeal`,
/// the `ChangeCondition` that revives, `ChangeMonsterHP` and
/// `ChangeMonsterMP`; and, to know which of those run, the single
/// `ControlSwitches`, the `ControlVars` the console does in battle and the
/// battle's branches on a switch or a variable. The rest does not change
/// who fights nor draws battle randomness.
#[derive(Debug, Clone)]
pub struct TroopPage {
    pub condition: TroopPageCondition,
    /// `(code, indent, parameters)`.
    pub commands: Vec<(i32, i32, Vec<i32>)>,
}

fn parameter(p: &[i32], k: usize) -> Result<i64> {
    p.get(k)
        .map(|&v| v as i64)
        .ok_or_else(|| Bad::answer(format!("a troop page's command has no parameter {k}")))
}

impl TroopPage {
    pub fn of(page: &ditto::schema::TroopPage) -> TroopPage {
        TroopPage {
            condition: page.condition.clone(),
            commands: page
                .event_commands
                .iter()
                .map(|c| (c.code.to_i32(), c.indent, c.parameters.clone()))
                .collect(),
        }
    }

    fn met(&self, battle: &Battle) -> Result<bool> {
        let c = &self.condition;
        let f = &c.flags;
        if !(f.switch_a
            || f.switch_b
            || f.variable
            || f.turn
            || f.fatigue
            || f.enemy_hp
            || f.actor_hp)
        {
            return Ok(false);
        }
        if f.switch_a && !battle.switch(c.switch_a_id as i64) {
            return Ok(false);
        }
        if f.switch_b && !battle.switch(c.switch_b_id as i64) {
            return Ok(false);
        }
        if f.variable {
            return Err(Bad::answer(
                "a troop page on a variable: the battle has no variables",
            ));
        }
        if f.turn && !check_turns(battle.turn, c.turn_b as i64, c.turn_a as i64) {
            return Ok(false);
        }
        let percent = |who: &Combatant| -> Result<i64> {
            if who.hp_max == 0 {
                return Err(Bad::answer(format!(
                    "{:?} has no HP to take a percentage of",
                    who.name
                )));
            }
            Ok(floor_div(100 * who.hp, who.hp_max))
        };
        if f.enemy_hp {
            let Some(e) = usize::try_from(c.enemy_id)
                .ok()
                .and_then(|k| battle.enemies.get(k))
            else {
                return Ok(false);
            };
            let p = percent(e)?;
            if !(c.enemy_hp_min as i64 <= p && p <= c.enemy_hp_max as i64) {
                return Ok(false);
            }
        }
        if f.actor_hp {
            // Only if it is in the party, like the console.
            let Some(a) = battle
                .actors
                .iter()
                .find(|a| a.number == c.actor_id as i64 && !a.hidden)
            else {
                return Ok(false);
            };
            let p = percent(a)?;
            if !(c.actor_hp_min as i64 <= p && p <= c.actor_hp_max as i64) {
                return Ok(false);
            }
        }
        Ok(true)
    }

    /// The commands, with the branches resolved: a branch not taken skips
    /// everything nested deeper than it, and its `else` is where it ends.
    fn run(&self, db: &Db, battle: &mut Battle) -> Result<()> {
        let mut skip_from: Option<i32> = None;
        for (code, indent, p) in &self.commands {
            let (code, indent) = (*code, *indent);
            if let Some(from) = skip_from {
                if indent > from {
                    continue;
                }
                skip_from = None;
                if code == ELSE_BRANCH && indent == from {
                    continue;
                }
            }
            match code {
                BRANCH => {
                    let taken = match parameter(p, 0)? {
                        0 => battle.switch(parameter(p, 1)?) == (parameter(p, 2)? == 0),
                        1 => {
                            let value = battle.variable(parameter(p, 1)?)?;
                            let other = match parameter(p, 2)? {
                                0 => parameter(p, 3)?,
                                _ => battle.variable(parameter(p, 3)?)?,
                            };
                            compare(value, parameter(p, 4)?, other)?
                        }
                        _ => {
                            return Err(Bad::answer(
                                "a battle branch that is not on a switch or a variable",
                            ))
                        }
                    };
                    if !taken {
                        skip_from = Some(indent);
                    }
                }
                // The `else` of a branch that was taken is skipped.
                ELSE_BRANCH => skip_from = Some(indent),
                CONTROL_SWITCHES => {
                    let (mode, first, last, op) = (
                        parameter(p, 0)?,
                        parameter(p, 1)?,
                        parameter(p, 2)?,
                        parameter(p, 3)?,
                    );
                    if mode != 0 || first != last || !(op == 0 || op == 1) {
                        return Err(Bad::answer("a ControlSwitches the battle does not know"));
                    }
                    battle.state.insert(first, op == 0);
                    battle.lit_by_skills.remove(&first);
                }
                CONTROL_VARS => battle.control_vars(p)?,
                SHOW_HIDDEN_MONSTER => {
                    let k = parameter(p, 0)?;
                    if let Some(e) = usize::try_from(k)
                        .ok()
                        .and_then(|k| battle.enemies.get_mut(k))
                    {
                        e.hidden = false;
                    }
                }
                CHANGE_PARTY_MEMBERS => {
                    if parameter(p, 1)? != 0 {
                        return Err(Bad::answer("a ChangePartyMembers by variable"));
                    }
                    let actor = parameter(p, 2)?;
                    if parameter(p, 0)? == 0 {
                        battle.join(db, actor)?;
                    } else {
                        battle.leave(actor);
                    }
                }
                CHANGE_EQUIPMENT => battle.change_equipment(db, p)?,
                CHANGE_HP => {
                    if parameter(p, 3)? != 0 {
                        return Err(Bad::answer("a ChangeHP by variable"));
                    }
                    let mut amount = parameter(p, 4)?;
                    if parameter(p, 2)? != 0 {
                        amount = -amount;
                    }
                    let lethal = parameter(p, 5)? != 0;
                    for k in battle.targets(p)? {
                        battle.actors[k].change_hp(amount, lethal);
                    }
                }
                FULL_HEAL => {
                    for k in battle.targets(p)? {
                        let a = &mut battle.actors[k];
                        a.hp = a.hp_max;
                        a.sp = a.sp_max;
                    }
                }
                CHANGE_CONDITION => {
                    // Only removing death does anything here: the battle has
                    // no other states, and adding one does not compile.
                    if parameter(p, 2)? == 1 && parameter(p, 3)? == DEATH_STATE {
                        for k in battle.targets(p)? {
                            let a = &mut battle.actors[k];
                            if a.hp == 0 {
                                a.hp = 1;
                            }
                        }
                    }
                }
                CHANGE_MONSTER_HP | CHANGE_MONSTER_MP => {
                    if parameter(p, 2)? != 0 {
                        return Err(Bad::answer("a ChangeMonsterHP or MP not by a constant"));
                    }
                    let mut amount = parameter(p, 3)?;
                    if parameter(p, 1)? != 0 {
                        amount = -amount;
                    }
                    let k = parameter(p, 0)?;
                    let hp = code == CHANGE_MONSTER_HP;
                    let lethal = hp && parameter(p, 4)? != 0;
                    if let Some(e) = usize::try_from(k)
                        .ok()
                        .and_then(|k| battle.enemies.get_mut(k))
                    {
                        if hp {
                            e.change_hp(amount, lethal);
                        } else {
                            e.sp = (e.sp + amount).clamp(0, e.sp_max);
                        }
                    }
                }
                _ => {}
            }
        }
        Ok(())
    }
}

/// What happened in an action, for whoever counts: the turn, who, against
/// whom, whether it hit, whether it was critical, the damage and the HP it
/// left.
#[derive(Debug, Clone)]
pub struct Logged {
    pub turn: i64,
    pub source: String,
    pub target: String,
    pub hit: bool,
    pub critical: bool,
    pub damage: i64,
    pub hp: i64,
}

/// A battle, turn by turn: easyrpg's `Scene_Battle_Rpg2k` with what this
/// battle does.
///
/// The loop of a turn, in the order it consumes randomness —and that order
/// is the contract with the console—:
///
/// 1. the player chooses each living actor's command (no roll);
/// 2. each living enemy chooses what to do and against whom
///    —`CreateEnemyActions`, see [`Battle::enemy_action`]—: one roll for
///    the action if it has more than one possible, and one for the target
///    if the action asks for one;
/// 3. `CreateExecutionOrder`: one roll per combatant that acts, for its
///    `agi + rand(0, agi / 4 + 3)`, sorted from highest to lowest, stable;
/// 4. they run in that order, skipping those that died along the way. An
///    attack rolls three times —hit, critical and variance—, the critical
///    even at zero;
/// 5. on winning, one roll per enemy with an item, in troop order.
///
/// Step 2 before step 3 is `SelectNextActor`'s order.
#[derive(Debug, Clone)]
pub struct Battle {
    pub actors: Vec<Combatant>,
    pub enemies: Vec<Combatant>,
    pub rng: Rng,
    pub turn: i64,
    pub pages: Vec<TroopPage>,
    /// The pages that already ran this turn: `executed`.
    pub done_pages: BTreeSet<usize>,
    /// The switches the pages look at, from the ones given.
    pub state: BTreeMap<i64, bool>,
    /// The variables the pages look at: the ones given and the ones a page
    /// set. **One that is in neither is not known**, and a branch that looks
    /// at it is an error: the console has it from the game, and making up a
    /// zero would compare against something else.
    pub variables: BTreeMap<i64, i64>,
    /// The HP and SP of those a page took out of the party, by actor
    /// number: they are the `FAR_HP` of the console, which keeps them.
    pub outside: BTreeMap<i64, (i64, i64)>,
    /// The switches a `switch` skill turned on and no page turned off since.
    /// They go apart from `state` so that the answer's `state` stays what
    /// was given and what the pages wrote, which is what it said before
    /// skills turned them on here —the hashes in `tests/model.rs`—.
    pub lit_by_skills: BTreeSet<i64>,
    /// The places a page put someone in during this turn: whatever action
    /// was pending there belonged to whoever left it, and is lost. See
    /// [`Battle::join`].
    pub joined: BTreeSet<usize>,
    pub result: Option<i64>,
    pub escape_chance: i64,
    pub log: Vec<Logged>,
    /// The switches a `switch` skill turned on, in order.
    pub switches: Vec<i64>,
    /// The items the enemies dropped on losing.
    pub drops: Vec<i64>,
}

fn average_agility(whom: &[Combatant]) -> i64 {
    let alive: Vec<&Combatant> = whom.iter().filter(|c| c.alive()).collect();
    let counted: Vec<&Combatant> = if alive.is_empty() {
        whom.iter().collect()
    } else {
        alive
    };
    let sum: i64 = counted.iter().map(|c| c.agility()).sum();
    floor_div(sum, (counted.len() as i64).max(1))
}

impl Battle {
    pub fn new(
        actors: Vec<Combatant>,
        enemies: Vec<Combatant>,
        seed: i64,
        pages: Vec<TroopPage>,
        switches: BTreeMap<i64, bool>,
    ) -> Battle {
        let mut battle = Battle {
            actors,
            enemies,
            rng: Rng { state: seed },
            turn: 0,
            pages,
            done_pages: BTreeSet::new(),
            state: switches,
            variables: BTreeMap::new(),
            outside: BTreeMap::new(),
            lit_by_skills: BTreeSet::new(),
            joined: BTreeSet::new(),
            result: None,
            escape_chance: 0,
            log: Vec::new(),
            switches: Vec::new(),
            drops: Vec::new(),
        };
        battle.escape_chance = battle.initial_escape_chance();
        battle
    }

    /// `Scene_Battle::InitEscapeChance`: `base = round(100 * enemies_agi /
    /// party_agi)` and `chance = clamp(150 - base, 0, 100)`. easyrpg rounds
    /// to the nearest; with integers that is `(2a + b) / (2b)`.
    fn initial_escape_chance(&self) -> i64 {
        let enemies = average_agility(&self.enemies);
        let party = average_agility(&self.actors).max(1);
        let base = floor_div(2 * 100 * enemies + party, 2 * party);
        (150 - base).clamp(0, 100)
    }

    fn switch(&self, id: i64) -> bool {
        self.lit_by_skills.contains(&id) || self.state.get(&id).copied().unwrap_or(false)
    }

    fn variable(&self, id: i64) -> Result<i64> {
        self.variables.get(&id).copied().ok_or_else(|| {
            Bad::answer(format!(
                "a troop page looks at variable {id}, which this battle does not know"
            ))
        })
    }

    /// `ControlVars` on one variable, with what the console does in battle:
    /// set, add or subtract a constant, another variable or an actor's HP,
    /// SP or their maximums. Any other is not known and the variable stops
    /// being known: see `variables`.
    fn control_vars(&mut self, p: &[i32]) -> Result<()> {
        let (mode, first, last, op, kind, a, b) = (
            parameter(p, 0)?,
            parameter(p, 1)?,
            parameter(p, 2)?,
            parameter(p, 3)?,
            parameter(p, 4)?,
            parameter(p, 5)?,
            parameter(p, 6)?,
        );
        let value = match kind {
            _ if mode != 0 || first != last || op > 2 => None,
            0 => Some(a),
            1 => self.variables.get(&a).copied(),
            5 => self.actor_stat(a, b),
            _ => None,
        };
        let now = match (value, op) {
            (Some(v), 0) => Some(v),
            (Some(v), 1) => self.variables.get(&first).map(|x| x + v),
            (Some(v), 2) => self.variables.get(&first).map(|x| x - v),
            _ => None,
        };
        match now {
            Some(v) => {
                self.variables.insert(first, v);
            }
            None => {
                for id in first..=last {
                    self.variables.remove(&id);
                }
            }
        }
        Ok(())
    }

    /// `ControlVariables::Actor` for the four the console does: 2 the HP, 3
    /// the SP, 4 and 5 their maximums. Of one who is not fighting only what
    /// a page left in `outside` is known.
    fn actor_stat(&self, actor: i64, which: i64) -> Option<i64> {
        if let Some(a) = self
            .actors
            .iter()
            .find(|a| a.number == actor && !a.hidden)
        {
            return match which {
                2 => Some(a.hp),
                3 => Some(a.sp),
                4 => Some(a.hp_max),
                5 => Some(a.sp_max),
                _ => None,
            };
        }
        match which {
            2 => self.outside.get(&actor).map(|x| x.0),
            3 => self.outside.get(&actor).map(|x| x.1),
            _ => None,
        }
    }

    /// The places of the actors a command's `[type, id]` names, among those
    /// fighting: 0 the whole party, 1 one actor. One who is not fighting is
    /// left out; the console changes its `FAR_HP`, which the model only
    /// follows in `outside` for whom a page took out.
    fn targets(&self, p: &[i32]) -> Result<Vec<usize>> {
        let (kind, id) = (parameter(p, 0)?, parameter(p, 1)?);
        Ok((0..self.actors.len())
            .filter(|&k| !self.actors[k].hidden)
            .filter(|&k| kind == 0 || (kind == 1 && self.actors[k].number == id))
            .collect())
    }

    /// `ChangeEquipment` on one who is fighting, in the two forms the console
    /// does: unequipping a slot, and equipping armor, a helmet or an
    /// accessory the actor can use —`IsItemUsable`—. Its base parameters
    /// come from its equipment again and the modifiers stay, which is what
    /// `ba_reparam` does. The inventory is not followed.
    fn change_equipment(&mut self, db: &Db, p: &[i32]) -> Result<()> {
        let (kind, id, op, a, b) = (
            parameter(p, 0)?,
            parameter(p, 1)?,
            parameter(p, 2)?,
            parameter(p, 3)?,
            parameter(p, 4)?,
        );
        let (slot, item) = match op {
            0 if kind == 1 && a == 0 => {
                let it = db.item(b as i32)?;
                let usable = it
                    .actor_set
                    .get(id as usize - 1)
                    .copied()
                    .unwrap_or(false);
                let t = it.r#type.to_i32() as i64;
                if !(3..=5).contains(&t) {
                    return Err(Bad::answer("equipping a weapon or a shield from a troop page"));
                }
                if !usable {
                    return Ok(());
                }
                (t - 1, b as i32)
            }
            1 if (0..5).contains(&a) => (a, 0),
            _ => return Err(Bad::answer("a ChangeEquipment the battle does not know")),
        };
        let targets: Vec<usize> = (0..self.actors.len())
            .filter(|&k| !self.actors[k].hidden)
            .filter(|&k| kind == 0 || self.actors[k].number == id)
            .collect();
        for k in targets {
            let a = &mut self.actors[k];
            if a.equipment.len() < 5 {
                continue;
            }
            a.equipment[slot as usize] = item;
            a.base = rules::equipped_params(db, a.number as i32, &a.equipment, a.level)?;
            a.weapon_sp = rules::weapon_sp_of(db, &a.equipment)?;
        }
        Ok(())
    }

    /// `Game_Party::RemoveActor` in battle: the actor stops existing, and
    /// keeps its place, which the console does not move —see `ba_sync_in` in
    /// its `battle_troop.s`—. Its HP and SP stay in `outside`.
    fn leave(&mut self, actor: i64) {
        if let Some(a) = self
            .actors
            .iter_mut()
            .find(|a| a.number == actor && !a.hidden)
        {
            a.hidden = true;
            self.outside.insert(actor, (a.hp, a.sp));
        }
    }

    /// `Game_Party::AddActor` in battle: nothing if it is already fighting
    /// or the party is full; otherwise into the first place without anyone,
    /// which is where the console puts it, with the HP and SP it had —those
    /// of `outside`, or full—, its starting level and equipment, and no
    /// action this turn.
    fn join(&mut self, db: &Db, actor: i64) -> Result<()> {
        let present = self.actors.iter().filter(|a| !a.hidden).count();
        if present >= PARTY_MAX || self.actors.iter().any(|a| a.number == actor && !a.hidden) {
            return Ok(());
        }
        let mut who = Combatant::actor(db, actor as i32, None, None)?;
        if let Some(&(hp, sp)) = self.outside.get(&actor) {
            who.hp = hp;
            who.sp = sp;
        }
        self.outside.remove(&actor);
        let k = match self.actors.iter().position(|a| a.hidden) {
            Some(k) => {
                self.actors[k] = who;
                k
            }
            None => {
                self.actors.push(who);
                self.actors.len() - 1
            }
        };
        self.joined.insert(k);
        Ok(())
    }

    pub fn get(&self, who: Who) -> &Combatant {
        match who {
            Who::Actor(k) => &self.actors[k],
            Who::Enemy(k) => &self.enemies[k],
        }
    }

    fn get_mut(&mut self, who: Who) -> &mut Combatant {
        match who {
            Who::Actor(k) => &mut self.actors[k],
            Who::Enemy(k) => &mut self.enemies[k],
        }
    }

    /// The living ones of a side, in order.
    pub fn living(&self, actors: bool) -> Vec<Who> {
        if actors {
            (0..self.actors.len())
                .filter(|&k| self.actors[k].alive())
                .map(Who::Actor)
                .collect()
        } else {
            (0..self.enemies.len())
                .filter(|&k| self.enemies[k].alive())
                .map(Who::Enemy)
                .collect()
        }
    }

    /// `TryEscape`: a roll against the chance, and if it fails the chance
    /// goes up ten. `first_strike` is not here.
    pub fn flee(&mut self) -> bool {
        if self.rng.percent(self.escape_chance) {
            self.result = Some(ESCAPE);
            return true;
        }
        self.escape_chance = (self.escape_chance + 10).min(100);
        false
    }

    /// `CheckBattleEndAndScheduleEvents` until none is left: with a whole
    /// side out nothing runs; otherwise, the first page that is met and has
    /// not run this turn, and then again from the first.
    pub fn check_pages(&mut self, db: &Db) -> Result<()> {
        while !self.living(false).is_empty() && !self.living(true).is_empty() {
            let mut ran = false;
            for i in 0..self.pages.len() {
                if !self.done_pages.contains(&i) && self.pages[i].met(self)? {
                    self.done_pages.insert(i);
                    let page = self.pages[i].clone();
                    page.run(db, self)?;
                    ran = true;
                    break;
                }
            }
            if !ran {
                return Ok(());
            }
        }
        Ok(())
    }

    /// Before the first commands, on turn 0: the `eCheckEvents` of
    /// `ProcessSceneActionFightAutoEscape`.
    pub fn start(&mut self, db: &Db) -> Result<()> {
        self.check_pages(db)
    }

    /// What this enemy does: `SelectEnemyAiActionRpgRtCompat` over its
    /// list. The possible ones are the attack and the skills it has SP
    /// for; each weighs `max(0, rating - maximum + 10)` —**ten points below
    /// the best, an action never comes up**—, and one that is not
    /// effective weighs zero after the maximum was taken counting it. Then
    /// `rand(0, sum - 1)` chooses by weight. **With a single action of
    /// weight there is no roll**: it is the same distribution, and it leaves
    /// the battles of enemies that only attack as they were.
    pub fn enemy_action(&mut self, db: &Db, enemy: usize) -> Result<Option<Action>> {
        let e = &self.enemies[enemy];
        let mut possible = Vec::new();
        for a in &e.actions {
            let ok = match a.skill {
                None => true,
                Some(s) => e.sp >= db.skill(s)?.sp_cost as i64,
            };
            if ok {
                possible.push(*a);
            }
        }
        let Some(top) = possible.iter().map(|a| a.rating).max() else {
            return Ok(None);
        };
        let weights: Vec<(i64, Action)> = possible
            .into_iter()
            .map(|a| {
                (
                    if a.effective {
                        (a.rating - top + 10).max(0)
                    } else {
                        0
                    },
                    a,
                )
            })
            .filter(|(w, _)| *w > 0)
            .collect();
        match weights.len() {
            0 => return Ok(None),
            1 => return Ok(Some(weights[0].1)),
            _ => {}
        }
        let mut which = self
            .rng
            .up_to(weights.iter().map(|(w, _)| w).sum::<i64>() - 1);
        for (weight, action) in &weights {
            which -= weight;
            if which < 0 {
                return Ok(Some(*action));
            }
        }
        unreachable!("the roll is less than the sum of the weights")
    }

    /// `CreateEnemyActions`: each living enemy chooses its action and then
    /// its target —the order of `MakeAttack` and `MakeSkillAction`—: an
    /// attack or an `enemy` skill, a living actor, one roll; an `ally`
    /// skill, a living enemy, one roll; `self`, `enemies` and `party`, no
    /// roll. With no living actor left it stops, and the rest are left
    /// without an action.
    fn enemy_actions(&mut self, db: &Db) -> Result<Vec<(Who, i64, Target)>> {
        let mut out = Vec::new();
        for enemy in self.living(false) {
            let targets = self.living(true);
            if targets.is_empty() {
                break;
            }
            let Who::Enemy(k) = enemy else { unreachable!() };
            let Some(action) = self.enemy_action(db, k)? else {
                continue;
            };
            let Some(skill) = action.skill else {
                let target = targets[self.rng.up_to(targets.len() as i64 - 1) as usize];
                out.push((enemy, COMMAND_ATTACK, Target::One(target)));
                continue;
            };
            let target = match db.skill(skill)?.scope.to_i32() {
                SCOPE_ENEMY => targets[self.rng.up_to(targets.len() as i64 - 1) as usize],
                SCOPE_ALLY => {
                    // Among the ones the skill affects, which are all the
                    // living: a not effective one weighed zero.
                    let matching = self.living(false);
                    matching[self.rng.up_to(matching.len() as i64 - 1) as usize]
                }
                _ => enemy,
            };
            out.push((enemy, COMMAND_SKILL, Target::Skill(skill, target)));
        }
        Ok(out)
    }

    /// `CreateExecutionOrder`: `agi + rand(0, agi / 4 + 3)`, from highest
    /// to lowest, **stable**, which is what `std::sort` does on a list that
    /// already comes in the order it was stacked.
    fn execution_order(&mut self, actions: &[(Who, i64, Target)]) -> Vec<usize> {
        for (who, _, _) in actions {
            let agility = self.get(*who).agility();
            let roll = self.rng.up_to(floor_div(agility, 4) + 3);
            self.get_mut(*who).command = agility + roll;
        }
        let mut order: Vec<usize> = (0..actions.len()).collect();
        order.sort_by_key(|&i| -self.get(actions[i].0).command);
        order
    }

    fn logged(&mut self, source: Who, target: Who, hit: bool, critical: bool, damage: i64) {
        let entry = Logged {
            turn: self.turn,
            source: self.get(source).name.clone(),
            target: self.get(target).name.clone(),
            hit,
            critical,
            damage,
            hp: self.get(target).hp,
        };
        self.log.push(entry);
    }

    /// A normal attack, with its three rolls: `(hit, critical, damage)`.
    /// Before anything, and without rolling, it charges the weapon's SP
    /// —`Normal::vStart`—, even if it misses and even with none left: RM2k
    /// does not gray out Attack.
    pub fn attack(&mut self, source: Who, target: Who) -> (bool, bool, i64) {
        let s = self.get_mut(source);
        s.sp = (s.sp - s.weapon_sp).max(0);
        let (s, t) = (self.get(source).clone(), self.get(target).clone());
        let hit_rate = hit_rate_by_agility(s.hit_rate, s.agility(), t.agility());
        let hit = self.rng.percent(hit_rate);
        let critical = self.rng.percent(if hit { s.critical } else { 0 });
        if !hit {
            return (false, false, 0);
        }
        let mut damage = normal_damage(&s, &t, critical, &mut self.rng);
        if t.defending {
            damage = half(damage);
        }
        damage = damage.clamp(-DAMAGE_MAX, DAMAGE_MAX);
        let t = self.get_mut(target);
        t.hp = (t.hp - damage).max(0);
        (true, critical, damage)
    }

    /// `Game_BattleAlgorithm::Skill`. The order it consumes randomness in
    /// comes from `vExecute` read top to bottom: the cost first, rolling
    /// nothing —`vStart`—; a `switch` skill turns its switch on and ends
    /// there; then, **once per target**, the critical —always rolled, and
    /// always at zero for a skill of the database—, the variance if the
    /// effect is above zero, and one roll against the hit chance for each
    /// thing it affects, in the order HP, SP, attack, defense, spirit,
    /// agility. States, attributes, absorbing and reviving are not here.
    pub fn use_skill(&mut self, db: &Db, source: Who, skill: i32, target: Who) -> Result<()> {
        let s = db.skill(skill)?;
        let src = self.get_mut(source);
        src.sp = (src.sp - s.sp_cost as i64).max(0);
        if s.r#type.to_i32() == SKILL_SWITCH {
            // Turned on for the troop's pages too, which look at it before
            // the next action: it is how a character's system starts.
            self.switches.push(s.switch_id as i64);
            self.lit_by_skills.insert(s.switch_id as i64);
            self.logged(source, source, true, false, 0);
            return Ok(());
        }
        for one in self.skill_targets(source, s, target) {
            self.skill_on(source, s, one);
        }
        Ok(())
    }

    /// Whom it falls on, in the order `vExecute` walks them: `enemy` and
    /// `ally` on the one chosen, `self` on the one using it, `enemies` and
    /// `party` on each living one of the other side or its own, in screen
    /// order.
    fn skill_targets(&self, source: Who, skill: &Skill, target: Who) -> Vec<Who> {
        let is_actor = self.get(source).is_actor;
        match skill.scope.to_i32() {
            SCOPE_SELF => vec![source],
            SCOPE_ENEMIES => self.living(!is_actor),
            SCOPE_PARTY => self.living(is_actor),
            _ => vec![target],
        }
    }

    fn skill_on(&mut self, source: Who, skill: &Skill, target: Who) {
        // `CalcSkillToHit`: the skill's `hit`.
        let hit_rate = skill.hit as i64;
        let critical = self.rng.percent(0);
        let (s, t) = (self.get(source).clone(), self.get(target).clone());
        let mut effect = skill_effect(&s, &t, skill, critical);
        effect = apply_variance(effect, skill.variance as i64, &mut self.rng);
        effect = effect.clamp(-DAMAGE_MAX, DAMAGE_MAX);
        let positive = !db::targets_enemies(skill);
        if !positive {
            effect = -effect;
        }
        if skill.affect_hp && self.rng.percent(hit_rate) {
            let t = self.get_mut(target);
            let hp = if positive {
                // A heal does not kill: `max(-(cur_hp - 1), hp_effect)`.
                effect.max(-(t.hp - 1))
            } else if t.defending {
                half(effect)
            } else {
                effect
            };
            t.hp = (t.hp + hp).min(t.hp_max).max(0);
        }
        if skill.affect_sp && self.rng.percent(hit_rate) {
            let t = self.get_mut(target);
            t.sp = (t.sp + effect).min(t.sp_max).max(0);
        }
        let affects = [
            skill.affect_attack,
            skill.affect_defense,
            skill.affect_spirit,
            skill.affect_agility,
        ];
        for (k, affected) in affects.into_iter().enumerate() {
            if !affected || !self.rng.percent(hit_rate) {
                continue;
            }
            let t = self.get_mut(target);
            t.modifier[k] += modifier_change(t.modifier[k], t.base[k], effect);
        }
        self.logged(source, target, true, critical, -effect);
    }

    /// `Game_EnemyParty::GetExp` on winning: that of the dead, which are all
    /// but those that stayed hidden.
    pub fn experience(&self) -> i64 {
        self.enemies
            .iter()
            .filter(|e| !e.hidden)
            .map(|e| e.exp)
            .sum()
    }

    /// `GetMoney`, the same.
    pub fn gold(&self) -> i64 {
        self.enemies
            .iter()
            .filter(|e| !e.hidden)
            .map(|e| e.gold)
            .sum()
    }

    /// `Game_EnemyParty::GenerateDrops`: for each enemy, in troop order,
    /// **one roll if it has an item** —`ChanceOf(drop_prob, 100)`, which is
    /// the same as `percent`— and none if not; the one at 100 is rolled
    /// anyway. The items won, one per enemy that dropped its own.
    fn roll_drops(&mut self) -> Vec<i64> {
        let mut earned = Vec::new();
        for k in 0..self.enemies.len() {
            let (hidden, item, chance) = {
                let e = &self.enemies[k];
                (e.hidden, e.drop_item, e.drop_chance)
            };
            if hidden {
                continue;
            }
            if item > 0 && self.rng.percent(chance) {
                earned.push(item);
            }
        }
        earned
    }

    /// A whole turn, with a command per living actor in party order. The
    /// outcome if the battle ended.
    ///
    /// The troop's pages run **before each action and after the last**
    /// —`ePreAction`—, and the ones recorded are cleared at the start,
    /// which is `NextTurn`.
    pub fn play_turn(&mut self, db: &Db, commands: &[Command]) -> Result<Option<i64>> {
        self.turn += 1;
        self.done_pages.clear();
        self.joined.clear();
        for c in self.actors.iter_mut().chain(self.enemies.iter_mut()) {
            c.defending = false;
        }
        let place = |list: &[Combatant], k: i64, side: &str| -> Result<usize> {
            usize::try_from(k)
                .ok()
                .filter(|&k| k < list.len())
                .ok_or_else(|| Bad::answer(format!("there is no {side} at place {k}")))
        };
        let mut actions = Vec::new();
        for (actor, c) in self.living(true).into_iter().zip(commands) {
            let target = match c.command {
                COMMAND_ITEM => Target::Item(
                    c.what as i32,
                    Who::Actor(place(&self.actors, c.target, "actor")?),
                ),
                COMMAND_SKILL => {
                    let skill = db.skill(c.what as i32)?;
                    let dest = if !rules::needs_target(skill) {
                        actor
                    } else if db::targets_enemies(skill) {
                        Who::Enemy(place(&self.enemies, c.target, "enemy")?)
                    } else {
                        Who::Actor(place(&self.actors, c.target, "actor")?)
                    };
                    Target::Skill(skill.id, dest)
                }
                COMMAND_ATTACK => Target::One(Who::Enemy(place(&self.enemies, c.what, "enemy")?)),
                _ => Target::None,
            };
            actions.push((actor, c.command, target));
        }
        actions.extend(self.enemy_actions(db)?);
        for i in self.execution_order(&actions) {
            self.check_pages(db)?;
            let (who, command, target) = actions[i];
            if !self.get(who).alive() {
                continue;
            }
            // One a page put in this turn has no action: the one pending in
            // its place was of whoever left it.
            if matches!(who, Who::Actor(k) if self.joined.contains(&k)) {
                continue;
            }
            match (command, target) {
                // Defending marks the defender **when its turn comes**, not
                // when choosing: an enemy that acts before hits it in full.
                (COMMAND_DEFEND, _) => self.get_mut(who).defending = true,
                (COMMAND_ESCAPE, _) => {}
                (COMMAND_SKILL, Target::Skill(skill, target)) => {
                    // A dead target **is not retargeted**: `IsTargetValid`
                    // discards it and the action is lost.
                    if self.get(target).alive() {
                        self.use_skill(db, who, skill, target)?;
                    }
                }
                (COMMAND_ITEM, Target::Item(item, target)) => {
                    // An item cannot miss and rolls nothing, and it goes to
                    // the one chosen even if it changed along the way.
                    let before = self.get(target).hp;
                    let (hp, _up) = item_effect(db.item(item)?, self.get(target));
                    self.get_mut(target).hp = hp;
                    self.logged(who, target, true, false, before - hp);
                }
                (_, Target::One(mut target)) => {
                    if !self.get(target).alive() {
                        // `Game_BattleAlgorithm` retargets another one on the
                        // same side when the target died before its turn.
                        let candidates = self.living(self.get(target).is_actor);
                        let Some(&first) = candidates.first() else {
                            continue;
                        };
                        target = first;
                    }
                    let (hit, critical, damage) = self.attack(who, target);
                    self.logged(who, target, hit, critical, damage);
                }
                _ => {
                    return Err(Bad::answer(format!(
                        "command {command} has nothing to act on"
                    )));
                }
            }
        }
        self.check_pages(db)?;
        if self.living(false).is_empty() {
            self.result = Some(VICTORY);
            self.drops = self.roll_drops();
        } else if self.living(true).is_empty() {
            self.result = Some(DEFEAT);
        }
        Ok(self.result)
    }

    pub fn to_json(&self) -> Value {
        json!({
            "actors": self.actors.iter().map(Combatant::to_json).collect::<Vec<_>>(),
            "enemies": self.enemies.iter().map(Combatant::to_json).collect::<Vec<_>>(),
            "turn": self.turn,
            "result": self.result,
            "escape_chance": self.escape_chance,
            "rng": self.rng.state,
            "state": self.state.iter().map(|(k, v)| (k.to_string(), json!(v))).collect::<Map<_, _>>(),
            "done_pages": self.done_pages.iter().collect::<Vec<_>>(),
            "switches": self.switches,
            "drops": self.drops,
            "experience": self.experience(),
            "gold": self.gold(),
            "log": self.log.iter().map(|l| json!([l.turn, l.source, l.target, l.hit, l.critical, l.damage, l.hp])).collect::<Vec<_>>(),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn check_turns_is_easyrpgs() {
        let at = |base, multiple| -> Vec<i64> {
            (0..10)
                .filter(|&t| check_turns(t, base, multiple))
                .collect()
        };
        assert_eq!(at(1, 0), [1]);
        assert_eq!(at(0, 0), [0]);
        assert_eq!(at(1, 3), [1, 4, 7]);
        assert_eq!(at(0, 2), [0, 2, 4, 6, 8]);
    }

    #[test]
    fn change_hp_is_easyrpgs() {
        let one = |hp: i64, amount: i64, lethal: bool| {
            let mut c = Combatant {
                name: String::new(),
                number: 1,
                is_actor: true,
                hp_max: 40,
                hp,
                sp_max: 0,
                sp: 0,
                base: [1; 4],
                modifier: [0; 4],
                hit_rate: 90,
                critical: 0,
                skills: vec![],
                actions: vec![],
                weapon_sp: 0,
                equipment: vec![],
                level: None,
                defending: false,
                command: 0,
                hidden: false,
                exp: 0,
                gold: 0,
                drop_item: 0,
                drop_chance: 0,
            };
            c.change_hp(amount, lethal);
            c.hp
        };
        assert_eq!(one(40, -999, true), 0);
        assert_eq!(one(40, -999, false), 1, "a loss that is not lethal leaves 1");
        assert_eq!(one(0, 50, false), 0, "a dead one does not change");
        assert_eq!(one(30, 50, false), 40, "nor goes past its maximum");
    }

    #[test]
    fn a_branch_compares_in_rm2ks_order() {
        let ops: Vec<bool> = (0..6).map(|op| compare(40, op, 40).unwrap()).collect();
        assert_eq!(ops, [true, true, true, false, false, false]);
        assert!(compare(39, 1, 40).is_ok_and(|x| !x));
        assert!(compare(1, 6, 1).is_err());
    }

    #[test]
    fn a_defended_negative_effect_halves_toward_zero() {
        assert_eq!(half(-25), -12);
        assert_eq!(half(25), 12);
    }

    #[test]
    fn the_hit_chance_rounds_up_what_it_subtracts() {
        // 100 - ceil(10 * 30 / 20) = 100 - 15; and 100 - ceil(10 * 31 / 20).
        assert_eq!(hit_rate_by_agility(90, 10, 20), 85);
        assert_eq!(hit_rate_by_agility(90, 10, 21), 84);
    }
}
