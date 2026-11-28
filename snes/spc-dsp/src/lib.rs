//! The S-DSP on its own: the Super NES's sound chip, without the SPC700
//! that usually drives it. ARAM in, register writes, so many clocks, and the
//! stereo samples that come out.
//!
//! ```
//! # let aram = vec![0; spc_dsp::ARAM];
//! let mut dsp = spc_dsp::Dsp::new(aram);
//! dsp.write(0x6C, 0x20); // FLG: out of reset, echo writes off
//! let samples = dsp.run(17_040); // about one frame of the console
//! ```
//!
//! What runs is blargg's `SPC_DSP`, from snes_spc 0.9.0, in
//! `vendor/snes_spc/` as it came: the README says where from, what was
//! checked of it, and its licence. This wraps the three things of it that
//! bite from Rust —see each method—.

use std::ptr::NonNull;

/// The S-DSP's clock: about 1,024,000 per second. Every 32 clocks it puts
/// out one stereo pair, at 32 kHz.
pub const CLOCKS_PER_SECOND: u32 = 1_024_000;

/// Its registers: 128, from `$00` to `$7F`.
pub const REGISTERS: usize = 128;

/// The ARAM it reads the samples and the directory from: 64 KB.
pub const ARAM: usize = 0x10000;

/// What is compiled, as it is compiled: for whoever keeps what the DSP
/// played and has to know when that would change. A comment changed in one
/// of them changes it too, which costs a few plays and nobody has to
/// remember a number.
pub const SOURCES: [&[u8]; 9] = [
    include_bytes!("../vendor/snes_spc/SPC_DSP.cpp"),
    include_bytes!("../vendor/snes_spc/SPC_DSP.h"),
    include_bytes!("../vendor/snes_spc/blargg_common.h"),
    include_bytes!("../vendor/snes_spc/blargg_config.h"),
    include_bytes!("../vendor/snes_spc/blargg_endian.h"),
    include_bytes!("../vendor/snes_spc/blargg_source.h"),
    include_bytes!("shim.cpp"),
    include_bytes!("lib.rs"),
    include_bytes!("../build.rs"),
];

#[repr(C)]
struct Raw {
    _private: [u8; 0],
}

extern "C" {
    fn spc_dsp_new(ram: *mut u8) -> *mut Raw;
    fn spc_dsp_free(dsp: *mut Raw);
    fn spc_dsp_write(dsp: *mut Raw, address: i32, data: i32);
    fn spc_dsp_run(dsp: *mut Raw, clocks: i32, out: *mut i16, room: i32) -> i32;
}

/// One S-DSP, with its ARAM.
pub struct Dsp {
    raw: NonNull<Raw>,
    // The C++ object keeps a pointer into this for as long as it lives: it
    // is boxed so that moving the `Dsp` does not move it, and dropped after
    // `raw` is freed.
    aram: Box<[u8]>,
    out: Vec<i16>,
}

// The C++ object is plain data —no globals, no threads, no I/O— and owned
// by this alone, so it can go to another thread whole.
unsafe impl Send for Dsp {}

impl Dsp {
    /// A DSP over `aram`, at its power-on state.
    ///
    /// **The power-on state is not silent**: it is a pattern of register
    /// values measured on a console, with KON set, so whatever the first
    /// [`Dsp::run`] finds in the registers is played. Write every register
    /// a program sets at boot before the first run.
    ///
    /// Panics if `aram` is not [`ARAM`] bytes, or if there is no memory for
    /// the DSP: the class's `operator new` returns NULL instead of throwing.
    pub fn new(aram: Vec<u8>) -> Dsp {
        assert_eq!(aram.len(), ARAM, "the S-DSP reads 64 KB of ARAM");
        let mut aram = aram.into_boxed_slice();
        // SAFETY: `aram` is 64 KB and outlives the object: see the field.
        let raw = unsafe { spc_dsp_new(aram.as_mut_ptr()) };
        let raw = NonNull::new(raw).expect("no memory for the S-DSP");
        Dsp {
            raw,
            aram,
            out: Vec::new(),
        }
    }

    /// The ARAM, as the DSP left it: with echo writes on, it writes the
    /// echo buffer into it.
    pub fn aram(&self) -> &[u8] {
        &self.aram
    }

    /// Writes `value` to register `register`, at this point of the run.
    pub fn write(&mut self, register: u8, value: u8) {
        assert!(
            (register as usize) < REGISTERS,
            "the S-DSP has no register ${register:02X}"
        );
        // SAFETY: `raw` is alive and the register is in range.
        unsafe { spc_dsp_write(self.raw.as_ptr(), register.into(), value.into()) }
    }

    /// Runs `clocks` clocks and gives what came out: left and right
    /// interleaved, one pair every 32 clocks —the clocks left over carry to
    /// the next run—.
    ///
    /// **Zero clocks is nothing**: `SPC_DSP::run(0)` does not return —it
    /// counts down through four billion— so it is not called.
    pub fn run(&mut self, clocks: u32) -> &[i16] {
        if clocks == 0 {
            return &[];
        }
        let clocks = i32::try_from(clocks).expect("a run fits in an int");
        // At most one pair per 32 clocks, plus the one the clocks left over
        // from the last run may complete: past `room`, the class writes
        // into a buffer of its own and the samples are lost.
        let room = clocks as usize / 16 + 4;
        self.out.resize(room, 0);
        // SAFETY: `raw` is alive and `out` has `room` samples.
        let got = unsafe {
            spc_dsp_run(
                self.raw.as_ptr(),
                clocks,
                self.out.as_mut_ptr(),
                room as i32,
            )
        };
        &self.out[..got as usize]
    }
}

impl Drop for Dsp {
    fn drop(&mut self) {
        // SAFETY: `raw` came from `spc_dsp_new` and is freed once.
        unsafe { spc_dsp_free(self.raw.as_ptr()) }
    }
}
