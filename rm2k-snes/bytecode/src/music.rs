//! The music stream: what the 65816 reads, one event at a time, and expands into
//! writes to the S-DSP's registers, which it forwards to the SPC700 driver.
//!
//! It used to be those writes themselves —`OP_DSP register value`, three bytes
//! each—. Now it is per note, and the reader is what turns an event into
//! writes: a note is its voice, maybe its volume, and one byte naming a *sound*
//! of the song's table —sample, envelope, the release's GAIN and the pitch—.
//! The reader keeps a cache of the eight registers of each voice and skips a
//! write that would not change one, so the stream never says what stays the
//! same; `OP_DSP` is still here for the few writes that are not a voice's.
//!
//! Most events are about one voice, and the voice goes in the opcode's low
//! three bits: each of those is a family of eight, `_V0` to `_V7`, aligned to
//! eight, so that the reader finds the family with `op >> 3` and the voice with
//! `op & 7`. Nothing here enforces the families: the declaration knows
//! opcodes, not families. The reader and the writer check them.
//!
//! The waits close a frame: the notes of the frame are keyed on together, and
//! the next frame starts by releasing that key-on. `OP_WAIT_1` to `OP_WAIT_32`
//! are the short ones, one byte; `OP_WAIT` takes the count as a word, and a
//! count of 0 keys on without waiting.
//!
//! `OP_REPEAT` plays again something the song already played: it goes `back`
//! bytes back from the end of itself, reads `events` events there —from 1 to
//! 254— and comes back to the byte after itself. Those events cannot be another
//! `OP_REPEAT`, nor `OP_INIT` or `OP_END`: one level, so that the reader keeps a
//! single return address. They are the same bytes the stream had there, so they
//! write the same.
//!
//! A note's sound is one byte, and a song may have more than 256 sounds:
//! `OP_SOUND_PAGE` says which 256 the notes that follow name, until the next
//! one. Every song starts in page 0, so one with 256 sounds or fewer never
//! says it. The page is the reader's state, like its cache: an `OP_REPEAT`
//! reads its events in the page it finds, as the bytes it stands for would.
//!
//! The grammar, and what is deliberately not declared here, is
//! `bytecode!`'s. Each family's doc comment is repeated on its eight
//! members, so that each constant says what it is.

bytecode! {
    "music";
    /// a note: the sound, then key-on when the frame closes
    OP_NOTE_V0 = 0x00 (sound: byte);
    /// a note: the sound, then key-on when the frame closes
    OP_NOTE_V1 = 0x01 (sound: byte);
    /// a note: the sound, then key-on when the frame closes
    OP_NOTE_V2 = 0x02 (sound: byte);
    /// a note: the sound, then key-on when the frame closes
    OP_NOTE_V3 = 0x03 (sound: byte);
    /// a note: the sound, then key-on when the frame closes
    OP_NOTE_V4 = 0x04 (sound: byte);
    /// a note: the sound, then key-on when the frame closes
    OP_NOTE_V5 = 0x05 (sound: byte);
    /// a note: the sound, then key-on when the frame closes
    OP_NOTE_V6 = 0x06 (sound: byte);
    /// a note: the sound, then key-on when the frame closes
    OP_NOTE_V7 = 0x07 (sound: byte);

    /// a note with a new volume, the same on both sides
    OP_NOTE_VOL_V0 = 0x08 (volume: byte, sound: byte);
    /// a note with a new volume, the same on both sides
    OP_NOTE_VOL_V1 = 0x09 (volume: byte, sound: byte);
    /// a note with a new volume, the same on both sides
    OP_NOTE_VOL_V2 = 0x0A (volume: byte, sound: byte);
    /// a note with a new volume, the same on both sides
    OP_NOTE_VOL_V3 = 0x0B (volume: byte, sound: byte);
    /// a note with a new volume, the same on both sides
    OP_NOTE_VOL_V4 = 0x0C (volume: byte, sound: byte);
    /// a note with a new volume, the same on both sides
    OP_NOTE_VOL_V5 = 0x0D (volume: byte, sound: byte);
    /// a note with a new volume, the same on both sides
    OP_NOTE_VOL_V6 = 0x0E (volume: byte, sound: byte);
    /// a note with a new volume, the same on both sides
    OP_NOTE_VOL_V7 = 0x0F (volume: byte, sound: byte);

    /// a note with a new volume for each side
    OP_NOTE_PAN_V0 = 0x10 (left: byte, right: byte, sound: byte);
    /// a note with a new volume for each side
    OP_NOTE_PAN_V1 = 0x11 (left: byte, right: byte, sound: byte);
    /// a note with a new volume for each side
    OP_NOTE_PAN_V2 = 0x12 (left: byte, right: byte, sound: byte);
    /// a note with a new volume for each side
    OP_NOTE_PAN_V3 = 0x13 (left: byte, right: byte, sound: byte);
    /// a note with a new volume for each side
    OP_NOTE_PAN_V4 = 0x14 (left: byte, right: byte, sound: byte);
    /// a note with a new volume for each side
    OP_NOTE_PAN_V5 = 0x15 (left: byte, right: byte, sound: byte);
    /// a note with a new volume for each side
    OP_NOTE_PAN_V6 = 0x16 (left: byte, right: byte, sound: byte);
    /// a note with a new volume for each side
    OP_NOTE_PAN_V7 = 0x17 (left: byte, right: byte, sound: byte);

    /// release: ADSR off, and the GAIN of the voice's sound
    OP_RELEASE_V0 = 0x18 ();
    /// release: ADSR off, and the GAIN of the voice's sound
    OP_RELEASE_V1 = 0x19 ();
    /// release: ADSR off, and the GAIN of the voice's sound
    OP_RELEASE_V2 = 0x1A ();
    /// release: ADSR off, and the GAIN of the voice's sound
    OP_RELEASE_V3 = 0x1B ();
    /// release: ADSR off, and the GAIN of the voice's sound
    OP_RELEASE_V4 = 0x1C ();
    /// release: ADSR off, and the GAIN of the voice's sound
    OP_RELEASE_V5 = 0x1D ();
    /// release: ADSR off, and the GAIN of the voice's sound
    OP_RELEASE_V6 = 0x1E ();
    /// release: ADSR off, and the GAIN of the voice's sound
    OP_RELEASE_V7 = 0x1F ();

    /// release with some other GAIN
    OP_RELEASE_GAIN_V0 = 0x20 (gain: byte);
    /// release with some other GAIN
    OP_RELEASE_GAIN_V1 = 0x21 (gain: byte);
    /// release with some other GAIN
    OP_RELEASE_GAIN_V2 = 0x22 (gain: byte);
    /// release with some other GAIN
    OP_RELEASE_GAIN_V3 = 0x23 (gain: byte);
    /// release with some other GAIN
    OP_RELEASE_GAIN_V4 = 0x24 (gain: byte);
    /// release with some other GAIN
    OP_RELEASE_GAIN_V5 = 0x25 (gain: byte);
    /// release with some other GAIN
    OP_RELEASE_GAIN_V6 = 0x26 (gain: byte);
    /// release with some other GAIN
    OP_RELEASE_GAIN_V7 = 0x27 (gain: byte);

    /// a new volume for a voice that is already sounding
    OP_SET_VOL_V0 = 0x28 (volume: byte);
    /// a new volume for a voice that is already sounding
    OP_SET_VOL_V1 = 0x29 (volume: byte);
    /// a new volume for a voice that is already sounding
    OP_SET_VOL_V2 = 0x2A (volume: byte);
    /// a new volume for a voice that is already sounding
    OP_SET_VOL_V3 = 0x2B (volume: byte);
    /// a new volume for a voice that is already sounding
    OP_SET_VOL_V4 = 0x2C (volume: byte);
    /// a new volume for a voice that is already sounding
    OP_SET_VOL_V5 = 0x2D (volume: byte);
    /// a new volume for a voice that is already sounding
    OP_SET_VOL_V6 = 0x2E (volume: byte);
    /// a new volume for a voice that is already sounding
    OP_SET_VOL_V7 = 0x2F (volume: byte);

    /// the same, a different one for each side
    OP_SET_PAN_V0 = 0x30 (left: byte, right: byte);
    /// the same, a different one for each side
    OP_SET_PAN_V1 = 0x31 (left: byte, right: byte);
    /// the same, a different one for each side
    OP_SET_PAN_V2 = 0x32 (left: byte, right: byte);
    /// the same, a different one for each side
    OP_SET_PAN_V3 = 0x33 (left: byte, right: byte);
    /// the same, a different one for each side
    OP_SET_PAN_V4 = 0x34 (left: byte, right: byte);
    /// the same, a different one for each side
    OP_SET_PAN_V5 = 0x35 (left: byte, right: byte);
    /// the same, a different one for each side
    OP_SET_PAN_V6 = 0x36 (left: byte, right: byte);
    /// the same, a different one for each side
    OP_SET_PAN_V7 = 0x37 (left: byte, right: byte);

    /// a new pitch for a voice that is already sounding
    OP_SET_PITCH_V0 = 0x38 (pitch: word);
    /// a new pitch for a voice that is already sounding
    OP_SET_PITCH_V1 = 0x39 (pitch: word);
    /// a new pitch for a voice that is already sounding
    OP_SET_PITCH_V2 = 0x3A (pitch: word);
    /// a new pitch for a voice that is already sounding
    OP_SET_PITCH_V3 = 0x3B (pitch: word);
    /// a new pitch for a voice that is already sounding
    OP_SET_PITCH_V4 = 0x3C (pitch: word);
    /// a new pitch for a voice that is already sounding
    OP_SET_PITCH_V5 = 0x3D (pitch: word);
    /// a new pitch for a voice that is already sounding
    OP_SET_PITCH_V6 = 0x3E (pitch: word);
    /// a new pitch for a voice that is already sounding
    OP_SET_PITCH_V7 = 0x3F (pitch: word);

    /// close the frame and wait that many frames
    OP_WAIT_1 = 0x40 ();
    /// close the frame and wait that many frames
    OP_WAIT_2 = 0x41 ();
    /// close the frame and wait that many frames
    OP_WAIT_3 = 0x42 ();
    /// close the frame and wait that many frames
    OP_WAIT_4 = 0x43 ();
    /// close the frame and wait that many frames
    OP_WAIT_5 = 0x44 ();
    /// close the frame and wait that many frames
    OP_WAIT_6 = 0x45 ();
    /// close the frame and wait that many frames
    OP_WAIT_7 = 0x46 ();
    /// close the frame and wait that many frames
    OP_WAIT_8 = 0x47 ();
    /// close the frame and wait that many frames
    OP_WAIT_9 = 0x48 ();
    /// close the frame and wait that many frames
    OP_WAIT_10 = 0x49 ();
    /// close the frame and wait that many frames
    OP_WAIT_11 = 0x4A ();
    /// close the frame and wait that many frames
    OP_WAIT_12 = 0x4B ();
    /// close the frame and wait that many frames
    OP_WAIT_13 = 0x4C ();
    /// close the frame and wait that many frames
    OP_WAIT_14 = 0x4D ();
    /// close the frame and wait that many frames
    OP_WAIT_15 = 0x4E ();
    /// close the frame and wait that many frames
    OP_WAIT_16 = 0x4F ();
    /// close the frame and wait that many frames
    OP_WAIT_17 = 0x50 ();
    /// close the frame and wait that many frames
    OP_WAIT_18 = 0x51 ();
    /// close the frame and wait that many frames
    OP_WAIT_19 = 0x52 ();
    /// close the frame and wait that many frames
    OP_WAIT_20 = 0x53 ();
    /// close the frame and wait that many frames
    OP_WAIT_21 = 0x54 ();
    /// close the frame and wait that many frames
    OP_WAIT_22 = 0x55 ();
    /// close the frame and wait that many frames
    OP_WAIT_23 = 0x56 ();
    /// close the frame and wait that many frames
    OP_WAIT_24 = 0x57 ();
    /// close the frame and wait that many frames
    OP_WAIT_25 = 0x58 ();
    /// close the frame and wait that many frames
    OP_WAIT_26 = 0x59 ();
    /// close the frame and wait that many frames
    OP_WAIT_27 = 0x5A ();
    /// close the frame and wait that many frames
    OP_WAIT_28 = 0x5B ();
    /// close the frame and wait that many frames
    OP_WAIT_29 = 0x5C ();
    /// close the frame and wait that many frames
    OP_WAIT_30 = 0x5D ();
    /// close the frame and wait that many frames
    OP_WAIT_31 = 0x5E ();
    /// close the frame and wait that many frames
    OP_WAIT_32 = 0x5F ();

    /// close the frame and wait `frames`; 0 keys on without waiting
    OP_WAIT = 0x60 (frames: word);

    /// a raw write, for the registers that are not a voice's
    OP_DSP = 0x61 (register: byte, value: byte);

    /// the DSP's global setup, and both KON and KOF at zero
    OP_INIT = 0x62 ();

    /// the end of the song: it starts over
    OP_END = 0x63 ();

    /// `events` events from `back` bytes before the end of this one, and back here
    OP_REPEAT = 0x64 (back: word, events: byte);

    /// the notes from here on name the song's sounds from `page` × 256 on
    OP_SOUND_PAGE = 0x65 (page: byte);
}
