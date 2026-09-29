.segment "FAR"

; --- equipment and the shop, outside bank 0 -----------------------------------
;
; The two screens are three kilobytes, and bank 0 had twelve bytes left in the
; test cartridge. They moved down here on 2026-09-19 for the same reason as
; battle and by the same route: they are entered with `jsl` to
; `equipo_pantalla` and `tienda_pantalla`, and what they need from bank 0 is
; called through the `ba_t_*` bridges, which were already there for battle
; —only two new ones were needed, `ba_t_lista` and `ba_t_armar`—.
;
; **The data bank is still 0**, unlike battle: these two read and write the
; scratch space and bank 0's tables with absolute addressing and so keep working
; without touching anything. What did change is the other way around: a datum
; **from here** read with absolute addressing would land in bank 0. There is
; only one, `mensaje_de`, and it goes with `f:`; it cost an afternoon of a shop
; with no greeting.
;
; It costs no frames: both block inside the page, `vueltas` does not advance
; while they are shown, and the two extra cycles of each `jsl` fall on a screen
; waiting for the pad.
;
; `Scene_Equip`: the actor, their four parameters, the five slots with what
; they have on; A on a slot shows the list of what can be put on there —it
; replaces the slots while it lasts— with the parameters that would result.
; The empty line at the end is taking off what is in the slot. B goes back.
; `pantallas.pantalla_equipo` is the reference, and `pantallas.equipar` the
; rule. The windows and the cursor bar go on BG1, which BG2's text does not
; touch: see `eq_pantalla_subir` and `eq_barra`.
;   eq_actor     is comp_char      ; the actor number
;   eq_ranura    is comp_col       ; the highlighted slot, 0 to 4
;   eq_eligiendo is comp_col + 1   ; whether the list is shown
;   eq_elegido   is comp_fase      ; the cursor's place in the list
;   eq_arriba    is comp_fase + 1  ; and the first one visible
;   eq_n         is comp_base      ; how many are in the list, with the empty one
;   eq_cand      is comp_mask      ; the item under the cursor, 0 if none
;   eq_suma      is comp_or01      ; a parameter, while being added up
;   eq_param     is comp_or01 + 2  ; which one
;   eq_s         is comp_or01 + 3  ; the slot being looked at
;   eq_id        is comp_or23      ; an item, two bytes
;   eq_tmp       is comp_and       ; `eq_apuntar`'s scratch, four bytes

; A: the slot. Leaves the WRAM window pointing at that slot of the actor:
; `FAR_EQUIPO` + actor * 10 + slot * 2.
.proc eq_apuntar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    sta comp_and                  ; the slot times two
    lda comp_char
    and #$00FF
    asl a
    sta comp_and + 2              ; the actor times two
    asl a
    asl a                       ; times eight
    clc
    adc comp_and + 2
    clc
    adc comp_and
    clc
    adc #FAR_EQUIPO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; A: the slot. Returns with the item in `eq_id`.
.proc eq_leer
.a8
.i16
    jsr eq_apuntar
    lda WMDATA
    sta comp_or23
    lda WMDATA
    sta comp_or23 + 1
    rts
.endproc

; A: the slot; `eq_id`: the new item.
.proc eq_escribir
.a8
.i16
    jsr eq_apuntar
    lda comp_or23
    sta WMDATA
    lda comp_or23 + 1
    sta WMDATA
    rts
.endproc

; The `k` of the item in `eq_id`, in X, and Z=1 if it is none or one the ROM
; does not know.
.proc eq_k
.a8
.i16
    rep #$20
.a16
    lda comp_or23
    beq ninguno
    cmp #ITEMS_N
    bcs ninguno
    tax
    sep #$20
.a8
    lda f:item_k, x
    cmp #$FF
    beq ninguno8
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #1                      ; Z=0
    rts
.a16
ninguno:
    sep #$20
.a8
ninguno8:
    lda #0                      ; Z=1
    rts
.endproc

; How many of item `eq_id` are in the inventory, in A.
.proc eq_inv_apuntar
.a8
.i16
    rep #$20
.a16
    lda comp_or23
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; One more —capped at 99— or one less of item `eq_id`. A: 1 adds, 0 subtracts.
.proc eq_inv_mover
.a8
.i16
    pha
    jsr eq_inv_apuntar
    lda WMDATA
    sta comp_and
    jsr eq_inv_apuntar
    pla
    beq resta
    lda comp_and
    cmp #ITEM_MAX
    bcs listo
    inc a
    bra escribir
resta:
    lda comp_and
    beq listo
    dec a
escribir:
    sta WMDATA
listo:
    rts
.endproc

; Is item `eq_id` a two-handed weapon? Z=0 if so.
.proc eq_dos_manos
.a8
.i16
    jsr eq_k
    beq no
    lda item_uso, x
    and #8
    rts
no:
    lda #0
    rts
.endproc

; The item slot A would have: the one it has, or —while choosing— the one
; under the cursor if it is the chosen slot, and none in the other if the
; weapon is two-handed. It is `pantallas.equipar` without touching anything.
; Returns in `eq_id`.
.proc eq_efectivo
.a8
.i16
    sta comp_or01 + 3
    lda comp_col + 1
    beq tiene
    lda comp_or01 + 3
    cmp comp_col
    bne otra
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    rts
otra:
    ; A two-handed weapon removes the shield; a shield removes the two-handed
    ; weapon.
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda comp_or01 + 3
    cmp #1
    bne no_escudo
    lda comp_col
    bne tiene                   ; the weapon is not being chosen
    jsr eq_dos_manos
    bne ninguno
    bra tiene
no_escudo:
    lda comp_or01 + 3
    bne tiene                   ; neither shield nor weapon: the usual one
    lda comp_col
    cmp #1
    bne tiene                   ; the shield is not being chosen
    rep #$20
.a16
    lda comp_mask
    sep #$20
.a8
    beq tiene                   ; taking off the shield does not touch the weapon
    lda #0
    jsr eq_leer
    jsr eq_dos_manos
    bne ninguno
    rts                         ; `eq_id` is already the weapon
tiene:
    lda comp_or01 + 3
    jmp eq_leer
ninguno:
    stz comp_or23
    stz comp_or23 + 1
    rts
.endproc

; Parameter `eq_param` —0 attack, 1 defense, 2 spirit, 3 agility— with the
; equipment `eq_efectivo` says, in `pant_valor`, capped to [1, 999].
.proc eq_parametro
.a8
.i16
    ; The one for their current level: `nivel_param`, where the four here go
    ; from 2 to 5. And Y is saved because `nivel_param` clobbers it and the
    ; caller of this does not expect that.
    phy
    rep #$20
.a16
    lda comp_or01 + 2
    and #$00FF
    clc
    adc #2
    tay
    sep #$20
.a8
    lda comp_char
    jsl f:nivel_param
    stx comp_or01
    ply
    lda #0
ranura:
    pha
    jsr eq_efectivo
    jsr eq_k
    beq sin_puntos
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a                       ; eight bytes per item
    sta comp_and
    lda comp_or01 + 2
    and #$00FF
    asl a
    clc
    adc comp_and
    tax
    lda f:item_puntos, x
    clc
    adc comp_or01
    sta comp_or01
    sep #$20
.a8
sin_puntos:
    pla
    inc a
    cmp #5
    bcc ranura
    rep #$20
.a16
    lda comp_or01
    bmi uno                     ; signed: equipment can subtract
    beq uno
    cmp #1000
    bcc listo
    lda #999
    bra listo
uno:
    lda #1
listo:
    sta comp_dup
    sep #$20
.a8
    rtl
.endproc

; The list of what the actor can put on in `eq_ranura`, as `k` in
; `FAR_ITEM_LISTA`, and at the end an $FF which is the empty line. How many in
; `eq_n`. It is `pantallas.candidatos`.
.proc eq_lista_armar
.a8
.i16
    stz comp_base
    ldx #1
otro:
    rep #$20
.a16
    txa
    clc
    adc #FAR_ITEMS
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    beq siguiente
    lda f:item_k, x
    cmp #$FF
    beq siguiente
    phx
    rep #$20
.a16
    and #$00FF
    tax                         ; X = k
    sep #$20
.a8
    lda comp_col
    inc a
    cmp item_tipo, x
    bne no_va
    ; Can the actor use it? One bit per actor, eight bytes per item.
    rep #$20
.a16
    txa
    asl a
    asl a
    asl a
    sta comp_and
    lda comp_char
    and #$00FF
    dec a
    pha
    lsr a
    lsr a
    lsr a
    clc
    adc comp_and
    sta comp_and                ; the byte; `comp_and` no longer holds k times eight
    pla
    and #$0007
    sta comp_and + 2              ; and the bit
    sep #$20
.a8
    ; With `f:` because `item_actores` moved to RODATA on 2026-09-13: it is 496
    ; bytes and bank 0's area was already fifteen over before the skills. It
    ; costs one byte and one cycle per read, and this runs once per item when
    ; opening the equipment screen.
    ;
    ; **Through X and not Y**: the 65816 has no `lda long, y`, only `long, x`.
    ; X holds the item's `k` and it is needed further down, so it goes to the
    ; stack and back. The `plx` leaves no flag being looked at: what follows
    ; is an `and`.
    ;
    ; The index comes from `comp_and` and not from Y, and that is not
    ; indifferent: two branches moved this same code to RODATA separately, one
    ; leaving the byte in Y —`tay`— and the other in `comp_and`. In the merge
    ; git kept one's `sta comp_and` and left the other's `tyx` in conflict:
    ; together they assembled and read a register nobody loaded anymore.
    phx
    ldx comp_and
    lda f:item_actores, x
    plx
    ldy comp_and + 2
    beq bit_listo
correr:
    lsr a
    dey
    bne correr
bit_listo:
    and #1
    beq no_va
    txa                         ; the k, which fits in a byte
    pha
    rep #$20
.a16
    lda comp_base
    and #$00FF
    clc
    adc #FAR_ITEM_LISTA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    inc comp_base
no_va:
    plx
siguiente:
    inx
    cpx #ITEMS_N
    bcs lista_lista
    jmp otro                    ; a `bcc`'s 127 bytes fell short once
                                ; `item_actores` was read long
lista_lista:
    rep #$20
.a16
    lda comp_base
    and #$00FF
    clc
    adc #FAR_ITEM_LISTA
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda #$FF                    ; the empty line
    sta WMDATA
    inc comp_base
    rts
.endproc

; The item at place A in the list, in `eq_id`: 0 if it is the empty line.
.proc eq_de_lista
.a8
.i16
    jsl f:ba_t_lista
    cmp #$FF
    beq vacia
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda item_id, x
    sta comp_or23
    sep #$20
.a8
    rts
vacia:
    stz comp_or23
    stz comp_or23 + 1
    rts
.endproc

; Writes to `eleg_tabla` the name of item `eq_id`, if the ROM knows it, with
; no more than A letters.
.proc eq_nombre
.a8
.i16
    sta comp_dup + 3
    jsr eq_k
    beq nada
    rep #$20
.a16
    txa
    sta comp_and
    asl a
    clc
    adc comp_and
    tax                         ; 3k, the name
    sep #$20
.a8
    stz temp + 1
    jsl f:ba_t_texto
    rts
nada:
    lda #255
    sta comp_dup + 3
    rts
.endproc

; The description of item `eq_id`, on the top two lines.
.proc eq_desc
.a8
.i16
    jsr eq_k
    beq nada
    rep #$20
.a16
    txa
    sta comp_and
    asl a
    clc
    adc comp_and
    inc a                       ; 3k + 1
    pha
    lda #PANT_DESC_POS
    sta eleg_tabla
    plx
    phx
    sep #$20
.a8
    stz temp + 1
    jsl f:ba_t_texto
    rep #$20
.a16
    lda #(PANT_DESC_POS + 128)
    sta eleg_tabla
    plx
    inx
    sep #$20
.a8
    stz temp + 1
    jsl f:ba_t_texto
    rts
nada:
    rts
.endproc

; The whole screen, in the buffer: `pantallas.pantalla_equipo`.
.proc eq_componer
.a8
.i16
    lda #255
    sta comp_dup + 3
    jsl f:ba_t_limpiar
    stz temp + 1
    ; --- the actor's name ---
    rep #$20
.a16
    lda #EQ_ACTOR_POS
    sta eleg_tabla
    lda comp_char
    and #$00FF
    asl a
    tax
    lda actor_txt, x
    tax
    cmp #$FFFF                  ; an actor with no name in this ROM
    sep #$20                    ; `sep` does not touch Z
.a8
    beq sin_nombre
    jsl f:ba_t_texto
sin_nombre:
    ; --- the description ---
    lda comp_col + 1
    beq la_puesta
    lda comp_fase
    jsr eq_de_lista
    rep #$20
.a16
    lda comp_or23
    sta comp_mask
    sep #$20
.a8
    bra desc
la_puesta:
    lda comp_col
    jsr eq_leer
desc:
    jsr eq_desc
    ; --- the parameters: now and, while choosing, after ---
    stz comp_or01 + 2
param:
    lda comp_or01 + 2
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda eq_param_pos, x
    sta eleg_tabla
    lda comp_or01 + 2
    and #$00FF
    clc
    adc #EQ_TEXTO_PARAM
    tax
    sep #$20
.a8
    lda #3                      ; the term in red: `ITEM_ROJO`
    sta temp + 1
    jsl f:ba_t_texto
    stz temp + 1
    lda comp_col + 1
    pha
    stz comp_col + 1            ; now: what is on
    jsl f:eq_parametro
    pla
    sta comp_col + 1
    rep #$20
.a16
    lda comp_dup                ; `ba_t_numero` consumes it, and the new value
    pha                         ; is colored by comparing it with this one
    sep #$20
.a8
    jsr param_pos
    rep #$20
.a16
    clc
    adc #EQ_PARAM_VALOR
    sta eleg_tabla
    sep #$20
.a8
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_numero
    lda comp_col + 1
    beq sin_flecha
    jsr param_pos
    rep #$20
.a16
    clc
    adc #EQ_PARAM_FLECHA
    sta eleg_tabla
    sep #$20
.a8
    lda #3                      ; in red, like `Window_EquipStatus`
    sta temp + 1
    lda #$3E                    ; '>'
    jsl f:ba_t_glifo
    jsl f:eq_parametro            ; after: with what the cursor is on
    ; And its color, `Window_EquipStatus::GetNewParameterColor`'s: equal in
    ; white, more in the "goes up" one and less in gray. It is `pantallas.
    ; color_del_valor_nuevo`.
    rep #$20
.a16
    pla                         ; the current one
    cmp comp_dup
    sep #$20                    ; `sep` does not touch the `cmp`'s flags
.a8
    beq igual
    bcc sube
    lda #1                      ; goes down: gray
    bra con_color
sube:
    lda #2
    bra con_color
igual:
    lda #0
con_color:
    sta temp + 1
    lda #3
    sta comp_dup + 2
    jsl f:ba_t_numero
    stz temp + 1                ; what follows goes in white
    bra param_listo
sin_flecha:
    rep #$20
.a16
    pla                         ; the current one, which was not needed
    sep #$20
.a8
param_listo:
    inc comp_or01 + 2
    lda comp_or01 + 2
    cmp #4
    bcs params_listos
    jmp param
params_listos:
    lda comp_col + 1
    bne lista
    ; --- the slots ---
    lda #0
ranura:
    pha                         ; the cursor is the bar: see `eq_barra`
    jsr fila_pos
    rep #$20
.a16
    clc
    adc #EQ_RANURA_TERM
    sta eleg_tabla
    sep #$20
.a8
    pla
    pha
    rep #$20
.a16
    and #$00FF
    clc
    adc #EQ_TEXTO_RANURA
    tax
    sep #$20
.a8
    lda #3                      ; the term in red, and the name of what
    sta temp + 1                ; is on in white: `eq_nombre` restores it
    jsl f:ba_t_texto
    pla
    pha
    jsr fila_pos
    rep #$20
.a16
    clc
    adc #EQ_RANURA_NOMBRE
    sta eleg_tabla
    sep #$20
.a8
    pla
    pha
    jsr eq_leer
    lda #EQ_RANURA_ANCHO
    jsr eq_nombre
    pla
    inc a
    cmp #5
    bcc ranura
    rts

    ; --- the list ---
lista:
    lda #0
lista_fila:
    pha
    clc
    adc comp_fase + 1
    cmp comp_base
    bcs lista_listo
    pla
    pha
    clc
    adc comp_fase + 1
    jsr eq_de_lista
    rep #$20
.a16
    lda comp_or23
    sep #$20
.a8
    beq lista_siguiente         ; the empty line
    pla
    pha
    jsr fila_pos_lista
    rep #$20
.a16
    clc
    adc #EQ_LISTA_NOMBRE
    sta eleg_tabla
    sep #$20
.a8
    lda #255
    jsr eq_nombre
    pla
    pha
    jsr fila_pos_lista
    rep #$20
.a16
    clc
    adc #PANT_DOS_PUNTOS
    sta eleg_tabla
    sep #$20
.a8
    stz temp + 1
    lda #$3A                    ; ':'
    jsl f:ba_t_glifo
    jsr eq_inv_apuntar
    lda WMDATA
    sta comp_dup
    stz comp_dup + 1
    lda #2
    sta comp_dup + 2
    jsl f:ba_t_numero
lista_siguiente:
    pla
    inc a
    cmp #EQ_LISTA_FILAS
    bcc lista_fila
    rts
lista_listo:
    pla
    rts

; A16 = the position of parameter `eq_param`.
param_pos:
    lda comp_or01 + 2
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda eq_param_pos, x
    rts
.a8

; A: the slot. A16 = the position of its row.
fila_pos:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a                       ; times 128: two rows of cells
    clc
    adc #EQ_RANURA_POS0
    rts
.a8

; A: the list row. A16 = the position of its row.
fila_pos_lista:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a
    clc
    adc #EQ_LISTA_POS0
    rts
.a8
.endproc

; A on the list: `pantallas.equipar` with what the cursor is on.
.proc eq_equipar
.a8
.i16
    lda comp_fase
    jsr eq_de_lista
    rep #$20
.a16
    lda comp_or23
    sta comp_mask
    sep #$20
.a8
    lda comp_col
    jsr sacar
    rep #$20
.a16
    lda comp_mask
    sep #$20
.a8
    beq listo
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda #0
    jsr eq_inv_mover            ; one less in the inventory
    rep #$20
.a16
    lda comp_mask
    sta comp_or23
    sep #$20
.a8
    lda comp_col
    jsr eq_escribir
    ; Two hands.
    lda comp_col
    bne no_arma
    jsr eq_dos_manos            ; `eq_id` is the new weapon
    beq listo
    lda #1
    jmp sacar
no_arma:
    cmp #1
    bne listo
    lda #0
    jsr eq_leer
    jsr eq_dos_manos
    beq listo
    lda #0
    jmp sacar
listo:
    rts

; A: the slot. What it has goes back to the inventory and it is left empty.
sacar:
    pha
    jsr eq_leer
    rep #$20
.a16
    lda comp_or23
    sep #$20
.a8
    beq vacia
    lda #1
    jsr eq_inv_mover
    stz comp_or23
    stz comp_or23 + 1
    pla
    jmp eq_escribir
vacia:
    pla
    rts
.endproc

; The BG1 windows under the bar, and the bar: in each frame's vblank, behind
; the text. The rows of the bottom window are uploaded without the cursor
; —`EQ_MARCO_TEXTO_N` rows of cells— and on top the cursor's two with the bar,
; from `eq_marco_barras`: first those of the five slots and then those of the
; list rows. Without remembering where it was: each frame restores everything,
; so the bar cannot end up painted in two places. It is 768 bytes, some five
; vblank lines on top of the text's ten.
.proc eq_barra
.a8
.i16
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #(ITEM_MARCO_MAPA + EQ_MARCO_TEXTO * 32)
    sta VMADDL
    lda #.loword(eq_marco_mapa + EQ_MARCO_TEXTO * 64)
    sta A1T0L
    lda #(EQ_MARCO_TEXTO_N * 64)
    sta DAS0L
    sep #$20
.a8
    lda #^(eq_marco_mapa)
    sta A1B0
    lda #$01
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN
    ; Which one: the slot, or the visible list row.
    lda comp_col + 1
    beq en_ranuras
    lda comp_fase
    sec
    sbc comp_fase + 1
    ldx #(RANURAS_EQUIPO * 128) ; the list's, after the slots'
    bra fila
en_ranuras:
    lda comp_col
    ldx #0
fila:
    rep #$20
.a16
    and #$00FF
    xba
    lsr a                       ; 128 bytes per row
    pha
    lsr a                       ; which is 64 words
    clc
    adc #(ITEM_MARCO_MAPA + EQ_BARRA_FILA0 * 32)
    sta VMADDL
    txa
    clc
    adc 1, s
    adc #.loword(eq_marco_barras) ; carry was left at zero: it is a
    sta A1T0L                   ; single-bank table
    pla
    lda #128
    sta DAS0L
    sep #$20
.a8
    lda #^(eq_marco_barras)
    sta A1B0
    lda #$01
    sta MDMAEN
    rts
.endproc

; The equipment screen of actor A, until the player goes back with B.
.proc equipo_pantalla
.a8
.i16
    sta comp_char
    stz comp_col
    stz comp_col + 1
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsl f:eq_pantalla_subir
    jsr eq_componer
    jsl f:ba_t_subir
    jsr eq_barra
    jsl f:items_ppu_prender     ; BG2 and BG1, the windows
espera:
    jsl f:ba_t_vblank
    ; The pad first and the DMA after. The other way around, the 1792 bytes
    ; take some ten lines and `read_pad` arrived with the pad's auto-read
    ; already over: it waited for the next frame's, each tick took two
    ; frames, and a one-frame press was lost half the time. With the pad
    ; read, the DMA still fits in vblank.
    jsl f:ba_t_pad
    jsl f:ba_t_subir
    jsr eq_barra
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    lda comp_col + 1
    beq en_ranuras
    jmp en_lista
en_ranuras:
    lda titulo_flancos
    and #PAD_UP
    beq r_no_arriba
    lda comp_col
    beq espera
    dec comp_col
    jmp recomponer
r_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq r_no_abajo
    lda comp_col
    cmp #4
    bcs espera
    inc comp_col
    jmp recomponer
r_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq r_mira_a
    rtl
r_mira_a:
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera
    jsr eq_lista_armar
    stz comp_fase
    stz comp_fase + 1
    lda #1
    sta comp_col + 1
    jmp recomponer
en_lista:
    lda titulo_flancos
    and #PAD_UP
    beq l_no_arriba
    lda comp_fase
    beq espera2
    dec comp_fase
    lda comp_fase
    cmp comp_fase + 1
    bcs recomponer
    sta comp_fase + 1
    bra recomponer
l_no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq l_no_abajo
    lda comp_fase
    inc a
    cmp comp_base
    bcs espera2
    sta comp_fase
    sec
    sbc comp_fase + 1
    cmp #EQ_LISTA_FILAS
    bcc recomponer
    inc comp_fase + 1
    bra recomponer
l_no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq l_mira_a
    stz comp_col + 1
    bra recomponer
l_mira_a:
    lda pad_a
    beq espera2
    lda pad_a_ant
    bne espera2
    jsr eq_equipar
    stz comp_col + 1
recomponer:
    jsr eq_componer
espera2:
    jmp espera
.endproc

