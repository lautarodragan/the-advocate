//! Walking a page already compiled, without running it: what the converter
//! asks of the bytecode —which events a page sends walking, who it flashes,
//! which battle animations and troops it shows—. The sizes come from the
//! protocol's declaration, through the compiler's generated module.

use crate::fail::{Result, Stop};
use rm2k_snes_bytecode::events::BYTECODE;

/// How many bytes the opcode starting at `code[i]` takes.
pub fn opcode_size(code: &[u8], i: usize) -> Result<usize> {
    let op = code[i];
    if BYTECODE.opcode(op).is_none() {
        return Err(Stop::new(format!("unknown opcode: 0x{op:02X}")));
    }
    Ok(BYTECODE.size_at(code, i).unwrap())
}

/// The offset of each opcode of a compiled page.
pub fn walk(code: &[u8]) -> Result<Vec<usize>> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < code.len() {
        out.push(i);
        i += opcode_size(code, i)?;
    }
    Ok(out)
}

/// `code[i]`, or 0 past the end —an operand a truncated page lacks—.
pub fn at(code: &[u8], i: usize) -> u8 {
    code.get(i).copied().unwrap_or(0)
}
