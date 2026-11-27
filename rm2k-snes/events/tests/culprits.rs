//! The culprits report, as the converter asks it for `culprits.json`: what
//! it says of a game, and how a request that is not there and a dump that
//! is not one tell apart. `scan` and `compile` are in `small_game.rs` and
//! `compile_stage.rs`. Until 2026-11-25 these looked at a `scan`
//! subcommand, and until 2026-11-27 at the binary's `culprits`, which went
//! with the binary: nothing ran it.

use rm2k_snes_events::{culprits, Bad, Game, Request};
use std::path::PathBuf;

fn here() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests")
}

#[test]
fn culprits_writes_its_report() {
    let request = Request::read(&here().join("scan.json")).unwrap();
    let game = Game::from_dump(&here().join("game"), request.patches.clone()).unwrap();
    let report = culprits::report(&culprits::judge_game(&game, &request, false).unwrap());
    assert!(
        report["totals"]["maps"]["pages"].as_u64().unwrap() > 0,
        "{report}"
    );
}

#[test]
fn a_request_that_is_not_there_is_a_wrong_call() {
    let done = Request::read(&here().join("nowhere.json"));
    assert!(matches!(done, Err(Bad::Usage(_))), "{:?}", done.err());
}

#[test]
fn a_dump_that_is_not_one_is_a_no() {
    let request = Request::read(&here().join("scan.json")).unwrap();
    let dir = std::env::temp_dir().join(format!("rm2k-snes-events-dump-{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let done = Game::from_dump(&dir, request.patches.clone());
    assert!(matches!(done, Err(Bad::Answer(_))), "{:?}", done.err());
    std::fs::remove_dir_all(&dir).unwrap();
}
