//! The shared sample bank: one sample per General MIDI program and one per
//! percussion hit in the whole cartridge, each with the budget of its worst
//! package, and the copies that keep a song from paying for a package it is
//! not in.

use crate::fail::{Bad, Result};
use crate::midi;
use crate::num;
use crate::samples::{SoundFontSamples, Voice, Zone, REFERENCE_KEY};
use crate::song::Parsed;
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::fmt;
use std::rc::Rc;

/// Where the samples go: from $0400 to the end of the 64 KB, with no
/// reservation: echo is off and the SPC700's stack lives at $0100, below.
pub const SAMPLES_ADDR: i64 = 0x0400;
/// How far uploads go: the last 64 bytes of the ARAM are the ones the boot
/// ROM covers when it is enabled, and that way the limit fits in sixteen
/// bits.
pub const ARAM_END: i64 = 0x10000 - 64;
/// What is left free for each package when allocating: each sample's length
/// is rounded up to BRR blocks and the allocation asks by budget, so this is
/// slack for that; [`Bank::new`] checks what they really take against the
/// ARAM with no margin.
pub const ARAM_MARGIN: i64 = 1024;
/// The silence: a BRR block with the end and loop bits, and eight zero
/// bytes. It is where every sample that is not in the ARAM points.
pub const SILENCE: [u8; 9] = [0x03, 0, 0, 0, 0, 0, 0, 0, 0];
/// SRCN is one byte and the ROM's sample lists end with $FF, so the
/// directory goes up to 255 entries: the music's samples and the sound
/// effect places together.
pub const DIRECTORY_MAX: i64 = 255;
/// Leaves out of every song's keys the ones that do not fit in `room`
/// directory entries: it keeps the ones the most songs use, and among those
/// the first in key order, so the answer is the same every run. Returns
/// what it dropped. A dropped key is not in any song's set, which is how a
/// key the SoundFont lacks looks: its notes stay silent and nothing points
/// at a sample that is not there.
pub fn drop_surplus(keys_of: &mut [BTreeSet<Key>], room: i64) -> Vec<Key> {
    let mut uses: BTreeMap<Key, usize> = BTreeMap::new();
    for ks in keys_of.iter() {
        for k in ks {
            *uses.entry(k.clone()).or_default() += 1;
        }
    }
    let room = room.max(0) as usize;
    if uses.len() <= room {
        return Vec::new();
    }
    let mut ranked: Vec<(Key, usize)> = uses.into_iter().collect();
    ranked.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| a.0.cmp(&b.0)));
    let dropped: Vec<Key> = ranked.split_off(room).into_iter().map(|(k, _)| k).collect();
    for ks in keys_of.iter_mut() {
        ks.retain(|k| !dropped.contains(k));
    }
    dropped
}

/// A budget nobody reaches: with it, each sample comes out at the
/// SoundFont's rate —capped at the maximum—, which is what it would weigh
/// untrimmed.
pub const NATIVE: i64 = 1 << 24;
/// The minimum a sample is given even when its package is full.
pub const FLOOR: i64 = 256;
/// No copy is made for a sample that already plays at nearly its rate: a
/// directory entry is worth more than that.
const COPY_UNTIL: f64 = 0.9;

/// A sample of the bank: a melodic program at the key that picks its zone,
/// or a percussion hit; and, for a copy, the groups it was copied for.
///
/// The order is the one the bank numbers them in: hits after programs —`g`
/// before `p`, but the bank puts the programs first—, each by number, and a
/// copy right after what it copies.
#[derive(Clone, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub struct Key {
    /// `b'g'` for a hit, `b'p'` for a program.
    kind: u8,
    number: u8,
    /// The key that picks the zone; 0 for a hit.
    root: u8,
    copies: Vec<String>,
}

impl Key {
    pub fn program(program: u8, key: u8) -> Key {
        Key { kind: b'p', number: program, root: key, copies: Vec::new() }
    }

    pub fn hit(key: u8) -> Key {
        Key { kind: b'g', number: key, root: 0, copies: Vec::new() }
    }

    pub fn is_hit(&self) -> bool {
        self.kind == b'g'
    }

    /// The program, or the hit's key.
    pub fn number(&self) -> u8 {
        self.number
    }

    /// Whether it is a copy of another.
    pub fn is_copy(&self) -> bool {
        !self.copies.is_empty()
    }

    /// The same sample, for the songs of group `name`.
    pub fn copy_for(&self, name: &str) -> Key {
        let mut k = self.clone();
        k.copies.push(format!("@{name}"));
        k
    }

    /// Whether `other` is this key or a copy of it.
    pub fn is_prefix_of(&self, other: &Key) -> bool {
        self.kind == other.kind
            && self.number == other.number
            && self.root == other.root
            && other.copies.starts_with(&self.copies)
    }

    /// Parses what `Display` writes.
    pub fn parse(text: &str) -> Option<Key> {
        let mut parts = text.split('@');
        let head = parts.next()?;
        let copies: Vec<String> = parts.map(|p| format!("@{p}")).collect();
        let fields: Vec<&str> = head.split(':').collect();
        let mut key = match fields.as_slice() {
            ["p", program, root] => Key::program(program.parse().ok()?, root.parse().ok()?),
            ["g", hit] => Key::hit(hit.parse().ok()?),
            _ => return None,
        };
        key.copies = copies;
        Some(key)
    }
}

/// `p:0:60` for program 0 at key 60, `g:36` for hit 36, and a copy with the
/// names of its groups after an `@` each: `p:0:60@3`.
impl fmt::Display for Key {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        if self.is_hit() {
            write!(f, "g:{}", self.number)?;
        } else {
            write!(f, "p:{}:{}", self.number, self.root)?;
        }
        for c in &self.copies {
            f.write_str(c)?;
        }
        Ok(())
    }
}

/// The SoundFont's samples, by key.
pub struct Samples {
    pub font: SoundFontSamples,
}

impl Samples {
    /// A key's voice with that budget in BRR bytes, or None if the
    /// SoundFont does not have it.
    pub fn sample(&self, key: &Key, budget: i64) -> Result<Option<Rc<Voice>>> {
        if key.is_hit() {
            self.font.drum(key.number, budget)
        } else {
            self.font.voice(key.number, budget, key.root)
        }
    }

    fn native(&self, key: &Key) -> Result<Rc<Voice>> {
        self.sample(key, NATIVE)?
            .ok_or_else(|| Bad::answer(format!("the SoundFont has no {key}")))
    }

    /// (ADSR1, ADSR2, release GAIN) of a melodic note: the envelope of the
    /// SoundFont zone covering the key.
    ///
    /// The zone may not be the sample's —each program carries only one, the
    /// one from [`most_used_zones`]—, and that is on purpose: it is the
    /// envelope the SoundFont would give that key, and on a piano the decay
    /// changes key by key. If no zone covers the key, middle C's.
    pub fn envelope(&self, program: u8, key: u8) -> Result<(u8, u8, u8)> {
        let found = self
            .font
            .envelope(program, key)
            .or_else(|| self.font.envelope(program, REFERENCE_KEY))
            .ok_or_else(|| Bad::answer(format!("the SoundFont has no envelope for program {program}")))?;
        Ok(crate::sdsp::envelope(&found, key as i64))
    }
}

/// The samples a song asks for: `root_keys` are the ones from
/// [`most_used_zones`]; without one, middle C.
pub fn song_keys(parsed: Option<&Parsed>, root_keys: &BTreeMap<u8, u8>) -> BTreeSet<Key> {
    let Some(parsed) = parsed else { return BTreeSet::new() };
    let mut keys: BTreeSet<Key> = parsed
        .melodic()
        .into_iter()
        .map(|p| Key::program(p, *root_keys.get(&p).unwrap_or(&REFERENCE_KEY)))
        .collect();
    keys.extend(parsed.hits().into_iter().map(Key::hit));
    keys
}

/// {program: key}: which key each program's sample is requested with,
/// which is what picks the SoundFont zone.
///
/// **The zone where the whole cartridge plays the most note-time of that
/// program**, and not middle C's. A sample sounds good near its root: far
/// from it, the DSP stretches or squeezes it and you can hear it. Measured
/// on a whole game: a third of the melodic note-time played twelve
/// semitones or more from the root of the middle C sample, on keys for
/// which the SoundFont has another. It is one per program, so it costs no
/// ARAM; what it loses is that a program two songs play in different
/// registers is right for only one of them.
///
/// The key is that zone's root if the zone covers it —so two songs that
/// play the same zone ask for the same sample—, and if not, the key that
/// sounds the most inside the zone.
pub fn most_used_zones(songs: &[Option<Parsed>], font: &SoundFontSamples) -> BTreeMap<u8, u8> {
    let mut time_by_zone: BTreeMap<u8, BTreeMap<Zone, i64>> = BTreeMap::new();
    let mut inside: HashMap<(u8, Zone), BTreeMap<u8, i64>> = HashMap::new();
    for parsed in songs.iter().flatten() {
        for note in &parsed.notes {
            if note.channel == midi::DRUM_CHANNEL {
                continue;
            }
            let program = parsed.program(note.channel);
            let Some(zone) = font.zone(program, note.pitch) else { continue };
            *time_by_zone.entry(program).or_default().entry(zone.clone()).or_default() +=
                note.end - note.start;
            *inside.entry((program, zone)).or_default().entry(note.pitch).or_default() +=
                note.end - note.start;
        }
    }
    let mut root_keys = BTreeMap::new();
    for (program, by_zone) in time_by_zone {
        let zone = by_zone
            .iter()
            .max_by(|a, b| (a.1, a.0).cmp(&(b.1, b.0)))
            .map(|(z, _)| z.clone())
            .unwrap();
        let root = zone.1;
        if font.zone(program, root).as_ref() == Some(&zone) {
            root_keys.insert(program, root);
        } else {
            let amount = &inside[&(program, zone)];
            // The most played; on a tie, the lowest.
            let key = amount
                .iter()
                .max_by(|a, b| (a.1, -(*a.0 as i64)).cmp(&(b.1, -(*b.0 as i64))))
                .map(|(k, _)| *k)
                .unwrap();
            root_keys.insert(program, key);
        }
    }
    root_keys
}

/// A group of samples that has to fit together in `free` bytes.
#[derive(Clone, Debug)]
pub struct Constraint {
    pub name: String,
    pub keys: BTreeSet<Key>,
    pub free: i64,
}

/// Songs —indices— that have to fit together in the ARAM, with
/// `effect_bytes` of sound effects beside them: those of a package, a lone
/// exit song, or a package with the song that may be playing when it loads.
/// It is what the [`Constraint`]s come from: which sample each song plays
/// with is said by the assignment of [`copies`].
#[derive(Clone, Debug)]
pub struct Group {
    pub name: String,
    pub songs: Vec<usize>,
    pub effect_bytes: i64,
}

/// {base key: the sample it plays with}, one per song.
pub type Assignment = Vec<BTreeMap<Key, Key>>;

/// What is free for samples with `samples` of music and `effects` in the
/// directory: the ARAM from behind the directory and the silence up to
/// `aram_end`. Each directory entry is four bytes.
pub fn free_for(samples: i64, effects: i64, aram_end: i64) -> i64 {
    aram_end - (SAMPLES_ADDR + 4 * (samples + effects) + SILENCE.len() as i64)
}

/// The constraints for those groups, with the samples each song gets
/// according to `assignment`.
pub fn constraints_for(assignment: &Assignment, groups: &[Group], free: i64) -> Vec<Constraint> {
    let mut out = Vec::new();
    for g in groups {
        let keys: BTreeSet<Key> =
            g.songs.iter().flat_map(|&t| assignment[t].values().cloned()).collect();
        if !keys.is_empty() {
            out.push(Constraint { name: g.name.clone(), keys, free: free - g.effect_bytes });
        }
    }
    out
}

/// ({key: budget}, {key: constraint that limited it}): how much each sample
/// gets so that every constraint fits in its space minus `margin`.
///
/// It is progressive filling over the fraction of each sample's native
/// size: the fraction of all of them is raised together until some
/// constraint fills up, that one's samples are frozen, and it goes on with
/// the rest. That way a sample is limited by its **worst** package and not
/// by the whole bank, and the one with room to spare does not pay for the
/// one without. Whatever is in no constraint that fills up goes whole.
pub fn allocate(
    keys: &BTreeSet<Key>,
    constraints: &[Constraint],
    margin: i64,
    natives: &HashMap<Key, i64>,
) -> (BTreeMap<Key, i64>, BTreeMap<Key, String>) {
    let mut fraction: HashMap<&Key, f64> = HashMap::new();
    let mut limited_by: BTreeMap<Key, String> = BTreeMap::new();
    let mut free_voices: BTreeSet<&Key> = keys.iter().collect();
    let active: Vec<&Constraint> =
        constraints.iter().filter(|r| r.keys.iter().any(|k| free_voices.contains(k))).collect();
    // Each constraint's totals are kept up to date as samples freeze,
    // instead of summing them again on every pass: the copies allocate
    // thousands of times per conversion.
    let mut own: Vec<BTreeSet<&Key>> =
        active.iter().map(|r| r.keys.iter().filter(|k| free_voices.contains(k)).collect()).collect();
    let mut sums: Vec<i64> = own.iter().map(|s| s.iter().map(|k| natives[*k]).sum()).collect();
    let mut fixed = vec![0.0f64; active.len()];
    let mut where_: HashMap<&Key, Vec<usize>> = HashMap::new();
    for (i, s) in own.iter().enumerate() {
        for k in s {
            where_.entry(k).or_default().push(i);
        }
    }
    let mut alive: Vec<usize> = (0..active.len()).collect();
    while !free_voices.is_empty() && !alive.is_empty() {
        let mut worst: Option<(f64, usize)> = None;
        for &i in &alive {
            if own[i].is_empty() {
                continue;
            }
            let f = ((active[i].free - margin) as f64 - fixed[i]) / sums[i] as f64;
            if worst.is_none_or(|(w, _)| f < w) {
                worst = Some((f, i));
            }
        }
        let Some((worst, which)) = worst else { break };
        if worst >= 1.0 {
            break;
        }
        let level = worst.max(0.0);
        let frozen: Vec<&Key> = own[which].iter().copied().collect();
        for k in frozen {
            fraction.insert(k, level);
            limited_by.insert(k.clone(), active[which].name.clone());
            free_voices.remove(k);
            for &j in &where_[k] {
                fixed[j] += level * natives[k] as f64;
                sums[j] -= natives[k];
                own[j].remove(k);
            }
        }
        alive.retain(|&i| i != which);
    }
    let budget = keys
        .iter()
        .map(|k| {
            let f = *fraction.get(k).unwrap_or(&1.0);
            (k.clone(), ((f * natives[k] as f64) as i64).max(FLOOR))
        })
        .collect();
    (budget, limited_by)
}

/// Which sample each song plays each of its keys with. Almost always the
/// key itself —one sample per program and per hit in the whole cartridge—,
/// except for **the copies**.
///
/// A sample has to fit in every group it is in, so its rate is set by the
/// worst one, and the song that never plays there pays for it too: a map
/// with 43 KB of sound effects left the drums of every song at 10 kHz. A
/// copy is the same key as another sample, only for the songs of one group:
/// they stay the same, and the ones outside stop paying for a package they
/// are not in. One copy per song would be some 370 directory entries
/// against 255, so they are made in two rounds.
///
/// `effects` is how many directory entries the sound effects take today,
/// and `usual` how many they took when each had its own.
///
/// **The usual ones**, one at a time and **the worst first**: the sample
/// with the lowest fraction of its native size that has some song outside
/// the group limiting it, copied for the ones inside. Then the allocation is
/// redone, because the copy changes what each group takes, and it goes on
/// until the directory is full as it used to be —with `usual` entries for
/// the sound effects— or until none is left below `COPY_UNTIL`.
///
/// **The ones from the entries the sound effects freed up**: only those that
/// **do not lower the rate of any (song, key) pair** compared to how the
/// usual ones left it, and of those, the one that adds the most kHz across
/// all. Every possible copy —each key for the songs of each group it is
/// in— is tried against the floor, and it goes on until none adds anything
/// or the directory is full. This round allocates with the directory full,
/// even if it does not fill up: that way no copy costs anyone its four
/// bytes. And it allocates with `real`, the same groups with what their
/// sound effects really take: the whole ones the music does not pay for go
/// in what it leaves free, and a copy that goes up to its rate would fill
/// exactly that.
#[allow(clippy::too_many_arguments)]
pub fn copies(
    samples: &Samples,
    keys_of: &[BTreeSet<Key>],
    groups: &[Group],
    effects: i64,
    usual: i64,
    real: &[Group],
    aram_end: i64,
) -> Result<Assignment> {
    let cap = DIRECTORY_MAX;
    let until = COPY_UNTIL;
    let mut assignment: Assignment =
        keys_of.iter().map(|ks| ks.iter().map(|k| (k.clone(), k.clone())).collect()).collect();
    let mut natives: HashMap<Key, i64> = HashMap::new();
    let mut rates: HashMap<Key, f64> = HashMap::new();
    let native = |key: &Key, natives: &mut HashMap<Key, i64>, rates: &mut HashMap<Key, f64>| -> Result<i64> {
        if let Some(&n) = natives.get(key) {
            return Ok(n);
        }
        let voice = samples.native(key)?;
        natives.insert(key.clone(), voice.data.len() as i64);
        rates.insert(key.clone(), voice.rate / 1000.0);
        Ok(voice.data.len() as i64)
    };
    let users = |asg: &Assignment, key: &Key| -> Vec<usize> {
        asg.iter().enumerate().filter(|(_, a)| a.values().any(|v| v == key)).map(|(t, _)| t).collect()
    };
    let with_copy = |asg: &Assignment, key: &Key, copy: &Key, inside: &[usize]| -> Assignment {
        let mut new = asg.clone();
        for &t in inside {
            for v in new[t].values_mut() {
                if v == key {
                    *v = copy.clone();
                }
            }
        }
        new
    };
    let mut songs_of: HashMap<&str, BTreeSet<usize>> = HashMap::new();
    for g in groups {
        songs_of.insert(&g.name, g.songs.iter().copied().collect());
    }
    let all_keys = |asg: &Assignment| -> BTreeSet<Key> { asg.iter().flat_map(|a| a.values().cloned()).collect() };

    loop {
        let keys = all_keys(&assignment);
        if keys.len() as i64 + usual >= cap {
            break;
        }
        let rs = constraints_for(&assignment, groups, free_for(keys.len() as i64, usual, aram_end));
        for k in &keys {
            native(k, &mut natives, &mut rates)?;
        }
        let (budget, limited_by) = allocate(&keys, &rs, ARAM_MARGIN, &natives);
        // (fraction to three decimals, -outside, key, name, inside)
        let mut worst: Option<(f64, i64, Key, String, Vec<usize>)> = None;
        for (key, name) in &limited_by {
            let fraction = budget[key] as f64 / natives[key] as f64;
            if fraction >= until {
                continue;
            }
            let own = users(&assignment, key);
            let inside: Vec<usize> = own.iter().copied().filter(|t| songs_of[name.as_str()].contains(t)).collect();
            let outside = (own.len() - inside.len()) as i64;
            if inside.is_empty() || outside == 0 {
                continue;
            }
            let option = (num::round_to(fraction, 3), -outside, key.clone(), name.clone(), inside);
            let better = match &worst {
                None => true,
                Some(w) => {
                    (option.0, option.1, &option.2, &option.3, &option.4)
                        .partial_cmp(&(w.0, w.1, &w.2, &w.3, &w.4))
                        == Some(std::cmp::Ordering::Less)
                }
            };
            if better {
                worst = Some(option);
            }
        }
        let Some((_, _, key, name, inside)) = worst else { break };
        assignment = with_copy(&assignment, &key, &key.copy_for(&name), &inside);
    }

    let free = free_for(cap - effects, effects, aram_end);
    // (keys, budget, the kHz each song plays each key at)
    type Khz = (BTreeSet<Key>, BTreeMap<Key, i64>, Vec<BTreeMap<Key, f64>>);
    let khz = |asg: &Assignment, natives: &mut HashMap<Key, i64>, rates: &mut HashMap<Key, f64>| -> Result<Khz> {
        let keys = all_keys(asg);
        for k in &keys {
            native(k, natives, rates)?;
        }
        let (budget, _) = allocate(&keys, &constraints_for(asg, real, free), ARAM_MARGIN, natives);
        let raised = asg
            .iter()
            .map(|a| {
                a.iter()
                    .map(|(b, s)| (b.clone(), budget[s] as f64 / natives[s] as f64 * rates[s]))
                    .collect()
            })
            .collect();
        Ok((keys, budget, raised))
    };

    let (mut keys, mut budget, floor) = khz(&assignment, &mut natives, &mut rates)?;
    let mut current = floor.clone();
    // Trying all of them on every pass is thousands of allocations: they are
    // tried in the order of what they added the last time they were tried
    // —new ones first—, and the first one that, tried again, adds at least
    // what any of the following ones added is taken. That it lowers no one
    // is always checked on the spot.
    let mut bound: HashMap<(Key, Key, Vec<usize>), f64> = HashMap::new();
    while (keys.len() as i64) + effects < cap {
        let mut candidates: Vec<(Key, Key, Vec<usize>)> = Vec::new();
        for key in &keys {
            if budget[key] as f64 >= until * natives[key] as f64 {
                continue;
            }
            let own = users(&assignment, key);
            for g in groups {
                let inside: Vec<usize> =
                    own.iter().copied().filter(|t| songs_of[g.name.as_str()].contains(t)).collect();
                let copy = key.copy_for(&g.name);
                if inside.is_empty()
                    || inside.len() == own.len()
                    || keys.contains(&copy)
                    || candidates.iter().any(|c| &c.0 == key && c.2 == inside)
                {
                    continue;
                }
                candidates.push((key.clone(), copy, inside));
            }
        }
        candidates.sort_by(|a, b| {
            let (x, y) = (
                -bound.get(a).copied().unwrap_or(f64::INFINITY),
                -bound.get(b).copied().unwrap_or(f64::INFINITY),
            );
            x.partial_cmp(&y).unwrap()
        });
        let mut best: Option<(f64, Assignment, BTreeSet<Key>, BTreeMap<Key, i64>, Vec<BTreeMap<Key, f64>>)> = None;
        for candidate in candidates {
            let known = bound.get(&candidate).copied().unwrap_or(f64::INFINITY);
            if let Some(b) = &best {
                if b.0 >= known {
                    break;
                }
            }
            let (key, copy, inside) = &candidate;
            let new_asg = with_copy(&assignment, key, copy, inside);
            let (keys_n, budget_n, raised) = khz(&new_asg, &mut natives, &mut rates)?;
            let mut gained = 0.0;
            let mut lowers = false;
            for (t, row) in raised.iter().enumerate() {
                for (b, v) in row {
                    gained += v - current[t][b];
                    if *v < floor[t][b] - 1e-6 {
                        lowers = true;
                    }
                }
            }
            if lowers {
                gained = 0.0;
            }
            bound.insert(candidate.clone(), gained);
            if gained > 0.01 && best.as_ref().is_none_or(|b| gained > b.0) {
                best = Some((gained, new_asg, keys_n, budget_n, raised));
            }
        }
        let Some((_, a, k, b, c)) = best else { break };
        assignment = a;
        keys = k;
        budget = b;
        current = c;
    }
    Ok(assignment)
}

/// {sound effect: place}: which of the sound effects' directory entries
/// each one goes in. `packages` are each package's sound effects and
/// `names` all of them, in cartridge order.
///
/// The ARAM holds one package at a time, and none carries more than a score
/// of sound effects, so two sound effects that are never in the same package
/// can share an entry. It is graph coloring —two sound effects touch if they
/// share a package—, and with DSATUR as many places as the most loaded
/// package has sound effects are enough. The ROM cannot tell from the entry
/// which sound effect is there: it records it when uploading it.
pub fn effect_places(packages: &[Vec<String>], names: &[String]) -> BTreeMap<String, usize> {
    let mut touches: BTreeMap<&str, BTreeSet<&str>> =
        names.iter().map(|n| (n.as_str(), BTreeSet::new())).collect();
    for own in packages {
        let own: Vec<&str> = own.iter().map(|s| s.as_str()).filter(|n| touches.contains_key(n)).collect();
        for n in &own {
            let others: Vec<&str> = own.iter().copied().filter(|o| o != n).collect();
            touches.get_mut(n).unwrap().extend(others);
        }
    }
    let order: HashMap<&str, usize> = names.iter().enumerate().map(|(i, n)| (n.as_str(), i)).collect();
    let mut place: HashMap<&str, usize> = HashMap::new();
    while place.len() < touches.len() {
        // The most constrained first —the one with the most distinct places
        // already taken around it—, and among those the one with the most
        // neighbors; on a tie, the one earlier in the cartridge.
        let n = *touches
            .keys()
            .filter(|n| !place.contains_key(*n))
            .max_by_key(|n| {
                let taken: BTreeSet<usize> =
                    touches[*n].iter().filter_map(|v| place.get(v).copied()).collect();
                (taken.len(), touches[*n].len(), -(order[*n] as i64))
            })
            .unwrap();
        let taken: BTreeSet<usize> = touches[n].iter().filter_map(|v| place.get(v).copied()).collect();
        let free = (0..=taken.len()).find(|p| !taken.contains(p)).unwrap();
        place.insert(n, free);
    }
    place.into_iter().map(|(n, p)| (n.to_string(), p)).collect()
}

/// Each sample's directory entry: the first one with the same BRR and the
/// same loop gives it, and the others are numbered in order. See
/// [`Bank::directory`].
pub fn directory(voices: &[Rc<Voice>]) -> Vec<usize> {
    let mut first: HashMap<(&[u8], usize), usize> = HashMap::new();
    voices
        .iter()
        .map(|v| {
            let n = first.len();
            *first.entry((v.data.as_slice(), v.loop_block)).or_insert(n)
        })
        .collect()
}

/// The samples shared by **every** song in the ROM, one per program and one
/// per hit, each with the budget of its worst package.
///
/// There is only one —except for the copies—, and not to save cartridge
/// space but because of the numbering: the SRCN the stream writes is the
/// sample's index in the cartridge, so two songs that play piano point to
/// the same one. But **it is not uploaded whole**: the ARAM gets packages,
/// one per map, so what has to fit in the 64 KB is not the bank but each
/// package, with its sound effects.
///
/// **Two keys can come out as the same sample**, and then they are one
/// entry of the directory: see [`Bank::directory`].
pub struct Bank {
    /// Programs first, then hits, each in key order.
    pub keys: Vec<Key>,
    pub voices: Vec<Rc<Voice>>,
    /// Each key's entry in the SPC700's directory —the SRCN the ROM
    /// writes—, by key index.
    ///
    /// Two keys whose samples came out with the same BRR and the same loop
    /// share one: a copy built at the same rate as what it copies —its
    /// budget reached the native one in both—, or two keys of a program
    /// that pick the same zone. Until 2026-10-14 each key had its own, and
    /// the cartridge stored the same bytes once per key —sixteen times the
    /// same hi-hat, 201 KB of ABL's release— and a package that played two
    /// of them uploaded both. The rate and the root are not compared: the
    /// DSP only reads the BRR and the loop, and each sound brings its pitch.
    ///
    /// The songs are built with the key indices —what the allocation and
    /// `mix_fingerprint` count with— and renumbered to these afterwards:
    /// see `merge_identical` in `compile`.
    pub directory: Vec<usize>,
    /// Which constraint set each sample, for the report.
    pub limited_by: BTreeMap<Key, String>,
    pub constraints: Vec<Constraint>,
    /// What each package has for samples.
    pub free: i64,
    pub assignment: Assignment,
}

impl Bank {
    pub fn new(
        samples: &Samples,
        keys: &BTreeSet<Key>,
        constraints: Vec<Constraint>,
        free: i64,
        assignment: Assignment,
    ) -> Result<Bank> {
        let mut present = BTreeSet::new();
        let mut natives = HashMap::new();
        for k in keys {
            if let Some(v) = samples.sample(k, NATIVE)? {
                natives.insert(k.clone(), v.data.len() as i64);
                present.insert(k.clone());
            }
        }
        let (mut budget, limited_by) = allocate(&present, &constraints, ARAM_MARGIN, &natives);
        let mut voice: BTreeMap<Key, Rc<Voice>> = BTreeMap::new();
        let build = |k: &Key, b: i64| -> Result<Rc<Voice>> {
            samples.sample(k, b)?.ok_or_else(|| Bad::answer(format!("{k} does not fit in {b} B")))
        };
        for k in &present {
            voice.insert(k.clone(), build(k, budget[k])?);
        }
        let sum = |voice: &BTreeMap<Key, Rc<Voice>>, keys: &BTreeSet<Key>| -> i64 {
            keys.iter().filter_map(|k| voice.get(k)).map(|v| v.data.len() as i64).sum()
        };
        // The budget is a guide: the real length is rounded up to BRR
        // blocks, so what it really takes is checked and, if a constraint
        // goes over its space —without the margin: the margin is for this—,
        // its samples are asked for less and it is built again.
        let mut fits = false;
        for _ in 0..20 {
            let over: Vec<&Constraint> = constraints.iter().filter(|r| sum(&voice, &r.keys) > r.free).collect();
            if over.is_empty() {
                fits = true;
                break;
            }
            for r in over {
                let used = sum(&voice, &r.keys);
                let built: Vec<Key> = r.keys.iter().filter(|k| voice.contains_key(*k)).cloned().collect();
                for k in &built {
                    let b = (((budget[k] * r.free) as f64 / used as f64 * 0.98) as i64).max(FLOOR);
                    budget.insert(k.clone(), b);
                    voice.insert(k.clone(), build(k, b)?);
                }
            }
        }
        if !fits {
            let over: Vec<String> = constraints
                .iter()
                .filter(|r| sum(&voice, &r.keys) > r.free)
                .map(|r| format!("{} ({} of {} B)", r.name, sum(&voice, &r.keys), r.free))
                .collect();
            return Err(Bad::answer(format!(
                "the samples of {} do not fit in the ARAM even at the minimum",
                over.join(", ")
            )));
        }
        let keys: Vec<Key> = present
            .iter()
            .filter(|k| !k.is_hit())
            .chain(present.iter().filter(|k| k.is_hit()))
            .cloned()
            .collect();
        let voices: Vec<Rc<Voice>> = keys.iter().map(|k| voice[k].clone()).collect();
        // One entry per key until `merge_identical`, in `compile`, merges them.
        let directory = (0..voices.len()).collect();
        Ok(Bank { keys, voices, directory, limited_by, constraints, free, assignment })
    }

    /// The directory's music entries: the distinct samples, in the order
    /// their first key has.
    pub fn entries(&self) -> Vec<&Rc<Voice>> {
        let mut out: Vec<&Rc<Voice>> = Vec::new();
        for (v, &e) in self.voices.iter().zip(&self.directory) {
            if e == out.len() {
                out.push(v);
            }
        }
        out
    }

    /// From MIDI program to index in the bank, which is what goes in
    /// `V_SRCN`: the samples without copies.
    pub fn melodic(&self) -> BTreeMap<u8, usize> {
        self.keys
            .iter()
            .enumerate()
            .filter(|(_, k)| !k.is_hit() && !k.is_copy())
            .map(|(i, k)| (k.number, i))
            .collect()
    }

    /// And from percussion key to index; hits go after the melodic ones, so
    /// the DSP does not tell percussion from anything else.
    pub fn hits(&self) -> BTreeMap<u8, usize> {
        self.keys
            .iter()
            .enumerate()
            .filter(|(_, k)| k.is_hit() && !k.is_copy())
            .map(|(i, k)| (k.number, i))
            .collect()
    }

    /// The bank as song `t` sees it: its programs and its hits point to the
    /// samples it was given, copies included.
    pub fn for_song(&self, t: usize) -> (BTreeMap<u8, usize>, BTreeMap<u8, usize>) {
        let index: HashMap<&Key, usize> = self.keys.iter().enumerate().map(|(i, k)| (k, i)).collect();
        let (mut melodic, mut hits) = (BTreeMap::new(), BTreeMap::new());
        for (base, k) in &self.assignment[t] {
            if let Some(&i) = index.get(k) {
                if base.is_hit() {
                    hits.insert(base.number, i);
                } else {
                    melodic.insert(base.number, i);
                }
            }
        }
        (melodic, hits)
    }

    /// How much the samples of those keys take in the ARAM: two keys that
    /// share an entry take it once.
    pub fn takes(&self, keys: &BTreeSet<Key>) -> i64 {
        let entries: BTreeMap<usize, &Rc<Voice>> = self
            .keys
            .iter()
            .zip(&self.voices)
            .zip(&self.directory)
            .filter(|((k, _), _)| keys.contains(*k))
            .map(|((_, v), &e)| (e, v))
            .collect();
        entries.values().map(|v| v.data.len() as i64).sum()
    }

    /// The samples song `t` plays with.
    pub fn keys_of(&self, t: usize) -> BTreeSet<Key> {
        self.assignment[t].values().cloned().collect()
    }
}

#[cfg(test)]
mod tests {
    #[test]
    fn over_255_keys_the_least_used_are_left_out() {
        // 300 programs: the first 100 are in two songs, the rest in one.
        let all: BTreeSet<Key> = (0..300u32).map(|i| Key::program((i / 128) as u8, (i % 128) as u8)).collect();
        let shared: BTreeSet<Key> = all.iter().take(100).cloned().collect();
        let mut songs = vec![all.clone(), shared.clone()];
        let dropped = drop_surplus(&mut songs, 250);
        assert_eq!(dropped.len(), 50);
        assert_eq!(songs[0].len(), 250);
        assert!(shared.is_subset(&songs[0]) && shared.is_subset(&songs[1]));
        // the ones in a single song go from the end of the key order
        let expected: Vec<Key> = all.iter().skip(250).cloned().collect();
        let mut got = dropped.clone();
        got.sort();
        assert_eq!(got, expected);
        assert!(drop_surplus(&mut songs, 250).is_empty());
    }

    use super::*;

    #[test]
    fn keys_sort_as_the_bank_numbers_them_and_print_as_they_parse() {
        let mut keys = [Key::hit(36), Key::program(0, 60).copy_for("3"), Key::program(0, 60), Key::program(0, 72)];
        keys.sort();
        let text: Vec<String> = keys.iter().map(|k| k.to_string()).collect();
        assert_eq!(text, ["g:36", "p:0:60", "p:0:60@3", "p:0:72"]);
        for k in &keys {
            assert_eq!(Key::parse(&k.to_string()).as_ref(), Some(k));
        }
    }

    /// Two sound effects that never share a package share a place; the
    /// places are as many as the most loaded package has.
    #[test]
    fn effects_that_never_meet_share_a_place() {
        let names: Vec<String> = ["a", "b", "c", "d"].map(String::from).to_vec();
        let packages = vec![
            vec!["a".to_string(), "b".to_string()],
            vec!["c".to_string(), "d".to_string()],
            vec!["a".to_string(), "c".to_string()],
        ];
        let place = effect_places(&packages, &names);
        assert_eq!(place.values().max(), Some(&1));
        assert_ne!(place["a"], place["b"]);
        assert_ne!(place["a"], place["c"]);
        assert_ne!(place["c"], place["d"]);
    }

    /// A constraint that fills up freezes its samples at the fraction that
    /// fits; a sample in no full constraint goes whole.
    #[test]
    fn a_sample_is_limited_by_its_worst_package() {
        let (a, b, c) = (Key::hit(35), Key::hit(36), Key::hit(38));
        let natives = HashMap::from([(a.clone(), 1000), (b.clone(), 1000), (c.clone(), 1000)]);
        let keys: BTreeSet<Key> = [a.clone(), b.clone(), c.clone()].into();
        let tight = Constraint { name: "tight".into(), keys: [a.clone(), b.clone()].into(), free: 1000 };
        let loose = Constraint { name: "loose".into(), keys: [b.clone(), c.clone()].into(), free: 10000 };
        let (budget, limited) = allocate(&keys, &[tight, loose], 0, &natives);
        assert_eq!((budget[&a], budget[&b], budget[&c]), (500, 500, 1000));
        assert_eq!(limited.get(&a).map(|s| s.as_str()), Some("tight"));
        assert!(!limited.contains_key(&c));
    }
}
