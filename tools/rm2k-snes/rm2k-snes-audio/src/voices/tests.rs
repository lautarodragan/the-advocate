//! Which voice each note goes to, when it is released and with which
//! volume and pitch.
//!
//! They run no ROM: the notes and the bank are built by hand, just big
//! enough for what is looked at to happen, and what is looked at is what the
//! stream writes to the DSP —the per-note stream packed and decoded, which
//! has to give `writes`: the same the ROM will send it—.

use super::*;
use crate::midi::Control;
use crate::stream::{self, Write};

const PIANO: u8 = 0;
const BASS_DRUM: u8 = 36;
const NO_SAMPLE: u8 = 35;

/// The piano and the bass drum, one second each at 16 kHz, and nothing for
/// key 35. The envelope is the same for every note.
struct Bank {
    samples: Vec<SampleInfo>,
    melodic: HashMap<u8, usize>,
    hits: HashMap<u8, usize>,
}

impl Bank {
    fn new() -> Bank {
        let one = SampleInfo { root: 60.0, rate: 16000.0, frames: 16000 };
        Bank {
            samples: vec![one, one],
            melodic: HashMap::from([(PIANO, 0)]),
            hits: HashMap::from([(BASS_DRUM, 1)]),
        }
    }

    /// With more hits: 35, 38, 40 and 42.
    fn with_drums() -> Bank {
        let mut b = Bank::new();
        for key in [35, 38, 40, 42] {
            b.hits.insert(key, b.samples.len());
            b.samples.push(b.samples[0]);
        }
        b
    }
}

impl Instruments for Bank {
    fn sample(&self, index: usize) -> SampleInfo {
        self.samples[index]
    }
    fn melodic(&self, program: u8) -> Option<usize> {
        self.melodic.get(&program).copied()
    }
    fn hit(&self, key: u8) -> Option<usize> {
        self.hits.get(&key).copied()
    }
    fn envelope(&self, _program: u8, _key: u8) -> Result<(u8, u8, u8)> {
        Ok((0x8F, 0xE0, sdsp::GAIN_EXP_DECREASE | 12))
    }
}

fn note(start: i64, end: i64, channel: u8, pitch: u8) -> Note {
    Note::new(start, end, channel, pitch, 100)
}

/// What the song writes to the DSP: the per-note stream packed and decoded,
/// which has to give `writes`.
fn released(frames: &Frames, length: i64) -> Vec<Write> {
    let init = stream::init_writes();
    let (bytes, sounds) = stream::pack(frames, length, &init).unwrap();
    let out = stream::decode(&bytes, &sounds).unwrap();
    assert_eq!(out, stream::writes(frames, length, &init));
    out
}

fn voices_of(pairs: &[(u8, &[u8])]) -> BTreeMap<u8, Vec<u8>> {
    pairs.iter().map(|(c, v)| (*c, v.to_vec())).collect()
}

fn build(notes: &[Note], voices: BTreeMap<u8, Vec<u8>>, bank: &Bank) -> Vec<Write> {
    let programs = BTreeMap::from([(0, PIANO)]);
    let frames = build_events(notes, &voices, &programs, bank, &[], None, sdsp::HEADROOM).unwrap();
    released(&frames, notes.iter().map(|n| n.end).max().unwrap() + 10)
}

/// Per voice, the frames of its KONs and of its releases —ADSR1 at zero,
/// which is what hands control to GAIN—. An ADSR1 at zero with the ramp's
/// GAIN is not a release but the ramp before a steal, and does not count.
fn read(out: &[Write]) -> (BTreeMap<u8, Vec<i64>>, BTreeMap<u8, Vec<i64>>) {
    let (mut kon, mut off, mut gain) = (BTreeMap::new(), Vec::new(), HashMap::new());
    for &(frame, register, value) in out {
        if register == sdsp::KON {
            for voice in 0..8u8 {
                if value >> voice & 1 != 0 {
                    kon.entry(voice).or_insert_with(Vec::new).push(frame);
                }
            }
        } else if register < 0x80 && register & 0x0F == sdsp::V_ADSR1 && value == 0 {
            off.push((frame, register >> 4));
        } else if register < 0x80 && register & 0x0F == sdsp::V_GAIN {
            gain.insert((frame, register >> 4), value);
        }
    }
    let mut release = BTreeMap::new();
    for (frame, voice) in off {
        if gain.get(&(frame, voice)) != Some(&RAMP) {
            release.entry(voice).or_insert_with(Vec::new).push(frame);
        }
    }
    (kon, release)
}

/// (frame, voice register, value) of each write to `voice`, in order.
fn writes_to(out: &[Write], voice: u8) -> Vec<(i64, u8, u8)> {
    out.iter()
        .filter(|(_, r, _)| r >> 4 == voice && r & 0x0F < 8)
        .map(|&(c, r, v)| (c, r & 0x0F, v))
        .collect()
}

fn registers(out: &[Write], voice: u8, register: u8) -> Vec<u8> {
    writes_to(out, voice).into_iter().filter(|w| w.1 == register).map(|w| w.2).collect()
}

/// One channel with one voice: the second note steals the voice from the
/// first halfway through and lasts longer than it. The first one's release
/// —frame 100— used to land on the second, which went silent a hundred
/// frames before its end.
#[test]
fn a_stolen_note_does_not_release_the_thief() {
    let out = build(&[note(0, 100, 0, 60), note(50, 200, 0, 60)], voices_of(&[(0, &[0])]), &Bank::new());
    let (kon, release) = read(&out);
    assert_eq!(kon[&0], [0, 50]);
    assert_eq!(release[&0], [200], "the second note ends at 200");
}

/// It ends at 100 and another starts at 100 on the same voice: the
/// stealing note re-arms the ADSR after the release, so the release does
/// nothing and is left out.
#[test]
fn a_note_stolen_on_its_last_frame_writes_no_release() {
    let out = build(&[note(0, 100, 0, 60), note(100, 150, 0, 60)], voices_of(&[(0, &[0])]), &Bank::new());
    let (kon, release) = read(&out);
    assert_eq!(kon[&0], [0, 100]);
    assert_eq!(release[&0], [150]);
}

/// The drums with two voices: a bass drum on 6, a key the bank does not
/// have, and another bass drum overlapping the first. If the key without a
/// sample took 7, the second bass drum would steal 6 from the first, which
/// is still sounding, while 7 is silent.
#[test]
fn a_note_without_a_sample_takes_no_voice() {
    let d = midi::DRUM_CHANNEL;
    let notes = [note(0, 30, d, BASS_DRUM), note(5, 100, d, NO_SAMPLE), note(10, 40, d, BASS_DRUM)];
    let (kon, _) = read(&build(&notes, voices_of(&[(d, &[6, 7])]), &Bank::new()));
    assert_eq!((kon.get(&6).cloned(), kon.get(&7).cloned()), (Some(vec![0]), Some(vec![10])));
}

/// The notes with the voices from `assign` —all eight for everyone—: what
/// came out and which voice each one went to.
fn allocate(notes: &[Note], bank: &Bank) -> (Vec<Write>, Vec<Allotted>) {
    let programs: BTreeMap<u8, u8> =
        (0..16).filter(|&c| c != midi::DRUM_CHANNEL).map(|c| (c, PIANO)).collect();
    let mut allotted = Vec::new();
    let frames =
        build_events(notes, &assign(notes), &programs, bank, &[], Some(&mut allotted), sdsp::HEADROOM)
            .unwrap();
    (released(&frames, notes.iter().map(|n| n.end).max().unwrap() + 10), allotted)
}

/// Seven melodic channels and the drums, taking turns, and channel 0 plays
/// a four-note chord. With the fixed per-channel allocation the drums took
/// two voices, the six busiest channels one each, the seventh none, and
/// only one note of the chord sounded.
#[test]
fn a_chord_sounds_whole_with_more_channels_than_voices() {
    let mut notes: Vec<Note> = (0..7).map(|c| note(100 * c as i64, 100 * c as i64 + 50, c, 60)).collect();
    notes.push(note(700, 750, midi::DRUM_CHANNEL, BASS_DRUM));
    notes.extend([0, 4, 7, 12].map(|k| note(800, 900, 0, 60 + k)));
    let (out, allotted) = allocate(&notes, &Bank::new());
    let without: Vec<_> = allotted.iter().filter(|a| a.voice.is_none()).map(|a| a.note).collect();
    assert!(without.is_empty(), "notes without a voice while voices were free: {without:?}");
    let (kon, _) = read(&out);
    let in_chord = kon.values().filter(|frames| frames.contains(&800)).count();
    assert_eq!(in_chord, 4, "of the four-note chord {in_chord} voices sound");
}

/// A deterministic stand-in for a random song.
struct Lcg(u64);

impl Lcg {
    fn below(&mut self, n: u64) -> u64 {
        self.0 = self.0.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        (self.0 >> 33) % n
    }
}

/// A made-up song, with more polyphony than voices at times: a note that
/// gets no voice can only be one that arrives with all eight held.
#[test]
fn no_note_goes_without_a_voice_if_one_is_free() {
    let mut r = Lcg(5);
    let channels = [0, 1, 2, 3, 4, 5, 6, 7, 8, midi::DRUM_CHANNEL];
    let notes: Vec<Note> = (0..400)
        .map(|_| {
            let start = r.below(2000) as i64;
            let channel = channels[r.below(channels.len() as u64) as usize];
            let key = if channel == midi::DRUM_CHANNEL { BASS_DRUM } else { 40 + r.below(50) as u8 };
            let velocity = 20 + r.below(108) as u8;
            let end = start + 1 + r.below(119) as i64;
            Note::new(start, end, channel, key, velocity)
        })
        .collect();
    let sorted = notes;
    let (_, allotted) = allocate(&sorted, &Bank::new());
    assert!(allotted.iter().any(|a| a.voice.is_none()), "the case never goes past eight voices");
    // Who holds a voice at `t`: it started before, has not ended and was
    // not stolen from.
    let holds = |a: &Allotted, t: i64| {
        a.voice.is_some() && sorted[a.note].start <= t && t < a.end && a.stolen.is_none_or(|s| s > t)
    };
    for a in allotted.iter().filter(|a| a.voice.is_none()) {
        let t = sorted[a.note].start;
        let held: HashSet<u8> = allotted.iter().filter(|b| holds(b, t)).map(|b| b.voice.unwrap()).collect();
        assert_eq!(held.len(), sdsp::VOICES, "the note at {t} did not sound with {} voices held", held.len());
    }
}

/// All eight held: channel 0 with seven notes, one of them soft, and
/// channel 1 with just one, the softest of all. The new note on channel 2
/// steals the voice from channel 0's soft one: stealing from channel 1 would
/// leave it mute.
#[test]
fn the_weakest_is_stolen_not_a_channels_last() {
    let mut notes: Vec<Note> = (0..6).map(|k| note(0, 500, 0, 60 + k)).collect();
    notes.push(Note::new(0, 500, 0, 70, 40)); // the soft one
    notes.push(Note::new(0, 500, 1, 50, 30)); // the lone one
    notes.push(note(100, 200, 2, 80)); // the new one
    let (_, allotted) = allocate(&notes, &Bank::new());
    let of = |pitch: u8, channel: u8| {
        allotted
            .iter()
            .find(|a| notes[a.note].pitch == pitch && notes[a.note].channel == channel)
            .unwrap()
            .clone()
    };
    let (new, soft, lone) = (of(80, 2), of(70, 0), of(50, 1));
    assert_eq!(new.voice, soft.voice, "the new note took another voice than the soft one");
    assert_eq!((soft.stolen, lone.stolen), (Some(100), None));
}

/// Eleven notes in the same frame, all with the same velocity: five hits
/// —two bass drums, two snares and the hi-hat—, three one-note channels and
/// channel 0's three-note chord. The hits go first, one per family; then the
/// melodic part, each channel's loudest note before anyone's second; the
/// repeated hits last. Left out are the second bass drum, the second snare
/// and the bottom note of the chord.
#[test]
fn the_top_voice_of_a_chord_is_not_last_to_its_frame() {
    let d = midi::DRUM_CHANNEL;
    let mut notes: Vec<Note> = [35, 36, 38, 40, 42].map(|k| note(0, 30, d, k)).to_vec();
    notes.extend([(1, 40), (2, 45), (3, 50)].map(|(c, k)| note(0, 100, c, k)));
    notes.extend([64, 67, 72].map(|k| note(0, 100, 0, k)));
    let programs: BTreeMap<u8, u8> = (0..4).map(|c| (c, PIANO)).collect();
    let mut allotted = Vec::new();
    build_events(&notes, &assign(&notes), &programs, &Bank::with_drums(), &[], Some(&mut allotted), sdsp::HEADROOM)
        .unwrap();
    let mut without: Vec<(u8, u8)> = allotted
        .iter()
        .filter(|a| a.voice.is_none())
        .map(|a| (notes[a.note].channel, notes[a.note].pitch))
        .collect();
    without.sort();
    assert_eq!(without, [(0, 64), (d, 36), (d, 40)]);
}

/// One voice, two notes: the second steals the voice from the first while
/// it sounds. In the frame before, the voice has to come down with the ramp
/// —ADSR1 at zero and GAIN `RAMP`—, because KON drops it to zero at once and
/// that is a click. The third note arrives with the voice silent: no ramp.
#[test]
fn a_sounding_voice_is_lowered_a_frame_before_stealing_it() {
    let out = build(
        &[note(0, 100, 0, 60), note(50, 120, 0, 60), note(400, 450, 0, 60)],
        voices_of(&[(0, &[0])]),
        &Bank::new(),
    );
    let written = writes_to(&out, 0);
    let gain: Vec<(i64, u8)> = written.iter().filter(|w| w.1 == sdsp::V_GAIN).map(|w| (w.0, w.2)).collect();
    assert!(gain.contains(&(49, RAMP)), "no ramp before the steal at frame 50: {gain:?}");
    assert!(written.contains(&(49, sdsp::V_ADSR1, 0)), "without ADSR1 at zero the ramp's GAIN is not in control");
    assert!(!gain.iter().any(|&(c, v)| v == RAMP && c > 49), "{gain:?}");
}

/// The first note has already been released, but its tail is still sounding
/// when the second takes the voice —the bank's GAIN is exponential and
/// slow—: the ramp goes in anyway.
#[test]
fn a_release_tail_is_lowered_too_before_reusing_the_voice() {
    let out = build(&[note(0, 40, 0, 60), note(60, 100, 0, 60)], voices_of(&[(0, &[0])]), &Bank::new());
    let gain: Vec<(i64, u8)> =
        writes_to(&out, 0).iter().filter(|w| w.1 == sdsp::V_GAIN).map(|w| (w.0, w.2)).collect();
    assert_eq!(&gain[..2], &[(40, sdsp::GAIN_EXP_DECREASE | 12), (59, RAMP)]);
}

// --- velocity and controllers ----------------------------------------------

fn control(frame: i64, number: u16, value: f64, channel: u8) -> Control {
    Control { start: frame, channel, number, value }
}

fn build_with(notes: &[Note], controls: &[Control]) -> Vec<Write> {
    let programs = BTreeMap::from([(0, PIANO)]);
    let frames = build_events(
        notes,
        &voices_of(&[(0, &[0])]),
        &programs,
        &Bank::new(),
        controls,
        None,
        sdsp::HEADROOM,
    )
    .unwrap();
    released(&frames, notes.iter().map(|n| n.end).max().unwrap() + 10)
}

/// fluidsynth attenuates by 40·log10(127/v) dB —measured: 64 gives
/// -11.9 dB—, that is, the amplitude squared.
#[test]
fn velocity_lowers_the_volume_squared() {
    let out = build_with(&[Note::new(0, 30, 0, 60, 64)], &[]);
    let expected = num::round(sdsp::ceiling() as f64 * (64.0f64 / 127.0).powi(2)) as u8;
    assert_eq!(registers(&out, 0, sdsp::V_VOL_L), [expected]);
    assert_eq!(registers(&out, 0, sdsp::V_VOL_R), [expected]);
}

/// A CC7 in the middle of a note rewrites its voice's volume in that frame,
/// on both sides. And at 50 —half of GM's 100— it lowers the amplitude to a
/// quarter, the same as velocity.
#[test]
fn channel_volume_changes_a_note_already_sounding() {
    let out = build_with(&[Note::new(0, 100, 0, 60, 127)], &[control(40, midi::VOLUME, 50.0, 0)]);
    let quarter = num::round(sdsp::ceiling() as f64 / 4.0) as u8;
    let written = writes_to(&out, 0);
    for register in [sdsp::V_VOL_L, sdsp::V_VOL_R] {
        let got: Vec<(i64, u8)> = written.iter().filter(|w| w.1 == register).map(|w| (w.0, w.2)).collect();
        assert_eq!(got, [(0, sdsp::ceiling() as u8), (40, quarter)]);
    }
}

/// CC11 at 64 and CC7 at 127 before the note: 40·log10 each, like
/// fluidsynth. The volume is measured against 100, so 127 raises it.
#[test]
fn expression_and_volume_multiply() {
    let out = build_with(
        &[Note::new(10, 50, 0, 60, 127)],
        &[control(0, midi::EXPRESSION, 64.0, 0), control(0, midi::VOLUME, 127.0, 0)],
    );
    let expected =
        num::round(sdsp::ceiling() as f64 * (127.0f64 / 100.0).powi(2) * (64.0f64 / 127.0).powi(2)) as u8;
    assert_eq!(registers(&out, 0, sdsp::V_VOL_L), [expected]);
}

/// CC10 at 0 is fully left: the right at zero and the left 1.41 times the
/// ceiling. At 32, +2.3 dB and -5.3 dB.
#[test]
fn pan_splits_the_note_between_both_sides() {
    let out = build_with(
        &[Note::new(10, 50, 0, 60, 127), Note::new(60, 90, 0, 60, 127)],
        &[control(0, midi::PAN, 0.0, 0), control(55, midi::PAN, 32.0, 0)],
    );
    let (l, r) = (registers(&out, 0, sdsp::V_VOL_L), registers(&out, 0, sdsp::V_VOL_R));
    let c = sdsp::ceiling() as f64;
    assert_eq!((l[0], r[0]), (num::round(c * 2f64.sqrt()) as u8, 0));
    assert!((20.0 * (l[1] as f64 / c).log10() - 2.3).abs() < 0.3, "{l:?}");
    assert!((20.0 * (r[1] as f64 / c).log10() + 5.3).abs() < 0.5, "{r:?}");
}

/// A bend before the note plays it detuned from the start, and one during
/// it rewrites the voice's pitch.
#[test]
fn the_bend_moves_the_pitch_before_and_during_the_note() {
    let out = build_with(
        &[Note::new(10, 100, 0, 60, 127)],
        &[control(0, midi::BEND, 1.0, 0), control(50, midi::BEND, -2.0, 0)],
    );
    let mut steps: BTreeMap<i64, (u16, u16)> = BTreeMap::new();
    for (frame, register, value) in writes_to(&out, 0) {
        if register == sdsp::V_PITCH_L {
            steps.entry(frame).or_default().0 = value as u16;
        } else if register == sdsp::V_PITCH_H {
            steps.entry(frame).or_default().1 = value as u16;
        }
    }
    let step = |f: i64| (steps[&f].0 | steps[&f].1 << 8) as i64;
    assert_eq!(step(10), sdsp::pitch_for(61.0, 60.0, 16000.0));
    assert_eq!(step(50), sdsp::pitch_for(58.0, 60.0, 16000.0));
}

/// Channel 0's CC7 does not change channel 1's voice, and the drums' bend
/// does not move the hit: in General MIDI the note picks the instrument.
#[test]
fn a_control_touches_no_other_channels_voice_nor_the_drums() {
    let d = midi::DRUM_CHANNEL;
    let notes = [Note::new(0, 100, 0, 60, 127), Note::new(0, 100, 1, 60, 127), Note::new(0, 100, d, BASS_DRUM, 127)];
    let sorted = notes.to_vec();
    let programs = BTreeMap::from([(0, PIANO), (1, PIANO)]);
    let frames = build_events(
        &sorted,
        &voices_of(&[(0, &[0]), (1, &[1]), (d, &[6])]),
        &programs,
        &Bank::new(),
        &[control(40, midi::VOLUME, 50.0, 0), control(40, midi::BEND, 2.0, d)],
        None,
        sdsp::HEADROOM,
    )
    .unwrap();
    let out = released(&frames, 110);
    let frames_of = |voice: u8, register: u8| -> Vec<i64> {
        writes_to(&out, voice).iter().filter(|w| w.1 == register).map(|w| w.0).collect()
    };
    assert_eq!(frames_of(0, sdsp::V_VOL_L), [0, 40]);
    assert_eq!(frames_of(1, sdsp::V_VOL_L), [0]);
    assert_eq!(frames_of(6, sdsp::V_PITCH_L), [0]);
}
