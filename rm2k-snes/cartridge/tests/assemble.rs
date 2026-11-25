//! What the assembling does besides calling `ca65` + `ld65`: which
//! sources a ROM is made of, which files are the generated ones, and
//! refusing when one is shadowed. The checksum and the symbols are tested
//! next to their code.

use std::fs;
use std::path::{Path, PathBuf};

use cartridge::assemble::{assemble, generated, object_key, sources, write_bytecodes, Failure};

fn scratch(name: &str) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR"))
        .join("assemble")
        .join(name);
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

#[test]
fn sources_are_the_included_s_files_not_the_generated_ones() {
    let dir = scratch("sources");
    fs::write(
        dir.join("main.s"),
        ".include \"event_opcodes.inc\"\n.include \"shop.s\"\n\
         ; .include \"quoted.s\" in a comment does not count\n",
    )
    .unwrap();
    fs::write(dir.join("shop.s"), ".include \"prices.s\"\n").unwrap();
    fs::write(dir.join("prices.s"), "").unwrap();
    let main = dir.join("main.s");
    assert_eq!(
        sources(&main).unwrap(),
        [main.clone(), dir.join("shop.s"), dir.join("prices.s")]
    );
}

#[test]
fn the_generated_files_are_the_ones_found_in_the_include_directory() {
    let dir = scratch("generated");
    let runtime = dir.join("runtime");
    let build = dir.join("build");
    fs::create_dir_all(&runtime).unwrap();
    fs::create_dir_all(&build).unwrap();
    // In the order the assembler reads them, from any `.s` of the tree.
    fs::write(
        runtime.join("main.s"),
        ".include \"opcodes.inc\"\n.include \"music.inc\"\n.include \"rest.s\"\n",
    )
    .unwrap();
    fs::write(runtime.join("rest.s"), ".include \"maps.inc\"\n").unwrap();
    fs::write(runtime.join("opcodes.inc"), "").unwrap();
    fs::write(build.join("music.inc"), "").unwrap();
    fs::write(build.join("maps.inc"), "").unwrap();
    assert_eq!(
        generated(&runtime.join("main.s"), &build).unwrap(),
        [build.join("music.inc"), build.join("maps.inc")]
    );
}

#[test]
fn refuses_a_generated_file_next_to_the_source() {
    // `ca65` would read it before the build's, without a warning. And it
    // refuses before touching anything: nothing is packed or linked.
    let dir = scratch("shadowed");
    let build = dir.join("build");
    fs::create_dir_all(&build).unwrap();
    fs::write(dir.join("main.s"), ".include \"mapdata.inc\"\n").unwrap();
    fs::write(dir.join("mapdata.inc"), "stale").unwrap();
    fs::write(build.join("mapdata.inc"), ".segment \"RODATA\"\n").unwrap();
    let result = assemble(
        &dir.join("main.s"),
        &build,
        &build.join("x.sfc"),
        None,
        &dir,
        None,
    );
    match result {
        Err(Failure::Message(message)) => {
            assert!(message.contains("mapdata.inc"), "{message}");
            assert!(message.contains("another build's data"), "{message}");
        }
        other => panic!("it had to refuse, and gave {other:?}"),
    }
    assert!(!build.join("memory.cfg").exists());
    assert_eq!(
        fs::read_to_string(build.join("mapdata.inc")).unwrap(),
        ".segment \"RODATA\"\n"
    );
}

#[test]
fn the_bytecodes_are_generated_files_too() {
    // Written into the include directory, they are found there like the
    // converter's files; and a stale copy next to the source, where they
    // lived until 2026-10-02, is refused like any other.
    let dir = scratch("bytecodes");
    let build = dir.join("build");
    fs::create_dir_all(&build).unwrap();
    fs::write(
        dir.join("main.s"),
        ".include \"event_opcodes.inc\"\n.include \"music_opcodes.inc\"\n",
    )
    .unwrap();
    write_bytecodes(&build).unwrap();
    assert_eq!(
        generated(&dir.join("main.s"), &build).unwrap(),
        [
            build.join("event_opcodes.inc"),
            build.join("music_opcodes.inc")
        ]
    );
    let events = fs::read_to_string(build.join("event_opcodes.inc")).unwrap();
    assert!(events.contains("\nOP_DONE          = $00\n"), "{events}");
    assert!(events.contains(".macro EVENT_HANDLERS"), "{events}");

    fs::write(dir.join("music_opcodes.inc"), "stale").unwrap();
    let message = generated(&dir.join("main.s"), &build).unwrap_err();
    assert!(message.contains("music_opcodes.inc"), "{message}");
}

/// Two worktrees assemble the same runtime and the same data from different
/// places: `ca65`'s object is the same, so its key has to be too. And a
/// change in anything `ca65` reads —a source, a generated file, the
/// binary— is another key.
#[test]
fn the_object_key_is_what_ca65_reads_not_where() {
    let dir = scratch("object_key");
    let ca65 = dir.join("ca65");
    fs::write(&ca65, "an assembler").unwrap();
    let mut keys = Vec::new();
    for (side, data, code) in [
        ("one", "maps", "lda #0"),
        ("two", "maps", "lda #0"),
        ("three", "other maps", "lda #0"),
        ("four", "maps", "lda #1"),
    ] {
        let runtime = dir.join(side).join("runtime");
        let build = dir.join(side).join("build").join(side);
        fs::create_dir_all(&runtime).unwrap();
        fs::create_dir_all(&build).unwrap();
        fs::write(
            runtime.join("main.s"),
            ".include \"mapdata.inc\"\n.include \"rest.s\"\n",
        )
        .unwrap();
        fs::write(runtime.join("rest.s"), code).unwrap();
        fs::write(build.join("mapdata.inc"), data).unwrap();
        keys.push(object_key(&ca65, &runtime.join("main.s"), &build).unwrap());
    }
    assert_eq!(keys[0], keys[1]);
    assert_ne!(keys[0], keys[2]);
    assert_ne!(keys[0], keys[3]);
    fs::write(&ca65, "another assembler").unwrap();
    let runtime = dir.join("one").join("runtime");
    let build = dir.join("one").join("build").join("one");
    assert_ne!(
        keys[0],
        object_key(&ca65, &runtime.join("main.s"), &build).unwrap()
    );
}

/// An object from the cache names, in its debug info, the files of the
/// build that assembled it first: the generated ones by their absolute path
/// in that build's directory, and every one with that build's dates. `ld65`
/// passes that on to the `.dbg`, where a debugger looks for the sources. So
/// the `.dbg` of a build served from the cache has to be the one `ca65`
/// itself would have given in this build.
#[test]
fn a_cached_object_gives_the_dbg_a_fresh_one_gives() {
    use cartridge::assemble::which;
    if which("ca65").is_none() || which("ld65").is_none() {
        eprintln!("skipped: ca65 and ld65 are not on the PATH");
        return;
    }
    let dir = scratch("cached_dbg");
    let cache = dir.join("cache");
    let mut dbgs = Vec::new();
    // Two worktrees, each with its tools' checkout and its game's build,
    // the first one with older files: other paths, other dates. The second
    // assembles twice, from the cache and without it.
    for (side, cached) in [("one", true), ("two", true), ("two", false)] {
        let root = dir.join(side).join("tools");
        let runtime = root.join("runtime");
        let build = dir.join(side).join("game").join("build");
        if !runtime.exists() {
            fs::create_dir_all(&runtime).unwrap();
            fs::create_dir_all(&build).unwrap();
            fs::write(
                runtime.join("main.s"),
                ".p816\n.include \"mapdata.inc\"\n.include \"rest.s\"\n",
            )
            .unwrap();
            // The header carries the checksum's placeholders, which the build
            // checks.
            fs::write(
                runtime.join("rest.s"),
                ".segment \"CODE\"\n  rts\n\
                 .segment \"HEADER\"\n  .res 28\n  .word $FFFF\n  .word $0000\n",
            )
            .unwrap();
            fs::write(build.join("mapdata.inc"), ".segment \"CODE\"\n  nop\n").unwrap();
            if side == "one" {
                let old = std::time::UNIX_EPOCH + std::time::Duration::from_secs(1_700_000_000);
                for file in [
                    runtime.join("main.s"),
                    runtime.join("rest.s"),
                    build.join("mapdata.inc"),
                ] {
                    let file = fs::File::options().write(true).open(file).unwrap();
                    file.set_modified(old).unwrap();
                }
            }
        }
        let hit = assemble(
            &runtime.join("main.s"),
            &build,
            &build.join("game.sfc"),
            None,
            &root,
            cached.then_some(cache.as_path()),
        )
        .unwrap();
        assert_eq!(hit, side == "two" && cached, "{side}");
        dbgs.push(fs::read_to_string(build.join("game.sfc.dbg")).unwrap());
    }
    let files = |dbg: &str| -> Vec<String> {
        dbg.lines()
            .filter(|l| l.starts_with("file\t"))
            .map(String::from)
            .collect()
    };
    assert!(
        files(&dbgs[2])
            .iter()
            .any(|l| l.contains("name=\"runtime/rest.s\"")),
        "the test is not looking at the runtime: {}",
        dbgs[2]
    );
    assert_eq!(files(&dbgs[1]), files(&dbgs[2]));
    assert_eq!(dbgs[1], dbgs[2]);
}
