//! A minimal MIDI file reader: the notes and the controllers that are heard.
//!
//! When each note starts and ends, on which channel and with which velocity,
//! the tempo changes, the first instrument of each channel, and the
//! controllers that change how an already sounding note sounds: volume
//! (CC7), pan (CC10), expression (CC11) and pitch bend, which are returned as
//! [`Control`]s. The sustain pedal (CC64) is not returned: it lengthens the
//! notes, which is what a synthesizer does with it. The rest —reverb,
//! chorus, modulation, NRPNs, aftertouch— is dropped.
//!
//! And the clock: [`timeline`] turns ticks into frames of 60 Hz, which is
//! the unit everything downstream counts in.

use crate::fail::{Bad, Result};
use crate::num;
use std::collections::{BTreeMap, HashMap};

const NOTE_OFF: u8 = 0x80;
const NOTE_ON: u8 = 0x90;
const CONTROL: u8 = 0xB0;
const PROGRAM: u8 = 0xC0;
const BEND_STATUS: u8 = 0xE0;
const META: u8 = 0xFF;
const TEMPO: u8 = 0x51;
/// The standard's channel 10, counting from zero.
pub const DRUM_CHANNEL: u8 = 9;

/// The controllers that are returned, with their General MIDI number.
pub const VOLUME: u16 = 7;
pub const PAN: u16 = 10;
pub const EXPRESSION: u16 = 11;
/// Pitch bend is not a controller, but it travels the same way: it is
/// numbered outside the CC range so it does not clash with any of them. Its
/// value already comes in semitones, with the channel's range applied.
pub const BEND: u16 = 0x100;

/// The value a channel has before the MIDI says anything: General MIDI's,
/// which are fluidsynth's.
pub fn default_of(number: u16) -> f64 {
    match number {
        VOLUME => 100.0,
        PAN => 64.0,
        EXPRESSION => 127.0,
        _ => 0.0,
    }
}

const SUSTAIN: u8 = 64;
// What the pitch bend range needs: RPN 0 is selected with CC101 and CC100 at
// zero, and the value arrives through CC6 (semitones) and CC38 (cents).
// CC99 and CC98 select an NRPN, and from then on CC6 no longer belongs to
// the RPN.
const DATA_MSB: u8 = 6;
const DATA_LSB: u8 = 38;
const NRPN_LSB: u8 = 98;
const NRPN_MSB: u8 = 99;
const RPN_LSB: u8 = 100;
const RPN_MSB: u8 = 101;
const RAW_CONTROLLERS: [u8; 10] = [
    VOLUME as u8,
    PAN as u8,
    EXPRESSION as u8,
    SUSTAIN,
    DATA_MSB,
    DATA_LSB,
    NRPN_LSB,
    NRPN_MSB,
    RPN_LSB,
    RPN_MSB,
];
/// Semitones: General MIDI's, as long as nobody changes it.
const BEND_RANGE: f64 = 2.0;

/// One tick per frame: the unit in which the port counts time.
pub const TICKS_PER_SECOND: i64 = 60;

#[derive(Clone, Debug, PartialEq)]
pub struct Note {
    pub start: i64,
    pub end: i64,
    pub channel: u8,
    pub pitch: u8,
    pub velocity: u8,
}

impl Note {
    pub fn new(start: i64, end: i64, channel: u8, pitch: u8, velocity: u8) -> Note {
        Note { start, end, channel, pitch, velocity }
    }
}

/// A controller that changes on a channel: `number` is [`VOLUME`], [`PAN`],
/// [`EXPRESSION`] or [`BEND`].
#[derive(Clone, Debug, PartialEq)]
pub struct Control {
    pub start: i64,
    pub channel: u8,
    pub number: u16,
    pub value: f64,
}

/// What a MIDI file says, in ticks.
#[derive(Clone, Debug)]
pub struct Midi {
    pub notes: Vec<Note>,
    /// (tick, microseconds per quarter note).
    pub tempos: Vec<(i64, i64)>,
    pub division: i64,
    /// The first program of each channel.
    pub programs: BTreeMap<u8, u8>,
    pub controls: Vec<Control>,
}

fn varlen(data: &[u8], mut pos: usize) -> Result<(i64, usize)> {
    let mut value: i64 = 0;
    loop {
        let byte = *data.get(pos).ok_or_else(truncated)?;
        pos += 1;
        value = (value << 7) | (byte & 0x7F) as i64;
        if byte & 0x80 == 0 {
            return Ok((value, pos));
        }
    }
}

fn truncated() -> Bad {
    Bad::usage("the MIDI ends in the middle of an event")
}

fn at(data: &[u8], pos: usize) -> Result<u8> {
    data.get(pos).copied().ok_or_else(truncated)
}

/// A raw controller: (tick, channel, number, value), resolved later with
/// all the tracks together.
type Raw = (i64, u8, u16, i64);

/// Walks a track collecting notes, tempos and instruments, in ticks.
///
/// The controllers go raw into `raw` and are resolved later with all the
/// tracks together: a channel spreads its events over several tracks, so the
/// bend range or the pedal one track chose is used by another.
fn track(
    data: &[u8],
    mut pos: usize,
    end: usize,
    notes: &mut Vec<Note>,
    tempos: &mut Vec<(i64, i64)>,
    programs: &mut BTreeMap<u8, u8>,
    raw: &mut Vec<Raw>,
) -> Result<()> {
    let mut time: i64 = 0;
    let mut status: u8 = 0;
    // (channel, pitch) -> index in `notes` of the note sounding there.
    let mut sounding: Vec<((u8, u8), usize)> = Vec::new();

    while pos < end {
        let (delta, p) = varlen(data, pos)?;
        pos = p;
        time += delta;
        if pos >= end {
            break; // the track ends right after the last delta
        }
        if at(data, pos)? & 0x80 != 0 {
            status = at(data, pos)?;
            pos += 1;
        }
        // Otherwise it is "running status": the last one repeats and the byte
        // is already data.
        let (kind, channel) = (status & 0xF0, status & 0x0F);

        if status == META {
            let meta = at(data, pos)?;
            let (length, p) = varlen(data, pos + 1)?;
            pos = p;
            if meta == TEMPO {
                let bytes = &data[pos.min(data.len())..(pos + 3).min(data.len())];
                let us = bytes.iter().fold(0i64, |v, &b| v << 8 | b as i64);
                tempos.push((time, us));
            }
            pos += length as usize;
        } else if status == 0xF0 || status == 0xF7 {
            let (length, p) = varlen(data, pos)?;
            pos = p + length as usize;
        } else if kind == NOTE_ON || kind == NOTE_OFF {
            let (pitch, velocity) = (at(data, pos)?, at(data, pos + 1)?);
            pos += 2;
            let key = (channel, pitch);
            let here = sounding.iter().position(|(k, _)| *k == key);
            if kind == NOTE_ON && velocity != 0 {
                if let Some(i) = here {
                    notes[sounding[i].1].end = time;
                    sounding.remove(i);
                }
                notes.push(Note::new(time, time, channel, pitch, velocity));
                sounding.push((key, notes.len() - 1));
            } else if let Some(i) = here {
                notes[sounding[i].1].end = time;
                sounding.remove(i);
            }
        } else if kind == PROGRAM {
            // The first one of each channel.
            let program = at(data, pos)?;
            programs.entry(channel).or_insert(program);
            pos += 1;
        } else if kind == 0xD0 {
            pos += 1; // channel aftertouch
        } else if kind == CONTROL {
            let number = at(data, pos)?;
            if RAW_CONTROLLERS.contains(&number) {
                raw.push((time, channel, number as u16, at(data, pos + 1)? as i64));
            }
            pos += 2;
        } else if kind == BEND_STATUS {
            let value = (at(data, pos)? as i64 | (at(data, pos + 1)? as i64) << 7) - 8192;
            raw.push((time, channel, BEND, value));
            pos += 2;
        } else {
            pos += 2; // the rest are two bytes
        }
    }

    for (_, i) in sounding {
        notes[i].end = time;
    }
    Ok(())
}

/// The raw controllers of all the tracks, in time order, to [`Control`]s:
/// the bend to semitones with its channel's range, and the pedal applied to
/// the notes.
fn controls(mut raw: Vec<Raw>, notes: &mut [Note]) -> Vec<Control> {
    raw.sort_by_key(|e| e.0);
    let mut out = Vec::new();
    // channel -> the selected (is RPN, MSB, LSB)
    let mut param: HashMap<u8, (bool, i64, i64)> = HashMap::new();
    let mut semitones: HashMap<u8, f64> = HashMap::new();
    // channel -> [(down, up)], in the order the pedal went up
    let mut pedal: Vec<(u8, Vec<(i64, i64)>)> = Vec::new();
    // channel -> when it went down, in the order it did
    let mut down: Vec<(u8, i64)> = Vec::new();

    fn pedal_of(pedal: &mut Vec<(u8, Vec<(i64, i64)>)>, channel: u8) -> &mut Vec<(i64, i64)> {
        let i = match pedal.iter().position(|(c, _)| *c == channel) {
            Some(i) => i,
            None => {
                pedal.push((channel, Vec::new()));
                pedal.len() - 1
            }
        };
        &mut pedal[i].1
    }

    for (time, channel, number, value) in raw {
        let range = *semitones.get(&channel).unwrap_or(&BEND_RANGE);
        if number == BEND {
            out.push(Control {
                start: time,
                channel,
                number: BEND,
                value: value as f64 / 8192.0 * range,
            });
        } else if number == VOLUME || number == PAN || number == EXPRESSION {
            out.push(Control { start: time, channel, number, value: value as f64 });
        } else if number == SUSTAIN as u16 {
            let is_down = down.iter().position(|(c, _)| *c == channel);
            if value >= 64 && is_down.is_none() {
                down.push((channel, time));
            } else if value < 64 {
                if let Some(i) = is_down {
                    let (_, when) = down.remove(i);
                    pedal_of(&mut pedal, channel).push((when, time));
                }
            }
        } else if [RPN_MSB, RPN_LSB, NRPN_MSB, NRPN_LSB].contains(&(number as u8)) {
            let number = number as u8;
            let rpn = number == RPN_MSB || number == RPN_LSB;
            // Unselected, both are 127: the "null" RPN. Measured with
            // fluidsynth: a CC101 at 0 without its CC100 does not touch the
            // range.
            let mut selected = *param.get(&channel).unwrap_or(&(rpn, 127, 127));
            if selected.0 != rpn {
                selected = (rpn, 127, 127);
            }
            let msb = if number == RPN_MSB || number == NRPN_MSB { value } else { selected.1 };
            let lsb = if number == RPN_LSB || number == NRPN_LSB { value } else { selected.2 };
            param.insert(channel, (rpn, msb, lsb));
        } else if param.get(&channel) == Some(&(true, 0, 0)) {
            // RPN 0, the bend range. **No cap**: a song can ask for 95
            // semitones and fluidsynth honors them —measured—; a GS
            // synthesizer would cap it at 24. This follows fluidsynth, which
            // is what the result is compared against.
            let whole = range.trunc();
            let fraction = range - whole;
            if number == DATA_MSB as u16 {
                semitones.insert(channel, value as f64 + fraction);
            } else {
                semitones.insert(channel, whole + value as f64 / 100.0);
            }
        }
    }

    if !down.is_empty() || !pedal.is_empty() {
        // A note released with the pedal down keeps sounding until it goes
        // up, or until the same key is played again. If it never goes up,
        // until the end of the song.
        let song_end = notes.iter().map(|n| n.end).max().unwrap_or(0);
        for (channel, time) in down {
            pedal_of(&mut pedal, channel).push((time, song_end));
        }
        let mut next_start: HashMap<(u8, u8), i64> = HashMap::new();
        let mut order: Vec<usize> = (0..notes.len()).collect();
        order.sort_by_key(|&i| -notes[i].start);
        for i in order {
            let key = (notes[i].channel, notes[i].pitch);
            if let Some((_, spans)) = pedal.iter().find(|(c, _)| *c == notes[i].channel) {
                for &(down_at, up_at) in spans {
                    if down_at < notes[i].end && notes[i].end < up_at {
                        notes[i].end = up_at.min(*next_start.get(&key).unwrap_or(&up_at));
                        break;
                    }
                }
            }
            next_start.insert(key, notes[i].start);
        }
    }
    out
}

fn u16_be(data: &[u8], at: usize) -> Result<u16> {
    Ok(u16::from_be_bytes([
        *data.get(at).ok_or_else(truncated)?,
        *data.get(at + 1).ok_or_else(truncated)?,
    ]))
}

fn u32_be(data: &[u8], at: usize) -> Result<u32> {
    Ok(((u16_be(data, at)? as u32) << 16) | u16_be(data, at + 2)? as u32)
}

/// Reads a MIDI file's bytes. `name` only goes into the error messages.
pub fn parse(data: &[u8], name: &str) -> Result<Midi> {
    if data.get(..4) != Some(b"MThd") {
        return Err(Bad::usage(format!("{name} is not a MIDI file")));
    }
    let header = u32_be(data, 4)? as usize;
    let tracks = u16_be(data, 10)?;
    let division = u16_be(data, 12)?;
    if division & 0x8000 != 0 {
        return Err(Bad::usage(format!("{name}: MIDI with SMPTE division, not supported")));
    }

    let (mut notes, mut tempos, mut programs, mut raw) =
        (Vec::new(), Vec::new(), BTreeMap::new(), Vec::new());
    let mut pos = 8 + header;
    for _ in 0..tracks {
        if data.get(pos..pos + 4) != Some(b"MTrk") {
            break;
        }
        let length = u32_be(data, pos + 4)? as usize;
        track(data, pos + 8, pos + 8 + length, &mut notes, &mut tempos, &mut programs, &mut raw)
            .map_err(|e| Bad::usage(format!("{name}: {e}")))?;
        pos += 8 + length;
    }

    let controls = controls(raw, &mut notes);
    notes.sort_by_key(|n| (n.start, n.pitch));
    if tempos.is_empty() {
        tempos.push((0, 500000));
    }
    Ok(Midi { notes, tempos, division: division as i64, programs, controls })
}

/// Reads a MIDI file.
pub fn read(path: &std::path::Path) -> Result<Midi> {
    let data = std::fs::read(path).map_err(|e| Bad::usage(format!("{}: {e}", path.display())))?;
    parse(&data, &path.display().to_string())
}

/// Turns MIDI ticks into frames, with the tempo applied.
pub struct Clock {
    /// (tick, second, microseconds per quarter note from there on).
    marks: Vec<(i64, f64, i64)>,
    division: i64,
}

impl Clock {
    pub fn new(tempos: &[(i64, i64)], division: i64) -> Clock {
        let mut sorted = tempos.to_vec();
        sorted.sort();
        let mut marks = vec![(0, 0.0, sorted[0].1)];
        for &(tick, us) in &sorted[1..] {
            let (last_tick, last_second, last_us) = *marks.last().unwrap();
            marks.push((
                tick,
                last_second + (tick - last_tick) as f64 / division as f64 * last_us as f64 / 1e6,
                us,
            ));
        }
        Clock { marks, division }
    }

    pub fn frame(&self, tick: i64) -> i64 {
        let &(base_tick, base_second, us) = self
            .marks
            .iter()
            .rev()
            .find(|m| m.0 <= tick)
            .unwrap_or(&self.marks[0]);
        num::round(
            (base_second + (tick - base_tick) as f64 / self.division as f64 * us as f64 / 1e6)
                * TICKS_PER_SECOND as f64,
        )
    }
}

/// Converts the notes and the controllers from ticks to frames. Returns
/// how long the song lasts: the end of its last note.
pub fn timeline(midi: &mut Midi) -> i64 {
    let clock = Clock::new(&midi.tempos, midi.division);
    for note in &mut midi.notes {
        note.start = clock.frame(note.start);
        note.end = clock.frame(note.end);
        note.end = note.end.max(note.start + 1);
    }
    for control in &mut midi.controls {
        control.start = clock.frame(control.start);
    }
    midi.notes.iter().map(|n| n.end).max().unwrap_or(0)
}

/// How long each number of simultaneous spans plays, in frames: {how many:
/// frames}. A span is (start, end).
pub fn note_time(spans: &[(i64, i64)]) -> BTreeMap<i64, i64> {
    let mut edges: BTreeMap<i64, i64> = BTreeMap::new();
    for &(start, end) in spans {
        if end > start {
            *edges.entry(start).or_default() += 1;
            *edges.entry(end).or_default() -= 1;
        }
    }
    let mut out: BTreeMap<i64, i64> = BTreeMap::new();
    let (mut playing, mut previous) = (0, None);
    for (&at, &change) in &edges {
        if let Some(p) = previous {
            if playing > 0 {
                *out.entry(playing).or_default() += at - p;
            }
        }
        playing += change;
        previous = Some(at);
    }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A one-track MIDI, format 0, 96 ticks per quarter note.
    fn midi(events: &[(u32, &[u8])]) -> Vec<u8> {
        fn varlen(mut n: u32) -> Vec<u8> {
            let mut b = vec![(n & 0x7F) as u8];
            n >>= 7;
            while n != 0 {
                b.insert(0, (n & 0x7F) as u8 | 0x80);
                n >>= 7;
            }
            b
        }
        let mut track: Vec<u8> = Vec::new();
        for (delta, bytes) in events {
            track.extend(varlen(*delta));
            track.extend_from_slice(bytes);
        }
        track.extend_from_slice(&[0x00, 0xFF, 0x2F, 0x00]);
        let mut data = b"MThd".to_vec();
        data.extend(6u32.to_be_bytes());
        data.extend(0u16.to_be_bytes());
        data.extend(1u16.to_be_bytes());
        data.extend(96u16.to_be_bytes());
        data.extend(b"MTrk");
        data.extend((track.len() as u32).to_be_bytes());
        data.extend(track);
        data
    }

    fn bend(fraction_of_range: f64, channel: u8) -> [u8; 3] {
        let value = (fraction_of_range * 8192.0) as i64 + 8192;
        [0xE0 | channel, (value & 0x7F) as u8, (value >> 7) as u8]
    }

    /// The range is selected with CC101 and CC100 at zero and arrives
    /// through CC6. A CC101 alone is not enough —measured with fluidsynth: a
    /// song that sends CC101 and CC6 at 64 without CC100 keeps its bend at 2
    /// semitones—.
    #[test]
    fn the_bend_range_needs_a_whole_rpn_0() {
        let b0 = bend(0.5, 0);
        let b1 = bend(0.5, 1);
        let data = midi(&[
            (0, &[0xB0, 101, 0]),
            (0, &[0xB0, 6, 64]),
            (0, &b0),
            (0, &[0xB1, 101, 0]),
            (0, &[0xB1, 100, 0]),
            (0, &[0xB1, 6, 12]),
            (0, &b1),
            (0, &[0x90, 60, 100]),
            (96, &[0x80, 60, 0]),
        ]);
        let m = parse(&data, "t.mid").unwrap();
        let bends: Vec<(u8, f64)> = m
            .controls
            .iter()
            .filter(|c| c.number == BEND)
            .map(|c| (c.channel, c.value))
            .collect();
        assert_eq!(bends, [(0, 1.0), (1, 6.0)]);
    }

    /// CC64: the note released with the pedal down goes on until the pedal
    /// comes up.
    #[test]
    fn a_note_released_with_the_pedal_down_lasts_until_it_comes_up() {
        let data = midi(&[
            (0, &[0xB0, 64, 127]),
            (0, &[0x90, 60, 100]),
            (96, &[0x80, 60, 0]),
            (96, &[0xB0, 64, 0]),
            (0, &[0x90, 62, 100]),
            (96, &[0x80, 62, 0]),
        ]);
        let m = parse(&data, "t.mid").unwrap();
        let ends: Vec<(u8, i64, i64)> = m.notes.iter().map(|n| (n.pitch, n.start, n.end)).collect();
        assert_eq!(ends, [(60, 0, 192), (62, 192, 288)]);
    }

    #[test]
    fn the_clock_follows_the_tempo_changes() {
        // 96 ticks per quarter note: at 500000 us a quarter is half a second,
        // 30 frames; after the change to 250000, 15.
        let clock = Clock::new(&[(0, 500000), (96, 250000)], 96);
        assert_eq!(clock.frame(96), 30);
        assert_eq!(clock.frame(192), 45);
    }

    #[test]
    fn note_time_counts_how_long_each_polyphony_lasts() {
        let spans = note_time(&[(0, 10), (5, 15), (20, 20)]);
        assert_eq!(spans.into_iter().collect::<Vec<_>>(), [(1, 10), (2, 5)]);
    }
}
