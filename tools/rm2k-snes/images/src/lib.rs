//! An rm2k-snes game's pictures brought to the console.
//!
//! Five kinds of picture, and the same road for all of them: the picture as
//! RM2k draws it —`rm2k-render`, as a library—, scaled to the console's
//! screen with Pillow's LANCZOS —[`resample`]—, toned where the console
//! tones, down to fifteen bits a colour and down to the colours its
//! palette holds —[`adeleine`]—, and out as indices into that palette:
//!
//! * [`fullscreen`]: a picture that fills the screen at 8 bits a pixel,
//!   as unique tiles, a palette and a tilemap —the title, the Game Over—;
//! * [`show_picture`]: the picture of a `ShowPicture`, where it lands and
//!   its fifteen colours;
//! * [`background`]: the picture of a `ShowPicture` too big for the
//!   sprites, as a 4bpp layer with a few palettes;
//! * [`scene`]: a battle's backdrop, in quality and in the light fallback,
//!   and its battlers;
//! * [`animation`]: a battle animation's frames in the box the console
//!   draws them in.
//!
//! **Which** pictures, and the bytes that carry them, are the caller's:
//! this takes files and sizes and gives back pixels. The sizes —the scene,
//! the box, how many colours and from which entry— come in each request,
//! because they are numbers of the cartridge that its caller also writes
//! down for the console, and they are written in one place.
//!
//! Every step copies, to the bit, what the converter did in Python until
//! 2026-09-30 —Pillow's resize and `alpha_composite` included—: the point
//! is that the cartridge comes out byte for byte the same.

pub mod animation;
pub mod background;
pub mod composite;
pub mod fail;
pub mod fullscreen;
pub mod pixels;
pub mod request;
pub mod scene;
pub mod show_picture;
pub mod tint;

pub use fail::{Bad, Result};
