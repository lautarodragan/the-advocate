//! How loud, how fast and how gradually a song starts, in the units
//! `OP_BGM` and `OP_SYSTEM_BGM` carry —and the map table of a map's own
//! song, which is the same thing without an opcode—.
//!
//! It lives here, next to the declarations, because three stages write it:
//! the event compiler for `PlayBGM` and `ChangeSystemBGM`, and the music's
//! stage for the song a map plays by its properties. Each writing its own
//! copy is how two of them would drift.

/// The video frames in a second, which is what a fade counts in: `irq_music`
/// ticks the level once per frame.
const FRAMES_PER_SECOND: i64 = 60;

/// An RM2k song's volume, tempo, balance and fade-in, in the console's units:
/// the gain of each side in 128ths, the music frames per video frame in
/// 256ths and the fade-in's step per frame in 65536ths. 100, 100 and 50
/// —the editor's defaults— with no fade are 128, 128, 256 and 0: the song as
/// written.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Level {
    pub left: u8,
    pub right: u8,
    pub step: u16,
    pub fade: u16,
}

impl Default for Level {
    fn default() -> Level {
        Level::WHOLE
    }
}

impl Level {
    /// The song as written.
    pub const WHOLE: Level = Level {
        left: 128,
        right: 128,
        step: 256,
        fade: 0,
    };

    /// From RM2k's `[fade-in in ms, volume, tempo, balance]`.
    ///
    /// * **The volume** is what easyrpg's MIDI path does, and the games'
    ///   songs are all MIDI: it scales each channel's CC7
    ///   —`AudioDecoderMidi::SetVolume` sends `channel_volumes[i] * volume`—.
    ///   The stream already went through that CC7 squared —see `volume` in
    ///   rm2k-snes-audio's sdsp.rs—, so a volume of 50 is a quarter of the
    ///   amplitude.
    /// * **The balance** is easyrpg's curve for audio without MIDI messages
    ///   —`ApplyLogVolume`—: the opposite side drops 6 dB every 10 away from
    ///   50. Its MIDI path moves each channel's pan instead, which the stream
    ///   already baked into each voice; scaling the sides is the cheap
    ///   approximation, and few songs ask for a balance other than 50.
    /// * **The tempo** is the MIDI one: the song goes faster or slower and
    ///   the pitch stays —`AudioDecoderMidi` advances its clock by
    ///   `pitch / 100`—. It is clamped to the editor's range, 50 to 150,
    ///   which also keeps `irq_music` at two music frames at most per video
    ///   frame.
    /// * **The fade-in** is `ceil(65536 / frames)`, the same number
    ///   `OP_FADE_BGM` carries to fade out: the level goes up from zero by it
    ///   each frame, and the song reaches its volume **within** the frames
    ///   asked for. easyrpg clamps it to 10 seconds, and so does this.
    pub fn new(fade_ms: i64, volume: i64, tempo: i64, balance: i64) -> Level {
        let gain = (volume.clamp(0, 100) as f64 / 100.0).powi(2);
        let balance = balance.clamp(0, 100);
        let drop = |away: i64| 0.5012f64.powf(away.max(0) as f64 / 10.0);
        let side = |g: f64| (128.0 * gain * g).round().clamp(0.0, 128.0) as u8;
        let step = (256.0 * tempo.clamp(50, 150) as f64 / 100.0).round() as u16;
        Level {
            left: side(drop(balance - 50)),
            right: side(drop(50 - balance)),
            step,
            fade: fade_step(fade_ms.clamp(0, 10_000)),
        }
    }

    /// The six bytes, in the order the opcodes and the map table carry them.
    pub fn bytes(&self) -> [u8; 6] {
        [
            self.left,
            self.right,
            self.step as u8,
            (self.step >> 8) as u8,
            self.fade as u8,
            (self.fade >> 8) as u8,
        ]
    }
}

/// How much a fade of `ms` milliseconds moves the level per frame, in
/// 65536ths: `ceil(65536 / frames)`, at least one frame. Zero milliseconds
/// is no fade, zero.
pub fn fade_step(ms: i64) -> u16 {
    if ms <= 0 {
        return 0;
    }
    let frames = (ms * FRAMES_PER_SECOND / 1000).max(1);
    (-((-0x10000i64).div_euclid(frames))).min(0xFFFF) as u16
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_defaults_are_the_song_as_written() {
        assert_eq!(Level::new(0, 100, 100, 50), Level::WHOLE);
    }

    #[test]
    fn seventy_percent_is_about_half_the_amplitude() {
        let l = Level::new(0, 70, 100, 50);
        assert_eq!((l.left, l.right, l.step, l.fade), (63, 63, 256, 0));
    }

    #[test]
    fn a_second_of_fade_in_reaches_the_top_in_sixty_frames() {
        let step = Level::new(1000, 100, 100, 50).fade as u32;
        assert_eq!(step, 1093);
        assert!(step * 60 >= 0x10000 && step * 59 < 0x10000);
    }

    #[test]
    fn the_fade_in_is_clamped_to_ten_seconds() {
        assert_eq!(Level::new(20_000, 100, 100, 50).fade, fade_step(10_000));
        assert_eq!(fade_step(10_000), 110);
    }

    #[test]
    fn a_short_fade_is_one_frame() {
        assert_eq!(fade_step(1), 0xFFFF);
    }
}
