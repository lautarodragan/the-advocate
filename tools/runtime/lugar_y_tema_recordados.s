.segment "FAR"
.a8
.i16

; --- the memorized location and song ---------------------------------------------
;
; The bodies of `op_location` and `op_memorized_bgm`, which in bank 0 are only
; the entry: both arrive with `jsl`, with Y on their first operand, and return
; with `rtl` and the cursor advanced. They live here for space —bank 0 had
; about three hundred bytes left and the two together asked for almost two
; hundred—.
;
; Variables are read and written **directly in far RAM**, with
; `f:FAR_LARGO + FAR_VARIABLES`, and not with `var_read` and `var_write`:
; those are called with `jsr` and do not cross banks. Writing this way is the
; same as through the window —it is the same RAM— and the refresh is flagged
; the same way as in `var_write`.

; `MemorizeLocation` and `RecallToLocation`: the hero's location in three
; variables —the map, x and y—, and the jump to whatever they say. The
; operands are the mode and the three slots. In the mode, bit 0 says which of
; the two: 0 memorize, 1 jump (`LUGAR_SALTAR` in eventos.py); when memorizing,
; bits 7, 6 and 5 are the VAR_REFRESCO of the writes of the map, x and y, in
; that order, so it is enough to shift it once per write.
;
; **In the variables the map is the RM2k id**, not the cartridge's index: any
; other page reads and writes them —the breaking floors of the recycling plant
; load 61 with a ControlVars—, so both directions go through `mapa_rm2k`, the
; table of ids the converter emits.
;
; Jumping returns with carry set and `salto_mapa`, `salto_x` and `salto_y`
; set, and `op_location` ends like a `Teleport`: it ends the frame and the
; page continues on the new map. It is `CommandRecallToLocation`, which sets
; up the same `ReserveTeleport`. To a map the cartridge does not carry **it
; does not jump, and the page continues**: jumping anywhere would be worse,
; and ending the page would leave the player not knowing why.
.proc remembered_place
.a8
.i16
    lda [cod_ptr], y            ; the mode
    iny
    sta temp + 1
    lsr a
    bcs saltar
    ; Memorize: the map, from the table of ids, and the hero's live cell, like
    ; class 6 of ControlVars.
    rep #$20
.a16
    lda mapa_actual
    asl a
    tax
    lda f:mapa_rm2k, x
    jsr escribir
    lda tile_x
    jsr escribir
    lda tile_y
    jsr escribir
    sep #$20
.a8
    clc
    rtl

.a16
; A: the value, in sixteen bits. Writes it to the operand's slot and flags the
; refresh if the top bit of `temp + 1` asks for it, then shifts it.
escribir:
    pha
    lda [cod_ptr], y            ; the slot, and the neighboring byte
    iny
    and #$00FF
    asl a                       ; two bytes per variable
    tax
    pla
    sta f:FAR_LARGO + FAR_VARIABLES, x
    sep #$20
.a8
    lda temp + 1
    asl temp + 1                ; the next write's bit moves to the top
    and #VAR_REFRESCO
    beq sin_refresco
    lda #1
    sta refresco
sin_refresco:
    rep #$20
.a16
    rts

.a8
saltar:
    rep #$20
.a16
    jsr leer                    ; the RM2k id of the map
    ldx #0
buscar:
    cmp f:mapa_rm2k, x
    beq hallado
    inx
    inx
    cpx #MAPA_COUNT * 2
    bcc buscar
    iny                         ; not in the cartridge: the other two
    iny                         ; slots, and carry on
    sep #$20
.a8
    clc
    rtl
.a16
hallado:
    txa
    lsr a
    sta salto_mapa
    jsr leer
    sta salto_x
    jsr leer
    sta salto_y
    sep #$20
.a8
    sec
    rtl

.a16
; The variable in the operand's slot, in a 16-bit A.
leer:
    lda [cod_ptr], y
    iny
    and #$00FF
    asl a
    tax
    lda f:FAR_LARGO + FAR_VARIABLES, x
    rts

.endproc

; `MemorizeBGM` (operand 0) and `PlayMemorizedBGM` (operand 1): note down
; which song is playing in `TEMA_RECORDADO`, and put it back on. Putting it on
; returns with carry set and the song in A, and `op_memorized_bgm` plays it
; like a `PlayBGM`.
;
; Putting back the one already playing **does not restart it**: that is
; easyrpg's `Game_System::BgmPlay`, which with the same name and no fade in
; progress only adjusts the volume. That is exactly the game's case: the droid
; tutorial memorizes the song it arrived with and puts it on when leaving, and
; in between it does not change. With nothing memorized ($FF) it does nothing,
; where RM2k would silence the music; no page in the game plays a memorized
; song without having memorized it earlier in the same page.
.proc remembered_song
.a8
.i16
    lda [cod_ptr], y
    iny
    cmp #0                      ; explicit: so it is written down what is being tested
    bne put
    lda tema_actual + 1
    beq recordar
    lda #$FF                    ; none is playing
    bra anotar
recordar:
    lda tema_actual
anotar:
    sta f:TEMA_RECORDADO
    clc
    rtl
put:
    lda f:TEMA_RECORDADO
    cmp #TEMA_TOTAL
    bcs nada                    ; none, or one the cartridge does not carry
    ; Is it the one playing? The same question as `mapa_tema_callar`.
    pha
    lda bgm_fundido
    bne distinto                ; it was fading out: start over
    lda f:MSU_SUENA
    bne suena
    lda music_apagada
    bne distinto
suena:
    lda tema_actual + 1
    bne distinto
    pla
    cmp tema_actual
    bne tocar
nada:
    clc
    rtl
distinto:
    pla
tocar:
    sec
    rtl

.endproc
