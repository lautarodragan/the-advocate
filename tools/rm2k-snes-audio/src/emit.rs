//! What the ROM gets: `musicdata.inc`, the `.inc` the assembler builds along
//! with the runtime; and what the rest of the build needs to know about it.

use crate::bank::{self, SILENCE};
use crate::compile::{Built, Music};
use crate::effects;
use crate::fail::{Bad, Result};
use crate::music_opcodes::OP_END;
use crate::samples::BLOCK_BYTES;
use crate::sdsp;
use crate::spc700::DRIVER_ADDR;
use crate::stream::{self, SAMPLES_ADDR};
use crate::voices::{SE_VOICE, SE_VOICE2};
use std::fmt::Write as _;

/// How many directory places can belong to sound effects: the ROM records
/// which sound effect is in each one in `FAR_EFFECT_IN`, which has that size.
const SE_PLACES_MAX: usize = 48;

/// What uploading to the SPC700 costs, in frames, for the boot count. A
/// package's samples go in triplets through the driver's command 3:
/// measured in the ROM, from 1.33 to 1.42 frames per KB across eighteen
/// packages, and a bit more goes here. The driver and the directory go byte
/// by byte through the IPL, which measured 1.4. And loading the map, without
/// audio and without decompressing, is about 8 frames; 10 go here. What
/// decompressing costs depends on the map and goes separately.
const FRAMES_PER_KB_PACKAGE: f64 = 1.45;
const FRAMES_PER_KB_IPL: f64 = 1.5;
const MAP_FRAMES: f64 = 10.0;

/// A sound of the cartridge —an entry of the bytecode's sound table—: the
/// sound effect, its volume, its tempo and its pan, as RM2k says them.
#[derive(Clone, Debug)]
pub struct SoundRequest {
    pub effect: String,
    pub volume: i64,
    pub tempo: i64,
    pub balance: i64,
}

/// What the cartridge's compiler decided that goes into `musicdata.inc`
/// besides the music itself.
#[derive(Clone, Debug)]
pub struct Emit {
    /// How many of the packages are the ROM's, in map table order: the ones
    /// after them only constrain the allocation.
    pub packages: usize,
    /// The song that plays from the first frame, or $FF.
    pub boot: u8,
    /// The title screen's, or $FF.
    pub title: u8,
    /// The Game Over screen's song and its package, or $FF and $FFFF.
    pub game_over: (u8, u16),
    /// The song each map turns on when entered, or $FF.
    pub map_song: Vec<u8>,
    pub sounds: Vec<SoundRequest>,
    /// Which package the ROM boots with, and how many frames decompressing
    /// that map takes.
    pub start: usize,
    pub decompress_frames: f64,
}

/// A package as the ROM gets it: its songs, its sound effects by number, its
/// exit songs and its separate songs.
pub type RomPackage = (Vec<usize>, Vec<usize>, Vec<usize>, Vec<usize>);

pub fn rom_packages(music: &Music, emit: &Emit) -> Vec<RomPackage> {
    music.packages[..emit.packages]
        .iter()
        .map(|p| {
            (
                p.songs.clone(),
                p.effects.iter().filter_map(|e| music.effect_id(e)).collect(),
                p.exits.clone(),
                p.separate.clone(),
            )
        })
        .collect()
}

/// One row per sound: the sample —$FF if it did not fit—, the pitch, the
/// volume of each side, how many frames it lasts and the sound effect
/// number, which is what says which of the ones sharing the sample it is.
pub fn sound_table(music: &Music, sounds: &[SoundRequest]) -> Vec<(i64, i64, i64, i64, i64, i64)> {
    sounds
        .iter()
        .map(|s| {
            let (Some(srcn), Some(id)) = (music.srcn(&s.effect), music.effect_id(&s.effect)) else {
                return (0xFF, 0, 0, 0, 0, 0xFF);
            };
            let e = &music.effects[id];
            let (left, right) = effects::volume(s.volume, s.balance);
            (
                srcn as i64,
                effects::pitch(e.rate, s.tempo),
                left,
                right,
                effects::frames(e.seconds, s.tempo),
                id as i64,
            )
        })
        .collect()
}

/// How long boot takes, erring high: the map, the driver and the directory
/// through the IPL, and the samples of the boot map's package. The exit ones
/// count: they are uploaded if there is room, and with an empty ARAM there
/// is. Returns (frames, package bytes).
pub fn boot_frames(music: &Music, package: &RomPackage, decompress: f64) -> Result<(f64, i64)> {
    let (own, effects, exits, _) = package;
    let music_n = music.bank.voices.len();
    let mut indices: std::collections::BTreeSet<usize> = effects.iter().map(|e| music_n + e).collect();
    for &t in own.iter().chain(exits) {
        if !music.songs[t].sounds.is_empty() {
            indices.extend(music.songs[t].samples()?.into_iter().map(|s| s as usize));
        }
    }
    let all = music.all_samples();
    let bytes: i64 = indices.iter().map(|&i| all[i].0.len() as i64).sum();
    let ipl = (music.driver.len() + 4 * (music_n + music.places).max(1) + SILENCE.len()) as f64;
    Ok((
        MAP_FRAMES + decompress + ipl * FRAMES_PER_KB_IPL / 1024.0 + bytes as f64 * FRAMES_PER_KB_PACKAGE / 1024.0,
        bytes,
    ))
}

/// A labelled block of bytes. No `.block` except on the samples, and
/// `.crossbank` instead: the driver goes byte by byte through the ports and
/// the stream is walked by a reader that does the bank jump by hand, so they
/// can end up split. The samples do carry it: they are walked with a 24-bit
/// pointer that does not jump banks.
fn block(label: &str, data: &[u8], as_block: bool) -> String {
    let mut out = if as_block { format!(".block {}\n", data.len()) } else { ".crossbank\n".to_string() };
    out.push_str(&format!("{label}:"));
    for chunk in data.chunks(16) {
        out.push_str("\n    .byte ");
        out.push_str(&chunk.iter().map(|b| format!("${b:02X}")).collect::<Vec<_>>().join(","));
    }
    out
}

/// Lists of bytes, each part closed with $FF, with an index of offsets in
/// front.
fn lists(label: &str, groups: &[Vec<Vec<u8>>]) -> String {
    let mut body = Vec::new();
    let mut offsets = Vec::new();
    for group in groups {
        offsets.push(2 * groups.len() + body.len());
        for part in group {
            body.extend_from_slice(part);
            body.push(0xFF);
        }
    }
    let mut data: Vec<u8> = offsets.iter().flat_map(|o| (*o as u16).to_le_bytes()).collect();
    data.extend(body);
    if data.is_empty() {
        data.push(0xFF);
    }
    block(label, &data, true)
}

fn bytes_list(values: impl IntoIterator<Item = u8>) -> String {
    values.into_iter().map(|v| format!("${v:02X}")).collect::<Vec<_>>().join(", ")
}

fn as_bytes(values: &[usize]) -> Result<Vec<u8>> {
    values
        .iter()
        .map(|&v| u8::try_from(v).map_err(|_| Bad::answer(format!("{v} does not fit in a byte"))))
        .collect()
}

/// `musicdata.inc`.
///
/// The songs go in the order the bytecode already numbers them. None of the
/// samples is uploaded at boot: they go to the SPC700 in **packages**, one
/// per map, and the directory starts with all of them pointing to the
/// silence. The sound effects share the directory's last places, so its
/// entries are the music's samples and those places, not one per sample.
pub fn musicdata(music: &Music, emit: &Emit) -> Result<String> {
    let songs = &music.songs;
    let voices = music.all_samples();
    let music_n = music.bank.voices.len();
    let places = music.places;
    let driver = &music.driver;
    let sounds = sound_table(music, &emit.sounds);
    let packages = rom_packages(music, emit);

    let labels: Vec<String> = if songs.is_empty() {
        vec!["song_stream_0".into()]
    } else {
        (0..songs.len()).map(|i| format!("song_stream_{i}")).collect()
    };
    let end = vec![OP_END];
    let streams: Vec<&[u8]> =
        if songs.is_empty() { vec![&end] } else { songs.iter().map(|t| t.stream.as_slice()).collect() };
    let mut table = [("song_lo", "<"), ("song_hi", ">"), ("song_bk", "^")]
        .iter()
        .map(|(name, prefix)| {
            format!(
                "{name}:\n    .byte {}",
                labels.iter().map(|l| format!("{prefix}{l}")).collect::<Vec<_>>().join(", ")
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    // The DSP prologue, for the MSU-1 path. With a track the stream never
    // runs, and it is the start of the stream that takes the DSP out of the
    // mute the SPC700 boots with, sets its master volume and tells it where
    // the sample directory is. Without this, sound effects fire against a
    // mute DSP and are not heard.
    //
    // KON and KOF are left out on purpose: with a track, the ROM leaves KOF
    // at $FF so the music's voices do not play, and clears it only when a
    // sound effect starts.
    //
    // Two parallel tables and not one of pairs because the 65816 walks them
    // with an index.
    let init: Vec<(u8, u8)> =
        stream::init_writes().into_iter().filter(|(r, _)| *r != sdsp::KON && *r != sdsp::KOF).collect();
    write!(table, "\ndsp_init_reg:\n    .byte {}, $FF", bytes_list(init.iter().map(|w| w.0))).unwrap();
    write!(table, "\ndsp_init_val:\n    .byte {}, $00", bytes_list(init.iter().map(|w| w.1))).unwrap();
    // And which MSU-1 track each one gets, or $FF.
    let tracks: Vec<u8> = if songs.is_empty() {
        vec![0xFF]
    } else {
        songs.iter().map(|t| t.track.filter(|&n| n != 0).unwrap_or(0xFF)).collect()
    };
    write!(table, "\nsong_msu:\n    .byte {}", bytes_list(tracks)).unwrap();
    // And each map's own song. Outside bank 0: it is read once per teleport.
    let per_map = if emit.map_song.is_empty() { vec![0xFF] } else { emit.map_song.clone() };
    let mut map_song_table =
        format!(".block {}\nmap_song:\n      .byte {}", per_map.len(), bytes_list(per_map.iter().copied()));
    // And the music's sounds —six bytes: the pitch, SRCN, ADSR1, ADSR2 and
    // the release GAIN—, those of every song in one table and where each
    // one's start. In a single bank, because the 65816 reaches them with a
    // sixteen-bit index that does not cross banks.
    let (mut body, mut bases) = (Vec::new(), Vec::new());
    for t in songs {
        bases.push(body.len());
        for sound in &t.sounds {
            body.extend_from_slice(sound);
        }
    }
    if body.len() > 0x8000 {
        return Err(Bad::answer(format!("the music's sounds go over one bank: {} B", body.len())));
    }
    let bases = if bases.is_empty() { vec![0] } else { bases };
    let sounds_block = if body.is_empty() { vec![0u8; 6] } else { body };
    write!(
        map_song_table,
        "\n.block {}\nsong_sounds:\n      .word {}\n{}",
        2 * bases.len(),
        bases.iter().map(|b| b.to_string()).collect::<Vec<_>>().join(", "),
        block("music_sounds", &sounds_block, true)
    )
    .unwrap();
    // And the sound effects: seven bytes per sound.
    let rows = if sounds.is_empty() { vec![(0xFF, 0, 0, 0, 0, 0xFF)] } else { sounds.clone() };
    let mut se_table = format!(".block {}\nsound_table:\n", 7 * rows.len())
        + &rows
            .iter()
            .map(|(srcn, pitch, left, right, frames, _)| {
                format!("    .byte ${srcn:02X}, <{pitch}, >{pitch}, {left}, {right}, <{frames}, >{frames}")
            })
            .collect::<Vec<_>>()
            .join("\n");
    // And which sound effect each row is, separately so as not to touch the
    // seven columns the ROM walks: the row's sample is a place several sound
    // effects share, and this says whether the one in the ARAM is its own.
    // And each sound effect's place, which is what the package uses to
    // upload it.
    write!(
        se_table,
        "\n.block {}\nsound_effect:\n      .byte {}",
        rows.len(),
        rows.iter().map(|r| format!("${:02X}", r.5)).collect::<Vec<_>>().join(", ")
    )
    .unwrap();
    let mut effect_place: Vec<usize> = music.effects.iter().map(|e| music.place[&e.name]).collect();
    if effect_place.is_empty() {
        effect_place.push(0xFF);
    }
    write!(
        se_table,
        "\n.block {}\neffect_place:\n     .byte {}",
        effect_place.len(),
        effect_place.iter().map(|l| format!("${l:02X}")).collect::<Vec<_>>().join(", ")
    )
    .unwrap();

    // The SPC700 directory, with all of them on the silence, and the silence
    // after it. It is the only thing uploaded at boot besides the driver.
    let n = (music_n + places).max(1);
    if n as i64 > bank::DIRECTORY_MAX {
        return Err(Bad::answer(format!("the directory has {n} entries and SRCN is one byte")));
    }
    if voices.len() - music_n > 0xFF {
        return Err(Bad::answer(format!(
            "there are {} sound effects and their number is one byte",
            voices.len() - music_n
        )));
    }
    if places > SE_PLACES_MAX {
        return Err(Bad::answer(format!(
            "the sound effects ask for {places} directory places and the ROM records \
             {SE_PLACES_MAX}: see FAR_EFFECT_IN"
        )));
    }
    let silence = SAMPLES_ADDR as usize + 4 * n;
    let data = silence + SILENCE.len();
    let mut directory: Vec<u8> = Vec::new();
    for _ in 0..n {
        for _ in 0..2 {
            directory.extend((silence as u16).to_le_bytes());
        }
    }
    directory.extend(SILENCE);
    // Each sample, on its own, and its row: the pointer, its length and
    // where it loops back to.
    let sample_blocks: Vec<String> = if voices.is_empty() {
        vec![block("sample_0", &SILENCE, false)]
    } else {
        voices.iter().enumerate().map(|(i, (d, _))| block(&format!("sample_{i}"), d, true)).collect()
    };
    let rows_of: Vec<(usize, usize)> = if voices.is_empty() {
        vec![(SILENCE.len(), 0)]
    } else {
        voices.iter().map(|(d, l)| (d.len(), l * BLOCK_BYTES)).collect()
    };
    let sample_rows: Vec<String> = rows_of
        .iter()
        .enumerate()
        .map(|(i, (length, lp))| {
            format!(
                "    .byte <(sample_{i}), >(sample_{i}), ^(sample_{i}), <{length}, >{length}, <{lp}, >{lp}"
            )
        })
        .collect();
    // Which samples each song uses, and each map's package: two blocks with
    // an index of offsets in front, and each list terminated with $FF.
    let song_samples: Vec<Vec<Vec<u8>>> = if songs.is_empty() {
        vec![vec![vec![]]]
    } else {
        songs.iter().map(|t| Ok(vec![t.samples()?])).collect::<Result<_>>()?
    };
    let package_lists: Vec<Vec<Vec<u8>>> = if packages.is_empty() {
        vec![vec![vec![], vec![], vec![], vec![]]]
    } else {
        packages
            .iter()
            .map(|(t, m, s, a)| Ok(vec![as_bytes(t)?, as_bytes(m)?, as_bytes(s)?, as_bytes(a)?]))
            .collect::<Result<_>>()?
    };

    let names = songs
        .iter()
        .map(|t| if t.name.is_empty() { "no music" } else { t.name.as_str() })
        .collect::<Vec<_>>()
        .join(", ");
    let mut out = String::new();
    // The line after the first, with the "no music" in it, is data: the
    // tools that read the cartridge look for "; Songs: " to know which song
    // each index is.
    out.push_str("; Generated by tools/audio/snes_music.py. Do not edit.\n");
    writeln!(out, "; Songs: {}\n", if names.is_empty() { "none" } else { &names }).unwrap();
    // The paths in this text still say `rom/src/`, where the runtime lived:
    // what is emitted is not changed yet.
    write!(
        out,
        "; How many songs the cartridge carries and which one plays from boot.\n\
         ; The indices are those of `Songs` in events.py, that is, the ones\n\
         ; the PlayBGM bytecode already has emitted.\n\
         ; $FF in SONG_BOOT means 'the ROM boots silent': the song of the\n\
         ; map it boots in does not exist, so an event has to turn it on.\n\
         SONG_TOTAL       = {}\n\
         SONG_BOOT        = ${:02X}\n\
         ; And the title screen's, which comes from the LDB's `title_music`.\n\
         ; $FF means this ROM has no title screen.\n\
         SONG_TITLE       = ${:02X}\n\
         ; And the Game Over screen's —`gameover_music`— with its package,\n\
         ; which goes after all the others: the song alone. $FF and $FFFF\n\
         ; if this ROM has no such screen. See rom/src/game_over.s.\n\
         SONG_GAME_OVER   = ${:02X}\n\
         PACKAGE_GAME_OVER = ${:04X}\n\
         ; The master volume the song plays at and the two DSP registers it\n\
         ; goes in. `sdsp.py` emits them, since that is where they come\n\
         ; from: the stream already writes them at start, and a `FadeOutBGM`\n\
         ; writes them again lowering them. Writing them in rom/src/ too\n\
         ; would be two sides that can be wrong in the same way.\n\
         SONG_VOLUME      = ${:02X}\n\
         DSP_MVOL_L       = ${:02X}\n\
         DSP_MVOL_R       = ${:02X}\n\
         SPC_DRIVER_ADDR  = ${:04X}\n\
         SPC_DRIVER_SIZE  = {}\n\
         SPC_SAMPLES_ADDR = ${:04X}\n\
         SPC_SAMPLES_SIZE = {}\n\
         ; Samples go to the SPC700 in packages: see `package_load`.\n\
         ; The directory is at SPC_SAMPLES_ADDR, the silence after it, and\n\
         ; the samples are placed between ARAM_DATA and ARAM_END.\n\
         ; SAMPLES_N is the directory's entries: the music's, and from\n\
         ; SE_FIRST on the SE_PLACES the sound effects share.\n\
         ; Each sound effect has its number —EFFECTS_N in total, which is\n\
         ; what the package lists carry— and its `sample_table` row at\n\
         ; SE_FIRST plus that number. See `lugares_de_efectos`.\n\
         SAMPLES_N        = {}\n\
         SE_FIRST         = {}\n\
         SE_PLACES        = {}\n\
         EFFECTS_N        = {}\n\
         ARAM_SILENCE     = ${:04X}\n\
         ARAM_DATA        = ${:04X}\n\
         ARAM_END         = ${:04X}\n\
         PACKAGES_N       = {}\n\
         ; The sound effects: which voice they play on and how many entries\n\
         ; `sound_table` has. See `build_efectos`.\n\
         SE_VOICE         = {}\n\
         SE_BIT           = ${:02X}\n\
         SE_REG           = ${:02X}\n\
         SE2_BIT          = ${:02X}\n\
         SE2_REG          = ${:02X}\n\
         SOUNDS_N         = {}\n\n\
         ; Where each song's stream starts, split into three tables\n\
         ; because they are read with an index: they go in bank 0 like\n\
         ; everything the CPU walks with `lda tabla, x`.\n\
         .segment \"TABLES\"\n{}\n\n\
         .segment \"RODATA\"\n{}\n{}\n{}\n{}\n\
         .block {}\nsample_table:\n{}\n{}\n{}\n{}\n{}\n",
        songs.len(),
        emit.boot,
        emit.title,
        emit.game_over.0,
        emit.game_over.1,
        sdsp::master(),
        sdsp::MVOL_L,
        sdsp::MVOL_R,
        DRIVER_ADDR,
        driver.len(),
        SAMPLES_ADDR,
        directory.len(),
        n,
        music_n,
        places,
        voices.len() - music_n,
        silence,
        data,
        bank::ARAM_END,
        packages.len().max(1),
        SE_VOICE,
        1u32 << SE_VOICE,
        SE_VOICE as u32 * 16,
        1u32 << SE_VOICE2,
        SE_VOICE2 as u32 * 16,
        emit.sounds.len(),
        table,
        se_table,
        map_song_table,
        block("spc_driver", driver, false),
        block("spc_samples", &directory, false),
        7 * sample_rows.len(),
        sample_rows.join("\n"),
        lists("song_samples", &song_samples),
        lists("packages", &package_lists),
        sample_blocks.join("\n"),
        labels.iter().zip(&streams).map(|(l, s)| block(l, s, false)).collect::<Vec<_>>().join("\n"),
    )
    .unwrap();
    Ok(out)
}

/// `musica.json`: what the MSU-1 tracks and the volume ceilings need from
/// each song —how long it lasts, the fingerprint of its mix, its track—.
pub fn songs_json(songs: &[Built]) -> serde_json::Value {
    serde_json::json!({
        "temas": songs.iter().map(|t| serde_json::json!({
            "nombre": t.name,
            "largo": t.length(),
            "huella": t.fingerprint.clone().unwrap_or_default(),
            "pista": t.track,
        })).collect::<Vec<_>>()
    })
}
