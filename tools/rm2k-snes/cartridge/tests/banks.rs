//! The bank packing.
//!
//! What these guard is not that the filling is pretty but that it respects
//! what the generated data declares: a block that crosses a bank is uploaded
//! by DMA reading the start of its own bank from the middle onwards, and that
//! does not fail at assembly, it fails by drawing garbage. The big net is whatever runs the
//! ROMs; this is the small one, and it makes an error show up here and not
//! in a screenshot.

use cartridge::banks::{
    self, cfg, file_offset, pack_texts, segment_of, size, slots, Slot, BANK_SIZE, HALF,
};

const B2: &str = ".segment \"BANKC2\"";
const B3: &str = ".segment \"BANKC3\"";

/// Runs the packing over one or two texts, into `slots`: what each becomes,
/// and (pieces, banks).
fn resolve_into(texts: &[&str], slots: &[Slot]) -> Result<(Vec<String>, (usize, usize)), String> {
    let names: Vec<String> = (0..texts.len()).map(|i| format!("part{i}.inc")).collect();
    let (out, packing) = pack_texts(&names, texts, slots)?;
    Ok((out, (packing.pieces, packing.banks)))
}

/// The same, into the cartridge's.
fn resolve(texts: &[&str]) -> Result<(Vec<String>, (usize, usize)), String> {
    resolve_into(texts, &slots())
}

/// What the packing wrote in `bank`'s segment.
fn bank(text: &str, bank: usize) -> &str {
    let (_, rest) = split_at(text, &format!(".segment \"{}\"", segment_of(bank)));
    rest.split(".segment").next().unwrap()
}

fn whole(bank: usize) -> Slot {
    Slot { bank, start: 0, size: BANK_SIZE }
}

fn one(text: &str) -> (String, (usize, usize)) {
    let (mut out, count) = resolve(&[text]).unwrap();
    (out.remove(0), count)
}

fn bytes(n: usize) -> String {
    format!("    .byte {}\n", vec!["$00"; n].join(","))
}

fn rodata() -> String {
    ".segment \"RODATA\"\n".to_string()
}

fn split_at<'a>(text: &'a str, marker: &str) -> (&'a str, &'a str) {
    let i = text.find(marker).expect("the marker is there");
    (&text[..i], &text[i + marker.len()..])
}

#[test]
fn rodata_becomes_the_bank_where_the_data_starts() {
    let (out, count) = one(&(rodata() + ".block 16\n" + &bytes(1)));
    assert!(out.contains(B2) && !out.contains("RODATA") && !out.contains(".block"));
    assert_eq!(count, (1, 1));
}

#[test]
fn a_block_that_does_not_fit_goes_to_another_bank() {
    // The case that gives meaning to everything: a block is never split. The
    // big one goes first, and the 16 bytes no longer fit in the 8 it leaves.
    let text = rodata()
        + ".block 16\nsmall:\n"
        + &bytes(16)
        + &format!(".block {}\nlabel:\n", BANK_SIZE - 8)
        + &bytes(8).repeat((BANK_SIZE - 8) / 8);
    let (out, count) = one(&text);
    let (b2, b3) = split_at(&out, B3);
    assert!(b2.contains("label:") && b3.contains("small:"));
    assert_eq!(count, (2, 2));
}

#[test]
fn first_fit_decreasing_fills_the_gaps() {
    // In order, two blocks of more than half a bank and two of less ask for
    // three banks. From largest to smallest, two.
    let half = BANK_SIZE / 2;
    let mut text = rodata();
    for (name, n) in [("a", half + 16), ("b", half + 16), ("c", half - 16), ("d", half - 16)] {
        text += &format!(".block {n}\n{name}:\n");
        text += &bytes(16).repeat(n / 16);
    }
    let (out, count) = one(&text);
    assert_eq!(count, (4, 2));
    let (b2, b3) = split_at(&out, B3);
    assert!(b2.contains("a:") && b2.contains("c:") && b3.contains("b:") && b3.contains("d:"));
}

#[test]
fn one_bigger_than_a_bank_starts_a_bank_and_lends_the_rest() {
    let text = rodata()
        + ".block 64\nsmall:\n"
        + &bytes(16).repeat(4)
        + &format!(".block {}\ntexts:\n", BANK_SIZE + 32)
        + &bytes(16).repeat(BANK_SIZE / 16 + 2);
    let (out, count) = one(&text);
    assert_eq!(count, (2, 2));
    let (b2, b3) = split_at(&out, B3);
    assert_eq!(b2.split('\n').nth(1), Some("texts:"), "it has to start the bank");
    assert!(b3.contains("small:") && b3.find("small:") > b3.find("$00"));
}

#[test]
fn the_exact_edge_fits() {
    let (out, _) = one(&(rodata() + &format!(".block {BANK_SIZE}\n")));
    assert!(!out.contains(B3));
}

#[test]
fn a_full_bank_is_left_before_the_label() {
    // A label at the end of a bank would point outside the ROM.
    let (out, _) = one(&(rodata() + &bytes(16).repeat(BANK_SIZE / 16) + "label:\n" + &bytes(1)));
    assert!(out.find(B3) < out.find("label:"));
}

#[test]
fn what_does_not_fit_is_split_between_two_banks() {
    let (out, _) = one(
        &(rodata()
            + &bytes(16).repeat(BANK_SIZE / 16 - 1)
            + &bytes(8)
            + "    .word $1111,$2222,$3333,$4444,$5555,$6666\n"),
    );
    let (before, after) = split_at(&out, B3);
    assert!(before.contains("$1111, $2222, $3333, $4444"));
    assert!(after.contains("$5555, $6666") && !after.contains("$4444"));
}

#[test]
fn a_word_is_not_split() {
    let error = resolve(&[&(rodata()
        + &bytes(16).repeat(BANK_SIZE / 16 - 1)
        + &bytes(15)
        + "    .word $1111,$2222\n")])
    .unwrap_err();
    assert!(error.contains("middle of a"), "{error}");
}

#[test]
fn what_is_not_rodata_does_not_count() {
    let (out, _) = one(
        &(rodata()
            + &bytes(16)
            + ".segment \"TABLES\"\n"
            + &bytes(BANK_SIZE - 16)
            + &rodata()
            + &format!(".block {}\n", BANK_SIZE - 16)),
    );
    assert!(!out.contains(B3));
    assert!(out.contains(".segment \"TABLES\""));
}

#[test]
fn the_banks_go_at_the_end_of_the_last_file() {
    let first = rodata() + "CONSTANT = 7\n.block 16\none:\n" + &bytes(16);
    let second = rodata() + &format!(".block {0}\nother:\n     .res {0}\n", BANK_SIZE - 8);
    let (out, _) = resolve(&[&first, &second]).unwrap();
    assert!(!out[0].contains("BANK") && !out[0].contains("one:"));
    assert!(out[0].contains("CONSTANT = 7"));
    assert!(out[1].contains(B2) && out[1].contains(B3) && out[1].contains("one:"));
}

#[test]
fn what_does_not_fit_in_the_cartridge_says_so() {
    let fit = slots().iter().filter(|s| s.size == BANK_SIZE).count();
    let mut text = rodata();
    for k in 0..=fit {
        text += &format!(".block {0}\nb{k}:\n     .res {0}\n", BANK_SIZE);
    }
    let error = resolve(&[&text]).unwrap_err();
    assert!(error.contains("does not fit"), "{error}");
}

#[test]
fn the_fast_banks_go_first() {
    let mut text = rodata();
    let fast = slots().iter().filter(|s| s.size == BANK_SIZE && s.fast()).count();
    for k in 0..=fast {
        text += &format!(".block {0}\nb{k}:\n     .res {0}\n", BANK_SIZE);
    }
    let (out, _) = one(&text);
    let (before, after) = split_at(&out, ".segment \"BANK42\"");
    assert!(before.contains(".segment \"BANKFF\"") && !after.contains("BANKC"));
    assert!(after.contains(&format!("b{fast}:")));
}

#[test]
fn a_half_takes_what_fits_in_it() {
    // The 40 KB one does not fit in what the big one leaves, nor in the half:
    // it opens the slow bank. The 30 KB one fits in neither of the two open
    // ones, and opens the half.
    let slots = [whole(0xC2), Slot { bank: 0xC0, start: 0, size: HALF }, whole(0x42)];
    let text = rodata()
        + ".block 61440\nbig:\n     .res 61440\n"
        + ".block 40960\nmiddle:\n     .res 40960\n"
        + ".block 30720\nsmall:\n     .res 30720\n";
    let (out, count) = resolve_into(&[&text], &slots).unwrap();
    assert_eq!(count, (3, 3));
    assert!(bank(&out[0], 0xC0).contains("small:"), "{}", out[0]);
    assert!(bank(&out[0], 0x42).contains("middle:"), "{}", out[0]);
}

#[test]
fn a_chain_does_not_cross_between_two_runs() {
    // `$C2:FFFF` is not followed by `$42:0000`: the stream that does not fit
    // in the 16 bytes left starts in the next bank instead of crossing.
    let slots = [whole(0xC2), whole(0x42)];
    let text = rodata()
        + &format!(".block {0}\nbig:\n     .res {0}\n", BANK_SIZE - 16)
        + ".crossbank\nstream:\n"
        + &bytes(16).repeat(4);
    let (out, _) = resolve_into(&[&text], &slots).unwrap();
    assert!(bank(&out[0], 0x42).contains("stream:"), "{}", out[0]);
}

#[test]
fn a_piece_longer_than_its_run_is_an_error() {
    let slots = [whole(0xC2), whole(0x42)];
    let text = rodata() + ".crossbank\nstream:\n" + &bytes(16).repeat(BANK_SIZE / 16 + 1);
    let error = resolve_into(&[&text], &slots).unwrap_err();
    assert!(error.contains("no free bank continues it"), "{error}");
}

#[test]
fn the_cartridge_decodes_addresses_like_exhirom() {
    assert_eq!(file_offset(0xC00000), Some(0x000000));
    assert_eq!(file_offset(0x808000), Some(0x008000));
    assert_eq!(file_offset(0xFFFFFF), Some(0x3FFFFF));
    assert_eq!(file_offset(0x400000), Some(0x400000));
    assert_eq!(file_offset(0x008000), Some(0x408000));
    assert_eq!(file_offset(0x3F8000), Some(0x7F8000));
    assert_eq!(file_offset(0x7D0000), Some(0x7D0000));
    assert_eq!(file_offset(0x7E0000), None, "the WRAM");
    assert_eq!(file_offset(0x802000), None, "the registers");
}

#[test]
fn every_slot_is_rom_and_none_overlaps() {
    let mut seen = std::collections::HashSet::new();
    for slot in slots() {
        let start = file_offset(slot.address()).expect("ROM");
        assert_eq!(file_offset(slot.address() + slot.size - 1), Some(start + slot.size - 1));
        for half in (start..start + slot.size).step_by(HALF) {
            assert!(seen.insert(half), "${:06X} twice", slot.address());
            // Neither the code banks nor their copies.
            assert!(banks::MIRRORS.iter().all(|&(a, b, _)| half != a && half != b));
            // Nor the low halves of `$70-$7D`, which some emulators make SRAM.
            assert!(!(0x700000..0x7E0000).contains(&half) || half & 0x8000 != 0);
        }
    }
}

#[test]
fn how_much_each_line_takes() {
    for (line, n) in [
        ("    .byte $00,$01,$02", 3),
        ("    .word $0000,$0001", 4),
        ("    .dword $00000000", 4),
        ("    .byte", 0),
        ("    .byte  ; nothing", 0),
        ("    .byte $00,$01  ; two, and a comma in the comment", 2),
        ("    .byte \"a,b\", $00", 2),
        ("label:", 0),
        ("CONSTANT = 7", 0),
        ("; a comment", 0),
        ("", 0),
        ("    .res 12", 12),
    ] {
        assert_eq!(size(line).unwrap(), n, "{line:?}");
    }
}

#[test]
fn align_is_left_alone_but_counted() {
    // If its padding did not enter the count, every block below would be
    // packed against a shifted number.
    let (out, _) = one(
        &(rodata()
            + &format!(".block {0}\nbig:\n     .res {0}\n", BANK_SIZE - 1)
            + ".align 2\n.block 1\naligned:\n     .byte $00\n"),
    );
    assert!(out.contains(".align 2"));
    // One byte is left, and with the alignment counted the one-byte one no
    // longer fits.
    assert!(out.find(B3) < out.find("aligned:"));
}

#[test]
fn a_block_outside_rodata_is_not_silent() {
    // There the packing cannot be computed, and the assembler would accept
    // the directive.
    let error = resolve(&[".segment \"TABLES\"\n.block 12\n     .byte $00\n"]).unwrap_err();
    assert!(error.contains("unresolved"), "{error}");
}

#[test]
fn a_table_without_a_block_is_not_silent() {
    // A table read with `lda f:table, x` cannot cross a bank: the index
    // carries the address to the next bank's `$0000`, which is not where the
    // packing put the rest unless the two banks continue each other. So the
    // packing **always** refuses, not only on the day the cut lands on it:
    // the error is latent.
    let error = resolve(&[&(rodata()
        + ".block 4\ncovered:\n    .word $1111,$2222\n"
        + "loose_table:\n    .word $3333,$4444\n")])
    .unwrap_err();
    assert!(error.contains("loose_table"), "{error}");
}

#[test]
fn a_block_covers_the_tables_inside_it() {
    // And a one-byte label cannot be split.
    resolve(&[&(rodata()
        + ".block 8\none:\n     .word 1,2\n"
        + "other:\n    .word 3,4\nloose:\n    .byte 5\n")])
    .unwrap();
}

#[test]
fn what_crosses_on_purpose_is_declared() {
    let (out, _) = one(
        &(rodata()
            + &bytes(16).repeat(BANK_SIZE / 16 - 1)
            + ".crossbank\nstream:\n"
            + &bytes(16)
            + &bytes(16)),
    );
    let (before, after) = split_at(&out, B3);
    assert!(before.contains("stream:") && !out.contains(".crossbank"));
    // The continuation goes first in the next bank, at its `$0000`.
    assert!(after.split('\n').nth(1).unwrap().starts_with("    .byte"));
}

#[test]
fn what_crosses_and_fits_whole_fills_a_gap() {
    let (out, count) = one(
        &(rodata()
            + &format!(".block {0}\nbig:\n     .res {0}\n", BANK_SIZE - 64)
            + &format!(".block {0}\nother:\n     .res {0}\n", BANK_SIZE - 16)
            + ".crossbank\nstream:\n"
            + &bytes(16).repeat(3)),
    );
    assert_eq!(count, (3, 2));
    let (b2, b3) = split_at(&out, B3);
    assert!(b2.contains("other:") && b3.contains("big:") && b3.contains("stream:"));
}

#[test]
fn running_it_twice_changes_nothing() {
    let text = rodata()
        + "CONSTANT = 7\n.block 64\nsmall:\n"
        + &bytes(16).repeat(4)
        + ".crossbank\nstream:\n"
        + &bytes(16).repeat(3);
    let (once, _) = one(&text);
    let (twice, count) = one(&once);
    assert_eq!(once, twice);
    assert_eq!(count, (0, 0));
}

#[test]
fn line_endings_and_blank_lines_come_back_as_they_were() {
    // The data files are rewritten in place: whatever is outside RODATA has
    // to come out byte for byte.
    let text = ".segment \"TABLES\"\r\n    .byte 1\r\n\r\n; x\n";
    let (out, _) = one(text);
    assert_eq!(out, ".segment \"TABLES\"\n    .byte 1\n\n; x\n");
}

#[test]
fn the_memory_map_puts_each_bank_in_place() {
    let text = cfg();
    assert!(text.contains("ROM:  start = $008000, size = $7FC0, fill = yes;"));
    assert!(text.contains("BANK01: start = $018000, size = $8000, fill = yes;"));
    assert!(text.contains("BANKC2: start = $C20000, size = $10000, fill = yes;"));
    assert!(text.contains("BANK7D: start = $7D8000, size = $8000, fill = yes;"));
    assert!(!text.contains("BANK7E"), "banks $7E and $7F are the WRAM");
    assert!(text.contains("FAR:      load = BANK01"));
    assert!(text.contains("BANKC2: load = BANKC2"));
    // The areas go in file order, and add up to the 8 MB.
    let mut offset = 0;
    let mut bank0 = None;
    for line in text.lines() {
        let Some(rest) = line.split("size = $").nth(1) else { continue };
        let Some((hex, tail)) = rest.split_once(',') else { continue };
        if !tail.trim_start().starts_with("fill") {
            continue;
        }
        if line.trim_start().starts_with("ROM:") {
            bank0 = Some(offset);
        }
        let start = line.split("start = $").nth(1).unwrap().split(',').next().unwrap();
        let start = usize::from_str_radix(start, 16).unwrap();
        if line.trim_start().starts_with("BANK") && !line.contains("BANK01") {
            assert_eq!(file_offset(start), Some(offset), "{line}");
        }
        offset += usize::from_str_radix(hex, 16).unwrap();
    }
    assert_eq!(offset, banks::ROM_SIZE);
    assert_eq!(bank0, Some(0x008000), "where the console sees $80:8000");
}
