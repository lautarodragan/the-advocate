//! A cartridge's plan and its `.msu`, for the small game of
//! `cartridge.json` —six maps, one without pages, exit songs, separate
//! ones, a jump that never happens, a jump that carries what came in and
//! one that carries its song; with and without title, Game Over and
//! battle— and two backdrops and three packages' sound effects.
//!
//! **The path it guards**: those shapes, which a game may not have. What a
//! real cartridge's plan gives is heard and played in A Blurred Line's
//! suite —which song each map's package carries, what is playing when it
//! loads— and its `.msu` read back by the console in `test_msu_data.py`
//! and `test_msu_effects.py`.

use rm2k_snes_audio::cartridge::{self, Cartridge};
use rm2k_snes_audio::msu::{Effects, PackageEffects, Version};
use serde_json::Value;
use std::collections::{HashMap, HashSet};

const GAME: &str = include_str!("cartridge.json");

fn unhex(text: &str) -> Vec<u8> {
    (0..text.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&text[i..i + 2], 16).unwrap())
        .collect()
}

fn cartridge(name: &str) -> Cartridge {
    let game: Value = serde_json::from_str(GAME).unwrap();
    let c = &game["cartridge"][name];
    let strings = |v: &Value| -> Vec<String> {
        v.as_array()
            .unwrap()
            .iter()
            .map(|s| s.as_str().unwrap().to_string())
            .collect()
    };
    let text = |v: &Value| v.as_str().map(String::from);
    Cartridge {
        songs: serde_json::from_value(game["songs"].clone()).unwrap(),
        maps: c["maps"]
            .as_array()
            .unwrap()
            .iter()
            .map(|m| m.as_i64().unwrap())
            .collect(),
        map_music: strings(&c["map_music"]),
        // The fixture is older than them too: every map, and the title, as
        // written.
        map_levels: Vec::new(),
        title_level: Default::default(),
        start: c["start"].as_u64().unwrap() as usize,
        title: text(&c["title"]),
        game_over: text(&c["game_over"]),
        apart: c["apart"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| {
                (
                    p[0].as_i64().unwrap(),
                    strings(&p[1]).into_iter().collect::<HashSet<_>>(),
                )
            })
            .collect::<HashMap<_, _>>(),
        not_given: c["not_given"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| (p[0].as_i64().unwrap(), p[1].as_i64().unwrap()))
            .collect(),
        system_songs: strings(&c["system_songs"]),
        // The fixture is older than them: none, which is what keeps its job.
        named_songs: Vec::new(),
        measuring_headroom: c["measuring_headroom"].as_f64(),
        decompress_frames: c["decompress_frames"].as_f64().unwrap(),
        msu_samples: false,
    }
}

/// The job a plan writes is one `compile` reads back, for both games.
#[test]
fn the_job_is_one_compile_reads() {
    for name in ["full", "sparse"] {
        let plan = cartridge::plan(&cartridge(name)).unwrap();
        let (_, emit) = rm2k_snes_audio::job::parse(&plan.job, rm2k_snes_audio::bank::ARAM_END)
            .unwrap_or_else(|e| panic!("{name}: {e:?}"));
        assert!(emit.is_some(), "{name}: the plan says what to emit");
    }
}

/// A song a troop page starts goes apart in the battle's package: not with
/// the battle song, and separate, as a map's `apart_themes`. The Python
/// never did this —until 2026-09-30 a troop page's `PlayBGM` was not done—,
/// so it is checked against the plan's own answer.
#[test]
fn a_troop_song_goes_apart_in_the_battle_package() {
    let mut c = cartridge("full");
    let battle = c
        .songs
        .per_package
        .get_mut(&cartridge::Key::Battle)
        .unwrap();
    let radio = c.songs.names.len();
    c.songs.names.push("Radio".into());
    battle.songs.push(radio);
    c.songs.troop_songs = vec![radio];
    let plan = cartridge::plan(&c).unwrap();
    let packages = plan.job["packages"].as_array().unwrap();
    let pelea = packages.iter().position(|p| p["name"] == "pelea").unwrap();
    assert_eq!(packages[pelea]["separate"], serde_json::json!([radio]));
    assert!(!packages[pelea]["songs"]
        .as_array()
        .unwrap()
        .contains(&serde_json::json!(radio)));
    assert_eq!(plan.separate[pelea], [radio]);
}

/// A map that plays its own song at a level other than the song as written
/// puts every map's level in the job, the six bytes of `Level`, and the rest
/// as written; and a title's song at another level, its own. The Python never did this —until 2026-10-19 a map's own song
/// played as written—, so it is checked against the plan's own answer.
#[test]
fn a_maps_level_and_the_titles_go_into_the_job() {
    use rm2k_snes_bytecode::level::Level;
    let mut c = cartridge("full");
    assert!(cartridge::plan(&c).unwrap().job["emit"]
        .get("map_level")
        .is_none());
    c.map_levels = vec![Level::WHOLE, Level::new(0, 70, 100, 50)];
    let plan = cartridge::plan(&c).unwrap();
    let levels = plan.job["emit"]["map_level"].as_array().unwrap();
    assert_eq!(levels.len(), c.maps.len());
    assert_eq!(levels[1], serde_json::json!([63, 63, 0, 1, 0, 0]));
    assert_eq!(levels[2], serde_json::json!(Level::WHOLE.bytes()));
    assert!(plan.job["emit"].get("title_level").is_none());
    c.title_level = Level::new(0, 90, 130, 50);
    let plan = cartridge::plan(&c).unwrap();
    assert_eq!(
        plan.job["emit"]["title_level"],
        serde_json::json!([104, 104, 77, 1, 0, 0])
    );
}

#[test]
/// The `.msu` reads back as one of this game's —signed, versioned— with an
/// entry per backdrop's tiles and colours and per package's version, each
/// the bytes it was given.
fn the_msu_reads_back() {
    let game: Value = serde_json::from_str(GAME).unwrap();
    let m = &game["msu"];
    let backdrops: Vec<(Vec<u8>, Vec<u8>)> = m["backdrops"]
        .as_array()
        .unwrap()
        .iter()
        .map(|p| (unhex(p[0].as_str().unwrap()), unhex(p[1].as_str().unwrap())))
        .collect();
    let indices = |v: &Value| -> Vec<usize> {
        v.as_array()
            .unwrap()
            .iter()
            .map(|i| i.as_u64().unwrap() as usize)
            .collect()
    };
    let quality = Effects {
        versions: m["versions"]
            .as_array()
            .unwrap()
            .iter()
            .map(|v| Version {
                effect: String::new(),
                rate: 0,
                data: unhex(v.as_str().unwrap()),
            })
            .collect(),
        packages: m["packages"]
            .as_array()
            .unwrap()
            .iter()
            .map(|p| PackageEffects {
                name: p["name"].as_str().unwrap().into(),
                versions: indices(&p["versions"]),
                rows: indices(&p["rows"]),
                pitches: p["pitches"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .map(|q| (q[0].as_u64().unwrap() as usize, q[1].as_i64().unwrap()))
                    .collect(),
            })
            .collect(),
        rates: Vec::new(),
    };
    let msu = cartridge::msu(&backdrops, &quality, b"TEST").unwrap();
    let entries = rm2k_snes_audio::msu_data::index(&msu.blob, b"TEST").unwrap();
    // The backdrops' tiles and colours, then each package's versions in
    // order, each entry the bytes it was given.
    let mut sources: Vec<&[u8]> = backdrops
        .iter()
        .flat_map(|(t, c)| [t.as_slice(), c.as_slice()])
        .collect();
    for p in &quality.packages {
        sources.extend(
            p.versions
                .iter()
                .map(|&v| quality.versions[v].data.as_slice()),
        );
    }
    assert_eq!(entries.len(), sources.len());
    for (k, (&(at, length), data)) in entries.iter().zip(&sources).enumerate() {
        let (at, length) = (at as usize, length as usize);
        assert_eq!(&msu.blob[at..at + length], *data, "entry {k}");
    }
    assert_eq!((msu.backdrops, msu.effects), (2, 3));
}
