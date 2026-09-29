.segment "CODE"

; --- the pause menu ----------------------------------------------------------
;
; `Scene_Menu`, over the bank of the slot screen: the geometry and the blocks
; come from `titulo.py`, and `render_menu` is the reference. It opens with B,
; when the hero is standing still: `request_menu` notes the request and
; `move_hero` serves it, which is how RM2k does it with `menu_calling`. The
; game clock does not run while it is shown —as on the slot screen— so the
; menu costs no tick.
;
; Today the things that do something are using items —the item screen, in
; `items.s`—, equipment, saving, which opens the slot screen and returns to
; the menu, and End Game, which opens its own —`fin_del_juego.s`—. Skills is
; drawn in gray and A does nothing with it.

; The permissions byte, in A. Only A, and the `lda`'s flags: bit 7 ends up in
; N.
.proc access_read
.a8
.i16
    rep #$20
.a16
    lda #FAR_ACCESS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; --- the sprite a `ChangeSpriteAssociation` gave an actor --------------------
;
; One byte per actor number in `FAR_ACTOR_GFX`, with the index into the map's
; graphics table or `ACTOR_GFX_NONE`. It lives far away, so WMADD is
; pointed at it and it goes through the port, like the variables.

; A: the actor. Leaves WMADD pointing at its byte.
.proc actor_gfx_point
.a8
.i16
    rep #$20
.a16
    and #$00FF
    clc
    adc #FAR_ACTOR_GFX
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; A: the actor. Returns with its graphic in A, or `ACTOR_GFX_NONE`.
.proc actor_gfx_read
.a8
.i16
    jsr actor_gfx_point
    lda WMDATA
    rts
.endproc

; A: the actor; `temp + 1`: the graphic.
.proc actor_gfx_write
.a8
.i16
    jsr actor_gfx_point
    lda temp + 1
    sta WMDATA
    rts
.endproc

; No actor with a changed sprite. Runs at reset, before loading the save,
; which overwrites it.
.proc actor_gfx_clear
.a8
.i16
    rep #$20
.a16
    lda #FAR_ACTOR_GFX
    sta WMADDL
    ldx #ACTORS_N
    sep #$20
.a8
    stz WMADDH
    lda #ACTOR_GFX_NONE
other:
    sta WMDATA
    dex
    bne other
    rts
.endproc

; The value `KeyInputProc` stores in the variable, in A, or 0 if there is no
; button yet. `temp + 1` carries the flags.
;
; **All three things**: cancel, the action button and the D-pad. By edge in
; the form that waits and by held state in the one that does not —see
; below—. The order is that of `CheckInput` —from highest value to lowest,
; which is what "RPG processes keys from highest variable value to lowest"
; says— and it is the same one `eventos.tecla_de` runs on the model's side;
; the numbers come from the converter and are not written here twice.
;
; Until 2026-09-13 this only looked at the action button, and what kept it
; cut short was not the ROM but the harness: the suite held a direction from
; boot, so no case could produce a D-pad edge. Now `--tocar` produces it, and
; the suite's `tecla-dir` case checks it.
;
; The edge is `Input::IsTriggered`: `pad` against `pad_prev` for B and the
; directions, `pad_a` against `pad_a_prev` for A —A lives in the other byte of
; the controller—, which is the same thing a message is closed with.
;
; `temp + 3` is the only one of the four that is free here: `temp` carries the
; slot and `temp + 1` the flags, and `op_key` stores the answer in `temp + 2`
; **after** returning from here.
.proc key_value
.a8
.i16
    ; The form that does not wait looks at what is **held** and not at the
    ; edge: it is the `wait ? IsTriggered : IsPressed` of
    ; `KeyInputState::CheckInput`, easyrpg `game_interpreter.cpp:3222`. It is
    ; the steering wheel of the race, which is held: by edge, the car changed
    ; lanes only once per press.
    ;
    ; The carry carries the wait flag **all the way to the action button**,
    ; without storing it: no `lda`, `and`, `eor` or `sta` in between touches
    ; it. Stored in `temp + 2` it cost four more bytes of bank 0.
    .assert KEY_WAIT = $01, error, "key_value takes it out with an lsr"
    lda temp + 1
    lsr a                       ; KEY_WAIT is bit 0: into the carry
    lda pad
    bcc joy_ready               ; no wait: what is held, as is
    eor pad_prev
    and pad
    ; Without the arrows that `arrows_repeat` made repeat this frame: here
    ; RM2k looks at `IsTriggered`, not `IsRepeated`. The `ora` and the `eor`
    ; are an `and` with the complement, and neither touches the carry.
    ora arrows_repeated
    eor arrows_repeated
joy_ready:
    sta temp + 3                ; JOY1H: B and the four arrows
    lda temp + 1
    and #KEY_CANCEL
    beq no_cancel
    lda temp + 3
    and #PAD_B
    beq no_cancel
    lda #KEY_VALUE_CANCEL
    rts
no_cancel:
    lda temp + 1
    and #KEY_DECISION
    beq no_decision
    lda pad_a
    bcc a_list                 ; the carry from above, still intact
    eor pad_a_prev
    and pad_a
a_list:
    beq no_decision
    lda #KEY_VALUE_DECISION
    rts
no_decision:
    lda temp + 1
    and #KEY_DIRS
    beq none
    ; The four, in the order of `CheckInput`, by table: written by hand they
    ; are four `bit`/`bne` plus four `lda`/`rts`, and bank 0 does not have
    ; them. The table ends in zero, which is no button.
    ldx #$0000
dir_other:
    lda f:key_dir_bit, x
    beq none
    and temp + 3
    bne dir_has
    inx
    bra dir_other
dir_has:
    lda f:key_dir_val, x
    rts
none:
    lda #0
    rts
.endproc

; A: the new permissions byte.
.proc access_write
.a8
.i16
    pha
    rep #$20
.a16
    lda #FAR_ACCESS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    rts
.endproc

; The menu request is dropped, if there was one. Only A.
.proc menu_forget
.a8
.i16
    jsr access_read
    bpl ready
    and #$7F
    jsr access_write
ready:
    rts
.endproc

; B just pressed asks for the menu, if it is allowed, there is no message and
; no page running: it is the end of `Game_Player::Update`. Runs after
; `move_hero`, so the menu opens on the next frame —or when the step ends, if
; the hero was walking—.
.proc request_menu
.a8
.i16
    lda pad
    eor pad_prev
    and pad
    and #PAD_B
    beq ready
    lda msg_open
    bne ready
    lda ev_active
    bne ready
    jsr access_read
    bit #ACCESS_NO_MENU
    bne ready
    ora #ACCESS_REQUESTED
    jsr access_write
ready:
    rts
.endproc

; Does option A do anything? Returns with A = 1 and Z=0 if so. Clobbers X.
.proc menu_enabled
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda menu_done, x
    beq ready
    cpx #MENU_SAVE
    bne ready
    jsr access_read
    and #ACCESS_NO_SAVE
    eor #ACCESS_NO_SAVE     ; 1 if allowed
ready:
    rts
.endproc

; The cursor on option A: `temp + 3` at 1 paints it and at 0 erases it. It is
; two cells, one below the other, written one word at a time. With the screen
; off or inside the vblank.
.proc menu_cursor_write
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda menu_cursor_vram, x
    tay
    sep #$20
.a8
    lda #$80
    sta VMAIN
    sty VMADDL
    lda temp + 3
    rep #$20
.a16
    beq erase
    lda menu_cursor_cells
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda menu_cursor_cells + 2
    sta VMDATAL
    sep #$20
.a8
    rts
.a16
erase:
    stz VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    stz VMDATAL
    sep #$20
.a8
    rts
.endproc

; The gold, right-aligned against the coin: it is divided by ten one byte at
; a time —the hardware divider is 16 by 8, and with the carried remainder the
; dividend never goes past 2559— and each remainder is a digit, from right to
; left. Zero is written "0".
.proc menu_gold_write
.a8
.i16
    rep #$20
.a16
    lda gold
    sta temp
    sep #$20
.a8
    lda gold + 2
    sta temp + 2
    lda #$80
    sta VMAIN
    ldy #(MENU_CURRENCY_VRAM - 1)
digit:
    stz temp + 3                ; the remainder carried along
    ldx #2
divide_it:
    lda temp, x
    sta WRDIVL
    lda temp + 3
    sta WRDIVH
    lda #10
    sta WRDIVB                  ; starts: the quotient takes sixteen cycles
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    sta temp, x
    lda RDMPYL                  ; the remainder
    sta temp + 3
    dex
    bpl divide_it
    rep #$20
.a16
    sty VMADDL
    lda temp + 3
    and #$00FF
    asl a
    asl a
    tax
    lda f:slot_glyph_cells + GLYPH_DIGIT_0, x
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda f:slot_glyph_cells + GLYPH_DIGIT_0 + 2, x
    sta VMDATAL
    dey
    lda temp                    ; anything left?
    bne other
    sep #$20
.a8
    lda temp + 2
    bne digit
    rts
.a16
other:
    sep #$20
.a8
    bra digit
.endproc

; The whole screen, with the screen off: the bank, the five options, the
; cursor on `title_sel`, the gold and the party. At the end it turns it on.
.proc menu_upload
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsr slot_bank_upload

    ; --- the options, each in its variant ---
    lda #0
other_option:
    pha
    jsr menu_enabled
    eor #1
    sta temp + 3                ; 1 if it goes in gray
    pla
    pha
    asl a
    ora temp + 3
    clc
    adc #MENU_BLK_OPTION
    sta temp + 3                ; the block
    pla
    pha
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda menu_option_vram, x
    tay
    lda temp + 3
    and #$00FF
    tax
    lda #(MENU_OPT_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #2
    sta temp + 2
    jsr slot_rect_upload
    pla
    inc a
    cmp #MENU_OPTIONS
    bcc other_option

    ; --- the cursor ---
    lda #1
    sta temp + 3
    lda title_sel
    jsr menu_cursor_write

    ; --- the gold and the coin ---
    jsr menu_gold_write
    rep #$20
.a16
    ldx #MENU_BLK_CURRENCY
    ldy #MENU_CURRENCY_VRAM
    lda #(MENU_CURRENCY_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #2
    sta temp + 2
    jsr slot_rect_upload

    jsr menu_party_paint
    jsl f:menu_exp_paint       ; the experience, which goes in sprites, and turns on
    lda #1
    sta menu_open
    rts
.endproc

; The party, one row per actor: the row's fixed block, the face, and on top
; the name, the level, the current HP and the maximum. Shared by the menu and
; the actor choice.
;
; **The block is a single one for the four rows and for every actor**: it
; carries the level term, the status and the HP term, which depend on no one.
; What does depend on the actor —its name, its level and its maximum— is
; composed with glyphs, and that is what keeps the tile bank from growing
; with the number of actors; see `slot_text_write`.
;
; The row stays on the stack for the whole pass and each step pulls the cell
; and the actor out of it again instead of saving them: the direct page is
; full —`temp` and `temp + 2` are used by the two routines that write— and
; each step runs once per row, with the PPU off.
.proc menu_party_paint
.a8
.i16
    lda #0
other_member:
    cmp party_n
    bcs party_ready
    cmp #MENU_ROWS_PARTY
    bcc enters
party_ready:
    rts
enters:
    pha                         ; the row, until the end of the pass
    jsr actor
    cmp #MENU_ACTORS_N
    bcc known
    jmp next               ; one this ROM does not know
known:

    ; --- the row's fixed block ---
    pla
    pha
    jsr row_vram
    lda #(MENU_ACTOR_COLS * 2)
    sta temp
    lda #MENU_ACTOR_ROWS
    sta temp + 2
    ldx #MENU_BLK_ROW
    jsr slot_rect_upload

    ; --- the face, in the row's top left corner ---
    pla
    pha
    jsr row_vram
    pla
    pha
    jsr actor
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda slot_face_block, x
    cmp #$FF
    beq no_face
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #(MENU_FACE_CELLS * 2)
    sta temp
    lda #MENU_FACE_CELLS
    sta temp + 2
    jsr slot_rect_upload
no_face:

    ; --- the name ---
    pla
    pha
    jsr row_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_NAME_OFS
    tay
    sep #$20
.a8
    pla
    pha
    jsr actor
    ldx #SLOT_TEXT_NAME
    jsr slot_text_of
    lda #MENU_NAME_COLS
    jsr slot_text_write

    ; --- the level ---
    pla
    pha
    jsr row_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_LEVEL_OFS
    tay
    sep #$20
.a8
    pla
    pha
    jsr actor
    jsl f:text_level           ; the current one: it goes up by fighting
    lda #SLOT_LEVEL_DIGITS
    jsr slot_text_write

    ; --- the maximum, after the slash ---
    pla
    pha
    jsr row_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_MAX_OFS
    tay
    sep #$20
.a8
    pla
    pha
    jsr actor
    jsl f:text_max          ; the one for its current level, like the level
    lda #MENU_MAX_DIGITS
    jsr slot_text_write

    ; --- and the current HP, which are not cartridge text but state ---
    pla
    pha
    sta temp + 2                ; the row
    jsr actor
    sta temp                    ; the actor
    jsl f:menu_hp_write
next:
    pla
    inc a
    jmp other_member

; The actor of the row given in A, and the cell where that row starts in the
; tilemap. Both are asked again at each step; see the comment above.
actor:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    rts

row_vram:
    rep #$20
.a16
    and #$00FF
    asl a                       ; two bytes per entry
    tax
    lda menu_row_vram, x
    tay
    sep #$20
.a8
    rts
.endproc

; The menu, until the player closes it with B. Returns to the restored map,
; like the slot screen from the save point.
.proc menu_screen
.a8
.i16
    phb
    phk
    plb
    sep #$20
    rep #$10
    stz title_sel              ; RM2k opens with the cursor on the first
build:
    jsr menu_upload
wait:
    jsr wait_vblank
    jsr read_pad
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    and #PAD_UP
    beq no_up
    lda title_sel
    bne uploads
    lda #MENU_OPTIONS          ; from the first, up wraps around
uploads:
    dec a
    jsr move
    bra wait
no_up:
    lda title_edges
    and #PAD_DOWN
    beq no_down
    lda title_sel
    inc a
    cmp #MENU_OPTIONS
    bcc low
    lda #0
low:
    jsr move
    bra wait
no_down:
    lda title_edges
    and #PAD_B
    bne close
    lda pad_a
    beq wait
    lda pad_a_prev
    bne wait                  ; it was already held: not an edge
    lda title_sel
    jsr menu_enabled
    beq wait                  ; in gray: RM2k plays a sound and does nothing
    lda title_sel
    cmp #2
    bne no_equipment
    ; Equipment: whom, and their screen. Both return to the menu.
    lda #1
    sta pick_cancel             ; for choosing
    jsr target_screen
    cmp #$FF
    beq equipment_return
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    jsl f:equipment_screen
equipment_return:
    lda #2
    sta title_sel
    jmp build
no_equipment:
    lda title_sel
    bne no_items
    ; Items: B returns to the menu, and using one goes straight back to the
    ; map.
    jsr items_screen
    beq items_return
    jmp close
items_return:
    stz title_sel
    jmp build
no_items:
    cmp #MENU_END
    bne save
    ; End Game: its screen, in `fin_del_juego.s`. "Yes" does not return —it
    ; ends in the reset—; "No" and B return to the menu with the cursor on the
    ; option, like `Scene::Pop`.
    jsl f:ending_screen
    lda #MENU_END
    sta title_sel
    jmp build
save:
    ; Save: the slot screen and, whether a slot is chosen or it is canceled,
    ; back to the menu with the cursor on "Save", like `Scene_Save` when it
    ; returns to `Scene_Menu`.
    lda #1
    jsr slots_screen
    cmp #$FF
    beq save_ready
    jsr set_slot
    jsr save_game
save_ready:
    lda #MENU_SAVE
    sta title_sel
    jmp build
close:
    ; The B that closes and the earlier A are consumed: without this
    ; `request_menu` would see the edge in this same pass and the menu would
    ; open again.
    lda pad
    sta pad_prev
    lda pad_a
    sta pad_a_prev
    stz menu_open
    lda boot_frames
    sta nmi_seen
    ; The equipment may have changed: the common events that only look at it
    ; run now, with the data bank still at 0. See `COMUNES_DEL_EQUIPO` in
    ; eventos.py.
    jsl f:equipment_commons
    plb
    jsl f:menu_exp_close       ; what the menu sprites changed
    jsr back_to_map
    rts

; The cursor to the option given in A: erased from where it was and painted
; there.
move:
    pha
    stz temp + 3
    lda title_sel
    jsr menu_cursor_write
    pla
    sta title_sel
    lda #1
    sta temp + 3
    lda title_sel
    jmp menu_cursor_write
.endproc

; --- the actor choice --------------------------------------------------------
;
; `Scene_ActorTarget`, over the menu's bank: the party panel, and the System
; windows and bar on BG1, which belong to `eleccion_de_actor.s`. `pick_cancel`
; says what for: at 1, to choose whom to equip, and A returns with the row; at
; 0, for the medicine `k` in `pick_edges`, and A uses it on the row
; —`medicine_use`— and **stays**, with that row's HP repainted, which is what
; `UpdateItem` does. B returns with $FF. `render_objetivo` in titulo.py is the
; reference.
;
; Until 2026-09-21 A did nothing with a medicine: it was written when outside
; battle nobody could have HP below the maximum, and it stayed that way when
; battles lowered them. It is taro's "the sandwich does not heal from the
; menu".

.proc target_screen
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsr slot_bank_upload
    jsr menu_party_paint
    jsl f:target_upload
    stz title_sel
    lda #1
    sta temp + 3
    lda #0
    jsl f:target_bar
    jsl f:target_ppu_on
wait:
    jsr wait_vblank
    jsr read_pad
    lda pad
    eor pad_prev
    and pad
    sta title_edges
    and #PAD_UP
    beq no_up
    lda title_sel
    beq wait
    dec a
    jsr move
    bra wait
no_up:
    lda title_edges
    and #PAD_DOWN
    beq no_down
    lda title_sel
    inc a
    cmp party_n
    bcs wait
    cmp #MENU_ROWS_PARTY
    bcs wait
    jsr move
    bra wait
no_down:
    lda title_edges
    and #PAD_B
    beq faces_a
    lda #$FF                    ; B: nothing chosen
    rts
faces_a:
    lda pad_a
    beq wait
    lda pad_a_prev
    bne wait                  ; it was already held: not an edge
    lda pick_cancel
    beq medicine
    lda title_sel              ; choosing: the chosen row
    rts
medicine:
    jsr actor_row
    jsl f:medicine_use
    beq wait                  ; it did not work: RM2k plays a sound and does nothing
    ; The row's HP, in the next vblank: the use took away the current value.
    jsr wait_vblank
    jsr actor_row
    sta temp
    lda title_sel
    sta temp + 2
    jsl f:menu_hp_write
    jsl f:target_count      ; and how many are left
    jmp wait

actor_row:
    rep #$20
.a16
    lda title_sel
    and #$00FF
    tax
    sep #$20
.a8
    lda party, x
    rts

move:
    pha
    stz temp + 3
    lda title_sel
    jsl f:target_bar
    pla
    sta title_sel
    lda #1
    sta temp + 3
    lda title_sel
    jsl f:target_bar
    rts
.endproc

