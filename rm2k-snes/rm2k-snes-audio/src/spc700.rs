//! The SPC700's side: its driver, and the few instructions it takes to
//! assemble it.
//!
//! There is no SPC700 assembler to be had that has been reviewed, and the
//! driver needs very few instructions: the 65816 sends it DSP (register,
//! value) pairs through the ports and the SPC700 copies them. So this
//! assembles those and nothing else. Each one is annotated with its encoding
//! so it can be checked without running anything.
//!
//! The memory map that matters:
//!
//! ```text
//!   $F1        control: resets the ports
//!   $F2/$F3    DSP address and data
//!   $F4-$F7    the four ports to the 65816 (there they are $2140-$2143)
//! ```

use crate::fail::{Bad, Result};
use std::collections::HashMap;

/// Where the driver lives in the SPC700's 64 KB. The boot ROM keeps the
/// first $200 bytes for its variables, so everything starts higher up.
pub const DRIVER_ADDR: u16 = 0x0200;

// It waits for the 65816 to change the token in port 3 —the 65816
// increments it on every write, and the driver hands it back as an
// acknowledgement— and looks at port 2, which says what to do:
//
//   0  a DSP (register, value) pair in ports 0 and 1: the music
//   1  a byte from port 0 into the ARAM, where the pointer points, which
//      advances
//   2  the ARAM pointer, from ports 0 and 1
//   3  a block: port 0 says how many triplets are coming —up to 85, so that
//      index Y does not go past a byte—, and then one arrives per token, in
//      ports 0, 1 and 2, after the pointer. The pointer does not advance: the
//      65816 sets it again before each block. That is about 56 SPC700 cycles
//      per triplet, about 55 KB per second
//   4  go back to the IPL ROM: see below. It does not answer the
//      acknowledgement, because by the time the 65816 would read it the
//      driver no longer exists
//
// Command 4 is there to **boot the ROM again**. The 65816 cannot reset the
// SPC700 —the console's reset button can, because the line reaches both, but
// a `jml reset` from inside the game cannot—, so after a Game Over the SPC700
// keeps running this driver and the IPL is no longer there to greet with
// $AA/$BB, and the 65816 would wait for that greeting forever. Setting bit 7
// of $F1 makes the IPL ROM reappear at $FFC0, and jumping there boots it from
// scratch, which is exactly what the 65816 sees when the console is switched
// on.
//
// The three ARAM ones exist because of each map's audio package: the samples
// are uploaded while the music plays, so the driver has to be able to receive
// them without stopping serving the DSP. The pointer and the count live at
// $00-$03 of the zero page, which the boot ROM uses and leaves free.
//
// The music keeps sending 0 commands without touching port 2: whoever
// uploads to the ARAM leaves it at zero before releasing the bus.
//
// The labels are in Spanish because that is how the driver was written, and
// they are part of its source, not of any output.
pub const DRIVER: &str = "
    mov x, $F7          ; start with whatever token is there, without firing
espera:
    cmp x, $F7
    beq espera
    mov x, $F7
    mov a, $F6          ; the command
    bne no_dsp
    mov a, $F4          ; DSP register
    mov $F2, a
    mov a, $F5          ; the value that goes in that register
    mov $F3, a
    mov $F7, x          ; acknowledge by handing the token back
    bra espera
no_dsp:
    cmp a, #$01
    bne no_byte
    mov a, $F4
    mov y, #$00
    mov [$00]+y, a
    incw $00
    mov $F7, x
    bra espera
no_byte:
    cmp a, #$02
    bne no_puntero
    mov a, $F4
    mov $00, a
    mov a, $F5
    mov $01, a
    mov $F7, x
    bra espera
no_puntero:
    cmp a, #$04
    bne bloque
    mov a, #$80         ; the IPL ROM, back at $FFC0
    mov $F1, a
    jmp !$FFC0
bloque:
    mov a, $F4
    mov $02, a
    mov $F7, x
    mov y, #$00
terna:
    cmp x, $F7
    beq terna
    mov x, $F7
    mov a, $F4
    mov [$00]+y, a
    inc y
    mov a, $F5
    mov [$00]+y, a
    inc y
    mov a, $F6
    mov [$00]+y, a
    inc y
    mov $F7, x
    dec $02
    bne terna
    bra espera
";

/// (mnemonic, operand shape, opcode, how many operand bytes), in the order
/// they are tried. The shapes: dp = direct page, imm = immediate, rel = a
/// relative branch, abs = a sixteen-bit address, emitted little endian.
const OPCODES: &[(&str, &str, u8, usize)] = &[
    ("mov", "a,dp", 0xE4, 1),     // A <- (dp)
    ("mov", "a,imm", 0xE8, 1),    // A <- immediate
    ("mov", "dp,a", 0xC4, 1),     // (dp) <- A
    ("mov", "x,dp", 0xF8, 1),     // X <- (dp)
    ("mov", "x,imm", 0xCD, 1),    // X <- immediate
    ("mov", "dp,x", 0xD8, 1),     // (dp) <- X
    ("mov", "y,imm", 0x8D, 1),    // Y <- immediate
    ("mov", "[dp]+y,a", 0xD7, 1), // (word at dp + Y) <- A
    ("incw", "dp", 0x3A, 1),      // the word at dp, plus one
    ("decw", "dp", 0x1A, 1),      // minus one; Z if it reached zero
    ("dec", "dp", 0x8B, 1),       // the byte at dp, minus one
    ("inc", "y", 0xFC, 0),        // Y plus one
    ("cmp", "x,dp", 0x3E, 1),     // compares X with (dp)
    ("cmp", "a,imm", 0x68, 1),    // compares A with immediate
    ("beq", "rel", 0xF0, 1),      // branches if equal
    ("bne", "rel", 0xD0, 1),      // branches if not equal
    ("bra", "rel", 0x2F, 1),      // unconditional branch
    ("jmp", "abs", 0x5F, 2),      // long jump, to any address
    ("nop", "", 0x00, 0),
];

/// An operand like `$f4` or `#$10`, or None if it lacks the prefix.
fn number(text: &str, prefix: &str) -> Option<i64> {
    let text = text.strip_prefix(prefix)?;
    let text = text.strip_prefix('$').unwrap_or(text);
    i64::from_str_radix(text, 16).ok()
}

struct Assembler {
    origin: u16,
    labels: HashMap<String, i64>,
}

impl Assembler {
    /// If the operand has the expected shape, its value.
    fn fit(&self, shape: &str, operand: &str) -> Option<i64> {
        match shape {
            "" => (operand.is_empty()).then_some(0),
            // An unknown label, on the first pass, is the origin: the second
            // pass has them all.
            "rel" => Some(*self.labels.get(operand).unwrap_or(&(self.origin as i64))),
            "y" => (operand == "y").then_some(0),
            "abs" => number(operand, "!"),
            "dp" => number(operand, "$"),
            "[dp]+y,a" => {
                let inner = operand.strip_prefix('[')?.strip_suffix("]+y,a")?;
                number(inner, "$")
            }
            _ => {
                let (target, source) = shape.split_once(',')?;
                let (left, right) = operand.split_once(',').unwrap_or((operand, ""));
                let register = |s: &str| matches!(s, "a" | "x" | "y");
                if register(target) && left != target {
                    return None;
                }
                if register(source) && right != source {
                    return None;
                }
                let slot = if register(target) { right } else { left };
                if source == "imm" {
                    return number(slot, "#");
                }
                if source == "dp" || target == "dp" {
                    return number(slot, "$");
                }
                Some(0)
            }
        }
    }

    fn encode(&self, mnemonic: &str, operand: &str, address: i64) -> Result<Vec<u8>> {
        for &(name, shape, opcode, size) in OPCODES {
            if name != mnemonic {
                continue;
            }
            let Some(value) = self.fit(shape, operand) else {
                continue;
            };
            if size == 0 {
                return Ok(vec![opcode]);
            }
            if shape == "abs" {
                return Ok(vec![
                    opcode,
                    (value & 0xFF) as u8,
                    ((value >> 8) & 0xFF) as u8,
                ]);
            }
            if shape == "rel" {
                // Branches are relative to the end of the instruction.
                let offset = value - (address + 2);
                if !(-128..=127).contains(&offset) {
                    return Err(Bad::usage(format!(
                        "branch out of range: {mnemonic} {operand}"
                    )));
                }
                return Ok(vec![opcode, (offset & 0xFF) as u8]);
            }
            return Ok(vec![opcode, (value & 0xFF) as u8]);
        }
        Err(Bad::usage(format!("cannot assemble: {mnemonic} {operand}")))
    }

    fn pass(&mut self, source: &str) -> Result<Vec<u8>> {
        let mut code = Vec::new();
        for line in source.lines() {
            let line = line.split(';').next().unwrap().trim();
            if line.is_empty() {
                continue;
            }
            let here = self.origin as i64 + code.len() as i64;
            if let Some(label) = line.strip_suffix(':') {
                self.labels.insert(label.to_string(), here);
                continue;
            }
            let (mnemonic, operand) = line.split_once(char::is_whitespace).unwrap_or((line, ""));
            let operand: String = operand
                .chars()
                .filter(|c| *c != ' ')
                .collect::<String>()
                .to_lowercase();
            code.extend(self.encode(&mnemonic.to_lowercase(), &operand, here)?);
        }
        Ok(code)
    }
}

/// Assembles `source` to run at `origin`, in two passes: the first one
/// learns where the labels are.
pub fn assemble(source: &str, origin: u16) -> Result<Vec<u8>> {
    let mut a = Assembler {
        origin,
        labels: HashMap::new(),
    };
    a.pass(source)?;
    a.pass(source)
}

/// The driver, assembled at [`DRIVER_ADDR`].
pub fn driver() -> Vec<u8> {
    assemble(DRIVER, DRIVER_ADDR).expect("the driver assembles")
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The driver's bytes as the assembler this one replaced produced them:
    /// if this changes, the SPC700 runs something else.
    #[test]
    fn the_driver_is_the_one_it_was() {
        let d = driver();
        assert_eq!(d.len(), 104);
        assert_eq!(&d[..8], &[0xF8, 0xF7, 0x3E, 0xF7, 0xF0, 0xFC, 0xF8, 0xF7]);
    }

    #[test]
    fn a_branch_too_far_is_refused() {
        let mut far = String::from("start:\n");
        for _ in 0..70 {
            far.push_str("    mov a, #$00\n");
        }
        far.push_str("    bra start\n");
        assert!(assemble(&far, 0x200).is_err());
    }
}
