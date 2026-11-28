//! How the eight object palettes are split among a map's characters, and
//! which events drawn with a tile get drawn at all.

use crate::sprites::character::{
    character_palette, nearest, sheet, sprite_colors, Key, Sheets, OBJ_COLORS, OBJ_PALETTES,
};
use crate::sprites::fail::{Bad, Result};
use crate::sprites::npc::Npc;
use adeleine::{lab_distance, merge_least_visible, Color};
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
    /// The leader candidates that are also an event of this map and found
    /// no palette of their own: they went into one of the map's like any
    /// other character, and when one of them leads the console uploads that
    /// palette's colours, which are already there. A flash of the hero would
    /// tint whoever shares it, but a map where something flashes the hero
    /// has no such leaders: the converter gives those events a copy of the
    /// graphic, which is not a leader's (`separate_from_hero`).
    pub shared_leaders: BTreeSet<Key>,
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
    /// Those of them only the hero shows.
    pub hero_graphics: &'a BTreeSet<Key>,
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
    /// Who fits in no palette, in the order they came: see `lend`.
    pending: Vec<Key>,
}

impl Splitter<'_> {
    /// Whether the character's colours go into a palette there already is
    /// —a leader's too— without passing fifteen.
    fn merges(&self, key: &Key) -> Result<bool> {
        let image = sheet(self.ask.sheets, &key.0)?;
        let (palette, _, _) = character_palette(image, key.1, None, self.ask.poses.get(key))?;
        Ok(self.split.palettes.iter().any(|existing| {
            existing.len() + palette.iter().filter(|c| !existing.contains(c)).count() <= OBJ_COLORS
        }))
    }

    /// The first palette the character's colours fit in; a new one if there
    /// is room or it is `force`d; and otherwise **someone else's**, the one
    /// it is drawn nearest with. A character with odd colours is a
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
        // Someone else's. Which one is decided by `lend`, at the end, when
        // the palettes have every colour they are going to have: one that
        // looked far now can take, later, the colours that bring it near.
        if !s
            .palettes
            .iter()
            .enumerate()
            .any(|(n, p)| !s.leader_owned.contains(&n) && !p.is_empty())
        {
            return Ok(false); // the console overwrites the leaders' with theirs
        }
        s.lent.insert(key.clone());
        self.pending.push(key.clone());
        Ok(true)
    }

    /// Gives each character that fits in no palette someone else's: the one
    /// it is drawn nearest with.
    ///
    /// What a palette costs is what the screen shows: each pixel of the
    /// poses the map shows, times how far its colour lands —its own
    /// palette's, or the nearest of the lent one, which is how the bank
    /// draws it—. How far, and not its square as a merge counts it: with
    /// the square, a palette that drew a few pixels very far lost to one
    /// that drew all of them a little off, and over the maps that lend in
    /// every game more characters came out worse (see "The palette a
    /// character is lent" in the book).
    ///
    /// Until 2026-10-17 it was how many pixels of all twelve poses missed,
    /// however near or far they went, and it was decided with the palettes
    /// as they were when the character's turn came: map 38 of A Blurred
    /// Line lent a chest of greys the browns' palette, because the other
    /// objects of its block, which the map never shows, missed fewer pixels
    /// there.
    fn lend(&mut self) -> Result<()> {
        for key in std::mem::take(&mut self.pending) {
            let image = sheet(self.ask.sheets, &key.0)?;
            let (_, _, mapping) = character_palette(image, key.1, None, self.ask.poses.get(&key))?;
            let counts = sprite_colors(image, key.1, self.ask.poses.get(&key));
            let s = &mut self.split;
            let mut best: Option<(u64, usize)> = None;
            for (number, existing) in s.palettes.iter().enumerate() {
                if s.leader_owned.contains(&number) || existing.is_empty() {
                    continue;
                }
                let cost: u64 = counts
                    .iter()
                    .map(|(c, n)| {
                        let own = mapping[c];
                        let shown = if existing.contains(&own) {
                            own
                        } else {
                            nearest(existing, own)
                        };
                        n * (lab_distance(*c, shown) as u64).isqrt()
                    })
                    .sum();
                if best.is_none_or(|(b, _)| cost < b) {
                    best = Some((cost, number));
                }
            }
            if let Some((_, number)) = best {
                s.palette_of.set(key, number);
            }
        }
        Ok(())
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
///
/// A leader that is also an event gets its own **while one is left for the
/// rest**: a map that shows several of the leader candidates as events
/// —Dooms 2's map 1, where they are chosen— would otherwise give all eight
/// palettes to leaders and leave the other events with none. The ones that
/// do not get one are split later, with the events: see `shared_leaders`.
pub fn drawable_npcs(ask: &Ask, npcs: Vec<Npc>) -> Result<Drawable> {
    let mut sp = Splitter {
        ask,
        split: Split {
            poses: ask.poses.clone(),
            ..Split::default()
        },
        pending: Vec::new(),
    };
    let mut notes = Vec::new();

    let npc_keys: HashSet<Key> = npcs.iter().flat_map(Npc::keys).collect();
    // The ones some page draws: a row only a route dresses waits for the
    // routes' graphics, after these. See `Npc::dressed`.
    let page_keys: HashSet<Key> = npcs
        .iter()
        .filter(|n| !n.dressed())
        .flat_map(Npc::keys)
        .collect();
    let mut seen: HashSet<Key> = HashSet::new();
    let mut slot_leader: Option<usize> = None;
    for key in ask.leaders {
        if seen.contains(key) || sprite_colors(sheet(ask.sheets, &key.0)?, key.1, None).is_empty() {
            continue;
        }
        // A leader that only a route dresses as an event —the party walking
        // in a scene, The Book of Three's map 64— does not take a palette of
        // its own before the map's characters: it goes with the routes'
        // graphics, while they fit, and shares like the leaders that do not
        // get one.
        if npc_keys.contains(key) && !page_keys.contains(key) {
            sp.split.shared_leaders.insert(key.clone());
            continue;
        }
        // Room for the rest: one palette for the other events. Only if it
        // asks for a new one: a leader whose colours go into another
        // leader's costs nothing.
        if npc_keys.contains(key) && sp.split.palettes.len() + 1 >= ask.cap && !sp.merges(key)? {
            sp.split.shared_leaders.insert(key.clone());
            continue;
        }
        seen.insert(key.clone());
        if npc_keys.contains(key) || slot_leader.is_none() {
            sp.fits(key, true, true)?;
            if !npc_keys.contains(key) {
                slot_leader = sp.split.palette_of.get(key);
            }
        } else {
            sp.split
                .palette_of
                .set(key.clone(), slot_leader.unwrap_or(0));
            sp.split.own.insert(key.clone());
        }
    }

    // The graphics only the hero shows —a `ChangeSpriteAssociation`'s, a
    // route's on the hero— are a leader's other looks, and they go like the
    // leaders that share the slot: in its palette, with colours of their
    // own that the console uploads when the hero takes them. That way they
    // take no palette from the map, and their pose bank is the same in every
    // map: drawn with someone else's palette, each map quantized it its own
    // way, and the cartridge carried one bank per map. Not one an event of
    // the map also draws, which needs its colours in the map's palette.
    if let Some(slot) = slot_leader {
        for key in ask.route_graphics {
            if !ask.hero_graphics.contains(key)
                || seen.contains(key)
                || npc_keys.contains(key)
                || key.0.starts_with(TILE_PREFIX)
                || sprite_colors(sheet(ask.sheets, &key.0)?, key.1, None).is_empty()
            {
                continue;
            }
            seen.insert(key.clone());
            sp.split.palette_of.set(key.clone(), slot);
            sp.split.own.insert(key.clone());
        }
    }

    // The CharSets of the pages, in map order except the ones that weigh.
    // Not a row only a route dresses: its graphic goes with the routes', after
    // these. On The Book of Three's map 64 five of them took Monster1's
    // palette, and the soldiers that stand there the whole race were drawn
    // pale with someone else's.
    let mut by_weight: Vec<&Npc> = npcs.iter().filter(|n| !n.dressed()).collect();
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
        if !seen.contains(key) && !sprite_colors(sheet(ask.sheets, &key.0)?, key.1, None).is_empty()
        {
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
            union.extend(
                ask.timer_colors
                    .iter()
                    .filter(|c| !s.palettes[number].contains(c)),
            );
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
        npc.outside = npc
            .keys()
            .into_iter()
            .filter(|k| outside.contains(k))
            .collect();
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

    // Everyone has a place but those lent one: theirs now, with every
    // palette whole. Before the timer's room, which counts who shares each.
    sp.lend()?;

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
            let missing = ask
                .timer_colors
                .iter()
                .filter(|c| !s.palettes[n].contains(c))
                .count();
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
                if foreign {
                    ", and with a pose bank of its own"
                } else {
                    ""
                }
            ));
            s.palettes[n] = palette;
            s.caps.insert(key, new_cap);
        }
    }

    hold(ask, &sp.split)?;
    Ok(Drawable {
        npcs: out,
        discarded,
        split: sp.split,
        notes,
    })
}

/// What [`join_two`] did: the characters of the two palettes that became one,
/// and what the screen loses for it.
#[derive(Debug, Clone, PartialEq)]
pub struct Joined {
    /// The characters of the palette that stays, and of the one that went
    /// into it.
    pub kept: Vec<Key>,
    pub joined: Vec<Key>,
    /// How many distinct colours the two had together, past the fifteen a
    /// palette holds: the ones lost.
    pub colors_lost: usize,
    /// Of the pixels of their poses the map shows, how many are drawn in
    /// another colour than before, and of how many.
    pub moved: u64,
    pub total: u64,
}

/// Each character of `members` with the pixels of the poses the map shows,
/// by colour, and the colour each is drawn in with `palette` —its own
/// quantized one if the palette has it, the nearest otherwise, as
/// `build_characters` draws it—.
fn shown(ask: &Ask, members: &[Key], palette: &[Color]) -> Result<Vec<(Color, u64, Color)>> {
    let mut out = Vec::new();
    for key in members {
        let image = sheet(ask.sheets, &key.0)?;
        let poses = ask.poses.get(key);
        let (_, _, mapping) = character_palette(image, key.1, None, poses)?;
        for (c, n) in sprite_colors(image, key.1, poses) {
            let own = mapping[&c];
            let drawn = if palette.contains(&own) {
                own
            } else {
                nearest(palette, own)
            };
            out.push((c, n, drawn));
        }
    }
    Ok(out)
}

/// What drawing those pixels that way costs, as [`Splitter::lend`] counts
/// it: each pixel times how far its colour lands.
fn cost(pixels: &[(Color, u64, Color)]) -> u64 {
    pixels
        .iter()
        .map(|&(c, n, drawn)| n * (lab_distance(c, drawn) as u64).isqrt())
        .sum()
}

/// Makes two of the map's palettes one, to leave one free for something
/// that needs a whole one —an inn's gold window, see `arrow_obj` in
/// rm2k-snes-mapdata—: of every pair it can join, **the one that loses
/// least**, counted as [`Splitter::lend`] counts a lent palette, over the
/// pixels the map shows. The fifteen colours of the pair are the ones
/// Adeleine's merge keeps of both, weighed by those pixels, and each of
/// their characters is drawn with the nearest of them.
///
/// Not a leader's palette, which the console overwrites; nor one with a
/// character in `keep` —baked into the background, whose tiles keep its
/// colours—, nor one brought below fifteen for the timer, nor one with a
/// colour no character of it draws —the timer's—. `None` when no pair is
/// left.
///
/// The palette past the joined one moves down one, so the numbers stay
/// contiguous: the characters keep their colours, not their number.
pub fn join_two(ask: &Ask, split: &mut Split, keep: &BTreeSet<Key>) -> Result<Option<Joined>> {
    let mut members: Vec<Vec<Key>> = vec![Vec::new(); split.palettes.len()];
    for (key, n) in split.palette_of.iter() {
        if !split.own.contains(key) {
            members[n].push(key.clone());
        }
    }
    // Each candidate's pixels by the colour its palette draws them in.
    let mut weights: BTreeMap<usize, BTreeMap<Color, u64>> = BTreeMap::new();
    for (n, palette) in split.palettes.iter().enumerate() {
        let who = &members[n];
        if split.leader_owned.contains(&n)
            || who.is_empty()
            || who
                .iter()
                .any(|k| keep.contains(k) || split.caps.contains_key(k))
        {
            continue;
        }
        let mut w: BTreeMap<Color, u64> = BTreeMap::new();
        for (_, count, drawn) in shown(ask, who, palette)? {
            *w.entry(drawn).or_default() += count;
        }
        if palette.iter().all(|c| w.get(c).is_some_and(|&v| v > 0)) {
            weights.insert(n, w);
        }
    }
    let numbers: Vec<usize> = weights.keys().copied().collect();
    let mut best: Option<(u64, usize, usize, Vec<Color>, usize)> = None;
    for (a, &i) in numbers.iter().enumerate() {
        for &j in &numbers[a + 1..] {
            let mut both = weights[&i].clone();
            for (c, v) in &weights[&j] {
                *both.entry(*c).or_default() += v;
            }
            let counts: Vec<(Color, u64)> = both.into_iter().collect();
            let palette: Vec<Color> = if counts.len() <= OBJ_COLORS {
                counts.iter().map(|&(c, _)| c).collect()
            } else {
                let merged = merge_least_visible(&counts, OBJ_COLORS)?;
                let set: BTreeSet<Color> = merged.mapping.into_iter().collect();
                set.into_iter().collect()
            };
            let who: Vec<Key> = members[i].iter().chain(&members[j]).cloned().collect();
            let before = cost(&shown(ask, &members[i], &split.palettes[i])?)
                + cost(&shown(ask, &members[j], &split.palettes[j])?);
            let after = cost(&shown(ask, &who, &palette)?);
            let delta = after.saturating_sub(before);
            if best.as_ref().is_none_or(|b| delta < b.0) {
                let lost = counts.len().saturating_sub(OBJ_COLORS);
                best = Some((delta, i, j, palette, lost));
            }
        }
    }
    let Some((_, i, j, palette, colors_lost)) = best else {
        return Ok(None);
    };
    let old: Vec<(Color, u64, Color)> = shown(ask, &members[i], &split.palettes[i])?
        .into_iter()
        .chain(shown(ask, &members[j], &split.palettes[j])?)
        .collect();
    let who: Vec<Key> = members[i].iter().chain(&members[j]).cloned().collect();
    let new = shown(ask, &who, &palette)?;
    let moved = old
        .iter()
        .zip(&new)
        .filter(|(o, n)| o.2 != n.2)
        .map(|(o, _)| o.1)
        .sum();
    let total = old.iter().map(|o| o.1).sum();
    split.palettes[i] = palette;
    split.palettes.remove(j);
    let renumbered: Vec<(Key, usize)> = split
        .palette_of
        .iter()
        .map(|(k, n)| {
            let n = match n {
                n if n == j => i,
                n if n > j => n - 1,
                n => n,
            };
            (k.clone(), n)
        })
        .collect();
    for (k, n) in renumbered {
        split.palette_of.set(k, n);
    }
    split.leader_owned = split
        .leader_owned
        .iter()
        .map(|&n| if n > j { n - 1 } else { n })
        .collect();
    Ok(Some(Joined {
        kept: members[i].clone(),
        joined: members[j].clone(),
        colors_lost,
        moved,
        total,
    }))
}

/// Stops if anyone but a leader candidate —or a look only the hero shows—
/// went into a leader's palette. It is a bug in the split, not a limit of
/// the map, so there is no loss to declare.
///
/// A flash of the hero is a tint of its palette —`paint_flash` in the
/// runtime—, so whoever shares it flashes with them, which RM2k does not
/// do: taro saw two tiles above some chests turn red with Talan in A
/// Blurred Line's Emitter Room. No capture shows it unless a case puts a
/// second sprite beside the one that flashes, so it is checked at every
/// build. Until 2026-11-25 it was that game's
/// `tests/tooling/test_flash_palette.py`, over three of its maps.
///
/// The leaders a map splits with the rest —`shared_leaders`— are not
/// looked at: they are in a palette of the map on purpose, and the
/// converter keeps them off the maps where something flashes the hero.
fn hold(ask: &Ask, split: &Split) -> Result<()> {
    for (key, number) in split.palette_of.iter() {
        if split.leader_owned.contains(&number)
            && !ask.leaders.contains(key)
            && !split.own.contains(key)
        {
            return Err(Bad::new(format!(
                "the split put {}:{} in palette {number}, which is a leader's: when the hero \
                 flashes, it would flash with them",
                key.0, key.1
            )));
        }
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use rm2k_render::Picture;

    /// A sheet of eight characters, each drawing `colours[k]` in stripes
    /// over every pose, in 5-bit colour.
    fn sheet_of(colours: &[Vec<Color>]) -> Picture {
        let mut picture = Picture::transparent(288, 256);
        for (k, palette) in colours.iter().enumerate() {
            let (ox, oy) = ((k % 4) * 72, (k / 4) * 128);
            for y in 0..128 {
                for x in 0..72 {
                    let c = palette[(x + y) % palette.len()];
                    let at = ((oy + y) * 288 + ox + x) * 4;
                    picture.rgba[at..at + 4].copy_from_slice(&[
                        c[0] << 3,
                        c[1] << 3,
                        c[2] << 3,
                        255,
                    ]);
                }
            }
        }
        picture
    }

    /// Fifteen colours of a ramp of one hue, from dark to full.
    fn ramp(hue: Color) -> Vec<Color> {
        (1..16u16)
            .map(|i| hue.map(|h| (u16::from(h) * i / 15) as u8))
            .collect()
    }

    /// Each of the eight characters in a palette of its own.
    fn one_each(sheets: &Sheets) -> Split {
        let mut split = Split::default();
        for k in 0..8 {
            let image = sheet(sheets, "C").unwrap();
            let (palette, _, _) = character_palette(image, k, None, None).unwrap();
            split.palette_of.set(("C".to_string(), k), k as usize);
            split.palettes.push(palette);
        }
        split
    }

    #[test]
    fn two_palettes_join_where_they_lose_least() {
        // 6 is 2 with its two lightest colours a step off: theirs is the
        // pair that loses least.
        let mut near = ramp([0, 0, 31]);
        near[13][0] = 1;
        near[14][0] = 1;
        let colours: Vec<Vec<Color>> = vec![
            ramp([31, 0, 0]),
            ramp([0, 31, 0]),
            ramp([0, 0, 31]),
            ramp([31, 31, 0]),
            ramp([31, 0, 31]),
            ramp([0, 31, 31]),
            near,
            ramp([31, 31, 31]),
        ];
        let sheets: Sheets = HashMap::from([("C".to_string(), Some(sheet_of(&colours)))]);
        let poses = BTreeMap::new();
        let leaders = [("C".to_string(), 0)];
        let (hero, here, weights) = (BTreeSet::new(), HashSet::new(), BTreeMap::new());
        let ask = Ask {
            sheets: &sheets,
            leaders: &leaders,
            cap: OBJ_PALETTES,
            route_graphics: &[],
            hero_graphics: &hero,
            timer_colors: &[],
            only_here: &here,
            poses: &poses,
            weights: &weights,
        };
        let c = |k: i32| ("C".to_string(), k);

        // Character 0 leads: its palette is never joined.
        let mut split = one_each(&sheets);
        split.leader_owned.insert(0);
        let joined = join_two(&ask, &mut split, &BTreeSet::new())
            .unwrap()
            .unwrap();
        assert_eq!(
            (joined.kept.clone(), joined.joined.clone()),
            (vec![c(2)], vec![c(6)])
        );
        assert_eq!(joined.colors_lost, 2);
        assert!(
            joined.moved > 0 && joined.moved < joined.total,
            "{joined:?}"
        );
        assert_eq!(split.palettes.len(), 7);
        assert!(split.palettes[2].len() <= OBJ_COLORS);
        assert_eq!(split.palette_of.get(&c(6)), Some(2));
        assert_eq!(split.palette_of.get(&c(7)), Some(6));
        assert_eq!(split.leader_owned, BTreeSet::from([0]));

        // Baked into the background, 2 keeps its palette: another pair
        // joins, and loses more.
        let mut again = one_each(&sheets);
        let other = join_two(&ask, &mut again, &BTreeSet::from([c(2)]))
            .unwrap()
            .unwrap();
        assert!(!other.kept.contains(&c(2)) && !other.joined.contains(&c(2)));
        assert!(other.moved > joined.moved, "{other:?} against {joined:?}");
    }
}
