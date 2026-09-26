.segment "CODE"

; --- música ----------------------------------------------------------------
; El stream es por nota: notas, releases, cambios de volumen o de altura de una
; voz que suena, y esperas; `music_frame` lo expande a escrituras al DSP. Los
; opcodes los declara `tools/protocol/music.toml` y el equate sale generado:
; hasta el 2026-09-15 estaban escritos a mano acá **y** en
; tools/audio/snes_music.py, que es el que escribe el stream, sin nada que atara
; las dos copias.

; Un cuadro de música por cuadro de video, más uno extra cada cinco si la
; consola es PAL: seis cada cinco son exactamente 60 por cada 50.
.proc irq_musica
    jml f:rapida + RAPIDO       ; el vector cae en el banco 0: ver MEMSEL
rapida:
    ; Todo lo que se toca se guarda, B y D incluidos: se cae en el medio de
    ; cualquier cosa, el intérprete con B apuntando al bytecode entre ellas.
    rep #$30
.a16
.i16
    pha
    phx
    phy
    phb
    phd
    lda #0
    pha
    pld                         ; la página directa en cero
    sep #$20
.a8
    phk
    plb                         ; las tablas de la música, en el banco 0
    lda TIMEUP                  ; baja la bandera: si no, vuelve a entrar
    jsr music_tick
    rep #$30
.a16
.i16
    pld
    plb
    ply
    plx
    pla
    rti
.endproc

.proc music_tick
.a8
.i16
    ; El `FadeOutBGM` primero, y **afuera** del guard de `music_apagada`: es lo
    ; que lo va a prender cuando el volumen llegue a cero.
    lda bgm_fundido
    beq sin_fundido
    jsr bgm_fundido_tick
sin_fundido:
    ; Los efectos de sonido rodean a la música, y corren aunque esté callada:
    ; ver "los efectos de sonido".
    jsr se_antes
    lda music_apagada
    bne listo
    jsr music_frame
    lda es_pal
    beq listo
    inc pal_tick
    lda pal_tick
    cmp #5
    bcc listo
    stz pal_tick
    jsr music_frame             ; el cuadro que le falta a PAL
listo:
    jmp se_despues
.endproc

; Arranca desde el principio el tema cuyo índice trae A. El comienzo del stream
; trae la puesta a punto del DSP —los volúmenes, el directorio de muestras— así
; que volver a llamar acá es exactamente lo que hace un `PlayBGM`: empezar de
; cero.
;
; El cartucho lleva varios temas desde el 2026-09-06 y **todos comparten el
; banco de muestras**, que se sube una sola vez al arrancar: cambiar de tema es
; cambiar de stream y nada más, o sea que no cuesta ni un cuadro. De ahí que
; acá no haya nada que subir. Ver `Banco` en tools/audio/snes_music.py.
;
; Qué índice está sonando queda en `tema_actual`, que es lo que `music_frame`
; necesita para volver a empezar cuando el stream termina: sin eso el loop
; volvía siempre al primero.
.proc music_start
.a8
.i16
    ; El código principal la llama con la música andando —`PlayBGM`, el
    ; título—, y cambiar el puntero a medias con `irq_musica` leyéndolo sería
    ; tocar un tema desde la mitad de otro.
    pha
    jsr msu_parar               ; la pista de antes, si había
    pla
    pha
    jsr msu_arrancar
    beq sin_pista
    ; Con pista, el SPC700 se calla: el stream no corre y las voces sueltan.
    pla
    sta tema_actual
    stz tema_actual + 1
    php
    sei
    lda #1
    sta music_apagada
    stz bgm_fundido
    lda #$FF
    ldx #SE_KOF
    jsr dsp_par                 ; las ocho voces sueltan, y KOF queda puesto
    ; Y el DSP hay que ponerlo a punto acá, que es lo que no estaba: lo hace
    ; el comienzo del stream —FLG sin el mute con que arranca el SPC700, el
    ; volumen general, y dónde está el directorio de muestras— y con pista el
    ; stream no corre nunca. Sin esto los efectos de sonido se disparan contra
    ; un DSP mudo: medido en la apertura, correr con el efecto y con el efecto
    ; suprimido daba **cero** muestras de diferencia.
    ;
    ; KOF se queda en $FF, que es lo que mantiene calladas las voces de la
    ; música; `se_despues` lo limpia solo cuando arranca un efecto.
    ldy #0
otro_init:
    lda dsp_init_reg, y
    cmp #$FF
    beq init_listo
    tax                         ; dsp_par mira sólo el byte bajo de X
    lda dsp_init_val, y
    jsr dsp_par
    iny
    bra otro_init
init_listo:
    plp
    rts
sin_pista:
    ; El tema se queda en la pila: `tema_asegurar` pisa el acumulador, y
    ; `music_start_ya` lo necesita. Sacarlo antes dejaba el tema en $FF, el
    ; puntero del stream fuera de su tabla y la ROM muda a los diez cuadros.
    pla
    pha
    jsr tema_asegurar           ; que sus muestras estén en la ARAM
    pla
    php
    sei
    jsr music_start_ya
    plp
    rts
.endproc

.proc music_start_ya
.a8
.i16
    sta tema_actual
    stz tema_actual + 1
    ldx tema_actual
    lda tema_lo, x
    sta music
    lda tema_hi, x
    sta music + 1
    lda tema_bk, x
    sta music + 2
    ; El decodificador de cero: sin espera, sin disparos pendientes, y con el
    ; caché sin nada que valga —la primera nota de cada voz lo reescribe—.
    ; Pasa también al volver al principio del tema, y es lo que hace que la
    ; segunda vuelta escriba lo mismo que la primera.
    lda #0
    sta f:MUS_KON
    sta f:MUS_SONANDO
    sta f:MUS_VISTAS
    sta f:MUS_GAINS
    rep #$20
.a16
    lda #0                      ; de nuevo: el `lda #0` de ocho bits no
    sta f:MUS_ESPERA            ; limpió B, y la espera es de dieciséis
    lda tema_actual
    asl a
    tax
    lda f:tema_sonidos, x
    sta f:MUS_BASE
    sep #$20
.a8
    stz music_apagada
    ; Y se cancela el fundido que hubiera: el stream vuelve a escribir el
    ; volumen general al arrancar, así que seguir bajándolo apagaría el tema
    ; que el `PlayBGM` acaba de prender.
    stz bgm_fundido
    rts
.endproc

; Un cuadro del `FadeOutBGM`: baja el volumen general del DSP y, cuando llega a
; cero, corta el tema. Es `Game_System::BgmFade`, que en RM2k tampoco bloquea a
; la página que lo pidió.
;
; El nivel es de dieciséis bits y va de 65535 a cero; el volumen que se escribe
; es `TEMA_VOLUMEN` por su byte alto, con el multiplicador del hardware. La
; alternativa —bajar el registro de siete bits de a uno— daría noventa y seis
; escalones para un fundido de trescientos cuadros y se oiría a escalones.
.proc bgm_fundido_tick
.a8
.i16
    rep #$20
.a16
    lda bgm_nivel
    sec
    sbc bgm_paso
    bcs baja                    ; todavía queda
    lda #0
baja:
    sta bgm_nivel
    sep #$20
.a8
    lda bgm_nivel
    ora bgm_nivel + 1
    bne sigue
    stz bgm_fundido
    lda #1
    sta music_apagada           ; el tema se corta, como `BgmFade`
sigue:
    ; TEMA_VOLUMEN por el nivel, entre 256. **No con el multiplicador**: esto
    ; corre en `irq_musica`, y el código principal lo usa en treinta lugares
    ; —el divisor comparte el registro del resultado—; una interrupción entre
    ; su escritura y su lectura le cambiaría la cuenta. Así que a mano, de a
    ; un bit del nivel, con `dsp_valor` de lugar: es sólo de la música.
    ; El factor es el techo de lo que se está fundiendo: el volumen del tema
    ; si suena el SPC700, y el de la pista si hay MSU-1 —que no es 255, ver
    ; MSU_VOLUMEN_MAX—. Es un solo producto y un solo camino: con dos, el del
    ; MSU-1 se equivocaría solo.
    ldy #TEMA_VOLUMEN
    lda f:MSU_SUENA
    beq con_factor
    ldy #MSU_VOLUMEN_MAX
con_factor:
    rep #$20
.a16
    tya
    sta f:MSU_FACTOR            ; el lazo lo suma con `adc f:`: no hay dónde
    sep #$20                    ; tener un parcial, y `,s` no existe acá
.a8
    lda bgm_nivel + 1
    sta dsp_valor
    ldx #8
    rep #$20
.a16
    lda #0
bit_del_nivel:
    asl a
    sep #$20
.a8
    asl dsp_valor               ; sep y rep no tocan el carry
    rep #$20
.a16
    bcc sin_sumar
    clc
    adc f:MSU_FACTOR
sin_sumar:
    dex
    bne bit_del_nivel
    xba                         ; el byte alto del producto, o sea entre 256
    sep #$20
.a8
    sta dsp_valor
    ; Y lo mismo para la pista del MSU-1, que es la que suena si hay: el
    ; `FadeOutBGM` la baja igual. Al llegar a cero se corta.
    lda f:MSU_SUENA
    beq sin_msu
    ; Con pista, el fundido baja **su** volumen y no el del DSP. El volumen
    ; general del SPC700 es el que oyen los efectos de sonido, así que bajarlo
    ; acá los dejaba mudos hasta el `PlayBGM` siguiente, que es el único que lo
    ; repone.
    ;
    ; El producto ya está hecho arriba, y con el factor de la pista: `dsp_valor`
    ; es el nivel escalado contra MSU_VOLUMEN_MAX, que es el techo de la pista y
    ; no 255. Acá no hay ninguna cuenta que rehacer.
    lda dsp_valor
    sta MSU_VOLUMEN
    bne listo_msu
    jsr msu_parar               ; llegó a cero: la pista se corta
listo_msu:
    rts
sin_msu:
    lda #DSP_MVOL_L
    jsr escribir_dsp
    lda #DSP_MVOL_R
    jsr escribir_dsp
    rts
.endproc

; Le escribe `dsp_valor` al registro que trae A, con el testigo del SPC700. Es
; el mismo protocolo que usa `music_frame` con cada escritura del stream.
.proc escribir_dsp
.a8
.i16
    sta APUIO0
    lda dsp_valor
    sta APUIO1
    inc token                   ; el testigo le avisa al SPC700 que hay algo
    lda token
    sta APUIO3
espera:
    cmp APUIO3
    bne espera
    rts
.endproc

; La música al arrancar la ROM. `TEMA_ARRANQUE` es el tema del mapa donde la
; ROM arranca, o $FF si ese mapa no tiene —que es lo normal en este juego: los
; primeros mapas no traen música y la prende un `PlayBGM`—. Callado quiere
; decir que al DSP no se le escribe nada, así que no hay nada que silenciar.
.proc music_boot
.a8
.i16
    php
    sei
    jsr music_boot_ya
    plp
    rts
.endproc

.proc music_boot_ya
.a8
.i16
    ; Una partida cargada trae su propio tema —el que prendió el `PlayBGM` del
    ; evento— y `cargar_partida` ya lo dejó en `tema_actual` y `music_apagada`.
    ; Sin esto la partida arrancaría con el tema del mapa inicial de la ROM,
    ; que es el de la apertura y no el del lugar donde uno guardó.
    lda ranura
    cmp #$FF
    beq del_mapa                ; ninguna ranura cargada: el tema del mapa
    lda music_apagada
    bne callado                 ; se guardó en un momento sin música
    lda tema_actual
    jmp music_start
del_mapa:
    lda #TEMA_ARRANQUE
    cmp #$FF
    bne suena
callado:
    lda #1
    sta music_apagada
    rts
suena:
    jmp music_start
.endproc

; Avanza el puntero de música un byte, devolviendo en A lo que ya se leyó.
;
; En LoROM cada banco expone sólo su mitad alta, $8000-$FFFF, así que el byte
; que sigue a $00FFFF no es $010000 sino $018000. Un incremento común de 24 bits
; caería en la RAM del banco 1 y leería basura. Con el tema entero más las
; muestras pasando los 64 KB, esto no es teórico: se cruza sí o sí.
.proc advance
.a8
.i16
; El acumulador trae el byte que el llamador acaba de leer, así que hay que
; devolverlo intacto: por eso el pha/pla en la rama del salto de banco.
    inc music
    bne done
alto:                           ; donde sigue `LEER` cuando el byte bajo dio la vuelta
    inc music + 1
    bne done                    ; si la parte alta no dio la vuelta, listo
    pha
    lda #$80                    ; dio la vuelta: al banco siguiente, en $8000
    sta music + 1
    pla
    inc music + 2
done:
    rts
.endproc

; `lda [music]` y `jsr advance`, sin el `jsr` en el caso de siempre: es lo que
; más se repite por evento, y el byte bajo del puntero da la vuelta una vez
; cada 256.
.macro LEER
    .local listo
    lda [music]
    inc music
    bne listo
    jsr advance::alto
listo:
.endmacro

; Un cuadro de música. El stream es por nota —ver "el formato por nota" en
; tools/audio/snes_music.py y el encabezado de tools/protocol/music.toml— y
; acá se expande a las escrituras al DSP que manda `dsp_musica`: exactamente
; las de `escrituras`, cuadro por cuadro. Se lee hasta toparse con una
; espera, que cierra el cuadro: dispara las voces que recibieron nota, y el
; cuadro siguiente abre bajando ese disparo. Al llegar al final vuelve a
; empezar.
;
; Volver a empezar tiene una trampa: un stream **vacío** es un OP_END solo, así
; que reiniciar lleva a leer OP_END otra vez y el lazo no sale nunca. La ROM se
; colgaba en el primer cuadro, con la pantalla ya encendida y el mapa dibujado
; —o sea que parecía andar—. Estuvo escondido todo este tiempo porque
; `musicdata.inc` lo generaba una receta aparte y siempre tenía un tema de
; verdad; apareció apenas el conversor empezó a emitir la música del mapa, y la
; mayoría de los mapas del juego no tienen ninguna.
;
; La guarda es no reiniciar dos veces en el mismo cuadro: si después de volver
; al principio lo primero que hay es otro final, no hay nada que tocar.
.proc music_frame
.a8
.i16
    stz reinicio
    rep #$20
.a16
    lda f:MUS_ESPERA
    beq abrir
    dec a
    sta f:MUS_ESPERA
    sep #$20
.a8
    rts

abrir:
.a16
    sep #$20
.a8
    lda f:MUS_SONANDO           ; bajar el disparo del cuadro anterior
    beq leer
    lda #0
    sta f:MUS_SONANDO
    ldx #SE_KON
    jsr dsp_musica

leer:
    LEER
    cmp #OP_WAIT_1
    bcs no_es_de_voz
    jmp de_voz
no_es_de_voz:
    cmp #OP_WAIT
    bcc espera_corta
    beq espera_larga
    cmp #OP_DSP
    beq cruda
    cmp #OP_INIT
    bne no_init
    jmp arranque
no_init:
    cmp #OP_END
    bne mudo                    ; un opcode que no existe: callar antes que
                                ; escribirle cualquier cosa al DSP
    lda reinicio
    bne mudo
    inc reinicio
    lda tema_actual             ; se terminó: el mismo, de nuevo desde arriba
    jsr music_start_ya          ; adentro de la IRQ: sin `sei` y sin paquete
    bra leer
mudo:
    ; Un stream vacío: nada que tocar, ni en este cuadro ni en los que vienen.
    ; Y hay que decirlo con la bandera, porque `advance` dejó el puntero **un
    ; byte más allá del final** y volver acá al cuadro siguiente leía ese byte
    ; como opcode. Era $FF de casualidad —el primer byte del bloque de al
    ; lado— hasta que las poses en caliente cambiaron el reparto de la ROM y
    ; pasó a ser $00: una escritura al DSP con su espera del SPC700, y otra, y
    ; otra, media pantalla por cuadro, y el lazo a la mitad de velocidad. Lo
    ; delataron tres casos de la tanda con un cuadro repetido, y una sonda de
    ; la línea de barrido al final de cada fase del lazo.
    lda #1
    sta music_apagada
    rts

cruda:
    ; Un registro que no es de una voz, así que no pasa por el caché.
    lda [music]
    jsr advance
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda [music]
    jsr advance
    jsr dsp_musica
    bra leer

espera_corta:
    sec
    sbc #OP_WAIT_1 - 1          ; de 1 a ESPERA_CORTA
    rep #$20
.a16
    and #$00FF
    bra cerrar
espera_larga:
.a8
    lda [music]
    jsr advance
    xba
    lda [music]
    jsr advance
    xba                         ; A de dieciséis: los dos bytes, bajo primero
    rep #$20
.a16
cerrar:
    ; Se cierra el cuadro: las voces que recibieron nota se disparan juntas.
    pha
    sep #$20
.a8
    lda f:MUS_KON
    beq sin_kon
    sta f:MUS_SONANDO
    ldx #SE_KON
    jsr dsp_musica
    lda #0
    sta f:MUS_KON
sin_kon:
    rep #$20
.a16
    ; El `pla` deja Z del valor que saca, y es a propósito: una espera de
    ; cero cuadros dispara y sigue leyendo en el mismo, sin abrir otro.
    pla
    beq sigue
    dec a
    sta f:MUS_ESPERA
    sep #$20
.a8
    rts
sigue:
.a16
    sep #$20
.a8
    jmp leer

arranque:
    ; El arranque del DSP: la misma tabla que usa el camino del MSU-1, y
    ; detrás KON y KOF en cero. Ver `escrituras_del_arranque`.
    ldy #0
otro_init:
    lda dsp_init_reg, y
    cmp #$FF
    beq init_listo
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda dsp_init_val, y
    jsr dsp_musica              ; no toca Y
    iny
    bra otro_init
init_listo:
    lda #0
    ldx #SE_KON
    jsr dsp_musica
    lda #0
    ldx #SE_KOF
    jsr dsp_musica
    jmp leer

de_voz:
    ; La voz en los tres bits bajos y la familia en los de arriba: ver el
    ; encabezado de music.toml. Y queda con el registro VOL_L de la voz.
    rep #$20
.a16
    and #$00FF
    pha
    and #$0007
    tax                         ; la voz
    asl a
    asl a
    asl a
    asl a
    tay
    sep #$20
.a8
    lda bit_de_voz, x
    sta f:MUS_BIT
    rep #$20
.a16
    pla
    and #$0038
    lsr a
    lsr a                       ; la familia por dos
    tax
    sep #$20
.a8
    jmp (familias, x)
.endproc

; Una por familia, en el orden de sus números.
familias:
    .addr ev_nota, ev_nota_vol, ev_nota_pan, ev_release, ev_release_gain
    .addr ev_set_vol, ev_set_pan, ev_set_pitch
.assert OP_NOTE_V0 = 0, error, "music.toml: las familias empiezan en 0"
.assert OP_NOTE_VOL_V0 = OP_NOTE_V0 + 8, error, "music.toml: familias fuera de orden"
.assert OP_NOTE_PAN_V0 = OP_NOTE_VOL_V0 + 8, error, "music.toml: familias fuera de orden"
.assert OP_RELEASE_V0 = OP_NOTE_PAN_V0 + 8, error, "music.toml: familias fuera de orden"
.assert OP_RELEASE_GAIN_V0 = OP_RELEASE_V0 + 8, error, "music.toml: familias fuera de orden"
.assert OP_SET_VOL_V0 = OP_RELEASE_GAIN_V0 + 8, error, "music.toml: familias fuera de orden"
.assert OP_SET_PAN_V0 = OP_SET_VOL_V0 + 8, error, "music.toml: familias fuera de orden"
.assert OP_SET_PITCH_V0 = OP_SET_PAN_V0 + 8, error, "music.toml: familias fuera de orden"
.assert OP_WAIT_1 = OP_SET_PITCH_V0 + 8, error, "music.toml: las esperas van detrás"

bit_de_voz:
    .byte $01, $02, $04, $08, $10, $20, $40, $80

; Escribe A en el registro Y, salvo que el caché diga que ya lo tiene. Con V
; prendido escribe sin mirar: así va la primera nota de cada voz desde que
; arrancó el tema, y el primer GAIN, porque el caché arranca con lo que haya
; quedado y no tiene manera de decir "no sé". No toca X, Y ni V.
.proc mus_escribir
.a8
.i16
    phx
    tyx
    bvs escribir
    cmp f:MUS_SOMBRA, x
    beq igual
escribir:
    sta f:MUS_SOMBRA, x
    jsr dsp_musica
igual:
    plx
    rts
.endproc

; V prendido si la voz del evento todavía no tuvo nota, y la marca. No toca
; X ni Y.
.proc nota_primera
.a8
.i16
    clv
    lda f:MUS_BIT
    and f:MUS_VISTAS
    bne ya
    lda f:MUS_BIT
    ora f:MUS_VISTAS
    sta f:MUS_VISTAS
    sep #$40                    ; V
ya:
    rts
.endproc

.proc ev_nota_vol
.a8
.i16
    jsr nota_primera
    LEER
    pha
    jsr mus_escribir            ; VOL_L
    iny
    pla
    jsr mus_escribir            ; VOL_R, el mismo
    iny
    jmp nota_sonido
.endproc

.proc ev_nota_pan
.a8
.i16
    jsr nota_primera
    LEER
    jsr mus_escribir            ; VOL_L
    iny
    LEER
    jsr mus_escribir            ; VOL_R
    iny
    jmp nota_sonido
.endproc

.proc ev_nota
.a8
.i16
    jsr nota_primera
    iny
    iny
    ; sigue en nota_sonido
.endproc

; El sonido de la nota: Y en PITCH_L de la voz y V como lo dejó
; `nota_primera`. Sus cinco primeros bytes van a PITCH_L, PITCH_H, SRCN, ADSR1
; y ADSR2, en ese orden, y el sexto es el GAIN con que se va a soltar.
.proc nota_sonido
.a8
.i16
    LEER
    php                         ; las sumas pisan V
    rep #$21                    ; A de dieciséis y el carry en cero
.a16
    and #$00FF
    sta f:MUS_T
    asl a
    adc f:MUS_T
    asl a                       ; por seis
    adc f:MUS_BASE
    tax
    plp
.a8
    .repeat 5, k
    lda f:musica_sonidos + k, x
    jsr mus_escribir
    iny
    .endrepeat
    lda f:musica_sonidos + 5, x
    tyx                         ; el registro 8 de la voz, que es ENVX
    sta f:MUS_SOMBRA + 1, x
    lda f:MUS_BIT
    ora f:MUS_KON
    sta f:MUS_KON
    jmp music_frame::leer
.endproc

.proc ev_release_gain
.a8
.i16
    lda [music]
    jsr advance
soltar:
    pha
    iny
    iny
    iny
    iny
    iny                         ; ADSR1
    clv
    lda #0
    jsr mus_escribir
    iny
    iny                         ; GAIN
    lda f:MUS_BIT
    and f:MUS_GAINS
    bne con_gain
    lda f:MUS_BIT
    ora f:MUS_GAINS
    sta f:MUS_GAINS
    sep #$40                    ; el primero va sin mirar el caché
con_gain:
    pla
    jsr mus_escribir
    jmp music_frame::leer
.endproc

.proc ev_release
.a8
.i16
    tyx
    lda f:MUS_SOMBRA + 8, x     ; el GAIN del sonido de la voz
    bra ev_release_gain::soltar
.endproc

.proc ev_set_vol
.a8
.i16
    clv
    lda [music]
    jsr advance
    pha
    jsr mus_escribir
    iny
    pla
    jsr mus_escribir
    jmp music_frame::leer
.endproc

.proc ev_set_pan
.a8
.i16
    clv
    lda [music]
    jsr advance
    jsr mus_escribir
    iny
    lda [music]
    jsr advance
    jsr mus_escribir
    jmp music_frame::leer
.endproc

.proc ev_set_pitch
.a8
.i16
    clv
    iny
    iny                         ; PITCH_L
    lda [music]
    jsr advance
    jsr mus_escribir
    iny
    lda [music]
    jsr advance
    jsr mus_escribir
    jmp music_frame::leer
.endproc

; El estado del decodificador en cero. En el reset: la RAM lejana arranca con
; basura.
.proc musica_limpiar
.a8
.i16
    ldx #0
    lda #0
otro:
    sta f:MUS_ESPERA, x
    inx
    cpx #MUS_ESTADO_BYTES
    bcc otro
    rts
.endproc
