; --- la transición de la pelea ----------------------------------------------
;
; La base de datos de A Blurred Line pide, al empezar una pelea,
; `battle_start_fadeout = 16` y `battle_start_fadein = 17`, y al terminarla
; `battle_end_fadeout = 17` y `battle_end_fadein = 16`. En la tabla de
; `Game_System::GetTransition` de easyrpg-player el 16 es `TransitionZoomIn`
; al borrar y `TransitionZoomOut` al mostrar, y el 17 es `TransitionMosaicOut`
; y `TransitionMosaicIn`. O sea: el mapa se acerca hasta desaparecer, la pelea
; aparece desde un mosaico, la pelea se va en mosaico y el mapa vuelve
; alejándose. Antes de todo, dos destellos blancos de diez cuadros cada uno:
; `Scene_Map::TransitionOut` los antepone siempre que se entra a una pelea,
; con `PrependFlashes(31, 31, 31, 31, 10, 2)`.
;
; Lo que se hace acá:
;
;   los destellos      con el color fijo sumado a toda la pantalla: color math,
;                      que el juego no usa para nada más
;   el zoom            **como fundido**, que es lo que taro decidió para las
;                      transiciones que la consola no hace: acercar el mapa es
;                      modo 7, y el mapa está en modo 3
;   el mosaico         con el mosaico del PPU, que es justamente eso, **y
;                      fundiendo a la vez**. La pelea son dos fondos —BG1 la
;                      escena, BG2 el texto— y al entrar y al salir no hay
;                      ningún sprite, así que el mosaico le llega a todo.
;
; Fundir el mosaico no es de RM2k —allá el mosaico no oscurece—, y es a
; propósito: **la carga del paquete de audio tiene que caer adentro del
; negro**. Subir el de la pelea, o volver a subir el del mapa, tarda entre
; medio segundo y un segundo y medio según el cartucho y el mapa, y sin esto se
; veía la pantalla congelada todo ese rato. En RM2k la carga es instantánea y
; no hay qué tapar. Así que cada lado se apaga hasta negro, carga, y recién
; ahí prende el otro: tarde lo que tarde la carga —con MSU-1 no sube el tema—,
; queda adentro.
;
; Las rampas son las del teletransporte, `fundido_rampa`: el brillo maestro
; tiene dieciséis pasos, y el mosaico va atado a él —tamaño 16 con brillo 0,
; tamaño 1 con brillo 15—, que son también los dieciséis tamaños que tiene el
; PPU. En RM2k el zoom y el mosaico duran 41 cuadros; acá cada rampa dura
; `FUNDIDO_RAMPA` y el resto es el negro de la carga, que siempre es más largo.
;
; Todo esto **bloquea**, como la pelea misma: `vueltas` no avanza, así que la
; transición no cuesta ningún tick —ver `test_la_pelea_no_gasta_ningun_tick`—.
; RM2k también congela la escena mientras dura una transición.

.segment "CODE"

; Y el mapa de vuelta, desde negro, ya repuesto por `volver_de_batalla`. Con
; `flush_video` en cada cuadro, como el lazo principal mientras un fundido lo
; congela: el scroll, la OAM y el brillo se escriben ahí y sólo ahí —ver el
; final de `flush_video`—. La OAM se arma una vez antes, porque la que hay en
; el PPU es la de la pelea; es lo mismo que hace `cargar_lo_pedido`.
.proc pelea_fundir_al_mapa
.a8
.i16
    jsr build_oam
    ldx #0
subir:
    lda fundido_rampa, x
    sta brillo
    phx
    jsr wait_vblank
    jsr flush_video
    plx
    inx
    cpx #FUNDIDO_RAMPA
    bcc subir
    rts                         ; y `brillo` queda en el lleno, como estaba
.endproc

.segment "FAR"

; Las que no llaman a nada del banco 0 más que a `wait_vblank`, por su puente,
; viven acá: el banco 0 no tiene lugar de sobra. No dependen del banco de
; datos —la de la pelea corre con $7E—, así que todo va con `f:`.

; Los dos destellos y el mapa hasta negro. Desde `pelea_arrancar`, con el mapa
; en pantalla. Deja la pantalla prendida con brillo cero: la carga que viene
; no escribe la VRAM.
.proc pelea_fundir_entrando
.a8
.i16
    ; El color fijo se suma en todas las capas y en el fondo. Los sprites de
    ; las paletas 0 a 3 no reciben color math —es del hardware—, así que el
    ; héroe destella menos que el mapa.
    lda #0
    sta f:CGWSEL
    lda #$3F
    sta f:CGADSUB
    ldy #2                      ; dos destellos, con la misma curva
otro_destello:
    ldx #0
destello:
    jsl f:ba_t_vblank           ; `wait_vblank`: no toca ni X ni Y
    lda f:destello_de_pelea, x
    sta f:COLDATA
    inx
    cpx #10
    bcc destello
    dey
    bne otro_destello
    ; Y el mapa hasta negro. El primer cuadro apaga el destello, en el mismo
    ; vblank; la rampa arranca un paso abajo del lleno para no gastar un cuadro
    ; en el brillo que ya había.
    ldx #(FUNDIDO_RAMPA - 2)
bajar:
    jsl f:ba_t_vblank
    lda #$30
    sta f:CGWSEL                ; color math apagado, como lo deja `ppu_reset`
    lda #0
    sta f:CGADSUB
    lda #$E0
    sta f:COLDATA
    lda f:fundido_rampa, x
    sta f:INIDISP
    dex
    bpl bajar
    rtl
.endproc

; La intensidad del color fijo en cada cuadro de un destello, con los tres
; canales prendidos. Es la curva de `Flash::Update`: el nivel arranca en 31 y
; en cada cuadro pierde `nivel / cuadros_que_quedan`, o sea 31 * (10 - k) / 10,
; truncado como lo trunca easyrpg al hacer el color.
destello_de_pelea:
    .byte $E0|31, $E0|27, $E0|24, $E0|21, $E0|18
    .byte $E0|15, $E0|12, $E0|9,  $E0|6,  $E0|3

; La pelea hasta negro, en mosaico. Desde `pelea_arrancar`, con la pelea ya
; terminada y todavía en pantalla. Si la pelea no llegó a prender nada —una
; tropa que el cartucho no lleva, o un grupo sin nadie en pie, que pierde sin
; pelear— la pantalla ya está en negro desde `pelea_fundir_entrando` y no hay
; qué apagar.
.proc pelea_fundir_saliendo
.a8
.i16
    lda f:PELEA_PRENDIDA
    beq listo
    lda #0
    sta f:PELEA_PRENDIDA
    ldx #(FUNDIDO_RAMPA - 2)
bajar:
    jsl f:ba_t_vblank
    lda f:fundido_rampa, x
    sta f:INIDISP
    eor #$0F                    ; el mosaico, atado al brillo: ver arriba
    asl a
    asl a
    asl a
    asl a
    ora #$03                    ; BG1 y BG2
    sta f:MOSAIC
    dex
    bpl bajar
    lda #0
    sta f:MOSAIC                ; ya en negro: nadie más lo apaga
listo:
    rtl
.endproc

; La pelea desde negro, en mosaico. Desde `batalla_correr`, con la escena ya
; subida y la pantalla prendida en brillo cero.
.proc pelea_fundir_mostrando
.a8
.i16
    lda #1
    sta f:PELEA_PRENDIDA
    ldx #0
subir:
    jsl f:ba_t_vblank           ; `wait_vblank`, que no toca X
    lda f:fundido_rampa, x
    sta f:INIDISP
    eor #$0F
    asl a
    asl a
    asl a
    asl a
    ora #$03                    ; BG1 y BG2
    sta f:MOSAIC
    inx
    cpx #FUNDIDO_RAMPA
    bcc subir
    lda #0
    sta f:MOSAIC                ; el último ya era de tamaño 1: lo mismo, apagado
    rts
.endproc
