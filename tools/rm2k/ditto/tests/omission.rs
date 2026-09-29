//! How far the omission rule goes, measured.
//!
//! The exact round trip rests on **"a field holding its default is not
//! written"**. That is not a decision of ours: it is what the editor does. But
//! it is a decision *of whoever writes*, so a file that did store a field with
//! its default value explicitly would come out of our round trip without that
//! chunk, and the binary would not be identical.
//!
//! These two tests pin down both sides of the number: how much is lost if it
//! happens, and how many times the real editor chose to omit in a real game.
//! See `README.md`, "The limit of the omission rule, measured".

mod common;

use std::path::PathBuf;

/// Splits a `.lmu` into (raw header, top-level chunks).
fn split(d: &[u8]) -> (Vec<u8>, Vec<(u32, Vec<u8>)>) {
    let mut l = ditto::lcf::Reader::new(d);
    let n = l.ber().unwrap() as usize;
    l.bytes(n).unwrap();
    let head = d[..l.pos].to_vec();
    let mut chunks = Vec::new();
    loop {
        let id = l.ber().unwrap() as u32;
        if id == 0 {
            break;
        }
        let length = l.ber().unwrap() as usize;
        chunks.push((id, l.bytes(length).unwrap().to_vec()));
    }
    (head, chunks)
}

fn assemble(head: &[u8], chunks: &[(u32, Vec<u8>)]) -> Vec<u8> {
    let mut e = ditto::lcf::Writer::new();
    e.bytes(head);
    e.dump(chunks.to_vec(), &[]);
    e.ber(0);
    e.b
}

fn round_trip(bin: &[u8]) -> Vec<u8> {
    let doc = ditto::file::read(bin).unwrap();
    ditto::file::write(&doc).unwrap()
}

/// `generator_surround` is field 0x33 of `Map` and its default is `True`, so a
/// map written by the editor never carries it.
const FIELD: u32 = 0x33;

/// **The known limit, not a bug that slipped in.** A chunk written by hand with
/// the field's default value does not survive the round trip: exactly its three
/// bytes —id, length and body— are lost and everything behind it shifts.
///
/// If it is ever covered, this is the test to turn around.
#[test]
fn a_hand_written_default_is_lost() {
    let Some(dir) = common::dir() else { return };
    let maps = common::maps(&dir);
    if maps.is_empty() {
        println!("SKIPPED: {dir:?} has no .lmu files.");
        return;
    }
    // Any map that does not already carry the field will do for the measurement.
    let Some((map, head, chunks)) = maps.iter().find_map(|p| {
        let d = std::fs::read(p).ok()?;
        let (head, chunks) = split(&d);
        (!chunks.iter().any(|c| c.0 == FIELD)).then_some((p.clone(), head, chunks))
    }) else {
        println!("SKIPPED: every map in {dir:?} already carries chunk {FIELD:#04x}.");
        return;
    };
    let original = std::fs::read(&map).unwrap();

    assert_eq!(
        assemble(&head, &chunks),
        original,
        "the raw reassembly does not give the original"
    );
    assert_eq!(round_trip(&original), original, "the plain round trip already fails");

    let mut with = chunks.clone();
    with.push((FIELD, vec![0x01]));
    with.sort_by_key(|c| c.0);

    let input = assemble(&head, &with);
    assert_eq!(input.len(), original.len() + 3);
    let output = round_trip(&input);
    assert_eq!(
        output.len(),
        input.len() - 3,
        "the explicit chunk should be lost: those are its 3 bytes"
    );
    assert_eq!(output, original, "what comes out is the file without that chunk");
}

/// The other half of the number: the editor **does** omit. Over a real game,
/// only a fraction of the chunks `Map` could write at its top level are
/// actually present. With that, the whole corpus coming back byte for byte
/// stops being luck and becomes proof that the real editor follows the same
/// rule as Ditto.
#[test]
fn the_editor_omits_the_defaults() {
    let Some(dir) = common::dir() else { return };
    let maps: Vec<PathBuf> = common::maps(&dir);
    if maps.is_empty() {
        println!("SKIPPED: {dir:?} has no .lmu files.");
        return;
    }

    // How many top-level chunks a `Map` can write, per `fields.csv`.
    let possible_per_map = 33usize;
    let present: usize = maps
        .iter()
        .map(|a| split(&std::fs::read(a).unwrap()).1.len())
        .sum();
    let possible = possible_per_map * maps.len();
    println!(
        "{} maps: {} chunks present of {} possible; the editor omitted {}",
        maps.len(),
        present,
        possible,
        possible.saturating_sub(present)
    );
    assert!(
        present * 2 < possible,
        "most of the possible chunks should be omitted; if this drops, the \
         evidence that the editor omits got weaker"
    );
}
