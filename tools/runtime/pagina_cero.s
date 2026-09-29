.segment "ZEROPAGE"
source:     .res 3      ; pointer to the block we are uploading
music:      .res 3      ; pointer into the music stream
camara_x:   .res 2      ; where the camera is looking, in pixels
camara_y:   .res 2
scroll_y:   .res 2      ; the same minus one, which is what the PPU wants
pad:        .res 1      ; what the pad had pressed this frame
pad_a:      .res 1      ; and A, which lives in the pad's other byte
pad_a_ant:  .res 1      ; how it was last frame, to see the edge
; The open choice, if there is one: it is `ShowChoice`. While `eleg_activo` is
; set there is a message window on screen with the options and the page is
; blocked, same as with an ordinary message.
;
; The cursor is not a sprite or a drawing: the converter emitted **one text
; frame per option**, identical except for where the ">" is, so moving it is
; recomposing the window with another offset. That is why there is no more
; state here than which one is highlighted.
eleg_activo: .res 1
eleg_n:      .res 1     ; how many options
eleg_sel:    .res 1     ; which one is highlighted, from zero
eleg_cancel: .res 1     ; which option the B button picks, plus one; 0 is "cannot
                        ; be cancelled". It is RM2k's `choice_cancel_type` as
                        ; is, which easyrpg uses as `type - 1`.
eleg_tabla:  .res 2     ; where the choice's table starts, inside the page:
                        ; for each option, the frame and the destination
eleg_flancos: .res 1    ; the buttons just pressed this frame. It does not
                        ; use `temp` because `events_tick` has it busy.
; The title screen menu. These are two bytes of its own and not the `eleg_`
; ones even though the cursor movement is the same: the interpreter's choice
; lives inside an event page and this one runs before there is a map, so
; sharing them would tie together two things that never touch.
; 1 if boot —or the title menu— loaded a save from SRAM. `music_boot` looks at
; it: a save brings its own song and not the one of the starting map.
; Which slot is being worked on, from 0 to SRAM_SLOTS - 1, or **$FF if no
; save is loaded**. That sentinel does both jobs —which slot and whether one
; was loaded— because bank 0 RAM is full and storing the fact separately did
; not fit.
;
; It lives in the **direct page** on purpose, and not for room but for the
; bank: the routines that work with SRAM have the data bank at $70, and a BSS
; variable read with absolute addressing would give them SRAM. The direct page
; always points to bank 0, so from there it reads correctly whatever the bank.
ranura: .res 1
titulo_sel:     .res 1  ; which option is selected, from zero
titulo_flancos: .res 1  ; and the buttons just pressed
; 1 while the slot screen is visible. The ROM does not read it: it is for the
; harness, like `cuadros_perdidos`. `vueltas` does not advance while the
; screen is showing, so a test that waits by ticks would hang; with this
; `consola.py` knows when to press. See `Partida.guardar_en`.
menu_abierto:   .res 1
pad_ant:     .res 1     ; last frame's JOY1H, to look at the edges of the
                        ; directions and of B as was already done with A

temp:       .res 4      ; intermediate computations
hero_x:     .res 2      ; where the hero is on the map, in pixels
hero_y:     .res 2
hero_dir:   .res 1      ; which way it faces
tile_x:     .res 2      ; and which 16x16 cell it is in. Two bytes: there are maps
tile_y:     .res 2      ; 500 cells wide and one would not fit
celdas:     .res 3      ; pointer to the block row where the window starts
celdas_ptr: .res 3      ; the same, while it is walked to build a strip
; The forced move route of the event being walked, while the tick lasts. It
; lives in the direct page and not in the slot because `lda [ptr], y`
; **only** addresses the direct page: with the pointer in BSS the assembler
; would emit the low byte and the ROM would read from somewhere else. It
; already happened once, with `msg_ptr`.
ruta_ptr:   .res 3
; The pose table of the walking NPCs, of the loaded map.
poses_ptr:  .res 3
win_col:    .res 2      ; the 8x8 cell that was at the window's edge
win_row:    .res 2      ; last frame, to know whether the camera crossed it
win_block:  .res 2      ; and the block row `celdas` points to
col_addr:   .res 2      ; where in VRAM the column just built goes
row_addr:   .res 2      ; likewise the row; $0000 in both if there is nothing
tira_ofs:   .res 2      ; offset inside the block, while it is built
tira_paso_col: .res 2   ; the size of a block row, in bytes
tira_resta: .res 2      ; how many cells are left to build
hero_ptr:   .res 3      ; and which grid cell, as a pointer: it moves
                        ; with it instead of being recomputed
step_left:  .res 1      ; what is left of the step in progress, in RM2k half
                        ; units —128 per cell—, 0 if there is none
step_dx:    .res 2      ; the step's direction in x: -1, 0 or 1
step_dy:    .res 2
anim_step:  .res 1      ; which point of the walk cycle it is at
anim_timer: .res 1      ; how many frames the walk frame has lasted:
                        ; `anim_count`, which goes up and is compared with the speed
moving:     .res 1      ; whether it moved this frame
oam_slot:   .res 2      ; which OAM object we are on
npc_ofs:    .res 2      ; offset inside the NPC table
hero_key:   .res 2      ; the hero's sort key
hero_drawn: .res 1      ; whether it has already been interleaved
high_acc:   .res 1      ; the bits of the small table being gathered
high_ptr:   .res 2      ; and which byte of it they are at. Two bytes because
                        ; it is used as an index, and `ldx` with 16-bit X reads
                        ; two: with one it would take garbage as the high byte.
obj_x:      .res 2      ; on-screen position of the object being built
obj_y:      .res 2
obj_tile:   .res 1
obj_attr:   .res 1
token:      .res 1      ; token for the handshake with the SPC700
es_pal:     .res 1      ; 1 if the console runs at 50 frames per second
pal_tick:   .res 1      ; to insert the missing music frame
reinicio:   .res 1      ; whether the stream already looped this frame

; The loaded map. All of this came from constants in the .inc when there was
; a single map; now it comes from its record in `mapa_tabla` —which lives in
; RODATA and is read with `lda f:`— and stays here for as
; long as it lasts. What is used only once —the DMA sizes, the VRAM bases—
; is not copied: it is read from the record at the time.
mapa_ofs:    .res 2     ; the offset of the current map's record
; And its index, to know whether a jump changes map. Two bytes since
; OP_TELEPORT's destination is a word: the game has 328 maps and a byte holds
; 256. The ceiling left is MAPA_STRIDE: `mapa_ofs` is sixteen bits, so it is
; 512 maps.
mapa_actual: .res 2
mapa_ancho:  .res 2     ; its width in 16x16 cells
mapa_alto:   .res 2
mapa_cw:     .res 2     ; and in 8x8 cells, which is double. It is stored ready
mapa_ch:     .res 2     ; because the redraw looks at it on every column and row
npc_total:   .res 2     ; how many bytes this map's NPC table takes
cam_max_x:   .res 2     ; how far the camera can go without leaving the map
cam_max_y:   .res 2
bloques_ptr: .res 3     ; the block table, which no longer fits in bank 0
bloques8_ptr: .res 3    ; the same shifted eight bytes, which is where the upper
                        ; layer starts inside the block. Two pointers come out
                        ; cheaper than eight `iny` in the hottest loop.
pass_ptr:    .res 3     ; passability, one byte per block
npc_ptr:     .res 3     ; and the NPC table, only while it is copied to RAM
entrada_x:   .res 2    ; where to enter the map about to be loaded, in
entrada_y:   .res 2     ; cells. $FFFF means "wherever the record says"

; The event interpreter.
pag_ptr:     .res 3     ; the page table of the loaded map
cod_ptr:     .res 3     ; the code of the page being run
elegida:     .res 3     ; the code of the page that won, while it is decided
elegida_hay: .res 1     ; whether some page of the current event won
elegida_trigger: .res 1 ; and what triggers it, to run only the automatic ones
; And which layer it is on, which is what decides which of the two cells
; triggers it with the action button: the one in front asks for the hero's
; layer and its own asks for any other. See `try_action`.
elegida_capa: .res 1
; Which of the two is being looked at: 1 the hero's, 0 the one in front.
accion_propia: .res 1
; `ev_actual` lived here and nobody read it: its two bytes are the ones that
; pay for the sixteen-bit map index, which otherwise did not fit —the ZP was
; at 256 of 256—.
salto_mapa:  .res 2     ; a Teleport requested by an event: to which map
salto_x:     .res 2     ; and to which cell. salto_hay says if one is pending
salto_y:     .res 2
salto_hay:   .res 1
saltos_restantes: .res 1 ; how many teleport chains are still allowed
; And how many there are. What the cap counts is **chained** teleports, that
; is, the ones that happen without the player getting control back: two maps
; that point at each other would hang forever. It does not count the ones in
; a save, which can be as many as they like. See where it is refilled, in
; `events_tick`.
;
; It was 8 until 2026-09-27, and Boss Wick's lair proved it wrong: from the
; neighbor's door on 37 back to there it is twelve jumps between maps without
; the player touching the pad —41, 40, the vidcasts, the video, 40 again, 43,
; 42, the favor, 41 and 37—, and with 8 the ROM panicked halfway through the
; second pass through 43. 32 leaves room for another scene like that and
; still cuts off a pair of maps that point at each other, only half a minute
; later.
SALTOS_MAX = 32
; And what happens when it runs out. **The jump is not dropped**: everything
; stops and it is reported. Dropping it silently is what hid the bug above for
; weeks —the game kept going, only on the wrong map— and it is exactly the
; failure CLAUDE.md calls "a path no test runs". A cap that is reached is a
; mistake of ours or of the game: either the cap fell short for a real scene
; —as happened with Wick's—, or two maps point at each other, and in RM2k that
; hangs the game.
;
; `panico` is the code of what happened, zero as long as nothing happens. The
; state test reads it; on the console what you see is the screen flashing,
; which cannot be mistaken for anything in the game.
panico:      .res 1
PANICO_SALTOS = 1       ; the teleport budget ran out
; The interpreter runs one frame at a time, not in a single pass. Before,
; `enter_map` ran all the pages in one go with the screen off and the waits
; were skipped: that collapsed time, and everything that in RM2k happens
; *during* a page did not exist. Now the chosen pages are queued when the map
; loads and the main loop consumes them.
; How many pages can start in the same frame, chained. In RM2k the cap is not
; on pages but on commands —`loop_limit = 10000` in `game_interpreter.h`— and
; it is shared among all the ones that start in the frame. Here it is counted
; per page, which is coarser: it only shows with a page that ends without
; doing anything and activates again, that is, the one that hangs the game in
; RM2k. There this one does not hang: it spends the frame and moves on.
ARRANQUES_MAX = 8

; The two bits of `ev_flags`, one per event.
FLAG_ESPERA = $01
FLAG_AUTO   = $02
ev_cur:      .res 2     ; the cursor inside the running page
; The parallel interpreters. The event list and each one's state live in bank
; 1 RAM; only what the loop needs at hand stays here.
par_n:       .res 1     ; how many events with a parallel page the map has
par_i:       .res 1     ; which one the loop is on
par_dir:     .res 2     ; where its state falls, which has to be pointed at twice
par_ev:      .res 1     ; which event it belongs to, to move it after the interpreter
; How many ticks the main loop has run, that is, **game time**. A tick is an
; RM2k logic step —easyrpg's `while (Game_Clock::NextGameTimeStep())`,
; `player.cpp:245`—, which there too is separate from the frame that is
; drawn: logic runs at DEFAULT_FPS and drawing at whatever the machine can
; manage. Here they normally match, and they split when a tick overruns the
; frame.
;
; The tests read it through WRAM to know **which tick** they are looking at
; —see `Partida` in rom/pruebas/arnes/consola.py—, so with this it no longer
; matters whether the ROM was late. How late it is is told by
; `cuadros_perdidos`, which is another question.
vueltas:     .res 2
; The only thing the ChipSet animation stores: what has to be uploaded in the
; next vblank, three bits per family —zero is nothing, otherwise the drawing
; plus one—.
;
; That the **decision** lives here and not inside the vblank is not taste: map
; 8's vblank does not have a cycle to spare. Twenty `nop` put there on purpose
; cost it 61 pixels —the pose queue spills out of the vblank and the last
; writes land with the screen already on— so the two divisions go in the body
; of the loop, where there is time to spare, and the vblank keeps an `lda` and
; a `beq`. It is the last free byte of the direct page.
anim_pend:   .res 1
ev_activo:   .res 1     ; whether there is a page halfway through running
ev_esperando: .res 2    ; how many frames are left of the current wait
; The hero's forced move route. In RM2k `ForceMoveRoute` is asynchronous: the
; page keeps running and the one who walks is the character, so this does not
; live in the interpreter but here, and `move_hero` consumes it instead of the
; pad. The commands are in the bytecode: see `ruta_heroe`.
ruta_n:      .res 1
ruta_i:      .res 1
; Whether the step the hero has in progress was started by the forced route
; and not by the pad. `any_routes` needs it: the last step of a route still
; counts as a pending route even when no commands are left, and a pad step
; never counts. Without this, `ProceedWithMovement` would stop waiting eight
; frames early, or would wait too long because the player started walking.
ruta_paso:   .res 1
ruta_espera: .res 1     ; the frames left of a route `wait`
; The target and the length of the route being read from the bytecode. The
; length goes in two bytes with the high one always zero: it is added to Y,
; which is sixteen.
ruta_blanco: .res 1
ruta_cuantas: .res 2
; A tint requested by an event, to apply in the next vblank.
tinte_pendiente: .res 1
; The party, in order. The hero's graphic is the first one's —RM2k decides it
; that way, and `AddActor`/`RemoveActor` both call `ResetGraphic`—, which
; means this is not bookkeeping: it shows on screen. `hero_poses` points to
; the twelve words of the map's actor table that say which tile each pose is,
; and `hero_pal` to which palette it is drawn with.
grupo:       .res 4
grupo_n:     .res 2
hero_poses:  .res 3
hero_pal:    .res 1
; And where its fifteen colors are, inside the map's actor table.
;
; The possible leaders **share a CGRAM slot**: one leads at a time, so giving
; each one a palette is having it occupied by someone who is not on screen.
; `apply_tint` uploads the leader's on top of that slot, tinted like the
; rest. At zero, there is no leader with a graphic and nothing is uploaded.
hero_cgram:  .res 3
; The page being looked at, already read from the table. It is copied instead
; of read in place because Y is the table's cursor, and also using it to index
; the switch bitmap makes the code impossible to follow.
pag_ofs:     .res 2
pag_restan:  .res 2
pg_evento:   .res 2
pg_trigger:  .res 1
pg_sa:       .res 2
pg_sb:       .res 2
pg_cod:      .res 3
pg_actor:    .res 1     ; the actor it requires in the party, or 0
act_ptr:     .res 3     ; cursor into the map's actor table
tinte_r:     .res 1     ; the screen tint, from 0 to 200 with 100 neutral
tinte_g:     .res 1
tinte_b:     .res 1
tin_ptr:     .res 3     ; the palette being tinted, in ROM
tin_count:   .res 2     ; how many colors it has
tin_cgadd:   .res 1     ; and which CGRAM entry it goes to
tin_fin:     .res 2     ; how many bytes it is, which is the loop's limit

; --- the text composer ------------------------------------------------------
; All of this is touched in the innermost loop of the repo —twelve rows per
; character, four sixteen-bit writes per row— so it goes in the zero page.
msg_ptr:     .res 3     ; pointer to the next character, inside `mensajes`. It goes
                        ; here and not with the rest of the state because `[dp],y`
                        ; only addresses the direct page.
comp_glifo:  .res 3     ; pointer to the character's twelve rows, in ROM
comp_char:   .res 2     ; which character, already as an index into the font
comp_col:    .res 2     ; which column of the line it is at
comp_fase:   .res 2     ; and which pixel of the cell it falls on, that is x mod 8
comp_base:   .res 2     ; the buffer byte where its cell column starts
comp_mask:   .res 2     ; the glyph row already shifted to its phase
comp_color:  .res 1     ; which palette index it is painted with
comp_fila:   .res 1     ; which buffer row, from 0 to 15
comp_dup:    .res 4     ; the mask duplicated to the two planes of each pair
comp_and:    .res 4     ; and the three combinations that come out of it
comp_or01:   .res 4
comp_or23:   .res 4
