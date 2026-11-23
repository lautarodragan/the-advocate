//! A usb2snes client for the FX Pak (sd2snes) over its USB serial port, from
//! the firmware's source, sd2snes v1.11.0: see [`protocol`] and [`client`].

pub mod client;
pub mod device;
pub mod port;
pub mod protocol;
pub mod sdpath;
