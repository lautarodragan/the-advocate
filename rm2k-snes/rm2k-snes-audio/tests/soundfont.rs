//! The envelopes of a real SoundFont, the one in `SOUNDFONT`: what these
//! enforce is precisely that the numbers come from there. Without the
//! variable they are skipped with a message, the way Ditto's tests skip
//! without their corpus.

use rm2k_snes_audio::bank::Samples;
use rm2k_snes_audio::samples::SoundFontSamples;
use rm2k_snes_audio::sdsp;

fn samples() -> Option<Samples> {
    let Ok(path) = std::env::var("SOUNDFONT") else {
        eprintln!("skipped: a real SoundFont is needed, SOUNDFONT=<the .sf2>");
        return None;
    };
    Some(Samples { font: SoundFontSamples::open(path.as_ref()).unwrap() })
}

/// The General MIDI synth bass (38) of the SoundFont the game was composed
/// with is released in 30 ms. With the families from before 2026-09-25 it
/// dragged a 2.4 s tail with exponential GAIN; the release is linear GAIN,
/// because the fastest exponential does not reach zero in less than 25 ms.
#[test]
fn the_synth_bass_releases_as_the_soundfont_says() {
    let Some(s) = samples() else { return };
    let (_, _, gain) = s.envelope(38, 36).unwrap();
    assert_eq!(gain & 0xE0, sdsp::GAIN_LINEAR_DECREASE, "GAIN ${gain:02X}");
    let seconds = (64 * sdsp::PERIOD[(gain & 0x1F) as usize]) as f64 / sdsp::SAMPLE_RATE as f64;
    assert!(seconds < 0.1, "the release lasts {seconds:.3} s");
}

/// The piano (0) has no sustain —1440 centibels: it decays to silence— and
/// its decay gets shorter with the key. So the DSP's sustain level goes at
/// the very top (SL = 7, the decay phase ends immediately) and the sustain
/// rate changes between a low C and a high one: a higher rate is faster.
#[test]
fn the_piano_decays_differently_per_key_until_silent() {
    let Some(s) = samples() else { return };
    let (_, low, _) = s.envelope(0, 36).unwrap();
    let (_, high, _) = s.envelope(0, 84).unwrap();
    assert_eq!((low >> 5, high >> 5), (7, 7), "ADSR2 {low:#04x} {high:#04x}");
    assert!(high & 0x1F > low & 0x1F, "ADSR2 {low:#04x} {high:#04x}");
}
