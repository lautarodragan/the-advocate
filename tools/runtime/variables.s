.segment "CODE"

; --- the variables ---------------------------------------------------------
;
; They live in far RAM, and are read and written with long indexed addressing
; —`lda f:FAR_LENGTH + FAR_VARIABLES, x`—, which does not depend on the data
; bank. `var_read` returns in a 16-bit A **and leaves M at sixteen**;
; `var_write` takes the value from `temp + 2`. Neither of them touches X, Y
; or `temp`: callers count on that —see `op_place_var`—, and that is why the
; `phx`/`plx`.
;
; Until 2026-09-27 they were reached through the WMADD window, pointing and
; reading one byte at a time through the port: that cost twice as much, and
; each parallel page of the race does four of these per frame. See
; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.

; A: the slot. Returns its value in a 16-bit A, and M at sixteen.
.proc var_read
.a8
.i16
    phx
    rep #$20
.a16
    and #VAR_RANURA             ; the slot byte, without whatever B carries
    asl a                       ; two bytes per variable
    tax
    lda f:FAR_LENGTH + FAR_VARIABLES, x
    plx
    rts
.endproc

; A: the slot; B: the opcode's flags byte, with `VAR_REFRESCO` in the top bit
; if this write asks for a page refresh; `temp + 2`: the value.
;
; The refresh is flagged **here and not in each opcode** because every write
; goes through here —`op_var`, both branches of `op_key`, `op_terrain` and
; `op_location`— and that way the bit is checked only once. It is
; `Game_Map::SetNeedRefreshForVarChange`, which does not flag on just any
; write either: it asks `map_cache` whether any page condition on the map
; looks at that variable. Here that question was answered by the converter;
; see VAR_REFRESCO in eventos.py.
;
; Until 2026-09-27 the bit came in the slot, and that capped the variables at
; 128: see VAR_RANURA_MAX in eventos.py.
.proc var_write
.a8
.i16
    xba                         ; the flags
    bpl sin_refresco            ; VAR_REFRESCO is bit 7: see the .assert
    lda #1                      ; the flags are no longer needed: the `and`
    sta refresh                ; below drops whatever is left in B
sin_refresco:
    xba                         ; and the slot back
    phx
    rep #$20
.a16
    and #VAR_RANURA
    asl a
    tax
    lda temp + 2
    sta f:FAR_LENGTH + FAR_VARIABLES, x
    sep #$20
.a8
    plx
    rts
.endproc

.assert VAR_REFRESCO = $80, error, "var_write checks VAR_REFRESCO with the N flag"

; Turns the switch in temp on or off according to A.
;
; **Clobbers X and Y**, and a caller from the interpreter has to save Y, which
; is the bytecode cursor: that is why the `phy`/`ply` in `op_switch`. Without
; it the `run_code` loop keeps reading from the byte left in Y —an offset
; into the switch table— so the page is cut off at its first command and the
; event does nothing. The two pages in the game that do something start by
; turning switches on, so the symptom is "no page runs" and not "this page
; fails".
.proc set_switch
.a8
.i16
    pha
    rep #$20
.a16
    lda temp
    and #$0007
    tax
    lda temp
    lsr a
    lsr a
    lsr a
    tay
    sep #$20
.a8
    pla
    beq apagar
    lda switches, y
    ora f:mask, x
    sta switches, y
    lda #1
    sta refresh                ; the pages that ask for it may change
    rts
apagar:
    lda f:mask, x
    eor #$FF
    and switches, y
    sta switches, y
    lda #1
    sta refresh
    rts
.endproc

; All at zero, the random seed set, the hero's speed at 4, the inventory empty
; and the menu and saving allowed. Runs at reset, before loading the saved
; game. They live back to back in far RAM, so it is a single pass through the
; port.
.proc clear_variables
.a8
.i16
    rep #$20
.a16
    lda #FAR_ACCESS
    sta WMADDL
    ; Up to the end of the inventory, with whatever gap there is between the
    ; variables and it: it is one pass at reset and it does not matter.
    ldx #(FAR_ITEMS + ITEMS_N - FAR_ACCESS - 4)
    sep #$20
.a8
    stz WMADDH
    stz WMDATA                  ; saving and the menu, allowed
    lda #4                      ; the hero's normal speed
    sta WMDATA
    lda #<AZAR_SEMILLA
    sta WMDATA
    lda #>AZAR_SEMILLA
    sta WMDATA
otra:
    stz WMDATA
    dex
    bne otra
    rts
.endproc

; Every actor's initial equipment into `FAR_EQUIPMENT`: a DMA from the
; converter's table to the WRAM window. Runs at reset, before loading the
; saved game, which overwrites it.
.proc initial_equipment_set
.a8
.i16
    rep #$20
.a16
    lda #FAR_EQUIPMENT
    sta WMADDL
    lda #<(equipo_inicial)
    ora #(>(equipo_inicial) * 256)
    sta A1T0L
    lda #(ACTORES_N * 10)
    sta DAS0L
    sep #$20
.a8
    stz WMADDH
    lda #^(equipo_inicial)
    sta A1B0
    stz DMAP0                   ; A to B, one byte at a time
    lda #$80                    ; WMDATA
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc


; The hero's speed, in A. Only A: whoever asks for it is in the middle of a
; step with X and Y in use.
.proc hero_speed_read
.a8
.i16
    rep #$20
.a16
    lda #FAR_HERO_SPEED
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; A: the new speed.
.proc hero_speed_write
.a8
.i16
    pha
    rep #$20
.a16
    lda #FAR_HERO_SPEED
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    rts
.endproc

; How many frames each frame of the walk animation lasts at the hero's speed:
; `anim_per_speed`, which is `GetStationaryAnimFrames`. At speed 4 it is the
; usual six.
.proc hero_anim_frames
.a8
.i16
    jsr hero_speed_read
    rep #$20
.a16
    and #$00FF
    dec a
    tax
    sep #$20
.a8
    lda anim_per_speed, x
    rts
.endproc

; The signed comparison of `ConditionalBranch` and of the page condition by
; variable —RM2k uses `CheckOperator` for both—. A carries the variable's
; value in sixteen bits, `temp + 2` what it is compared against and `temp + 1`
; the code: ==, >=, <=, >, <, != in that order. Returns in eight bits with
; A = 1 and Z=0 if it holds, A = 0 and Z=1 if not. Clobbers `temp + 1` to
; `temp + 3`.
.proc compare_var
.a16
.i16
    sec
    sbc temp + 2                ; N, V and Z of the signed subtraction
    sep #$20
.a8
    php
    pla                         ; A = the flags: N $80, V $40, Z $02
    pha
    and #$C0
    beq no_menor                ; N and V clear: not less
    cmp #$C0
    beq no_menor                ; both set: not either
    lda #1
    bra menor_listo
no_menor:
    lda #0
menor_listo:
    sta temp + 2                ; less
    pla
    and #$02
    beq no_igual
    lda #1
no_igual:
    sta temp + 3                ; equal
    lda temp + 1                ; the comparison
    beq igual
    cmp #1
    beq mayor_igual
    cmp #2
    beq menor_igual
    cmp #3
    beq mayor
    cmp #4
    beq menor
    lda temp + 3                ; !=
    eor #1
    rts
igual:
    lda temp + 3
    rts
mayor_igual:
    lda temp + 2
    eor #1
    rts
menor_igual:
    lda temp + 2
    ora temp + 3
    rts
mayor:
    lda temp + 2
    ora temp + 3
    eor #1
    rts
menor:
    lda temp + 2
    rts
.endproc

; The xorshift step: x ^= x << 7; x ^= x >> 9; x ^= x << 8. Returns with the
; new value in a 16-bit A, and M at sixteen. It is `random_next` from
; eventos.py, instruction by instruction. Uses `temp + 2` as scratch: its
; caller —`op_var`— has not loaded it yet.
.proc random_next
.a8
.i16
    rep #$20
.a16
    lda #FAR_RANDOM
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    pha
    lda WMDATA
    xba
    pla                         ; C = x
    rep #$20
.a16
    sta temp + 2
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor temp + 2
    sta temp + 2
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor temp + 2
    sta temp + 2
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor temp + 2
    sta temp + 2
    lda #FAR_RANDOM
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda temp + 2
    sta WMDATA
    lda temp + 3
    sta WMDATA
    rep #$20
.a16
    lda temp + 2
    rts
.endproc
.a8
.i16



; Composes the window for the highlighted option. The box comes from the
; table, at `pick_table + pick_sel * 4`; the destination is two bytes further
; on and `choice_tick` reads it.
;
; Calling `msg_start` again with the window already open is what moves the
; cursor: `msg_open` is not cleared, so the window does not flicker, and the
; composer overwrites what was there line by line. One option's line is five
; or six characters, that is, a couple of frames: it looks like a cursor
; moving, not like a window being rebuilt.
.proc pick_open
.a8
.i16
    lda pick_sel
    asl
    asl                         ; four bytes per option
    rep #$20
.a16
    and #$00FF
    clc
    adc pick_table
    tay
    lda [code_ptr], y            ; the box's offset, 16 bits
    jsr msg_start             ; which expects it in A and in 16-bit mode
    sep #$20
.a8
    rts
.endproc

; One frame of an open choice. Returns A nonzero when the player chose, and
; at that point the page already has the cursor set on the option's body and
; carries on in this same frame.
;
; The cursor movement is `Window_Selectable::Update` with `column_max` at one:
; up and down wrap around, and they count on the **edge** and not the state,
; which is the `Input::IsTriggered` over there. Holding down does not move down
; one line per frame.
;
; Covered by `rom/pruebas/rpgmaker/test_elegir.py`, which can press any
; button.
.proc choice_tick
.a8
.i16
    lda msg_open
    bne abierta
    lda #0                      ; still being composed: nobody chooses
    rts
abierta:
    lda pad
    eor pad_prev
    and pad                     ; what was pressed **on this frame**
    sta pick_edges
    and #PAD_UP
    beq no_arriba
    lda pick_sel
    bne sube_una
    lda pick_n                  ; from the first one, up wraps around
sube_una:
    dec a
    sta pick_sel
    jsr pick_open
    lda #0
    rts
no_arriba:
    lda pick_edges
    and #PAD_DOWN
    beq no_abajo
    lda pick_sel
    inc a
    cmp pick_n
    bcc baja_una
    lda #0                      ; and from the last one, down does too
baja_una:
    sta pick_sel
    jsr pick_open
    lda #0
    rts
no_abajo:
    lda pick_edges
    and #PAD_B
    beq mira_a
    lda pick_cancel
    beq mira_a                  ; this choice cannot be cancelled
    dec a                       ; `choice_result = cancel_type - 1`
    sta pick_sel
    ; And the B is consumed here: in RM2k the window processes the button
    ; **after** the hero, who saw it with the message open and did not ask for
    ; the menu. Here the choice runs before `request_menu`, so its edge is
    ; cleared.
    lda pad_prev
    ora #PAD_B
    sta pad_prev
    bra elige
mira_a:
    lda pad_a
    beq nothing
    lda pad_a_prev
    bne nothing                    ; it was already held: not an edge
elige:
    lda pick_sel
    asl
    asl
    rep #$20
.a16
    and #$00FF
    clc
    adc pick_table
    inc a
    inc a                       ; the destination comes after the box
    tay
    lda [code_ptr], y
    sta ev_cur
    sep #$20
.a8
    stz pick_active
    stz msg_open             ; and with that `flush_video` turns HDMA off
    lda #1
    rts
nothing:
    lda #0
    rts
.endproc
