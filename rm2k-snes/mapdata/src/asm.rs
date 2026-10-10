//! The two primitives the `.inc` is written with: a data block with its
//! placement declaration, and a symbolic 24-bit pointer.

use std::fmt::Write;

/// A data block with its placement declaration, sixteen bytes a line.
///
/// Each block is declared before emitting it: almost all are uploaded by
/// DMA, and a DMA that crosses a bank reads garbage from the middle onward.
/// The same holds for a table walked with `[ptr], y` or with
/// `lda f:table, x`: it has to stay whole on one side, and its pointers
/// being symbolic is not enough. Split, the console reads the second half
/// from `$0000` of the next bank, which is not where the packing put it
/// unless the two banks continue each other —and in LoROM, where this
/// first bit, was the WRAM mirror—. It is
/// an error that appears or disappears when a byte is added anywhere else
/// in the cartridge.
pub fn block(label: &str, data: &[u8]) -> String {
    placed(label, data, Some(format!(".block {}", data.len())))
}

/// [`block`] aligned to `align` bytes instead of declared whole.
pub fn aligned(label: &str, data: &[u8], align: usize) -> String {
    placed(label, data, Some(format!(".align {align}")))
}

/// [`block`] without a declaration, for what goes to `TABLES`: that area
/// lives inside bank 0, so nothing that falls there can cross, and the
/// declaration would be a computation that always comes out zero.
pub fn unplaced(label: &str, data: &[u8]) -> String {
    placed(label, data, None)
}

fn placed(label: &str, data: &[u8], declaration: Option<String>) -> String {
    let mut out = String::new();
    if let Some(declaration) = declaration {
        out.push_str(&declaration);
        out.push('\n');
    }
    out.push_str(label);
    out.push(':');
    for line in data.chunks(16) {
        out.push_str("\n    .byte ");
        for (k, b) in line.iter().enumerate() {
            if k > 0 {
                out.push(',');
            }
            let _ = write!(out, "${b:02X}");
        }
    }
    out
}

/// The three bytes of a symbolic pointer, for `.byte`.
pub fn pointer(dest: &str) -> String {
    format!("<({dest}), >({dest}), ^({dest})")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_block_is_declared_and_cut_every_sixteen_bytes() {
        let data: Vec<u8> = (0..18).collect();
        assert_eq!(
            block("x", &data),
            ".block 18\nx:\n    .byte $00,$01,$02,$03,$04,$05,$06,$07,$08,$09,$0A,$0B,$0C,\
             $0D,$0E,$0F\n    .byte $10,$11"
        );
        assert_eq!(unplaced("y", &[0xAB]), "y:\n    .byte $AB");
        assert_eq!(aligned("z", &[], 256), ".align 256\nz:");
    }

    #[test]
    fn a_pointer_takes_its_three_bytes_from_the_label() {
        assert_eq!(pointer("pose_3"), "<(pose_3), >(pose_3), ^(pose_3)");
    }
}
