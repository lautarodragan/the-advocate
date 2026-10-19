//! A libretro core, driven only for its audio: load a ROM, run frames,
//! keep what it plays.
//!
//! It is the least a frontend can be and still get the same samples as a
//! full one: the environment calls a core needs answered, the callbacks it
//! calls every frame, and nothing else —no picture is kept, no button is
//! pressed—. What it answers is exactly what the suite's Python harness
//! answers, because the ceilings measured here and the ones its tests
//! measure have to be the same numbers:
//!
//!   * **the order of the calls**: the environment callback before
//!     `retro_init`, the rest after, which is RetroArch's order;
//!   * **each option's first value**, the default by libretro convention,
//!     for every option the core declares: answering "no such variable"
//!     leaves the core with values nobody chose;
//!   * **the system directory is the ROM's own**, a directory with nothing
//!     else in it, so the core cannot find MSU-1 tracks next to it.
//!
//! **One console per process.** A core is a shared library with its state
//! in globals, so two consoles in the same process would be the same one.
//! Whoever wants several at once runs several processes.

use crate::fail::{Bad, Result};
use std::collections::HashMap;
use std::ffi::{c_char, c_int, c_uint, c_void, CStr, CString};
use std::path::Path;
use std::sync::Mutex;

// The environment commands that are answered; the rest are answered no,
// which is legal: the core has to make do with its default values.
const ENV_GET_OVERSCAN: c_uint = 2;
const ENV_GET_CAN_DUPE: c_uint = 3;
const ENV_GET_SYSTEM_DIRECTORY: c_uint = 9;
const ENV_SET_PIXEL_FORMAT: c_uint = 10;
const ENV_GET_VARIABLE: c_uint = 15;
const ENV_SET_VARIABLES: c_uint = 16;
const ENV_GET_SAVE_DIRECTORY: c_uint = 31;

#[repr(C)]
struct SystemInfo {
    library_name: *const c_char,
    library_version: *const c_char,
    valid_extensions: *const c_char,
    need_fullpath: bool,
    block_extract: bool,
}

#[repr(C)]
struct Variable {
    key: *const c_char,
    value: *const c_char,
}

#[repr(C)]
struct GameInfo {
    path: *const c_char,
    data: *const c_void,
    size: usize,
    meta: *const c_char,
}

#[repr(C)]
#[derive(Default)]
struct AvInfo {
    base_width: c_uint,
    base_height: c_uint,
    max_width: c_uint,
    max_height: c_uint,
    aspect_ratio: f32,
    fps: f64,
    sample_rate: f64,
}

/// What the callbacks write into. It is global because libretro's
/// callbacks carry no pointer back to whoever set them.
struct State {
    /// {option: value}, as C strings: the core keeps the pointer it is
    /// given, so each value has to live as long as the console.
    options: HashMap<Vec<u8>, CString>,
    directory: CString,
    audio: Vec<i16>,
}

static STATE: Mutex<Option<State>> = Mutex::new(None);

fn with_state<T>(f: impl FnOnce(&mut State) -> T) -> Option<T> {
    // A panic inside a callback would unwind into C; a poisoned lock is
    // taken as it is instead.
    let mut guard = STATE.lock().unwrap_or_else(|e| e.into_inner());
    guard.as_mut().map(f)
}

unsafe extern "C" fn on_environment(cmd: c_uint, data: *mut c_void) -> bool {
    match cmd {
        ENV_SET_VARIABLES if !data.is_null() => {
            let mut v = data as *const Variable;
            with_state(|s| {
                while !(*v).key.is_null() {
                    let key = CStr::from_ptr((*v).key).to_bytes().to_vec();
                    let text = CStr::from_ptr((*v).value).to_string_lossy();
                    // "Description; one|two|three": the default is the first.
                    let after = text.split_once(';').map_or(&*text, |(_, rest)| rest);
                    let default = after.trim().split('|').next().unwrap_or("").trim();
                    s.options
                        .insert(key, CString::new(default).unwrap_or_default());
                    v = v.add(1);
                }
            });
            true
        }
        ENV_GET_VARIABLE if !data.is_null() => {
            let v = data as *mut Variable;
            if (*v).key.is_null() {
                return false;
            }
            let key = CStr::from_ptr((*v).key).to_bytes().to_vec();
            with_state(|s| match s.options.get(&key) {
                Some(value) => {
                    (*v).value = value.as_ptr();
                    true
                }
                None => false,
            })
            .unwrap_or(false)
        }
        ENV_SET_PIXEL_FORMAT => {
            let format = *(data as *const c_int);
            (0..=2).contains(&format)
        }
        // No cropping, and a repeated frame may come without data: neither
        // matters for the audio, but they are what changes how the core
        // runs, so they are answered like the harness answers them.
        ENV_GET_OVERSCAN | ENV_GET_CAN_DUPE => {
            *(data as *mut bool) = true;
            true
        }
        ENV_GET_SYSTEM_DIRECTORY | ENV_GET_SAVE_DIRECTORY if !data.is_null() => {
            with_state(|s| *(data as *mut *const c_char) = s.directory.as_ptr()).is_some()
        }
        _ => false,
    }
}

unsafe extern "C" fn on_video(_data: *const c_void, _w: c_uint, _h: c_uint, _pitch: usize) {}

unsafe extern "C" fn on_audio_sample(_left: i16, _right: i16) {}

unsafe extern "C" fn on_audio_batch(data: *const i16, frames: usize) -> usize {
    if !data.is_null() {
        let samples = std::slice::from_raw_parts(data, frames * 2);
        with_state(|s| s.audio.extend_from_slice(samples));
    }
    frames
}

unsafe extern "C" fn on_input_poll() {}

unsafe extern "C" fn on_input_state(
    _port: c_uint,
    _device: c_uint,
    _index: c_uint,
    _id: c_uint,
) -> i16 {
    0
}

type EnvironmentFn = unsafe extern "C" fn(c_uint, *mut c_void) -> bool;
type VideoFn = unsafe extern "C" fn(*const c_void, c_uint, c_uint, usize);
type SampleFn = unsafe extern "C" fn(i16, i16);
type BatchFn = unsafe extern "C" fn(*const i16, usize) -> usize;
type PollFn = unsafe extern "C" fn();
type StateFn = unsafe extern "C" fn(c_uint, c_uint, c_uint, c_uint) -> i16;

/// A loaded core with a ROM in it.
pub struct Console {
    run: unsafe extern "C" fn(),
    av_info: unsafe extern "C" fn(*mut AvInfo),
    // The ROM's bytes, which the core may keep pointing at.
    _rom: Vec<u8>,
    _path: CString,
}

unsafe fn symbol<T>(lib: *mut c_void, name: &str) -> Result<T> {
    let c = CString::new(name).unwrap();
    let p = libc::dlsym(lib, c.as_ptr());
    if p.is_null() {
        return Err(Bad::usage(format!("the core has no {name}")));
    }
    Ok(std::mem::transmute_copy(&p))
}

impl Console {
    /// Loads `core` with the ROM at `rom`. The ROM has to be alone in its
    /// directory: that directory is what the core gets as its system and
    /// save directory, and where it would look for MSU-1 tracks.
    pub fn open(core: &Path, rom: &Path) -> Result<Console> {
        let data = std::fs::read(rom).map_err(|e| Bad::usage(format!("{}: {e}", rom.display())))?;
        let directory = rom.parent().unwrap_or(Path::new("."));
        let c = |p: &Path| CString::new(p.to_string_lossy().as_bytes()).unwrap();
        {
            let mut guard = STATE.lock().unwrap_or_else(|e| e.into_inner());
            if guard.is_some() {
                return Err(Bad::usage(
                    "one console per process: a core's state is global".to_string(),
                ));
            }
            *guard = Some(State {
                options: HashMap::new(),
                directory: c(directory),
                audio: Vec::new(),
            });
        }
        let path = c(rom);
        let core_c = c(core);
        unsafe {
            let lib = libc::dlopen(core_c.as_ptr(), libc::RTLD_NOW | libc::RTLD_LOCAL);
            if lib.is_null() {
                let why = CStr::from_ptr(libc::dlerror())
                    .to_string_lossy()
                    .into_owned();
                return Err(Bad::usage(format!(
                    "cannot load the core {}: {why}",
                    core.display()
                )));
            }
            let get_system_info: unsafe extern "C" fn(*mut SystemInfo) =
                symbol(lib, "retro_get_system_info")?;
            let set_environment: unsafe extern "C" fn(EnvironmentFn) =
                symbol(lib, "retro_set_environment")?;
            let init: unsafe extern "C" fn() = symbol(lib, "retro_init")?;
            let set_video: unsafe extern "C" fn(VideoFn) = symbol(lib, "retro_set_video_refresh")?;
            let set_sample: unsafe extern "C" fn(SampleFn) = symbol(lib, "retro_set_audio_sample")?;
            let set_batch: unsafe extern "C" fn(BatchFn) =
                symbol(lib, "retro_set_audio_sample_batch")?;
            let set_poll: unsafe extern "C" fn(PollFn) = symbol(lib, "retro_set_input_poll")?;
            let set_state: unsafe extern "C" fn(StateFn) = symbol(lib, "retro_set_input_state")?;
            let load_game: unsafe extern "C" fn(*const GameInfo) -> bool =
                symbol(lib, "retro_load_game")?;

            let mut info: SystemInfo = std::mem::zeroed();
            get_system_info(&mut info);
            // A core that opens the file itself ignores the data; the path
            // goes always, and the data only to whoever does not ask for
            // the file.
            let wants_path = info.need_fullpath;

            set_environment(on_environment);
            init();
            set_video(on_video);
            set_sample(on_audio_sample);
            set_batch(on_audio_batch);
            set_poll(on_input_poll);
            set_state(on_input_state);

            let game = GameInfo {
                path: path.as_ptr(),
                data: if wants_path {
                    std::ptr::null()
                } else {
                    data.as_ptr() as *const c_void
                },
                size: data.len(),
                meta: std::ptr::null(),
            };
            // Some cores print to standard output when loading —snes9x
            // writes its memory map—, and standard output is where whoever
            // runs this reads the answer. It is a printf from C, so it is
            // silenced by moving the descriptor, and libc's buffer is
            // flushed before putting it back: otherwise the text would come
            // out at exit, when the descriptor is ours again.
            libc::fflush(std::ptr::null_mut());
            let saved = libc::dup(1);
            let devnull = libc::open(c"/dev/null".as_ptr(), libc::O_WRONLY);
            libc::dup2(devnull, 1);
            let loaded = load_game(&game);
            libc::fflush(std::ptr::null_mut());
            libc::dup2(saved, 1);
            libc::close(devnull);
            libc::close(saved);
            if !loaded {
                return Err(Bad::usage(format!(
                    "the core could not load {}",
                    rom.display()
                )));
            }
            Ok(Console {
                run: symbol(lib, "retro_run")?,
                av_info: symbol(lib, "retro_get_system_av_info")?,
                _rom: data,
                _path: path,
            })
        }
    }

    /// Runs `frames` frames.
    pub fn run(&mut self, frames: usize) {
        for _ in 0..frames {
            unsafe { (self.run)() };
        }
    }

    /// At how many samples per second the core delivers the audio: it is
    /// each core's and each load's, not the console's.
    pub fn sample_rate(&self) -> f64 {
        let mut info = AvInfo::default();
        unsafe { (self.av_info)(&mut info) };
        info.sample_rate
    }

    /// What the core played since the last call, stereo interleaved.
    pub fn take_audio(&mut self) -> Vec<i16> {
        with_state(|s| std::mem::take(&mut s.audio)).unwrap_or_default()
    }
}
