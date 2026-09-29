//! Ditto as a library: a dump read back **with the schema's types**, from
//! either view.
//!
//! What it has to hold is that the two views are one document: the exact dump
//! and the resolved view of the same game read into the same values. A
//! consumer that reads the resolved view —every field written, enums as
//! numbers— then gets liblcf's names and types, and not a model of its own.
//!
//! The game is written here, so none of this needs a corpus. It carries what
//! makes the two views differ: fields at their default and away from it, an
//! enum by name, and an enum value `enums.csv` does not name.

use ditto::dump::{read_map, unpack, Dump, View};
use ditto::file::Document;
use ditto::schema::*;
use std::path::{Path, PathBuf};

struct Temp(PathBuf);

impl Temp {
    fn new(what: &str) -> Temp {
        let n = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let d = std::env::temp_dir().join(format!("ditto-{what}-{}-{n}", std::process::id()));
        std::fs::create_dir_all(&d).unwrap();
        Temp(d)
    }
}

impl Drop for Temp {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

fn database() -> Database {
    Database {
        actors: vec![
            Actor { id: 1, name: "Ditto".into(), initial_level: 5, ..Default::default() },
            Actor { id: 2, ..Default::default() },
        ],
        animations: vec![Animation {
            id: 1,
            position: AnimationPosition::Down,
            ..Default::default()
        }],
        chipsets: vec![Chipset {
            id: 1,
            chipset_name: "Tiles".into(),
            passable_data_lower: vec![15; 162],
            ..Default::default()
        }],
        ..Default::default()
    }
}

fn tree() -> TreeMap {
    TreeMap {
        maps: vec![
            MapInfo { id: 0, r#type: TreeMapMapType::Root, ..Default::default() },
            MapInfo { id: 1, r#type: TreeMapMapType::Map, encounter_steps: 0, ..Default::default() },
            MapInfo {
                id: 2,
                parent_map: 1,
                r#type: TreeMapMapType::Area,
                encounters: vec![Encounter { id: 1, troop_id: 7, ..Default::default() }],
                area_rect: Rect { l: 1, t: 1, r: 2, b: 2, ..Default::default() },
                ..Default::default()
            },
        ],
        tree_order: vec![0, 1, 2],
        ..Default::default()
    }
}

fn map() -> Map {
    let page = EventPage {
        id: 1,
        trigger: EventPageTrigger::Parallel,
        // A value `enums.csv` does not name: the exact dump writes it as
        // `{"Other": 9}` and the resolved view as `9`.
        layer: EventPageLayers::Other(9),
        event_commands: vec![EventCommand {
            code: EventCommandCode::from_i32(10110),
            string: "hello".into(),
            parameters: vec![1, 2],
            ..Default::default()
        }],
        ..Default::default()
    };
    Map {
        chipset_id: 1,
        width: 3,
        height: 2,
        lower_layer: vec![5000, 5001, 5002, 5003, 5004, 5005],
        upper_layer: vec![10000; 6],
        events: vec![Event { id: 1, x: 2, y: 1, pages: vec![page], ..Default::default() }],
        ..Default::default()
    }
}

/// The game above, as binaries, unpacked into its two views.
fn both_views(tmp: &Temp) -> (PathBuf, PathBuf) {
    let game = tmp.0.join("game");
    std::fs::create_dir_all(&game).unwrap();
    let write = |name: &str, doc: Document| {
        std::fs::write(game.join(name), ditto::file::write(&doc).unwrap()).unwrap();
    };
    write("RPG_RT.ldb", Document::Ldb { header: "LcfDataBase".into(), data: database() });
    write("RPG_RT.lmt", Document::Lmt { header: "LcfMapTree".into(), data: tree() });
    write("Map0001.lmu", Document::Lmu { header: "LcfMapUnit".into(), data: map() });
    let (exact, resolved) = (tmp.0.join("exact"), tmp.0.join("resolved"));
    unpack(&game, &exact, &resolved).unwrap();
    (exact, resolved)
}

#[test]
fn both_views_read_into_the_same_values() {
    let tmp = Temp::new("library-views");
    let (exact, resolved) = both_views(&tmp);
    for (dir, view) in [(&exact, View::Exact), (&resolved, View::Resolved)] {
        let dump = Dump::open(dir).unwrap();
        assert_eq!(dump.view(), view);
        assert_eq!(dump.database().unwrap(), database(), "{view:?}: the database");
        assert_eq!(dump.tree().unwrap(), tree(), "{view:?}: the tree");
        assert_eq!(dump.map(1).unwrap(), map(), "{view:?}: the map");
    }
}

/// A section on its own is the same as the database's, and reads nothing
/// else: the file of another section can be broken and it does not notice.
#[test]
fn a_section_reads_on_its_own() {
    let tmp = Temp::new("library-section");
    let (_, resolved) = both_views(&tmp);
    std::fs::write(resolved.join("db").join("animations.json"), "not json").unwrap();
    let dump = Dump::open(&resolved).unwrap();
    let actors: Vec<Actor> = dump.section("actors").unwrap();
    assert_eq!(actors, database().actors);
    assert!(dump.database().is_err(), "the broken section should break the whole");
}

/// A map in the dump's shape that is not in a dump —one a project changed,
/// kept somewhere else— reads the same way, `.tiles` included.
#[test]
fn a_map_reads_from_its_path() {
    let tmp = Temp::new("library-map");
    let (_, resolved) = both_views(&tmp);
    let elsewhere = tmp.0.join("elsewhere");
    std::fs::create_dir_all(&elsewhere).unwrap();
    for f in ["Map0001.json", "Map0001.tiles"] {
        std::fs::copy(resolved.join("maps").join(f), elsewhere.join(f)).unwrap();
    }
    assert_eq!(read_map(&elsewhere.join("Map0001.json")).unwrap(), map());
}

/// An enum reads from each of the three shapes the JSON can hold it in, and
/// a name the table does not have is still an error that says so.
#[test]
fn an_enum_reads_by_name_by_number_and_as_other() {
    let read = |s: &str| serde_json::from_str::<EventPageTrigger>(s);
    assert_eq!(read("\"parallel\"").unwrap(), EventPageTrigger::Parallel);
    assert_eq!(read("4").unwrap(), EventPageTrigger::Parallel);
    assert_eq!(read("{\"Other\": 9}").unwrap(), EventPageTrigger::Other(9));
    assert_eq!(read("9").unwrap(), EventPageTrigger::Other(9));
    let e = read("\"sideways\"").unwrap_err().to_string();
    assert!(e.contains("sideways") && e.contains("parallel"), "{e}");
}

/// A dump of another layout version is refused instead of read wrong.
#[test]
fn another_version_is_refused() {
    let tmp = Temp::new("library-version");
    let (_, resolved) = both_views(&tmp);
    let manifest = resolved.join("ditto.json");
    let text = std::fs::read_to_string(&manifest).unwrap();
    std::fs::write(&manifest, text.replace("\"ditto\": 2", "\"ditto\": 1")).unwrap();
    let e = Dump::open(Path::new(&resolved)).err().expect("version 1 should be refused");
    assert!(e.0.contains("version 1"), "{}", e.0);
}
