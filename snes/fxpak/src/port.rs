//! The FX Pak's USB serial port: a CDC ACM tty, put in raw mode, read and
//! written with a timeout on every wait.

use std::ffi::CString;
use std::io;
use std::os::fd::{AsRawFd, FromRawFd, OwnedFd};
use std::path::Path;
use std::time::{Duration, Instant};

pub struct Port {
    fd: OwnedFd,
}

#[derive(Debug)]
pub enum PortError {
    Io(io::Error),
    /// Nothing came for the whole timeout: `got` of `wanted` bytes arrived.
    Timeout {
        got: usize,
        wanted: usize,
    },
    /// Another `fxpak` holds the port.
    Busy,
}

impl std::fmt::Display for PortError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            PortError::Io(e) => write!(f, "{e}"),
            PortError::Timeout { got, wanted } => {
                write!(f, "timed out with {got} of {wanted} bytes")
            }
            PortError::Busy => write!(
                f,
                "another fxpak is using the port; two clients would interleave their blocks"
            ),
        }
    }
}

impl From<io::Error> for PortError {
    fn from(e: io::Error) -> Self {
        PortError::Io(e)
    }
}

fn check(r: libc::c_int) -> io::Result<libc::c_int> {
    if r < 0 {
        Err(io::Error::last_os_error())
    } else {
        Ok(r)
    }
}

impl Port {
    /// Opens the tty in raw mode and takes an exclusive `flock` on it, which
    /// keeps a second `fxpak` out (a client that does not flock is not kept
    /// out). HUPCL stays on, so closing the port drops DTR: the firmware
    /// takes that as a disconnect and goes back to idle from a transfer it
    /// was waiting on (`usbinterface.c` 409-417, `cdcuser.c` 264-266).
    pub fn open(path: &Path) -> Result<Port, PortError> {
        let c = CString::new(path.as_os_str().as_encoded_bytes())
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidInput, e))?;
        // SAFETY: a valid NUL-ended path; the fd is owned from here on.
        let fd = unsafe {
            OwnedFd::from_raw_fd(check(libc::open(
                c.as_ptr(),
                libc::O_RDWR | libc::O_NOCTTY | libc::O_CLOEXEC,
            ))?)
        };
        // SAFETY: plain calls on an fd we own, with structs they fill.
        unsafe {
            if libc::flock(fd.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) < 0 {
                let e = io::Error::last_os_error();
                return Err(if e.raw_os_error() == Some(libc::EWOULDBLOCK) {
                    PortError::Busy
                } else {
                    e.into()
                });
            }
            let mut t: libc::termios = std::mem::zeroed();
            check(libc::tcgetattr(fd.as_raw_fd(), &mut t))?;
            libc::cfmakeraw(&mut t);
            t.c_cflag |= libc::CLOCAL | libc::CREAD | libc::HUPCL;
            t.c_cc[libc::VMIN] = 1;
            t.c_cc[libc::VTIME] = 0;
            check(libc::tcsetattr(fd.as_raw_fd(), libc::TCSANOW, &t))?;
        }
        Ok(Port { fd })
    }

    fn poll(&self, events: libc::c_short, timeout: Duration) -> io::Result<bool> {
        let mut p = libc::pollfd {
            fd: self.fd.as_raw_fd(),
            events,
            revents: 0,
        };
        let ms = timeout.as_millis().min(i32::MAX as u128) as libc::c_int;
        loop {
            // SAFETY: one pollfd, valid for the call.
            let r = unsafe { libc::poll(&mut p, 1, ms) };
            if r < 0 {
                let e = io::Error::last_os_error();
                if e.kind() == io::ErrorKind::Interrupted {
                    continue;
                }
                return Err(e);
            }
            if r > 0 && p.revents & (libc::POLLERR | libc::POLLNVAL) != 0 {
                return Err(io::Error::other(
                    "the port went away (unplugged, or the console was turned off)",
                ));
            }
            return Ok(r > 0);
        }
    }

    pub fn write_all(&self, mut data: &[u8], timeout: Duration) -> Result<(), PortError> {
        let wanted = data.len();
        while !data.is_empty() {
            if !self.poll(libc::POLLOUT, timeout)? {
                return Err(PortError::Timeout {
                    got: wanted - data.len(),
                    wanted,
                });
            }
            // SAFETY: writing from a live slice.
            let n = unsafe { libc::write(self.fd.as_raw_fd(), data.as_ptr().cast(), data.len()) };
            if n < 0 {
                let e = io::Error::last_os_error();
                if e.kind() == io::ErrorKind::Interrupted || e.kind() == io::ErrorKind::WouldBlock {
                    continue;
                }
                return Err(e.into());
            }
            data = &data[n as usize..];
        }
        Ok(())
    }

    /// Reads exactly `buf.len()` bytes. `idle` bounds each wait for the next
    /// byte, not the whole read, so a long transfer that keeps moving is not
    /// cut, and one that stops is.
    pub fn read_exact(&self, buf: &mut [u8], idle: Duration) -> Result<(), PortError> {
        let mut got = 0;
        while got < buf.len() {
            if !self.poll(libc::POLLIN, idle)? {
                return Err(PortError::Timeout {
                    got,
                    wanted: buf.len(),
                });
            }
            // SAFETY: reading into the free part of a live buffer.
            let n = unsafe {
                libc::read(
                    self.fd.as_raw_fd(),
                    buf[got..].as_mut_ptr().cast(),
                    buf.len() - got,
                )
            };
            if n < 0 {
                let e = io::Error::last_os_error();
                if e.kind() == io::ErrorKind::Interrupted || e.kind() == io::ErrorKind::WouldBlock {
                    continue;
                }
                return Err(e.into());
            }
            if n == 0 {
                return Err(io::Error::other(
                    "the port closed (unplugged, or the console was turned off)",
                )
                .into());
            }
            got += n as usize;
        }
        Ok(())
    }

    /// Reads and drops whatever arrives until `quiet` passes with nothing,
    /// for at most `limit`; how many bytes it dropped. What is left over
    /// from a transfer someone did not finish reading would otherwise be
    /// taken as the next answer.
    pub fn drain(&self, quiet: Duration, limit: Duration) -> Result<usize, PortError> {
        let end = Instant::now() + limit;
        let mut dropped = 0;
        let mut buf = [0u8; 4096];
        while Instant::now() < end {
            if !self.poll(libc::POLLIN, quiet)? {
                break;
            }
            // SAFETY: reading into a live buffer.
            let n = unsafe { libc::read(self.fd.as_raw_fd(), buf.as_mut_ptr().cast(), buf.len()) };
            if n <= 0 {
                break;
            }
            dropped += n as usize;
        }
        Ok(dropped)
    }
}
