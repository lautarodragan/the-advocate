//! The conversion, in order: what the game says, each map, the pages,
//! the screens, the pictures, the battle, and the emission, the patches and
//! the music last.

use crate::animations::{self, Animations};
use crate::bytecode;
use crate::compiler::{self, CompileMap, Compiler, Indices, CASE_VARIABLE, COMPARE_AT_LEAST, TEST_SWITCH};
use crate::emit;
use crate::fail::{Result, Stop};
use crate::fullscreen;
use crate::game::{Command, Game, GameMap};
use crate::maps::{self, Cartridge, MapInfo, PageRecord};
use crate::options::{case_map, Options};
use crate::pictures;
use crate::scan;
use crate::scene;
use crate::screens;
use crate::settings::Settings;
use crate::stage;
use crate::text::{hex, repr, unhex};
use rm2k_project::Project;
use rm2k_snes_events::codes::{TELEPORT, TIMER_OPERATION};
use rm2k_snes_bytecode::events::{OP_FLASH, OP_ROUTE};
use rm2k_snes_mapdata::{engine, record, vram};
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet};
use std::ffi::OsString;
use std::path::PathBuf;

/// How many block pairs the ROM's substitution table holds at once. It is
/// `SUB_MAX` in the runtime's `low_ram.s`, and it is written on both sides
/// on purpose: the converter has to be able to refuse **before** emitting a
/// map that does not fit. `test_substitutions.py` compares the two.
pub const SUB_MAX: usize = 8;

/// The commands of a test page, as written by hand: the command by its
/// name or its number, and only the fields that say something.
pub fn handwritten_commands(path: &std::path::Path) -> Result<Vec<Command>> {
    let text = std::fs::read_to_string(path).map_err(|e| crate::fail::io(path, e))?;
    let data: Value = serde_json::from_str(&text).map_err(|e| Stop::new(format!("{}: {e}", path.display())))?;
    let mut out = Vec::new();
    for c in data["event_commands"].as_array().cloned().unwrap_or_default() {
        let code = match &c["code"] {
            Value::String(name) => ditto::schema::EventCommandCode::from_json_name(name)
                .map(|c| c.to_i32())
                .ok_or_else(|| Stop::new(format!("{}: {name} is not a command", path.display())))?,
            other => other.as_i64().unwrap_or(0) as i32,
        };
        out.push(Command {
            code,
            indent: c.get("indent").and_then(Value::as_i64).unwrap_or(0) as i32,
            string: c.get("string").and_then(Value::as_str).unwrap_or("").to_string(),
            parameters: c
                .get("parameters")
                .and_then(Value::as_array)
                .map(|p| p.iter().map(|v| v.as_i64().unwrap_or(0) as i32).collect())
                .unwrap_or_default(),
        });
    }
    Ok(out)
}

/// Which party the test continues with after its page, if the page touches
/// it: the case's `ChangePartyMembers` applied to the cartridge's party.
fn page_party(commands: &[Command], party: &[i32]) -> Option<Vec<i32>> {
    let mut state = scan::PartyState::new(party);
    let mut touches = false;
    for cmd in commands {
        let p = &cmd.parameters;
        if cmd.code == rm2k_snes_events::codes::CHANGE_PARTY_MEMBERS && p.len() >= 3 && p[1] == scan::PARTY_FIXED_ID {
            state.change_party(p[0], p[2]);
            touches = true;
        }
    }
    touches.then_some(state.party)
}

fn int(v: &Value) -> i64 {
    v.as_i64().unwrap_or(0)
}

fn join<T: ToString>(items: impl IntoIterator<Item = T>, sep: &str) -> String {
    items.into_iter().map(|i| i.to_string()).collect::<Vec<_>>().join(sep)
}

pub fn run(options: Options) -> Result<()> {
    let project = Project::locate(options.project.as_deref())?;
    let settings = Settings { project: &project };
    let environment = options.environment.clone();
    let order = options.map_order();
    if !(0 <= options.start_index && (options.start_index as usize) < order.len()) {
        crate::stop!("--start-index {} but there are {} maps", options.start_index, order.len());
    }
    let start_index = options.start_index as usize;
    let output = match &options.output {
        Some(o) => rm2k_project::absolute(o),
        None => project.build()?.join("inc").join("mapdata.inc"),
    };
    let game_dir = environment.game()?.to_path_buf();
    let rtp_dir = environment.rtp()?.to_path_buf();

    // The cases: each one's page, and the map where it runs.
    let mut cases: Vec<(String, Vec<Command>, i32)> = Vec::new();
    for file in &options.case_files {
        let commands = handwritten_commands(std::path::Path::new(file))?;
        let run_map = case_map(file, &commands, &order, start_index)?;
        cases.push((file.clone(), commands, run_map));
    }
    let file_commands: Vec<Command> = cases.iter().flat_map(|(_, c, _)| c.iter().cloned()).collect();
    let case_pairs: Vec<(i32, Vec<Command>)> = cases.iter().map(|(_, c, m)| (*m, c.clone())).collect();

    let game = Game::read(&game_dir, &project)?;
    // The hero's graphic comes from the party: in RM2k the first of the
    // list gives it.
    let party: Vec<i32> = match &options.party {
        Some(p) if !p.is_empty() => p.clone(),
        _ => game.db.party.clone(),
    };
    game.db.leader(&party)?;

    let search_dirs = search_dirs(&game, &project, &rtp_dir)?;

    // The cartridge's maps, read once.
    let mut every: Vec<GameMap> = Vec::new();
    for id in &order {
        every.push(game.map(*id)?);
    }
    let every_refs: Vec<&GameMap> = every.iter().collect();

    // **The indices go before anything that compiles a page**: without the
    // variables' slots no `ControlVars` compiled in that pass, and the
    // actors a page adds were lost. The compiler answers both in its first
    // call: the whole game's indices and which pages of each map compile.
    let mut extra = BTreeSet::new();
    if cases.len() > 1 {
        // The one that picks the case. With a single one it isn't needed,
        // and that way that cartridge comes out the same as before `--case`.
        extra.insert(CASE_VARIABLE);
    }
    let compiler = Compiler::new(&game, &settings)?;
    let test_event_map = (!cases.is_empty()).then(|| order[start_index]);
    let scan_answer = compiler.scan(&order, &file_commands, &extra, test_event_map, &case_pairs)?;
    let indices = Indices::from_answer(&scan_answer);
    let changes = scan::party_changes(&every_refs, &scan_answer)?;
    let mut leaders = scan::possible_leaders(&changes, &party);
    // And those of the party each test page continues with: the test can
    // start with it in any map of the cartridge.
    for (_, commands, _) in &cases {
        if let Some(test_party) = page_party(commands, &party) {
            for actor in scan::possible_leaders(&changes, &test_party) {
                if !leaders.contains(&actor) {
                    leaders.push(actor);
                }
            }
        }
    }
    // Which maps carry the timer digits, which cost a sprite palette: the
    // ones the timer can be running in. With `--no-timer`, only the maps
    // where a case that touches it runs. A map without digits doesn't draw
    // them.
    let mut timer_maps: BTreeSet<i32> = cases
        .iter()
        .filter(|(_, commands, _)| commands.iter().any(|c| c.code == TIMER_OPERATION))
        .map(|(_, _, m)| *m)
        .collect();
    if !options.no_timer {
        let never: BTreeSet<i32> =
            project.ints(&["graphics", "timer_never_runs_in"])?.into_iter().map(|m| m as i32).collect();
        let counters: BTreeSet<i32> = compiler::counters(&settings)?
            .iter()
            .map(|c| int(&c["common_event"]) as i32)
            .collect();
        timer_maps.extend(scan::timer_reach(&every_refs, &scan_answer, &game.db.common_events, &never, &counters)?);
    }
    println!(
        "  the timer's digits go in {} of the {} maps: {}",
        timer_maps.len(),
        order.len(),
        join(&timer_maps, " ")
    );
    // If some map sets rain, all of them carry the drops.
    let with_rain = scan::has_rain(every_refs.iter().copied(), &file_commands);
    let per_character = maps::maps_per_character(&every_refs);

    let test_maps: BTreeSet<i32> = if cases.is_empty() {
        BTreeSet::from([order[start_index]])
    } else {
        cases.iter().map(|(_, _, m)| *m).collect()
    };
    let cartridge = Cartridge {
        game: &game,
        settings: &settings,
        scan: &scan_answer,
        order: order.clone(),
        start_index,
        has_cases: !cases.is_empty(),
        cases: case_pairs.clone(),
        test_graphics: options.test_graphic.clone(),
        test_maps: test_maps.clone(),
        leaders: leaders.clone(),
        timer_maps: timer_maps.clone(),
        with_rain,
        maps_per_character: per_character,
        search_dirs: search_dirs.clone(),
        common_substitutions: maps::common_substitutions(&game),
    };
    let mut animation_cache = Animations::new(&search_dirs, &game.dump);
    let mut prepared = Vec::new();
    for id in &order {
        prepared.push(maps::prepare(&cartridge, &mut animation_cache, *id)?);
    }
    let answers = maps::run_all(&cartridge, &prepared)?;
    let mut infos: Vec<MapInfo> = Vec::new();
    for (p, written) in prepared.into_iter().zip(answers) {
        infos.push(maps::map_info(&game, p, written)?);
    }
    // The big pictures, which the cartridge carries once whatever map shows
    // them.
    let bigs: Vec<&[pictures::Big]> = infos.iter().map(|m| m.big_pictures.as_slice()).collect();
    let (big_layers, big_tables) = pictures::number_big(&bigs);
    for (m, table) in infos.iter_mut().zip(big_tables) {
        m.big_table = table;
    }
    // Teleports are resolved when all the maps are there.
    let table_index: BTreeMap<i32, usize> = infos.iter().enumerate().map(|(n, m)| (m.id, n)).collect();
    for m in &infos {
        for (upper, old, new) in &m.missing_substitutions {
            // It doesn't stop the conversion: the page that asks for it
            // doesn't compile. But it is said, because from outside it
            // looks like an event that does nothing.
            println!(
                "  map {}: TileSubstitution {old} -> {new} on the {} layer: the block that would be \
                 needed can't be built. Either the new tile isn't drawn in any cell of the map, or \
                 one of the two is an upper tile without 'Above' and is baked into the background. \
                 The page doesn't compile.",
                m.id,
                if *upper { "upper" } else { "lower" }
            );
        }
    }

    // The actors that can be in the party when saving, to have their face
    // and their name in the cartridge. A superset on purpose.
    let members = scan::possible_members(every_refs.iter().copied(), &party, &file_commands);
    // The random encounters of each map, and the experience tables:
    // `rm2k-snes-battle`'s first call.
    let written = stage::run(
        "rm2k-snes-battle",
        "battle",
        "tables",
        &json!({
            "party": members,
            "maps": infos.iter().map(|m| json!({"id": m.id, "width": m.map.width, "height": m.map.height}))
                .collect::<Vec<_>>(),
            "encounter_steps": options.test_encounters,
            "tree_nodes": game.tree.added_nodes,
        }),
        &["--data".into(), game.dump.clone().into_os_string()],
    )?;
    let tables_answer = stage::json(&written, "battle.json")?;
    let encounters = tables_answer["encounters"].clone();
    let battle_tables = json!({
        "experience": stage::text(&written, "experience.inc")?,
        "slots": tables_answer["experience"]["slots"],
        "encounters": stage::text(&written, "encounters.inc")?,
    });
    if int(&encounters["records"]) != 0 {
        println!(
            "  random encounters: {} map(s), {} zone(s), {} troop(s)",
            int(&encounters["records"]),
            int(&encounters["zones"]),
            encounters["troops"].as_array().map_or(0, Vec::len)
        );
    }
    // Every page of the cartridge, compiled: `rm2k-snes-events`' second
    // call.
    let compile_maps: Vec<CompileMap> = infos
        .iter()
        .map(|m| CompileMap {
            id: m.id,
            names: compiler::names([&m.map]),
            substitution_table: m.substitution_table.clone(),
            pictures: m.pictures.as_ref().map(|(_, table, _)| table.clone()),
            big_table: m.big_table.clone(),
        })
        .collect();
    let test_graphics: BTreeMap<i32, Vec<(String, i32)>> = match &options.test_graphic {
        Some(graphics) if !graphics.is_empty() => test_maps.iter().map(|m| (*m, graphics.clone())).collect(),
        _ => BTreeMap::new(),
    };
    let compiled = compiler.compile(
        &compile_maps,
        &case_pairs,
        &file_commands,
        &extra,
        test_event_map,
        &test_graphics,
        &encounters["troops"],
    )?;
    let messages = unhex(compiled["messages"]["data"].as_str().unwrap_or(""));
    let message_count = int(&compiled["messages"]["count"]);
    let message_pairs = json!({"first": compiled["messages"]["pair_first"], "table": compiled["messages"]["pairs"]});
    let troops = scene::Troops {
        ids: compiled["troops"]["ids"]
            .as_array()
            .map(|a| a.iter().map(|v| int(v) as i32).collect())
            .unwrap_or_default(),
        backdrops: compiled["troops"]["backdrops"]
            .as_array()
            .map(|a| {
                a.iter()
                    .map(|e| (int(&e[0]) as i32, e[1].as_str().map(str::to_string)))
                    .collect()
            })
            .unwrap_or_default(),
    };
    if let Some(commons) = compiled.get("commons").filter(|c| !c.is_null() && c.as_object().is_some_and(|o| !o.is_empty())) {
        let bodies = commons["bodies"].as_array().cloned().unwrap_or_default();
        println!(
            "shared common events: {} bodies, {} bytes; automatic ones that run: {}; left out, not compiling: {}",
            bodies.len(),
            bodies.iter().map(|b| b[1].as_str().map_or(0, |s| s.len() / 2)).sum::<usize>(),
            join(
                commons["autostart"].as_array().cloned().unwrap_or_default().iter().map(|a| int(&bodies[int(&a[1]) as usize][0])),
                ", "
            ),
            {
                let left: Vec<String> =
                    commons["left_out"].as_array().cloned().unwrap_or_default().iter().map(|v| v.to_string()).collect();
                if left.is_empty() {
                    "none".to_string()
                } else {
                    left.join(", ")
                }
            }
        );
    }
    let mut test_code: Vec<Vec<u8>> = Vec::new();
    for (k, code) in compiled["cases"].as_array().cloned().unwrap_or_default().iter().enumerate() {
        match code.as_str() {
            None => crate::stop!("{}: the test page doesn't compile", cases[k].0),
            Some(hex) => test_code.push(unhex(hex)),
        }
    }

    let triggers = [
        engine::TRIGGER_ACTION as i64,
        engine::TRIGGER_TOUCH_HERO as i64,
        engine::TRIGGER_AUTOSTART as i64,
        engine::TRIGGER_PARALLEL as i64,
    ];
    for m in infos.iter_mut() {
        let entry = compiler::map_entry(&compiled, m.id)?.clone();
        // The pages of the map's events: their conditions, and the code of
        // the ones that can be run.
        let pages = maps::pages(&entry["pages"], m)?;
        // And which substitutions they asked for: the blocks their pairs
        // start from are the keys of the ROM's table. See `SUB_MAX`.
        let mut sub_keys = BTreeSet::new();
        let truthy = |v: &Value| v.as_bool().unwrap_or_else(|| int(v) != 0);
        for asked in entry["substitutions"].as_array().cloned().unwrap_or_default() {
            let upper = truthy(&asked[0]);
            let found = m.substitution_table.as_array().and_then(|t| {
                t.iter().find(|s| truthy(&s["upper"]) == upper && s["old"] == asked[1] && s["new"] == asked[2])
            });
            if let Some(pairs) = found.and_then(|s| s["pairs"].as_array()) {
                for pair in pairs {
                    sub_keys.insert(int(&pair[0]));
                }
            }
        }
        m.sub_keys = sub_keys;
        // One interpreter per event with some parallel page that compiles.
        // The ROM carries them in a fixed-cap list and **doesn't warn** if
        // it goes over, so the stop goes here.
        let with_parallel: BTreeSet<i64> = pages
            .iter()
            .filter(|p| p.trigger == engine::TRIGGER_PARALLEL as i64 && p.has_code)
            .map(|p| p.event)
            .collect();
        if with_parallel.len() > record::PARALLEL_MAX {
            crate::stop!(
                "map {} has {} events with a parallel page and {} fit: see PARALLEL_MAX",
                m.id,
                with_parallel.len(),
                record::PARALLEL_MAX
            );
        }
        if !with_parallel.is_empty() {
            println!("  map {}: {} event(s) with a parallel page", m.id, with_parallel.len());
        }
        // The graphics command 34 and `ChangeSpriteAssociation` carry by
        // index: the two passes have to have numbered them the same.
        let graphics: Vec<(String, i64)> = entry["graphics"]
            .as_array()
            .map(|a| a.iter().map(|g| (g[0].as_str().unwrap_or("").to_string(), int(&g[1]))).collect())
            .unwrap_or_default();
        if graphics != m.route_graphics {
            crate::stop!(
                "map {}: the two passes numbered the route graphics differently: {:?} against {:?}",
                m.id,
                graphics,
                m.route_graphics
            );
        }
        m.pages = pages;
        // And which maps outside the ROM the ones that don't compile point
        // to: a `Teleport` to a map that didn't make it cuts the whole page,
        // and it is the one reason fixed from outside.
        let mut outside_of = BTreeSet::new();
        let mut how_many = 0;
        for page in &m.pages {
            if page.has_code || !triggers.contains(&page.trigger) || page.test {
                continue;
            }
            let event = &m.map.events[page.event as usize];
            let missing: BTreeSet<i32> = event.pages[page.page as usize]
                .commands
                .iter()
                .filter(|c| c.code == TELEPORT && !c.parameters.is_empty() && !table_index.contains_key(&c.parameters[0]))
                .map(|c| c.parameters[0])
                .collect();
            if !missing.is_empty() {
                outside_of.extend(missing);
                how_many += 1;
            }
        }
        if !outside_of.is_empty() {
            println!(
                "  map {}: {how_many} of those {} because of a teleport to a map that didn't make it into the ROM: {}",
                m.id,
                if how_many == 1 { "doesn't compile" } else { "don't compile" },
                join(&outside_of, ", ")
            );
        }
        // Debts are warned about: a page accepted without doing everything
        // it asks for is a difference from the original game.
        for code in entry["debts"].as_array().cloned().unwrap_or_default() {
            let code = int(&code) as i32;
            let name = ditto::schema::EventCommandCode::from_i32(code)
                .json_name()
                .map_or_else(|| code.to_string(), str::to_string);
            println!(
                "  map {}: WARNING, a page uses {name} and the ROM doesn't do it; see ACCEPTED_UNDONE in tools/rm2k-snes/events",
                m.id
            );
        }
    }

    // The second round: with the pages of all the cases compiled, they are
    // put in the boot map and each map's block is built.
    let boot = order[start_index];
    for m in infos.iter_mut() {
        if !cases.is_empty() && m.id == boot {
            // The test pages, only in the map the ROM boots in, at **index
            // 0** —the empty event put first—: the ROM walks the events from
            // lowest to highest, and they run before the game's. **One page
            // per case**, and page k asks for `CASE_VARIABLE` to be at least
            // k; and one that turns it off, which asks for `TEST_SWITCH` and
            // has no code.
            for (k, code) in test_code.iter().enumerate() {
                let variable = if k > 0 {
                    json!([indices.variable_slot(CASE_VARIABLE as i64)?, COMPARE_AT_LEAST, k])
                } else {
                    Value::Null
                };
                m.pages.push(test_page(k as i64, 0, variable, code.clone()));
            }
            m.pages.push(test_page(cases.len() as i64, TEST_SWITCH as i64, Value::Null, Vec::new()));
        }
        let mut code = Vec::new();
        for page in m.pages.iter_mut() {
            page.offset = code.len();
            code.extend_from_slice(&page.code);
            // And the commands of its own route, behind, one byte per
            // command.
            if let Some(own) = &page.own_route {
                page.route_offset = code.len();
                for order in own["commands"].as_array().cloned().unwrap_or_default() {
                    code.push(int(&order) as u8);
                }
            }
        }
        // What each page of the events that change graphic draws: where
        // its poses are in the sprite bank —`page_oam` in the emission—.
        for page in m.pages.iter_mut() {
            let continues = m.changing.contains(&page.event);
            if !continues && !m.appearing.contains(&page.event) {
                continue;
            }
            let Some(graphic) = &page.graphic else { continue };
            if m.outside.get(&page.event).is_some_and(|o| o.contains(&(graphic.0.clone(), graphic.1))) {
                continue;
            }
            let (mut block, mut palette) = (Value::Null, json!(0));
            if continues {
                // The one that only appears goes without a block: its own
                // row points at its slot of twelve poses.
                let (b, p) = match m.shared.get(&page.event) {
                    Some(shared) => shared.clone(),
                    None => m
                        .where_
                        .get(graphic)
                        .cloned()
                        .ok_or_else(|| Stop::new(format!("map {}: {graphic:?} is not in the sprite bank", m.id)))?,
                };
                block = b;
                palette = p;
            }
            page.draws = Some(json!({"block": block, "palette": palette, "pose": graphic.2, "tile_pass": page.tile_pass}));
        }
        m.evcode = code;
        // The ROM's substitution table has a fixed cap and **doesn't warn**
        // if it goes over.
        if m.sub_keys.len() > SUB_MAX {
            crate::stop!(
                "map {} substitutes {} distinct blocks and the RAM table carries {SUB_MAX}: see SUB_MAX",
                m.id,
                m.sub_keys.len()
            );
        }
        // How many distinct events this map can end up sending walking: a
        // route that finds no room is discarded **without saying
        // anything**. The pages that **run** here: the map's and those of
        // the cases that jump to it.
        let mut run_here: Vec<&[u8]> = m.pages.iter().filter(|p| p.has_code && !p.test).map(|p| p.code.as_slice()).collect();
        for (k, (_, _, run_map)) in cases.iter().enumerate() {
            if *run_map == m.id {
                run_here.push(&test_code[k]);
            }
        }
        let mut targets = BTreeSet::new();
        for code in &run_here {
            for i in bytecode::walk(code)? {
                if code[i] == OP_ROUTE && bytecode::at(code, i + 1) != 0 {
                    targets.insert(code[i + 1]);
                }
            }
        }
        // And that nobody flashes someone who shares a graphic with another:
        // on the console the flash is done on the character's palette, so
        // two that share a graphic would flash together. This covers what
        // the compiler can't see, which is the hero's: which graphic it has
        // depends on the party.
        let mut graphics: BTreeMap<(String, i64), usize> = BTreeMap::new();
        for npc in m.npcs.as_array().cloned().unwrap_or_default() {
            *graphics.entry((npc["charset"].as_str().unwrap_or("").to_string(), int(&npc["index"]))).or_insert(0) += 1;
        }
        for actor in &leaders {
            let a = game.db.actor(*actor)?;
            *graphics.entry((a.character_name.clone(), a.character_index as i64)).or_insert(0) += 1;
        }
        for code in &run_here {
            for i in bytecode::walk(code)? {
                if code[i] != OP_FLASH || bytecode::at(code, i + 1) != 0 {
                    continue;
                }
                for actor in &leaders {
                    let a = game.db.actor(*actor)?;
                    if graphics.get(&(a.character_name.clone(), a.character_index as i64)).copied().unwrap_or(0) > 1 {
                        crate::stop!(
                            "map {}: a page makes the hero flash, and actor {actor} is drawn with {}[{}], \
                             which an NPC of the map also uses. On the console they share a palette and \
                             both would flash",
                            m.id,
                            a.character_name,
                            a.character_index
                        );
                    }
                }
            }
        }
        if targets.len() > record::ROUTE_EV_MAX {
            crate::stop!(
                "map {}: its pages send {} distinct events walking and the ROM has {} route slots",
                m.id,
                targets.len(),
                record::ROUTE_EV_MAX
            );
        }
        let runnable = m.pages.iter().filter(|p| p.has_code).count();
        if !m.pages.is_empty() {
            println!("  map {}: {} automatic event page(s), {} runnable", m.id, m.pages.len(), runnable);
        }
    }

    // The screens, all at once. And the items that can be in the
    // inventory, to carry their name and their description; the ones the
    // enemies of the cartridge's troops drop too. The menu bank's letters
    // are those of the medicines of the pages' items alone.
    let items_rom = scan::possible_items(every_refs.iter().copied(), &members, &game.db, &file_commands);
    let mut items_all: BTreeSet<i32> = items_rom.iter().copied().collect();
    items_all.extend(scan::drop_items(&game.db, &troops.ids));
    let items_all: Vec<i32> = items_all.into_iter().collect();
    let screens_answer = screens::convert(&game, &members, &items_all, &items_rom, !options.no_title)?;
    let w = &screens_answer["window"];
    println!(
        "  message window: {} fixed tiles + {} of text, {} colors; font {} B, {} text box(es) in {} B",
        w["tiles"].as_str().map_or(0, |s| s.len() / 2) / 32,
        w["background"].as_str().map_or(0, |s| s.len() / 2) / 32,
        w["cgram"].as_array().map_or(0, |c| c.iter().filter(|v| int(v) != 0).count()),
        w["font"].as_str().map_or(0, |s| s.len() / 2),
        message_count,
        messages.len()
    );
    for line in screens_answer["says"].as_array().cloned().unwrap_or_default() {
        println!("{}", line.as_str().unwrap_or(""));
    }
    vram::check_splits().map_err(|e| Stop::new(e.message().to_string()))?;
    let s = &screens_answer["slots"];
    let slot_tiles = s["tiles"].as_array().map_or(0, Vec::len);
    let headers = s["headers"].as_array().cloned().unwrap_or_default();
    let mut faces: Vec<i64> = s["faces"]
        .as_object()
        .map(|f| f.keys().map(|k| k.parse().unwrap_or(0)).collect())
        .unwrap_or_default();
    faces.sort();
    let face_names: Vec<String> = faces
        .iter()
        .map(|a| format!("{a} {}", game.db.actors.get(&(*a as i32)).map_or("", |x| x.name.as_str())))
        .collect();
    println!(
        "  slots screen: {}, {} 4bpp tiles ({} B) + {} palettes, {} B of cells; {} actors with a face: {}",
        vram::SLOTS,
        slot_tiles,
        slot_tiles * 32,
        s["palettes"].as_array().map_or(0, Vec::len),
        (headers.len() * headers.first().and_then(Value::as_array).map_or(0, Vec::len)
            + vram::SLOTS as usize * 4 * s["rows"][0][0][0].as_array().map_or(0, Vec::len))
            * 2,
        faces.len(),
        if face_names.is_empty() { "none".to_string() } else { face_names.join(", ") }
    );
    let mut title_screen = None;
    if !screens_answer["title"].is_null() {
        let t = &screens_answer["title"];
        let name = &game.db.title_name;
        let picture = game.game_dir.join("Title").join(format!("{name}.png"));
        let texts: Vec<String> =
            t["texts"].as_array().cloned().unwrap_or_default().iter().map(|v| v.as_str().unwrap_or("").to_string()).collect();
        let menu_tiles = t["tiles"].as_array().map_or(0, Vec::len);
        let menu_palette: Vec<[u8; 3]> = t["palette"]
            .as_array()
            .cloned()
            .unwrap_or_default()
            .iter()
            .map(|c| [int(&c[0]) as u8, int(&c[1]) as u8, int(&c[2]) as u8])
            .collect();
        let menu_maps = t["tilemaps"].as_array().map_or(0, Vec::len);
        // The image, compressed like the Game Over one, and with the menu's
        // colours below its own in the same stream: the whole CGRAM at
        // once, the menu's palette at the bottom because a 4-bit BG only
        // reaches those.
        let mut below = menu_palette.clone();
        while (below.len() as i64) < fullscreen::MENU_CGRAM {
            below.push([0, 0, 0]);
        }
        let screen = fullscreen::compressed(&picture, fullscreen::MENU_CGRAM, fullscreen::COLORS, &below)?;
        println!(
            "  title screen {}: {} 8bpp tiles + {} colors, {} B in an LZ2 stream of {} B",
            repr(name),
            screen.tiles,
            screen.colors - below.len(),
            screen.raw,
            screen.stream.len()
        );
        println!(
            "    menu ({}): {} 4bpp tiles ({} B) + {} colors, {} tilemap(s)",
            texts.iter().map(|t| repr(t)).collect::<Vec<_>>().join(", "),
            menu_tiles,
            menu_tiles * 32,
            menu_palette.len(),
            menu_maps
        );
        title_screen = Some(screen);
    }
    // The Game Over screen: the image the LDB's `System` names, in the
    // game's or the RTP's `GameOver/` —as RM2k looks for it—, compressed.
    let mut game_over = None;
    let gameover_name = &game.db.gameover_name;
    let path = crate::resources::find(&[&game.game_dir, &rtp_dir], "GameOver", gameover_name, &[".png", ".bmp"]);
    if let (false, Some(path)) = (gameover_name.is_empty(), path) {
        let screen = fullscreen::compressed(&path, 0, 256, &[])?;
        println!(
            "  Game Over screen {}: {} 8bpp tiles + {} colors, {} B in an LZ2 stream of {} B",
            repr(&path.file_name().unwrap().to_string_lossy()),
            screen.tiles,
            screen.colors,
            screen.raw,
            screen.stream.len()
        );
        game_over = Some(screen);
    }
    // The battle animations the already emitted bytecode shows: their
    // prerendered frames go to the cartridge.
    let shown = animations::shown(infos.iter().flat_map(|m| m.pages.iter().map(|p| p.code.as_slice())))?;
    let shown: Vec<i32> = shown.into_iter().collect();
    let animations: BTreeMap<i32, animations::Info> = animation_cache
        .by_numbers(&game, &shown)?
        .into_iter()
        .filter_map(|(n, info)| info.map(|i| (n, i)))
        .collect();
    for (number, info) in &animations {
        let r = animations::report(info);
        println!(
            "  animation {number}: {} frames of {}x{}, shrunk from {}x{} to {}%, {} colors, {} B",
            r.frames, r.size.0, r.size.1, r.original.0, r.original.1, r.percent, r.colors, r.bytes
        );
    }
    // The backdrops and the battlers the cartridge's battles ask for,
    // each one once.
    let scenes = scene::rom_scene(&game, &settings, &rtp_dir, &troops, &infos, &encounters)?;
    for b in &scenes.backdrops {
        let (rom_tiles, rom_colors) = scene::fallback_bytes(&b.light);
        let (msu_tiles, msu_colors) = &scenes.quality[b.number];
        println!(
            "  battle backdrop {} {}: {}x{}, {} tiles from CGRAM entry {}; in the ROM {}x{} at 4bpp and {} colors ({} B), in the .msu 8bpp and {} colors ({} B)",
            b.number,
            repr(&b.name),
            scene::WIDTH,
            scene::HEIGHT,
            scene::TILES,
            scene::CGRAM_BASE,
            scene::FALLBACK_WIDTH,
            scene::FALLBACK_HEIGHT,
            b.light["palette"].as_array().map_or(0, Vec::len),
            rom_tiles.len() + rom_colors.len(),
            scene::COLORS,
            msu_tiles.len() + msu_colors.len()
        );
    }
    let in_rom: BTreeSet<usize> = scenes.backdrops.iter().map(|b| b.number).collect();
    let outside: Vec<usize> = (0..scenes.game.len()).filter(|k| !in_rom.contains(k)).collect();
    if !outside.is_empty() && !scenes.backdrops.is_empty() {
        println!(
            "  battle backdrops only in the .msu, which without MSU-1 fall back to {}: {}",
            repr(&scenes.backdrops[scenes.fallback_of[outside[0]]].name),
            outside.iter().map(|k| format!("{k} {}", scenes.game[*k])).collect::<Vec<_>>().join(", ")
        );
    }
    for b in &scenes.battlers {
        println!("{}", scene::battler_report(b));
    }
    // The event pages of the troops some battle of the cartridge asks for.
    let tp = &compiled["troop_pages"];
    println!(
        "  troop pages: {} of {} in {} distinct body(ies), {} B of code and {} B in {} message(s)",
        int(&tp["pages"]) - int(&tp["left_out"]),
        int(&tp["pages"]),
        int(&tp["distinct"]),
        tp["code"].as_str().map_or(0, |s| s.len() / 2),
        tp["messages"].as_str().map_or(0, |s| s.len() / 2),
        int(&tp["message_count"])
    );
    // The battle's model, `rm2k-snes-battle`'s second call.
    let layout = screens::layout()?;
    let mut pairs: Vec<((i64, i64), i64)> = indices.skills.clone();
    pairs.sort_by_key(|(_, slot)| *slot);
    let written = stage::run(
        "rm2k-snes-battle",
        "battle",
        "model",
        &json!({
            "actors": members, "troops": troops.ids, "items": items_all,
            "skill_pairs": pairs.iter().map(|((a, h), _)| json!([a, h])).collect::<Vec<_>>(),
            "item_name_width": layout["ITEM_NAME_WIDTH"],
        }),
        &["--data".into(), game.dump.clone().into_os_string()],
    )?;
    let battle_model = stage::json(&written, "model.json")?;
    // The common events the menu runs on closing, by the switch that turns
    // them on.
    let party_codes = compiler::party_common_events(&compiled);
    let mut party_common: Vec<(i64, i64)> = indices.party_common_events.clone();
    party_common.sort();
    let mut party_common_json = Vec::new();
    for (switch, number) in party_common {
        let code = party_codes
            .get(&number)
            .ok_or_else(|| Stop::new(format!("common event {number} was not compiled")))?;
        party_common_json.push(json!([switch, number, code]));
    }
    let case_slot = if cases.len() > 1 { Some(indices.variable_slot(CASE_VARIABLE as i64)?) } else { None };
    let request = json!({
        "maps": infos.iter().map(emit::map_record).collect::<Vec<_>>(),
        "start": start_index,
        "hero_above": options.hero_above,
        "speed_keys": !options.no_speed_keys,
        "enemy_hp": options.enemy_hp,
        "party": party,
        // What the ROM says about itself, from the `[rom]` of the project
        // file: the header title and the save signature in SRAM.
        "rom": {
            "title": settings.ascii(&["rom", "title"], None, Some(TITLE_HEADER))?,
            "sram_signature": settings.ascii(&["rom", "sram_signature"], Some(4), None)?,
        },
        "screens": screens_answer,
        "messages": hex(&messages),
        "message_pairs": message_pairs,
        "title": title_screen.as_ref().map(fullscreen::Screen::request),
        "game_over": game_over.as_ref().map(fullscreen::Screen::request),
        "animations": animations::request(&animations),
        "troops": troops.ids,
        "battle_audio": compiled["battle_audio"],
        "scene": scene::request(&scenes, &troops.ids, &game.db),
        "battle_tables": battle_tables,
        "troop_pages": compiled["troop_pages"],
        "party_common": party_common_json,
        "commons": compiled.get("commons").cloned().unwrap_or(Value::Null),
        "battle_model": battle_model,
        // The compiler's indices: each variable's slot and each (actor,
        // skill) pair's bit.
        "variables": indices.variables.iter().map(|(v, s)| json!([v, s])).collect::<Vec<_>>(),
        "skill_pairs": indices.skills.iter().map(|((a, h), s)| json!([a, h, s])).collect::<Vec<_>>(),
        "items": items_all,
        "actors": members,
        "text_padding": options.text_padding,
        "case_slot": case_slot,
        // The big pictures' layers.
        "big_pictures": big_layers.iter().map(|l| json!({
            "top": l["top"], "rows": l["rows"], "center": l["center"], "half": l["half"],
            "wider": l["wider"], "tiles": l["tiles"], "tilemap": l["tilemap"], "palettes": l["palettes"],
        })).collect::<Vec<_>>(),
    });
    let emitted = emit::emit(&output, &request, &game.dump)?;
    println!(
        "{} map(s) -> {}, boots at {start_index} (map {})",
        infos.len(),
        output.display(),
        infos[start_index].id
    );
    let directory = output.parent().map(rm2k_project::absolute).unwrap_or_default();
    // What Adeleine decided, as images: to look at which colours were lost
    // and which palette each cell ended up in without building or running
    // the ROM.
    maps::write_adeleine(&directory.join("adeleine"), &infos)?;
    // And **what it decided to lose**, written down: which colour was
    // merged with which in each layer, at what size each battle animation
    // is drawn, and which fifteen colours each battler is reduced to. What
    // travels is the decision; the text it is written as is
    // `rm2k-snes-patches`'.
    let patches_request = json!({
        "maps": infos.iter().map(|m| json!({
            "id": m.id, "name": m.name, "colors": m.colors, "budget": m.budget,
            "background": m.merges_background, "above": m.merges_above,
        })).collect::<Vec<_>>(),
        "animations": animations.iter().map(|(number, info)| {
            let r = animations::report(info);
            let anim = &game.db.animations[number];
            json!({"number": number, "name": anim.name, "sheet": anim.sheet, "side": animations::BOX,
                   "size": [r.size.0, r.size.1], "original": [r.original.0, r.original.1], "frames": r.frames})
        }).collect::<Vec<_>>(),
        "battlers": scenes.battlers.iter().map(|b| json!({
            "key": b.key, "image": b.image, "hue": b.hue, "width": b.width, "height": b.height,
            "colors": b.colors, "palette": b.palette, "merges": b.merges,
        })).collect::<Vec<_>>(),
    });
    stage::hand_over("rm2k-snes-patches", "patches", &patches_request, &[directory.clone().into_os_string()], None)?;
    // And who asked for each one, which isn't versioned: what separates, in
    // the ROM that is played, what belongs to the game from what only
    // exists because of the suite.
    let uses = scene::patch_uses(&infos, &game)?;
    let uses_path = directory.join("parches").join("usos.json");
    std::fs::write(&uses_path, crate::pyjson::to_string(&uses)).map_err(|e| crate::fail::io(&uses_path, e))?;
    if !emitted.report.is_empty() {
        println!("material compressed and shared between maps:");
        for line in &emitted.report {
            println!("{line}");
        }
    }
    // The music comes from here and not from a separate recipe: emitting
    // them together is the only thing that guarantees both describe the
    // same ROM. What each map's package carries, whether the boot fits and
    // the `.msu` are `rm2k-snes-audio cartridge`'s.
    let msu = options.msu.clone().map(rm2k_project::absolute).unwrap_or_else(|| directory.join("datos.msu"));
    let mut flags: Vec<OsString> = vec![
        "--out".into(),
        directory.clone().into_os_string(),
        "--msu".into(),
        msu.into_os_string(),
        "--data".into(),
        game.dump.clone().into_os_string(),
        "--project".into(),
        project.directory().as_os_str().to_owned(),
    ];
    flags.extend(environment.as_flags(&["game_dir", "rtp_dir", "soundfont"]));
    stage::hand_over(
        "rm2k-snes-audio",
        "rm2k-snes-audio",
        &json!({
            "songs": compiled["songs"],
            "maps": infos.iter().map(|m| m.id).collect::<Vec<_>>(),
            "start": start_index,
            "title": !options.no_title,
            "game_over": game_over.is_some(),
            "decompress_frames": emitted.frames.get(start_index).cloned().unwrap_or(Value::Null),
            "measuring_headroom": options.measure_headroom,
            // The quality backdrops are the emission's bytes: the stage only
            // puts them in their place in the `.msu`.
            "backdrops": scenes.quality.iter().map(|(t, c)| json!([hex(t), hex(c)])).collect::<Vec<_>>(),
            "tree_nodes": game.tree.added_nodes,
        }),
        &flags,
        Some("cartridge"),
    )?;
    // The bank packing is not decided here: both files send everything to
    // RODATA, and `rm2k-snes-assemble` spreads it into banks.
    Ok(())
}

/// Where the pictures are looked for: the images of the ChipSets the
/// project adds go first, built now —see `chipsets`—, and then the suite's,
/// the game's and the RTP.
pub fn search_dirs(game: &Game, project: &Project, rtp_dir: &std::path::Path) -> Result<Vec<PathBuf>> {
    let mut dirs: Vec<PathBuf> = vec![rm2k_project::suite::root(), game.game_dir.clone(), rtp_dir.to_path_buf()];
    let built = project.build()?.join("parches-manual");
    crate::chipsets::build_images(game, &built, &dirs)?;
    dirs.insert(0, built);
    Ok(dirs)
}

/// The header title of a SNES ROM: 21 bytes, at `$FFC0`.
const TITLE_HEADER: usize = 21;

/// A test page of the boot map's event 0.
fn test_page(k: i64, switch_a: i64, variable: Value, code: Vec<u8>) -> PageRecord {
    PageRecord {
        event: 0,
        page: k,
        trigger: engine::TRIGGER_AUTOSTART as i64,
        switch_a: json!(switch_a),
        switch_b: json!(0),
        actor: json!(0),
        variable,
        item: json!(0),
        layer: json!(0),
        frequency: json!(engine::ROUTE_FREQUENCY),
        speed: json!(4),
        has_code: !code.is_empty(),
        code,
        own_route: None,
        graphic: None,
        tile_pass: None,
        turns: false,
        fixed_direction: false,
        test: true,
        offset: 0,
        route_offset: 0,
        draws: None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The cap is written on both sides, and has to be: the ROM **cannot
    /// warn** that it was exceeded, so the one that refuses a map that does
    /// not fit is the converter. One cannot be generated from the other
    /// —the BSS `.res` and the converter's cutoff share nothing—, so they
    /// are compared; and the table is two words per pair, keys and values in
    /// parallel arrays, which is how `cell_replaced` walks them.
    #[test]
    fn the_substitution_table_cap_is_the_runtime_s() {
        let path = rm2k_project::suite::runtime().join("low_ram.s");
        let source = std::fs::read_to_string(&path).unwrap();
        let line = |prefix: &str| {
            source
                .lines()
                .find(|l| l.starts_with(prefix))
                .unwrap_or_else(|| panic!("{} no longer says {prefix}", path.display()))
                .to_string()
        };
        assert_eq!(line("SUB_MAX ").split('=').nth(1).unwrap().trim(), SUB_MAX.to_string());
        assert!(line("sub_key:").contains(".res SUB_MAX * 2"));
        assert!(line("sub_value:").contains(".res SUB_MAX * 2"));
    }

    #[test]
    fn a_test_page_party_is_only_that_of_the_cases_that_touch_it() {
        let add = Command { code: 10330, indent: 0, string: String::new(), parameters: vec![0, 0, 11] };
        assert_eq!(page_party(&[add], &[10]), Some(vec![10, 11]));
        assert_eq!(page_party(&[], &[10]), None);
    }
}
