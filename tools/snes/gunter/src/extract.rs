//! Taking one sample out of a SoundFont, as `gunter sf2 --extract` does.
//!
//! The selector picks a zone —or a raw sample by name—, and what comes out is
//! the audio plus everything a player needs to play it as the font meant:
//! the root key, the tuning, the loop relative to the extracted audio, and
//! the zone's volume envelope. The command line prints this; a program that
//! uses this crate as a library gets the same thing without a process in the
//! middle.

use crate::fail::{Bad, Result};
use crate::sf2::{self, SoundFont, VolumeEnvelope};

/// What `--extract` was asked for.
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub enum Selector {
    Program { program: u16, bank: u16, key: u8 },
    Named(String),
}

/// The key a melodic program's zone is chosen with when nobody says: middle C.
pub const REFERENCE_KEY: u8 = 60;

pub fn parse_selector(text: &str) -> Result<Selector> {
    let bad = || {
        Bad(format!(
            "{text:?} is not a selector: expected program:N, program:N@KEY, \
             drum:N or sample:NAME"
        ))
    };
    let (kind, rest) = text.split_once(':').ok_or_else(bad)?;
    match kind {
        "program" => {
            let (number, key) = match rest.split_once('@') {
                Some((n, k)) => (n, Some(k)),
                None => (rest, None),
            };
            let program: u16 = number
                .parse()
                .map_err(|_| Bad(format!("program {number:?} is not a number 0-127")))?;
            let key: u8 = match key {
                None => REFERENCE_KEY,
                Some(k) => k
                    .parse()
                    .map_err(|_| Bad(format!("key {k:?} is not a number 0-127")))?,
            };
            Ok(Selector::Program { program, bank: 0, key })
        }
        "drum" => {
            let key: u8 = rest
                .parse()
                .map_err(|_| Bad(format!("drum key {rest:?} is not a number 0-127")))?;
            Ok(Selector::Program { program: 0, bank: sf2::DRUM_BANK, key })
        }
        "sample" => Ok(Selector::Named(rest.to_string())),
        _ => Err(bad()),
    }
}

/// Where a selector leads, before any audio is read: the sample's entry and
/// what the zone says about playing it.
#[derive(Clone, Debug)]
pub struct Contract {
    pub name: String,
    /// The sample's entry in the font: where its audio is.
    pub sample: sf2::Sample,
    pub rate: u32,
    /// Which key sounds at `rate`: the zone's override, or the sample's own.
    pub root_key: u8,
    /// The tuning on top of the root key, from all three places a font
    /// keeps it.
    pub tuning_cents: i32,
    /// The loop, relative to the extracted audio, if the zone repeats.
    pub loop_start: Option<u32>,
    pub loop_end: Option<u32>,
    /// The zone's volume envelope; `None` for a `sample:NAME`, which has no
    /// zone.
    pub envelope: Option<VolumeEnvelope>,
}

impl Contract {
    pub fn loops(&self) -> bool {
        self.loop_start.is_some()
    }

    /// How many frames the extracted audio has.
    pub fn frames(&self) -> u32 {
        self.sample.frames()
    }
}

/// What the selector picks in the font, or `None` if nothing covers it.
pub fn contract(font: &SoundFont, selector: &Selector) -> Option<Contract> {
    let (zone, envelope, sample) = match selector {
        Selector::Program { program, bank, key } => {
            let found = font.zone_for(*program, *key, *bank)?;
            (Some(found.zone.clone()), Some(found.envelope()), found.sample)
        }
        Selector::Named(name) => (None, None, font.find_sample(name)?.clone()),
    };

    // The loop is reported relative to the extracted audio, because that is
    // the only place it means anything once the sample is out of the file.
    let looped = zone.as_ref().map_or(sample.loop_end > sample.loop_start, |z| {
        z.looped() && sample.loop_end > sample.loop_start
    });
    let loop_start = looped.then(|| sample.loop_start.saturating_sub(sample.start));
    let loop_end = looped.then(|| sample.loop_end.saturating_sub(sample.start));

    let root_key = match zone.as_ref().and_then(|z| z.get(sf2::GEN_ROOT_KEY)) {
        Some(k) if (0..=127).contains(&k) => k as u8,
        _ => sample.root_key,
    };
    // A SoundFont corrects tuning from three different places, and a player
    // that reads only one of them plays the sample out of tune.
    let tuning_cents = sample.correction as i32
        + zone.as_ref().map_or(0, |z| z.get_or(sf2::GEN_FINE_TUNE, 0))
        + 100 * zone.as_ref().map_or(0, |z| z.get_or(sf2::GEN_COARSE_TUNE, 0));

    Some(Contract {
        name: sample.name.clone(),
        rate: sample.rate,
        root_key,
        tuning_cents,
        loop_start,
        loop_end,
        envelope,
        sample,
    })
}

/// A contract and its audio.
#[derive(Clone, Debug)]
pub struct Extracted {
    pub contract: Contract,
    pub pcm: Vec<i16>,
}

/// The sample the selector picks, with its audio, or `None` if nothing
/// covers it. An error is the font's audio block being short.
pub fn extract(font: &mut SoundFont, selector: &Selector) -> Result<Option<Extracted>> {
    let Some(contract) = contract(font, selector) else {
        return Ok(None);
    };
    let pcm = font.pcm(contract.sample.start, contract.sample.end)?;
    Ok(Some(Extracted { contract, pcm }))
}
