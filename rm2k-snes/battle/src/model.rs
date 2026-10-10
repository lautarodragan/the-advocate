//! What the rest of the conversion writes of the battle —the second call
//! of the stage, after the pages compiled—, and the battle played for
//! whoever tests a console against it.
//!
//! The requests are JSON, and so are the answers; see the README for their
//! shape.

use crate::db::Db;
use crate::fail::{Bad, Result};
use crate::rules::{self, ACTIONS_MAX};
use crate::screen::{
    self, BA_ENEMY_NAME_WIDTH, BA_ITEM_NAME_WIDTH, BA_NAME_WIDTH, BA_SKILL_NAME_WIDTH,
    BA_STATE_WIDTH,
};
use rm2k_rules::actor::Standing;
use rm2k_snes_text::cells;
use rm2k_snes_text::font::Font;
use crate::simulate::{self, Battle, Combatant, Command, TroopPage, BATTLE_SEED};
use serde_json::{json, Map, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

/// The file `model` writes.
pub const MODEL_FILE: &str = "model.json";
/// The file `simulate` writes.
pub const SIMULATE_FILE: &str = "simulate.json";
/// The file `lines` writes.
pub const LINES_FILE: &str = "lines.json";
/// The file `layout` writes.
pub const LAYOUT_FILE: &str = "layout.json";
/// The file `experience` writes.
pub const EXPERIENCE_FILE: &str = "experience.json";

/// A request file, parsed.
pub fn read_request(path: &Path) -> Result<Value> {
    let text = std::fs::read_to_string(path)
        .map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{}: {e}", path.display())))
}

fn field<'a>(data: &'a Value, name: &str) -> Result<&'a Value> {
    data.get(name)
        .ok_or_else(|| Bad::answer(format!("the request has no `{name}`")))
}

fn number(v: &Value, what: &str) -> Result<i64> {
    v.as_i64()
        .ok_or_else(|| Bad::answer(format!("{what}: {v} is not a whole number")))
}

fn numbers(v: &Value, what: &str) -> Result<Vec<i64>> {
    v.as_array()
        .ok_or_else(|| Bad::answer(format!("{what} is not a list")))?
        .iter()
        .map(|x| number(x, what))
        .collect()
}

fn list<'a>(data: &'a Value, name: &str) -> Result<&'a Vec<Value>> {
    field(data, name)?
        .as_array()
        .ok_or_else(|| Bad::answer(format!("`{name}` is not a list")))
}

/// The answer to `model`:
///
/// ```json
/// {"actors": [11, 12], "troops": [82, 97], "items": [1, 2],
///  "skill_pairs": [[11, 131], [11, 146]], "item_name_width": 20}
/// ```
///
/// `actors` are the ones that can be in the party; `troops`, the ones the
/// cartridge's battles ask for, in the compiler's order; `items`, the ones
/// the cartridge knows; `skill_pairs`, every (actor, skill) the compiler
/// gave a slot, in the slots' order; `item_name_width`, how much of an
/// item's name the item screens write, which is theirs.
pub fn model(db: &Db, request: &Value) -> Result<Value> {
    let to_i32 = |v: Vec<i64>| v.into_iter().map(|x| x as i32).collect::<Vec<i32>>();
    let actors = to_i32(numbers(field(request, "actors")?, "`actors`")?);
    let troops = to_i32(numbers(field(request, "troops")?, "`troops`")?);
    let items = to_i32(numbers(field(request, "items")?, "`items`")?);
    let name_width = number(field(request, "item_name_width")?, "`item_name_width`")? as usize;
    let mut pairs = Vec::new();
    for p in list(request, "skill_pairs")? {
        let p = numbers(p, "a skill pair")?;
        if p.len() != 2 {
            return Err(Bad::answer(format!(
                "a skill pair is two numbers, not {p:?}"
            )));
        }
        pairs.push((p[0] as i32, p[1] as i32));
    }

    // The troops the database has, in the cartridge's order, and the
    // enemies that form them.
    let used: Vec<i32> = troops
        .into_iter()
        .filter(|t| db.troops.contains_key(t))
        .collect();
    let mut enemies = BTreeSet::new();
    for &t in &used {
        for m in &db.troop(t)?.members {
            enemies.insert(m.enemy_id);
        }
    }
    let enemies: Vec<i32> = enemies.into_iter().collect();

    // What each enemy can do, and the skills of those actions: the console
    // weighs at most `ACTIONS_MAX`, and carries the rating in seven bits.
    let mut actions = Map::new();
    let mut skills = BTreeSet::new();
    for &e in &enemies {
        let theirs = rules::actions_of_enemy(db, e)?;
        if theirs.len() > ACTIONS_MAX {
            return Err(Bad::answer(format!(
                "enemy {e} brings {} actions and the console weighs {ACTIONS_MAX}",
                theirs.len()
            )));
        }
        for a in &theirs {
            if !(0 < a.rating && a.rating < 0x80) {
                return Err(Bad::answer(format!(
                    "enemy {e} brings an action with rating {} and the console carries it in \
                     seven bits",
                    a.rating
                )));
            }
            skills.extend(a.skill);
        }
        actions.insert(
            e.to_string(),
            json!(theirs.iter().map(simulate::action_json).collect::<Vec<_>>()),
        );
    }
    // And the ones the party can end up knowing that the battle offers:
    // every pair the compiler knows of, not only the learning table's.
    for &(a, h) in &pairs {
        if actors.contains(&a) && rules::skill_usable(db.skill(h)?) {
            skills.insert(h);
        }
    }
    let skills: Vec<i32> = skills.into_iter().collect();
    // The ones leveling up teaches past the starting level —`SetLevel`'s,
    // clamped to the actor's range—, whose whole name the victory says.
    let mut taught = BTreeSet::new();
    for &(a, h) in &pairs {
        if let (true, Some(actor)) = (actors.contains(&a), db.actors.get(&a)) {
            if rules::level_learned(actor, h) > rm2k_rules::actor::initial_level(actor) {
                taught.insert(h);
            }
        }
    }
    let taught: Vec<i32> = taught.into_iter().collect();
    let pair_levels: Vec<i64> = pairs
        .iter()
        .map(|&(a, h)| {
            db.actors
                .get(&a)
                .map_or(0, |actor| rules::level_learned(actor, h))
        })
        .collect();
    let mut item_battle = Vec::new();
    for &i in &items {
        item_battle.push(rules::item_usable_in_battle(db.item(i)?));
    }
    // What the battle writes with the game's font, if the request says it
    // —`font` and `letter_spacing`, as the screens stage takes them—: the
    // names it cuts, and how many pairs of tiles of the text layer its
    // busiest lists ask for.
    let mut party_line = None;
    let game_font = font_of(request)?;
    let (cut, pairs_asked) = match request.get("font") {
        None => (Vec::new(), Value::Null),
        Some(spec) => {
            let spec = spec.as_str().ok_or_else(|| Bad::answer("`font` is a name or a path"))?;
            let spacing = request.get("letter_spacing").and_then(Value::as_i64).unwrap_or(0);
            let font = Font::named(spec, rm2k_snes_text::font::MINCHO)
                .and_then(|f| f.with_spacing(spacing))
                .map_err(Bad::answer)?;
            let mut usable = Vec::new();
            for (&i, &battle) in items.iter().zip(&item_battle) {
                if battle {
                    usable.push(db.item(i)?.name.clone());
                }
            }
            let mut commands = Vec::new();
            let mut known: BTreeMap<i32, BTreeSet<i32>> = BTreeMap::new();
            for &a in &actors {
                commands.push(strip_name(&rules::skill_command_name(db, a)?));
                known.insert(a, BTreeSet::new());
            }
            for &(a, h) in &pairs {
                if let Some(theirs) = known.get_mut(&a) {
                    if rules::skill_usable(db.skill(h)?) {
                        theirs.insert(h);
                    }
                }
            }
            let party_skills: BTreeSet<i32> = known.values().flatten().copied().collect();
            let enemy_names: Vec<String> =
                enemies.iter().map(|&e| Ok(db.enemy(e)?.name.clone())).collect::<Result<_>>()?;
            let skill_names: Vec<String> =
                party_skills.iter().map(|&h| Ok(db.skill(h)?.name.clone())).collect::<Result<_>>()?;
            let actor_names: Vec<String> =
                actors.iter().filter_map(|a| db.actors.get(a)).map(|a| a.name.clone()).collect();
            let states = vec![db.terms.normal_status.clone(), screen::dead_text(db)?];
            let mut all_commands = commands.clone();
            all_commands.extend(
                [&db.terms.command_attack, &db.terms.command_defend, &db.terms.command_item, &db.terms.battle_escape]
                    .map(|t| screen::command_text(t)),
            );
            let places = [
                ("actor names in the battle", &actor_names, WHOLE, BA_NAME_WIDTH),
                ("states in the battle", &states, WHOLE, BA_STATE_WIDTH),
                ("enemy names in the battle", &enemy_names, WHOLE, BA_ENEMY_NAME_WIDTH),
                ("skill names in the battle", &skill_names, WHOLE, BA_SKILL_NAME_WIDTH),
                ("item names in the battle", &usable, name_width, BA_ITEM_NAME_WIDTH),
                ("commands in the battle", &all_commands, screen::BA_COMMAND_WIDTH, screen::BA_COMMAND_CELLS),
            ];
            party_line = screen::check_party_line(&font, &db.terms.hp_short, &db.terms.sp_short);
            let cut: Vec<Value> = places
                .iter()
                .filter_map(|(place, names, letters, cells)| cut_in_cells(&font, place, names, *letters, *cells))
                .collect();
            let lists = BusiestLists { font: &font };
            let mut skills_asked = (0, 0, 0);
            for (&a, theirs) in &known {
                let names: Vec<(String, String)> = theirs
                    .iter()
                    .map(|&h| Ok((db.skill(h)?.name.clone(), db.skill(h)?.description.clone())))
                    .collect::<Result<_>>()?;
                skills_asked = skills_asked.max((lists.skill_list(&names), a, names.len()));
            }
            let items_asked = lists.item_list(&usable, name_width);
            (
                cut,
                json!({"skills": skills_asked.0, "skills_actor": skills_asked.1, "skills_known": skills_asked.2, "items": items_asked}),
            )
        }
    };
    let mut troop_list = Vec::new();
    let (mut exp_max, mut gold_max) = (0, 0);
    for &t in &used {
        let (exp, gold) = (rules::troop_exp(db, t)?, rules::troop_gold(db, t)?);
        exp_max = exp_max.max(exp);
        gold_max = gold_max.max(gold);
        troop_list.push(json!({"id": t, "exp": exp, "gold": gold}));
    }

    // The texts. The victory term has to fit in the lines the window leaves
    // it, and every line the victory builds in its width.
    let t = &db.terms;
    let victory = screen::victory_lines_in(&t.victory, game_font.as_ref())?;
    if victory.len() > screen::BA_VICTORY_TERM_MAX {
        return Err(Bad::answer(format!(
            "the victory term takes {} lines and the window leaves it {}: {victory:?}",
            victory.len(),
            screen::BA_VICTORY_TERM_MAX
        )));
    }
    let mut drop_names = BTreeSet::new();
    for &e in &enemies {
        let drop = db.enemy(e)?.drop_id;
        if drop != 0 {
            drop_names.insert(drop);
        }
    }
    let mut drop_texts = Vec::new();
    for d in drop_names {
        drop_texts.push(db.item(d)?.name.clone());
    }
    let actor_names: Vec<String> = actors
        .iter()
        .filter_map(|a| db.actors.get(a))
        .map(|a| a.name.clone())
        .collect();
    let mut taught_names = Vec::new();
    for &h in &taught {
        taught_names.push(db.skill(h)?.name.clone());
    }
    screen::check_victory(
        db,
        exp_max,
        &actor_names,
        &taught_names,
        gold_max,
        &drop_texts,
        name_width,
        game_font.as_ref(),
    )?;

    let mut enemy_names = Map::new();
    for &e in &enemies {
        enemy_names.insert(
            e.to_string(),
            json!(db.enemy(e)?.name),
        );
    }
    let mut skill_texts = Map::new();
    for &h in &skills {
        let s = db.skill(h)?;
        skill_texts.insert(
            h.to_string(),
            json!({"name": s.name,
                   "description": s.description}),
        );
    }
    let mut skill_commands = Map::new();
    for &a in &actors {
        skill_commands.insert(
            a.to_string(),
            json!(screen::command_text(&rules::skill_command_name(db, a)?)),
        );
    }
    let mut out = json!({
        "layout": screen::layout(),
        "enemies": enemies,
        "actions": actions,
        "skills": skills,
        "taught": taught,
        "pair_levels": pair_levels,
        "item_battle": item_battle,
        "troops": troop_list,
        "texts": {
            "victory": victory,
            "attack": screen::command_text(&t.command_attack),
            "defend": screen::command_text(&t.command_defend),
            "escape": screen::command_text(&t.battle_escape),
            "revived": screen::revived_text(db)?,
            "dead": screen::dead_text(db)?,
            "skill_commands": skill_commands,
            "enemies": enemy_names,
            "skills": skill_texts,
        },
    });
    // Only with the font: without it there is nothing to measure.
    if !pairs_asked.is_null() {
        out["cut"] = json!(cut);
        out["pairs"] = pairs_asked;
        out["party_line"] = json!(party_line);
    }
    Ok(out)
}

/// Whether a request needs the troops, which are most of the database:
/// only if it names one —a battle's troop or pages, the model's troops—.
pub fn needs_troops(request: &Value) -> bool {
    ["troop", "pages"]
        .iter()
        .any(|k| request.get(*k).is_some_and(|v| !v.is_null()))
        || request
            .get("troops")
            .and_then(Value::as_array)
            .is_some_and(|t| !t.is_empty())
}

fn optional<'a>(data: &'a Value, name: &str) -> Option<&'a Value> {
    data.get(name).filter(|v| !v.is_null())
}

/// The battle a `simulate` request describes, and its steps played:
///
/// ```json
/// {"seed": null,
///  "actors": [{"id": 11, "equipment": null, "level": null, "skills": null}],
///  "troop": 82, "enemies": null, "pages": null, "switches": {},
///  "steps": [{"start": null}, {"set": {"side": "enemies", "place": 0, "hp": 1}},
///            {"turn": [[0, 0], [1, 0], [4, 150, 0], [3, 12, 1]]},
///            {"escape_chance": 0}, {"flee": null}, {"enemy_action": 0}]}
/// ```
pub fn simulate(db: &Db, request: &Value) -> Result<Value> {
    let empty = Vec::new();
    let mut actors = Vec::new();
    for a in optional(request, "actors").map_or(Ok(&empty), |_| list(request, "actors"))? {
        let id = number(field(a, "id")?, "an actor's `id`")? as i32;
        let equipment = match optional(a, "equipment") {
            Some(e) => Some(
                numbers(e, "an actor's `equipment`")?
                    .into_iter()
                    .map(|x| x as i32)
                    .collect::<Vec<_>>(),
            ),
            None => None,
        };
        let level = optional(a, "level")
            .map(|l| number(l, "an actor's `level`"))
            .transpose()?;
        let mut who = Combatant::actor(db, id, equipment.as_deref(), level)?;
        if let Some(s) = optional(a, "skills") {
            who.skills = numbers(s, "an actor's `skills`")?
                .into_iter()
                .map(|x| x as i32)
                .collect();
        }
        actors.push(who);
    }
    let mut enemies = Vec::new();
    if let Some(list) = optional(request, "enemies") {
        for e in list
            .as_array()
            .ok_or_else(|| Bad::answer("`enemies` is not a list"))?
        {
            let id = number(field(e, "id")?, "an enemy's `id`")? as i32;
            let place = number(field(e, "place")?, "an enemy's `place`")?;
            let hidden = optional(e, "hidden")
                .and_then(Value::as_bool)
                .unwrap_or(false);
            enemies.push(Combatant::enemy(db, id, place, hidden)?);
        }
    } else if let Some(t) = optional(request, "troop") {
        let t = number(t, "`troop`")? as i32;
        for (place, m) in db.members(t)?.into_iter().enumerate() {
            enemies.push(Combatant::enemy(db, m.enemy_id, place as i64, m.invisible)?);
        }
    }
    let pages = match optional(request, "pages") {
        Some(t) => db
            .troop(number(t, "`pages`")? as i32)?
            .pages
            .iter()
            .map(TroopPage::of)
            .collect(),
        None => Vec::new(),
    };
    let mut switches = BTreeMap::new();
    if let Some(s) = optional(request, "switches") {
        for (k, v) in s
            .as_object()
            .ok_or_else(|| Bad::answer("`switches` is not an object"))?
        {
            let id: i64 = k
                .parse()
                .map_err(|_| Bad::answer(format!("switch {k:?} is not a number")))?;
            switches.insert(id, v.as_bool().unwrap_or(false));
        }
    }
    let seed = optional(request, "seed")
        .map(|s| number(s, "`seed`"))
        .transpose()?
        .unwrap_or(BATTLE_SEED);
    let mut battle = Battle::new(actors, enemies, seed, pages, switches);
    let mut returned = Vec::new();
    for step in optional(request, "steps").map_or(Ok(&empty), |_| list(request, "steps"))? {
        returned.push(play(db, &mut battle, step)?);
    }
    Ok(json!({"steps": returned, "battle": battle.to_json()}))
}

fn play(db: &Db, battle: &mut Battle, step: &Value) -> Result<Value> {
    let step = step
        .as_object()
        .filter(|o| o.len() == 1)
        .ok_or_else(|| Bad::answer(format!("a step is an object with one key, not {step}")))?;
    let (name, arg) = step.iter().next().unwrap();
    match name.as_str() {
        "start" => {
            battle.start(db)?;
            Ok(Value::Null)
        }
        "flee" => Ok(json!(battle.flee())),
        // The escape chance, as a test puts it in the console's
        // `BA_ESCAPE`: a failed escape is otherwise up to the seed.
        "escape_chance" => {
            battle.escape_chance = number(arg, "`escape_chance`")?;
            Ok(Value::Null)
        }
        "enemy_action" => {
            let k = number(arg, "`enemy_action`")?;
            let k = usize::try_from(k)
                .ok()
                .filter(|&k| k < battle.enemies.len())
                .ok_or_else(|| Bad::answer(format!("there is no enemy at place {k}")))?;
            Ok(battle
                .enemy_action(db, k)?
                .as_ref()
                .map_or(Value::Null, simulate::action_json))
        }
        "set" => {
            let side = field(arg, "side")?.as_str().unwrap_or("");
            let place = number(field(arg, "place")?, "`place`")?;
            let list = match side {
                "actors" => &mut battle.actors,
                "enemies" => &mut battle.enemies,
                _ => return Err(Bad::answer(format!("there is no side {side:?}"))),
            };
            let who = usize::try_from(place)
                .ok()
                .and_then(|k| list.get_mut(k))
                .ok_or_else(|| Bad::answer(format!("there is no {side} at place {place}")))?;
            if let Some(hp) = optional(arg, "hp") {
                who.hp = number(hp, "`hp`")?;
            }
            if let Some(sp) = optional(arg, "sp") {
                who.sp = number(sp, "`sp`")?;
            }
            Ok(Value::Null)
        }
        "turn" => {
            let mut commands = Vec::new();
            for c in arg
                .as_array()
                .ok_or_else(|| Bad::answer("`turn` is not a list"))?
            {
                let c = numbers(c, "a command")?;
                let at = |k: usize| c.get(k).copied().unwrap_or(0);
                if c.is_empty() {
                    return Err(Bad::answer("a command with nothing in it"));
                }
                commands.push(Command {
                    command: at(0),
                    what: at(1),
                    target: at(2),
                });
            }
            Ok(json!(battle.play_turn(db, &commands)?))
        }
        _ => Err(Bad::answer(format!("there is no step {name:?}"))),
    }
}

/// The victory's lines as the console builds them, for whoever compares:
///
/// ```json
/// {"item_name_width": 20,
///  "lines": [["victory"], ["exp", 90], ["gold", 285], ["item", 257],
///            ["level", 11, 21], ["skill", 148]]}
/// ```
///
/// Each one answers a list of lines: the victory term, split, is more than
/// one; the others are one.
pub fn lines(db: &Db, request: &Value) -> Result<Value> {
    let name_width = number(field(request, "item_name_width")?, "`item_name_width`")? as usize;
    let mut out = Vec::new();
    for l in list(request, "lines")? {
        let l = l
            .as_array()
            .ok_or_else(|| Bad::answer("a line is a list"))?;
        let kind = l.first().and_then(Value::as_str).unwrap_or("");
        let arg = |k: usize| -> Result<i64> {
            number(
                l.get(k).unwrap_or(&Value::Null),
                &format!("the `{kind}` line"),
            )
        };
        out.push(match kind {
            "victory" => screen::victory_lines_in(&db.terms.victory, font_of(request)?.as_ref())?,
            "exp" => vec![screen::exp_line(db, arg(1)?)],
            "gold" => vec![screen::gold_line(db, arg(1)?)],
            "item" => vec![screen::item_line(
                db,
                &db.item(arg(1)? as i32)?.name,
                name_width,
            )],
            "level" => vec![screen::level_line(
                db,
                &db.actor(arg(1)? as i32)?.name,
                arg(2)?,
            )],
            "skill" => vec![screen::skill_line(db, &db.skill(arg(1)? as i32)?.name)],
            _ => return Err(Bad::answer(format!("there is no line {kind:?}"))),
        });
    }
    Ok(json!({"lines": out}))
}

/// What a `ChangeExp` or a `ChangeLevel` leaves, one change per entry:
///
/// ```json
/// {"changes": [{"actor": 15, "level": 3, "exp": 90, "skills": [147],
///               "exp_by": 500},
///              {"actor": 15, "level": 3, "exp": 90, "skills": [147],
///               "levels_by": -2}]}
/// ```
///
/// Each from where the actor stands —`level`, `exp`, the `skills` it
/// knows—, by `exp_by` experience or by `levels_by` levels: easyrpg's
/// `ChangeExp(GetExp() + exp_by)` and `ChangeLevel(GetLevel() +
/// levels_by)`. The answer, per change, is where it was left and the lines
/// of its level-up message —its level line and one per skill it did not
/// know— or none if it did not go up, which is what RM2k's
/// `PendingMessage` gets:
///
/// ```json
/// {"changes": [{"level": 5, "exp": 512, "skills": [140, 147, 148],
///               "lines": ["Arden LEVEL 5 achieved!", "Wild Slash learned!", "..."]}]}
/// ```
pub fn experience(db: &Db, request: &Value) -> Result<Value> {
    let mut out = Vec::new();
    for c in list(request, "changes")? {
        let id = number(field(c, "actor")?, "`actor`")? as i32;
        let actor = db.actor(id)?;
        let mut at = Standing {
            level: number(field(c, "level")?, "`level`")?,
            exp: number(field(c, "exp")?, "`exp`")?,
            skills: numbers(field(c, "skills")?, "`skills`")?
                .into_iter()
                .map(|h| h as i32)
                .collect(),
        };
        at.skills.sort_unstable();
        at.skills.dedup();
        let before = at.level;
        let learned = match (optional(c, "exp_by"), optional(c, "levels_by")) {
            (Some(by), None) => at.change_exp(actor, at.exp + number(by, "`exp_by`")?),
            (None, Some(by)) => at.change_level(actor, at.level + number(by, "`levels_by`")?),
            _ => return Err(Bad::answer("a change is `exp_by` or `levels_by`, one of the two")),
        };
        let mut lines = Vec::new();
        if at.level > before {
            lines.push(screen::level_line(db, &actor.name, at.level));
            for h in learned {
                lines.push(screen::skill_line(db, &db.skill(h)?.name));
            }
        }
        out.push(json!({"level": at.level, "exp": at.exp, "skills": at.skills, "lines": lines}));
    }
    Ok(json!({"changes": out}))
}

/// The game's font, if the request names it —`font` and `letter_spacing`,
/// as the screens stage takes them—.
fn font_of(request: &Value) -> Result<Option<Font>> {
    let Some(spec) = request.get("font") else {
        return Ok(None);
    };
    let spec = spec.as_str().ok_or_else(|| Bad::answer("`font` is a name or a path"))?;
    let spacing = request.get("letter_spacing").and_then(Value::as_i64).unwrap_or(0);
    Font::named(spec, rm2k_snes_text::font::MINCHO)
        .and_then(|f| f.with_spacing(spacing))
        .map(Some)
        .map_err(Bad::answer)
}

/// Python's `str.strip()`, which the commands go through: see
/// `screen::command_text`.
fn strip_name(text: &str) -> String {
    text.trim_matches(|c: char| c.is_whitespace()).to_string()
}

/// How many letters the cartridge keeps of an enemy's or a skill's name:
/// all of them —see `screen.rs`, above `TL_RECORD`—, so only the pixels cut.
const WHOLE: usize = usize::MAX;

/// The names of `names` the battle cuts: the cartridge keeps `letters` of
/// each, and of those, the ones whose advances add up to `cells` cells
/// —the console's `scr_cap`—. `{"place", "cells", "names": [[name, its
/// pixels, what shows]]}`, or nothing if none is cut.
fn cut_in_cells(font: &Font, place: &str, names: &[String], letters: usize, cells: usize) -> Option<Value> {
    let mut seen = BTreeSet::new();
    let mut cut = Vec::new();
    for name in names {
        if !seen.insert(name.clone()) {
            continue;
        }
        let shown = shown_in_cells(font, name, letters, cells);
        if shown != *name {
            cut.push(json!([name, font.width(name), shown]));
        }
    }
    (!cut.is_empty()).then(|| json!({"place": place, "cells": cells, "names": cut}))
}

/// What the battle shows of `text`: its first `letters`, and of those the
/// ones whose advances add up to `cells` cells.
fn shown_in_cells(font: &Font, text: &str, letters: usize, cells: usize) -> String {
    let mut width = 0;
    text.chars()
        .take(letters)
        .take_while(|&c| {
            width += font.advance(c);
            width <= 8 * cells
        })
        .collect()
}

/// The battle's busiest lists as the text layer composes them, with the
/// widest texts the cartridge can put in each place at once: what they ask
/// of its pool of pairs of tiles —see `rm2k_snes_text::cells`—. The rows
/// are the console's: the description on top and the list in the band
/// below the scene, which is all the screen shows while a list is open. An
/// upper bound, since what shows at once is never all the widest.
struct BusiestLists<'a> {
    font: &'a Font,
}

/// Where a run starts inside its cell: the text layer's, `SCR_TEXT_X` of
/// `rm2k-snes-screens`, which the battle shares.
const TEXT_X: usize = 1;

/// A row: its runs, `(x, text, colour)`.
type Row = Vec<(usize, String, usize)>;

impl BusiestLists<'_> {
    /// A run from cell `col`, where the console starts one.
    fn at(col: i64, text: &str) -> (usize, String, usize) {
        (col as usize * 8 + TEXT_X, text.to_string(), 0)
    }

    /// A list of two columns as the band shows it: per row, each column's
    /// cursor, name, mark —the dash or the colon— and two digits.
    fn two_columns(names: &[String], mark: &str) -> Vec<Row> {
        let per_row = screen::BA_SKILL_COLUMNS as usize;
        names
            .chunks(per_row)
            .take(screen::BA_SKILL_ROWS as usize)
            .map(|chunk| {
                let mut row = Row::new();
                for (c, name) in chunk.iter().enumerate() {
                    let x0 = c as i64 * screen::BA_SKILL_COLUMN_DX;
                    row.push(Self::at(x0 + screen::BA_SKILL_NAME_COL, name));
                    row.push(Self::at(x0 + screen::BA_SKILL_DASH_COL, mark));
                    row.push(Self::at(x0 + screen::BA_SKILL_COST_COL, "99"));
                }
                row
            })
            .collect()
    }

    /// An actor's skill list: the widest description, and its widest
    /// skills in the two columns with their costs.
    fn skill_list(&self, skills: &[(String, String)]) -> usize {
        let mut names: Vec<String> = skills
            .iter()
            .map(|(n, _)| shown_in_cells(self.font, n, WHOLE, BA_SKILL_NAME_WIDTH))
            .collect();
        names.sort_by_key(|n| std::cmp::Reverse(self.font.width(n)));
        let description = skills
            .iter()
            .map(|(_, d)| shown_in_cells(self.font, d, WHOLE, screen::BA_HELP_WIDTH))
            .max_by_key(|d| self.font.width(d))
            .unwrap_or_default();
        // Two lines of it, which is what the converter's split can give: an
        // upper bound.
        let mut rows: Vec<Row> = vec![
            vec![Self::at(screen::BA_SKILL_DESC_COL, &description)],
            vec![Self::at(screen::BA_SKILL_DESC_COL, &description)],
        ];
        rows.extend(Self::two_columns(&names, "-"));
        cells::pairs(self.font, rows.iter().map(Vec::as_slice))
    }

    /// The item list, with the widest items the battle can use and their
    /// counts, under the two lines of a description as wide as the band.
    fn item_list(&self, usable: &[String], name_width: usize) -> usize {
        let mut names: Vec<String> = usable
            .iter()
            .map(|n| shown_in_cells(self.font, n, name_width, BA_ITEM_NAME_WIDTH))
            .collect();
        names.sort_by_key(|n| std::cmp::Reverse(self.font.width(n)));
        let wide = "W".repeat(screen::BA_HELP_WIDTH);
        let mut rows: Vec<Row> = vec![
            vec![Self::at(screen::BA_HELP_COL, &wide)],
            vec![Self::at(screen::BA_HELP_COL, &wide)],
        ];
        rows.extend(Self::two_columns(&names, ":"));
        cells::pairs(self.font, rows.iter().map(Vec::as_slice))
    }
}
