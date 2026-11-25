//! What turns a converted game into cartridges, and says how much room they
//! have left.
//!
//! `advocate build` is the command over it:
//!
//! * building: which cartridges the project declares, whether each one is
//!   up to date, and building them ([`cartridges`]);
//! * the assembling: the bank packing ([`banks`]), `ca65` + `ld65`, the
//!   header checksum and the symbol table ([`assemble`]);
//! * the space: what is left in each bank and each RAM area ([`space`]).
//!
//! Until 2026-11-25 it had a binary of its own, `rm2k-snes-cartridges`,
//! with `assemble` and `space` subcommands.

pub mod assemble;
pub mod banks;
pub mod cartridges;
pub mod dbg;
pub mod msu;
pub mod space;
mod text;
