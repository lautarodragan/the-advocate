//! A game or an RTP that comes as a `.zip`: unpacked once into the
//! project's cache, and a directory for everyone after `unpack`.

use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

use flate2::write::DeflateEncoder;
use rm2k_project::environment::Environment;
use rm2k_project::{archive, Project};

fn scratch(name: &str) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR"))
        .join("archive")
        .join(name);
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

/// A `.zip` with `entries` —name, content, deflated or stored—, written by
/// hand: the format is small, and the real games' are checked by the ROMs
/// coming out the same.
fn zip(path: &Path, entries: &[(&str, &[u8], bool)]) {
    let mut out = Vec::new();
    let mut central = Vec::new();
    for (name, content, deflate) in entries {
        let data = if *deflate {
            let mut e = DeflateEncoder::new(Vec::new(), flate2::Compression::default());
            e.write_all(content).unwrap();
            e.finish().unwrap()
        } else {
            content.to_vec()
        };
        let mut crc = flate2::Crc::new();
        crc.update(content);
        let method: u16 = if *deflate { 8 } else { 0 };
        let flags: u16 = if name.is_ascii() { 0 } else { 0x0800 };
        let offset = out.len() as u32;
        let mut common = Vec::new();
        common.extend(20u16.to_le_bytes());
        common.extend(flags.to_le_bytes());
        common.extend(method.to_le_bytes());
        common.extend([0u8; 4]);
        common.extend(crc.sum().to_le_bytes());
        common.extend((data.len() as u32).to_le_bytes());
        common.extend((content.len() as u32).to_le_bytes());
        common.extend((name.len() as u16).to_le_bytes());
        common.extend(0u16.to_le_bytes());
        out.extend(0x0403_4b50u32.to_le_bytes());
        out.extend(&common);
        out.extend(name.as_bytes());
        out.extend(&data);
        central.extend(0x0201_4b50u32.to_le_bytes());
        central.extend(20u16.to_le_bytes());
        central.extend(&common);
        central.extend([0u8; 10]);
        central.extend(offset.to_le_bytes());
        central.extend(name.as_bytes());
    }
    let start = out.len() as u32;
    out.extend(&central);
    out.extend(0x0605_4b50u32.to_le_bytes());
    out.extend([0u8; 4]);
    out.extend((entries.len() as u16).to_le_bytes());
    out.extend((entries.len() as u16).to_le_bytes());
    out.extend((central.len() as u32).to_le_bytes());
    out.extend(start.to_le_bytes());
    out.extend(0u16.to_le_bytes());
    fs::write(path, out).unwrap();
}

fn project(dir: &Path) -> Project {
    Project::from_text(dir, "[paths]\nbuild = \"build\"\n").unwrap()
}

#[test]
fn a_zip_game_is_a_directory_after_unpack() {
    let dir = scratch("game");
    let game = dir.join("Game.zip");
    zip(
        &game,
        &[
            ("RPG_RT.ldb", b"database", false),
            ("ChipSet/Town.png", b"tiles tiles tiles tiles", true),
            ("Music/Canción.mid", b"song", true),
        ],
    );
    let mut environment = Environment::default();
    environment.set("game_dir", &game);
    environment.set("rtp_dir", &dir);
    // Before unpacking, it is an error and not an empty game: a lookup
    // that finds nothing in the game falls back to the RTP silently.
    let error = environment.game().unwrap_err().to_string();
    assert!(error.contains("did not unpack it"), "{error}");
    environment.unpack(&project(&dir)).unwrap();
    let unpacked = environment.game().unwrap().to_path_buf();
    assert!(
        unpacked.starts_with(dir.join("build/cache/zip")),
        "{}",
        unpacked.display()
    );
    assert_eq!(
        fs::read(unpacked.join("ChipSet/Town.png")).unwrap(),
        b"tiles tiles tiles tiles"
    );
    assert_eq!(
        fs::read(unpacked.join("Music/Canción.mid")).unwrap(),
        b"song"
    );
    assert_eq!(fs::read(unpacked.join("RPG_RT.ldb")).unwrap(), b"database");
    // The tools it runs get the directory.
    let flags = environment.as_flags(&["game_dir"]);
    assert_eq!(flags[1], unpacked.as_os_str());
    let (zip_path, hash) = environment.archive("game_dir").unwrap();
    assert_eq!(zip_path, game);
    assert_eq!(hash, archive::content_hash(&game).unwrap());
    // A directory stays as it is.
    assert_eq!(environment.rtp().unwrap(), dir);
    assert!(environment.archive("rtp_dir").is_none());
    // Unpacked once: the second time finds it.
    fs::write(unpacked.join("marker"), "").unwrap();
    let mut again = Environment::default();
    again.set("game_dir", &game);
    again.unpack(&project(&dir)).unwrap();
    assert!(again.game().unwrap().join("marker").exists());
    // Another `.zip` with the same name is another copy.
    zip(&game, &[("RPG_RT.ldb", b"other", false)]);
    let mut other = Environment::default();
    other.set("game_dir", &game);
    other.unpack(&project(&dir)).unwrap();
    assert_ne!(other.game().unwrap(), unpacked);
    assert_eq!(
        fs::read(other.game().unwrap().join("RPG_RT.ldb")).unwrap(),
        b"other"
    );
}

#[test]
fn a_zip_that_writes_outside_is_refused() {
    let dir = scratch("outside");
    let game = dir.join("bad.zip");
    zip(&game, &[("../escaped", b"x", false)]);
    let mut environment = Environment::default();
    environment.set("game_dir", &game);
    let error = environment.unpack(&project(&dir)).unwrap_err().to_string();
    assert!(error.contains("goes out of the .zip"), "{error}");
    assert!(!dir.join("escaped").exists());
}
