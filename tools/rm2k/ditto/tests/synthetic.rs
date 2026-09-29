//! A corpus Ditto builds for itself.
//!
//! The other tests need somebody's game in `DITTO_CORPUS` and skip without it.
//! These need nothing: the file under test is written here, byte by byte or
//! field by field, so a fresh clone measures something real.
//!
//! **What this proves and what it does not.** Writing a struct, reading it
//! back and finding it equal only proves that the reader and the writer agree
//! with each other. If both misread the same field the same way, the
//! comparison comes out clean and says nothing. That is why the first half of
//! this file is not a round trip at all: the bytes are **written out by hand**
//! from the format —a BER integer, a chunk `(id, length, body)`, the omission
//! rule— and the assertions say which value each byte stands for. A reader
//! that invents its own format fails those.
//!
//! The real game stays necessary for the opposite reason: only it proves that
//! the format written here is the one RPG Maker actually writes. The two
//! corpora answer different questions and neither replaces the other.

use ditto::file::Document;
use ditto::lcf::*;
use ditto::schema::*;

// --- Written out by hand ---------------------------------------------------

/// BER: seven bits per byte, most significant group first, the high bit says
/// another byte follows. The encoding is canonical —the fewest bytes— which is
/// what makes a rewritten file identical and not merely equivalent.
#[test]
fn ber_integers_are_the_bytes_the_format_says() {
    for (value, bytes) in [
        (0i32, &[0x00][..]),
        (1, &[0x01][..]),
        (127, &[0x7F][..]),
        // The first boundary: 128 no longer fits in seven bits.
        (128, &[0x81, 0x00][..]),
        (16383, &[0xFF, 0x7F][..]),
        (16384, &[0x81, 0x80, 0x00][..]),
        // Negatives travel as two's complement, so they take all five bytes.
        (-1, &[0x8F, 0xFF, 0xFF, 0xFF, 0x7F][..]),
        (i32::MIN, &[0x88, 0x80, 0x80, 0x80, 0x00][..]),
    ] {
        assert_eq!(enc_ber(value), bytes, "writing {value}");
        assert_eq!(dec_ber(bytes), value, "reading {bytes:02x?}");
    }
}

/// The 0x80..0x9F range is where cp1252 departs from Latin-1, and it has to be
/// a bijection: a byte no table names still has to come back as itself.
#[test]
fn text_survives_the_high_bytes() {
    let all: Vec<u8> = (0u8..=255).collect();
    assert_eq!(enc_text(&dec_text(&all)), all);
    assert_eq!(dec_text(&[0x80]), "\u{20AC}"); // €
    assert_eq!(dec_text(&[0x81]), "\u{0081}"); // undefined in cp1252, kept
}

/// A map written out chunk by chunk, to say what each byte means.
fn a_map_by_hand() -> Vec<u8> {
    let mut b = vec![0x0A];
    b.extend_from_slice(b"LcfMapUnit");
    b.extend_from_slice(&[0x01, 0x01, 0x07]); // chipset_id = 7
    b.extend_from_slice(&[0x02, 0x02, 0x81, 0x00]); // width = 128
    b.extend_from_slice(&[0x03, 0x01, 0x21]); // height = 33
    b.extend_from_slice(&[0x0B, 0x01, 0x01]); // scroll_type = 1
    b.extend_from_slice(&[0x20, 0x02, b'h', b'i']); // parallax_name = "hi"
    b.extend_from_slice(&[0x47, 0x04, 0x01, 0x00, 0xFF, 0xFF]); // lower = [1, -1]
    b.extend_from_slice(&[0x48, 0x00]); // upper = [], and written anyway
    b.extend_from_slice(&[0x51, 0x01, 0x00]); // events: a count of zero
    b.extend_from_slice(&[0x7F, 0x03, 0xAA, 0xBB, 0xCC]); // nobody's field
    b.push(0x00); // the id that closes the struct
    b
}

#[test]
fn the_hand_written_map_reads_as_those_values() {
    let Document::Lmu { header, data } = ditto::file::read(&a_map_by_hand()).unwrap() else {
        panic!("a LcfMapUnit header should give a map");
    };
    assert_eq!(header, "LcfMapUnit");
    assert_eq!(data.chipset_id, 7);
    assert_eq!(data.width, 128);
    assert_eq!(data.height, 33);
    assert_eq!(data.scroll_type.to_i32(), 1);
    assert_eq!(data.parallax_name, "hi");
    assert_eq!(data.lower_layer, vec![1i16, -1]);
    assert!(data.upper_layer.is_empty());
    assert!(data.events.is_empty());
    // A field the schema does not name is kept as it came, which is what lets
    // a file written by a newer editor come back whole.
    assert_eq!(
        data.unknown,
        vec![RawChunk { id: 0x7F, bytes: vec![0xAA, 0xBB, 0xCC] }]
    );
    // And every field the map does not carry holds the format's default, not
    // the zero of its type.
    assert_eq!(data.generator_width, 4);
    assert!(data.generator_surround);
}

#[test]
fn the_hand_written_map_is_written_back_identical() {
    let original = a_map_by_hand();
    let doc = ditto::file::read(&original).unwrap();
    assert_eq!(ditto::file::write(&doc).unwrap(), original);
}

/// The rule that makes this format hard: a field holding its default is not
/// written at all —except for the handful the tables mark otherwise, which are
/// written even when empty—. Spelled out in bytes, an untouched map is this
/// short.
#[test]
fn a_default_map_is_only_its_persisted_fields() {
    let doc = Document::Lmu {
        header: "LcfMapUnit".into(),
        data: Map::default(),
    };
    let mut want = vec![0x0A];
    want.extend_from_slice(b"LcfMapUnit");
    want.extend_from_slice(&[0x0B, 0x01, 0x00]); // scroll_type, persisted
    want.extend_from_slice(&[0x47, 0x00]); // lower_layer, persisted and empty
    want.extend_from_slice(&[0x48, 0x00]); // upper_layer, the same
    want.extend_from_slice(&[0x51, 0x01, 0x00]); // events: a count of zero
    want.push(0x00);
    assert_eq!(ditto::file::write(&doc).unwrap(), want);
}

/// The JSON follows the same rule, so a default struct writes no fields at all
/// —and comes back holding the format's defaults, not the type's.
#[test]
fn the_json_omits_the_defaults_too() {
    assert_eq!(serde_json::to_string(&Enemy::default()).unwrap(), "{}");
    let back: Enemy = serde_json::from_str("{}").unwrap();
    assert_eq!(back.max_hp, 10);
    assert_eq!(back, Enemy::default());

    // A field set to its default explicitly is the same thing as not setting
    // it: this is what a JSON that hides the defaults costs, and it has to be
    // the same value the binary omits.
    let e = Enemy { max_hp: 10, ..Default::default() };
    assert_eq!(serde_json::to_string(&e).unwrap(), "{}");
    let e = Enemy { max_hp: 11, ..Default::default() };
    assert_eq!(serde_json::to_string(&e).unwrap(), r#"{"max_hp":11}"#);
}

/// `stringify!` keeps the `r#` of a raw identifier, so the field the tables
/// call `type` used to serialize as `"r#type"` and read back as its default.
/// It cost a Skill that turned from a teleport into a normal attack.
#[test]
fn the_field_called_type_keeps_its_name() {
    let m = MapInfo { r#type: TreeMapMapType::from_i32(2), ..Default::default() };
    let json = serde_json::to_string(&m).unwrap();
    assert!(json.contains("\"type\""), "{json}");
    assert!(!json.contains("r#"), "{json}");
    let back: MapInfo = serde_json::from_str(&json).unwrap();
    assert_eq!(back.r#type.to_i32(), 2);
}

// --- Built, written, and read back -----------------------------------------

/// Writes the document, reads it back, and comes back through the JSON too.
/// Both ways have to give the same structure **and** the same bytes.
fn closes(doc: &Document) {
    let binary = ditto::file::write(doc).unwrap();
    let back = ditto::file::read(&binary).unwrap();
    assert_eq!(&back, doc, "the binary does not give back the same structure");
    assert_eq!(ditto::file::write(&back).unwrap(), binary, "writing is not stable");

    let json = serde_json::to_vec(doc).unwrap();
    let from_json: Document = serde_json::from_slice(&json).unwrap();
    assert_eq!(&from_json, doc, "the JSON does not give back the same structure");
    assert_eq!(ditto::file::write(&from_json).unwrap(), binary);
}

/// The values a real game rarely holds: the extremes of BER, text with high
/// bytes, empty vectors next to full ones, and a field left at its default on
/// purpose.
#[test]
fn a_map_of_awkward_values_closes() {
    let command = |code: i32, indent: i32, string: &str, parameters: Vec<i32>| EventCommand {
        code: EventCommandCode::from_i32(code),
        indent,
        string: string.to_string(),
        parameters,
        ..Default::default()
    };
    let page = EventPage {
        id: 1,
        event_commands: vec![
            command(10110, 0, "€ ñ \u{0081}", vec![]),
            command(10140, 1, "", vec![i32::MIN, -1, 0, 127, 128, i32::MAX]),
            command(20110, 2, "the last one", vec![1]),
        ],
        ..Default::default()
    };
    let data = Map {
        chipset_id: 0,
        width: 16384,
        height: 15, // its default, on purpose: it must not be written
        parallax_name: "a name with a € in it".to_string(),
        lower_layer: vec![i16::MIN, -1, 0, i16::MAX],
        upper_layer: Vec::new(),
        save_count: 128,
        events: vec![
            Event { id: 1, name: "one".into(), x: -1, y: 16383, pages: vec![page], ..Default::default() },
            Event { id: 4096, ..Default::default() },
        ],
        unknown: vec![RawChunk { id: 0x64, bytes: vec![0x00, 0xFF] }],
        ..Default::default()
    };
    // Said out loud, because a round trip would pass either way: the default
    // field left the binary.
    let binary = ditto::file::write(&Document::Lmu { header: "LcfMapUnit".into(), data: data.clone() }).unwrap();
    assert!(
        !binary.windows(3).any(|w| w == [0x03, 0x01, 0x0F]),
        "height was written even though it holds its default"
    );
    closes(&Document::Lmu { header: "LcfMapUnit".into(), data });
}

#[test]
fn a_database_closes() {
    let data = Database {
        actors: vec![
            Actor { id: 1, name: "Ditto".into(), title: "".into(), ..Default::default() },
            Actor { id: 2, ..Default::default() },
        ],
        enemies: vec![
            // The one that started all this: a default of 10, not of 0.
            Enemy { id: 1, name: "Slime".into(), max_hp: 10, ..Default::default() },
            Enemy { id: 2, name: "Boss".into(), max_hp: 9999, ..Default::default() },
        ],
        ..Default::default()
    };
    closes(&Document::Ldb { header: "LcfDataBase".into(), data });
}

/// The map tree is one of the six structures read by position instead of by
/// chunk id, so nothing in it is optional and a wrong count eats the rest of
/// the file.
#[test]
fn a_map_tree_closes() {
    let data = TreeMap {
        maps: vec![
            MapInfo { id: 0, name: "root".into(), ..Default::default() },
            MapInfo {
                id: 1,
                name: "a map".into(),
                parent_map: 0,
                r#type: TreeMapMapType::from_i32(1),
                ..Default::default()
            },
            MapInfo {
                id: 2,
                name: "an area".into(),
                parent_map: 1,
                r#type: TreeMapMapType::from_i32(2),
                ..Default::default()
            },
        ],
        tree_order: vec![0, 1, 2],
        active_node: 1,
        start: Start { party_map_id: 1, party_x: 4, party_y: 5, ..Default::default() },
        ..Default::default()
    };
    closes(&Document::Lmt { header: "LcfMapTree".into(), data });
}

/// An empty everything: the shortest file each format admits.
#[test]
fn the_empty_documents_close() {
    closes(&Document::Lmu { header: "LcfMapUnit".into(), data: Map::default() });
    closes(&Document::Ldb { header: "LcfDataBase".into(), data: Database::default() });
    closes(&Document::Lmt { header: "LcfMapTree".into(), data: TreeMap::default() });
}

/// A command list carries no count: it ends with four zero bytes, which is a
/// command of code 0. So code 0 is not a command one can have, and a JSON
/// edited by hand into holding one **loses everything after it** —silently,
/// because the file it produces is perfectly valid—. Pinned here because it is
/// the one way a hand-written JSON can lose data without anything failing.
#[test]
fn a_command_of_code_zero_ends_the_list() {
    let page = EventPage {
        id: 1,
        event_commands: vec![
            EventCommand { code: EventCommandCode::from_i32(10110), string: "kept".into(), ..Default::default() },
            EventCommand { code: EventCommandCode::from_i32(0), ..Default::default() },
            EventCommand { code: EventCommandCode::from_i32(10110), string: "lost".into(), ..Default::default() },
        ],
        ..Default::default()
    };
    let data = Map {
        events: vec![Event { id: 1, pages: vec![page], ..Default::default() }],
        ..Default::default()
    };
    let binary = ditto::file::write(&Document::Lmu { header: "LcfMapUnit".into(), data }).unwrap();
    let Document::Lmu { data, .. } = ditto::file::read(&binary).unwrap() else { unreachable!() };
    let commands = &data.events[0].pages[0].event_commands;
    assert_eq!(commands.len(), 1);
    assert_eq!(commands[0].string, "kept");
}
