.segment "FAR"
.a8
.i16

; --- el lugar y el tema recordados ----------------------------------------------
;
; Los cuerpos de `op_location` y `op_memorized_bgm`, que en el banco 0 son sólo
; la entrada: los dos llegan con `jsl`, con Y en su primer operando, y vuelven
; con `rtl` y el cursor avanzado. Viven acá por lugar —en el banco 0 quedaban
; unos trescientos bytes y los dos juntos pedían casi doscientos—.
;
; Las variables se leen y se escriben **directo en la RAM lejana**, con
; `f:FAR_LARGO + FAR_VARIABLES`, y no con `var_leer` y `var_escribir`: ésas se
; llaman con `jsr` y no cruzan de banco. Escribir así es lo mismo que por la
; ventana —es la misma RAM— y el refresco se marca igual que en
; `var_escribir`.

; `MemorizeLocation` y `RecallToLocation`: el lugar del héroe en tres
; variables —el mapa, la x y la y—, y el salto a lo que digan. Los operandos
; son el modo y las tres ranuras. En el modo, el bit 0 es cuál de los dos: 0
; recordar, 1 saltar (`LUGAR_SALTAR` en eventos.py); al recordar, los bits 7,
; 6 y 5 son el VAR_REFRESCO de las escrituras del mapa, la x y la y, en ese
; orden, así que alcanza con correrlo uno por escritura.
;
; **En las variables el mapa es el id de RM2k**, no el índice del cartucho:
; las lee y las escribe cualquier otra página —los pisos que se rompen de la
; planta de reciclaje cargan el 61 con un ControlVars—, así que las dos
; direcciones pasan por `mapa_rm2k`, la tabla de ids que emite el conversor.
;
; Saltar vuelve con el acarreo prendido y `salto_mapa`, `salto_x` y `salto_y`
; puestos, y `op_location` termina como un `Teleport`: corta el cuadro y la
; página sigue en el mapa nuevo. Es `CommandRecallToLocation`, que arma el
; mismo `ReserveTeleport`. A un mapa que el cartucho no lleva **no salta, y la
; página sigue**: saltar a cualquier lado sería peor, y cortar la página
; dejaría al jugador sin saber por qué.
.proc lugar_recordado
.a8
.i16
    lda [cod_ptr], y            ; el modo
    iny
    sta temp + 1
    lsr a
    bcs saltar
    ; Recordar: el mapa, de la tabla de ids, y la celda viva del héroe, como
    ; la clase 6 de ControlVars.
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
; A: el valor, en dieciséis. Lo escribe en la ranura del operando y marca el
; refresco si lo pide el bit de arriba de `temp + 1`, que después corre.
escribir:
    pha
    lda [cod_ptr], y            ; la ranura, y el byte de al lado
    iny
    and #$00FF
    asl a                       ; dos bytes por variable
    tax
    pla
    sta f:FAR_LARGO + FAR_VARIABLES, x
    sep #$20
.a8
    lda temp + 1
    asl temp + 1                ; el de la escritura siguiente pasa arriba
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
    jsr leer                    ; el id de RM2k del mapa
    ldx #0
buscar:
    cmp f:mapa_rm2k, x
    beq hallado
    inx
    inx
    cpx #MAPA_COUNT * 2
    bcc buscar
    iny                         ; no está en el cartucho: las otras dos
    iny                         ; ranuras, y sigue
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
; La variable de la ranura del operando, en A de dieciséis.
leer:
    lda [cod_ptr], y
    iny
    and #$00FF
    asl a
    tax
    lda f:FAR_LARGO + FAR_VARIABLES, x
    rts

.endproc

; `MemorizeBGM` (el operando en 0) y `PlayMemorizedBGM` (en 1): anotar qué
; tema suena en `TEMA_RECORDADO`, y volver a ponerlo. Poner vuelve con el
; acarreo prendido y el tema en A, y `op_memorized_bgm` lo toca como un
; `PlayBGM`.
;
; Volver a poner el que ya suena **no lo arranca de nuevo**: es el
; `Game_System::BgmPlay` de easyrpg, que con el mismo nombre y sin un fundido
; en curso sólo ajusta el volumen. Es justamente el caso del juego: el
; tutorial del droide recuerda el tema con el que llegó y lo pone al irse, y
; en el medio no cambia. Con nada recordado ($FF) no hace nada, y en RM2k
; callaría la música; ninguna página del juego pone un tema recordado sin
; haberlo recordado antes en la misma página.
.proc tema_recordado
.a8
.i16
    lda [cod_ptr], y
    iny
    cmp #0                      ; explícito: que quede escrito qué se mira
    bne poner
    lda tema_actual + 1
    beq recordar
    lda #$FF                    ; no suena ninguno
    bra anotar
recordar:
    lda tema_actual
anotar:
    sta f:TEMA_RECORDADO
    clc
    rtl
poner:
    lda f:TEMA_RECORDADO
    cmp #TEMA_TOTAL
    bcs nada                    ; ninguno, o uno que el cartucho no lleva
    ; ¿Es el que suena? La misma pregunta que `mapa_tema_callar`.
    pha
    lda bgm_fundido
    bne distinto                ; se estaba apagando: vuelve a empezar
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
