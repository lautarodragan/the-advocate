//! What a song writes to the DSP, and the per-note stream that says it.
//!
//! [`writes`] is **the stream's specification**: (frame, register, value),
//! in order. The stream itself is per note —see "the per-note format"
//! below— and the 65816 expands it into exactly those writes, frame by
//! frame: [`check`] verifies it with every song, through [`decode`], which
//! is the model of the 65816's decoder.

use crate::fail::{Bad, Result};
use crate::music_opcodes::*;
use crate::sdsp;
use std::collections::{BTreeMap, HashMap, HashSet};

/// Where the sample directory is in the SPC700's memory.
pub const SAMPLES_ADDR: u16 = 0x0400;

/// A write to the DSP: (frame, register, value).
pub type Write = (i64, u8, u8);

/// What a note writes to its voice before the KON, and the GAIN it will be
/// released with —None for the drums, which are not released—.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct NoteSetup {
    pub voice: u8,
    pub left: u8,
    pub right: u8,
    pub pitch: u16,
    pub sample: u8,
    pub adsr1: u8,
    pub adsr2: u8,
    pub gain: Option<u8>,
}

impl NoteSetup {
    /// The seven writes, in the order they go to the DSP.
    pub fn writes(&self) -> [(u8, u8); 7] {
        let base = self.voice * 0x10;
        [
            (base + sdsp::V_VOL_L, self.left),
            (base + sdsp::V_VOL_R, self.right),
            (base + sdsp::V_PITCH_L, (self.pitch & 0xFF) as u8),
            (base + sdsp::V_PITCH_H, (self.pitch >> 8) as u8),
            (base + sdsp::V_SRCN, self.sample),
            (base + sdsp::V_ADSR1, self.adsr1),
            (base + sdsp::V_ADSR2, self.adsr2),
        ]
    }
}

/// Everything that happens in a frame, split by when it has to be written.
///
/// Order matters: first each voice is prepared —volume, pitch, timbre— and
/// only at the end are KON and KOF touched, which are what trigger. The
/// other way round, the note would start with the previous one's values.
#[derive(Clone, Debug, Default)]
pub struct Frame {
    /// The notes released in this frame: (voice, release GAIN), and the
    /// voices brought down with the ramp because another note takes them in
    /// the next frame.
    pub release: Vec<(u8, u8)>,
    /// The ones that start, in order.
    pub setup: Vec<NoteSetup>,
    pub kon: u8,
    pub kof: u8,
    /// What the controllers change on a voice that was already sounding:
    /// register -> value, the frame's last one wins. A map and not a list
    /// because a fade brings several CC7s per frame, and writing the ones in
    /// the middle is bytes the DSP never gets to use.
    pub control: BTreeMap<u8, u8>,
}

impl Frame {
    fn is_empty(&self) -> bool {
        self.release.is_empty()
            && self.setup.is_empty()
            && self.kon == 0
            && self.kof == 0
            && self.control.is_empty()
    }
}

pub type Frames = BTreeMap<i64, Frame>;

/// The DSP's state before the first note: everything global to it.
pub fn init_writes() -> Vec<(u8, u8)> {
    vec![
        (sdsp::FLG, sdsp::FLG_BASE), // no echo, no mute
        (sdsp::MVOL_L, sdsp::master() as u8),
        (sdsp::MVOL_R, sdsp::master() as u8),
        (sdsp::EVOL_L, 0x00),
        (sdsp::EVOL_R, 0x00),
        (sdsp::EON, 0x00),  // no voice sends to the echo
        (sdsp::PMON, 0x00), // no modulation between voices
        (sdsp::NON, 0x00),  // no noise: the percussion has its own samples
        (sdsp::DIR, (SAMPLES_ADDR >> 8) as u8), // where the directory is
        (sdsp::KON, 0x00),
        (sdsp::KOF, 0x00),
    ]
}

/// What the song writes to the DSP, in order.
///
/// The DSP's registers are plain latches: writing the same value again does
/// nothing. So what each one holds is tracked and the writes that change
/// nothing are skipped. That is safe even with the song looping: a write is
/// skipped only because an earlier write in the same stream left that
/// value, and that one also runs on the second pass.
///
/// KON is the exception and is never cached: it is not a latch but a
/// trigger. The DSP looks at it every two milliseconds and starts the voices
/// whose bit is set, so it has to be cleared by hand or the note repeats.
pub fn writes(frames: &Frames, length: i64, init: &[(u8, u8)]) -> Vec<Write> {
    let mut out = Vec::new();
    let mut state: HashMap<u8, u8> = HashMap::new();
    let mut frame_no: i64 = 0;

    fn write(out: &mut Vec<Write>, state: &mut HashMap<u8, u8>, at: i64, register: u8, value: u8) {
        if state.get(&register) == Some(&value) {
            return;
        }
        state.insert(register, value);
        out.push((at, register, value));
    }

    for &(r, v) in init {
        write(&mut out, &mut state, frame_no, r, v);
    }
    let mut sounding = 0u8;
    for (&at, frame) in frames {
        if at > length {
            break;
        }
        if frame.is_empty() {
            continue;
        }
        frame_no = at;
        if sounding != 0 {
            // clear the previous frame's trigger
            out.push((frame_no, sdsp::KON, 0x00));
            sounding = 0;
        }
        write(&mut out, &mut state, frame_no, sdsp::KOF, 0x00);
        for &(voice, gain) in &frame.release {
            // ADSR off: GAIN rules
            write(&mut out, &mut state, frame_no, voice * 0x10 + sdsp::V_ADSR1, 0x00);
            write(&mut out, &mut state, frame_no, voice * 0x10 + sdsp::V_GAIN, gain);
        }
        for setup in &frame.setup {
            for (r, v) in setup.writes() {
                write(&mut out, &mut state, frame_no, r, v);
            }
        }
        for (&r, &v) in &frame.control {
            write(&mut out, &mut state, frame_no, r, v);
        }
        if frame.kof != 0 {
            write(&mut out, &mut state, frame_no, sdsp::KOF, frame.kof);
        }
        if frame.kon != 0 {
            out.push((frame_no, sdsp::KON, frame.kon));
            sounding = frame.kon;
        }
    }
    // At the end everything is shut off, otherwise the last note keeps
    // sounding into the loop.
    frame_no = frame_no.max(length);
    out.push((frame_no, sdsp::KON, 0x00));
    out.push((frame_no, sdsp::KOF, 0xFF));
    out
}

// --- the per-note format ---------------------------------------------------
//
// A song is its stream and its table of *sounds*: everything a note writes
// to its voice except the volume —pitch, sample, ADSR— plus the GAIN it will
// be released with. The pitch goes inside, and not separately, because that
// way the instrument and the key are a single byte.
//
// What the format does **not** assume, on purpose, is which channel each
// voice belongs to: the event says the voice and the compiler chose it. A
// voice changing instrument note by note costs one sound per note, the same
// as not changing it. And the ramp before reusing a sounding voice is an
// `OP_RELEASE_GAIN` with the ramp's GAIN, one frame before the note.
//
// The register cache of `writes` is kept by the 65816 and not by the stream:
// each event says values and the decoder skips the one the register already
// has. It has a single trap, which is that it cannot say "I don't know" —see
// `decode`—. KON does not go in the stream either: the notes accumulate it
// and the wait that closes the frame fires it, which is `writes`'s rule.

/// A sound: (PITCH_L, PITCH_H, SRCN, ADSR1, ADSR2, release GAIN), in the
/// order they are written, which is what lets the 65816 walk it with a
/// single index.
pub type Sound = [u8; 6];

/// The voice registers the decoder keeps in its cache: from VOL_L to GAIN.
const VOICE_REGISTERS: u8 = 8;

/// The families of eight opcodes, one per voice: the voice goes in the three
/// low bits and the family in the upper ones, which is how the decoder
/// finds them. The declaration cannot declare them: `check_families` says
/// they are where they should be.
const FAMILIES: [(&str, u8); 8] = [
    ("NOTE", OP_NOTE_V0),
    ("NOTE_VOL", OP_NOTE_VOL_V0),
    ("NOTE_PAN", OP_NOTE_PAN_V0),
    ("RELEASE", OP_RELEASE_V0),
    ("RELEASE_GAIN", OP_RELEASE_GAIN_V0),
    ("SET_VOL", OP_SET_VOL_V0),
    ("SET_PAN", OP_SET_PAN_V0),
    ("SET_PITCH", OP_SET_PITCH_V0),
];
/// The short waits, from OP_WAIT_1 to OP_WAIT_32: one byte closes the frame
/// and waits. Almost all of them fit; the rest go with OP_WAIT, sixteen bits.
const SHORT_WAIT: i64 = 32;

/// That the families and the short waits are where the format expects them.
pub fn check_families() -> std::result::Result<(), String> {
    for (k, (family, first)) in FAMILIES.iter().enumerate() {
        if *first as usize != 8 * k {
            return Err(format!("music.toml: OP_{family}_V0 is not where the family expects it"));
        }
    }
    if OP_WAIT_1 as usize != 8 * FAMILIES.len() || OP_WAIT_32 as i64 != OP_WAIT_1 as i64 + SHORT_WAIT - 1 {
        return Err("music.toml: the short waits are not after the families".into());
    }
    Ok(())
}

fn is_voice_register(register: u8) -> bool {
    register < 0x80 && register & 0x0F < VOICE_REGISTERS
}

/// What `OP_INIT` writes: the startup without KON or KOF, followed by KON
/// and KOF at zero.
pub fn boot_writes() -> Vec<(u8, u8)> {
    let mut out: Vec<(u8, u8)> = init_writes()
        .into_iter()
        .filter(|(r, _)| *r != sdsp::KON && *r != sdsp::KOF)
        .collect();
    out.push((sdsp::KON, 0x00));
    out.push((sdsp::KOF, 0x00));
    out
}

/// Builds a song's per-note stream. It keeps the same state as the 65816's
/// decoder —the voice register cache, each voice's sound, the frame's
/// accumulated KON— and the same cache as `writes`, so it decides each
/// event knowing exactly which writes it will produce.
struct Encoder {
    stream: Vec<u8>,
    sounds: Vec<Sound>,
    sound_index: HashMap<Sound, usize>,
    /// `writes`'s cache.
    state: HashMap<u8, u8>,
    /// The sound of each voice's last note.
    sound_of: HashMap<u8, usize>,
}

impl Encoder {
    fn sound(&mut self, p: &NoteSetup) -> usize {
        let key = [
            (p.pitch & 0xFF) as u8,
            (p.pitch >> 8) as u8,
            p.sample,
            p.adsr1,
            p.adsr2,
            p.gain.unwrap_or(0),
        ];
        if let Some(&i) = self.sound_index.get(&key) {
            return i;
        }
        self.sound_index.insert(key, self.sounds.len());
        self.sounds.push(key);
        self.sounds.len() - 1
    }

    fn changes(&self, register: u8, value: u8) -> bool {
        self.state.get(&register) != Some(&value)
    }

    fn write(&mut self, register: u8, value: u8) {
        self.state.insert(register, value);
    }

    fn op(&mut self, bytes: &[u8]) {
        self.stream.extend_from_slice(bytes);
    }

    /// A cached write outside the voices: it goes raw if it changes.
    fn global(&mut self, register: u8, value: u8) {
        assert!(!is_voice_register(register), "{register}");
        if self.changes(register, value) {
            self.write(register, value);
            self.op(&[OP_DSP, register, value]);
        }
    }

    fn note(&mut self, p: &NoteSetup) {
        let (v, base) = (p.voice, p.voice * 0x10);
        let s = self.sound(p) as u8;
        if !self.changes(base + sdsp::V_VOL_L, p.left) && !self.changes(base + sdsp::V_VOL_R, p.right) {
            self.op(&[OP_NOTE_V0 + v, s]);
        } else if p.left == p.right {
            self.op(&[OP_NOTE_VOL_V0 + v, p.left, s]);
        } else {
            self.op(&[OP_NOTE_PAN_V0 + v, p.left, p.right, s]);
        }
        self.sound_of.insert(v, s as usize);
        for (r, value) in p.writes() {
            self.write(r, value);
        }
    }

    fn release(&mut self, v: u8, gain: u8) {
        let base = v * 0x10;
        if !self.changes(base + sdsp::V_ADSR1, 0) && !self.changes(base + sdsp::V_GAIN, gain) {
            return; // it would write nothing
        }
        let own = self.sounds[self.sound_of[&v]][5];
        if own == gain {
            self.op(&[OP_RELEASE_V0 + v]);
        } else {
            self.op(&[OP_RELEASE_GAIN_V0 + v, gain]);
        }
        self.write(base + sdsp::V_ADSR1, 0);
        self.write(base + sdsp::V_GAIN, gain);
    }

    fn controls(&mut self, control: &BTreeMap<u8, u8>) {
        let mut by_voice: BTreeMap<u8, BTreeMap<u8, u8>> = BTreeMap::new();
        for (&register, &value) in control {
            assert!(
                is_voice_register(register),
                "a controller writes ${register:02X}, which is not a voice register"
            );
            by_voice.entry(register >> 4).or_default().insert(register & 0x0F, value);
        }
        for (v, regs) in by_voice {
            let base = v * 0x10;
            let keys: Vec<u8> = regs.keys().copied().collect();
            assert!(
                keys == [0, 1] || keys == [2, 3] || keys == [0, 1, 2, 3],
                "a controller writes to voice {v} the registers {keys:?}: the format only \
                 knows the volume pair and the pitch pair"
            );
            if let (Some(&l), Some(&r)) = (regs.get(&0), regs.get(&1)) {
                if self.changes(base, l) || self.changes(base + 1, r) {
                    if l == r {
                        self.op(&[OP_SET_VOL_V0 + v, l]);
                    } else {
                        self.op(&[OP_SET_PAN_V0 + v, l, r]);
                    }
                    self.write(base, l);
                    self.write(base + 1, r);
                }
            }
            if let (Some(&lo), Some(&hi)) = (regs.get(&2), regs.get(&3)) {
                if self.changes(base + 2, lo) || self.changes(base + 3, hi) {
                    self.op(&[OP_SET_PITCH_V0 + v, lo, hi]);
                    self.write(base + 2, lo);
                    self.write(base + 3, hi);
                }
            }
        }
    }

    fn wait(&mut self, n_frames: i64) {
        if (1..=SHORT_WAIT).contains(&n_frames) {
            self.op(&[OP_WAIT_1 + (n_frames - 1) as u8]);
        } else {
            self.op(&[OP_WAIT, (n_frames & 0xFF) as u8, (n_frames >> 8) as u8]);
        }
    }
}

/// The song in the per-note format: (stream, sounds). What the stream
/// produces in the DSP is **exactly** `writes(frames, length, init)`.
pub fn pack(frames: &Frames, length: i64, init: &[(u8, u8)]) -> Result<(Vec<u8>, Vec<Sound>)> {
    let mut c = Encoder {
        stream: Vec::new(),
        sounds: Vec::new(),
        sound_index: HashMap::new(),
        state: HashMap::new(),
        sound_of: HashMap::new(),
    };
    if init == boot_writes().as_slice() {
        c.op(&[OP_INIT]);
        for &(r, v) in init {
            c.write(r, v);
        }
    } else {
        for &(r, v) in init {
            c.global(r, v);
        }
    }

    let (mut previous, mut sounding) = (0i64, 0u8);
    for (&at, frame) in frames {
        if at > length {
            break;
        }
        if frame.is_empty() {
            continue;
        }
        if at > previous {
            // The decoder clears KON on opening; what counts at the end is
            // the last frame's, set below.
            c.wait(at - previous);
        }
        previous = at;
        c.global(sdsp::KOF, 0x00);
        for &(voice, gain) in &frame.release {
            c.release(voice, gain);
        }
        let mut kon = 0u8;
        for p in &frame.setup {
            c.note(p);
            kon |= 1 << p.voice;
        }
        c.controls(&frame.control);
        if frame.kof != 0 {
            c.global(sdsp::KOF, frame.kof);
        }
        assert_eq!(kon, frame.kon, "the frame's KON is not its notes' KON");
        sounding = kon;
    }

    // The end: `writes` clears KON and shuts everything off in frame
    // `length`.
    if length > previous {
        c.wait(length - previous);
        if sounding == 0 {
            c.op(&[OP_DSP, sdsp::KON, 0x00]);
        }
    } else {
        c.op(&[OP_WAIT, 0, 0]); // fires the KON without waiting
        c.op(&[OP_DSP, sdsp::KON, 0x00]);
    }
    c.op(&[OP_DSP, sdsp::KOF, 0xFF]);
    c.op(&[OP_END]);
    if c.sounds.len() > 256 {
        return Err(Bad::answer(format!(
            "the song uses {} sounds and the index is one byte",
            c.sounds.len()
        )));
    }
    Ok((c.stream, c.sounds))
}

/// The model of the 65816's decoder —`music_frame`—, step by step: what the
/// stream writes, up to its `OP_END`. It has to give the same as `writes`.
///
/// It also imitates what the 65816 does **not** know. Its cache has no
/// "empty": when the song starts it holds whatever was left, and what stands
/// in for that is that each voice's first note writes everything without
/// looking, and the first release writes its GAIN regardless. If the stream
/// ever compared against a register nobody has written yet, on the console
/// it would be comparing against garbage: here that stops.
pub fn decode(stream: &[u8], sounds: &[Sound]) -> Result<Vec<Write>> {
    Ok(decode_counting(stream, sounds)?.0)
}

/// [`decode`], and how many bytes the stream took, its `OP_END` included:
/// whoever reads it from a cartridge learns where it ends.
pub fn decode_counting(stream: &[u8], sounds: &[Sound]) -> Result<(Vec<Write>, usize)> {
    let mut out = Vec::new();
    let mut cache: HashMap<u8, u8> = HashMap::new();
    let (mut seen, mut with_gain): (HashSet<u8>, HashSet<u8>) = (HashSet::new(), HashSet::new());
    let mut gain_of: HashMap<u8, u8> = HashMap::new();
    let (mut frame_no, mut kon, mut sounding, mut i) = (0i64, 0u8, 0u8, 0usize);
    // Inside an `OP_REPEAT`: where it comes back to, and how many of its
    // events are left to read. The 65816 keeps the same two things.
    let (mut back_to, mut left): (Option<usize>, u8) = (None, 0);
    let bad = |m: String| Bad::answer(m);

    let read = |i: &mut usize| -> Result<u8> {
        let b = *stream.get(*i).ok_or_else(|| bad("the stream ends without OP_END".into()))?;
        *i += 1;
        Ok(b)
    };

    fn write(
        out: &mut Vec<Write>,
        cache: &mut HashMap<u8, u8>,
        frame_no: i64,
        register: u8,
        value: u8,
        force: bool,
    ) -> Result<()> {
        if !force {
            match cache.get(&register) {
                None => {
                    return Err(Bad::answer(format!(
                        "the stream compares register ${register:02X} against the cache before \
                         writing it: in the ROM it would be garbage"
                    )))
                }
                Some(&v) if v == value => return Ok(()),
                _ => {}
            }
        }
        cache.insert(register, value);
        out.push((frame_no, register, value));
        Ok(())
    }

    loop {
        // Before each event, as `music_frame::read` does: once the repeat's
        // last one was read, back to where it was.
        if let Some(to) = back_to {
            if left == 0 {
                i = to;
                back_to = None;
            } else {
                left -= 1;
            }
        }
        let op = read(&mut i)?;
        if back_to.is_some() && !repeatable(op) {
            return Err(bad(format!("opcode ${op:02X} inside an OP_REPEAT: it has one level")));
        }
        if op == OP_END {
            return Ok((out, i));
        }
        if op == OP_REPEAT {
            let at = i - 1;
            let back = read(&mut i)? as usize | (read(&mut i)? as usize) << 8;
            let events = read(&mut i)?;
            if !(1..=REPEAT_MAX_EVENTS).contains(&events) {
                return Err(bad(format!("an OP_REPEAT of {events} events")));
            }
            if back > i || i - back >= at {
                return Err(bad(format!("the OP_REPEAT at {at} goes {back} bytes back")));
            }
            back_to = Some(i);
            left = events;
            i -= back;
            continue;
        }
        if op == OP_INIT {
            for (r, v) in boot_writes() {
                out.push((frame_no, r, v));
            }
            continue;
        }
        if op == OP_DSP {
            let (r, v) = (read(&mut i)?, read(&mut i)?);
            if is_voice_register(r) {
                return Err(bad(format!("OP_DSP writes ${r:02X}, a voice register")));
            }
            out.push((frame_no, r, v));
            continue;
        }
        if op == OP_WAIT || (OP_WAIT_1..OP_WAIT_1 + SHORT_WAIT as u8).contains(&op) {
            let n = if op == OP_WAIT {
                let lo = read(&mut i)? as i64;
                lo | (read(&mut i)? as i64) << 8
            } else {
                (op - OP_WAIT_1) as i64 + 1
            };
            if kon != 0 {
                out.push((frame_no, sdsp::KON, kon));
                sounding = kon;
                kon = 0;
            }
            if n != 0 {
                frame_no += n;
                if sounding != 0 {
                    out.push((frame_no, sdsp::KON, 0));
                    sounding = 0;
                }
            }
            continue;
        }
        if op >= OP_WAIT_1 {
            return Err(bad(format!("opcode ${op:02X}")));
        }
        let (family, v) = (FAMILIES[(op >> 3) as usize].0, op & 7);
        let base = v * 0x10;
        match family {
            "NOTE" | "NOTE_VOL" | "NOTE_PAN" => {
                // The voice's first note writes everything: see above.
                let force = seen.insert(v);
                if family == "NOTE_VOL" {
                    let vol = read(&mut i)?;
                    write(&mut out, &mut cache, frame_no, base + sdsp::V_VOL_L, vol, force)?;
                    write(&mut out, &mut cache, frame_no, base + sdsp::V_VOL_R, vol, force)?;
                } else if family == "NOTE_PAN" {
                    let (l, r) = (read(&mut i)?, read(&mut i)?);
                    write(&mut out, &mut cache, frame_no, base + sdsp::V_VOL_L, l, force)?;
                    write(&mut out, &mut cache, frame_no, base + sdsp::V_VOL_R, r, force)?;
                }
                let index = read(&mut i)? as usize;
                let sound = *sounds
                    .get(index)
                    .ok_or_else(|| bad(format!("sound {index} of {}", sounds.len())))?;
                for k in 0..5u8 {
                    // from PITCH_L to ADSR2, in that order
                    write(&mut out, &mut cache, frame_no, base + sdsp::V_PITCH_L + k, sound[k as usize], force)?;
                }
                gain_of.insert(v, sound[5]);
                kon |= 1 << v;
            }
            "RELEASE" | "RELEASE_GAIN" => {
                let gain = if family == "RELEASE_GAIN" {
                    read(&mut i)?
                } else {
                    *gain_of.get(&v).ok_or_else(|| bad(format!("voice {v} is released before any note")))?
                };
                write(&mut out, &mut cache, frame_no, base + sdsp::V_ADSR1, 0, false)?;
                let force = !with_gain.contains(&v);
                write(&mut out, &mut cache, frame_no, base + sdsp::V_GAIN, gain, force)?;
                with_gain.insert(v);
            }
            "SET_VOL" => {
                let vol = read(&mut i)?;
                write(&mut out, &mut cache, frame_no, base + sdsp::V_VOL_L, vol, false)?;
                write(&mut out, &mut cache, frame_no, base + sdsp::V_VOL_R, vol, false)?;
            }
            "SET_PAN" => {
                let (l, r) = (read(&mut i)?, read(&mut i)?);
                write(&mut out, &mut cache, frame_no, base + sdsp::V_VOL_L, l, false)?;
                write(&mut out, &mut cache, frame_no, base + sdsp::V_VOL_R, r, false)?;
            }
            _ => {
                let (lo, hi) = (read(&mut i)?, read(&mut i)?);
                write(&mut out, &mut cache, frame_no, base + sdsp::V_PITCH_L, lo, false)?;
                write(&mut out, &mut cache, frame_no, base + sdsp::V_PITCH_H, hi, false)?;
            }
        }
    }
}

// --- repeats -----------------------------------------------------------------
//
// A song plays the same bars again, and its stream says them again byte for
// byte: the decoder's state —the register cache, each voice's sound— depends
// only on the bytes it read, so the same events in the same order write the
// same. `fold` replaces a run of events the stream already has, as written,
// with an `OP_REPEAT` that goes back and reads them there. One level: what it
// goes back to is plain events, never another repeat, so the 65816 keeps one
// return address and one count —see `music_frame::read`—.
//
// What a repeat reads is **the same bytes**, so `unfold` gives back the stream
// `pack` wrote, and `fold` checks that before returning. The writes are
// checked apart, through `decode`, which follows the repeats as the 65816
// does: see `check`.

/// How many events an `OP_REPEAT` may read: the 65816 counts them in a byte,
/// starting at one more than this, and goes back when it reaches zero.
pub const REPEAT_MAX_EVENTS: u8 = 254;
/// What an `OP_REPEAT` takes: the opcode, how far back, how many events.
const REPEAT_BYTES: usize = 4;
/// How far back it can go: the distance is a word.
const REPEAT_MAX_BACK: usize = 0xFFFF;
/// The shortest run worth a repeat, in bytes. Not five, which is the first
/// that saves one: a repeat leaves what it covers out of what later ones can
/// go back to, and a short one that saves a byte or two keeps a long one from
/// happening further on. Measured on a hundred songs, with the lazy step of
/// `fold`: five folds 20% off the streams, seven 23.5%, eight 23.1%, ten
/// 21.3%.
const REPEAT_MIN_BYTES: usize = 7;

fn opcode_size(op: u8) -> Option<usize> {
    OPCODE_SIZE.iter().find(|(o, _)| *o == op).map(|(_, n)| *n)
}

/// Whether an `OP_REPEAT` may read this opcode.
fn repeatable(op: u8) -> bool {
    !matches!(op, OP_END | OP_INIT | OP_REPEAT)
}

/// The events of a stream, as ranges of bytes, up to its `OP_END` included.
fn events_of(stream: &[u8]) -> Result<Vec<std::ops::Range<usize>>> {
    let mut out = Vec::new();
    let mut i = 0;
    loop {
        let op = *stream.get(i).ok_or_else(|| Bad::answer("the stream ends without OP_END"))?;
        let n = opcode_size(op).ok_or_else(|| Bad::answer(format!("opcode ${op:02X} at {i}")))?;
        if i + n > stream.len() {
            return Err(Bad::answer(format!("the stream ends inside the event at {i}")));
        }
        out.push(i..i + n);
        i += n;
        if op == OP_END {
            return Ok(out);
        }
    }
}

/// The stream with each run of events it already said, as written, replaced
/// by an `OP_REPEAT` that reads it there: from left to right, at each event
/// the run that saves the most bytes, if it is at least `REPEAT_MIN_BYTES`
/// long. What it gives back writes exactly the same; it checks that `unfold`
/// gives back `stream` before returning.
pub fn fold(stream: &[u8]) -> Result<Vec<u8>> {
    let events = events_of(stream)?;
    let bytes = |k: usize| &stream[events[k].clone()];
    let n = events.len();
    let mut out: Vec<u8> = Vec::with_capacity(stream.len());
    // Where each event went in `out`, if it went as itself: only those can be
    // gone back to.
    let mut placed: Vec<Option<usize>> = vec![None; n];
    // Where each pair of consecutive placed events starts, by their bytes: a
    // repeat that pays reads at least two, because one event takes at most
    // four bytes, which is what the repeat costs.
    let pair = |k: usize| &stream[events[k].start..events[k + 1].end];
    let mut pairs: HashMap<&[u8], Vec<usize>> = HashMap::new();
    // The run that saves the most if the repeat goes at event `k` and `out`
    // is `at` bytes long: (saves, from, events).
    let best_at = |k: usize, at: usize, placed: &[Option<usize>], pairs: &HashMap<&[u8], Vec<usize>>| {
        let mut best: Option<(usize, usize, usize)> = None;
        let candidates = if k + 1 < n { pairs.get(pair(k)).map(|v| v.as_slice()) } else { None };
        for &from in candidates.unwrap_or(&[]).iter().rev() {
            let start = placed[from].expect("only placed events are indexed");
            if at + REPEAT_BYTES - start > REPEAT_MAX_BACK {
                break; // the older ones are farther still
            }
            let (mut len, mut size) = (0usize, 0usize);
            while len < REPEAT_MAX_EVENTS as usize
                && from + len < k
                && k + len < n
                && placed[from + len].is_some()
                && repeatable(stream[events[from + len].start])
                && bytes(from + len) == bytes(k + len)
            {
                size += bytes(k + len).len();
                len += 1;
            }
            if size >= REPEAT_MIN_BYTES && best.map_or(true, |(saves, _, _)| size - REPEAT_BYTES > saves) {
                best = Some((size - REPEAT_BYTES, from, len));
            }
        }
        best
    };
    let mut k = 0;
    while k < n {
        let mut best = best_at(k, out.len(), &placed, &pairs);
        if let Some((saves, _, _)) = best {
            // Lazy: if the event after this one starts a run that saves more
            // than what this one costs as itself, this one goes as itself.
            // It is worth little —a tenth of a percent—, and costs nothing.
            if let Some((next, _, _)) = best_at(k + 1, out.len() + bytes(k).len(), &placed, &pairs) {
                if next > saves + bytes(k).len() {
                    best = None;
                }
            }
        }
        if let Some((_, from, len)) = best {
            let back = out.len() + REPEAT_BYTES - placed[from].unwrap();
            out.extend_from_slice(&[OP_REPEAT, back as u8, (back >> 8) as u8, len as u8]);
            k += len;
            continue;
        }
        placed[k] = Some(out.len());
        out.extend_from_slice(bytes(k));
        if k >= 1
            && placed[k - 1].is_some()
            && repeatable(stream[events[k - 1].start])
            && repeatable(stream[events[k].start])
        {
            pairs.entry(pair(k - 1)).or_default().push(k - 1);
        }
        k += 1;
    }
    if unfold(&out)? != stream[..events[n - 1].end] {
        return Err(Bad::answer("folding the stream changed what it says"));
    }
    Ok(out)
}

/// The stream with each `OP_REPEAT` replaced by the events it reads: what
/// `pack` wrote before `fold`.
pub fn unfold(stream: &[u8]) -> Result<Vec<u8>> {
    let mut out = Vec::with_capacity(stream.len() * 2);
    for event in events_of(stream)? {
        let e = &stream[event.clone()];
        if e[0] != OP_REPEAT {
            out.extend_from_slice(e);
            continue;
        }
        let back = e[1] as usize | (e[2] as usize) << 8;
        let wrong = || Bad::answer(format!("the OP_REPEAT at {} goes {back} bytes back", event.start));
        let mut i = event.end.checked_sub(back).filter(|&f| f < event.start).ok_or_else(wrong)?;
        for _ in 0..e[3] {
            let op = stream[i];
            let size = opcode_size(op).filter(|_| repeatable(op)).ok_or_else(|| {
                Bad::answer(format!("the OP_REPEAT at {} reads opcode ${op:02X}", event.start))
            })?;
            out.extend_from_slice(&stream[i..i + size]);
            i += size;
        }
    }
    Ok(out)
}

/// How many `OP_REPEAT` the stream has.
pub fn repeats(stream: &[u8]) -> Result<usize> {
    Ok(events_of(stream)?.iter().filter(|e| stream[e.start] == OP_REPEAT).count())
}

/// That a song's stream, decoded, writes the same as `writes`: every
/// register, every value, in the same order and the same frame.
pub fn check(name: &str, stream: &[u8], sounds: &[Sound], reference: &[Write]) -> Result<()> {
    let out = decode(stream, sounds)?;
    if out == reference {
        return Ok(());
    }
    let n = out
        .iter()
        .zip(reference)
        .position(|(a, b)| a != b)
        .unwrap_or(out.len().min(reference.len()));
    let show = |w: Option<&Write>| w.map_or("none".to_string(), |w| format!("{w:?}"));
    Err(Bad::answer(format!(
        "the stream of {name} does not write what it has to write: write {n} is {} and it had \
         to be {} (frame, register, value)",
        show(out.get(n)),
        show(reference.get(n))
    )))
}

/// Which samples a song uses: the values its stream writes to the voices'
/// SRCN registers. It is what the ROM has to have in the ARAM to play it,
/// taken from what the song does —its stream, decoded— and not from how it
/// was built.
pub fn samples_of(stream: &[u8], sounds: &[Sound]) -> Result<Vec<u8>> {
    let mut used: Vec<u8> = decode(stream, sounds)?
        .into_iter()
        .filter(|&(_, r, _)| is_voice_register(r) && r & 0x0F == sdsp::V_SRCN)
        .map(|(_, _, v)| v)
        .collect();
    used.sort();
    used.dedup();
    Ok(used)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_declaration_puts_the_families_where_the_format_wants_them() {
        check_families().unwrap();
    }

    #[test]
    fn an_empty_song_is_the_startup_and_the_shutdown() {
        let frames = Frames::new();
        let reference = writes(&frames, 0, &init_writes());
        let (stream, sounds) = pack(&frames, 0, &init_writes()).unwrap();
        assert_eq!(decode(&stream, &sounds).unwrap(), reference);
        assert_eq!(stream[0], OP_INIT);
        assert_eq!(*stream.last().unwrap(), OP_END);
    }

    /// A song that plays the same bar four times, the bar being a note on two
    /// voices, a release and a wait, with another note in between the
    /// second and the third.
    fn bars() -> (Vec<u8>, Vec<Sound>) {
        let sounds = vec![[0x00, 0x10, 0, 0x8F, 0xE0, 0x9C], [0x00, 0x20, 1, 0x8F, 0xE0, 0x9C]];
        let bar = [
            OP_NOTE_VOL_V0, 0x40, 0,
            OP_NOTE_VOL_V1, 0x30, 1,
            OP_WAIT_1 + 7,
            OP_RELEASE_V0,
            OP_RELEASE_V1,
            OP_WAIT_1 + 3,
        ];
        let mut stream = vec![OP_INIT];
        stream.extend_from_slice(&bar);
        stream.extend_from_slice(&bar);
        stream.extend_from_slice(&[OP_NOTE_V0, 1, OP_WAIT_1]);
        stream.extend_from_slice(&bar);
        stream.extend_from_slice(&bar);
        stream.extend_from_slice(&[OP_DSP, sdsp::KOF, 0xFF, OP_END]);
        (stream, sounds)
    }

    #[test]
    fn folding_writes_the_same_frame_by_frame() {
        let (flat, sounds) = bars();
        let folded = fold(&flat).unwrap();
        assert!(folded.len() < flat.len(), "{} bytes, and before {}", folded.len(), flat.len());
        assert!(repeats(&folded).unwrap() >= 2);
        assert_eq!(unfold(&folded).unwrap(), flat);
        assert_eq!(decode(&folded, &sounds).unwrap(), decode(&flat, &sounds).unwrap());
        // `length` is the folded stream's: whoever reads it from a cartridge
        // finds its OP_END there.
        assert_eq!(decode_counting(&folded, &sounds).unwrap().1, folded.len());
    }

    #[test]
    fn a_repeat_goes_back_to_plain_events_only() {
        let (flat, _) = bars();
        let folded = fold(&flat).unwrap();
        let events = events_of(&folded).unwrap();
        for e in events.iter().filter(|e| folded[e.start] == OP_REPEAT) {
            let back = folded[e.start + 1] as usize | (folded[e.start + 2] as usize) << 8;
            let from = e.end - back;
            let read: Vec<_> = events.iter().skip_while(|f| f.start != from).take(folded[e.start + 3] as usize).collect();
            assert_eq!(read.len(), folded[e.start + 3] as usize, "it does not land on an event");
            assert!(read.iter().all(|f| repeatable(folded[f.start]) && f.end <= e.start));
        }
    }

    #[test]
    fn a_repeat_that_comes_back_to_the_wrong_place_writes_something_else() {
        let (flat, sounds) = bars();
        let folded = fold(&flat).unwrap();
        let at = events_of(&folded).unwrap().into_iter().find(|e| folded[e.start] == OP_REPEAT).unwrap();
        // One event less: it comes back before the bar ends.
        let mut wrong = folded.clone();
        wrong[at.start + 3] -= 1;
        assert_ne!(decode(&wrong, &sounds).ok(), Some(decode(&flat, &sounds).unwrap()));
    }

    #[test]
    fn a_repeat_inside_a_repeat_is_refused() {
        let (flat, sounds) = bars();
        let mut folded = fold(&flat).unwrap();
        let events = events_of(&folded).unwrap();
        let first = events.iter().find(|e| folded[e.start] == OP_REPEAT).unwrap().clone();
        // A second repeat that goes back to the first one.
        folded.pop();
        let end = folded.len() + REPEAT_BYTES;
        let back = end - first.start;
        folded.extend_from_slice(&[OP_REPEAT, back as u8, (back >> 8) as u8, 1, OP_END]);
        assert!(decode(&folded, &sounds).is_err());
        assert!(unfold(&folded).is_err());
    }
}
