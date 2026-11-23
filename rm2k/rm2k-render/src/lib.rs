//! An RPG Maker 2000 game's graphics, drawn the way RM2k draws them.
//!
//! **A map's tile layers**: a map is two layers of tile ids and a ChipSet;
//! this expands the ChipSet into every tile it can draw —the autotiles
//! combined with their neighbours— and draws the map as RM2k stacks it: what
//! goes behind the hero, what goes in front, and the other drawings of the
//! ChipSet's animation, the water's and the animated tiles'.
//!
//! **What an event is drawn with** ([`charset`]): a CharSet, an event drawn
//! with a tile of the ChipSet, and a translucent one over what is behind it,
//! all as CharSet sheets.
//!
//! **What the screens are drawn with** ([`face`], [`system`],
//! [`show_picture`]): an actor's face, a window and its cursor from the
//! System, and the picture of a `ShowPicture`; and the 52 icons of RPG_RT's
//! ExFont, which a `$` and a letter draw in a text ([`exfont`]).
//!
//! **What a battle is drawn with**: a battle animation's cells, placed as
//! RM2k places them ([`battle_animation`]), and a battle's backdrop and its
//! enemies' pictures ([`battle`]).
//!
//! No panorama and no placing of events on the map: those are drawn by
//! whoever uses the layers. Nothing here knows which game the map is from.

pub mod battle;
pub mod battle_animation;
pub mod charset;
pub mod chipset;
pub mod exfont;
pub mod face;
pub mod fail;
pub mod layers;
pub mod picture;
pub mod show_picture;
pub mod source;
pub mod system;

pub use chipset::Atlas;
pub use fail::{Bad, Result};
pub use layers::{Family, Layers, Map};
pub use picture::Picture;
