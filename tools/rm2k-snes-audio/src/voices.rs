//! Which DSP voice each note plays on, and what it writes there, frame by
//! frame: [`build_events`].
//!
//! The eight voices belong to every channel and are allocated note by note:
//! a note takes a free voice, and if there is none, it steals another by
//! priority —see `victim`—, or it does not play. It is what a synthesizer
//! does when it runs out of polyphony. Until 2026-09-26 each channel had its
//! fixed voices, and a song with more chords than voices lost whole
//! instruments: 55% of the note-time in one of them, against the 23% that is
//! lost unavoidably with eight.

use crate::fail::Result;
use crate::midi::{self, Control, Note, TICKS_PER_SECOND};
use crate::num;
use crate::sdsp;
use crate::stream::{Frame, Frames, NoteSetup};
use std::collections::{BTreeMap, HashMap, HashSet};

/// What the allocation needs to know about a sample.
#[derive(Clone, Copy, Debug)]
pub struct SampleInfo {
    /// Which key sounds at `rate`.
    pub root: f64,
    pub rate: f64,
    /// How long it is, in samples: a hit sounds until it runs out.
    pub frames: i64,
}

/// The instruments a song plays with: which sample each program and each
/// hit is, and the envelope of each melodic note.
pub trait Instruments {
    fn sample(&self, index: usize) -> SampleInfo;
    /// The sample of a melodic program, if it has one.
    fn melodic(&self, program: u8) -> Option<usize>;
    /// The sample of a percussion key, if it has one.
    fn hit(&self, key: u8) -> Option<usize>;
    /// (ADSR1, ADSR2, release GAIN) of a melodic note.
    fn envelope(&self, program: u8, key: u8) -> Result<(u8, u8, u8)>;
}

/// Which voices each channel may take: all eight, every channel. It still
/// gives one group per channel because [`build_events`] accepts them
/// different, and the tests use that to build small cases.
pub fn assign(notes: &[Note]) -> BTreeMap<u8, Vec<u8>> {
    notes
        .iter()
        .map(|n| (n.channel, (0..sdsp::VOICES as u8).collect()))
        .collect()
}

/// The voice a sound effect plays on, stolen from the music.
pub const SE_VOICE: u8 = 7;
/// And the second, so two sound effects can play at once.
pub const SE_VOICE2: u8 = 6;
/// While a sound effect plays, what the music writes to its voice goes to a
/// shadow and not to the DSP, so whatever note was there goes silent. That
/// is why percussion hits, which last half a second, go there first, and
/// melodic notes only if no other voice is free.
const EFFECT_VOICES: [u8; 2] = [SE_VOICE2, SE_VOICE];

/// The GAIN used to bring down a voice that is playing one frame before
/// handing it to another note: linear, 64 steps of 6 samples, so it reaches
/// zero in 12 ms, before the next frame. What it avoids is the KON click,
/// which drops the envelope to zero at once.
pub const RAMP: u8 = sdsp::GAIN_LINEAR_DECREASE | 26;
const _: () = assert!(64 * sdsp::PERIOD[(RAMP & 0x1F) as usize] <= sdsp::SAMPLE_RATE / TICKS_PER_SECOND);

/// What the allocation knows about a voice: the note holding it, until when
/// it holds it —`end`— and until when it can be heard —`tail`, with the
/// release or however long the hit lasts—, and the volume it started with,
/// left plus right.
#[derive(Clone, Copy)]
struct Held {
    note: usize,
    end: i64,
    tail: i64,
    level: i64,
}

/// How many frames a voice released with that GAIN takes to go silent,
/// from the top: the linear one drops 1/64 per step, and the exponential
/// one reaches zero in `STEPS_TO_ZERO`.
fn release_frames(gain: u8) -> i64 {
    let period = sdsp::PERIOD[(gain & 0x1F) as usize];
    let steps = if gain & 0xE0 == sdsp::GAIN_LINEAR_DECREASE { 64 } else { sdsp::STEPS_TO_ZERO };
    ((steps * period * TICKS_PER_SECOND) as f64 / sdsp::SAMPLE_RATE as f64) as i64 + 1
}

/// The General MIDI hits that are the same instrument played another way:
/// two bass drums, two snares, the hi-hat closed, pedaled and open, two crash
/// cymbals, two rides. A MIDI asking for them together is thickening the
/// hit, not playing two. Not the toms: they are different drums and a roll
/// brings them together.
fn hit_family(key: u8) -> u8 {
    match key {
        35 | 36 => 35,
        38 | 40 => 38,
        42 | 44 | 46 => 42,
        49 | 57 => 49,
        51 | 59 => 51,
        _ => key,
    }
}

/// In which order the notes that start in the same frame pick a voice: when
/// there are not enough for all, the last ones are left out, because
/// `victim` does not steal from a note that started in the frame.
///
/// * **Hits first, one per family**, from loudest to softest: they are
///   short, and they are the rhythm.
/// * **Then the melodic notes, by their level divided by their place in
///   their channel**: each channel's loudest note goes with its level, the
///   second with half, the third with a third. That way the top voice of a
///   chord goes before a softer channel, but the second note of that chord
///   goes after, unless that channel is little more than a whisper.
/// * **Last, a family's repeated hit**, which only plays if there is a
///   voice to spare.
///
/// `levels` is each note's level with the frame's controllers, left plus
/// right. Until 2026-09-26 the order was by velocity, and a battle song with
/// every note at 127 gave all eight voices to its hits and basses before the
/// melody arrived: 214 of its 536 melody notes did not play.
fn frame_order(notes: &[usize], all: &[Note], levels: &HashMap<usize, i64>) -> Vec<usize> {
    let mut by_channel: BTreeMap<u8, Vec<usize>> = BTreeMap::new();
    for &n in notes {
        by_channel.entry(all[n].channel).or_default().push(n);
    }
    let mut place: HashMap<usize, (i64, f64)> = HashMap::new();
    for (channel, ns) in by_channel {
        let mut ns = ns.clone();
        if channel == midi::DRUM_CHANNEL {
            ns.sort_by_key(|&n| (-levels[&n], all[n].pitch));
            let mut seen = HashSet::new();
            for n in ns {
                let family = hit_family(all[n].pitch);
                let rank = if seen.contains(&family) { 2 } else { 0 };
                place.insert(n, (rank, -levels[&n] as f64));
                seen.insert(family);
            }
        } else {
            ns.sort_by_key(|&n| (-levels[&n], -(all[n].pitch as i64)));
            for (i, n) in ns.into_iter().enumerate() {
                place.insert(n, (1, -levels[&n] as f64 / (1.0 + i as f64)));
            }
        }
    }
    let mut out = notes.to_vec();
    out.sort_by(|a, b| {
        let (pa, pb) = (place[a], place[b]);
        pa.0.cmp(&pb.0)
            .then(pa.1.partial_cmp(&pb.1).unwrap())
            .then(all[*a].pitch.cmp(&all[*b].pitch))
    });
    out
}

/// What one note got: the note, its voice or None if it did not play, the
/// frame its voice was stolen in, and until when it holds it —the end of the
/// note, or of the sample if it is a hit shorter than the note—.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Allotted {
    pub note: usize,
    pub voice: Option<u8>,
    pub stolen: Option<i64>,
    pub end: i64,
}

/// The order among the free voices —the ones nobody holds at `t`—: the
/// lowest wins.
fn free_order(
    voice: u8,
    t: i64,
    holders: &HashMap<u8, Held>,
    note: &Note,
    all: &[Note],
    drums: bool,
) -> (bool, i64, bool, bool, u8) {
    let s = holders.get(&voice);
    // Silent ones first: reusing one that is still sounding in its tail cuts
    // it. Among the sounding ones, the one that dies out first.
    let sounding = s.is_some_and(|s| s.tail > t);
    (
        sounding,
        if sounding { s.unwrap().tail } else { 0 },
        // Hits go to the sound effect voices; melodic notes, to the rest.
        EFFECT_VOICES.contains(&voice) != drums,
        // And the one that had a note from the same channel: same instrument
        // and same volume, so the new note costs two bytes.
        s.is_none_or(|s| all[s.note].channel != note.channel),
        voice,
    )
}

/// Which voice `note` steals when every voice in its group is held, or None
/// if it steals none and does not play.
///
/// * The same key of the same channel sounding again steals from itself: it
///   is a synthesizer retriggering the note.
/// * Never from a note that started in this same frame, which would never
///   get to sound; nor from a channel's last voice, which would leave it
///   mute.
/// * Among the rest, from the weakest —the volume it started with— and, on
///   a tie, from the oldest.
/// * And the new note yields instead of stealing if its channel is already
///   sounding and the victim is another channel's last, or is louder than
///   it and its channel has no more voices than the new note's.
///
/// Measured on the 32 songs of a whole game, always stealing the oldest cuts
/// 2.5 times more notes while they sound, and always stealing the weakest
/// loses more note-time.
fn victim(
    note: &Note,
    t: i64,
    group: &[u8],
    holders: &HashMap<u8, Held>,
    all: &[Note],
    level: i64,
) -> Option<u8> {
    let mut by_channel: HashMap<u8, i64> = HashMap::new();
    for v in group {
        *by_channel.entry(all[holders[v].note].channel).or_default() += 1;
    }
    for &v in group {
        let s = &all[holders[&v].note];
        if s.channel == note.channel && s.pitch == note.pitch {
            return Some(v);
        }
    }
    let count = |c: u8| *by_channel.get(&c).unwrap_or(&0);
    // Another channel's last voice: stealing it leaves that channel mute. Not
    // the same channel's, which keeps sounding with the new note.
    let is_last = |s: &Held| all[s.note].channel != note.channel && count(all[s.note].channel) <= 1;
    let cost = |v: u8| {
        let s = &holders[&v];
        (all[s.note].start == t, is_last(s), s.level, all[s.note].start, v)
    };
    let v = *group.iter().min_by_key(|&&v| cost(v))?;
    let s = &holders[&v];
    if all[s.note].start == t {
        return None;
    }
    let theirs = all[s.note].channel;
    if count(note.channel) >= 1
        && theirs != note.channel
        && (is_last(s) || (s.level > level && count(theirs) <= count(note.channel)))
    {
        return None;
    }
    Some(v)
}

/// The writes to the DSP, frame by frame.
///
/// Each channel has its group of voices —all eight for everyone: see
/// [`assign`]—; a note that starts takes a free one, the one that cuts least
/// according to `free_order`, and if they are all held it steals the one
/// `victim` says, or it does not play.
///
/// `controls` are the song's, already in frames: volume, expression and pan
/// go into the volume of each side of the note, and bend into its pitch. A
/// frame's controls are applied before its notes, so the note starts with
/// the state the frame ends with; and a voice that was already sounding —or
/// is in its tail— gets its registers rewritten.
///
/// `allocation`, if given, is filled with what each note that has a sample
/// got: see [`Allotted`]. It is where the amount of lost note-time comes
/// from.
///
/// `headroom` is the ceiling of this song's voices, `sdsp::HEADROOM` or a
/// lower one.
#[allow(clippy::too_many_arguments)]
pub fn build_events(
    notes: &[Note],
    voices: &BTreeMap<u8, Vec<u8>>,
    programs: &BTreeMap<u8, u8>,
    bank: &dyn Instruments,
    controls: &[Control],
    mut allocation: Option<&mut Vec<Allotted>>,
    headroom: f64,
) -> Result<Frames> {
    let mut frames: Frames = BTreeMap::new();
    let ceiling = headroom / sdsp::HEADROOM;
    let program_of = |n: &Note| *programs.get(&n.channel).unwrap_or(&0);

    let mut state: HashMap<u8, HashMap<u16, f64>> = HashMap::new();
    let get = |state: &HashMap<u8, HashMap<u16, f64>>, channel: u8, number: u16| -> f64 {
        state
            .get(&channel)
            .and_then(|c| c.get(&number))
            .copied()
            .unwrap_or_else(|| midi::default_of(number))
    };
    let mut pending: Vec<&Control> = controls.iter().collect();
    pending.sort_by_key(|c| c.start);
    let mut next_control = 0;

    let sides = |state: &HashMap<u8, HashMap<u16, f64>>, note: &Note, drums: bool| -> (i64, i64) {
        let top = if drums { sdsp::ceiling_drum() } else { sdsp::ceiling() } as f64;
        sdsp::volume(
            note.velocity as f64,
            ceiling * top,
            get(state, note.channel, midi::VOLUME),
            get(state, note.channel, midi::EXPRESSION),
            get(state, note.channel, midi::PAN),
        )
    };
    let pitch = |state: &HashMap<u8, HashMap<u16, f64>>, note: &Note, drums: bool| -> i64 {
        if drums {
            // In General MIDI the note picks the instrument, not the pitch, so
            // each hit has its own sample and is played at its original
            // rate: transposing it would turn a bass drum into something
            // else. That is why the bend does not move it either.
            let drum = bank.sample(bank.hit(note.pitch).unwrap());
            return sdsp::pitch_for(drum.root, drum.root, drum.rate);
        }
        let instrument = bank.sample(bank.melodic(program_of(note)).unwrap());
        sdsp::pitch_for(
            note.pitch as f64 + get(state, note.channel, midi::BEND),
            instrument.root,
            instrument.rate,
        )
    };

    // Who owns each voice now: the last note that took it, with until when
    // it holds it and until when it can be heard. A note's release is only
    // scheduled at the end, and only if it reached its end still being the
    // owner: if another note stole the voice first, releasing it would
    // release the thief.
    let mut holders: HashMap<u8, Held> = HashMap::new();
    // The owners in the order each voice was first taken.
    let mut owner: Vec<(u8, usize)> = Vec::new();
    let mut robbed: HashMap<usize, i64> = HashMap::new();
    let mut sounded: Vec<(usize, u8, u8)> = Vec::new();
    let mut ramps: Vec<(i64, u8)> = Vec::new();
    let mut owner_entry: HashMap<u8, usize> = HashMap::new();

    // Applies the controllers up to frame `until`, and rewrites what changed
    // on the voices whose note is from that channel.
    let apply_controls = |until: Option<i64>,
                          next_control: &mut usize,
                          state: &mut HashMap<u8, HashMap<u16, f64>>,
                          owner: &Vec<(u8, usize)>,
                          frames: &mut Frames| {
        while *next_control < pending.len()
            && until.is_none_or(|u| pending[*next_control].start <= u)
        {
            let c = pending[*next_control];
            *next_control += 1;
            if get(state, c.channel, c.number) == c.value {
                continue;
            }
            state.entry(c.channel).or_default().insert(c.number, c.value);
            // `owner` still has the note after its end, so this also changes
            // the volume of a tail that is dying out, like fluidsynth.
            for &(voice, n) in owner {
                let note = &notes[n];
                if note.channel != c.channel {
                    continue;
                }
                let base = voice * 0x10;
                let drums = note.channel == midi::DRUM_CHANNEL;
                if c.number == midi::BEND {
                    if drums {
                        continue;
                    }
                    let step = pitch(state, note, drums);
                    let frame = &mut frames.entry(c.start).or_default().control;
                    frame.insert(base + sdsp::V_PITCH_L, (step & 0xFF) as u8);
                    frame.insert(base + sdsp::V_PITCH_H, (step >> 8) as u8);
                } else {
                    let (left, right) = sides(state, note, drums);
                    let frame = &mut frames.entry(c.start).or_default().control;
                    frame.insert(base + sdsp::V_VOL_L, left as u8);
                    frame.insert(base + sdsp::V_VOL_R, right as u8);
                }
            }
        }
    };

    let mut by_frame: BTreeMap<i64, Vec<usize>> = BTreeMap::new();
    for (i, n) in notes.iter().enumerate() {
        by_frame.entry(n.start).or_default().push(i);
    }
    for (frame_no, in_frame) in &by_frame {
        // The frame's controllers go before sorting it, because the order
        // goes by the level each note starts with.
        apply_controls(Some(*frame_no), &mut next_control, &mut state, &owner, &mut frames);
        let levels: HashMap<usize, i64> = in_frame
            .iter()
            .map(|&n| {
                let (l, r) = sides(&state, &notes[n], notes[n].channel == midi::DRUM_CHANNEL);
                (n, l + r)
            })
            .collect();
        for n in frame_order(in_frame, notes, &levels) {
            let note = &notes[n];
            let Some(group) = voices.get(&note.channel).filter(|g| !g.is_empty()) else {
                continue;
            };
            let program = program_of(note);
            let drums = note.channel == midi::DRUM_CHANNEL;
            // Before picking a voice: a note without a sample does not play,
            // and if it took the voice it would take the place of one that
            // does.
            let source = if drums { bank.hit(note.pitch) } else { bank.melodic(program) };
            let Some(source) = source else { continue };

            let step = pitch(&state, note, drums);
            let (left, right) = sides(&state, note, drums);
            let (adsr1, adsr2, gain, end, tail);
            if drums {
                // Instant attack and no decay: the hit already carries its own
                // shape, the envelope only shuts it off at the end. It has no
                // release, so no GAIN either: it is heard until the sample
                // runs out. But the voice holds it only until the note's end
                // in the MIDI, and what follows is like a release tail:
                // another note can take it.
                (adsr1, adsr2, gain) = (0x8F, 0xE0, None);
                let sample = bank.sample(source);
                tail = note.start
                    + ((sample.frames * TICKS_PER_SECOND) as f64 / sample.rate).ceil() as i64;
                end = tail.min(note.end);
            } else {
                let (a1, a2, g) = bank.envelope(program, note.pitch)?;
                (adsr1, adsr2, gain) = (a1, a2, Some(g));
                end = note.end;
                tail = note.end + release_frames(g);
            }

            let t = note.start;
            let free: Vec<u8> = group
                .iter()
                .copied()
                .filter(|v| holders.get(v).is_none_or(|h| h.end <= t))
                .collect();
            let voice = if !free.is_empty() {
                free.iter()
                    .copied()
                    .min_by_key(|&v| free_order(v, t, &holders, note, notes, drums))
            } else {
                victim(note, t, group, &holders, notes, left + right)
            };
            let Some(voice) = voice else {
                if let Some(a) = allocation.as_deref_mut() {
                    a.push(Allotted { note: n, voice: None, stolen: None, end });
                }
                continue;
            };
            if let Some(&(_, previous_note)) = owner.iter().find(|(v, _)| *v == voice) {
                robbed.entry(previous_note).or_insert(t);
                if let (Some(&k), Some(a)) = (owner_entry.get(&voice), allocation.as_deref_mut()) {
                    a[k].stolen = Some(t);
                }
                // If the voice is still sounding, it is brought down to zero in
                // the frame before: KON drops the envelope to zero at once,
                // and that is a click. Not for a note that started in that
                // same frame, which is prepared after the release and undoes
                // it.
                let previous = holders[&voice];
                if previous.tail > t - 1 && notes[previous.note].start < t - 1 {
                    ramps.push((t - 1, voice));
                }
            }
            holders.insert(voice, Held { note: n, end, tail, level: left + right });
            match owner.iter_mut().find(|(v, _)| *v == voice) {
                Some(entry) => entry.1 = n,
                None => owner.push((voice, n)),
            }
            if let Some(a) = allocation.as_deref_mut() {
                a.push(Allotted { note: n, voice: Some(voice), stolen: None, end });
                owner_entry.insert(voice, a.len() - 1);
            }

            let start = frames.entry(note.start).or_default();
            let base = voice * 0x10;
            // What the controllers were rewriting for the previous owner in
            // this frame no longer applies: this note writes its own, with
            // the same state.
            for register in [sdsp::V_VOL_L, sdsp::V_VOL_R, sdsp::V_PITCH_L, sdsp::V_PITCH_H] {
                start.control.remove(&(base + register));
            }
            start.setup.push(NoteSetup {
                voice,
                left: left as u8,
                right: right as u8,
                pitch: step as u16,
                sample: source as u8,
                adsr1,
                adsr2,
                gain,
            });
            start.kon |= 1 << voice;
            if let Some(g) = gain {
                sounded.push((n, voice, g));
            }
        }
    }
    // The ones left after the last note: a fade at the end of a song is CC7
    // over the notes that were already sounding.
    apply_controls(None, &mut next_control, &mut state, &owner, &mut frames);

    for (n, voice, gain) in sounded {
        // Stolen in the same frame it ends in is not released either: the
        // thief writes its ADSR1 after the release and undoes it, so it
        // would be six bytes that do nothing.
        if robbed.get(&n).is_some_and(|&t| t <= notes[n].end) {
            continue;
        }
        frames.entry(notes[n].end).or_insert_with(Frame::default).release.push((voice, gain));
    }
    // Ramps go after their frame's releases, to win over them.
    for (frame_no, voice) in ramps {
        frames.entry(frame_no).or_default().release.push((voice, RAMP));
    }
    Ok(frames)
}

/// (what is lost, the floor): what fraction of the note-time of notes with
/// a sample does not play for lack of voices, and what fraction could not
/// play under any rule —whatever goes beyond eight notes at once—.
///
/// Note-time is how long the note holds its voice. It is lost entirely if
/// the note gets no voice, and from the moment of the steal if its voice is
/// stolen before that end. The release tail does not count: it is not in
/// the MIDI.
pub fn lost_time(allocation: &[Allotted], notes: &[Note]) -> (f64, f64) {
    let (mut total, mut lost) = (0i64, 0i64);
    let mut spans = Vec::new();
    for a in allocation {
        let start = notes[a.note].start;
        let length = a.end - start;
        total += length;
        spans.push((start, a.end));
        if a.voice.is_none() {
            lost += length;
        } else if let Some(stolen) = a.stolen {
            lost += (a.end - stolen).max(0);
        }
    }
    let floor: i64 = midi::note_time(&spans)
        .iter()
        .map(|(&n, &frames)| (n - sdsp::VOICES as i64).max(0) * frames)
        .sum();
    (
        lost as f64 / total.max(1) as f64,
        floor as f64 / total.max(1) as f64,
    )
}

/// Rounds for printing a percentage, as the reports have always done.
pub fn percent(x: f64) -> i64 {
    num::round(100.0 * x)
}

#[cfg(test)]
mod tests;
