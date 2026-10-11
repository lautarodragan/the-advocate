//! Where everything is, for the tools of an `rm2k-snes` suite.
//!
//! Four questions, and one module each:
//!
//! * **Which game is being built**: [`Project`]. The tools do not know where
//!   any game lives; they find it the way cargo finds its `Cargo.toml`, by
//!   looking for `rm2k-snes.toml` from the current directory upwards, or they
//!   are told with `--project`.
//! * **What the game decided**: the settings in that file, read through
//!   [`Project`]. A missing key is an error that names the key, never a
//!   default: a default in a tool would be some other game's value.
//! * **Where the machine keeps things**: [`environment`]. The original game,
//!   the RTP, the SoundFont… arrive by flags, and have no default either.
//! * **What a cached value depends on**: [`cache`], the key of the disk
//!   cache.
//!
//! And [`suite`]: where the suite's own files are —the runtime—, which
//! travel with the tools and not with any game.
//!
//! And [`resolved`]: all of the above about one project, as JSON, for
//! whoever asks from outside the tools.

pub mod archive;
pub mod cache;
pub mod environment;
mod paths;
mod project;
mod resolved;
pub mod suite;

pub use paths::{absolute, relative};
pub use project::{Error, Project, FILENAME};
pub use resolved::resolved;
