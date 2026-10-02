; ---------------------------------------------------------------------------
; The whole ROM, in a single assembly: this is the only thing `ca65` sees.
;
; The `.s` files next to this one **are not assembled on their own**: they are
; stretches of a single text, and `.include` pastes them in this order. Three
; things follow from that which you do not see by opening one of them:
;
; * **The order of the list is the order in the ROM.** Moving an `.include`,
;   or a `.proc` from one file to another, changes addresses and bytes;
;   splitting does not, because what reaches `ca65` is the same text. Until
;   2026-09-25 this was a single file of thirty-four thousand lines, and it
;   was split without changing a byte: that is why some files end with a
;   routine that belongs to another topic, and moving it is a ROM change that
;   gets verified on its own.
; * **Each file inherits the state of the previous one**: the `.a8`/`.i16`
;   widths and the segment. The `.segment` at the top of each one is written
;   for the reader, and it is the same one that was already in effect.
; * **Anonymous labels and the local labels of a `.proc` are resolved over the
;   pasted text**, so the script that did the split refused to cut inside a
;   block or between a `:+` and its `:`, and any new cut has to respect the
;   same.
;
; And two traps that hold for every file and have no line to live on:
;
; * **The width of A and of X/Y is state, and `ca65` believes it without
;   checking.** `.a8` and `.a16` do not describe: they dictate how each
;   immediate is emitted. A label that is jumped to from another width has to
;   declare its own —see `low` in `cells.s`—, or the immediate comes out as
;   two bytes, the CPU in 8-bit mode reads one, and the leftover `$00` runs as
;   a `BRK`. The ROM goes off the rails, and neither the diff nor the
;   pixel-by-pixel comparison sees it, and bisecting with `rts` does not work
;   because it unbalances the stack: if a ROM goes off the rails for no
;   apparent reason, look here first. The same goes for transfers between
;   different widths —`tax` with a 16-bit X, `ldx` from a one-byte variable—,
;   which drag in the neighboring byte. Since 2026-10-02 `goombario` follows
;   the widths on every path of each built cartridge and flags an immediate
;   assembled for the other one, and a declaration that is not what runs:
;   rom/pruebas/herramientas/test_linter.py. What it cannot decide it skips.
; * **There is no calling convention**: a `jsr` returns X and Y however suits
;   the routine. If an index has to survive the call —the interpreter's
;   bytecode cursor—, the caller saves it with `phy`, since it is the only one
;   that knows it is needed.
;
; **Where new code goes.** There are three code banks, each 32 KB, and
; `just espacio` says how much each has left:
;
; * `CODE`, bank 0, run from its fast mirror at `$80`: what runs every frame,
;   in the vblank or in `irq_music`, and whatever that calls with `jsr`. It
;   shares the bank with `TABLES`, so it is the hardest to make room in:
;   nothing goes here that can go elsewhere.
; * `FAR`, bank 1: entered with `jsl`, and only fast if the `jsl` carries
;   `+ FAST`.
; * `FAR2`, the low half of `$C0` —see `FAR2` in
;   tools/rm2k-snes/cartridge/src/banks.rs—: entered with `jsl` and
;   **without** `+ FAST`, because `$C0` is already fast and adding it gives
;   a wrong address. It is where new code goes by default: what is cold —a
;   screen, a map load, the battle— goes here or in `FAR`, whichever has
;   room. It opened on 2026-10-02, when bank 1 had 131 bytes left, with the
;   battle and the audio package.
;
; **A subsystem goes whole in one bank**: inside, its routines call each
; other with `jsr`, which does not change the program bank. Across banks it
; is `jsl` and `rtl`, and a routine that is also called with `jsr` from its
; own bank gets an entry `_l` —`jsr` it and `rtl`—, like `dsp_pair_l`. A
; `jmp (table, x)` reads its table from the program bank, and an `lda table,
; x` from the data bank, which is 0 —`$7E` in the battle—: a table in
; another bank goes with `f:`. **The assembler checks none of this**: a `jsr`
; to a routine in another bank assembles and links, and lands at the same
; address in the caller's bank. Since 2026-10-02 a test does, over each
; built cartridge: rom/pruebas/herramientas/test_saltos_entre_bancos.py
; reads the `.dbg` and flags every absolute `jsr`/`jmp`, jump table and
; absolute data access that lands somewhere other than the symbol it names.
; It assumes the data bank per file —its `BANCO_DE_DATOS`—, so code that
; runs with another one is listed there. A `jsl` to `FAR2` with `+ FAST`
; does not need it: `ld65` refuses it with a range error.
;
; What stays written here is what is not a subsystem: where the generated
; `.inc` files come in —the two bytecodes and the cartridge's data—. A new
; file is added to the list at the place it belongs in the ROM; the
; fingerprint in `tools/ensamblado/cartridges.py` already covers all of
; `tools/runtime/`.
; ---------------------------------------------------------------------------

.p816
.smart

.include "registers.s"
.include "far_ram.s"
; The two bytecodes this ROM reads, generated from tools/snes/protocol/: the events
; one, which `run_code` interprets, and the music stream, which
; `irq_music` reads. Each one is declared by a file that belongs neither to
; the side that emits the bytes nor to the side that reads them.
;
; The events one came inside mapdata.inc until 2026-09-14, which means an
; opcode's number arrived here inside a map's data; the music one was written
; by hand on both sides until 2026-09-15.
.include "event_opcodes.inc"
.include "music_opcodes.inc"

.include "musicdata.inc"
.include "mapdata.inc"

; The text area is eight cell rows, that is four lines of two rows each, and
; the composer's buffer is one line long. They go down here and not above
; because `WINDOW_TEXT_COLS` is emitted by the converter.
WINDOW_TEXT_LINES = WINDOW_TEXT_ROWS / 2
TEXT_BUF_BYTES = WINDOW_TEXT_COLS * 2 * 32

.include "zero_page.s"
.include "boot.s"
.include "enter_map.s"
.include "event_pages.s"
.include "interpreter.s"
.include "interpreter_message.s"
.include "interpreter_conditions.s"
.include "interpreter_gold_and_items.s"
.include "interpreter_shop_and_battle.s"
.include "interpreter_effects.s"
.include "interpreter_movement.s"
.include "interpreter_flashes.s"
.include "interpreter_timer.s"
.include "interpreter_music.s"
.include "interpreter_save.s"
.include "interpreter_variables.s"
.include "interpreter_party.s"
.include "interpreter_game_over.s"
.include "interpreter_map.s"
.include "interpreter_keys_and_waits.s"
.include "interpreter_camera_and_tint.s"
.include "interpreter_teleport.s"
.include "battle_fade.s"
.include "teleport_transition.s"
.include "variables.s"
.include "tint.s"
.include "party.s"
.include "hero_route.s"
.include "load_graphics.s"
.include "event_routes.s"
.include "action_key.s"
.include "character_flash.s"
.include "walking_events.s"
.include "save_game.s"
.include "title.s"
.include "slots.s"
.include "menu.s"
.include "text_screens.s"
.include "battle_bridges.s"
.include "rain.s"
.include "msu1.s"
.include "audio_package.s"
.include "sound_effects.s"
.include "items.s"
.include "animated_stills.s"
.include "picture.s"
.include "battle_animation.s"
.include "turn_toward_hero.s"
.include "npcs.s"
.include "cells.s"
.include "screen_flash.s"
.include "camera.s"
.include "map_window.s"
.include "messages.s"
.include "vblank.s"
.include "chipset_animation.s"
.include "hero.s"
.include "timer.s"
.include "oam.s"
.include "control.s"
.include "spc700.s"
.include "low_ram.s"
.include "music.s"
.include "bank1.s"
.include "level.s"
.include "medicine.s"
.include "equipment_from_events.s"
.include "battle.s"
.include "battle_items.s"
.include "battle_skills.s"
.include "game_over.s"
.include "battle_loop.s"
.include "battle_troop.s"
.include "battle_victory.s"
.include "battle_scene.s"
.include "battle_run.s"
.include "screen_bank.s"
.include "encounters.s"
.include "battle_animation_frames.s"
.include "decompress.s"
.include "equipment_screen.s"
.include "actor_choice.s"
.include "shop.s"
.include "msu_effects.s"
.include "remembered_place_and_song.s"
.include "bgm_level.s"
.include "interpreter_cells.s"
.include "far_npcs.s"
.include "menu_experience.s"
.include "end_game.s"
.include "counter.s"
.include "picture_far.s"
.include "big_picture.s"
.include "hero_speed_keys.s"
.include "message_letter.s"
.include "number_input.s"
.include "shared_poses.s"
.include "common_events.s"
.include "header.s"
