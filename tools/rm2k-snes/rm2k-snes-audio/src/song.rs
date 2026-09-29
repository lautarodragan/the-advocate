//! A song as the compiler needs it before having the bank: its notes and
//! controllers in frames, its voices and its programs.

use crate::fail::Result;
use crate::game::Game;
use crate::midi::{self, Control, Note};
use crate::voices;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug)]
pub struct Parsed {
    pub name: String,
    pub notes: Vec<Note>,
    pub controls: Vec<Control>,
    /// When its last note ends, in frames.
    pub length: i64,
    pub voices: BTreeMap<u8, Vec<u8>>,
    pub programs: BTreeMap<u8, u8>,
}

impl Parsed {
    /// A channel's program: its first, or 0.
    pub fn program(&self, channel: u8) -> u8 {
        *self.programs.get(&channel).unwrap_or(&0)
    }

    /// What it contributes to the shared bank: the programs of its melodic
    /// channels...
    pub fn melodic(&self) -> BTreeSet<u8> {
        self.voices
            .keys()
            .filter(|&&c| c != midi::DRUM_CHANNEL)
            .map(|&c| self.program(c))
            .collect()
    }

    /// ...and the percussion keys it plays.
    pub fn hits(&self) -> BTreeSet<u8> {
        self.notes.iter().filter(|n| n.channel == midi::DRUM_CHANNEL).map(|n| n.pitch).collect()
    }
}

/// What needs to be known about a song **before** having the bank.
///
/// None if the name is missing or is not a MIDI, which is like a map without
/// music: the song still goes into the numbering —the bytecode already
/// carries its index— but its stream is a lone `OP_END` and the ROM stays
/// silent when it is played.
pub fn read(name: &str, game: &Game) -> Result<Option<Parsed>> {
    let Some(path) = game.song_path(name) else { return Ok(None) };
    if !path.to_string_lossy().to_lowercase().ends_with(".mid") {
        return Ok(None);
    }
    let mut m = midi::read(&path)?;
    let voices = voices::assign(&m.notes);
    let length = midi::timeline(&mut m);
    Ok(Some(Parsed {
        name: name.to_string(),
        notes: m.notes,
        controls: m.controls,
        length,
        voices,
        programs: m.programs,
    }))
}
