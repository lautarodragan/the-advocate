//! What the data of an RPG Maker 2000 game means.
//!
//! Ditto reads the format: a ChipSet is a list of passability bytes, a page
//! is a condition and a graphic. This says what the engine does with them:
//! where one can walk, which tile goes in front of the hero, which page of an
//! event is showing and what it draws, how much experience a level takes,
//! which troops a step on a map can meet. They are the original engine's
//! rules, so they hold for any RM2k game and for any program that runs one;
//! nothing here knows what that program is.
//!
//! **None of the numbers are ours.** They are easyrpg-player's and liblcf's,
//! and each function says which of theirs it is.
//!
//! It reads Ditto's types —`ditto::schema`— and nothing else: whatever a
//! caller changed on top of a game reaches this as those same types.

pub mod actor;
pub mod animation;
pub mod battle_animation;
pub mod charset;
pub mod chipset;
pub mod event;
pub mod faceset;
pub mod passability;
pub mod picture;
pub mod system;
pub mod tree;
