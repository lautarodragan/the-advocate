//! What the cartridge decided about a map, which the game's dump does not
//! say: the request, as the caller writes it —[`Asked`] for a whole map,
//! [`LayersAsked`] for its layers alone—, and what this stage makes of it,
//! [`MapRequest`] and [`LayersRequest`]. The converter builds an [`Asked`]
//! and this stage reads it back with serde, so a field renamed on one side
//! does not compile on the other; [`read`] reads the same types from a
//! request file.
//!
//! **The fields go in the order the converter wrote them by hand** when
//! the request was a `json!`: the request is part of the key the
//! converter caches the answer under, and a field moved is every answer
//! computed again once.

use crate::background::panorama::Way;
use crate::fail::{Bad, Result};
use crate::game::Game;
use crate::map::{MapRequest, PictureAsked};
use crate::map_pictures::MapPicture;
use crate::moves::ScannedPage;
use crate::sprites::character::Key;
use crate::sprites::extras::Image;
use crate::substitutions::Triple;
use serde::{Deserialize, Deserializer, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};
use std::path::{Path, PathBuf};

/// A request for one map's layers:
///
/// ```json
/// {"map": 7,
///  "map_files": {"11": "/…/Map0011.json"},
///  "chipset_files": {"53": "/…/0053.json"},
///  "baked": [[412, 10005]],
///  "window_colors": 13,
///  "panorama": {"layouts": [[3, 256, 384, 1, 576], [1, 256, 256, 128, 768]],
///               "baked_tiles": 544}}
/// ```
///
/// `baked` are the cells of the upper layer the caller painted a tile
/// into, as `[cell, tile id]`: the events it bakes into the map.
/// `window_colors` are the colour-memory entries the message window takes
/// after the backdrop, which the background starts after: the game's
/// System decides them, so the caller counts them —see
/// [`crate::background::layers::cgram_reserved`]—.
///
/// `panorama`, if it is there and not null, says the cartridge can show the
/// map's panorama, and gives the VRAM layouts it has for a map that does,
/// as `[mode, background, sprites, upper, panorama]` tiles —the
/// background's in 64-byte units—, and in `baked_tiles` the most
/// background tiles the others leave. Without it a panorama is not drawn and
/// the map is black where it would show, as it always was. With it, how
/// the map shows its panorama is decided here, from the map and the
/// panorama alone: see [`crate::background::panorama::Way`]. `"way"`, if
/// it is there, forces one by its name.
#[derive(Debug, Clone, Default)]
pub struct LayersRequest {
    pub map: i32,
    pub baked: Vec<(usize, i16)>,
    pub window_colors: usize,
    pub panorama: Option<PanoramaBudget>,
    /// If set, the background is drawn with at most this many tiles, the
    /// cells that look most alike fused: see [`crate::background::fuse`].
    pub fuse_tiles: Option<usize>,
    /// The decorative events painted into the lower layer: see
    /// [`crate::decor`]. Not from the request: the map's conversion picks
    /// them.
    pub decor: Vec<crate::decor::Decoration>,
    /// The `(lower, upper)` tile pairs the map's `TileSubstitution`s will
    /// need and the map does not draw: see `Drawn::extended`. Not from
    /// the request: the map's conversion works them out.
    pub extra: Vec<(i32, i32)>,
    /// Whether some of `extra` cannot be built out of halves of what the
    /// map draws —see `substitutions::beyond_halves`—: only then does a map
    /// on a layer of its own other than flattened convert with them. Drawn
    /// for nothing, they move the colours Adeleine merges and with them
    /// what is seen.
    pub extra_needed: bool,
    /// The cells whose tiles above the hero are drawn below, because no
    /// character can ever cover them: see [`crate::layers::below`]. Not
    /// from the request: the map's conversion works them out.
    pub below: Vec<usize>,
    /// The poses of the still events drawn into the background, each in a
    /// cell of its own below the map —see `Drawn::extended`—: the cell the
    /// event stands on, whose tiles that cell repeats, and the pose's 24x32
    /// drawing, painted over it. Not from the request: the map's
    /// conversion picks them, see [`crate::posed`]. With what the others
    /// draw past their cells onto it, in order: see [`crate::posed::cells`].
    pub posed: Vec<crate::posed::Cell>,
    /// What those draw past their cells, painted into the map over the
    /// decorations, back to front: see [`crate::posed::spills`].
    pub spills: Vec<(usize, rm2k_render::Picture)>,
    /// The still pieces painted into the map's panorama, with the ChipSet's
    /// layers folded in under and over them: see [`crate::pieces`]. Not from
    /// the request: the map's conversion picks them, and only for a map the
    /// project asks it of, whose panorama is fixed to it. `None` for every
    /// other map; an empty list still folds the layers.
    pub pieces: Option<Vec<crate::pieces::Piece>>,
}

/// A VRAM layout for a map that shows its panorama: the mode the map goes
/// in, and how many tiles it leaves each thing.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct PanoramaLayout {
    pub mode: u8,
    /// The background's, in 64-byte units: an 8-bit tile, or two 4-bit.
    pub background: usize,
    pub sprites: usize,
    pub above: usize,
    pub panorama: usize,
}

/// The layouts a panorama can get, in the order they are tried, and the
/// way the caller forces, if it does.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct PanoramaBudget {
    pub layouts: Vec<PanoramaLayout>,
    /// The most background tiles a map without a panorama layer can get,
    /// in 64-byte units: what a panorama baked into the background has.
    pub baked: usize,
    pub way: Option<crate::background::panorama::Way>,
    /// Whether a map whose panorama is the map itself may go painted: see
    /// `Way::Painted`. `painted` in the request, false if it is missing.
    pub painted: bool,
}

impl PanoramaBudget {
    /// The layouts for `mode`, in the order they are tried.
    pub fn of_mode(&self, mode: u8) -> impl Iterator<Item = &PanoramaLayout> {
        self.layouts.iter().filter(move |l| l.mode == mode)
    }
}

/// A request for a whole map:
///
/// ```json
/// {"map": 7, "map_files": {}, "dropped_events": {}, "walls": {},
///  "chipset_files": {}, "names": [[3, 1, "Ghost~horneado:7:4:5"]],
///  "test_event": false, "leaders": [10, 1],
///  "pages": [{"event": 2, "page": 0, "trigger": 0, "compiles": true,
///             "route_targets": [2], "route_graphics": [[2, 0]],
///             "route_turns": [], "own_route": false, "turns": true}],
///  "route_graphics": [["People1", 3]], "hero_graphics": [], "also_walk": [],
///  "decorative": false, "posed_stills": false, "baked_events_nudge": 0,
///  "test_commands": [], "timer": null, "map_pictures": [], "rain": false,
///  "sand": null, "picture": null, "battle_animation": false,
///  "singles": [["People1", 3]], "palette_weight": {"savept": 1},
///  "dither": "five_of_eight", "substitutions": [[false, 80, 81]],
///  "common_substitutions": [], "layouts": [[448, 448, 128], [480, 256, 128]],
///  "panorama": {"layouts": [[3, 256, 384, 1, 576]], "baked_tiles": 544,
///               "way": null},
///  "window_colors": 13}
/// ```
///
/// What a request leaves out is empty, nothing or no, but for the fields
/// without a default, which it has to say. What each one is for, in
/// [`MapRequest`]; how they become it, in [`Asked::request`].
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct Asked {
    pub map: i32,
    /// The project's maps and ChipSets over the dump's: see
    /// [`Game::map_files`] and [`Game::chipset_files`].
    pub map_files: BTreeMap<i32, PathBuf>,
    /// [`Game::dropped`], of the request's map alone.
    #[serde(default)]
    pub dropped_events: BTreeMap<i32, BTreeSet<i32>>,
    /// [`Game::walls`], of the request's map alone.
    #[serde(default)]
    pub walls: BTreeMap<i32, Vec<(usize, usize)>>,
    pub chipset_files: BTreeMap<i32, PathBuf>,
    /// `(event id, page id, name)`: [`MapRequest::names`].
    pub names: Vec<(i32, i32, String)>,
    pub test_event: bool,
    pub leaders: Vec<i32>,
    pub pages: Vec<ScannedPage>,
    pub route_graphics: Vec<Key>,
    #[serde(default)]
    pub hero_graphics: Vec<Key>,
    pub also_walk: BTreeSet<usize>,
    #[serde(default)]
    pub decorative: bool,
    /// [`MapRequest::posed`].
    #[serde(default)]
    pub posed_stills: bool,
    #[serde(default)]
    pub baked_events_nudge: i32,
    #[serde(default)]
    pub test_commands: Vec<(i32, Vec<i32>)>,
    pub timer: Option<PathBuf>,
    /// [`Game::map_pictures`].
    #[serde(default)]
    pub map_pictures: Vec<MapPicture>,
    pub rain: bool,
    #[serde(default)]
    pub sand: Option<bool>,
    pub picture: Option<Picture>,
    pub battle_animation: bool,
    pub singles: Vec<Key>,
    /// [`MapRequest::weights`].
    pub palette_weight: BTreeMap<String, i64>,
    pub dither: String,
    pub substitutions: Vec<Triple>,
    pub common_substitutions: Vec<Triple>,
    pub layouts: Vec<(usize, usize, usize)>,
    #[serde(default)]
    pub panorama: Option<Panorama>,
    pub window_colors: usize,
    #[serde(default, skip_serializing_if = "is_false")]
    pub painted_events: bool,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reach: Option<Reach>,
    /// [`MapRequest::lowers`]: yes if it does not say, as a request from
    /// before 2026-11-18, which sent `reach` only to lower.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reach_lowers: Option<bool>,
    /// [`MapRequest::boots_here`]: yes if it does not say.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub boots_here: Option<bool>,
    /// [`MapRequest::picture_own`]: missing is none, null is a map without
    /// pictures of its own.
    #[serde(
        default,
        skip_serializing_if = "Option::is_none",
        deserialize_with = "present"
    )]
    pub picture_own: Option<Option<Picture>>,
    /// [`Game::chipsets`]: a variant of the map, read with another ChipSet.
    #[serde(default, skip_serializing_if = "BTreeMap::is_empty")]
    pub chipsets: BTreeMap<i32, i32>,
}

/// A request's `picture`: the map's pictures already cut by whoever
/// decided them —the tiles they reserve from the base, and each one's 64
/// colour indices from there—, and how many sprite palettes they share.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Picture {
    pub name: String,
    pub objects: usize,
    pub tiles: usize,
    pub cells: Vec<(usize, Vec<u8>)>,
    /// One if it does not say; a request from before 2026-10-16 said
    /// `slots`, one palette each.
    #[serde(default = "one", alias = "slots")]
    pub palettes: usize,
}

/// A request's `panorama`: see [`LayersRequest`].
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Panorama {
    /// `(mode, background, sprites, upper, panorama)`: a [`PanoramaLayout`].
    pub layouts: Vec<(u8, usize, usize, usize, usize)>,
    pub baked_tiles: usize,
    #[serde(default)]
    pub way: Option<Way>,
    #[serde(default, skip_serializing_if = "is_false")]
    pub painted: bool,
}

/// A request for one map's layers: see [`LayersRequest`].
#[derive(Debug, Clone, Default, Deserialize)]
pub struct LayersAsked {
    pub map: i32,
    pub map_files: BTreeMap<i32, PathBuf>,
    pub chipset_files: BTreeMap<i32, PathBuf>,
    #[serde(default)]
    pub dropped_events: BTreeMap<i32, BTreeSet<i32>>,
    #[serde(default)]
    pub walls: BTreeMap<i32, Vec<(usize, usize)>>,
    #[serde(default)]
    pub map_pictures: Vec<MapPicture>,
    #[serde(default)]
    pub chipsets: BTreeMap<i32, i32>,
    pub baked: Vec<(usize, i16)>,
    pub window_colors: usize,
    #[serde(default)]
    pub panorama: Option<Panorama>,
    #[serde(default)]
    pub fuse_tiles: Option<usize>,
}

fn is_false(b: &bool) -> bool {
    !*b
}

fn one() -> usize {
    1
}

/// A field that is there, null included, as `Some`: serde's own takes null
/// for missing.
fn present<'de, D, T>(d: D) -> std::result::Result<Option<T>, D::Error>
where
    D: Deserializer<'de>,
    T: Deserialize<'de>,
{
    T::deserialize(d).map(Some)
}

/// `T` out of the request `data`, with `whose` starting what is wrong.
pub fn typed<T: serde::de::DeserializeOwned>(data: &Value, whose: &str) -> Result<T> {
    T::deserialize(data).map_err(|e| Bad::answer(format!("{whose}: {e}")))
}

/// Reads a request file.
pub fn read(path: &Path) -> Result<(Value, String)> {
    let whose = path.display().to_string();
    let text = std::fs::read_to_string(path).map_err(|e| Bad::usage(format!("{whose}: {e}")))?;
    let data = serde_json::from_str(&text).map_err(|e| Bad::answer(format!("{whose}: {e}")))?;
    Ok((data, whose))
}

impl Panorama {
    fn budget(&self, whose: &str) -> Result<PanoramaBudget> {
        let layouts = self
            .layouts
            .iter()
            .map(|&(mode, background, sprites, above, panorama)| {
                if mode != 1 && mode != 3 && mode != 4 {
                    return Err(Bad::answer(format!(
                        "{whose}: a panorama layout's mode is {mode}"
                    )));
                }
                Ok(PanoramaLayout {
                    mode,
                    background,
                    sprites,
                    above,
                    panorama,
                })
            })
            .collect::<Result<_>>()?;
        Ok(PanoramaBudget {
            layouts,
            baked: self.baked_tiles,
            way: self.way,
            painted: self.painted,
        })
    }
}

fn budget(p: &Option<Panorama>, whose: &str) -> Result<Option<PanoramaBudget>> {
    p.as_ref().map(|p| p.budget(whose)).transpose()
}

impl Picture {
    fn asked(&self, whose: &str) -> Result<PictureAsked> {
        let cells = self
            .cells
            .iter()
            .map(|(tile, values)| {
                if values.len() != 64 {
                    return Err(Bad::answer(format!(
                        "{whose}: picture tile {tile} has {} colours, not 64",
                        values.len()
                    )));
                }
                let mut cell = [[0u8; 8]; 8];
                for (i, &v) in values.iter().enumerate() {
                    cell[i / 8][i % 8] = v;
                }
                Ok((*tile, cell))
            })
            .collect::<Result<_>>()?;
        Ok(PictureAsked {
            name: self.name.clone(),
            objects: self.objects,
            image: Image {
                tiles: self.tiles,
                cells,
            },
            palettes: self.palettes,
        })
    }
}

impl LayersAsked {
    /// The game in `data`, its pictures looked up in `search_dirs`, with
    /// the project's files the request names over the dump's.
    pub fn game(&self, data: &Path, search_dirs: &[PathBuf]) -> Game {
        Game {
            data: data.to_path_buf(),
            search_dirs: search_dirs.to_vec(),
            map_files: self.map_files.clone(),
            chipset_files: self.chipset_files.clone(),
            dropped: self.dropped_events.clone(),
            walls: self.walls.clone(),
            map_pictures: self.map_pictures.clone(),
            chipsets: self.chipsets.clone(),
        }
    }

    pub fn request(&self, whose: &str) -> Result<LayersRequest> {
        Ok(LayersRequest {
            map: self.map,
            baked: self.baked.clone(),
            window_colors: self.window_colors,
            panorama: budget(&self.panorama, whose)?,
            fuse_tiles: self.fuse_tiles,
            ..LayersRequest::default()
        })
    }
}

impl Asked {
    /// [`LayersAsked::game`], with this request's files.
    pub fn game(&self, data: &Path, search_dirs: &[PathBuf]) -> Game {
        Game {
            data: data.to_path_buf(),
            search_dirs: search_dirs.to_vec(),
            map_files: self.map_files.clone(),
            chipset_files: self.chipset_files.clone(),
            dropped: self.dropped_events.clone(),
            walls: self.walls.clone(),
            map_pictures: self.map_pictures.clone(),
            chipsets: self.chipsets.clone(),
        }
    }

    /// A request that only says some of what a whole map's says —the
    /// questions of [`crate::inspect`] need less—: what it leaves out is
    /// empty, nothing, or no.
    pub fn partial(data: &Value, whose: &str) -> Result<Asked> {
        let mut full = serde_json::json!({
            "map_files": {}, "chipset_files": {}, "names": [], "test_event": false,
            "leaders": [], "pages": [], "route_graphics": [], "also_walk": [],
            "timer": null, "rain": false, "picture": null,
            "battle_animation": false, "singles": [], "palette_weight": {},
            "dither": "five_of_eight", "substitutions": [], "common_substitutions": [],
            "layouts": [],
            // None of the questions converts the layers, the only thing the
            // window's colours are for.
            "window_colors": 0,
        });
        let given = data
            .as_object()
            .ok_or_else(|| Bad::answer(format!("{whose}: not an object")))?;
        for (k, v) in given {
            full[k] = v.clone();
        }
        typed(&full, whose)
    }

    /// What the conversion makes of the request.
    ///
    /// `layouts` are the VRAM layouts the cartridge can give a map, as
    /// `(background tiles, sprite tiles, upper tiles)`: a map that fits
    /// none of them with every still pose in VRAM is converted again with
    /// the still ones that are never on screen together sharing slots —see
    /// `crate::sprites::share`—. Empty, nothing is shared.
    ///
    /// `substitutions` are the `TileSubstitution`s the map's events and its
    /// test pages can run, as `(upper layer, old tile, new tile)`: their
    /// blocks are built. `common_substitutions` are the common events',
    /// which a `CallEvent` can bring into any map: they are only translated,
    /// with the blocks there are.
    ///
    /// `picture_own` is only there when the map carries copies of common
    /// events with pictures: the map's own pictures without theirs, which go
    /// in instead when theirs do not fit —see [`crate::map::convert`]—.
    pub fn request(&self, whose: &str) -> Result<MapRequest> {
        if self.baked_events_nudge < 0 {
            return Err(Bad::answer(format!(
                "{whose}: `baked_events_nudge` is {}, not a number of pixels",
                self.baked_events_nudge
            )));
        }
        let picture = |p: &Option<Picture>| p.as_ref().map(|p| p.asked(whose)).transpose();
        Ok(MapRequest {
            map: self.map,
            names: self
                .names
                .iter()
                .map(|(event, page, name)| ((*event, *page), name.clone()))
                .collect(),
            test_event: self.test_event,
            leaders: self.leaders.clone(),
            pages: self.pages.clone(),
            route_graphics: self.route_graphics.clone(),
            hero_graphics: self.hero_graphics.iter().cloned().collect(),
            also_walk: self.also_walk.clone(),
            timer: self.timer.clone(),
            rain: self.rain,
            sand: self.sand,
            picture: picture(&self.picture)?,
            picture_own: self.picture_own.as_ref().map(picture).transpose()?,
            battle_animation: self.battle_animation,
            singles: self.singles.iter().cloned().collect(),
            weights: self.palette_weight.clone(),
            dither: self.dither.clone(),
            substitutions: self.substitutions.clone(),
            common_substitutions: self.common_substitutions.clone(),
            layouts: self.layouts.clone(),
            window_colors: self.window_colors,
            panorama: budget(&self.panorama, whose)?,
            fuse_tiles: None,
            decorative: self.decorative,
            test_commands: self.test_commands.clone(),
            reach: self.reach.clone(),
            lowers: self.reach_lowers.unwrap_or(true),
            boots_here: self.boots_here.unwrap_or(true),
            posed: self.posed_stills,
            painted_events: self.painted_events,
            baked_events_nudge: self.baked_events_nudge,
        })
    }
}

/// What the caller knows of where characters can be on a map that the map
/// itself does not say, for `rm2k_rules::reach::covered`: where the hero
/// can arrive from outside its pages —`None`: anywhere—, whether also on
/// any cell one can step on, the vehicles that can carry him over water,
/// and the commands it runs there besides its pages' and the common
/// events'. With it the tiles above the hero no character can cover are
/// drawn below; without it, all of them above.
#[derive(Clone, Debug, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct Reach {
    pub entries: Option<Vec<(i32, i32)>>,
    /// See `rm2k_rules::reach::Outside::any_open`.
    #[serde(default)]
    pub any_open: bool,
    /// By name: `boat`, `ship`.
    #[serde(default)]
    pub vehicles: Vec<String>,
    /// As `(code, parameters)`.
    pub commands: Vec<(i32, Vec<i32>)>,
}

#[cfg(test)]
mod tests {
    use super::*;

    /// What the converter writes the stage reads back as it was: the
    /// fields it leaves out when they say nothing, and `picture_own`'s null,
    /// which is not its absence.
    #[test]
    fn a_request_reads_back_as_it_was_written() {
        let asked = Asked {
            map: 7,
            map_files: BTreeMap::from([(11, PathBuf::from("/maps/Map0011.json"))]),
            dropped_events: BTreeMap::from([(7, BTreeSet::from([6]))]),
            pages: vec![ScannedPage {
                event: 2,
                compiles: true,
                route_graphics: vec![(2, 0)],
                ..ScannedPage::default()
            }],
            map_pictures: vec![MapPicture {
                number: 3,
                name: "mist".to_string(),
                corner: (-8, 0),
                transparency: 50,
                tone: [100; 4],
                transparent_color: true,
                repeat: false,
                path: Some(PathBuf::from("/build/mist.png")),
            }],
            panorama: Some(Panorama {
                layouts: vec![(3, 256, 384, 1, 576)],
                baked_tiles: 544,
                way: Some(Way::Mode3),
                painted: true,
            }),
            reach: Some(Reach {
                entries: None,
                commands: vec![(11330, vec![5, 0])],
                ..Reach::default()
            }),
            boots_here: Some(false),
            picture_own: Some(None),
            chipsets: BTreeMap::from([(7, 2)]),
            ..Asked::default()
        };
        let text = serde_json::to_string(&asked).unwrap();
        let back: Asked = serde_json::from_str(&text).unwrap();
        assert_eq!(serde_json::to_string(&back).unwrap(), text);
        assert_eq!(back.picture_own, Some(None));
        let request = back.request("test").unwrap();
        assert!(!request.boots_here && request.lowers);
        assert!(matches!(request.picture_own, Some(None)));

        let plain = serde_json::to_value(Asked::default()).unwrap();
        for absent in [
            "painted_events",
            "reach",
            "reach_lowers",
            "boots_here",
            "picture_own",
            "chipsets",
        ] {
            assert!(plain.get(absent).is_none(), "{absent}");
        }
        let back: Asked = typed(&plain, "test").unwrap();
        assert_eq!(back.picture_own, None);
    }
}
