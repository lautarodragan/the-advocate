.segment "CODE"

; --- la pantalla de título -------------------------------------------------
;
; La imagen del LDB —`title_name`, que en el ABL es ABL20Title— con su tema
; —`title_music`, Fantasia_Of_The_Wind—, y de ahí a la partida.
;
; **Vive sola en la VRAM.** Mientras se ve no hay mapa cargado, así que no hay
; reparto que negociar: la imagen va en BG1, que en modo 3 tiene ocho bits por
; pixel y direcciona CGRAM entera. Un mapa reparte sus colores en paletas de
; dieciséis porque los sprites necesitan las suyas; acá no hay sprites.
;
; Los 496 tiles entran en $4000 —la base de tiles de BG1 va de a 4096 palabras,
; y 15872 palabras desde ahí terminan en 32256 de las 32768 que hay— y el
; tilemap en $0000. Al salir, `cargar_mapa` repone las dos bases y pisa todo.
;
; **Corre con su propio lazo y no con el principal.** El lazo principal mueve al
; héroe, corre el intérprete y arma el OAM, y acá no hay nada de eso: lo único
; que tiene que pasar por cuadro es leer el control y seguir la música.
.proc pantalla_titulo
.a8
.i16
    ; ¿Esta ROM lleva pantalla de título? TITULO_TILES no entra en ocho bits,
    ; así que la pregunta son los dos bytes.
    lda #<TITULO_TILES
    ora #>TITULO_TILES
    bne hay
    rts
hay:
    jsr titulo_subir
    ; El tema del título. $FF quiere decir que esta ROM no lo lleva —o que no
    ; entró en la ARAM—, y entonces la pantalla se ve callada.
    ;
    ; Va **acá y no en `titulo_subir`**: ésa corre también al volver de la
    ; pantalla de ranuras, y ahí el tema sigue sonando y no hay que tocarlo.
    ; Hasta el 2026-09-10 lo reiniciaba, con un comentario que decía que eso
    ; hacía RM2k, y no: `Scene_Title::Continue` al volver de la pantalla de
    ; cargar no pasa por `Start()`, y `Game_System::BgmPlay` con el mismo tema
    ; que ya suena no lo reinicia. taro lo escuchó en la consola.
    lda #TEMA_TITULO
    cmp #$FF
    beq mudo
    jsr music_start
mudo:
    jmp titulo_lazo
.endproc

; Sube la pantalla de título entera —la imagen, el menú, los colores— y la
; enciende. Está aparte del lazo porque hay dos caminos que llegan acá: entrar,
; y **volver de la pantalla de ranuras después de cancelar**, que pisó la VRAM y
; CGRAM con lo suyo.
.proc titulo_subir
.a8
.i16
    lda #$80
    sta INIDISP                 ; blanking forzado: la VRAM sólo se toca así
    stz HDMAEN                  ; y sin la ventana de mensaje encima

    ; --- los tiles ---
    lda #$80
    sta VMAIN                   ; avanzar una palabra tras el byte alto
    rep #$20
.a16
    lda #TITULO_VRAM
    sta VMADDL
    lda #(TITULO_TILES * BYTES_POR_TILE)
    sta DAS0L
    lda #<(titulo_tiles)
    ora #(>(titulo_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(titulo_tiles)
    sta A1B0
    lda #$01
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN

    ; --- el tilemap ---
    rep #$20
.a16
    lda #TITULO_MAP
    sta VMADDL
    lda #(32 * 32 * 2)
    sta DAS0L
    lda #<(titulo_celdas)
    ora #(>(titulo_celdas) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(titulo_celdas)
    sta A1B0
    lda #$01
    sta MDMAEN

    ; --- los tiles del menú ---
    ; Van en BG2, que en modo 3 tiene cuatro bits por pixel, así que cuestan la
    ; mitad. El tile 0 es transparente y le toca a casi toda la pantalla: es lo
    ; que deja ver la imagen debajo.
    rep #$20
.a16
    lda #TITULO_MENU_VRAM
    sta VMADDL
    lda #(TITULO_MENU_TILES * 32)
    sta DAS0L
    lda #<(titulo_menu_tiles)
    ora #(>(titulo_menu_tiles) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(titulo_menu_tiles)
    sta A1B0
    lda #$01
    sta MDMAEN

    ; --- los colores ---
    ; CGRAM entera y desde el índice 0: acá no hay ni ventana de mensaje ni
    ; color de fondo que respetar, que es lo que en un mapa se lleva las de
    ; abajo.
    stz CGADD
    rep #$20
.a16
    ; CGRAM entera: las TITULO_MENU_CGRAM de abajo son del menú y las
    ; TITULO_COLORES de arriba, de la imagen. Subir sólo las de la imagen
    ; dejaba las últimas dieciséis sin escribir, y ahí viven los colores menos
    ; usados —el degradé de los créditos—: 145 pixeles de diferencia contra la
    ; referencia, todos en el mismo par de renglones.
    lda #((TITULO_COLORES + TITULO_MENU_CGRAM) * 2)
    sta DAS0L
    lda #<(titulo_cgram)
    ora #(>(titulo_cgram) * 256)
    sta A1T0L
    sep #$20
.a8
    lda #^(titulo_cgram)
    sta A1B0
    stz DMAP0                   ; un registro, escribiendo de a un byte
    lda #$22
    sta BBAD0                   ; destino: CGDATA
    lda #$01
    sta MDMAEN

    ; --- y el PPU apuntando a todo eso ---
    lda #(TITULO_MAP / 1024 * 4)
    sta BG1SC                   ; tilemap de 32x32: los dos bits bajos en cero
    lda #(TITULO_MENU_MAP / 1024 * 4)
    sta BG2SC                   ; y el del menú, del mismo tamaño
    ; Las dos bases de tiles, que van de a 4096 palabras: BG1 en el nibble bajo
    ; y BG2 en el alto. La imagen arranca en $4000 porque 15872 palabras desde
    ; ahí terminan en 32256 de las 32768 que hay; el menú, en $1000, entra en el
    ; hueco que queda debajo junto con los dos tilemaps.
    lda #((TITULO_MENU_VRAM / 4096 * 16) | (TITULO_VRAM / 4096))
    sta BG12NBA
    stz BG1HOFS
    stz BG1HOFS
    stz BG2HOFS
    stz BG2HOFS
    lda #$FF
    sta BG2VOFS
    sta BG2VOFS
    ; El PPU muestra la línea vofs+1 en el primer scanline, igual que en el
    ; mapa: con 0 la imagen sale corrida una línea hacia arriba.
    lda #$FF
    sta BG1VOFS
    sta BG1VOFS
    lda #$03
    sta TM                      ; la imagen y el menú; sprites no hay

    stz titulo_sel              ; se entra con la primera opción elegida
    jsl f:titulo_subir_menu

    lda #$0F
    sta INIDISP                 ; y la pantalla encendida, al máximo
    rts
.endproc

; El lazo del menú. Arriba y abajo mueven el cursor por **flanco** y dando la
; vuelta, igual que `eleccion_tick` con el ShowChoice: es el
; `Window_Selectable::Update` de RM2k con una sola columna, y sostener abajo no
; baja un renglón por cuadro.
.proc titulo_lazo
.a8
.i16
espera:
    jsr wait_vblank
    jsr read_pad

    lda pad
    eor pad_ant
    and pad                     ; lo que se apretó en este cuadro
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    bne sube_una
    lda #TITULO_MENU_N          ; desde la primera, arriba da la vuelta
sube_una:
    dec a
    sta titulo_sel
    jsl f:titulo_subir_menu
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp #TITULO_MENU_N
    bcc baja_una
    lda #0                      ; y desde la última, abajo también
baja_una:
    sta titulo_sel
    jsl f:titulo_subir_menu
    bra espera
no_abajo:
    ; Elegir es A o START. START no lo mira RM2k —allá el menú es del ratón y
    ; del teclado— pero en una consola la pantalla de título se pasa con START
    ; y no tenerlo se siente roto.
    lda pad_a
    beq mira_start
    lda pad_a_ant
    beq elige                   ; flanco, no estado
mira_start:
    lda titulo_flancos
    and #PAD_START
    beq espera
elige:
    ; La segunda opción es 'Resume the Story': se carga la partida y, si hay,
    ; el mapa y la celda salen de ella. Si no hay, empieza igual que la
    ; primera, que es lo que hace RM2k cuando no hay nada que cargar.
    lda titulo_sel
    beq salir
    ; 'Resume the Story': la pantalla de ranuras, en modo cargar. Si el jugador
    ; cancela con B se vuelve al título, y como esa pantalla pisó la VRAM y
    ; CGRAM hay que subirlo de nuevo entero.
    lda #0
    jsr ranuras_pantalla
    cmp #$FF
    bne la_elegida
    jsr titulo_subir
    jmp titulo_lazo
la_elegida:
    jsr poner_ranura
    jsr cargar_partida
    beq salir                   ; la ranura estaba vacía o la suma no cuadra
    jsr entrada_de_la_partida
    rep #$20
.a16
    lda mapa_actual             ; el índice va en dieciséis bits
    bra cargar_el_mapa
.a8
salir:
    rep #$20
.a16
    lda #MAPA_INICIAL
cargar_el_mapa:
    ; La VRAM quedó con la imagen del título, así que el mapa hay que volver a
    ; cargarlo entero. Pero la VRAM no es lo único que esta pantalla movió: los
    ; **registros del PPU** también, y ésos no los repone `cargar_mapa`.
    ;
    ; `BG1SC`, `BG2SC`, los scrolls y `TM` los escribe `ppu_init`, que hasta
    ; ahora corría una sola vez en el arranque porque nadie los tocaba después.
    ; Sin volver a llamarlo el juego arranca con el tilemap de BG1 apuntando al
    ; del título —o sea todos los tiles corridos, que es lo que taro vio
    ; jugando la demo— y con `TM` en cero, que es la pantalla en negro con la
    ; lógica y la música corriendo detrás.
    ;
    ; **snes9x y la comparación de pixeles no lo vieron**, y por una razón que
    ; conviene recordar: la tanda mira la pantalla de título y no lo que pasa
    ; después de salir de ella. El cuadro que lo habría cobrado no existía.
    pha                         ; el índice del mapa, de dieciséis bits
    sep #$20
.a8
    lda #$80
    sta INIDISP
    stz TM                      ; y sin el menú encima mientras se rehace todo
    jsr ppu_init                ; los registros del PPU, como los dejó el reset
    rep #$20
.a16
    pla
    jsr cargar_mapa
    sep #$20
.a8
    jsr clear_oam
    jsr build_oam
    jsr flush_video

    ; La música. Sin esto el tema del título se queda sonando adentro del
    ; juego, que es lo que taro vio el 2026-09-10: `Fantasia_Of_The_Wind` en el
    ; pasillo de la apertura. `music_boot` es exactamente lo que hace una ROM
    ; sin pantalla de título al arrancar —el tema del mapa inicial, o callar si
    ; no tiene—, así que las dos siguen sonando igual.
    jsr music_boot
    lda music_apagada
    beq listo_musica
    ; `TEMA_ARRANQUE` en $FF quiere decir que el mapa arranca callado y que lo
    ; prende un `PlayBGM`, que es lo normal en este juego. `music_boot` no le
    ; escribe nada al DSP porque en el arranque no hay nada sonando; **acá sí
    ; lo hay**, así que el volumen general hay que bajarlo a mano. El
    ; `PlayBGM` que venga lo vuelve a subir: su stream escribe los dos
    ; registros al arrancar.
    php
    sei                         ; el SPC700 atiende de a uno: ver `irq_musica`
    stz dsp_valor
    lda #DSP_MVOL_L
    jsr escribir_dsp
    lda #DSP_MVOL_R
    jsr escribir_dsp
    plp
listo_musica:
    lda #$0F
    sta INIDISP
    rts
.endproc

