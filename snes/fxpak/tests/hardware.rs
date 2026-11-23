//! Against a real FX Pak, only when `FXPAK_DEVICE` names its port —like
//! Ditto's corpus in `DITTO_CORPUS`—; skipped otherwise.
//!
//! It boots nothing and resets nothing: someone may be playing. It reads
//! INFO, the memory, `/advocate`, and writes one small file under
//! `/advocate/fxpak-test/`, which it reads back. One test, so that its
//! steps do not race for the port.

use std::path::PathBuf;

use fxpak::client::Client;
use fxpak::protocol::Kind;
use fxpak::sdpath::SdPath;

#[test]
fn a_real_fx_pak_answers_and_keeps_a_file() {
    let Some(dev) = std::env::var_os("FXPAK_DEVICE").filter(|v| !v.is_empty()) else {
        eprintln!("skipped: FXPAK_DEVICE does not name an FX Pak's serial port");
        return;
    };
    let mut c = Client::open(&PathBuf::from(dev)).unwrap();
    let info = c.info().unwrap();
    eprintln!(
        "running {:?}, firmware {:?} on {:?}",
        info.rom, info.version, info.device
    );
    assert!(!info.version.is_empty());

    let mem = c.get_snes(0, 600).unwrap();
    assert_eq!(mem.len(), 600);
    assert_eq!(
        c.get_snes(0, 600).unwrap(),
        mem,
        "two reads of the ROM's copy differ"
    );

    let dir = SdPath::parse("/advocate/fxpak-test").unwrap();
    c.mkdir(&dir).unwrap();
    let file = dir.join("round-trip.bin").unwrap();
    let data: Vec<u8> = (0..1500u32)
        .map(|i| (i.wrapping_mul(2654435761) >> 13) as u8)
        .collect();
    c.put_file(&file, &data).unwrap();
    assert_eq!(c.get_file(&file).unwrap(), data);
    let entries = c.ls(&dir).unwrap();
    assert!(entries
        .iter()
        .any(|e| e.name == "round-trip.bin" && e.kind == Kind::File));
    assert_eq!(c.info().unwrap().rom, info.rom, "the running ROM changed");
}
