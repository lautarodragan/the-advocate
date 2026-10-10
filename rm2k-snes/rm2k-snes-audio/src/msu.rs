//! The sound effects the ROM reads from the `.msu` when there is an MSU-1:
//! which version of each goes in each package, and what the ROM needs to
//! play it. The `.msu` itself is assembled by whoever also puts other
//! things in it; this says what goes in and in which order.

use crate::compile::Music;
use crate::effects::{self, MsuPackage};
use crate::emit::{self, Emit};
use crate::fail::Result;
use crate::game::Game;
use std::collections::{BTreeMap, BTreeSet, HashMap};

/// One version of a sound effect: whole, at `rate`, in BRR.
pub struct Version {
    pub effect: String,
    pub rate: i64,
    pub data: Vec<u8>,
}

/// A package's quality sound effects.
pub struct PackageEffects {
    pub name: String,
    /// Its sound effects in the order of their place in the directory
    /// —their SRCN—, which is the order the ROM uploads them in: an index
    /// into the versions each.
    pub versions: Vec<usize>,
    /// For each sound effect of its list, in the order the ROM walks it:
    /// which of `versions` it is.
    pub rows: Vec<usize>,
    /// (sound, pitch) of the sounds whose sound effect is from here, sorted
    /// by sound: the pitch of that package's version.
    pub pitches: Vec<(usize, i64)>,
}

pub struct Effects {
    pub versions: Vec<Version>,
    pub packages: Vec<PackageEffects>,
    /// {package: [(sound effect, rate)]}, for whoever wants to see what the
    /// allocation decided.
    pub rates: Vec<(String, Vec<(String, i64)>)>,
}

/// The ROM's packages' quality sound effects.
///
/// **Each package has its own version of each sound effect**, at the rate
/// it gets there —see [`effects::rates_per_package`]—: a single one per sound effect —the one that fits its worst
/// package— left at 4.7 kHz the ones a crowded package shares with ten
/// others that have room to spare. What it costs is that the ROM uploads
/// the sound effects again on every package even if they were already in
/// the ARAM, because it has nowhere to record which version was left.
pub fn effects(music: &Music, emit: &Emit, game: &Game) -> Result<Effects> {
    let all = music.all_samples();
    // What the music takes with MSU-1 in each package: only the songs
    // without a track, which do upload their samples.
    let mut weighs: HashMap<usize, Vec<u8>> = HashMap::new();
    let mut requested = Vec::new();
    for p in &music.packages[..emit.packages] {
        let mut theirs = BTreeSet::new();
        for &t in &p.songs {
            if music.songs[t].track.is_none() {
                if !weighs.contains_key(&t) {
                    weighs.insert(t, music.songs[t].samples()?);
                }
                theirs.extend(weighs[&t].iter().copied());
            }
        }
        requested.push(MsuPackage {
            name: p.name.clone(),
            effects: p.effects.clone(),
            music_bytes: theirs.iter().map(|&i| all[i as usize].0.len() as i64).sum(),
        });
    }
    let cartridge: BTreeMap<String, effects::SoundEffect> =
        music.effects.iter().map(|e| (e.name.clone(), e.clone())).collect();
    let mut wavs: HashMap<String, (Vec<i64>, i64)> = HashMap::new();
    for p in &requested {
        for e in &p.effects {
            if cartridge.contains_key(e) && !wavs.contains_key(e) {
                if let Some(w) = effects::wav_of(game, e) {
                    wavs.insert(e.clone(), w);
                }
            }
        }
    }
    let sources: HashMap<String, effects::MsuSource> =
        wavs.iter().map(|(e, wav)| (e.clone(), effects::MsuSource::new(wav))).collect();
    let rates = effects::rates_per_package(&requested, &cartridge, &sources, music.bank.free, crate::bank::ARAM_MARGIN);

    let unique: BTreeSet<(String, i64)> =
        rates.iter().flat_map(|(_, own)| own.iter().cloned()).collect();
    let mut versions = Vec::new();
    let mut index: HashMap<(String, i64), usize> = HashMap::new();
    for (e, r) in unique {
        let (rate, data) = effects::build_msu(&wavs[&e], r)?;
        index.insert((e.clone(), r), versions.len());
        versions.push(Version { effect: e, rate, data });
    }

    let by_package: HashMap<&str, &Vec<(String, i64)>> =
        rates.iter().map(|(n, own)| (n.as_str(), own)).collect();
    let rom = emit::rom_packages(music, emit);
    let mut packages = Vec::new();
    for (p, (_, numbers, _, _)) in music.packages[..emit.packages].iter().zip(&rom) {
        let theirs: BTreeMap<&str, i64> = by_package
            .get(p.name.as_str())
            .map(|own| own.iter().map(|(e, r)| (e.as_str(), *r)).collect())
            .unwrap_or_default();
        let mut in_srcn: Vec<&str> = numbers
            .iter()
            .map(|&i| music.effects[i].name.as_str())
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect();
        in_srcn.sort_by_key(|e| music.srcn(e));
        let versions_here: Vec<usize> =
            in_srcn.iter().map(|e| index[&(e.to_string(), theirs[e])]).collect();
        let rows = numbers
            .iter()
            .map(|&i| in_srcn.iter().position(|e| *e == music.effects[i].name).unwrap())
            .collect();
        // Only the sounds whose sound effect is from here: zero is "not from
        // here" for the ROM, so it is not stored.
        let pitches = emit
            .sounds
            .iter()
            .enumerate()
            .filter_map(|(k, s)| {
                let rate = theirs.get(s.effect.as_str())?;
                let v = &versions[index[&(s.effect.clone(), *rate)]];
                let pitch = effects::pitch(v.rate, s.tempo);
                (pitch != 0).then_some((k, pitch))
            })
            .collect();
        packages.push(PackageEffects { name: p.name.clone(), versions: versions_here, rows, pitches });
    }
    Ok(Effects { versions, packages, rates })
}
