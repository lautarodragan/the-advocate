use std::path::PathBuf;
use std::process::ExitCode;

use clap::{Parser, Subcommand};
use fxpak::client::{Client, Error, POKE_END};
use fxpak::device;
use fxpak::protocol::Kind;
use fxpak::sdpath::SdPath;

/// Talks usb2snes to an FX Pak over its USB serial port.
///
/// Writes on the SD card go only under /advocate/. Addresses are hex with
/// `$` or `0x`, decimal otherwise.
#[derive(Parser)]
#[command(version)]
struct Cli {
    /// The serial port; otherwise $FXPAK_DEVICE, otherwise the one with USB
    /// ids 1209:5a22.
    #[arg(long, global = true)]
    device: Option<PathBuf>,
    #[command(subcommand)]
    command: Command,
}

#[derive(Subcommand)]
enum Command {
    /// The ROM running, the firmware and the device's name.
    Info,
    /// Reads the FX Pak's memory: the ROM's copy from $000000, the save RAM
    /// at $E00000, the WRAM copy at $F50000.
    Peek {
        #[arg(value_parser = parse_u32)]
        addr: u32,
        #[arg(value_parser = parse_u32, default_value = "16")]
        len: u32,
        /// Writes the bytes to a file instead of a hex dump.
        #[arg(long)]
        out: Option<PathBuf>,
    },
    /// Copies a file from the card.
    Get { sd: String, local: PathBuf },
    /// Copies a file to the card, under /advocate/, and reads it back.
    Put {
        local: PathBuf,
        sd: String,
        /// Skips reading it back.
        #[arg(long)]
        no_verify: bool,
    },
    /// Creates a directory under /advocate/, and the ones missing above it.
    Mkdir { sd: String },
    /// Lists a directory of the card.
    Ls { sd: String },
    /// Loads a ROM from the card and runs it, cutting what was running.
    Boot { sd: String },
    /// Resets the running game, like a short press of the reset button.
    Reset,
    /// Goes back to the FX Pak's menu, like a long press of the reset button.
    Menu,
    /// Writes into the ROM's copy in PSRAM, below $C00000.
    ///
    /// It changes the running game's code or data under it, until the ROM
    /// is loaded again; nothing goes to the card. The menu, the save RAM
    /// (which the FX Pak writes back to the card) and the menu's mailboxes
    /// are above $C00000 and refused.
    Poke {
        #[arg(value_parser = parse_u32)]
        addr: u32,
        /// The bytes, in hex: `a9 00 8d` or `a9008d`.
        bytes: String,
        /// Required: says that writing the FX Pak's memory is meant.
        #[arg(long)]
        write_memory: bool,
    },
}

fn parse_u32(s: &str) -> Result<u32, String> {
    let r = if let Some(h) = s.strip_prefix('$').or_else(|| s.strip_prefix("0x")) {
        u32::from_str_radix(h, 16)
    } else {
        s.parse()
    };
    r.map_err(|e| format!("{s:?}: {e}"))
}

fn parse_hex(s: &str) -> Result<Vec<u8>, String> {
    let digits: String = s.chars().filter(|c| !c.is_whitespace()).collect();
    if !digits.len().is_multiple_of(2) {
        return Err("an odd number of hex digits".into());
    }
    (0..digits.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&digits[i..i + 2], 16).map_err(|e| e.to_string()))
        .collect()
}

fn hexdump(addr: u32, data: &[u8]) {
    for (i, row) in data.chunks(16).enumerate() {
        let hex: Vec<String> = row.iter().map(|b| format!("{b:02x}")).collect();
        let ascii: String = row
            .iter()
            .map(|&b| {
                if (0x20..0x7f).contains(&b) {
                    b as char
                } else {
                    '.'
                }
            })
            .collect();
        println!(
            "{:06x}  {:<47}  {ascii}",
            addr as usize + i * 16,
            hex.join(" ")
        );
    }
}

fn sd(s: &str) -> Result<SdPath, Error> {
    SdPath::parse(s).map_err(Error::Refused)
}

fn run(cli: Cli) -> Result<(), Error> {
    // Refusals that need no device come before looking for it.
    match &cli.command {
        Command::Poke {
            write_memory: false,
            ..
        } => {
            return Err(Error::Refused(
                "poke writes the FX Pak's memory: say so with --write-memory".into(),
            ));
        }
        Command::Put { sd: s, .. } | Command::Mkdir { sd: s } => {
            sd(s)?.writable().map_err(Error::Refused)?
        }
        _ => {}
    }
    let path = device::find(cli.device).map_err(Error::Refused)?;
    let mut c = Client::open(&path)?;
    match cli.command {
        Command::Info => {
            let i = c.info()?;
            println!("rom:      {}", i.rom);
            println!("firmware: {} ({:#010x})", i.version, i.fw_version);
            println!("device:   {}", i.device);
            println!("features: {:#04x}", i.features);
        }
        Command::Peek { addr, len, out } => {
            let data = c.get_snes(addr, len)?;
            match out {
                Some(f) => std::fs::write(&f, &data)
                    .map_err(|e| Error::Refused(format!("{}: {e}", f.display())))?,
                None => hexdump(addr, &data),
            }
        }
        Command::Get { sd: s, local } => {
            let data = c.get_file(&sd(&s)?)?;
            std::fs::write(&local, &data)
                .map_err(|e| Error::Refused(format!("{}: {e}", local.display())))?;
            println!("{s}: {} bytes to {}", data.len(), local.display());
        }
        Command::Put {
            local,
            sd: s,
            no_verify,
        } => {
            let p = sd(&s)?;
            let data = std::fs::read(&local)
                .map_err(|e| Error::Refused(format!("{}: {e}", local.display())))?;
            c.put_file(&p, &data)?;
            if no_verify {
                println!("{p}: {} bytes sent, not read back", data.len());
            } else {
                let back = c.get_file(&p)?;
                if back != data {
                    let at = back
                        .iter()
                        .zip(&data)
                        .position(|(a, b)| a != b)
                        .unwrap_or(back.len().min(data.len()));
                    return Err(Error::Failed(format!(
                        "{p}: read back {} bytes, sent {}, first different at byte {at}",
                        back.len(),
                        data.len()
                    )));
                }
                println!("{p}: {} bytes sent and read back the same", data.len());
            }
        }
        Command::Mkdir { sd: s } => {
            let p = sd(&s)?;
            c.mkdir(&p)?;
            println!("{p}: a directory");
        }
        Command::Ls { sd: s } => {
            for e in c.ls(&sd(&s)?)? {
                if e.name == "." || e.name == ".." {
                    continue;
                }
                match e.kind {
                    Kind::Dir => println!("{}/", e.name),
                    Kind::File => println!("{}", e.name),
                }
            }
        }
        Command::Boot { sd: s } => {
            let p = sd(&s)?;
            println!("was running: {}", c.info()?.rom);
            c.boot(&p)?;
            println!("running:     {}", c.info()?.rom);
        }
        Command::Reset | Command::Menu => {
            let to_menu = matches!(cli.command, Command::Menu);
            println!("was running: {}", c.info()?.rom);
            c.reset(to_menu)?;
        }
        Command::Poke { addr, bytes, .. } => {
            let data = parse_hex(&bytes).map_err(Error::Refused)?;
            if addr as u64 + data.len() as u64 > POKE_END {
                return Err(Error::Refused(format!(
                    "poke writes only below ${POKE_END:06X}"
                )));
            }
            println!("running: {}", c.info()?.rom);
            c.poke(addr, &data)?;
            println!("${addr:06x}: {} bytes written", data.len());
        }
    }
    Ok(())
}

fn main() -> ExitCode {
    match run(Cli::parse()) {
        Ok(()) => ExitCode::SUCCESS,
        Err(e) => {
            eprintln!("fxpak: {e}");
            ExitCode::FAILURE
        }
    }
}
