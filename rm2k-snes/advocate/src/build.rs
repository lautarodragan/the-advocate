//! `advocate build`: the game's cartridges, the ones its project file
//! declares in `[cartridges]`, and `build/advocate.json`.
//!
//! What each cartridge carries and when it is up to date is the cartridge
//! library's, `rm2k-snes-cartridge`; this reads the command line, builds,
//! leaves the file and says how much room each cartridge has left. A new
//! cartridge is one more table in `[cartridges]`, and nothing here.

use std::path::{Path, PathBuf};

use cartridge::cartridges::{Cartridges, FROM_ENVIRONMENT, RELEASE};
use clap::{Arg, ArgAction, ArgMatches, Command};
use rm2k_project::environment::{arguments, Environment};
use rm2k_project::Project;
use serde_json::Value;

pub fn command() -> Command {
    Command::new("build")
        .about("Builds the cartridges of advocate.toml that are not up to date, and leaves build/advocate.json")
        .arg(
            Arg::new("project")
                .long("project")
                .value_name("DIRECTORY")
                .help("the directory where advocate.toml is. Without this, it is looked up from the current directory upwards"),
        )
        .args(arguments(FROM_ENVIRONMENT))
        .arg(
            Arg::new("list")
                .long("list")
                .action(ArgAction::SetTrue)
                .help("which case goes in which cartridge, without building anything"),
        )
        .arg(
            Arg::new("into")
                .long("into")
                .value_name("DIR")
                .conflicts_with("list")
                .help("convert and assemble the one cartridge named into DIR, without a stamp, even if it is up to date, and without touching build/advocate.json; what follows `--` goes to the converter"),
        )
        .arg(
            Arg::new("force")
                .long("force")
                .action(ArgAction::SetTrue)
                .conflicts_with_all(["list", "into"])
                .help("build them even if they are up to date: the RTP and the SoundFont go into the fingerprint by their path and not their content, so after changing one in place this is how the cartridges see it"),
        )
        .arg(
            Arg::new("without_tracks")
                .long("without-tracks")
                .action(ArgAction::SetTrue)
                .help("do not make the MSU-1 tracks of release"),
        )
        .arg(
            Arg::new("write_patches")
                .long("write-patches")
                .action(ArgAction::SetTrue)
                .conflicts_with_all(["list", "into"])
                .help("write release's decisions over the versioned patches, patches/auto/, once it is built: every build compares them and says which are stale"),
        )
        .arg(
            Arg::new("names")
                .value_name("CARTRIDGE")
                .num_args(0..)
                .help("only these; without names, all of them"),
        )
        .arg(
            Arg::new("extra")
                .value_name("CONVERTER_FLAGS")
                .num_args(0..)
                .last(true)
                .requires("into")
                .help("with --into: more flags for the converter"),
        )
}

pub fn run(matches: &ArgMatches) -> Result<(), String> {
    let project = Project::locate(matches.get_one::<String>("project").map(Path::new))?;
    // What the machine gave, before a `.zip` is unpacked: the file says
    // both.
    let given = Environment::from_matches(matches, FROM_ENVIRONMENT);
    let cartridges = Cartridges::load(project, given.clone())?;
    let names: Vec<String> = matches
        .get_many::<String>("names")
        .map(|n| n.cloned().collect())
        .unwrap_or_default();
    for name in &names {
        if cartridges.get(name).is_none() {
            return Err(format!(
                "there is no cartridge '{name}': the ones there are {}",
                cartridges.names().join(", ")
            ));
        }
    }

    if matches.get_flag("list") {
        for name in cartridges.names() {
            let cases = cartridges.cases(&name)?;
            println!("{name} ({}): {}", cases.len(), cases.join(" "));
        }
        return Ok(());
    }

    if let Some(dest) = matches.get_one::<String>("into") {
        let [name] = names.as_slice() else {
            return Err("--into takes exactly one cartridge".into());
        };
        let dest = rm2k_project::absolute(dest);
        let file = cartridges
            .rom_of(name)?
            .file_name()
            .map(PathBuf::from)
            .unwrap();
        let extra: Vec<String> = matches
            .get_many::<String>("extra")
            .map(|e| e.cloned().collect())
            .unwrap_or_default();
        return cartridges.convert(name, &dest, &dest.join(file), &extra);
    }

    let inputs = cartridges.fingerprint()?;
    let names = if names.is_empty() {
        cartridges.names()
    } else {
        names
    };
    let force = matches.get_flag("force");
    let tracks = names.iter().any(|n| n == RELEASE) && !matches.get_flag("without_tracks");
    let built = cartridges.build_these(&names, &inputs, force, tracks);
    if built.is_ok() && matches.get_flag("write_patches") {
        crate::patches::write(&cartridges)?;
    }
    // The file, whatever the build answered: a cartridge that failed says
    // there why it is stale.
    let written = crate::file::write(&cartridges, &given)?;
    for name in &names {
        println!("{}", room(name, &written));
    }
    if let Some(stale) = written["patches"]["stale"]
        .as_array()
        .filter(|s| !s.is_empty())
    {
        println!(
            "{} versioned patch(es) do not match what the converter decides; \
             `advocate build --write-patches` writes {RELEASE}'s:",
            stale.len()
        );
        for complaint in stale {
            println!("  {}", complaint.as_str().unwrap_or_default());
        }
    }
    built
}

/// The cartridge's line at the end of a build: its free data banks and the
/// tightest of the banks that are not data —the whole of it, by name, is
/// in the file—. Or why it has none.
fn room(name: &str, written: &Value) -> String {
    let cartridge = written["listing"]["cartridges"]
        .as_array()
        .and_then(|all| all.iter().find(|c| c["name"] == name));
    let Some(cartridge) = cartridge else {
        return format!("{name}: not in the file");
    };
    if let Some(why) = cartridge["stale"].as_str() {
        return format!("{name}: {why}");
    }
    let space = &cartridge["space"];
    let n = |key: &str| space[key].as_i64().unwrap_or(0);
    let tightest = [
        ("bank 0", "bank0"),
        ("bank 1", "bank1"),
        ("bank $C0", "bank_far2"),
        ("bank $C1", "bank_far3"),
        ("bank $FF", "bank_far4"),
    ]
    .into_iter()
    .min_by_key(|(_, key)| n(key))
    .map(|(bank, key)| format!("{bank} with {} B left", n(key)))
    .unwrap();
    format!(
        "{name}: {} free data banks ({} fast) and {} halves; the tightest, {tightest}",
        n("free"),
        n("free_fast"),
        n("free_halves"),
    )
}

#[cfg(test)]
mod tests {
    use super::room;
    use serde_json::json;

    #[test]
    fn a_cartridge_says_its_free_banks_and_its_tightest_one() {
        let written = json!({"listing": {"cartridges": [
            {"name": "release", "stale": null, "space": {
                "free": 12, "free_fast": 3, "free_halves": 1,
                "bank0": 85, "bank1": 900, "bank_far2": 40, "bank_far3": 7000,
                "bank_far4": 300}},
            {"name": "test-special", "stale": "is not built", "space": null},
        ]}});
        assert_eq!(
            room("release", &written),
            "release: 12 free data banks (3 fast) and 1 halves; the tightest, bank $C0 with 40 B left"
        );
        assert_eq!(room("test-special", &written), "test-special: is not built");
        assert_eq!(room("other", &written), "other: not in the file");
    }
}
