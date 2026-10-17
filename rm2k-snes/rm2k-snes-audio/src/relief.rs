//! A package whose music would go below the sound effects' own rate, 6 kHz,
//! to make room for its sound effects, relieved: its songs after the first
//! go separate —each uploaded when its `PlayBGM` asks for it—, and the sound
//! effects at the end of its list are left out, until what is left fits with
//! the music at that rate.
//!
//! **The floor is 6 kHz, and below it a package is relieved**: taro's, on
//! 2026-10-16, after hearing A Blurred Line's map 3 both ways —*"vamos por
//! el 6k. Coincido en que el salto entre 4 y 6k no tiene sentido, y 4k es
//! demasiado poco"* ("6k it is. I agree the jump between 4 and 6k makes no
//! sense, and 4k is too little")—. Until then a package was relieved only
//! when it did not fit **even with every sample at the minimum** (from
//! 2026-10-15; before that, the build stopped there), so a package a few
//! bytes lighter kept every effect and got its music squeezed to ~4.5 kHz,
//! and one a few bytes heavier got it at 6 kHz with fewer effects. A
//! package whose music stays at 6 kHz or above is not touched: how far its
//! sound effects push it down to there is the allocation's, and the game's
//! by ear (`paid_by_music`, `[sound_effects.whole]`).

use crate::bank::Key;
use crate::compile::Package;
use crate::effects::SE_RATE;
use std::collections::{BTreeMap, BTreeSet, HashMap};

/// The `kind` of each loss in `degradations.json`.
pub const SONGS_ON_PLAY: &str = "songs-uploaded-on-play";
pub const EFFECTS_LEFT_OUT: &str = "sound-effects-left-out";
pub const PACKAGE_WAITS: &str = "package-waits-for-playbgm";

/// What a relieved package loses, as `degradations.json` wants it: the map,
/// if the package is a map's —the battle's, the Game Over's and the title's
/// are the cartridge's—, a stable `kind` and what is lost.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Loss {
    pub map: Option<i64>,
    pub kind: &'static str,
    pub text: String,
}

/// What a sample takes in the ARAM at its least and at the floor rate.
#[derive(Clone, Copy, Debug, Default)]
pub struct Sizes {
    /// Built with the smallest budget the bank gives: what `Bank::new` ends
    /// up checking when everything else failed.
    pub minimum: i64,
    /// At [`SE_RATE`], or its native size if the sample is slower than that.
    pub floor: i64,
}

/// A sample's size at the floor rate, from its native size and rate. The
/// sound effects play at [`SE_RATE`] and the game accepts them so: a music
/// sample is not pushed below that to make room for them when it is this
/// module, and not the game, deciding what is lost.
pub fn floor_bytes(native_bytes: i64, native_rate: f64) -> i64 {
    if native_rate <= SE_RATE as f64 {
        return native_bytes;
    }
    let bytes = native_bytes as f64 * SE_RATE as f64 / native_rate;
    let block = crate::samples::BLOCK_BYTES as i64;
    (bytes / block as f64).ceil() as i64 * block
}

fn keys_of_songs(songs: &[usize], keys_of: &[BTreeSet<Key>]) -> BTreeSet<Key> {
    songs.iter().flat_map(|&t| keys_of.get(t).cloned().unwrap_or_default()).collect()
}

fn list(names: &[&str]) -> String {
    match names.len() {
        0 => String::new(),
        1 => names[0].to_string(),
        n => format!("{} and {}", names[..n - 1].join(", "), names[n - 1]),
    }
}

/// Relieves the packages whose music does not fit in `free` at the floor
/// rate next to every sound effect, and says what each one lost. `keys_of` are each song's samples, `sizes` each
/// sample's, `budgeted` what the music budgets for each sound effect, and
/// `room` what the relieved package is given to fit in at the floor rate:
/// less than `free`, so that the copies and the block rounding that come
/// after still fit.
///
/// A package that fits at the floor rate is not touched. In one that does
/// not, first its songs go separate: from the end of its list, one at a
/// time, until the ones left fit with every sound effect at the floor rate
/// or only the first is left, if it `enters` —the first is then the one
/// that plays on entering, the map's own or the boot's, see `plan` in
/// `cartridge`—; **all of them** if it does not: in a map whose songs are
/// all started by its pages' `PlayBGM`s, keeping one would upload on every
/// entry a song that is likely not the one about to play, and squeeze the
/// sound effects next to the one that is. A separate song is started by its
/// `PlayBGM`, which uploads it then, with a pause. Then the sound effects are left out
/// from the end of the list, until the music of the package —and of each
/// separate song alone, since each goes up with the same sound effects—
/// fits at the floor rate: the end of the list is also what the ROM leaves
/// out when the package does not fit, so what the tool budgets is what
/// plays. Songs before sound effects because a separate song still plays,
/// with a pause, and a sound effect left out does not.
#[allow(clippy::too_many_arguments)]
pub fn relieve(
    packages: &mut [Package],
    enters: &[bool],
    keys_of: &[BTreeSet<Key>],
    sizes: &HashMap<Key, Sizes>,
    budgeted: &BTreeMap<String, i64>,
    free: i64,
    room: i64,
    names: &[String],
) -> Vec<Loss> {
    let size = |keys: &BTreeSet<Key>, pick: fn(&Sizes) -> i64| -> i64 {
        keys.iter().filter_map(|k| sizes.get(k)).map(pick).sum()
    };
    let mut losses = Vec::new();
    for (i, p) in packages.iter_mut().enumerate() {
        let enters = enters.get(i).copied().unwrap_or(true);
        let mut own: Vec<String> = Vec::new();
        for e in &p.effects {
            if budgeted.contains_key(e) && !own.contains(e) {
                own.push(e.clone());
            }
        }
        let effects_all: i64 = own.iter().map(|e| budgeted[e]).sum();
        // Against `free`, the ARAM with the directory as it is now, and not
        // `room`, which is smaller: so a package whose music stays at 6 kHz
        // or above is surely not touched. The relief itself aims at `room`.
        if effects_all + size(&keys_of_songs(&p.songs, keys_of), |s| s.floor) <= free {
            continue;
        }
        let where_ = match p.name.parse::<i64>() {
            Ok(map) => format!("map {map}"),
            Err(_) => format!("package {}", p.name),
        };
        let map = p.name.parse::<i64>().ok();

        let mut kept = p.songs.clone();
        let mut moved: Vec<usize> = Vec::new();
        if enters {
            while kept.len() > 1 && effects_all + size(&keys_of_songs(&kept, keys_of), |s| s.floor) > room {
                moved.insert(0, kept.pop().unwrap());
            }
        } else {
            std::mem::swap(&mut kept, &mut moved);
        }
        // The music that has to fit next to the sound effects, at the floor
        // rate: the package's songs together, and each separate song alone.
        let alone = p.separate.iter().chain(&moved);
        let music_floor = alone
            .map(|&t| size(&keys_of_songs(&[t], keys_of), |s| s.floor))
            .chain(std::iter::once(size(&keys_of_songs(&kept, keys_of), |s| s.floor)))
            .max()
            .unwrap_or(0);
        let mut kept_effects = own.clone();
        let mut cut: Vec<String> = Vec::new();
        while !kept_effects.is_empty() && kept_effects.iter().map(|e| budgeted[e]).sum::<i64>() + music_floor > room {
            cut.insert(0, kept_effects.pop().unwrap());
        }

        if !moved.is_empty() {
            let name = |t: &usize| names.get(*t).map_or("?", String::as_str);
            let moved_names: Vec<&str> = moved.iter().map(name).collect();
            let together = if kept.is_empty() {
                format!("its {} sound effect(s)", own.len())
            } else {
                format!("{} and its {} sound effect(s)", list(&kept.iter().map(name).collect::<Vec<_>>()), own.len())
            };
            losses.push(Loss {
                map,
                kind: SONGS_ON_PLAY,
                text: format!(
                    "{where_}: its songs {} do not fit in the ARAM together with {together}: each one is uploaded \
                     when its PlayBGM asks for it, with a pause, and the others are let go",
                    list(&moved_names),
                ),
            });
            p.separate.extend(moved);
            p.songs = kept;
        }
        if !cut.is_empty() {
            let cut_names: Vec<&str> = cut.iter().map(String::as_str).collect();
            losses.push(Loss {
                map,
                kind: EFFECTS_LEFT_OUT,
                text: format!(
                    "{where_}: {} of its {} sound effects do not fit in the ARAM next to its music at {} kHz and do not \
                     play there: {}",
                    cut.len(),
                    own.len(),
                    SE_RATE / 1000,
                    list(&cut_names)
                ),
            });
            p.effects.retain(|e| !cut.contains(e));
        }
    }
    losses
}

/// Keeps, of the `inheritance` pairs —(package, song that may be playing
/// when it loads)—, the ones whose package fits next to that song in `free`
/// at the minimum, and says what each dropped one loses: a package that
/// cannot fit next to the arriving song even so is not made to, because
/// nothing is left to lower. The ROM does what it does when a package does
/// not fit next to the song playing: it uploads what fits, and the next
/// `PlayBGM` —which silences that song— completes it. See `song_ensure` in
/// the runtime's `audio_package.s`.
pub fn relieve_inheritance(
    inheritance: &[(String, usize)],
    packages: &[Package],
    keys_of: &[BTreeSet<Key>],
    sizes: &HashMap<Key, Sizes>,
    free: i64,
    names: &[String],
) -> (Vec<(String, usize)>, Vec<Loss>) {
    let (mut kept, mut losses) = (Vec::new(), Vec::new());
    for (name, song) in inheritance {
        let mut songs: Vec<usize> = packages.iter().find(|p| &p.name == name).map(|p| p.songs.clone()).unwrap_or_default();
        songs.push(*song);
        let minimum: i64 = keys_of_songs(&songs, keys_of).iter().filter_map(|k| sizes.get(k)).map(|s| s.minimum).sum();
        if minimum <= free {
            kept.push((name.clone(), *song));
            continue;
        }
        let where_ = match name.parse::<i64>() {
            Ok(map) => format!("map {map}"),
            Err(_) => format!("package {name}"),
        };
        losses.push(Loss {
            map: name.parse::<i64>().ok(),
            kind: PACKAGE_WAITS,
            text: format!(
                "{where_}: with {} playing on arrival, its audio package does not fit in the ARAM next to it even \
                 at the minimum: what does not fit waits for the next PlayBGM",
                names.get(*song).map_or("?", String::as_str)
            ),
        });
    }
    (kept, losses)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn package(name: &str, songs: &[usize], effects: &[&str]) -> Package {
        Package {
            name: name.into(),
            songs: songs.to_vec(),
            effects: effects.iter().map(|e| e.to_string()).collect(),
            ..Default::default()
        }
    }

    /// (each song's keys, each key's sizes, each sound effect's budget, the
    /// songs' names)
    type World = (Vec<BTreeSet<Key>>, HashMap<Key, Sizes>, BTreeMap<String, i64>, Vec<String>);

    /// Four songs with two samples each, every sample 100 B at the minimum
    /// and 1,000 B at the floor; three sound effects of 2,000 B.
    fn world() -> World {
        let mut keys_of = Vec::new();
        let mut sizes = HashMap::new();
        for t in 0..4u8 {
            let own: BTreeSet<Key> = [Key::program(2 * t, 60), Key::program(2 * t + 1, 60)].into();
            for k in &own {
                sizes.insert(k.clone(), Sizes { minimum: 100, floor: 1000 });
            }
            keys_of.push(own);
        }
        let budgeted = ["a", "b", "c"].iter().map(|e| (e.to_string(), 2000)).collect();
        let names = ["first", "second", "third", "fourth"].iter().map(|s| s.to_string()).collect();
        (keys_of, sizes, budgeted, names)
    }

    #[test]
    fn a_package_whose_music_fits_at_the_floor_is_not_touched() {
        let (keys_of, sizes, budgeted, names) = world();
        // 6,000 of sound effects and 8,000 of music at the floor, in 14,000:
        // the music stays at 6 kHz or above, and nothing is lost.
        let mut packages = vec![package("3", &[0, 1, 2, 3], &["a", "b", "c"])];
        let losses = relieve(&mut packages, &[true], &keys_of, &sizes, &budgeted, 14000, 13000, &names);
        assert!(losses.is_empty(), "{losses:?}");
        assert_eq!(packages[0].songs, [0, 1, 2, 3]);
        assert!(packages[0].separate.is_empty());
        assert_eq!(packages[0].effects.len(), 3);
    }

    #[test]
    fn a_package_that_fits_only_below_the_floor_is_relieved() {
        let (keys_of, sizes, budgeted, names) = world();
        // 6,000 of sound effects and 800 of music at the minimum fit in
        // 7,000, but at the floor its music is 8,000: it is relieved instead
        // of squeezing the music below 6 kHz.
        let mut packages = vec![package("3", &[0, 1, 2, 3], &["a", "b", "c"])];
        let losses = relieve(&mut packages, &[true], &keys_of, &sizes, &budgeted, 7000, 6500, &names);
        assert!(!losses.is_empty());
        assert_eq!(packages[0].songs, [0]);
        assert_eq!(packages[0].effects, ["a", "b"]);
    }

    #[test]
    fn the_songs_after_the_first_go_separate_and_the_last_effects_are_left_out() {
        let (keys_of, sizes, budgeted, names) = world();
        // 6,000 of sound effects and 800 of music at the minimum do not fit
        // in 6,500. With 6,500 of room: one song at the floor is 2,000, so
        // the other three go separate, and then 2,000 + 6,000 is still over,
        // so the last sound effect goes and 2,000 + 4,000 fits.
        let mut packages = vec![package("1", &[0, 1, 2, 3], &["a", "b", "c"])];
        let losses = relieve(&mut packages, &[true], &keys_of, &sizes, &budgeted, 6500, 6500, &names);
        assert_eq!(packages[0].songs, [0]);
        assert_eq!(packages[0].separate, [1, 2, 3]);
        assert_eq!(packages[0].effects, ["a", "b"]);
        assert_eq!(losses.len(), 2);
        assert_eq!((losses[0].map, losses[0].kind), (Some(1), SONGS_ON_PLAY));
        assert!(losses[0].text.starts_with("map 1: its songs second, third and fourth do not fit"), "{}", losses[0].text);
        assert_eq!((losses[1].map, losses[1].kind), (Some(1), EFFECTS_LEFT_OUT));
        assert!(losses[1].text.contains("1 of its 3 sound effects") && losses[1].text.ends_with(": c"), "{}", losses[1].text);
    }

    /// A map whose songs are all started by `PlayBGM`s —none plays on
    /// entering— sends every one to its `PlayBGM`: the package keeps the
    /// sound effects alone, and more of them fit.
    #[test]
    fn where_no_song_plays_on_entering_every_song_goes_separate() {
        let (keys_of, sizes, budgeted, names) = world();
        let mut packages = vec![package("1", &[0, 1, 2, 3], &["a", "b", "c"])];
        let losses = relieve(&mut packages, &[false], &keys_of, &sizes, &budgeted, 6500, 8000, &names);
        assert!(packages[0].songs.is_empty(), "{:?}", packages[0].songs);
        assert_eq!(packages[0].separate, [0, 1, 2, 3]);
        // Each separate song alone at the floor is 2,000: all three sound
        // effects fit next to it in 8,000.
        assert_eq!(packages[0].effects, ["a", "b", "c"]);
        assert_eq!(losses.len(), 1);
        assert!(losses[0].text.contains("together with its 3 sound effect(s)"), "{}", losses[0].text);
    }

    #[test]
    fn only_as_many_songs_as_needed_go_separate() {
        let (keys_of, sizes, budgeted, names) = world();
        // With 10,000 of room, two songs at the floor —4,000— fit next to the
        // 6,000 of sound effects: the last two go, in the list's order.
        let mut packages = vec![package("5", &[0, 1, 2, 3], &["a", "b", "c"])];
        relieve(&mut packages, &[true], &keys_of, &sizes, &budgeted, 6500, 10000, &names);
        assert_eq!(packages[0].songs, [0, 1]);
        assert_eq!(packages[0].separate, [2, 3]);
        assert_eq!(packages[0].effects.len(), 3);
    }

    #[test]
    fn a_lone_song_without_effects_is_left_to_the_allocation() {
        let (keys_of, sizes, budgeted, names) = world();
        // Nothing to separate and nothing to cut: `Bank::new` says whether
        // it fits at the minimum, as before.
        let mut packages = vec![package("pelea", &[0], &[])];
        let losses = relieve(&mut packages, &[true], &keys_of, &sizes, &budgeted, 100, 50, &names);
        assert!(losses.is_empty());
        assert_eq!(packages[0].songs, [0]);
    }

    #[test]
    fn a_package_that_is_not_a_maps_is_the_cartridges() {
        let (keys_of, sizes, budgeted, names) = world();
        let mut packages = vec![package("pelea", &[0, 1], &["a", "b", "c"])];
        let losses = relieve(&mut packages, &[true], &keys_of, &sizes, &budgeted, 6000, 6000, &names);
        assert_eq!(losses[0].map, None);
        assert!(losses[0].text.starts_with("package pelea:"), "{}", losses[0].text);
    }

    #[test]
    fn a_package_that_cannot_fit_next_to_an_arriving_song_waits_for_the_playbgm() {
        let (keys_of, sizes, _, names) = world();
        // Two songs at the minimum are 400 B: the package with the arriving
        // song fits in 500 and the pair stays; with 300 it cannot, the pair
        // goes and the loss says so.
        let packages = vec![package("4", &[0], &[]), package("pelea", &[1], &[])];
        let pairs = vec![("4".to_string(), 1), ("pelea".to_string(), 2)];
        let (kept, losses) = relieve_inheritance(&pairs, &packages, &keys_of, &sizes, 500, &names);
        assert_eq!(kept, pairs);
        assert!(losses.is_empty());
        let (kept, losses) = relieve_inheritance(&pairs, &packages, &keys_of, &sizes, 300, &names);
        assert!(kept.is_empty(), "{kept:?}");
        assert_eq!(losses.len(), 2);
        assert_eq!((losses[0].map, losses[0].kind), (Some(4), PACKAGE_WAITS));
        assert!(losses[0].text.starts_with("map 4: with second playing on arrival"), "{}", losses[0].text);
        assert_eq!(losses[1].map, None);
    }

    #[test]
    fn the_floor_is_the_effects_rate_in_whole_blocks() {
        // 9,000 B at 22,050 Hz: 2,449 B at 6,000, which is 273 blocks.
        assert_eq!(floor_bytes(9000, 22050.0), 273 * 9);
        // A sample already below the rate keeps its size.
        assert_eq!(floor_bytes(900, 4000.0), 900);
    }
}
