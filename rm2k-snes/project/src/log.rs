//! What a conversion says while it runs, kept apart from what another one
//! running beside it says.
//!
//! The converter and the stages it calls report as they go —each map's
//! header, what a package lost to fit, an event left out—, and the
//! cartridges' builder keeps it in each cartridge's `converter.log`. While
//! the converter was a process of its own that was its stdout and stderr,
//! which the builder captured: one process per cartridge, so each log held
//! one cartridge's lines. Since the builder calls the converter as a
//! library, the cartridges convert in threads of one process, and a
//! `println!` would mix them on one stdout.
//!
//! **So they write through [`outln!`] and [`errln!`]**, which go to the
//! [`Log`] the thread is converting into, or to stdout and stderr when it
//! is converting into none —a stage called from its crate's tests, and
//! until 2026-11-27 a stage's own binary or the converter's—, as
//! `println!` and `eprintln!` did. Two buffers and not one, because the
//! process's log was its stdout first and its stderr after it, and
//! `converter.log` keeps those bytes.
//!
//! **Why the thread and not a parameter**: what prints is a hundred lines
//! in nine of the converter's files and a few in the stages it calls, each
//! behind a function signature that would have to carry the log for that
//! alone; and the stages are called through functions whose shape is their
//! request and their answer. A thread that starts work for the conversion
//! —its two thread scopes— carries the log over with [`current`] and
//! [`Log::during`].

use std::cell::RefCell;
use std::fmt;
use std::io::Write;
use std::sync::{Arc, Mutex, Once};

/// Where a conversion's lines go: what it says, and its warnings apart, as
/// a process's stdout and stderr.
#[derive(Clone, Default)]
pub struct Log {
    buffers: Arc<Mutex<Buffers>>,
}

#[derive(Default)]
struct Buffers {
    out: Vec<u8>,
    err: Vec<u8>,
}

thread_local! {
    static CURRENT: RefCell<Option<Log>> = const { RefCell::new(None) };
}

impl Log {
    pub fn new() -> Log {
        Log::default()
    }

    /// Runs `f` with this thread's lines going here, and puts back whatever
    /// the thread was writing into before, also if `f` panics.
    pub fn during<T>(&self, f: impl FnOnce() -> T) -> T {
        within(Some(self.clone()), f)
    }

    /// Everything said: the lines, and the warnings after them, as a
    /// process's log captured stdout first and stderr after.
    pub fn bytes(&self) -> Vec<u8> {
        let buffers = self.buffers.lock().unwrap_or_else(|e| e.into_inner());
        let mut out = buffers.out.clone();
        out.extend(&buffers.err);
        out
    }

    /// The lines alone, without the warnings.
    pub fn out(&self) -> Vec<u8> {
        let buffers = self.buffers.lock().unwrap_or_else(|e| e.into_inner());
        buffers.out.clone()
    }

    /// The warnings alone.
    pub fn err(&self) -> Vec<u8> {
        let buffers = self.buffers.lock().unwrap_or_else(|e| e.into_inner());
        buffers.err.clone()
    }

    fn write(&self, warning: bool, text: &[u8]) {
        let mut buffers = self.buffers.lock().unwrap_or_else(|e| e.into_inner());
        if warning {
            buffers.err.extend(text);
        } else {
            buffers.out.extend(text);
        }
    }
}

/// The log this thread is writing into, to hand to a thread it starts.
pub fn current() -> Option<Log> {
    CURRENT.with(|c| c.borrow().clone())
}

/// Runs `f` writing into `log` —into stdout and stderr if it is None—, and
/// puts back the one before.
pub fn within<T>(log: Option<Log>, f: impl FnOnce() -> T) -> T {
    struct Restore(Option<Log>);
    impl Drop for Restore {
        fn drop(&mut self) {
            let before = self.0.take();
            CURRENT.with(|c| *c.borrow_mut() = before);
        }
    }
    let before = CURRENT.with(|c| c.replace(log));
    let _restore = Restore(before);
    f()
}

/// A line, into the thread's log or onto stdout. What [`outln!`] calls.
pub fn out(args: fmt::Arguments) {
    say(false, args)
}

/// A warning, into the thread's log or onto stderr. What [`errln!`] calls.
pub fn err(args: fmt::Arguments) {
    say(true, args)
}

fn say(warning: bool, args: fmt::Arguments) {
    let written = CURRENT.with(|c| {
        c.borrow().as_ref().map(|log| {
            log.write(warning, fmt::format(args).as_bytes());
        })
    });
    if written.is_none() {
        if warning {
            let _ = std::io::stderr().write_fmt(args);
        } else {
            let _ = std::io::stdout().write_fmt(args);
        }
    }
}

/// A panic in a thread that writes into a log is said in that log, as a
/// converter process's panic was said on its stderr, which went into its
/// `converter.log`; on any other thread, as before. Installed once, by
/// whoever calls a conversion in its own process.
pub fn panics_into_logs() {
    static ONCE: Once = Once::new();
    ONCE.call_once(|| {
        let before = std::panic::take_hook();
        std::panic::set_hook(Box::new(move |info| match current() {
            Some(log) => {
                let name = std::thread::current()
                    .name()
                    .map_or("<unnamed>".to_string(), str::to_string);
                log.write(true, format!("thread '{name}' {info}\n").as_bytes());
            }
            None => before(info),
        }));
    });
}

/// `println!`, into the thread's [`Log`] if it has one.
#[macro_export]
macro_rules! outln {
    () => {
        $crate::log::out(format_args!("\n"))
    };
    ($($arg:tt)*) => {
        $crate::log::out(format_args!("{}\n", format_args!($($arg)*)))
    };
}

/// `eprintln!`, into the thread's [`Log`] if it has one.
#[macro_export]
macro_rules! errln {
    () => {
        $crate::log::err(format_args!("\n"))
    };
    ($($arg:tt)*) => {
        $crate::log::err(format_args!("{}\n", format_args!($($arg)*)))
    };
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn each_thread_writes_into_its_own_log_and_the_warnings_go_last() {
        let (a, b) = (Log::new(), Log::new());
        std::thread::scope(|scope| {
            scope.spawn(|| {
                a.during(|| {
                    crate::errln!("a warns");
                    crate::outln!("a says {}", 1);
                })
            });
            scope.spawn(|| b.during(|| crate::outln!("b says")));
        });
        assert_eq!(a.bytes(), b"a says 1\na warns\n");
        assert_eq!(b.bytes(), b"b says\n");
        assert!(current().is_none());
    }

    #[test]
    fn a_thread_carries_the_log_into_the_ones_it_starts() {
        let log = Log::new();
        log.during(|| {
            let here = current();
            std::thread::scope(|scope| {
                scope.spawn(|| within(here, || crate::outln!("from a worker")));
            });
            crate::outln!();
        });
        assert_eq!(log.bytes(), b"from a worker\n\n");
    }

    #[test]
    fn a_panic_is_said_in_the_log_and_the_one_before_comes_back() {
        panics_into_logs();
        let (outer, inner) = (Log::new(), Log::new());
        outer.during(|| {
            let caught = std::panic::catch_unwind(|| inner.during(|| panic!("no room")));
            assert!(caught.is_err());
            crate::outln!("still the outer one");
        });
        assert!(String::from_utf8(inner.err()).unwrap().contains("no room"));
        assert_eq!(outer.bytes(), b"still the outer one\n");
    }
}
