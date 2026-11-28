//! The cache forgets what nobody used in four days, and never what a
//! process that may still read it is alive for: the sweep with the clock
//! ahead and with stamps set back, and the lock between two processes.

use std::fs::{self, File, FileTimes};
use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, SystemTime};

use rm2k_project::cache::{self, Eviction, Swept};

const DAY: Duration = Duration::from_secs(24 * 60 * 60);

/// A fresh directory under the target dir, one per test.
fn scratch(name: &str) -> PathBuf {
    let dir = Path::new(env!("CARGO_TARGET_TMPDIR"))
        .join("eviction")
        .join(name);
    let _ = fs::remove_dir_all(&dir);
    fs::create_dir_all(&dir).unwrap();
    dir
}

/// Puts `path`'s stamp `days` back, as if nobody had used it since.
fn used_days_ago(path: &Path, days: u32) {
    let then = SystemTime::now() - DAY * days;
    File::open(path)
        .unwrap()
        .set_times(FileTimes::new().set_accessed(then))
        .unwrap();
}

/// What each kind of entry is left with after a sweep four days after the
/// fact: a value nobody read in twenty days goes, also a whole directory
/// —a game unpacked in `zip/`—; one read three days ago stays; one left
/// half written goes whatever its age; and the lock and the sweep's own
/// date are not entries. A hard link a build keeps frees no bytes.
#[test]
fn a_sweep_takes_what_nobody_used_in_two_weeks() {
    let dir = scratch("sweep");
    assert!(cache::store(&dir, "stages", "old", b"12345"));
    assert!(cache::store(&dir, "stages", "recent", b"x"));
    assert!(cache::store(&dir, "ca65", "old", b"1234567"));
    fs::create_dir_all(dir.join("zip").join("game-1").join("Music")).unwrap();
    fs::write(
        dir.join("zip").join("game-1").join("Music").join("a.mid"),
        b"abc",
    )
    .unwrap();
    fs::write(dir.join("stages").join(".tmp-1-0-0-k"), b"half").unwrap();
    let build = scratch("sweep-build");
    fs::write(build.join("game-1.pcm"), b"track").unwrap();
    assert!(cache::store_file(
        &dir,
        "msu-tracks",
        "old",
        &build.join("game-1.pcm")
    ));
    for old in [
        cache::entry(&dir, "stages", "old"),
        cache::entry(&dir, "ca65", "old"),
        cache::entry(&dir, "msu-tracks", "old"),
        dir.join("zip").join("game-1"),
    ] {
        used_days_ago(&old, 20);
    }
    used_days_ago(&cache::entry(&dir, "stages", "recent"), 3);

    let cutoff = SystemTime::now() - cache::UNUSED_FOR;
    let counted = cache::sweep(&dir, cutoff, false);
    assert_eq!(
        counted,
        Swept {
            entries: 5,
            bytes: 5 + 7 + 3 + 4
        }
    );
    assert!(
        cache::entry(&dir, "stages", "old").is_file(),
        "counting deletes nothing"
    );
    assert_eq!(cache::sweep(&dir, cutoff, false), counted, "nor stamps");

    assert_eq!(cache::sweep(&dir, cutoff, true), counted);
    let mut left = Vec::new();
    for category in fs::read_dir(&dir).unwrap() {
        let category = category.unwrap();
        if category.file_type().unwrap().is_dir() {
            for item in fs::read_dir(category.path()).unwrap() {
                left.push(format!(
                    "{}/{}",
                    category.file_name().to_string_lossy(),
                    item.unwrap().file_name().to_string_lossy()
                ));
            }
        }
    }
    left.sort();
    assert_eq!(left, ["stages/recent"]);
    assert!(dir.join(".lock").is_file());
    assert_eq!(fs::read(build.join("game-1.pcm")).unwrap(), b"track");
}

/// Reading a value is using it, though the kernel's access time would not
/// say so —`noatime`—, and so is fetching a stored file as a hard link,
/// which reads nothing, and finding one's own copy still in place.
#[test]
fn reading_fetching_or_touching_a_value_keeps_it() {
    let dir = scratch("stamp");
    let build = scratch("stamp-build");
    fs::write(build.join("made.pcm"), b"track").unwrap();
    assert!(cache::store(&dir, "stages", "read", b"v"));
    assert!(cache::store_file(
        &dir,
        "msu-tracks",
        "fetched",
        &build.join("made.pcm")
    ));
    assert!(cache::store(&dir, "msu-tracks", "touched", b"t"));
    assert!(cache::store(&dir, "stages", "forgotten", b"f"));
    for key in ["read", "forgotten"] {
        used_days_ago(&cache::entry(&dir, "stages", key), 20);
    }
    for key in ["fetched", "touched"] {
        used_days_ago(&cache::entry(&dir, "msu-tracks", key), 20);
    }

    assert_eq!(cache::load(&dir, "stages", "read").unwrap(), b"v");
    assert!(cache::fetch_file(
        &dir,
        "msu-tracks",
        "fetched",
        &build.join("game-1.pcm")
    ));
    cache::touch(&dir, "msu-tracks", "touched");

    let cutoff = SystemTime::now() - cache::UNUSED_FOR;
    assert_eq!(cache::sweep(&dir, cutoff, true).entries, 1);
    assert!(cache::entry(&dir, "stages", "read").is_file());
    assert!(cache::entry(&dir, "msu-tracks", "fetched").is_file());
    assert!(cache::entry(&dir, "msu-tracks", "touched").is_file());
    assert!(!cache::entry(&dir, "stages", "forgotten").exists());
}

/// With the clock four days and a day ahead, what was stored today goes;
/// and a build sweeps once a day, not every time: the next one, an hour
/// later, finds it not due. Whatever it answers, the process holds the
/// cache after, so a second sweep in it cannot lock it.
#[test]
fn the_clock_decides_what_is_old_and_when_to_sweep_again() {
    let dir = scratch("clock");
    // Stored by hand: `store` would hold this directory before the sweep.
    fs::create_dir_all(dir.join("stages")).unwrap();
    fs::write(dir.join("stages").join("k"), b"value").unwrap();
    let later = SystemTime::now() + cache::UNUSED_FOR + DAY;
    assert_eq!(
        cache::evict_and_hold(&dir, later),
        Eviction::Swept(Swept {
            entries: 1,
            bytes: 5
        })
    );
    assert!(!cache::entry(&dir, "stages", "k").exists());
    assert_eq!(
        cache::evict_and_hold(&dir, later + DAY),
        Eviction::AlreadyHeld
    );

    // Another process an hour later, which the child is.
    let dir = scratch("clock-not-due");
    fs::create_dir_all(dir.join("stages")).unwrap();
    fs::write(dir.join("stages").join("k"), b"value").unwrap();
    assert_eq!(
        child(&dir, "evict 16").answer(),
        "Swept(Swept { entries: 1, bytes: 5 })"
    );
    fs::write(dir.join("stages").join("k"), b"value").unwrap();
    assert_eq!(child(&dir, "evict 16").answer(), "NotDue");
    assert_eq!(
        child(&dir, "evict 18").answer(),
        "Swept(Swept { entries: 1, bytes: 5 })"
    );
}

/// **Two processes**: while one holds the cache —a build, a stage a test
/// runs— another's sweep does not wait and deletes nothing; and while one
/// sweeps —here, this test holding the lock exclusively— a process that
/// comes to read waits until it is done.
#[test]
fn nothing_is_swept_while_another_process_holds_the_cache() {
    let dir = scratch("two");
    fs::create_dir_all(dir.join("stages")).unwrap();
    fs::write(dir.join("stages").join("k"), b"value").unwrap();
    used_days_ago(&dir.join("stages").join("k"), 20);

    let mut reader = child(&dir, "hold");
    reader.wait_for("HELD", Duration::from_secs(30));
    assert_eq!(child(&dir, "evict 0").answer(), "Busy");
    assert!(dir.join("stages").join("k").is_file());
    reader.finish();
    assert_eq!(
        child(&dir, "evict 0").answer(),
        "Swept(Swept { entries: 1, bytes: 5 })"
    );

    let sweeping = File::options()
        .read(true)
        .write(true)
        .open(dir.join(".lock"))
        .unwrap();
    sweeping.lock().unwrap();
    let mut reader = child(&dir, "hold");
    assert!(
        reader
            .lines
            .recv_timeout(Duration::from_millis(500))
            .is_err(),
        "it read while the cache was being swept"
    );
    drop(sweeping);
    reader.wait_for("HELD", Duration::from_secs(30));
    reader.finish();
}

/// One of this test binary's own processes, doing what `CACHE_CHILD` says
/// on `CACHE_DIR`: see [`child_process`].
struct Child {
    process: std::process::Child,
    lines: mpsc::Receiver<String>,
}

fn child(dir: &Path, what: &str) -> Child {
    let mut process = Command::new(std::env::current_exe().unwrap())
        .args([
            "child_process",
            "--exact",
            "--nocapture",
            "--test-threads=1",
        ])
        .env("CACHE_CHILD", what)
        .env("CACHE_DIR", dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .spawn()
        .unwrap();
    let out = process.stdout.take().unwrap();
    let (send, lines) = mpsc::channel();
    std::thread::spawn(move || {
        // The harness writes its own `test child_process ... ` in front.
        for line in BufReader::new(out).lines().map_while(Result::ok) {
            if let Some(at) = line.find("HELD").or_else(|| line.find("ANSWER ")) {
                let _ = send.send(line[at..].to_string());
            }
        }
    });
    Child { process, lines }
}

impl Child {
    fn wait_for(&mut self, line: &str, limit: Duration) {
        assert_eq!(self.lines.recv_timeout(limit).unwrap(), line);
    }

    /// What its sweep answered.
    fn answer(self) -> String {
        let line = self.lines.recv_timeout(Duration::from_secs(60)).unwrap();
        self.finish();
        line.strip_prefix("ANSWER ").unwrap().to_string()
    }

    /// Closes its stdin, which is what it waits for, and waits for it.
    fn finish(mut self) {
        drop(self.process.stdin.take());
        assert!(self.process.wait().unwrap().success());
    }
}

/// The other process, when `CACHE_CHILD` says what to do; nothing in a
/// normal run. `hold` holds the cache and says so, until its stdin closes;
/// `evict N` sweeps with the clock N days ahead and says what it did.
#[test]
fn child_process() {
    let (Some(what), Some(dir)) = (
        std::env::var_os("CACHE_CHILD"),
        std::env::var_os("CACHE_DIR"),
    ) else {
        return;
    };
    let what = what.to_string_lossy().into_owned();
    let dir = PathBuf::from(dir);
    if what == "hold" {
        cache::hold(&dir);
        println!("HELD");
    } else if let Some(days) = what.strip_prefix("evict ") {
        let days: u32 = days.parse().unwrap();
        let now = SystemTime::now() + DAY * days;
        println!("ANSWER {:?}", cache::evict_and_hold(&dir, now));
    }
    let mut rest = String::new();
    let _ = std::io::Read::read_to_string(&mut std::io::stdin(), &mut rest);
}
