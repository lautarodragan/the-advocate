//! Finding the FX Pak's serial port.
//!
//! It enumerates as a CDC ACM device with USB vendor `1209` and product
//! `5a22`. On Linux the tty's `device` link in sysfs is the USB interface,
//! and its parent, the USB device, has `idVendor` and `idProduct`. The node
//! is looked up by those ids instead of taking the first `ttyACM*`, which
//! could be any modem or board.

use std::path::PathBuf;

pub const VENDOR: &str = "1209";
pub const PRODUCT: &str = "5a22";
/// Overrides the lookup, like `--device`.
pub const ENV: &str = "FXPAK_DEVICE";

pub fn find(explicit: Option<PathBuf>) -> Result<PathBuf, String> {
    if let Some(p) = explicit {
        return Ok(p);
    }
    if let Some(p) = std::env::var_os(ENV).filter(|v| !v.is_empty()) {
        return Ok(PathBuf::from(p));
    }
    find_in_sysfs()
}

#[cfg(target_os = "linux")]
fn find_in_sysfs() -> Result<PathBuf, String> {
    let mut found = Vec::new();
    if let Ok(dir) = std::fs::read_dir("/sys/class/tty") {
        for e in dir.flatten() {
            let name = e.file_name().to_string_lossy().into_owned();
            if !name.starts_with("ttyACM") {
                continue;
            }
            let usb = e.path().join("device/..");
            let id = |f: &str| {
                std::fs::read_to_string(usb.join(f))
                    .map(|s| s.trim().to_string())
                    .unwrap_or_default()
            };
            if id("idVendor") == VENDOR && id("idProduct") == PRODUCT {
                found.push(PathBuf::from("/dev").join(name));
            }
        }
    }
    found.sort();
    match found.len() {
        0 => Err(not_found()),
        1 => {
            let p = found.pop().unwrap();
            if p.exists() {
                Ok(p)
            } else {
                Err(format!(
                    "the FX Pak is on USB, as {}, but that node does not exist here: in a container, it was created before the device existed; recreate it",
                    p.display()
                ))
            }
        }
        _ => Err(format!(
            "more than one FX Pak on USB ({}): pick one with --device or {ENV}",
            found
                .iter()
                .map(|p| p.display().to_string())
                .collect::<Vec<_>>()
                .join(", ")
        )),
    }
}

#[cfg(not(target_os = "linux"))]
fn find_in_sysfs() -> Result<PathBuf, String> {
    Err(format!("finding the FX Pak by its USB ids only works on Linux: pass its serial port with --device or {ENV}"))
}

fn not_found() -> String {
    format!(
        "no FX Pak on USB (vendor {VENDOR}, product {PRODUCT}): the console is off, the cable is out, or —in a container— it was created before the device existed: recreate it. --device or {ENV} names the port by hand"
    )
}
