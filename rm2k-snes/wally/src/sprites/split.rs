//! How the eight object palettes are split among a map's characters, and
//! which events drawn with a tile get drawn at all.

use crate::sprites::character::{character_palette, sheet, sprite_colors, Key, Sheets, OBJ_COLORS, OBJ_PALETTES};
use crate::sprites::fail::Result;
use crate::sprites::npc::Npc;
use adeleine::{merge_least_visible, Color};
use std::collections::{BTreeMap, BTreeSet, HashMap, HashSet};

/// The name an event drawn with a ChipSet tile gives its made-up sheet.
pub const TILE_PREFIX: &str = "@tile:";
/// The suffix of a translucent CharSet drawn dithered: it weighs what its
/// drawing weighs.
pub const DITHER_SUFFIX: &str = "~trama";

/// A map from characters to palettes that remembers the order each one was
/// first given one, which is the order the timer's candidates are looked
/// at in.
#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct PaletteOf {
    order: Vec<Key>,
    number: HashMap<Key, usize>,
}

impl PaletteOf {
    pub fn get(&self, key: &Key) -> Option<usize> {
        self.number.get(key).copied()
    }

    pub fn contains(&self, key: &Key) -> bool {
        self.number.contains_key(key)
    }

    pub fn set(&mut self, key: Key, number: usize) {
        if !self.number.contains_key(&key) {
            self.order.push(key.clone());
        }
        self.number.insert(key, number);
    }

    /// Every character with its palette, in the order they were given one.
    pub fn iter(&self) -> impl Iterator<Item = (&Key, usize)> {
        self.order.iter().map(|k| (k, self.number[k]))
    }
}

/// What the split decided for the whole map, which everything after it uses
/// as is: a second split in another order could give another count.
#[derive(Clone, Debug, Default)]
pub struct Split {
    /// Each palette's colours, in the order of its entries from 1.
    pub palettes: Vec<Vec<Color>>,
    pub palette_of: PaletteOf,
    /// The leader candidates that share the leaders' slot and keep their
    /// own colours: the console uploads them there when their turn to lead
    /// comes.
    pub own: BTreeSet<Key>,
    /// The palettes of the leader candidates, which nobody else gets.
    pub leader_owned: BTreeSet<usize>,
    /// Who was brought below fifteen colours to make room for the timer.
    pub caps: BTreeMap<Key, usize>,
    /// Who was drawn with someone else's palette, for lack of one.
    pub lent: BTreeSet<Key>,
    /// Which poses each character can show, which is what its fifteen
    /// colours are chosen over.
    pub poses: BTreeMap<Key, BTreeSet<i32>>,
}

/// What `drawable_npcs` answered.
pub struct Drawable {
    /// The events that are drawn.
    pub npcs: Vec<Npc>,
    /// `(event, sheet)` of each graphic left out.
    pub discarded: Vec<(usize, String)>,
    pub split: Split,
    /// What it has to say, in order.
    pub notes: Vec<String>,
}

/// How much a CharSet weighs when splitting the palettes, which the game
/// decides: the one that weighs is served first. The dithered suffix does
/// not count: the weight belongs to the drawing.
fn weight(weights: &BTreeMap<String, i64>, charset: &str) -> i64 {
    let base = charset.split(DITHER_SUFFIX).next().unwrap_or("");
    weights.get(base).copied().unwrap_or(0)
}

/// The inputs of the split.
pub struct Ask<'a> {
    pub sheets: &'a Sheets,
    /// The characters the leader candidates are drawn with, in order.
    pub leaders: &'a [Key],
    /// How many palettes the characters get.
    pub cap: usize,
    pub route_graphics: &'a [Key],
    /// The timer's colours, sorted; empty without a timer.
    pub timer_colors: &'a [Color],
    /// The characters that appear in this map of the cartridge only.
    pub only_here: &'a HashSet<Key>,
    pub poses: &'a BTreeMap<Key, BTreeSet<i32>>,
    pub weights: &'a BTreeMap<String, i64>,
}

struct Splitter<'a> {
    ask: &'a Ask<'a>,
    split: Split,
}

impl Splitter<'_> {
    /// The first palette the character's colours fit in; a new one if there
    /// is room or it is `force`d; and otherwise **someone else's**, the one
    /// that moves the fewest pixels. A character with odd colours is a
    /// visible error; one that is not drawn is a trap. `false` only when
    /// there is no palette at all that is not a leader's.
    fn fits(&mut self, key: &Key, force: bool, leader: bool) -> Result<bool> {
        let image = sheet(self.ask.sheets, &key.0)?;
        let (palette, _, _) = character_palette(image, key.1, None, self.ask.poses.get(key))?;
        let s = &mut self.split;
        for number in 0..s.palettes.len() {
            if s.leader_owned.contains(&number) && !leader {
                continue;
            }
            let mut union = s.palettes[number].clone();
            union.extend(palette.iter().filter(|c| !s.palettes[number].contains(c)));
            if union.len() <= OBJ_COLORS {
                s.palettes[number] = union;
                s.palette_of.set(key.clone(), number);
                return Ok(true);
            }
        }
        if force || s.palettes.len() < self.ask.cap {
            if leader {
                s.leader_owned.insert(s.palettes.len());
            }
            s.palette_of.set(key.clone(), s.palettes.len());
            s.palettes.push(palette);
            return Ok(true);
        }
        let counts = sprite_colors(image, key.1, None);
        let mut best: Option<(u64, usize)> = None;
        for (number, existing) in s.palettes.iter().enumerate() {
            if s.leader_owned.contains(&number) {
                continue; // the console overwrites those with the leader's
            }
            let cost: u64 = counts.iter().filter(|(c, _)| !existing.contains(c)).map(|(_, n)| n).sum();
            if best.is_none_or(|(b, _)| cost < b) {
                best = Some((cost, number));
            }
        }
        let Some((_, number)) = best else {
            return Ok(false);
        };
        s.palette_of.set(key.clone(), number);
        s.lent.insert(key.clone());
        Ok(true)
    }
}

/// The map's events that are drawn —every one with a CharSet, and those
/// drawn with a tile **that fit**— and how the palettes are split.
///
/// First the leader candidates, then the events with a CharSet —the ones
/// that weigh first, the rest in map order—, then the graphics routes
/// change to, the timer's colours, and last the tiles, each one while it
/// fits. A tile left out is not drawn, but its event is still there: it
/// blocks and triggers all the same.
///
/// The leader candidates **share one palette**, because one leads at a
/// time: the console uploads the colours of whoever leads. Except the one
/// that is also an event of this map, which gets its own: its row uses it
/// at the same time as the hero. And nobody else goes into a leader's
/// palette: a flash of the hero is a tint of its palette, and would tint
/// whoever shared it.
pub fn drawable_npcs(ask: &Ask, npcs: Vec<Npc>) -> Result<Drawable> {
    let mut sp = Splitter {
        ask,
        split: Split {
            poses: ask.poses.clone(),
            ..Split::default()
        },
    };
    let mut notes = Vec::new();

    let npc_keys: HashSet<Key> = npcs.iter().flat_map(Npc::keys).collect();
    let mut seen: HashSet<Key> = HashSet::new();
    let mut slot_leader: Option<usize> = None;
    for key in ask.leaders {
        if seen.contains(key) || sprite_colors(sheet(ask.sheets, &key.0)?, key.1, None).is_empty() {
            continue;
        }
        seen.insert(key.clone());
        if npc_keys.contains(key) || slot_leader.is_none() {
            sp.fits(key, true, true)?;
            if !npc_keys.contains(key) {
                slot_leader = sp.split.palette_of.get(key);
            }
        } else {
            sp.split.palette_of.set(key.clone(), slot_leader.unwrap_or(0));
            sp.split.own.insert(key.clone());
        }
    }

    // The CharSets of the pages, in map order except the ones that weigh.
    let mut by_weight: Vec<&Npc> = npcs.iter().collect();
    by_weight.sort_by_key(|n| -weight(ask.weights, &n.charset));
    for npc in by_weight {
        for key in npc.keys() {
            if !seen.contains(&key) && !key.0.starts_with(TILE_PREFIX) {
                seen.insert(key.clone());
                sp.fits(&key, false, false)?;
            }
        }
    }
    // The graphics of command 34, while they fit; a transparent one asks
    // for nothing.
    for key in ask.route_graphics {
        if !seen.contains(key) && !sprite_colors(sheet(ask.sheets, &key.0)?, key.1, None).is_empty() {
            seen.insert(key.clone());
            sp.fits(key, false, false)?;
        }
    }
    // The timer before the tiles: it is on screen always, and a tile goes
    // in only while it fits.
    if !ask.timer_colors.is_empty() {
        let s = &mut sp.split;
        for number in 0..s.palettes.len() {
            if s.leader_owned.contains(&number) {
                continue;
            }
            let mut union = s.palettes[number].clone();
            union.extend(ask.timer_colors.iter().filter(|c| !s.palettes[number].contains(c)));
            if union.len() <= OBJ_COLORS {
                s.palettes[number] = union;
                break;
            }
        }
    }

    let mut fit: HashSet<Key> = HashSet::new();
    let mut outside: HashSet<Key> = HashSet::new();
    let mut out = Vec::new();
    let mut discarded = Vec::new();
    for mut npc in npcs {
        for key in npc.keys() {
            if seen.contains(&key) || fit.contains(&key) || outside.contains(&key) {
                continue;
            }
            if sp.fits(&key, false, false)? {
                fit.insert(key);
            } else {
                outside.insert(key);
            }
        }
        npc.outside = npc.keys().into_iter().filter(|k| outside.contains(k)).collect();
        discarded.extend(npc.outside.iter().map(|k| (npc.event, k.0.clone())));
        if outside.contains(&(npc.charset.clone(), npc.index)) {
            npc.visible = false;
            npc.tile_pass = None;
            if !npc.changes {
                continue;
            }
            // The row stays for the other pages, hidden, with the fields of
            // the first of them that fits.
            let other = npc
                .graphics
                .iter()
                .flatten()
                .find(|g| !outside.contains(&(g.0.clone(), g.1)))
                .cloned();
            let Some((name, index, pose)) = other else {
                continue;
            };
            npc.charset = name;
            npc.index = index;
            npc.pose = pose;
        }
        out.push(npc);
    }

    // And last, the timer, if it has nowhere to go: not a palette with room
    // nor a free one. Then a character of a palette of its own loses a
    // colour, the one that moves the fewest pixels —the ones in another map
    // of the cartridge last: the pose bank is the cartridge's—.
    let s = &mut sp.split;
    if !ask.timer_colors.is_empty()
        && s.palettes.len() >= OBJ_PALETTES
        && !s.palettes.iter().enumerate().any(|(n, p)| {
            !s.leader_owned.contains(&n) && {
                let union: HashSet<&Color> = p.iter().chain(ask.timer_colors).collect();
                union.len() <= OBJ_COLORS
            }
        })
    {
        let mut singles: HashMap<usize, usize> = HashMap::new();
        for (_, n) in s.palette_of.iter() {
            *singles.entry(n).or_default() += 1;
        }
        type Cost = (bool, f64, Key);
        let mut best: Option<(Cost, Key, usize, usize, Vec<Color>)> = None;
        for (key, n) in s.palette_of.iter() {
            if s.leader_owned.contains(&n) || singles[&n] != 1 || key.0.starts_with(TILE_PREFIX) {
                continue;
            }
            let foreign = !ask.only_here.contains(key);
            let counts = sprite_colors(sheet(ask.sheets, &key.0)?, key.1, ask.poses.get(key));
            if counts.is_empty() {
                continue;
            }
            let missing = ask.timer_colors.iter().filter(|c| !s.palettes[n].contains(c)).count();
            let new_cap = OBJ_COLORS - missing;
            let merged = merge_least_visible(&counts, new_cap)?;
            let moved: u64 = counts
                .iter()
                .zip(&merged.mapping)
                .filter(|((c, _), m)| c != *m)
                .map(|((_, v), _)| v)
                .sum();
            let total: u64 = counts.iter().map(|(_, v)| v).sum();
            let cost: Cost = (foreign, moved as f64 / total as f64, key.clone());
            let better = match &best {
                None => true,
                Some((b, ..)) => cost.partial_cmp(b) == Some(std::cmp::Ordering::Less),
            };
            if better {
                let palette: BTreeSet<Color> = merged.mapping.iter().copied().collect();
                best = Some((cost, key.clone(), n, new_cap, palette.into_iter().collect()));
            }
        }
        if let Some(((foreign, ratio, _), key, n, new_cap, palette)) = best {
            notes.push(format!(
                "  to make room for the timer, {}:{} drops to {} colors ({:.2}% of its pixels){}",
                key.0,
                key.1,
                new_cap,
                100.0 * ratio,
                if foreign { ", and with a pose bank of its own" } else { "" }
            ));
            s.palettes[n] = palette;
            s.caps.insert(key, new_cap);
        }
    }

    Ok(Drawable {
        npcs: out,
        discarded,
        split: sp.split,
        notes,
    })
}
