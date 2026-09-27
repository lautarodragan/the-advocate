.segment "CODE"

; --- arranque --------------------------------------------------------------
.proc reset
    sei
    clc
    xce                         ; a modo nativo del 65816
    jml f:rapido + RAPIDO       ; al espejo rápido: ver MEMSEL
rapido:
    rep #$30                    ; A, X e Y de 16 bits
.a16
.i16
    ldx #$1FFF
    txs
    ; El banco de datos, en el del código. En un reset de verdad el 65816 lo
    ; deja en cero y todo lo de acá abajo funcionaría igual, pero desde el
    ; 2026-09-13 acá se llega también con un `jml` —el Game Over de
    ; `op_battle`— y ahí el banco de datos es el del bytecode, o sea un banco
    ; del cartucho: `sta INIDISP` escribiría la ROM en vez del PPU.
    phk
    plb

    sep #$20
.a8
    lda #$80
    sta INIDISP                 ; blanking forzado: la VRAM sólo se toca así
    ; La región no es un detalle cosmético: el stream de música está armado en
    ; cuadros, y una consola PAL da 50 por segundo en vez de 60. Sin corregirlo
    ; el tema suena un 17% lento.
    lda STAT78
    and #$10
    sta es_pal
    stz pal_tick

    jsr ppu_reset               ; la consola no arranca limpia; el emulador sí
    lda #$01
    sta MEMSEL                  ; la ROM del espejo, rápida
    jsr msu_detectar            ; ¿la música sale de una pista?

    ; Después del reset, no antes: ppu_reset apaga NMITIMEN junto con todo lo
    ; demás, así que habilitarlo primero no serviría de nada.
    lda #$01
    sta NMITIMEN                ; que la consola lea los controles sola
    stz boot_cuadros
    stz vueltas                 ; la RAM arranca con basura y el arnés lo
    stz vueltas + 1             ; lee desde el cuadro cero
    rep #$20
.a16
    lda #0
    sta f:vueltas_congeladas    ; y ésta, que las animaciones restan
    sep #$20
.a8
    lda #$81
    sta NMITIMEN                ; y la NMI, que cuenta los cuadros del arranque

    jsr ppu_init

    ; Sin entrada puesta: el primer mapa arranca donde diga su registro.
    rep #$20
.a16
    lda #$FFFF
    sta entrada_x
    sep #$20
.a8

    ; Los switches arrancan todos apagados, como una partida nueva de RM2k, y
    ; la pantalla sin teñir.
    ldx #$0000
borrar_switches:
    stz switches, x
    inx
    cpx #SWITCH_BYTES
    bne borrar_switches
    lda #TINTE_NEUTRO
    sta tinte_r
    sta tinte_g
    sta tinte_b
    sta tinte_s
    stz salto_hay
    lda #$FF                    ; ningún tema recordado, como una partida
    sta f:TEMA_RECORDADO        ; nueva: ver `op_memorized_bgm`
    stz anim_pend               ; la RAM arranca con basura y esto dispara DMAs
    stz panico                  ; la RAM arranca con basura, y 85 no es un código
    stz oro
    stz oro + 1
    stz oro + 2
    ; El grupo va antes de cargar el primer mapa: `cargar_mapa` elige con
    ; qué se dibuja el héroe, y sin esto leería la basura con la que
    ; arranca la RAM. El grupo con el que arranca la partida la partida, de la base del juego. El gráfico
    ; del héroe sale del primero, así que esto decide qué sprite se ve; que en
    ; este juego el actor 10 sea invisible es dato del juego, no un error.
    ldx #$0000
copiar_grupo:
    cpx #GRUPO_INICIAL_N
    beq grupo_listo
    lda grupo_inicial, x
    sta grupo, x
    inx
    bra copiar_grupo
grupo_listo:
    rep #$20
.a16
    lda #GRUPO_INICIAL_N
    sta grupo_n                 ; de 16 bits: X e Y lo comparan enteros
    sep #$20
.a8

    ; El intérprete y la ruta, en cero antes de cargar nada. La RAM arranca con
    ; basura y esto la lee en el primer cuadro: con `ev_esperando` en cualquier
    ; cosa se queda descontando para siempre y ninguna página corre, y con
    ; `ruta_i` menor que `ruta_n` `move_hero` cree que hay una ruta forzada
    ; pendiente y no lee el pad nunca —el héroe no se mueve—.
    ;
    ; Lo de la ruta lo encontró taro jugando en mednafen, no la tanda, y ésa es
    ; la parte que importa: **lo que snes9x deja en la RAM es siempre lo mismo**,
    ; así que esconde justo los errores que un patrón fijo esconde. Con estas dos
    ; sin inicializar, `ruta_i < ruta_n` da falso las diez corridas de snes9x y
    ; el error desaparece; en bsnes con entropía alta se ve. La tanda entera
    ; daba verde con esto adentro, y en hardware real habría fallado igual que
    ; en mednafen. Está medido: con estas dos sin inicializar a mano y diez
    ; corridas por core, snes9x da 0 de 10 en rojo y bsnes 2 de 10. Contra eso
    ; existe `pruebas/rpgmaker/test_cores.py`, que corre la misma ROM en snes9x y en
    ; bsnes —éste con `bsnes_entropy=High`— y compara las dos pantallas entre
    ; sí; ese archivo tiene el resto de los números. Verificado el 2026-09-16
    ; sacando estas dos líneas: de cinco corridas, cuatro en rojo.
    stz ev_activo
    jsr limpiar_esperas
    stz ruta_n                  ; sin ruta forzada pendiente
    stz ruta_i
    stz ruta_espera
    lda #8
    sta ruta_frec               ; la de siempre, hasta que un OP_ROUTE diga otra
    ; Y lo demás que una ruta deja prendido. La RAM arranca con basura —snes9x
    ; la llena de $55— así que sin esto el héroe arrancaría atravesando paredes
    ; y con la animación parada.
    stz ruta_salto
    stz ruta_atraviesa
    stz ruta_anim_para
    stz atravesando
    stz atravesando + 1
    stz tinte_pendiente
    ; Y la ventana de mensaje. `msg_abierto` en basura deja la página bloqueada
    ; para siempre: `eventos_tick` cree que hay un mensaje en pantalla y espera
    ; una A que ya no cierra nada. Está medido —sin este `stz`, `snes-cerrar` se
    ; cae en las doce corridas, y en snes9x además de en bsnes—.
    stz msg_abierto
    stz eleg_activo
    stz msg_estado
    stz msg_subir
    ; Los dos que dicen quién abrió el mensaje. En basura, `par_ev` haría que
    ; el primer plano anotara un dueño cualquiera y `un_paralelo` saltearía
    ; para siempre al evento que llevara ese número: es de los errores que
    ; `test_cores.py` ve y una golden no, porque bsnes arranca la WRAM con
    ; basura y snes9x en cero.
    lda #$FF
    sta msg_duenio
    sta par_ev
    ; Y su cola de escapes, por lo mismo: una pausa en basura frenaría la
    ; página igual que `msg_abierto`. Hoy no se leen sin que `msg_empezar` las
    ; haya escrito, pero eso vale mientras el guard de arriba siga siendo
    ; `msg_abierto | msg_estado`.
    rep #$20
.a16
    lda #0
    sta f:FAR_MSG_PAUSA         ; `stz` no tiene modo largo
    sep #$20
.a8
    sta f:FAR_MSG_AUTO
    ; Los dos del pad son por las dudas y no por un error visto: `read_pad`
    ; los reescribe antes de que nadie los mire. Cuestan dos instrucciones.
    stz pad_a
    stz pad_a_ant
    stz autofire
    lda #MOVIL_HEROE
    sta movil
    lda #CAPA_HEROE
    sta movil_capa
    stz sacudida_pos
    stz sacudida_pos + 1
    stz tinte_listo
    lda #VQ_POR_CUADRO
    sta vq_tope
    stz sacudida_resta
    stz sacudida_resta + 1
    stz destello_nivel          ; la RAM arranca con basura: sin esto el
    stz destello_nivel + 1      ; primer cuadro sale destellado
    stz destello_resta
    stz destello_listo
    rep #$20
.a16
    stz ev_esperando
    stz ev_cur
    sep #$20
.a8

    ; Mirando a cámara, como arranca RM2k. Va antes de cargar el primer mapa
    ; porque ahí corren sus eventos, y una ruta forzada puede girarlo: si esto
    ; quedara después, pisaría lo que la ruta acaba de decidir.
    lda #DIR_DOWN
    sta hero_dir

    ; El cronómetro arranca apagado y en cero. Va acá y no en `cargar_mapa`
    ; porque en RM2k vive en `Game_Party`: sobrevive a los mapas, que es
    ; justamente para lo que el juego lo usa. La RAM arranca con basura —snes9x
    ; la llena de $55— así que sin esto se vería corriendo solo.
    stz timer_activo
    stz timer_visible
    stz timer_sub
    rep #$20
.a16
    stz timer_seg
    sep #$20
.a8
    jsr timer_digitos

    ; La RAM arranca con basura —snes9x la llena de $55— y `flush_video` mira
    ; las dos: sin esto el primer vblank prendería la pantalla con el brillo que
    ; hubiera quedado, y el lazo arrancaría creyéndose adentro de un fundido.
    stz fundido
    lda #BRILLO_MAX
    sta brillo
    stz bgm_fundido             ; y lo mismo con el del tema
    jsl f:transicion_de_arranque    ; y el teletransporte, con fundido
    jsl f:encuentro_arranque    ; la semilla del azar de los encuentros

    ; Si el cartucho tiene una partida guardada, se carga acá: los switches que
    ; trae deciden qué página está activa en cada evento, así que tienen que
    ; estar puestos **antes** de cargar el mapa. Y la entrada se arma con la
    ; celda guardada, que es como una puerta le dice a `cargar_mapa` dónde
    ; plantar al héroe.
    lda #$FF
    sta ranura                  ; ninguna cargada; la RAM arranca con basura
    ; La semilla del azar, y las variables en cero: la RAM lejana también
    ; arranca con basura, y una partida cargada las pisa después.
    jsr limpiar_variables
    jsr equipo_inicial_poner
    jsl f:hp_inicial_poner
    jsl f:hab_inicial_poner
    jsr actor_graf_limpiar
    jsr clima_limpiar
    jsr se_limpiar
    jsr musica_limpiar
    jsr giro_limpiar
    jsr aram_limpiar
    jsr animacion_limpiar
    lda #0                      ; la RAM arranca con basura
    sta f:CARTEL_ACTIVA
    sta f:CARTEL_LISTO
    ; El testigo de la pantalla de ranuras también: con $55 el arnés la vería
    ; abierta desde el reset. Es lo que pasó el 2026-09-10 con los dos
    ; contadores que "daban 85": leían la basura del emulador.
    stz menu_abierto
    ; Con pantalla de título esto no se hace acá: cargar o empezar de nuevo lo
    ; decide el menú, y hasta que el jugador elija la partida guardada no se
    ; toca. Sin pantalla de título —que es toda la tanda— sigue pasando lo de
    ; siempre, o sea que si hay partida se carga sola.
    lda #<TITULO_TILES
    ora #>TITULO_TILES
    bne nueva
    lda #0                      ; sin menú que elija, siempre la primera
    jsr poner_ranura
    jsr cargar_partida
    beq nueva
    jsr entrada_de_la_partida
    rep #$20
.a16
    lda mapa_actual             ; el índice va en dieciséis bits
    bra cargar
.a8
nueva:
    rep #$20
.a16
    lda #MAPA_INICIAL
cargar:
    jsr cargar_mapa
    sep #$20
.a8
    jsr clear_oam

    stz step_left               ; parado, sin paso en curso
    stz pad                     ; la RAM arranca con basura y move_hero la lee
    lda #1
    sta anim_step               ; el frame del medio: la pose parada
    stz anim_timer

    jsr build_oam
    jsr flush_video

    lda #$0F
    sta INIDISP                 ; pantalla encendida, brillo al máximo

    ; La subida al SPC700 va después de prender la pantalla, no antes: con el
    ; paquete de audio del mapa es un tercio de segundo, y así el mapa aparece
    ; de entrada en vez de hacerte mirar una pantalla negra hasta que termine.
    ;
    ; Y antes de subir nada, el comando 4: **que el SPC700 vuelva a su ROM del
    ; IPL**. Acá se llega de dos maneras y sólo una de las dos deja al SPC700
    ; como recién encendido. Con el botón de reset de la consola la línea les
    ; llega a los dos procesadores y el IPL arranca solo; con el `jml reset`
    ; del Game Over de `op_battle`, no: el SPC700 sigue corriendo el driver y
    ; el saludo $AA/$BB que `spc_upload` espera no llega **nunca**. Ése era el
    ; cuelgue del cofre trampa de los Rat Tracks —pantalla encendida, mapa
    ; dibujado y el juego clavado—, y el mismo lo tenía cualquier Game Over.
    ;
    ; Con el IPL corriendo esto no molesta: mientras espera el $CC mira el
    ; puerto 0, y acá se escriben el 2 y el 3. El testigo se incrementa sin
    ; esperar acuse, porque del otro lado ya no queda quién lo devuelva.
    lda #APU_CMD_IPL
    sta APUIO2
    inc token
    lda token
    sta APUIO3
    jsr spc_upload
    ; El puerto 2 es el comando del driver, y `spc_upload` lo deja con lo que
    ; haya mandado último: en cero, el driver lee pares del DSP.
    stz APUIO2
    ; Y el paquete de audio del mapa de arranque: `cargar_mapa` no lo pudo
    ; subir porque el driver todavía no corría. Ver `paquete_cargar`.
    lda #1
    sta f:APU_LISTO
    jsr paquete_cargar
    jsr music_boot

    ; Y se espera a que el arranque dure lo que dura siempre: BOOT_CUADROS.
espera_boot:
    lda boot_cuadros
    cmp #BOOT_CUADROS
    bcc espera_boot
    ; La NMI sigue contando después del arranque: es la única forma de saber
    ; si una vuelta del lazo se pasó del cuadro. Ver `contar_perdidos`.
    lda boot_cuadros
    sta nmi_visto
    stz cuadros_perdidos

    ; Y desde acá la música corre sola, en `irq_musica`: una vez por cuadro
    ; en la línea IRQ_LINEA, tarde lo que tarde el lazo. Va después de la
    ; espera y no antes para que el tema arranque en el mismo cuadro que
    ; cuando la tocaba el lazo.
    lda #<IRQ_LINEA
    sta VTIMEL
    lda #>IRQ_LINEA
    sta VTIMEH
    lda #$A1
    sta NMITIMEN                ; la NMI, los controles y la IRQ vertical
    cli

    ; La pantalla de título, si esta ROM la lleva. Va **después** de que el
    ; arranque terminó de contar sus BOOT_CUADROS y no antes: así una ROM sin
    ; título llega al lazo exactamente en el cuadro de siempre, y los 96 casos
    ; de la tanda —que cuentan cuadros desde el reset— no se enteran de que
    ; esto existe.
    jsr pantalla_titulo

loop:
    jsr wait_vblank
    ; El control primero: la consola lo lee sola al empezar el vblank y hay que
    ; esperar a que arranque. Si antes se hiciera algo largo —el DMA de OAM, por
    ; ejemplo— se llegaría con la lectura ya terminada, y esperar su arranque
    ; significaría esperar al cuadro siguiente: medio cuadro por vuelta.
    jsr read_pad
    jsr flush_video             ; lo del cuadro anterior, todavía en vblank
    ; El fundido de un teletransporte congela el juego entero mientras dura,
    ; como RM2k: lo único que sigue corriendo es la música. Ver `fundido_tick`.
    jsr fundido_tick
    bne congelado
    ; De acá abajo el cuadro sigue el orden de `Game_Map::Update`
    ; —`game_map.cpp:1256-1318` de easyrpg—, y lo que manda es **dónde cae el
    ; jugador**: allá `UpdateMapEvents` va antes de `game_player->Update()`
    ; (`:1274` contra `:1288`) y `UpdateForegroundEvents` va después (`:1310`),
    ; con `UpdateMessage` (`:1297`) y `UpdateTimers` (`:1304`) en el medio.
    ;
    ; Lo que **no** está en ese orden son los ticks de pantalla —el destello,
    ; la sacudida, la cámara corrida, el cartel, la lluvia—: allá son
    ; `game_screen->Update()` y `game_pictures->Update()` y van en `:1305`, o
    ; sea antes del intérprete, y acá van después. Ninguno de ellos decide si
    ; algo se mueve ni cuándo, así que la diferencia es de un cuadro en lo que
    ; se ve y no en lo que pasa; moverlos es otro cambio, con sus goldens.
    jsr eventos_de_mapa         ; `UpdateMapEvents`: refresco, automáticas y
                                ; paralelos, **antes** del héroe
    jsr animar_quietos          ; los que animan sin moverse, antes que las
                                ; rutas: si una agarra a uno, gana la ranura
    jsr mover_eventos           ; y las rutas forzadas de los eventos, que son
                                ; la parte de `UpdateMapEvents` que camina
                                ; —`Game_Character::Update()` desde
                                ; `Game_Event::Update`, `game_event.cpp:608`—.
                                ; Van acá y no después del intérprete para que
                                ; un evento y el héroe arranquen la ruta que
                                ; una página les acaba de poner en el mismo
                                ; cuadro: los dos, en el que viene. Con el
                                ; intérprete todavía arriba del héroe los dos
                                ; arrancaban un cuadro antes y empataban; con
                                ; él abajo, dejarlos acá abajo desempataba, y
                                ; `parar-rutas` lo mostraba con el NPC
                                ; adelantado un cuadro respecto del héroe.
    jsr move_hero               ; `game_player->Update()`
    jsr pedir_menu              ; B, al final del héroe: ver `pedir_menu`
    ; El cronómetro va **antes** del intérprete, que es donde lo pone
    ; `Game_Map::Update`: `UpdateTimers()` corre y recién después
    ; `UpdateForegroundEvents`. O sea que la página que lo arranca no se lleva
    ; un cuadro en el mismo cuadro en que lo arranca. Después del intérprete
    ; la ROM iba un cuadro adelante de RM2k para siempre, y se veía sólo en los
    ; cuadros en que los dos puntos parpadean o cambia un dígito.
    jsr timer_tick
    ; `UpdateForegroundEvents`, **después** del héroe: lo que el paso recién
    ; terminado encoló —un evento de contacto, un cofre, una trampa— arranca en
    ; este mismo cuadro y no en el que viene. Estuvo arriba de `move_hero`
    ; hasta el 2026-09-20, y eso le costaba un cuadro a todo contacto: el
    ; barrido de la cola ya había pasado cuando `advance_step` la llenaba.
    jsr eventos_tick
    jsr tinte_de_evento         ; el tinte que haya pedido el intérprete, pegado
                                ; a él: si no, lo aplicaría un cuadro tarde
    jsr animacion_tick          ; la animación de batalla, antes que los
                                ; destellos que dispara
    jsr animacion_dibujo_tick   ; y su dibujo, pegado: los dos avanzan el
                                ; mismo reloj de RM2k y el dibujo dura más
    jsr flashes_tick            ; y los destellos, en el mismo lugar
    jsr sacudida_tick           ; y uno de la sacudida de pantalla
    jsr pan_tick                ; y uno de la cámara corrida sin el héroe
    jsr imagen_tick             ; y uno del fundido del cartel. Va **antes**
                                ; del destello y no después: los dos arman su
                                ; paleta en `pal_buf`, y el destello deja la
                                ; suya ahí esperando el vblank. Al revés, el
                                ; cartel le pisaba los primeros dieciséis
                                ; colores del fondo en el cuadro en que los
                                ; dos corren.
    jsr destello_tick           ; y uno del destello de pantalla
    jsr lluvia_tick             ; y uno de la lluvia
    jsr animate_hero
    jsr follow_camera
    jsr stream_map              ; la columna o la fila que la cámara destapó
    jsr mensaje_tick            ; y unos caracteres del mensaje que se esté
                                ; componiendo, si hay alguno
    jsr build_oam               ; y se arma el siguiente, ya fuera del vblank
    bra contada
congelado:
    ; Una vuelta del fundido: el tick corre —el fundido y el arnés lo cuentan—
    ; pero el mundo no, y las animaciones del mapa tampoco. Ver
    ; `vueltas_congeladas`.
    rep #$20
.a16
    lda f:vueltas_congeladas
    inc a
    sta f:vueltas_congeladas
    sep #$20
.a8
contada:
    rep #$20
.a16
    inc vueltas
    sep #$20
.a8
    jsr anim_tick               ; qué dibujo del ChipSet toca en la vuelta que
                                ; viene, para que el vblank sólo tenga que subirlo
    jsr contar_perdidos
    bra loop
.endproc

; Cuántos vblanks pasaron desde la vuelta anterior: uno es lo normal, y cada
; uno de más es un cuadro que la ROM perdió, porque la vuelta tardó más que un
; cuadro y `wait_vblank` tuvo que esperar al siguiente. Se mira acá, al final
; de la vuelta, y no a la salida de `wait_vblank`: ahí la NMI de este cuadro
; puede no haber corrido todavía. Contra una golden un cuadro perdido es
; una posición atrasada, y la comparación lo cobra en pixeles sin decir por
; qué; este contador dice por qué. Lo leen las pruebas por la WRAM del
; emulador —`Partida.cuadros_perdidos`—, y en la consola no lo lee nadie.
; Satura en 255.
.proc contar_perdidos
.a8
.i16
    lda boot_cuadros
    sec
    sbc nmi_visto
    dec a                       ; el vblank que le tocaba a esta vuelta
    beq al_dia
    clc
    adc cuadros_perdidos
    bcc cabe
    lda #255
cabe:
    sta cuadros_perdidos
al_dia:
    lda boot_cuadros
    sta nmi_visto
    rts
.endproc

; Se acabó: algo que no puede pasar pasó. A trae el código, que queda en
; `panico` para que una prueba de estado pueda decir cuál fue.
;
; No hay `printf` en una SNES y volver de acá no tiene sentido —el estado ya es
; inconsistente—, así que lo que queda es que se vea: la pantalla parpadea entre
; negro y pleno para siempre. Es feo a propósito. Lo que se quiere evitar es lo
; contrario, que el juego siga andando como si nada y el error aparezca media
; hora después convertido en otra cosa.
.proc entrar_en_panico
.a8
.i16
    sta panico
    sei                         ; ni siquiera el vblank: nada más va a pasar
lazo:
    ldx #$2000
espera_prendido:
    dex
    bne espera_prendido
    lda #$0F
    sta INIDISP
    ldx #$2000
espera_apagado:
    dex
    bne espera_apagado
    lda #$80
    sta INIDISP
    bra lazo
.endproc

; --- espera de vblank ------------------------------------------------------
; Sin NMI habilitada, se mira la bandera de HVBJOY: primero que salga del
; vblank anterior y después que entre al siguiente.
; La NMI: suma un cuadro y baja la bandera. No toca nada más, y deja P como
; estaba porque `rti` lo saca de la pila. Corre durante el arranque, para que
; dure siempre lo mismo, y después también: ver `contar_perdidos`.
.proc nmi_boot
    sep #$20
.a8
    pha
    ; **El banco de datos, fijado acá y no heredado.** `boot_cuadros` y
    ; `RDNMI` se leen con direccionamiento absoluto, así que van al banco de
    ; datos que tenga el código al que la NMI interrumpió. Guardar y cargar
    ; corren con el banco en la SRAM, y una NMI que cayera ahí le sumaba uno a
    ; `$70:1C07` —el byte 769 de la cuarta ranura— en vez de a `boot_cuadros`:
    ; la suma de control dejaba de dar y la ranura 4 cargaba como vacía. Las
    ; otras tres no pasan por esa dirección, que es por qué fallaba una sola.
    ; `phk` da el banco 0, porque los vectores corren ahí, y en el 0 están la
    ; WRAM baja y los registros.
    phb
    phk
    plb
    inc boot_cuadros
    lda RDNMI
    plb
    pla
    rti
.endproc

.proc wait_vblank
.a8
.i16
out:
    lda HVBJOY
    bmi out
in:
    lda HVBJOY
    bpl in
    rts
.endproc

; --- puesta a cero del PPU -------------------------------------------------
; El emulador arranca con todos los registros en cero. La consola real no: se
; queda con lo que dejó el programa anterior, que en un EverDrive es su menú.
; Si ese menú dejó encendido el color math, el sub-screen, una ventana o un
; canal de HDMA, todo eso sigue funcionando debajo de nuestro mapa aunque
; nosotros no lo hayamos pedido.
;
; Por eso no alcanza con escribir los registros que usamos: hay que escribir
; todos.
.proc ppu_reset
.a8
.i16
    lda #$80
    sta INIDISP                 ; blanking forzado antes de tocar nada

    ; Lo primero es cortar el DMA por scanline: si quedó un canal activo, sigue
    ; escribiendo registros del PPU en cada línea y nada de lo que hagamos acá
    ; se sostiene.
    stz HDMAEN
    stz MDMAEN
    stz NMITIMEN

    ; Los registros del PPU con valores conocidos, en dos tramos: los de scroll
    ; quedan en el medio y necesitan otro tratamiento.
    ldx #$0000
bajos:
    lda f:ppu_bajos, x
    sta $2101, x
    inx
    cpx #(ppu_bajos_end - ppu_bajos)
    bne bajos

    ldx #$0000
altos:
    lda f:ppu_altos, x
    sta $2115, x
    inx
    cpx #(ppu_altos_end - ppu_altos)
    bne altos

    ; Los ocho registros de scroll: cada uno se escribe dos veces, byte bajo y
    ; byte alto, o el latch queda a medias.
    ldx #$0000
scrolls:
    stz $210D, x
    stz $210D, x
    inx
    cpx #8
    bne scrolls

    ; La VRAM entera a cero, por DMA con la fuente fija en un byte nulo. Sin
    ; esto quedan los tiles del menú donde no llegan los nuestros.
    lda #$80
    sta VMAIN
    ldx #$0000
    stx VMADDL
    ldx #.loword(cero)
    stx A1T0L
    lda #^cero
    sta A1B0
    ldx #$0000                  ; 0 significa 65536: la VRAM completa
    stx DAS0L
    lda #$09                    ; dos registros, de a palabras, fuente fija
    sta DMAP0
    lda #$18
    sta BBAD0
    lda #$01
    sta MDMAEN

    ; Y CGRAM, que si no deja la paleta del menú en los colores que no usamos.
    stz CGADD
    ldx #.loword(cero)
    stx A1T0L
    lda #^cero
    sta A1B0
    ldx #512
    stx DAS0L
    lda #$08                    ; un registro, de a bytes, fuente fija
    sta DMAP0
    lda #$22
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc

; De $2101 a $210C: objetos, modo, mosaico y dónde vive cada capa. Todo en
; cero, que es "nada encendido".
.segment "TABLAS"

; Lo que **tiene** que vivir en el banco 0: se lee con `lda tabla, y`, y el
; 65816 no tiene absoluto largo indexado por Y —`long,X` sí, `long,Y` no—, o
; con tantos índices distintos que el byte de más por acceso costaría más que
; la tabla. Las que se leen con X y se leen poco fueron bajando a RODATA a lo
; largo del 2026-09-13, en tres vueltas distintas y por el mismo motivo: hacer
; lugar. En `banco1.s` está el porqué de cada una y lo que todavía se podría bajar.

; `salto_por_vel` bajó a RODATA el 2026-09-14: un solo acceso, y pasarlo por X
; cuesta cuatro bytes contra los seis de la tabla. Ver `banco1.s`.
; Cada cuántos cuadros cambia el frame de la caminata, por velocidad: caminando
; y quieto con la animación continua: `GetStationaryAnimFrames` y
; `GetContinuousAnimFrames` de `Game_Character::UpdateAnimation`.
anim_parado:
    .byte 12, 10, 8, 6, 5, 4
anim_continua:
    .byte 16, 12, 10, 8, 7, 6


.segment "CODE"

; --- el PPU ----------------------------------------------------------------
; Modo 3: BG1 con 8 bits por pixel. Ahí cada pixel es un índice directo a CGRAM
; y no hay paleta por tile, así que el mapa entra con sus 60 colores sin
; fusionar ninguno. Cuesta el doble de VRAM por tile y sobra lugar de todas
; formas.
.proc ppu_init
.a8
.i16
    lda #$03
    sta BGMODE
    ; BG2SC lleva la dirección del tilemap en el byte alto y el tamaño en los
    ; dos bits bajos; con VRAM_ABOVE_MAP en $7800 y el tamaño 1 —dos pantallas
    ; de 32x32 una al lado de la otra, o sea 64x32— queda $79.
    lda #>VRAM_ABOVE_MAP | MAP_LAYOUT
    sta BG2SC                   ; la ventana de la capa de encima
    ; BG12NBA y BG1SC salen del mapa, así que los pone cargar_mapa —y
    ; `volver_al_mapa`—. Acá quedarían con el valor del mapa anterior en cuanto
    ; haya más de uno: el tilemap del fondo no está en el mismo lugar en todos
    ; los repartos, ver LAYOUT_VENTANA_AMBOS.
    stz BG1HOFS                 ; el scroll es de dos escrituras, byte bajo
    stz BG1HOFS                 ; y byte alto
    ; El PPU muestra la línea vofs+1 en el primer scanline visible, no la vofs.
    ; Con 0 el mapa queda corrido una línea hacia arriba; con -1 cae en su
    ; lugar. Lo destapó la comparación pixel a pixel contra el render de Python:
    ; a ojo las dos imágenes se veían idénticas.
    lda #$FF
    sta BG1VOFS
    sta BG1VOFS
    lda #$13
    sta TM                      ; las dos capas del mapa y los sprites
    rts
.endproc

