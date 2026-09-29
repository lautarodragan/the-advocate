.segment "FAR"

; --- la pantalla de Game Over ------------------------------------------------
;
; Es `Scene_Gameover` de RM2k: la imagen que nombra el `System` del LDB, el tema
; de Game Over del sistema, un fundido de entrada, y al apretar A —o START, como
; en el título— un fundido de salida y la pantalla de título. Se llega por tres
; caminos:
;
;   perder una pelea sin manejador de derrota: `op_battle` anota el destino de
;                la derrota con `game_over_anotar`, y `pelea_arrancar` pregunta
;                con `game_over_si_perdio` apenas la pelea termina de fundirse
;                a negro. El mapa no se vuelve a cargar: en RM2k la pelea se
;                borra y aparece la imagen, sin pasar por el mapa
;   perder un encuentro al azar, que es siempre Game Over: `game_over_siempre`
;   el comando `GameOver`: `op_game_over` salta a `game_over_desde_el_mapa`,
;                que funde el mapa a negro como `Scene_Map::TransitionOut`
;
; **No vuelve**: termina en `reset`, que es la pantalla de título si el cartucho
; la lleva, con la partida guardada esperando en la SRAM. Por eso tampoco
; cuida la pila, ni la VRAM, ni la WRAM del $7F, ni el paquete de audio: el
; arranque repone todo. Y por eso se entra con `jml`.
;
; Vive en el banco 1 porque en el banco 0 no hay lugar: allá quedan sólo las
; entradas —tres `jsl` y el `jml` de `op_game_over`— y el puente del audio,
; `ba_t_audio`. Lo que necesita del banco 0 lo pide por los puentes de la
; pelea, que reponen el banco de datos.

; Cuántos cuadros dura cada uno de los dieciséis niveles de brillo. Son los de
; easyrpg-player: `Scene_Gameover` entra y sale en 80 cuadros, y el mapa se
; borra con el fundido de siempre, que son 35 —acá 32, dos por nivel—.
GO_CUADROS_PANTALLA = 5
GO_CUADROS_MAPA     = 2

; Los registros del PPU que sólo pone en cero esta pantalla: los demás los
; nombra registros.s. El mapa puede venir con la ventana de mensaje, un tinte
; o un mosaico, y la pelea con los suyos: sin esto se verían encima.
GO_W12SEL = $2123
GO_W34SEL = $2124
GO_TS     = $212D
GO_TSW    = $212F
GO_SETINI = $2133

; Adónde descomprime `pantalla_subir`: la WRAM del $7F desde el principio. Vale
; sólo mientras se sube —la pelea y la animación del ChipSet usan ese banco, y
; los dos se rearman después—, igual que `LZ2_BUFFER`. Entran los 64 KB que un
; flujo LZ2 puede dar, y pisa la mitad alta de la grilla: al Game Over le sigue
; el arranque, y a la pantalla de título `cargar_mapa`, y los dos la vuelven a
; descomprimir. `test_reservas_de_la_wram.py` lo deja pasar.
PANTALLA_BUFFER = $7F0000
; El tilemap de la pantalla, en palabras de VRAM. Los tiles van desde $0000 y
; la imagen más cargada son 896 tiles de 8bpp, o sea hasta $7000: arriba de
; eso no llegan nunca. El título pone su menú en el medio: ver el `.assert`
; de `titulo_subir`.
PANTALLA_MAPA = $7C00

; `op_battle` antes de pelear: el destino de la derrota, que está seis bytes
; detrás de la tropa —victoria, huida, derrota, de a palabra—. Entra con Y en
; la tropa y lo deja como estaba.
.proc game_over_anotar
.a8
.i16
    rep #$20
.a16
    phy
    iny
    iny
    iny
    iny
    iny
    iny
    lda [cod_ptr], y
    sta f:GO_PIERDE
    ply
    sep #$20
.a8
    rtl
.endproc

; Un encuentro al azar: perderlo es Game Over siempre, porque no hay página
; que traiga manejador.
.proc game_over_siempre
.a8
.i16
    lda #$FF
    sta f:GO_PIERDE
    sta f:GO_PIERDE + 1
    rtl
.endproc

; `pelea_arrancar`, con la pelea ya fundida a negro: si se perdió y el destino
; de la derrota es `BATALLA_PERDER`, no vuelve. Si no, sigue como siempre.
.proc game_over_si_perdio
.a8
.i16
    lda f:BAT_LARGO + BA_RESULT
    cmp #BA_DERROTA
    bne sigue
    rep #$20
.a16
    lda f:GO_PIERDE
    inc a                       ; $FFFF da cero, y `sep` no toca Z
    sep #$20
.a8
    bne sigue
    jmp game_over_negro
sigue:
    rtl
.endproc

; `GameOver`: el mapa se funde a negro desde el brillo que tenga —puede estar
; a mitad de un fundido— y de ahí, la pantalla.
.proc game_over_desde_el_mapa
.a8
.i16
.if ::GAME_OVER_TILES = 0     ; `::`: en un `.proc`, sin él no es constante
    jml f:reset                 ; una ROM sin imagen vuelve al título directo
.else
    phk
    plb
    lda #GO_CUADROS_MAPA
    sta f:GO_CUADROS
    lda brillo
    sta f:GO_NIVEL
baja:
    jsr go_esperar
    lda f:GO_NIVEL
    beq negro
    dec a
    sta f:GO_NIVEL
    sta INIDISP
    bra baja
negro:
    jmp game_over_negro
.endif
.endproc

; La pantalla, con la anterior ya en negro.
.proc game_over_negro
.a8
.i16
.if ::GAME_OVER_TILES = 0     ; `::`: en un `.proc`, sin él no es constante
    jml f:reset
.else
    phk
    plb
    lda #$80
    sta INIDISP                 ; blanking forzado: la VRAM sólo se toca así
    stz HDMAEN                  ; sin la ventana de mensaje
    lda #0
    sta f:GO_ESPERA
    ; El tema, primero: su paquete —el tema solo, ver PAQUETE_GAME_OVER en
    ; snes_convert.py— se sube con la pantalla en negro, y así suena desde el
    ; primer cuadro del fundido, como en RM2k. Con pista de MSU-1 el paquete
    ; no sube nada y suena la pista.
    ldx #PAQUETE_GAME_OVER
    jsl f:ba_t_audio
    lda #TEMA_GAME_OVER
    jsl f:ba_t_bgm
    ldx #(PANTALLA_GAME_OVER * PANTALLA_FILA)
    jsl f:pantalla_descomprimir
    jsl f:pantalla_subir        ; la misma fila: `pantalla_descomprimir` no
                                ; toca X

    ; El fundido de entrada.
    lda #GO_CUADROS_PANTALLA
    sta f:GO_CUADROS
    lda #0
    sta f:GO_NIVEL
sube:
    lda f:GO_NIVEL
    sta INIDISP
    jsr go_esperar
    lda f:GO_NIVEL
    cmp #$0F
    beq arriba
    inc a
    sta f:GO_NIVEL
    bra sube
arriba:
    ; Y la tecla, que en RM2k es `Input::DECISION`: A, por flanco. START
    ; también, como en la pantalla de título: ver `titulo_lazo`. Lo que se
    ; apretó durante el fundido no cuenta, porque `go_esperar` leyó el
    ; control en cada cuadro y el flanco ya pasó.
    lda #1
    sta f:GO_ESPERA
espera:
    jsl f:ba_t_vblank
    jsl f:ba_t_pad
    lda pad_a
    beq mira_start
    lda pad_a_ant
    beq cierra
mira_start:
    lda pad
    eor pad_ant
    and pad
    and #PAD_START
    beq espera
cierra:
    lda #0
    sta f:GO_ESPERA
    ; El fundido de salida, con el tema sonando todavía: en RM2k lo cambia
    ; recién el título.
baja:
    jsr go_esperar
    lda f:GO_NIVEL
    beq negro
    dec a
    sta f:GO_NIVEL
    sta INIDISP
    bra baja
negro:
    lda #$80
    sta INIDISP
    ; La música, callada antes del arranque: el reset vuelve a subir el driver
    ; al SPC700, pero una pista de MSU-1 seguiría sonando durante todo el
    ; arranque, hasta que el título pida la suya.
    lda #0
    sta f:MSU_SUENA
    sta MSU_CONTROL
    lda #$FF
    jsl f:ba_t_bgm
    jml f:reset
.endif
.endproc

; Los cuadros de GO_CUADROS, leyendo el control en cada uno. Pisa A.
.proc go_esperar
.a8
.i16
    lda f:GO_CUADROS
cuadro:
    pha
    jsl f:ba_t_vblank
    jsl f:ba_t_pad
    pla
    dec a
    bne cuadro
    rts
.endproc

; Una pantalla completa de `pantallas_tabla` —X es su fila, en bytes—, en dos
; pasos: `pantalla_descomprimir` la deja en `PANTALLA_BUFFER`, y
; `pantalla_subir` la lleva de ahí a la VRAM y a CGRAM.
;
; La fila es: el flujo LZ2 (tres bytes), cuántos bytes de tiles y cuántos de
; colores (una palabra cada uno) y desde qué color de CGRAM (un byte). El
; flujo trae las tres partes seguidas: los tiles, el tilemap de 32x32 y los
; colores. Ver tools/port/pantalla_completa.py.
;
; La usan la de Game Over y la de título: por eso no sabe cuál está subiendo.
; Son dos pasos por la de título, que se descomprime en el arranque, mientras
; se esperan los BOOT_CUADROS, y se sube recién al mostrarse: ver
; `titulo_subir`.
;
; Descomprimir no toca la VRAM, así que puede ser con la pantalla prendida.
; Deja X como estaba.
.proc pantalla_descomprimir
.a8
.i16
.ifdef ::PANTALLA_FILA
    phb
    phk
    plb
    phx                         ; la fila
    lda #^PANTALLA_BUFFER
    sta f:LZ2_BANCO
    lda f:pantallas_tabla + 2, x
    pha                         ; el banco del flujo
    rep #$20
.a16
    lda f:pantallas_tabla, x
    tax
    sep #$20
.a8
    pla
    ldy #.loword(PANTALLA_BUFFER)
    jsl f:lz2_descomprimir + RAPIDO
    plx
    plb
.endif
    rtl
.endproc

; La pantalla que `pantalla_descomprimir` dejó en `PANTALLA_BUFFER`, con X en
; la misma fila, a la VRAM y a CGRAM, y el PPU puesto para mostrarla en BG1 de
; modo 3, sola. La deja con la pantalla apagada: el brillo es de quien llama.
.proc pantalla_subir
.a8
.i16
.ifdef ::PANTALLA_FILA
    phb
    phk
    plb
    lda #$80
    sta INIDISP

    ; --- los tiles ---
    lda #$80
    sta VMAIN
    rep #$20
.a16
    lda #$0000
    sta VMADDL
    lda f:pantallas_tabla + 3, x
    sta DAS0L
    lda #.loword(PANTALLA_BUFFER)
    sta A1T0L
    sep #$20
.a8
    lda #^PANTALLA_BUFFER
    sta A1B0
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN

    ; --- el tilemap, detrás de los tiles ---
    rep #$20
.a16
    lda #PANTALLA_MAPA
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda f:pantallas_tabla + 3, x
    clc
    adc #.loword(PANTALLA_BUFFER)
    sta A1T0L
    sep #$20
.a8
    lda #$01
    sta MDMAEN                  ; el banco y el destino, los de arriba

    ; --- los colores, detrás del tilemap ---
    lda f:pantallas_tabla + 7, x
    sta CGADD
    rep #$20
.a16
    lda f:pantallas_tabla + 5, x
    sta DAS0L
    lda f:pantallas_tabla + 3, x
    clc
    adc #(.loword(PANTALLA_BUFFER) + 32 * 32 * 2)
    sta A1T0L
    sep #$20
.a8
    stz DMAP0                   ; un registro, de a bytes
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN

    ; --- y el PPU, con todo lo que el mapa o la pelea pudieron dejar ---
    lda #$03
    sta BGMODE
    lda #(PANTALLA_MAPA / 1024 * 4)
    sta BG1SC                   ; tilemap de 32x32
    stz BG12NBA                 ; los tiles de BG1 desde $0000
    stz BG1HOFS
    stz BG1HOFS
    lda #$FF                    ; la línea vofs+1 en el primer scanline: ver
    sta BG1VOFS                 ; `ppu_init`
    sta BG1VOFS
    lda #$01
    sta TM                      ; la imagen sola: ni sprites ni la otra capa
    ; Todo como lo deja `ppu_reset` —ver `ppu_altos` en banco1.s—, y no en
    ; cero: TMW y CGWSEL los pone sólo el reset, y el mapa los espera así. Al
    ; Game Over le sigue el reset, pero al título le sigue el mapa: con TMW en
    ; cero la ventana de mensaje dejaba de tapar a los objetos.
    stz GO_TS
    lda #$10
    sta TMW                     ; la máscara, sólo para los objetos, que acá
                                ; no se ven
    stz GO_TSW
    stz GO_W12SEL
    stz GO_W34SEL
    stz WOBJSEL
    lda #$30
    sta CGWSEL                  ; sin color math: ni tinte ni destello
    stz CGADSUB
    stz MOSAIC
    stz GO_SETINI
    plb
.endif
    rtl
.endproc
