//! What `ditto schema` publishes, checked against the schema itself.
//!
//! The JSON Ditto writes omits every field holding its default and stores
//! enums by name, so it cannot be read without knowing the defaults and the
//! tables. `ditto schema` hands both out, and these tests are there so that
//! what it hands out is the same thing the codec actually uses.
//!
//! The one that carries the weight is `every_declared_default_is_the_real
//! _one`: it builds a document **out of the description** and asks the real
//! `Deserialize`/`Serialize` of every struct whether every field came out
//! holding its default. Since a field at its default is left out when writing,
//! the answer has to be an empty object. A wrong default there would mean the
//! dump omits a field that a reader then fills in with something else, which
//! is the class of bug that started this whole project: an enemy with 1 HP
//! where the format says 10.
//!
//! None of this needs a corpus.

use ditto::schema::description::{ENUMS, STRUCTS};
use ditto::schema::*;

/// Every struct of the schema, named so that a type can be asked about it.
/// `structs_are_all_covered` is what keeps this list from going stale.
macro_rules! for_every_struct {
    ($check:ident) => {
        $check!(
            Actor,
            Animation,
            AnimationCellData,
            AnimationFrame,
            AnimationTiming,
            Attribute,
            BattleCommand,
            BattleCommands,
            BattlerAnimation,
            BattlerAnimationItemSkill,
            BattlerAnimationPose,
            BattlerAnimationWeapon,
            Chipset,
            Class,
            CommonEvent,
            Database,
            Encounter,
            Enemy,
            EnemyAction,
            Equipment,
            Event,
            EventCommand,
            EventPage,
            EventPageCondition,
            Item,
            Learning,
            Map,
            MapInfo,
            MoveCommand,
            MoveRoute,
            Music,
            Parameters,
            Rect,
            Save,
            SaveActor,
            SaveCommonEvent,
            SaveEventExecFrame,
            SaveEventExecState,
            SaveInventory,
            SaveMapEvent,
            SaveMapEventBase,
            SaveMapInfo,
            SavePanorama,
            SavePartyLocation,
            SavePicture,
            SaveScreen,
            SaveSystem,
            SaveTarget,
            SaveTitle,
            SaveVehicleLocation,
            Skill,
            Sound,
            Start,
            State,
            Switch,
            System,
            Terms,
            Terrain,
            TestBattler,
            TreeMap,
            Troop,
            TroopMember,
            TroopPage,
            TroopPageCondition,
            Variable
        )
    };
}

fn described(name: &str) -> &'static [ditto::schema::description::FieldDesc] {
    STRUCTS
        .iter()
        .find(|(n, _)| *n == name)
        .unwrap_or_else(|| panic!("the description does not name {name}"))
        .1
}

/// The document the description says is all-defaults, for one struct.
///
/// The fields whose default is "the default of the type" —a list, a nested
/// struct— are left out: absent is exactly what they mean.
fn all_defaults(name: &str) -> String {
    let mut parts = Vec::new();
    for f in described(name) {
        let Some(default) = f.default else { continue };
        let value = match f.enumeration {
            // An enum travels by name, so the description's number has to go
            // back through the table it publishes next to it.
            Some(e) => {
                let number: i64 = default.parse().unwrap();
                let table = ENUMS
                    .iter()
                    .find(|(n, _)| *n == e)
                    .unwrap_or_else(|| panic!("{name}.{}: no table for {e}", f.name))
                    .1;
                match table.iter().find(|(_, v)| *v as i64 == number) {
                    Some((variant, _)) => format!("\"{variant}\""),
                    // A value the table does not name travels as a number, so
                    // that the round trip does not depend on liblcf knowing
                    // every one of them. `EventCommand.code` defaults to 0,
                    // which is the command that ends a list and has no name.
                    None => format!("{{\"Other\": {number}}}"),
                }
            }
            None => default.to_string(),
        };
        parts.push(format!("\"{}\": {}", f.name, value));
    }
    format!("{{{}}}", parts.join(", "))
}

fn check_one<T>(name: &str)
where
    T: serde::Serialize + serde::de::DeserializeOwned + Default + PartialEq + std::fmt::Debug,
{
    let document = all_defaults(name);
    let parsed: T = serde_json::from_str(&document)
        .unwrap_or_else(|e| panic!("{name}: the described defaults do not parse: {e}"));
    assert_eq!(
        parsed,
        T::default(),
        "{name}: the description's defaults are not the ones the codec uses"
    );
    // And the other way round: what the codec calls a default is what gets
    // left out of the dump, which is the property the readers depend on.
    assert_eq!(
        serde_json::to_string(&parsed).unwrap(),
        "{}",
        "{name}: a field holding its default was still written out"
    );
}

#[test]
fn every_declared_default_is_the_real_one() {
    macro_rules! check {
        ($($t:ident),*) => { $( check_one::<$t>(stringify!($t)); )* };
    }
    for_every_struct!(check);
}

#[test]
fn structs_are_all_covered() {
    macro_rules! names {
        ($($t:ident),*) => { vec![$(stringify!($t)),*] };
    }
    let listed: Vec<&str> = for_every_struct!(names);
    let described: Vec<&str> = STRUCTS.iter().map(|(n, _)| *n).collect();
    assert_eq!(
        listed, described,
        "the description and the list in this file do not hold the same structs"
    );
}

/// The names the enums travel under are the ones `serde` reads and writes.
/// Published wrong, a reader would turn `"auto_start"` into the wrong number
/// and nothing would complain: the dump is still valid JSON.
#[test]
fn every_enum_name_is_the_one_serde_uses() {
    for (name, variants) in ENUMS {
        assert!(!variants.is_empty(), "{name} has no values");
        let mut seen = std::collections::BTreeSet::new();
        for (variant, _) in *variants {
            assert!(seen.insert(*variant), "{name} names {variant} twice");
        }
    }
    // Spot-checked against the real codec: these three are the ones the port
    // reads on every map, and a rename would be silent.
    let page: EventPage = serde_json::from_str(r#"{"trigger": "auto_start"}"#).unwrap();
    assert_eq!(page.trigger.to_i32(), value("EventPageTrigger", "auto_start"));
    let page: EventPage = serde_json::from_str(r#"{"layer": "same"}"#).unwrap();
    assert_eq!(page.layer.to_i32(), value("EventPageLayers", "same"));
    let command: EventCommand = serde_json::from_str(r#"{"code": "ShowMessage"}"#).unwrap();
    assert_eq!(
        command.code.to_i32(),
        value("EventCommandCode", "ShowMessage")
    );
}

fn value(enumeration: &str, variant: &str) -> i32 {
    ENUMS
        .iter()
        .find(|(n, _)| *n == enumeration)
        .unwrap()
        .1
        .iter()
        .find(|(v, _)| *v == variant)
        .unwrap()
        .1
}

/// The chunk and the `PersistIfDefault` flag are the other half of what the
/// description carries, and neither shows up in the JSON. These are the four
/// that a reader of the dump leans on hardest, pinned by hand: the shop reads
/// the terms by chunk number, and the three `persist` ones are what a reader
/// of the binary always saw and a reader of the JSON has to fill in.
#[test]
fn the_chunks_and_the_persist_flags_are_pinned() {
    let actor = described("Actor");
    let field = |n: &str| actor.iter().find(|f| f.name == n).unwrap();
    assert_eq!(field("id").chunk, None);
    assert_eq!(field("final_level").chunk, Some(0x08));
    assert_eq!(field("final_level").persist, false);
    assert_eq!(field("skills").persist, true);
    assert_eq!(field("skills").nested, Some("Learning"));
    assert_eq!(field("parameters").nested, Some("Parameters"));
}

/// What the subcommand writes is JSON, and it says the same thing the tables
/// say. It is parsed with `serde_json` rather than compared as text, because
/// what matters is what a reader gets.
#[test]
fn the_published_json_says_what_the_tables_say() {
    let document: serde_json::Value = serde_json::from_str(&ditto::describe::to_json())
        .expect("`ditto schema` did not write valid JSON");
    let fields = document["fields"].as_object().unwrap();
    assert_eq!(fields.len(), STRUCTS.len());
    for (name, described) in STRUCTS {
        let published = fields[*name].as_object().unwrap();
        assert_eq!(published.len(), described.len(), "{name}");
        for f in *described {
            let entry = &published[f.name];
            assert_eq!(
                entry["chunk"],
                match f.chunk {
                    Some(c) => serde_json::json!(c),
                    None => serde_json::Value::Null,
                },
                "{name}.{}",
                f.name
            );
            assert_eq!(entry["persist"], serde_json::json!(f.persist));
            assert_eq!(entry["only_2003"], serde_json::json!(f.only_2003));
        }
    }
    let enums = document["enums"].as_object().unwrap();
    assert_eq!(enums.len(), ENUMS.len());
    for (name, variants) in ENUMS {
        let published = enums[*name].as_object().unwrap();
        for (variant, v) in *variants {
            assert_eq!(published[*variant], serde_json::json!(v), "{name}.{variant}");
        }
    }
}

/// The five defaults the old scraper got wrong, pinned so that whatever
/// replaces this path has to get them right too. `kPanXDefault` is `9 * 256`
/// in the CSV, and reading only its first number gives 9.
#[test]
fn a_default_written_as_an_expression_is_the_whole_expression() {
    let location = described("SavePartyLocation");
    let field = |n: &str| location.iter().find(|f| f.name == n).unwrap();
    assert_eq!(field("pan_current_x").default, Some("2304"));
    assert_eq!(field("pan_current_y").default, Some("1792"));
    assert_eq!(field("pan_finish_x").default, Some("2304"));
    assert_eq!(field("pan_finish_y").default, Some("1792"));
    assert_eq!(field("pan_speed").default, Some("16"));
}
