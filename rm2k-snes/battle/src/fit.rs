//! A troop with more members than a battle holds, cut down to
//! [`ENEMIES_MAX`] by leaving out the ones its pages only use as scenery,
//! with the pages' commands renumbered to the places that are left.
//!
//! RM2k's own data has no limit —liblcf reads as many members as the LDB
//! holds, and easyrpg-player's `Game_EnemyParty` sets them all up—, and The
//! Book of Three has a troop of nine. The console's battle holds eight: its
//! combatants live at fixed places in far RAM, forty bytes each, and the
//! scene's masks, the hidden ones' table and the drawing order are a byte
//! per troop. Carrying a ninth is a wider battle for every game, for one
//! troop of one; leaving out one the player never fights is a scene with
//! one extra fewer.
//!
//! **Which ones go**, by what the pages do with each member, from the
//! highest place down within each kind:
//!
//! 1. one hidden that no page ever shows: nobody sees it;
//! 2. one hidden that every page that shows it also kills —a
//!    `ChangeMonsterCondition` with the death, after the show, in the same
//!    page—: a figure that walks through a scene and is not fought;
//! 3. and only if there are still too many, the last places, which is what
//!    the cut was before 2026-10-15: that battle may not be the game's.
//!
//! One a page condition or a battle branch asks about is never chosen in
//! the first two kinds: whatever the page waits for has to be there.
//!
//! **The pages are rewritten** to the new places: `ShowHiddenMonster`,
//! `ChangeMonsterCondition`, `ChangeMonsterHP` and `ChangeMonsterMP` about
//! a member that was left out become a `Comment` —the same index, so what
//! the compiler reports by command still points at RM2k's—, and the rest
//! are renumbered. `ShowBattleAnimationB` on one left out goes to the whole
//! troop: the console draws no battle animation and only keeps its wait.
//!
//! Everyone who reads troops calls [`fit`] —the battle's [`crate::db`], the
//! event compiler and the converter—, so the places agree; the converter
//! notes each [`Cut`] in `degradations.json`.

use crate::db::ENEMIES_MAX;
use ditto::schema::{EventCommand, EventCommandCode, Troop};

/// RM2k's command codes this reads: liblcf's `EventCommand::Code`.
const COMMENT: i32 = 12410;
const CHANGE_MONSTER_HP: i32 = 13110;
const CHANGE_MONSTER_MP: i32 = 13120;
const CHANGE_MONSTER_CONDITION: i32 = 13130;
const SHOW_HIDDEN_MONSTER: i32 = 13150;
const SHOW_BATTLE_ANIMATION_B: i32 = 13260;
const BATTLE_COND_BRANCH: i32 = 13310;
/// `ConditionalBranch_B`'s kind that asks whether an enemy can act.
const BRANCH_ENEMY_CAN_ACT: i32 = 3;
/// The death, which is always state 1 in RM2k.
const DEATH: i32 = 1;

/// What a troop lost to fit.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Cut {
    pub troop: i32,
    /// How many members it had.
    pub members: usize,
    /// The places left out, from 0 as the pages count them, in order.
    pub left_out: Vec<usize>,
    /// Whether all of them were scenery —kinds 1 and 2—, or the battle
    /// lost members it may need.
    pub scenery: bool,
}

impl Cut {
    /// The line `degradations.json` says it with: RM2k's numbering, from 1.
    pub fn text(&self) -> String {
        let places: Vec<String> = self.left_out.iter().map(|p| (p + 1).to_string()).collect();
        let why = if self.scenery {
            "only shown and hidden by its pages, never fought"
        } else {
            "the last ones: the battle may not be the game's"
        };
        format!(
            "troop {} has {} members and a battle holds {ENEMIES_MAX}: member {} left out, {why}",
            self.troop,
            self.members,
            places.join(", ")
        )
    }
}

/// Cuts `troop` down to [`ENEMIES_MAX`] members and rewrites its pages, if
/// it has more; sorts its members and pages by id either way, which is the
/// order RM2k walks them in.
pub fn fit(troop: &mut Troop) -> Option<Cut> {
    troop.members.sort_by_key(|m| m.id);
    troop.pages.sort_by_key(|p| p.id);
    let n = troop.members.len();
    if n <= ENEMIES_MAX {
        return None;
    }
    let left_out = choose(troop);
    let scenery = left_out.iter().all(|&p| kind(troop, p) < 3);
    let kept = |p: usize| -> Option<usize> {
        (!left_out.contains(&p)).then(|| p - left_out.iter().filter(|&&q| q < p).count())
    };
    for page in &mut troop.pages {
        let c = &mut page.condition;
        if c.flags.enemy_hp {
            c.enemy_id = place(c.enemy_id, &kept);
        }
        for command in &mut page.event_commands {
            rewrite(command, &kept);
        }
    }
    let mut place_now = 0;
    troop.members.retain(|_| {
        place_now += 1;
        !left_out.contains(&(place_now - 1))
    });
    Some(Cut { troop: troop.id, members: n, left_out, scenery })
}

/// The places to leave out, sorted.
fn choose(troop: &Troop) -> Vec<usize> {
    let n = troop.members.len();
    let mut order: Vec<usize> = (0..n).collect();
    // By kind, and the highest place first within one.
    order.sort_by_key(|&p| (kind(troop, p), std::cmp::Reverse(p)));
    let mut out: Vec<usize> = order.into_iter().take(n - ENEMIES_MAX).collect();
    out.sort();
    out
}

/// 1, 2 or 3: see the module.
fn kind(troop: &Troop, p: usize) -> u8 {
    if asked_about(troop, p) || !troop.members[p].invisible {
        return 3;
    }
    let mut shown = false;
    for page in &troop.pages {
        let mut standing = false;
        for c in &page.event_commands {
            let code = c.code.to_i32();
            if about(c) != Some(p) {
                continue;
            }
            if code == SHOW_HIDDEN_MONSTER {
                shown = true;
                standing = true;
            } else if code == CHANGE_MONSTER_CONDITION && remove(c) == Some(false) && state(c) == Some(DEATH) {
                standing = false;
            }
        }
        if standing {
            return 3;
        }
    }
    if shown {
        2
    } else {
        1
    }
}

/// Whether a page condition or a battle branch asks about place `p`.
fn asked_about(troop: &Troop, p: usize) -> bool {
    troop.pages.iter().any(|page| {
        (page.condition.flags.enemy_hp && page.condition.enemy_id == p as i32)
            || page.event_commands.iter().any(|c| {
                c.code.to_i32() == BATTLE_COND_BRANCH
                    && c.parameters.first() == Some(&BRANCH_ENEMY_CAN_ACT)
                    && c.parameters.get(1) == Some(&(p as i32))
            })
    })
}

/// The member a command acts on, if it is one of those that name one.
fn about(c: &EventCommand) -> Option<usize> {
    match c.code.to_i32() {
        SHOW_HIDDEN_MONSTER | CHANGE_MONSTER_CONDITION | CHANGE_MONSTER_HP | CHANGE_MONSTER_MP => {
            c.parameters.first().and_then(|&p| usize::try_from(p).ok())
        }
        _ => None,
    }
}

fn remove(c: &EventCommand) -> Option<bool> {
    c.parameters.get(1).map(|&r| r > 0)
}

fn state(c: &EventCommand) -> Option<i32> {
    c.parameters.get(2).copied()
}

/// A place renumbered; one left out, to `ENEMIES_MAX`, which no battle
/// has —as easyrpg's `GetEnemy` answering null—. Only the last-resort cut
/// gets there: the first two kinds never take one that is asked about.
fn place(p: i32, kept: &impl Fn(usize) -> Option<usize>) -> i32 {
    match usize::try_from(p) {
        Ok(p) => kept(p).unwrap_or(ENEMIES_MAX) as i32,
        Err(_) => p,
    }
}

fn rewrite(c: &mut EventCommand, kept: &impl Fn(usize) -> Option<usize>) {
    let code = c.code.to_i32();
    if let Some(p) = about(c) {
        match kept(p) {
            Some(now) => c.parameters[0] = now as i32,
            None => {
                *c = EventCommand {
                    code: EventCommandCode::from_i32(COMMENT),
                    indent: c.indent,
                    string: format!("rm2k-snes: member {} left out of the troop", p + 1),
                    parameters: Vec::new(),
                    unknown: Vec::new(),
                };
            }
        }
    } else if code == SHOW_BATTLE_ANIMATION_B {
        if let Some(target) = c.parameters.get_mut(1) {
            if *target >= 0 {
                *target = match kept(*target as usize) {
                    Some(now) => now as i32,
                    None => -1,
                };
            }
        }
    } else if code == BATTLE_COND_BRANCH && c.parameters.first() == Some(&BRANCH_ENEMY_CAN_ACT) {
        if let Some(target) = c.parameters.get_mut(1) {
            *target = place(*target, kept);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ditto::schema::{TroopMember, TroopPage};

    fn command(code: i32, parameters: &[i32]) -> EventCommand {
        EventCommand {
            code: EventCommandCode::from_i32(code),
            parameters: parameters.to_vec(),
            ..Default::default()
        }
    }

    fn troop(invisible: &[bool], commands: Vec<EventCommand>) -> Troop {
        Troop {
            id: 83,
            members: invisible
                .iter()
                .enumerate()
                .map(|(k, &invisible)| TroopMember { id: k as i32 + 1, enemy_id: 1, invisible, ..Default::default() })
                .collect(),
            pages: vec![TroopPage { id: 1, event_commands: commands, ..Default::default() }],
            ..Default::default()
        }
    }

    fn show(p: i32) -> EventCommand {
        command(SHOW_HIDDEN_MONSTER, &[p])
    }

    fn kill(p: i32) -> EventCommand {
        command(CHANGE_MONSTER_CONDITION, &[p, 0, DEATH])
    }

    #[test]
    fn eight_or_fewer_are_left_as_they_are() {
        let mut t = troop(&[false; 8], vec![show(7)]);
        let before = t.clone();
        assert_eq!(fit(&mut t), None);
        assert_eq!(t, before);
    }

    /// Troop 83 of The Book of Three, by its shape: the first visible, the
    /// rest hidden; the page shows and kills them in a procession, and
    /// leaves the ninth standing.
    #[test]
    fn the_procession_loses_its_last_extra_and_the_ninth_stays() {
        let mut page = vec![show(1), kill(0), show(2), kill(1), kill(2)];
        page.extend((3..8).map(show));
        page.extend((3..8).rev().map(kill));
        page.push(show(8));
        let mut t = troop(&[false, true, true, true, true, true, true, true, true], page);
        let cut = fit(&mut t).unwrap();
        assert_eq!(cut.left_out, vec![7]);
        assert!(cut.scenery);
        assert_eq!(t.members.len(), ENEMIES_MAX);
        assert_eq!(t.members.last().unwrap().id, 9, "the ninth is kept, at the last place");
        let commands = &t.pages[0].event_commands;
        // show(7) and kill(7) are comments, at their indices.
        assert_eq!(commands[9].code.to_i32(), COMMENT);
        assert_eq!(commands[10].code.to_i32(), COMMENT);
        assert_eq!(commands.last().unwrap().parameters, vec![7], "show(8) is now show(7)");
        assert_eq!(commands[11].parameters[0], 6, "kill(6) stays at 6");
    }

    #[test]
    fn one_never_shown_goes_before_one_shown() {
        let mut page: Vec<EventCommand> = (1..8).map(show).collect();
        page.extend((1..8).map(kill));
        let mut hidden = [true; 9];
        hidden[0] = false;
        let mut t = troop(&hidden, page);
        assert_eq!(fit(&mut t).unwrap().left_out, vec![8]);
        // And among the shown ones, the highest place.
        let mut page: Vec<EventCommand> = (1..9).map(show).collect();
        page.extend((1..9).map(kill));
        let mut t = troop(&hidden, page);
        assert_eq!(fit(&mut t).unwrap().left_out, vec![8]);
    }

    #[test]
    fn one_a_page_asks_about_is_not_scenery() {
        let mut page: Vec<EventCommand> = (1..9).map(show).collect();
        page.extend((1..9).map(kill));
        let mut hidden = [true; 9];
        hidden[0] = false;
        let mut t = troop(&hidden, page);
        t.pages[0].condition.flags.enemy_hp = true;
        t.pages[0].condition.enemy_id = 8;
        let cut = fit(&mut t).unwrap();
        assert_eq!(cut.left_out, vec![7]);
        assert_eq!(t.pages[0].condition.enemy_id, 7, "renumbered");
    }

    #[test]
    fn with_no_scenery_the_last_places_go_and_it_says_so() {
        let mut t = troop(&[false; 10], vec![command(SHOW_BATTLE_ANIMATION_B, &[1, 9, 1])]);
        let cut = fit(&mut t).unwrap();
        assert_eq!(cut.left_out, vec![8, 9]);
        assert!(!cut.scenery);
        assert!(cut.text().contains("member 9, 10 left out"), "{}", cut.text());
        assert_eq!(t.pages[0].event_commands[0].parameters, vec![1, -1, 1]);
    }
}
