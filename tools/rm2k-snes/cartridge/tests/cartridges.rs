//! What `rm2k-snes-cartridges` reads from a project, on a small game built
//! inside the test: which maps and cases each cartridge carries, in which
//! order, where it goes, and when it is stale.

use std::fs;
use std::path::{Path, PathBuf};

use cartridge::assemble::sources;
use cartridge::cartridges::{variables_stamp, Cartridges};
use rm2k_project::environment::Environment;
use rm2k_project::Project;

/// The file of a small game, with `{cartridges}` where the cartridges go.
const SETTINGS: &str = r#"
[paths]
data = "data"
patches = "patches"
build = "build"
cases = "cases"

[rom]
name = "game"

[maps]
below = 8
excluded = [3]
added = [20]
test = [30]

[debug]
debug_map = true
enemy_hp = true

[cases]
real_game = "nothing"
debug_map_entry = "to-debug"

{cartridges}
"#;

const RELEASE: &str = r#"
[cartridges.release]
start_map = 4
party = [10]
maps = "game"
test_graphics = [["Hero", "0"]]
flags = []
cases = "all"
excluded_cases = ["only-small"]
"#;

const SMALL: &str = r#"
[cartridges.test-small]
start_map = 6
party = []
maps = [6, 1]
test_graphics = []
flags = ["--no-title"]
cases = ["both", "only-small"]
"#;

/// A game on disk: the tree, the debug map, the cases.
fn game(name: &str, cartridges: &str) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR")).join("cartridges").join(name);
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(dir.join("data")).unwrap();
    fs::create_dir_all(dir.join("patches/manual/nuevos")).unwrap();
    fs::create_dir_all(dir.join("cases")).unwrap();
    fs::write(
        dir.join("rm2k-snes.toml"),
        SETTINGS.replace("{cartridges}", cartridges),
    )
    .unwrap();
    // Type 1 is a map; 5 is an area, which the rule leaves out on its own.
    let nodes: Vec<String> = [(0, 0), (1, 1), (2, 1), (3, 1), (4, 1), (5, 2), (6, 1), (7, 1), (20, 1), (30, 1)]
        .iter()
        .map(|(id, kind)| format!("{{\"id\": {id}, \"type\": {kind}}}"))
        .collect();
    // What makes `data/` a Ditto dump, and which view it is.
    fs::write(dir.join("data/ditto.json"), r#"{"ditto": 2, "view": "resolved"}"#).unwrap();
    fs::write(
        dir.join("data/maps.json"),
        format!("{{\"maps\": [{}]}}", nodes.join(", ")),
    )
    .unwrap();
    fs::write(
        dir.join("patches/manual/nuevos/Map0900.json"),
        r#"{"id": 900, "arbol": {"id": 900, "type": 1}}"#,
    )
    .unwrap();
    for (case, text) in [
        ("nothing", r#"{"event_commands": []}"#),
        ("to-debug", r#"{"event_commands": [{"code": "Teleport"}]}"#),
        ("both", r#"{"event_commands": [{"code": "Teleport"}, {"code": "Wait"}]}"#),
        ("only-small", r#"{"event_commands": [{"code": "Wait"}]}"#),
    ] {
        fs::write(dir.join("cases").join(format!("{case}.json")), text).unwrap();
    }
    dir
}

fn load(dir: &Path) -> Result<Cartridges, String> {
    Cartridges::load(Project::open(dir).map_err(String::from)?, Environment::default())
}

#[test]
fn the_maps_are_the_rule_the_added_ones_the_debug_map_and_the_test_ones() {
    let c = load(&game("maps", &(RELEASE.to_string() + SMALL))).unwrap();
    // Below 8, real maps, not excluded; then the added ones and the debug map.
    assert_eq!(c.game_maps, [1, 2, 4, 6, 7, 20, 900]);
    assert_eq!(c.all_maps(), [1, 2, 4, 6, 7, 20, 900, 30]);
    assert_eq!(c.rule_maps(&[], &[]), [1, 2, 3, 4, 6, 7]);
}

#[test]
fn the_flags_come_out_in_the_usual_order() {
    let c = load(&game("flags", &(RELEASE.to_string() + SMALL))).unwrap();
    let release = c.get("release").unwrap();
    assert_eq!(
        release.flags,
        [
            "--party", "10", "--map-id", "4", "--maps", "1", "2", "6", "7", "20", "900", "30",
            "--test-graphic", "Hero", "0", "--enemy-hp"
        ]
    );
    let small = c.get("test-small").unwrap();
    assert_eq!(
        small.flags,
        ["--map-id", "6", "--maps", "1", "--no-title", "--enemy-hp"]
    );
    assert!(c.without_title("test-small").unwrap());
    assert!(!c.without_title("release").unwrap());
}

#[test]
fn release_carries_every_case_with_its_first_page_first() {
    let c = load(&game("cases", &(RELEASE.to_string() + SMALL))).unwrap();
    assert_eq!(c.cases("release").unwrap(), ["to-debug", "both", "nothing"]);
    // The clean delivery: without the debug map, not its entry either.
    assert_eq!(c.cases_of("release", false).unwrap(), ["nothing", "both"]);
    let (cases, teleports) = c.manifest("release").unwrap();
    assert_eq!(cases.len(), teleports.len());
    assert_eq!(teleports, [true, true, false]);
}

#[test]
fn where_a_case_runs_does_not_depend_on_the_order_of_the_file() {
    // With the small one first, a case in both ran in the small one and
    // moved its golden without anyone touching the case.
    let first = load(&game("order_a", &(RELEASE.to_string() + SMALL))).unwrap();
    let second = load(&game("order_b", &(SMALL.to_string() + RELEASE))).unwrap();
    assert_eq!(second.names(), ["test-small", "release"]);
    for case in first.all_cases().unwrap() {
        assert_eq!(first.where_is(&case).unwrap(), second.where_is(&case).unwrap());
    }
    assert_eq!(first.where_is("both").unwrap(), ["release", "test-small"]);
    assert_eq!(first.where_is("only-small").unwrap(), ["test-small"]);
}

#[test]
fn each_one_has_its_directory_and_its_rom() {
    let dir = game("where", &(RELEASE.to_string() + SMALL));
    let c = load(&dir).unwrap();
    assert_eq!(c.rom_of("release").unwrap(), dir.join("build/release/game.sfc"));
    assert_eq!(c.msu_of("release").unwrap(), dir.join("build/release/game.msu"));
    assert_eq!(c.rom_of("test-small").unwrap(), dir.join("build/tests/small/prueba.sfc"));
    let mut moved = Environment::default();
    moved.set("test_cartridges", "/elsewhere");
    let c = Cartridges::load(Project::open(&dir).unwrap(), moved).unwrap();
    assert_eq!(c.directory("test-small").unwrap(), PathBuf::from("/elsewhere/small"));
    assert_eq!(c.directory("release").unwrap(), dir.join("build/release"));
}

#[test]
fn a_game_without_release_is_refused() {
    let error = load(&game("no_release", SMALL)).err().unwrap();
    assert!(error.contains("missing [cartridges.release]"), "{error}");
}

#[test]
fn a_missing_setting_names_its_key() {
    let broken = SMALL.replace("party = []\n", "");
    let error = load(&game("no_party", &(RELEASE.to_string() + &broken))).err().unwrap();
    assert!(error.ends_with("missing key cartridges.test-small.party"), "{error}");
    let broken = SMALL.replace("maps = [6, 1]", "maps = \"all\"");
    let error = load(&game("bad_maps", &(RELEASE.to_string() + &broken))).err().unwrap();
    assert!(error.contains("maps of test-small is a list or \"game\""), "{error}");
}

#[test]
fn the_stamp_says_when_a_cartridge_is_stale() {
    let dir = game("stale", &(RELEASE.to_string() + SMALL));
    let c = load(&dir).unwrap();
    let inputs = "0123456789abcdef";
    assert_eq!(c.stale("test-small", inputs).unwrap(), Some("is not built"));
    assert_eq!(c.stale("nope", inputs).unwrap(), Some("does not exist"));
    let build = c.directory("test-small").unwrap();
    fs::create_dir_all(&build).unwrap();
    fs::write(build.join("sello.txt"), c.stamp("test-small", inputs).unwrap()).unwrap();
    assert_eq!(c.stale("test-small", inputs).unwrap(), Some("does not have its .msu"));
    fs::write(c.msu_of("test-small").unwrap(), "").unwrap();
    assert_eq!(c.stale("test-small", inputs).unwrap(), None);
    // Other sources, or a case that changed.
    let other = "fedcba9876543210";
    assert!(c.stale("test-small", other).unwrap().is_some());
    fs::write(dir.join("cases/both.json"), r#"{"event_commands": []}"#).unwrap();
    assert!(c.stale("test-small", inputs).unwrap().is_some());
}

#[test]
fn the_converter_variables_are_in_the_stamp() {
    // Through `lookup` and not the process's environment, which the tests
    // running in parallel share.
    let unset = variables_stamp(|_| None);
    let dither = variables_stamp(|name| (name == "TRANSLUCENT_MODE").then(|| "dither".to_string()));
    let empty = variables_stamp(|name| (name == "TRANSLUCENT_MODE").then(String::new));
    assert_ne!(unset, dither);
    assert_ne!(unset, empty);
    assert_ne!(dither, empty);
    let pattern = variables_stamp(|name| (name == "DITHER_PATTERN").then(|| "checker".to_string()));
    assert_ne!(unset, pattern);
}

#[test]
fn everything_that_builds_the_rom_is_in_the_fingerprint() {
    // If not, editing an included file leaves the cartridge "up to date"
    // and the tests run against an old ROM without a warning. On a runtime
    // built by hand, which does not depend on what the real one has.
    let dir = game("fingerprint", &(RELEASE.to_string() + SMALL));
    let runtime = dir.join("runtime");
    fs::create_dir_all(runtime.join("deep")).unwrap();
    fs::write(runtime.join("main.s"), ".include \"shop.s\"\n.include \"deep/x.s\"\n").unwrap();
    fs::write(runtime.join("shop.s"), "").unwrap();
    fs::write(runtime.join("deep/x.s"), "").unwrap();
    // The tools the fingerprint hashes, as stand-ins on a PATH of their own.
    let bin = dir.join("bin");
    fs::create_dir_all(&bin).unwrap();
    for tool in [
        "ca65",
        "ld65",
        "lz2",
        "rm2k-snes-audio",
        "rm2k-snes-battle",
        "rm2k-snes-events",
        "rm2k-snes-images",
        "rm2k-snes-maps",
        "rm2k-snes-patches",
        "rm2k-snes-screens",
        "rm2k-snes-assemble",
    ] {
        let path = bin.join(tool);
        fs::write(&path, tool).unwrap();
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(&path, fs::Permissions::from_mode(0o755)).unwrap();
    }
    // Only this test reads the PATH, through the fingerprint.
    std::env::set_var("PATH", &bin);
    let c = load(&dir).unwrap();
    let files = c.fingerprint_files(&runtime).unwrap();
    for source in sources(&runtime.join("main.s")).unwrap() {
        assert!(files.contains(&source), "{} is not in the fingerprint", source.display());
    }
    assert!(files.contains(&bin.join("rm2k-snes-assemble")));
    assert!(files.contains(&bin.join("rm2k-snes-audio")));
    assert!(files.contains(&bin.join("rm2k-snes-battle")));
    assert!(files.contains(&bin.join("rm2k-snes-events")));
    assert!(files.contains(&bin.join("rm2k-snes-images")));
    assert!(files.contains(&bin.join("rm2k-snes-patches")));
    assert!(files.contains(&bin.join("rm2k-snes-screens")));
    assert!(files.contains(&dir.join("rm2k-snes.toml")));
    assert!(files.contains(&dir.join("patches/manual/nuevos/Map0900.json")));
    // The real runtime too: the fingerprint of the cartridges reads it.
    let fingerprint = c.fingerprint().unwrap();
    assert_eq!(fingerprint.len(), 16);
    assert_eq!(fingerprint, c.fingerprint().unwrap());
}
