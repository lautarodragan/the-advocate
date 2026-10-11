//! What turns a converted game into cartridges, and says how much room they
//! have left.
//!
//! Three executables share this library:
//!
//! * `rm2k-snes-assemble`: the bank packing ([`banks`]), `ca65` + `ld65`,
//!   the header checksum and the symbol table ([`assemble`]);
//! * `rm2k-snes-space`: what is left in each bank and each RAM area
//!   ([`space`]);
//! * `rm2k-snes-cartridges`: which cartridges the project declares, whether
//!   each one is up to date, and building them ([`cartridges`]).

pub mod assemble;
pub mod banks;
pub mod cartridges;
pub mod dbg;
pub mod msu;
pub mod space;
mod text;
