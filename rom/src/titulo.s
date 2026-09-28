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
; La imagen viene comprimida, y la sube `pantalla_subir`, la misma rutina que
; la de Game Over: los tiles desde $0000 y su tilemap en PANTALLA_MAPA. El
; reparto de la VRAM está en mapdata.inc, junto a TITULO_MENU_VRAM. Al salir,
; `cargar_mapa` repone las bases y pisa todo.
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
    stz HDMAEN                  ; sin la ventana de mensaje encima

    ; --- la imagen, con CGRAM entera ---
    ; La sube `pantalla_subir`, que es la de Game Over: los tiles desde $0000,
    ; el tilemap en PANTALLA_MAPA y los colores —los del menú abajo y los de
    ; la imagen arriba, en el mismo flujo: ver tools/port/pantalla_completa.py—.
    ; Deja la pantalla apagada, BG1 en modo 3 y TM, la ventana y el color math
    ; en cero.
    ;
    ; **No la descomprime**: eso lo hizo el arranque, mientras esperaba sus
    ; BOOT_CUADROS, y `PANTALLA_BUFFER` la tiene desde ahí. Descomprimirla acá
    ; son nueve cuadros más de negro antes del título, y otros nueve al volver
    ; de la pantalla de ranuras —medido el 2026-09-28—. Vale porque nada de lo
    ; que corre en el título escribe el banco $7F: ni su lazo, ni la música, ni
    ; la pantalla de ranuras. El buffer pisa la grilla y los dibujos de la
    ; animación del ChipSet del mapa de arranque, y se puede porque de acá se
    ; sale siempre por `cargar_mapa`, que los rearma.
.ifdef ::PANTALLA_TITULO        ; sin pantalla de título no hay fila
    ldx #(PANTALLA_TITULO * PANTALLA_FILA)
    jsl f:pantalla_subir
.endif

    ; --- los tiles del menú ---
    ; Van en BG2, que en modo 3 tiene cuatro bits por pixel, así que cuestan la
    ; mitad. El tile 0 es transparente y le toca a casi toda la pantalla: es lo
    ; que deja ver la imagen debajo. `VMAIN` es el que dejó `pantalla_subir`.
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
    sta DMAP0                   ; dos registros, de a palabras
    lda #$18
    sta BBAD0                   ; destino: VMDATAL
    lda #$01
    sta MDMAEN

    ; --- y el PPU apuntando al menú ---
    lda #(TITULO_MENU_MAP / 1024 * 4)
    sta BG2SC                   ; tilemap de 32x32: los dos bits bajos en cero
    ; Las dos bases de tiles, que van de a 4096 palabras: BG1 en el nibble bajo
    ; —en cero, donde `pantalla_subir` puso la imagen— y BG2 en el alto.
    lda #(TITULO_MENU_VRAM / 4096 * 16)
    sta BG12NBA
    stz BG2HOFS
    stz BG2HOFS
    ; El PPU muestra la línea vofs+1 en el primer scanline, igual que en el
    ; mapa: con 0 el menú sale corrido una línea hacia arriba.
    lda #$FF
    sta BG2VOFS
    sta BG2VOFS
    lda #$03
    sta TM                      ; la imagen y el menú; sprites no hay

    stz titulo_sel              ; se entra con la primera opción elegida
    jsl f:titulo_subir_menu

    lda #$0F
    sta INIDISP                 ; y la pantalla encendida, al máximo
    rts
.endproc
; Lo que `pantalla_subir` pone en la VRAM no puede pisar lo del menú: los tiles
; de la imagen, a 32 palabras cada uno, van debajo del tilemap del menú, y los
; tiles del menú, a 16, terminan antes del tilemap de la imagen.
.assert TITULO_TILES * 32 <= TITULO_MENU_MAP, error, "los tiles del título pisan el tilemap del menú"
.assert TITULO_MENU_VRAM + TITULO_MENU_TILES * 16 <= PANTALLA_MAPA, error, "los tiles del menú del título pisan el tilemap de la imagen"

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
    ; **El tema del título se calla antes de cargar el mapa**, y no después
    ; con `music_boot`: `paquete_cargar` deja quietas las muestras del tema
    ; que dice estar sonando, y acá ése no suena. Con una partida cargada,
    ; `tema_actual` ya es el de la partida, y las muestras suyas que el
    ; paquete del título había subido quedaban fijas donde estaban,
    ; partiendo la ARAM: el paquete del mapa no entraba, y el `PlayBGM` del
    ; mapa lo volvía a subir entero —cargar en el mapa 1 tardaba el doble—.
    ; `music_apagada` se repone justo antes de `music_boot`, que lo lee: es el
    ; de la partida.
    lda music_apagada
    pha
    php
    sei                         ; el SPC700 atiende de a uno: ver `irq_musica`
    lda #1
    sta music_apagada
    lda #$FF
    ldx #SE_KOF
    jsr dsp_musica              ; como abajo: sin tocar las voces de efectos
    plp
    rep #$20
.a16
    lda 2, s                    ; el índice del mapa, detrás de music_apagada
    jsr cargar_mapa
    sep #$20
.a8
    pla                         ; el music_apagada de la partida
    plx                         ; el índice, que ya no hace falta
    pha
    jsr clear_oam
    jsr build_oam
    jsr flush_video
    pla
    sta music_apagada

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
    ; lo hay**, así que las voces del título se sueltan a mano. Con KOF y por
    ; `dsp_musica`, que deja afuera a las que tengan un efecto, y **no** con
    ; el volumen general, que es también el de los efectos: hasta el
    ; 2026-09-26 se bajaba ése, y los efectos quedaban mudos hasta el primer
    ; `PlayBGM`.
    php
    sei                         ; el SPC700 atiende de a uno: ver `irq_musica`
    lda #$FF
    ldx #SE_KOF
    jsr dsp_musica
    plp
listo_musica:
    lda #$0F
    sta INIDISP
    rts
.endproc

