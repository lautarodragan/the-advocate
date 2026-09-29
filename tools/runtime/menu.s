.segment "CODE"

; --- the pause menu ----------------------------------------------------------
;
; `Scene_Menu`, over the bank of the slot screen: the geometry and the blocks
; come from `titulo.py`, and `render_menu` is the reference. It opens with B,
; when the hero is standing still: `pedir_menu` notes the request and
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
.proc acceso_leer
.a8
.i16
    rep #$20
.a16
    lda #FAR_ACCESO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; --- the sprite a `ChangeSpriteAssociation` gave an actor --------------------
;
; One byte per actor number in `FAR_ACTOR_GRAF`, with the index into the map's
; graphics table or `ACTOR_GRAF_NINGUNO`. It lives far away, so WMADD is
; pointed at it and it goes through the port, like the variables.

; A: the actor. Leaves WMADD pointing at its byte.
.proc actor_graf_apuntar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    clc
    adc #FAR_ACTOR_GRAF
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; A: the actor. Returns with its graphic in A, or `ACTOR_GRAF_NINGUNO`.
.proc actor_graf_leer
.a8
.i16
    jsr actor_graf_apuntar
    lda WMDATA
    rts
.endproc

; A: the actor; `temp + 1`: the graphic.
.proc actor_graf_escribir
.a8
.i16
    jsr actor_graf_apuntar
    lda temp + 1
    sta WMDATA
    rts
.endproc

; No actor with a changed sprite. Runs at reset, before loading the save,
; which overwrites it.
.proc actor_graf_limpiar
.a8
.i16
    rep #$20
.a16
    lda #FAR_ACTOR_GRAF
    sta WMADDL
    ldx #ACTORES_N
    sep #$20
.a8
    stz WMADDH
    lda #ACTOR_GRAF_NINGUNO
otro:
    sta WMDATA
    dex
    bne otro
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
; The edge is `Input::IsTriggered`: `pad` against `pad_ant` for B and the
; directions, `pad_a` against `pad_a_ant` for A —A lives in the other byte of
; the controller—, which is the same thing a message is closed with.
;
; `temp + 3` is the only one of the four that is free here: `temp` carries the
; slot and `temp + 1` the flags, and `op_key` stores the answer in `temp + 2`
; **after** returning from here.
.proc tecla_valor
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
    .assert TECLA_ESPERA = $01, error, "tecla_valor takes it out with an lsr"
    lda temp + 1
    lsr a                       ; TECLA_ESPERA is bit 0: into the carry
    lda pad
    bcc joy_listo               ; no wait: what is held, as is
    eor pad_ant
    and pad
    ; Without the arrows that `flechas_repetir` made repeat this frame: here
    ; RM2k looks at `IsTriggered`, not `IsRepeated`. The `ora` and the `eor`
    ; are an `and` with the complement, and neither touches the carry.
    ora flechas_repetidas
    eor flechas_repetidas
joy_listo:
    sta temp + 3                ; JOY1H: B and the four arrows
    lda temp + 1
    and #TECLA_CANCELAR
    beq sin_cancelar
    lda temp + 3
    and #PAD_B
    beq sin_cancelar
    lda #TECLA_VALOR_CANCELAR
    rts
sin_cancelar:
    lda temp + 1
    and #TECLA_DECISION
    beq sin_decision
    lda pad_a
    bcc a_lista                 ; the carry from above, still intact
    eor pad_a_ant
    and pad_a
a_lista:
    beq sin_decision
    lda #TECLA_VALOR_DECISION
    rts
sin_decision:
    lda temp + 1
    and #TECLA_DIRS
    beq ninguna
    ; The four, in the order of `CheckInput`, by table: written by hand they
    ; are four `bit`/`bne` plus four `lda`/`rts`, and bank 0 does not have
    ; them. The table ends in zero, which is no button.
    ldx #$0000
dir_otra:
    lda f:tecla_dir_bit, x
    beq ninguna
    and temp + 3
    bne dir_hay
    inx
    bra dir_otra
dir_hay:
    lda f:tecla_dir_val, x
    rts
ninguna:
    lda #0
    rts
.endproc

; A: the new permissions byte.
.proc acceso_escribir
.a8
.i16
    pha
    rep #$20
.a16
    lda #FAR_ACCESO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    rts
.endproc

; The menu request is dropped, if there was one. Only A.
.proc menu_olvidar
.a8
.i16
    jsr acceso_leer
    bpl listo
    and #$7F
    jsr acceso_escribir
listo:
    rts
.endproc

; B just pressed asks for the menu, if it is allowed, there is no message and
; no page running: it is the end of `Game_Player::Update`. Runs after
; `move_hero`, so the menu opens on the next frame —or when the step ends, if
; the hero was walking—.
.proc pedir_menu
.a8
.i16
    lda pad
    eor pad_ant
    and pad
    and #PAD_B
    beq listo
    lda msg_abierto
    bne listo
    lda ev_activo
    bne listo
    jsr acceso_leer
    bit #ACCESO_SIN_MENU
    bne listo
    ora #ACCESO_PEDIDO
    jsr acceso_escribir
listo:
    rts
.endproc

; Does option A do anything? Returns with A = 1 and Z=0 if so. Clobbers X.
.proc menu_habilitada
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda menu_hecha, x
    beq listo
    cpx #MENU_GUARDAR
    bne listo
    jsr acceso_leer
    and #ACCESO_SIN_GUARDAR
    eor #ACCESO_SIN_GUARDAR     ; 1 if allowed
listo:
    rts
.endproc

; The cursor on option A: `temp + 3` at 1 paints it and at 0 erases it. It is
; two cells, one below the other, written one word at a time. With the screen
; off or inside the vblank.
.proc menu_cursor_escribir
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
    beq borra
    lda menu_cursor_celdas
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda menu_cursor_celdas + 2
    sta VMDATAL
    sep #$20
.a8
    rts
.a16
borra:
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
.proc menu_oro_escribir
.a8
.i16
    rep #$20
.a16
    lda oro
    sta temp
    sep #$20
.a8
    lda oro + 2
    sta temp + 2
    lda #$80
    sta VMAIN
    ldy #(MENU_MONEDA_VRAM - 1)
cifra:
    stz temp + 3                ; the remainder carried along
    ldx #2
dividir:
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
    bpl dividir
    rep #$20
.a16
    sty VMADDL
    lda temp + 3
    and #$00FF
    asl a
    asl a
    tax
    lda f:ranura_glifo_celdas + GLIFO_CIFRA_0, x
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda f:ranura_glifo_celdas + GLIFO_CIFRA_0 + 2, x
    sta VMDATAL
    dey
    lda temp                    ; anything left?
    bne otra
    sep #$20
.a8
    lda temp + 2
    bne cifra
    rts
.a16
otra:
    sep #$20
.a8
    bra cifra
.endproc

; The whole screen, with the screen off: the bank, the five options, the
; cursor on `titulo_sel`, the gold and the party. At the end it turns it on.
.proc menu_subir
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsr ranura_banco_subir

    ; --- the options, each in its variant ---
    lda #0
otra_opcion:
    pha
    jsr menu_habilitada
    eor #1
    sta temp + 3                ; 1 if it goes in gray
    pla
    pha
    asl a
    ora temp + 3
    clc
    adc #MENU_BLQ_OPCION
    sta temp + 3                ; the block
    pla
    pha
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda menu_opcion_vram, x
    tay
    lda temp + 3
    and #$00FF
    tax
    lda #(MENU_OPC_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #2
    sta temp + 2
    jsr ranura_rect_subir
    pla
    inc a
    cmp #MENU_OPCIONES
    bcc otra_opcion

    ; --- the cursor ---
    lda #1
    sta temp + 3
    lda titulo_sel
    jsr menu_cursor_escribir

    ; --- the gold and the coin ---
    jsr menu_oro_escribir
    rep #$20
.a16
    ldx #MENU_BLQ_MONEDA
    ldy #MENU_MONEDA_VRAM
    lda #(MENU_MONEDA_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #2
    sta temp + 2
    jsr ranura_rect_subir

    jsr menu_grupo_pintar
    jsl f:menu_exp_pintar       ; the experience, which goes in sprites, and turns on
    lda #1
    sta menu_abierto
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
; with the number of actors; see `ranura_texto_escribir`.
;
; The row stays on the stack for the whole pass and each step pulls the cell
; and the actor out of it again instead of saving them: the direct page is
; full —`temp` and `temp + 2` are used by the two routines that write— and
; each step runs once per row, with the PPU off.
.proc menu_grupo_pintar
.a8
.i16
    lda #0
otro_miembro:
    cmp grupo_n
    bcs grupo_listo
    cmp #MENU_FILAS_GRUPO
    bcc entra
grupo_listo:
    rts
entra:
    pha                         ; the row, until the end of the pass
    jsr actor_de
    cmp #MENU_ACTORES_N
    bcc conocido
    jmp siguiente               ; one this ROM does not know
conocido:

    ; --- the row's fixed block ---
    pla
    pha
    jsr fila_vram
    lda #(MENU_ACTOR_COLS * 2)
    sta temp
    lda #MENU_ACTOR_FILAS
    sta temp + 2
    ldx #MENU_BLQ_FILA
    jsr ranura_rect_subir

    ; --- the face, in the row's top left corner ---
    pla
    pha
    jsr fila_vram
    pla
    pha
    jsr actor_de
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ranura_cara_bloque, x
    cmp #$FF
    beq sin_cara
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #(MENU_CARA_CELDAS * 2)
    sta temp
    lda #MENU_CARA_CELDAS
    sta temp + 2
    jsr ranura_rect_subir
sin_cara:

    ; --- the name ---
    pla
    pha
    jsr fila_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_NOMBRE_DESPL
    tay
    sep #$20
.a8
    pla
    pha
    jsr actor_de
    ldx #RANURA_TEXTO_NOMBRE
    jsr ranura_texto_de
    lda #MENU_NOMBRE_COLS
    jsr ranura_texto_escribir

    ; --- the level ---
    pla
    pha
    jsr fila_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_NIVEL_DESPL
    tay
    sep #$20
.a8
    pla
    pha
    jsr actor_de
    jsl f:text_level           ; the current one: it goes up by fighting
    lda #RANURA_NIVEL_CIFRAS
    jsr ranura_texto_escribir

    ; --- the maximum, after the slash ---
    pla
    pha
    jsr fila_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_MAX_DESPL
    tay
    sep #$20
.a8
    pla
    pha
    jsr actor_de
    jsl f:text_max          ; the one for its current level, like the level
    lda #MENU_MAX_CIFRAS
    jsr ranura_texto_escribir

    ; --- and the current HP, which are not cartridge text but state ---
    pla
    pha
    sta temp + 2                ; the row
    jsr actor_de
    sta temp                    ; the actor
    jsl f:menu_hp_write
siguiente:
    pla
    inc a
    jmp otro_miembro

; The actor of the row given in A, and the cell where that row starts in the
; tilemap. Both are asked again at each step; see the comment above.
actor_de:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    rts

fila_vram:
    rep #$20
.a16
    and #$00FF
    asl a                       ; two bytes per entry
    tax
    lda menu_fila_vram, x
    tay
    sep #$20
.a8
    rts
.endproc

; The menu, until the player closes it with B. Returns to the restored map,
; like the slot screen from the save point.
.proc menu_pantalla
.a8
.i16
    phb
    phk
    plb
    sep #$20
    rep #$10
    stz titulo_sel              ; RM2k opens with the cursor on the first
armar:
    jsr menu_subir
espera:
    jsr wait_vblank
    jsr read_pad
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    bne sube
    lda #MENU_OPCIONES          ; from the first, up wraps around
sube:
    dec a
    jsr mover
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp #MENU_OPCIONES
    bcc baja
    lda #0
baja:
    jsr mover
    bra espera
no_abajo:
    lda titulo_flancos
    and #PAD_B
    bne cerrar
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; it was already held: not an edge
    lda titulo_sel
    jsr menu_habilitada
    beq espera                  ; in gray: RM2k plays a sound and does nothing
    lda titulo_sel
    cmp #2
    bne no_equipo
    ; Equipment: whom, and their screen. Both return to the menu.
    lda #1
    sta eleg_cancel             ; for choosing
    jsr objetivo_pantalla
    cmp #$FF
    beq volver_de_equipo
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    jsl f:equipo_pantalla
volver_de_equipo:
    lda #2
    sta titulo_sel
    jmp armar
no_equipo:
    lda titulo_sel
    bne no_items
    ; Items: B returns to the menu, and using one goes straight back to the
    ; map.
    jsr items_pantalla
    beq volver_de_items
    jmp cerrar
volver_de_items:
    stz titulo_sel
    jmp armar
no_items:
    cmp #MENU_FIN
    bne guardar
    ; End Game: its screen, in `fin_del_juego.s`. "Yes" does not return —it
    ; ends in the reset—; "No" and B return to the menu with the cursor on the
    ; option, like `Scene::Pop`.
    jsl f:ending_screen
    lda #MENU_FIN
    sta titulo_sel
    jmp armar
guardar:
    ; Save: the slot screen and, whether a slot is chosen or it is canceled,
    ; back to the menu with the cursor on "Save", like `Scene_Save` when it
    ; returns to `Scene_Menu`.
    lda #1
    jsr ranuras_pantalla
    cmp #$FF
    beq guardar_listo
    jsr poner_ranura
    jsr guardar_partida
guardar_listo:
    lda #MENU_GUARDAR
    sta titulo_sel
    jmp armar
cerrar:
    ; The B that closes and the earlier A are consumed: without this
    ; `pedir_menu` would see the edge in this same pass and the menu would
    ; open again.
    lda pad
    sta pad_ant
    lda pad_a
    sta pad_a_ant
    stz menu_abierto
    lda boot_cuadros
    sta nmi_visto
    ; The equipment may have changed: the common events that only look at it
    ; run now, with the data bank still at 0. See `COMUNES_DEL_EQUIPO` in
    ; eventos.py.
    jsl f:equipment_commons
    plb
    jsl f:menu_exp_cerrar       ; what the menu sprites changed
    jsr volver_al_mapa
    rts

; The cursor to the option given in A: erased from where it was and painted
; there.
mover:
    pha
    stz temp + 3
    lda titulo_sel
    jsr menu_cursor_escribir
    pla
    sta titulo_sel
    lda #1
    sta temp + 3
    lda titulo_sel
    jmp menu_cursor_escribir
.endproc

; --- the actor choice --------------------------------------------------------
;
; `Scene_ActorTarget`, over the menu's bank: the party panel, and the System
; windows and bar on BG1, which belong to `eleccion_de_actor.s`. `eleg_cancel`
; says what for: at 1, to choose whom to equip, and A returns with the row; at
; 0, for the medicine `k` in `eleg_flancos`, and A uses it on the row
; —`medicine_use`— and **stays**, with that row's HP repainted, which is what
; `UpdateItem` does. B returns with $FF. `render_objetivo` in titulo.py is the
; reference.
;
; Until 2026-09-21 A did nothing with a medicine: it was written when outside
; battle nobody could have HP below the maximum, and it stayed that way when
; battles lowered them. It is taro's "the sandwich does not heal from the
; menu".

.proc objetivo_pantalla
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsr ranura_banco_subir
    jsr menu_grupo_pintar
    jsl f:objetivo_subir
    stz titulo_sel
    lda #1
    sta temp + 3
    lda #0
    jsl f:objetivo_barra
    jsl f:objetivo_ppu_prender
espera:
    jsr wait_vblank
    jsr read_pad
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    beq espera
    dec a
    jsr mover
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp grupo_n
    bcs espera
    cmp #MENU_FILAS_GRUPO
    bcs espera
    jsr mover
    bra espera
no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq mira_a
    lda #$FF                    ; B: nothing chosen
    rts
mira_a:
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; it was already held: not an edge
    lda eleg_cancel
    beq medicina
    lda titulo_sel              ; choosing: the chosen row
    rts
medicina:
    jsr actor_de_la_fila
    jsl f:medicine_use
    beq espera                  ; it did not work: RM2k plays a sound and does nothing
    ; The row's HP, in the next vblank: the use took away the current value.
    jsr wait_vblank
    jsr actor_de_la_fila
    sta temp
    lda titulo_sel
    sta temp + 2
    jsl f:menu_hp_write
    jsl f:objetivo_cuantos      ; and how many are left
    jmp espera

actor_de_la_fila:
    rep #$20
.a16
    lda titulo_sel
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    rts

mover:
    pha
    stz temp + 3
    lda titulo_sel
    jsl f:objetivo_barra
    pla
    sta titulo_sel
    lda #1
    sta temp + 3
    lda titulo_sel
    jsl f:objetivo_barra
    rts
.endproc

