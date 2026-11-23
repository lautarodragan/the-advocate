//! What turns a converted game into cartridges, and says how much room they
//! have left.
//!
//! One executable, `rm2k-snes-cartridges`, and its subcommands share this
//! library:
//!
//! * building: which cartridges the project declares, whether each one is
//!   up to date, and building them ([`cartridges`]);
//! * `assemble`: the bank packing ([`banks`]), `ca65` + `ld65`, the header
//!   checksum and the symbol table ([`assemble`]);
//! * `space`: what is left in each bank and each RAM area ([`space`]).

pub mod assemble;
pub mod banks;
pub mod cartridges;
pub mod dbg;
pub mod msu;
pub mod space;
mod text;
