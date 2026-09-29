.segment "BSS"
; How many passes of the loop went by with the world frozen by a fade. The map
; animations —the ChipSet's and that of the ones that animate standing still—
; count `ticks` **minus** these, so they do not advance while the screen
; fades, and that is what easyrpg-player does: during a transition
; `Player::Update(false)` does not call `IncFrame`, and the `GetFrameCounter`
; that `tilemap_layer.cpp:288` looks at stays still. `ticks` cannot be
; stopped there: it is the fade's own clock and the harness's. Without counting
; them, the water came out of a teleport seventy ticks ahead in phase.
frozen_ticks: .res 2


; Two bits per event, instead of a queue. `FLAG_AUTO` says whether the event's
; active page is an autorun that compiled —the refresh redoes it— and
; `FLAG_WAIT` is EasyRPG's `waiting_execution`: who has a page waiting its
; turn, whether it was put there by the autorun sweep, the action button or a
; touch.
;
; They replace a queue of eight pointers that filled up and dropped. One bit
; per event cannot overflow or mark the same one twice, which is exactly what
; makes it possible to re-mark every frame. Both bits go in the same table and
; not in two: 128 more bytes did not fit in the 7680 of RAM.
ev_flags:     .res EV_MAX
waiting_n:  .res 1     ; how many are waiting, so as not to sweep 128 bytes for nothing
ev_running: .res 2     ; which event the running page belongs to, or $FFFF
only_auto:    .res 1     ; the short pass of `pick_autostart`
auto_n:       .res 1     ; how many events have an active autorun
refresh_frame: .res 1  ; a refresh in the middle of a command left the long pass
rp_ev_prev:    .res 2     ; the previous page's event, in the refresh
boots:    .res 1     ; budget of pages per frame; see STARTS_MAX
port0: .res 1

; What `flush_video` writes to INIDISP at the end of the vblank: the master
; brightness from 0 to BRILLO_MAX. Nobody else writes it, and the why is in
; `prender`. It goes in the BSS and not in the direct page because it is
; touched once per frame, in no tight loop —and the zero page is full—.
brightness:      .res 1

; `FadeOutBGM`: if one is running, how much volume is left —from 65535 down to
; zero— and how much it drops per frame. The converter emits the step; see
; `eventos.paso_de_fundido`.
bgm_fade: .res 1
bgm_level:   .res 2
bgm_step:    .res 2
dsp_value:   .res 1     ; scratch for the track's fade: see `bgm_fade_tick`

; The camera moved without the hero: `PanScreen`. Where it is and where it is
; going, both in 1/16 pixel and signed, and how far it moves per frame.
; `pan_px` and `pan_py` are the same already reduced to whole pixels, which is
; what `follow_camera` adds: it is computed once per frame in `pan_tick` and
; not on each use.
pan_x:      .res 2
pan_y:      .res 2
pan_dest_x: .res 2
pan_dest_y: .res 2
pan_step:   .res 2
pan_px:     .res 2
pan_py:     .res 2

; A teleport's fade. See `fade_tick`.
fade:      .res 1    ; whether one is running
fade_base: .res 1    ; the low byte of `ticks` when it started
fade_kind:  .res 1    ; what has to be done on the black frame, and is no longer
fade_map: .res 2    ; to which map, for the two cases that load
FADE_NOTHING   = 0      ; already done
; `FADE_DOOR` is the only one that **no path in the ROM asks for**: the
; harness writes it from outside —`Partida.ir_al_mapa`— to plant the game on
; any map, and that is why it wants the whole `enter_map`, with the jump
; budget restored, and not the path of a chained jump. It is called that
; because it was what a door asked for when doors had a table of their own;
; today they go through the interpreter and ask for `FADE_JUMP` like any
; other teleport. Deleting it takes away the tests' way of starting on a map
; that is not the cartridge's.
FADE_DOOR = 1      ; the harness's: `enter_map`, with its jump cap
FADE_JUMP  = 2      ; a Teleport to another map
FADE_SAME  = 3      ; a Teleport to the same one: just move the hero

; The hero's forced move route: the pointer to its first command, inside the
; bytecode, just like an event's. Until 2026-09-27 it was copied here, into a
; 32-byte buffer, and whatever did not fit was silently lost: the one for the
; race's bridge is 50 commands and the car stopped halfway, and with sounds
; inside move routes —which carry two bytes of operand— the cut could land in
; the middle of one. The bytecode lives in the ROM and is not going anywhere.
; It does not go in the direct page, which is where `lda [ptr], y` needs it,
; because there is no room left there: `hero_command` copies it to
; `route_ptr` to read.
hero_route:  .res 3
; The frequency of the move route set on the hero, and the one the OP_ROUTE
; being read carries. It is RM2k's stop counter: see `ruta_tras_paso`.
route_freq:    .res 1
route_freq_op: .res 1

; The message window. `msg_open` is whether one is on screen, and the other
; two are requests the main loop handles at the end of the frame, with the
; screen off: the tilemap cannot be written with the PPU drawing.
;
; They go here and not in the zero page because they are not touched in any
; tight loop, and the text compositor needs the zero page.
msg_open: .res 1

; Whose message is on screen: the parallel event that opened it, or $FF if the
; foreground opened it —or if there is none—. It is easyrpg's
; `_state.show_message`, which there is a field per interpreter and here one
; is enough because there is one message at a time. `op_message` writes it by
; copying `pair_ev`, which is $FF outside the parallel loop.
msg_owner:  .res 1

; The compositor's state. A message does not appear on the frame it is asked
; for: it is composed MSG_CHARS characters per pass of the loop, line by line,
; and only when it is whole does the HDMA get turned on.
;
; The per-pass budget is not an optimization but what keeps the game's pace:
; if a pass overran the frame, `wait_vblank` would catch the next one and the
; hero would walk at half speed.
msg_state:  .res 1     ; 0 idle, 1 composing, 2 ready
msg_line:   .res 1     ; which line is being built
msg_lines:  .res 1     ; how many the message has
msg_col:     .res 1     ; which character it is on
msg_length:   .res 1     ; how many the line has
msg_primed:  .res 1     ; whether the buffer already has the line's background
msg_upload:   .res 1     ; whether there is a line ready to upload to VRAM

; The line being composed: two rows of cells by 30 columns, in the console's
; tile format. The 48 extra bytes are so the last character's mask can write
; its second column without going out: it always writes zero there, but
; reading and writing outside the buffer would be stepping on someone else.
text_buf:   .res (VENTANA_TEXTO_COLS * 2 * 32 + 48)

; The window's two HDMA tables. They live in RAM because the first two entries
; carry this frame's camera; the last one, which is the window's, never
; changes.
;
;   hdma_sc    [127][BG2SC mapa] [17][BG2SC mapa] [80][BG2SC ventana] [0]
;   hdma_ofs   [127][hofs][vofs] [17][hofs][vofs] [80][0][WINDOW_VOFS] [0]
;
; The top 144 scanlines go in two stretches because an entry's line counter is
; 7 bits and does not reach 144.
hdma_sc:  .res 7
hdma_ofs: .res 16

; OAM is built in RAM and sent whole by DMA every frame. It is simpler than
; writing single entries, and it is what will be needed when there are NPCs.
; It is 128 objects of four bytes plus a small table of two bits per object.
oam:      .res 512
oam_high: .res 32

; The VRAM upload queue: what has to be uploaded in the coming vblank and
; cannot be uploaded now. Each entry is three bytes of source in the cartridge
; and two of destination in VRAM words, and what gets uploaded is always a
; pose: 512 bytes in four rows of 128, because a 32x32 object is four rows of
; the name grid. Up to VQ_PER_FRAME per vblank; the rest waits for the next,
; and whoever queued it learns it did not fit and asks again. See
; `vram_queue` and `vram_drain`.
VQ_MAX = 8
VQ_PER_FRAME = 5
VQ_STRIDE = 5
vq_n:      .res 1
vq:        .res VQ_MAX * VQ_STRIDE
vq_src:    .res 3
vq_dest:   .res 2
vq_done: .res 1
vq_rows:  .res 1
; The hero pose that is in VRAM, or $FF if whichever is due has to be uploaded.
hero_pose_vram: .res 1
hero_pose:     .res 1

; The map strips are built here outside the vblank and uploaded from here when
; the next one starts, just like OAM. Building them inside the vblank would not
; fit, and writing them to VRAM outside it would show them half done.
;
; A column is the window's 32 cells; a row, the 64. They are indexed by slot,
; not by map cell: that way the buffer's order is exactly the order VRAM wants
; them in and each strip comes out of one DMA.
; The four in a row and in this order: `clear_tilemaps` clears them in one
; go, and `push_one_row` and `push_one_column` reach the upper layer's by
; adding the other's length, instead of carrying two pointers.
strip_col:   .res WINDOW_ROWS * 2
strip_col2:  .res WINDOW_ROWS * 2
strip_row:   .res WINDOW_COLS * 2
strip_row2:  .res WINDOW_COLS * 2

; The strip `push_strips` is uploading, while it lasts: where it comes from and
; where it goes. They exist because there are **two** per axis and not one
; —see `stream_map`— and writing the DMA block four times with different
; addresses was four copies of the same code.
strip_vram:  .res 2      ; the VRAM word where it starts
strip_of:    .res 2      ; and where it comes from, the low sixteen bits
strip_bank: .res 1      ; in which bank: 0 this pass's, $7E the spare
; And where the spare ones go, which is the same as `col_addr` and `row_addr`
; for the others. In the BSS and not in the direct page like their twins
; because there are three bytes left there, measured with a `.res` in the
; segment.
col_addr_b: .res 2
row_addr_b: .res 2

; The `TileSubstitution` table: which block is drawn in place of which. It is
; the only part of the map that can change while running —the grid lives in
; the cartridge— and that is why the substitution is not written anywhere but
; looked up when reading each cell: see `cell_replaced`.
;
; **It lives as long as the loaded map lives, not as long as the tilemap
; window.** It is cleared when loading a map and not when refilling the
; window. That way it matches what RM2k does —the substitution applies to the
; scene's spriteset, so it is lost when the map is reloaded— and is also
; correct on returning from a battle, which refills the window without loading
; anything.
;
; `SUB_MAX` is also written in `tools/port/snes_convert.py`, which is the one
; that can refuse to emit a map that does not fit. `test_sustitucion.py`
; compares the two: here there is no way to report that it went over.
SUB_MAX = 8
sub_n:      .res 2      ; how many pairs are set, **in bytes**
sub_key:  .res SUB_MAX * 2
sub_value:  .res SUB_MAX * 2
; What `op_tile_sub` needs while it applies an instruction. It does not go in
; `temp`, which is four bytes and half the interpreter already uses.
sub_remain: .res 1      ; pairs left in this instruction
sub_of:     .res 2      ; the block going out and the one coming in, of the current pair
sub_a:      .res 2
sub_has:    .res 2      ; whether some key already was the one going out
; How many columns of the window are left to redo after a substitution.
;
; It is needed because **the tilemap in VRAM does not rewrite itself**:
; `stream_map` only builds the column and the row the camera uncovers, so a
; substitution with the camera still would not show until walking. **One
; column per frame** is redone, and only on frames where the camera did not
; take its own: two columns per frame do not fit, because `push_strips`
; uploads a single one and the rest of the vblank is already sold. So the whole
; window takes `WINDOW_COLS` frames to catch up, against RM2k's "on the spot"
; —it redraws the spriteset—; the stretch that is seen is the screen's
; columns, and the margin's go after. It is measured in `test_sustitucion.py`.
sub_refresh: .res 2

; The loaded map's NPC table. It is the only one of the map tables that is
; copied to RAM instead of read through a pointer, and for a concrete reason:
; build_oam walks it with an index and at five different offsets, so with
; `lda tabla, x` it takes one instruction per field and with a pointer it takes
; three. Copying it costs one DMA per map load and fits easily: the map with
; the most NPCs in the whole game has 89, and 127 fit here, which is the cap
; OAM imposes.
npc_buf:  .res NPC_MAX * NPC_STRIDE
; The graphics this map's move routes change to with command 34: two bytes per
; graphic, the entry in `npc_poses` and the palette. It is copied here when
; the map loads, like the NPC table, and for the same reason: it is read with
; an index —`lda route_gfx_buf, x`— and that addresses the data bank.
;
; Copying it rather than reading it from the cartridge with a long pointer is
; what makes it cheap: an `lda [ptr], y` wants the pointer in the direct page,
; and the direct page is full. It fits easily: the map that asks for the most
; in the whole game asks for six. See RUTA_GRAF_MAX in snes_convert.py.
route_gfx_buf: .res RUTA_GRAF_MAX * 2

; Where each of the map's events is, in cells, by table index. It is copied
; from the ROM when the map loads, like the NPC one, and for a reason that is
; not convenience: **a forced move route changes it**, and the next move route
; on the same event starts from where it left off. There is a page in this
; game that sends the same event walking nine times.
;
; The whole map goes and not only the events with a graphic: half the move
; routes in this game fall on invisible events, which are not drawn but do
; take time, and that time is what `ProceedWithMovement` waits for.
ev_pos_buf: .res EV_MAX * EV_STRIDE

; The forced move routes running on events. One slot per move route and not
; per event: there are few at a time —the page that sends the most walking
; moves four— and that way the table does not depend on how many events the
; map has.
;
;   +0  evento     the event's index, or $FF if the slot is free
;   +1  ptr        24-bit pointer to the first command, in the bytecode
;   +4  n          how many commands it has
;   +5  i          which one it is on
;   +6  movio      whether this frame was part of a step, which is what
;                  advances the walk cycle
;   +7  cuadros    how many frames the current step has left
;   +8  mirando    which way it faces, or $FF if the move route has not
;                  turned it yet: then the direction its page carries holds
;   +9  espera     the frames left in a `wait`
;   +12 banderas   bit 0 goes through walls, bit 1 animation stopped
;   +13 salto      what is left of the current jump, 0 if there is none
;   +14 jump_dx   and where it started from, in cells and signed
;   +15 jump_dy
;   +10 paso       which point of the walk cycle it is on
;   +11 timer      how many frames until the next frame
;
; The stride is 16 and not 9 so the slot is indexed with four shifts instead
; of a multiplication.
; The slot's fields: +0 the event, +1..+3 the pointer to the commands, +4
; how many, +5 which one it is on, +6 whether it moved this frame, +7 what the
; step has left, +8 which way it faces, +9 the wait, +10 and +11 the animation,
; +12 the flags, +13 what the jump has left and +14/+15 where it started, +16
; the frequency, +19 its row in `npc_buf` plus one, remembered by `slot_npc`. The stride is a power of two out of habit; there is room to spare.
ROUTE_EV_STRIDE = 32
ROUTE_EV_FREE = $FF
ROUTE_EV_NO_FACE = $FF     ; in +8: the move route has not turned it yet
route_ev:  .res RUTA_EV_MAX * ROUTE_EV_STRIDE
; How many of the twelve are worth looking at: the highest one used since the
; map was loaded, plus one. **It does not go down** when one is freed, and it
; does not need to: a slot that was never taken has $FF at +0, so searching
; beyond it cannot find anything.
;
; It exists because of `event_slot`, which runs **once per parallel
; event per frame** and always walked all twelve. In the Lazer Teeth HQ there
; are eleven events with a parallel page and **a single slot in use**: that was
; eleven walks of twelve to find one, and with that the loop overran the frame.
; It is one byte because exactly one was left in bank 0's BSS.
route_ev_cap: .res 1

; The running flashes. One slot per flash:
;
;   +0 target   0 the hero, or the event's index plus one; $FF free
;   +1 r, +2 g, +3 b   the color, from 0 to 31
;   +4 strength, +5 frames, +6 k
;   +7 the CGRAM entry of its palette if it is waiting for the vblank in
;      FAR_FLASH_PAL, or 0. It is never zero otherwise: the sprite
;      palettes start at 128
;
; The stride is eight so the slot is indexed with three shifts.
FLASH_STRIDE = 8
FLASH_FREE = $FF
flash_ev:  .res FLASH_MAX * FLASH_STRIDE
; What `palette_with_flash` needs while it builds the tables.
flash_dest: .res 1
flash_alpha: .res 1
flash_slot: .res 2
flash_slot_ofs: .res 2
flash_partial: .res 2

; The cell being queried, for `cell_ptr` and `cell_allowed`. It goes here
; and not in the direct page because it is read with absolute addressing,
; which is enough: only what is used as a pointer with `[dp], y` has to be in
; the direct page, and there are twelve bytes left there, counted.
cell_x:  .res 2
cell_y:  .res 2
; How many events the map has —to look them up by cell— and which one is being
; looked at. They go here and not in the direct page because they are read
; with absolute addressing.
ev_total:   .res 2
ev_sought: .res 2
; Which trigger is being looked for: the action button or the touch. Both use
; the same search —a cell's event and its active page— and only what trigger
; it has to match changes.
trigger_sought: .res 2
; The row of the NPC being refreshed, and where it lands in pixels.
npc_row: .res 2
npc_px:   .res 2
npc_py:   .res 2
; What `refresh_npc` copies from the slot before using X for something else.
; Whether any move route slot did something this frame. It is what decides
; whether the NPC table has to be sorted again, which otherwise costs every
; frame.
routes_moved: .res 1
; The two rows being compared or swapped.
cmp_a:    .res 2
cmp_b:    .res 2
slot_frames: .res 1
slot_facing:    .res 1
slot_step:    .res 1
; The two current directions. They are two bytes with the high one at zero
; because they are used as an index, and X and Y are sixteen-bit: a one-byte
; `ldx dir` would pick up the next byte along with it. `route_dir` is the one of
; the command being executed and has to survive the call that uses `cell_dir`.
route_dir:  .res 2
cell_dir: .res 2
; What command 34 takes from the map's table: which character the poses will
; come from —$FF is "hide the row"— and with which palette.
gfx_k:   .res 1
gfx_pal: .res 1
; What a diagonal step needs while it tries its two L's: the two components,
; and the cell it starts from, because `cell_allowed` works on
; `cell_x`/`cell_y` and it has to be moved to the elbow and back.
diag_v: .res 1
diag_h: .res 1
; And the pose a diagonal's turn starts from, already resolved: +8 may still
; hold ROUTE_EV_NO_FACE.
diag_facing: .res 1
diag_x: .res 2
diag_y: .res 2

; The timer. The frames are not kept whole but split into seconds and the
; remainder within the second, and that is not an optimization: it is what
; avoids dividing by 60 every frame. Counting one down is `sub - 1`, and when
; `sub` wraps around a second goes down; the timer being at zero is
; `timer_sec = 0`, which is the same as `Game_Party::UpdateTimers`'
; `frames / 60 == 0`.
;
; The colon blinks with `sub`, which is `frames % 60`.
timer_sec:  .res 2
timer_sub:  .res 1
timer_active:  .res 1
timer_visible: .res 1
; The four digits already separated, from minutes to seconds. They are
; recomputed when the second changes and not every frame: dividing by 60 and
; by 10 sixty times a second would be work for nothing.
timer_dig:  .res 4
; And what `timer_oam` keeps track of while it draws: which of the five glyphs
; it is on, which of its two halves, and which glyph it got.
timer_i:     .res 1
timer_half: .res 1
timer_glyph: .res 1
; The size the next object goes out with, already shifted into its place in
; OAM's small table: $02 is the characters' 32x32 and $00 the digits' 8x8. It
; is the only thing the two OBSEL sizes need to tell apart.
obj_big:  .res 1

; One bit per RM2k switch. The game queries up to 1003 in page conditions, so
; 1024 is enough. They are cleared only once at boot: in RM2k a new game
; starts with all of them off.
; The party's gold, 24 bits because RM2k's cap is 999999. It is not shown
; anywhere yet —the menu does not exist— but the gold branch of
; `ConditionalBranch` asks about it, and `ChangeGold` moves it.
gold:      .res 3
switches: .res SWITCH_BYTES

; The screen tint scales each channel by the same factor for every color, so
; instead of doing the computation 256 times it is done 32: one table per
; channel, indexed by the 5-bit value it had.
; The tint's saturation, in the same units as the other three. It goes in the
; BSS and not in the direct page —where `tint_r`, `tint_g` and `tint_b`
; are— because it no longer fits there: only what is used as a pointer with
; `[dp], y` has to be there, and there were twelve bytes left, counted.
; What the hero's forced move route carries besides the cursor. It goes in the
; BSS and not in the direct page —where `route_i` and `route_n` are— because it
; no longer fits there: only what is used as a pointer with `[dp], y` has to be
; there.
route_crosses: .res 1  ; walk_everywhere: the move route ignores collision
route_anim_for: .res 1  ; stop_animation: the pose stays on the middle one
route_jump:  .res 1     ; what is left of the current jump, 0 if there is none
; `ruta_salto_dx` and `ruta_salto_dy` lived here and nobody read them; their
; extra byte is what pays for the sixteen-bit `fade_map`.
; On while a step of a move route that goes through walls is being tried.
; `can_leave` and `can_enter` look at it, and the pad walking uses them too:
; that is why it lives here and not inside the move route.
crossing: .res 2
; Who is trying a step or a jump, to collide with the others: the event's
; index, or HERO_WALKER. And the layer of its active page, or $FF if it has
; none, which is an event that is not there —`IsActive()`— and collides with
; nobody. `prepare_walker` sets them for an event and `hero_blocked` for the
; hero, and `move_events` gives them back to the hero when it finishes, so
; outside an event's move route they always say "the hero".
walker:       .res 1
walker_layer:  .res 1
; Which layer the page `read_page` just read is on. It goes here and not
; with the other `pg_*` because the direct page is full —257 bytes in 256 with
; this one inside— and it is read with absolute addressing, which is enough.
pg_layer:     .res 1
; And its own move route, the one it walks by itself: the flags —bit 0 it has
; one, 1 it repeats, 2 it skips what is blocked, 3 it always faces the same
; way, 4 the animation keeps going while still—, the frequency and the speed,
; and where its commands are and how many. The speed goes on every page, with
; a move route or without one: it is what a forced move route on the event
; uses, as in RM2k.
pg_flags:    .res 1
pg_tile:     .res 1     ; +20..+23: what the page draws, see read_page
pg_attr:     .res 1
pg_pose:     .res 1
pg_pass:     .res 1
; The cell `pass_with_event` looks at.
pass_x:      .res 2
pass_y:      .res 2
; Whether any NPC row on this map can impose its passability bits (+15 other
; than $FF). `pass_look` sets it when the map loads, and the refresh does when
; a page with a tile graphic brings them; it is not cleared until the next map,
; so it can say yes too often, never no too often. With zero,
; `pass_with_event` does not walk the table.
pass_has:    .res 1
pg_freq:     .res 1
pg_speed:      .res 1
pg_route:     .res 3
pg_route_n:   .res 1
; +24..+27, the condition on a variable, is not copied: `conditions_ok` reads
; it from the table, which is the only one that looks at it. The BSS is full.
; That a switch or the party changed and which page is active on each event
; has to be looked at again: `page_routes`, at the start of the next frame.
refresh:    .res 1
; What `page_routes` gathers: the active page of each event with its own
; move routes, by its offset in the table; $FFFF if the event has no move
; routes and $FFFE if it has them and no page qualifies.
pick_by_ev: .res EV_MAX * 2
rp_ev:       .res 2
slot_px:     .res 2
slot_dir:    .res 1
HERO_WALKER = $FF
HERO_LAYER_INDEX  = 1
; The cell it wants to enter, and what `cell_blocked` is looking at.
dest_x:      .res 2
; Where `build_row` is: the column it builds, signed, and how many of the 64
; it has left.
row_col:    .res 2
strip_total:  .res 2
dest_y:      .res 2
other_ev:     .res 1
swap_a:   .res 1
swap_b:   .res 1
; The screen shake: where it is in pixels, signed; how many frames it has
; left; and with what strength and speed. And `screen_x`, which is the
; camera plus the shake: it is what the scroll, the HDMA table and OAM see,
; while the tilemap streaming keeps looking at `camera_x`, because the shake is
; a shift of the drawing and not of what has to be loaded.
; The tint is built here during the frame —the map's three palettes, tinted,
; in their CGRAM place— and uploaded by DMA in the next vblank. Before,
; `event_tint` turned the screen off in the middle of the frame to write
; CGRAM directly, and that is a half-tinted frame in the emulator and a black
; band on hardware; the shake gave it away, since it compares frame by frame.
cgram_shadow: .res 512
tint_ready:  .res 1
; And the screen flash: whether there is one built in `pal_buf` to upload,
; where `dma_shadow` uploads from, and the flash itself.
flash_ready: .res 1
shadow_origin:  .res 2
flash_rgb:   .res 3
flash_level: .res 2  ; at scale 256: the high byte is what gets drawn
flash_remain: .res 1
dest_tab_r:  .res 32    ; the three tables, 32 bytes each
dest_tab_g:  .res 32
dest_tab_b:  .res 32
dest_level:  .res 1
dest_toward:  .res 2    ; sixteen-bit: it is added to an index
dest_end:    .res 2
; How many poses `vram_drain` can upload this vblank: VQ_PER_FRAME, unless
; the tint has already taken part of the budget.
vq_cap:      .res 1
; The frames since reset, counted by the NMI: the boot waits for them to be
; BOOT_FRAMES, and afterwards it keeps counting for `count_lost`.
boot_frames: .res 1
nmi_seen:        .res 1  ; what it was at the end of the previous pass
lost_frames: .res 1  ; the ones the main loop let go by, saturated

shake_pos:    .res 2
shake_remain:  .res 2
shake_force: .res 1
shake_speed:    .res 1
screen_x:      .res 2
shake_amp:   .res 1
shake_sine:  .res 1
shake_new: .res 2
shake_cutoff: .res 2
shake_lo:    .res 2
shake_hi:    .res 2
layer_ev:     .res 2
found_layer: .res 1
jump_command:   .res 1  ; the index of the `begin_jump` being built
jump_stuck: .res 1  ; 1 if the jump did not start because the cell is occupied
; What `armar_salto` gathers while it walks the commands of a jump: how far it
; moves in cells —signed— and which way it ends up facing.
jump_dx:  .res 1
jump_dy:  .res 1
; And the absolute value `jump_direction` compares the two axes with.
facing_abs: .res 2


; 1 while no song is playing. It goes in the BSS and not in the direct page
; —where the rest of the music state lives— because it no longer fits there.
music_off: .res 1
; Which song is playing, in two bytes with the high one at zero because it is
; used as an index into the three pointer tables and X is sixteen-bit.
song_current: .res 2
; The jump's offset with the sign already extended to sixteen bits, which is
; how it is added to the cell.
jump_dx16: .res 2
jump_dy16: .res 2
; And what `dibujo_del_salto` takes and returns: the position in pixels of
; whoever jumps, how much the jump has left, and how much the drawing has to
; be raised.
jump_px:  .res 2
jump_py:  .res 2
jump_remain: .res 1
jump_height: .res 2
jump_val:  .res 2
jump_prod: .res 2
jump_sign: .res 2

tint_s:  .res 1
; What the saturation needs while it runs. The three channels go in words and
; not in bytes so `ldx sat_r` can be done directly: the indexes are sixteen
; bits, so an `ldx` on a byte would pick up the next one along with it.
sat_r:    .res 2
sat_g:    .res 2
sat_b:    .res 2
sat_light:  .res 1     ; the color's gray, five bits
sat_ch:   .res 1     ; the channel being saturated
sat_upload_mark: .res 1  ; whether oversaturating moves the channel away upward
sat_acc:  .res 3     ; the sum of the three weights, 24 bits
weight_lo:  .res 1
weight_hi:  .res 1
weight_ch:  .res 1
; Whether the table being built is the upper half of the hard light, that is,
; the one that lightens. See `channel_table`.
tint_mirror: .res 1
; Where a table is copied while it is mirrored. See `channel_table`.
tint_tmp: .res 32

table_r:  .res 32
table_g:  .res 32
table_b:  .res 32
; And the three of the tint alone, which is where the others come from. They go
; in a single array —red at 0, green at 32 and blue at 64— so they can be
; indexed with an offset; the caller says which.
pure:     .res 96
pure_ofs: .res 2

; And the tinted palette is built here before uploading it. You cannot tint in
; CGRAM by reading it and writing it back: a second tint would compound with
; the first. It always starts from the original palette, which is in the ROM.
pal_buf:  .res 512
; The shadow with the screen flash on top —what `flash_range` builds and
; `upload_flash` uploads— lives in this same place: the tinted palette is
; built and copied to the shadow in the same frame, before `flash_tick`
; writes here, and whatever is there is uploaded in the following vblank. Bank
; 0's RAM did not have room for another 512 bytes.

; How many passes X has been held, modulo 256: the autofire phase comes from
; its bit `AUTOFIRE_FRAMES`, see `read_pad`. It is not in the zero page, next
; to `pad_a`, because there were three bytes left there and this costs only
; four more bytes of code in absolute addressing; and absolute is safe because
; `read_pad` already reads `JOY1L` that way, so all its callers have a data
; bank that sees low RAM. It goes at the end so as not to shift anyone's
; address. `arranque` sets it to zero even though `read_pad` overwrites it on
; every pass with X released, because with X held since power-on the first
; frame would read garbage in bsnes.
autofire: .res 1

; How many frames some arrow has been held, and which ones were made to repeat
; on this one: see `arrows_repeat`. At the end for the same reason as
; `autofire`.
arrows_frames:   .res 1
arrows_repeated: .res 1
