//! The wrapper against the S-DSP: a voice keyed on sounds, one that is not
//! is silence, and the traps of the C++ stay guarded.

use spc_dsp::{Dsp, ARAM};

const DIR: u8 = 0x02;
const SAMPLE: usize = 0x0300;

/// An ARAM with one looping square wave as directory entry 0.
fn aram() -> Vec<u8> {
    let mut aram = vec![0u8; ARAM];
    let entry = (DIR as usize) << 8;
    aram[entry..entry + 2].copy_from_slice(&(SAMPLE as u16).to_le_bytes());
    aram[entry + 2..entry + 4].copy_from_slice(&(SAMPLE as u16).to_le_bytes());
    // One BRR block: shift 11, no filter, loop and end; eight samples high,
    // eight low.
    aram[SAMPLE] = 0xB3;
    aram[SAMPLE + 1..SAMPLE + 5].fill(0x77);
    aram[SAMPLE + 5..SAMPLE + 9].fill(0x99);
    aram
}

/// What a program writes at boot, and voice 0 ready to play entry 0.
fn boot(dsp: &mut Dsp) {
    for (register, value) in [
        (0x6C, 0x20), // FLG: out of reset and mute, echo writes off
        (0x0C, 0x7F), // MVOL
        (0x1C, 0x7F),
        (0x2C, 0x00), // EVOL
        (0x3C, 0x00),
        (0x2D, 0x00), // PMON
        (0x3D, 0x00), // NON
        (0x4D, 0x00), // EON
        (0x5D, DIR),
        (0x4C, 0x00), // KON
        (0x5C, 0x00), // KOF
        (0x00, 0x7F), // voice 0: VOL, PITCH, SRCN, ADSR off, GAIN direct
        (0x01, 0x7F),
        (0x02, 0x00),
        (0x03, 0x10),
        (0x04, 0x00),
        (0x05, 0x00),
        (0x07, 0x7F),
    ] {
        dsp.write(register, value);
    }
}

#[test]
fn a_voice_keyed_on_sounds() {
    let mut dsp = Dsp::new(aram());
    boot(&mut dsp);
    dsp.write(0x4C, 0x01);
    let out: Vec<i16> = (0..20).flat_map(|_| dsp.run(320).to_vec()).collect();
    assert_eq!(out.len(), 20 * 20, "one pair every 32 clocks");
    assert!(out.iter().any(|&s| s > 1000) && out.iter().any(|&s| s < -1000));
}

#[test]
fn without_a_key_on_it_is_silence() {
    let mut dsp = Dsp::new(aram());
    boot(&mut dsp);
    let out = dsp.run(32 * 400).to_vec();
    assert_eq!(out.len(), 800);
    assert!(
        out.iter().all(|&s| s == 0),
        "the power-on KON was written over"
    );
}

#[test]
fn zero_clocks_is_nothing_and_left_over_clocks_carry() {
    let mut dsp = Dsp::new(aram());
    boot(&mut dsp);
    assert!(dsp.run(0).is_empty());
    // 7 clocks at a time, 32 times: as many pairs as 224 clocks in one go.
    let pieces: usize = (0..32).map(|_| dsp.run(7).len()).sum();
    assert_eq!(pieces, 14);
}

#[test]
fn the_same_writes_give_the_same_samples_in_any_thread() {
    let play = || {
        let mut dsp = Dsp::new(aram());
        boot(&mut dsp);
        dsp.write(0x4C, 0x01);
        dsp.run(32 * 1000).to_vec()
    };
    let here = play();
    let there = std::thread::spawn(play).join().unwrap();
    assert_eq!(here, there);
}

#[test]
#[should_panic(expected = "64 KB")]
fn the_aram_is_64_kb() {
    let _ = Dsp::new(vec![0; 1024]);
}
