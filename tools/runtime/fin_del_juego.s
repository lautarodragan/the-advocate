.segment "FAR"

; --- End Game ----------------------------------------------------------------
;
; `Scene_End`: la orden End Game del menú de pausa. Dos ventanas sobre negro
; —la pregunta, y "Yes" y "No" con la barra del System— que salen enteras,
; ya dibujadas, de tools/port/fin_del_juego.py: los tiles, las filas del
; tilemap que tienen algo, y dos paletas, una por orden marcada. Mover el
; cursor es subir la otra paleta; el porqué está en el encabezado de
; fin_del_juego.py.
;
; Todo va en BG2, sobre `RANURA_VRAM` y `RANURA_MAP`, que son los lugares que
; ya escriben el menú y la pantalla de ranuras: al volver, `menu_subir` los
; rearma y `volver_al_mapa` no tiene que reponer nada más.
;
; Se entra con `jsl` desde `menu_pantalla`, con la pantalla prendida o no, y:
;
;   B o "No"   vuelve con `rtl`, con la pantalla apagada: el menú se rearma
;   "Yes"      no vuelve: el tema y la pantalla se funden, se calla la música
;              y termina en `reset`, que es la pantalla de título si el
;              cartucho la lleva. Es el mismo final que el de la pantalla de
;              Game Over, y por lo mismo no cuida la pila ni la VRAM: el
;              arranque repone todo.
;
; `titulo_sel` es la orden marcada mientras se ve: el menú la vuelve a poner
; en End Game al volver, como hace con las otras pantallas.
.proc fin_pantalla
.a8
.i16
    phb
    phk
    plb
    lda #$80
    sta INIDISP                 ; blanking forzado: la VRAM sólo se toca así
    stz HDMAEN
    lda #FIN_ENTRA
    sta titulo_sel

    ; --- los tiles, desde RANURA_VRAM ---
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #RANURA_VRAM
    sta VMADDL
    lda #(FIN_TILES * 32)
    sta DAS0L
    lda #.loword(fin_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #^fin_tiles
    sta A1B0
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN
    ; --- el tilemap en blanco: origen fijo en el primer tile, que es cero ---
    rep #$20
.a16
    lda #RANURA_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #.loword(fin_tiles)
    sta A1T0L
    sep #$20
.a8
    lda #$09                    ; dos registros, sin avanzar el origen
    sta DMAP0
    lda #$01
    sta MDMAEN
    ; --- y las filas que tienen algo ---
    rep #$20
.a16
    lda #(RANURA_MAP + FIN_FILA0 * 32)
    sta VMADDL
    lda #(FIN_FILAS * 64)
    sta DAS0L
    lda #.loword(fin_mapa)
    sta A1T0L
    sep #$20
.a8
    lda #^fin_mapa
    sta A1B0
    lda #$01
    sta DMAP0
    sta MDMAEN
    jsr fin_paleta

    ; --- el PPU: BG2 sola, como `ranura_ppu_prender` ---
    lda #(RANURA_MAP / 1024 * 4)
    sta BG2SC
    lda #(RANURA_VRAM / 4096 * 16)
    sta BG12NBA
    stz BG2HOFS
    stz BG2HOFS
    lda #$FF                    ; la línea vofs+1 en el primer scanline: ver
    sta BG2VOFS                 ; `ppu_init`
    sta BG2VOFS
    lda #$02
    sta TM
    lda #$0F
    sta INIDISP

espera:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad
    ; Arriba y abajo cambian de orden, y con dos da lo mismo cuál: no hay
    ; tope, como en `Window_Selectable`, que da la vuelta.
    lda pad
    eor pad_ant
    and pad
    bit #PAD_B
    bne volver
    and #(PAD_UP | PAD_DOWN)
    beq mira_a
    lda titulo_sel
    eor #1
    sta titulo_sel
    jsr fin_paleta              ; todavía en el vblank
    bra espera
mira_a:
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; ya lo tenía apretado: no es un flanco
    lda titulo_sel
    cmp #FIN_NO
    bne salir
volver:
    lda #$80
    sta INIDISP
    plb
    rtl

salir:
    ; "Yes": el tema se funde como un `FadeOutBGM` de 400 ms —el `BgmFade`
    ; de `Scene_End`—, con la misma guarda que `op_fade_bgm`: con el tema
    ; apagado no hay nada que fundir, y con una pista del MSU-1 sí.
    lda f:MSU_SUENA
    bne fundir
    lda music_apagada
    bne pantalla
fundir:
    php
    sei                         ; lo lee `irq_musica`: todo junto o nada
    rep #$20
.a16
    lda #FIN_PASO_TEMA
    sta bgm_paso
    lda #$FFFF
    sta bgm_nivel               ; el volumen entero, que es de donde baja
    sep #$20
.a8
    lda #1
    sta bgm_fundido
    plp
pantalla:
    ; Y la pantalla, a negro por la rampa del conversor.
    ldx #0
baja:
    phx
    jsl f:ba_t_vblank
    plx
    lda f:fin_rampa, x
    sta INIDISP
    inx
    cpx #FIN_CUADROS
    bne baja
    lda #$80
    sta INIDISP
    ; El tema termina de fundirse con la pantalla en negro: el fundido de la
    ; pantalla es más corto. `bgm_fundido` vuelve a cero solo, en
    ; `irq_musica`; si no había tema, ya lo está. El tope es por las dudas:
    ; lo que le falta al tema son unos pocos cuadros, y FIN_CUADROS sobra.
    ldx #FIN_CUADROS
tema:
    lda bgm_fundido
    beq callado
    phx
    jsl f:ba_t_vblank
    plx
    dex
    bne tema
callado:
    ; La música, callada antes del arranque, como al salir del Game Over: el
    ; reset vuelve a subir el driver al SPC700, pero una pista de MSU-1
    ; seguiría sonando durante todo el arranque.
    lda #0
    sta f:MSU_SUENA
    sta MSU_CONTROL
    lda #$FF
    jsl f:ba_t_bgm
    jml f:reset
.endproc

; La paleta de la orden `titulo_sel` a las entradas 0 a 15. Con la pantalla
; apagada o adentro del vblank.
.proc fin_paleta
.a8
.i16
    stz CGADD
    lda titulo_sel
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    asl a
    asl a
    asl a                       ; 32 bytes por paleta
    clc
    adc #.loword(fin_cgram)
    sta A1T0L
    lda #32
    sta DAS0L
    sep #$20
.a8
    lda #^fin_cgram
    sta A1B0
    stz DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN
    rts
.endproc
