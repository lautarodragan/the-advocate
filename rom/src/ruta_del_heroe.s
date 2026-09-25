.segment "CODE"

; Un comando de la ruta forzada. Girar no consume cuadro y se sigue con el
; siguiente; esperar sí; y moverse arranca un paso de una celda, que después
; camina `advance_step` como cualquier otro. Un movimiento bloqueado se saltea:
; RM2k reintentaría para siempre y una prueba colgada no dice nada.
; Los saltos de acá adentro van con `jmp` y no con `bra`: el cuerpo pasó de
; siete órdenes a quince y los 127 bytes de alcance de un `bra` se quedaron
; cortos tres veces seguidas. Es la misma trampa que ya había cortado dos veces
; en la cadena de `cmp` que era el despacho de `correr_codigo` antes de la
; tabla, y se saca igual.
.proc paso_de_ruta
.a8
.i16
    ; Un `wait` en curso se lleva el cuadro entero y no mira la ruta. Son
    ; RUTA_ESPERA cuadros y no uno: es `SetMaxStopCountForWait` de RM2k, que con
    ; la frecuencia 8 da veinte. Valía uno de los dos lados a la vez, así que la
    ; comparación daba cero —el mismo error que el hard light del tinte—.
    ; El salto en curso no se mira acá sino en `move_hero`: ver
    ; `salto_avanzar_heroe`.
    lda ruta_espera
    beq sin_espera
    dec ruta_espera
    rts
sin_espera:
otra_orden:
    lda ruta_i
    cmp ruta_n
    bcc hay_orden
    jmp listo                   ; se terminó la ruta; `bcs` ya no llega
hay_orden:
    ; El índice a X pasando por A de dieciséis bits y limpiando el alto: `tax`
    ; transfiere los dos bytes del acumulador aunque A esté en ocho, y el alto
    ; trae lo que dejó la operación anterior. Es la trampa que ya está anotada
    ; en el README, y acá hacía que la ruta leyera basura y se cortara al primer
    ; paso: el héroe caminaba una celda de tres y no había ningún error.
    rep #$20
.a16
    lda ruta_i
    and #$00FF
    tax
    sep #$20
.a8
    lda ruta, x
    inc ruta_i

    cmp #23                     ; wait: éste y los RUTA_ESPERA - 1 que siguen,
    bne no_es_wait              ; más los del giro si la frecuencia es baja
    lda ruta_frec
    jsr tras_giro
    clc
    adc #(RUTA_ESPERA - 1)
    sta ruta_espera
    jmp listo
no_es_wait:
    cmp #12
    bcs no_es_mover
    jmp mover                   ; 0..3 son los move_*
no_es_mover:
    cmp #16
    bcc face                    ; 12..15 son los face_*
    ; Girar sin moverse no se compila, y encarar al héroe —la 21— e ir hacia
    ; él —la 9— no se compilan **sobre el héroe**: ver `RUTA_ORDENES` en
    ; eventos.py. Acá no llegan. La 9 además caería en `mover` de arriba, que
    ; con una dirección que no es 0..3 manda al héroe a la izquierda por
    ; descarte, que es la misma trampa que las diagonales.
    cmp #24
    bne no_es_salto
    jsr armar_salto_heroe
    lda ruta_salto
    bne salto_arranco
    jmp otra_orden              ; no se pudo caer ahí: se saltea
salto_arranco:
    jmp listo
no_es_salto:
    cmp #25
    bne no_es_fin
    jmp otra_orden              ; el par ya lo consumió el `begin_jump`
no_es_fin:
    cmp #28
    bcc otra_orden              ; 26 y 27 no llegan sobre el héroe
    cmp #30
    bcs no_es_velocidad
    jmp velocidad               ; 28 y 29: la velocidad, que queda
no_es_velocidad:
    cmp #32
    bcc frecuencia              ; 30 y 31: la frecuencia de la ruta
    cmp #34
    bne no_es_grafico_heroe
    jmp grafico_heroe           ; la 34, la única con operando; queda lejos
no_es_grafico_heroe:
    cmp #36
    bcc otra_orden              ; 32, 33 y 35 —los switches y el sonido— no
                                ; llegan: el conversor los tira o los rechaza
    cmp #38
    bcc atravesar               ; 36 y 37
    cmp #40
    bcs otra_orden
    ; 38 para la animación y 39 la sigue, así que la resta va al revés.
    sec
    sbc #38
    eor #$01
    sta ruta_anim_para
    jmp otra_orden
atravesar:
    ; 36 prende y 37 apaga, así que el bit de abajo invertido es el valor.
    and #$01
    eor #$01
    sta ruta_atraviesa
    jmp otra_orden
frecuencia:
    ; 30 sube la frecuencia de la ruta y 31 la baja, topando en 8 y en 1: es
    ; `increase/decrease_movement_frequence`. De ella salen los cuadros quieto
    ; tras cada orden, así que se lee de `ruta_frec` y no de otro lado.
    ;
    ; Con la 1 la espera tras un paso son 256 cuadros y no entran en el byte de
    ; `ruta_tras_paso`; que no se llegue lo garantiza el conversor, que rechaza
    ; la ruta entera. Acá se topa igual en 1, como RM2k: topar distinto sería
    ; que los dos lados se equivoquen igual el día que ese guard falle.
    and #$01
    bne frec_menos
    lda ruta_frec
    cmp #RUTA_FRECUENCIA
    bcs frec_listo
    inc ruta_frec
    bra frec_listo
frec_menos:
    lda ruta_frec
    cmp #2
    bcc frec_listo
    dec ruta_frec
frec_listo:
    jmp otra_orden
face:
    sec
    sbc #12
    sta hero_dir                ; face_*: con la frecuencia 8 es instantáneo y
    lda ruta_frec               ; sigue el que viene; con otra, se queda
    jsr tras_giro               ; quieto los cuadros del giro
    bne giro_espera
    jmp otra_orden
giro_espera:
    dec a
    sta ruta_espera
    jmp listo

; `change_graphic` **sobre el héroe**: la 34 con su operando, el índice del
; gráfico en la tabla del mapa, igual que sobre un evento.
;
; Sale barata porque las dos tablas de poses tienen la misma forma: una entrada
; de `npc_poses` son doce punteros de tres bytes a las poses del personaje, y
; los doce que la tabla de actores le da al líder están escritos igual. O sea
; que alcanza con apuntar `hero_poses` treinta y seis bytes adentro de
; `npc_poses` y `place_hero` sigue sin enterarse.
;
; Dos cosas que **no** se hacen y que son lo que costaría de más:
;
; * `hero_cgram` se apaga. Los quince colores del líder los sube
;   `aplicar_tinte` **en la fila que dice `hero_pal`**, así que dejarlo puesto
;   con la paleta nueva le escribiría los colores de Talan encima a la paleta
;   del gráfico al que se cambió. Mientras el cambio está puesto, el héroe se
;   dibuja con la paleta del gráfico nuevo, que ya vive en CGRAM con el resto
;   de los sprites del mapa.
; * No sobrevive al cambio de mapa: `elegir_grafico_heroe` corre al cargar y lo
;   repone. No es pereza —las poses viven en el banco de sprites **del mapa**,
;   así que el gráfico de allá no existe acá—, y la referencia lo repone igual.
;   La página del `EV0047` del mapa 8, que es la que pidió todo esto, cambia a
;   `Crown7` justo antes de teletransportarse y vuelve a `Future1` justo
;   después, así que en el juego no se nota.
grafico_heroe:
    lda #$FF
    sta hero_pose_vram          ; la pose que hay en VRAM ya no es la suya
    rep #$20
.a16
    lda ruta_i
    and #$00FF
    tax
    sep #$20
.a8
    lda ruta, x
    inc ruta_i                  ; el operando ya está consumido
    jsr hero_poses_de_grafico
    bcc heroe_sin_grafico
    jmp otra_orden
heroe_sin_grafico:
    ; Un CharSet sin un solo pixel opaco —`nobodyhere`— o uno que no entró en
    ; las ocho paletas de sprite: el héroe deja de dibujarse, que es lo que
    ; `place_hero` hace con el puntero de poses en cero y lo mismo que le pasa
    ; a un evento con la fila escondida.
    stz hero_poses + 2
    stz hero_cgram + 2
    jmp otra_orden


mover:
    ; Acá no llegan las diagonales: el conversor rechaza la página que le dé
    ; una al héroe —ver MOVE_EVENT en `eventos.traducir`— porque la ROM sólo
    ; las camina sobre eventos, y ninguna de las 26 rutas del juego que las
    ; usan es del héroe. Sin ese corte, el descarte de abajo mandaría al héroe
    ; hacia la izquierda.
    sta hero_dir                ; move_* mira hacia donde va
    ; Atravesando paredes las dos caras dan que sí. Es el
    ; `if (self.GetThrough()) return true;` de `Game_Map::CheckOrMakeWayEx`, y
    ; se prende sólo alrededor de este paso: `can_leave` y `can_enter` los usa
    ; también la caminata con el pad, que no lo mira.
    lda ruta_atraviesa
    beq sin_atravesar
    lda #1
sin_atravesar:
    sta atravesando
    stz atravesando + 1
    lda hero_dir
    cmp #DIR_UP
    bne no_es_arriba
    jsr try_up
    jmp ver_si_arranco
no_es_arriba:
    cmp #DIR_RIGHT
    bne no_es_derecha
    jsr try_right
    jmp ver_si_arranco
no_es_derecha:
    cmp #DIR_DOWN
    bne no_es_abajo
    jsr try_down
    jmp ver_si_arranco
no_es_abajo:
    jsr try_left
ver_si_arranco:
    stz atravesando
    stz atravesando + 1
    lda step_left
    bne arranco                 ; bloqueado: se saltea y se prueba el siguiente
    jmp otra_orden
arranco:
    ; El paso arrancó, y queda anotado que lo arrancó la ruta: `hay_rutas` lo
    ; necesita para saber que el último paso de una ruta todavía cuenta.
    lda #1
    sta ruta_paso
listo:
    rts
velocidad:
    ; `increase_movement_speed` y `decrease_movement_speed`, topadas en 6 y 1
    ; como `MoveRouteSpeedUp`. Sobre el héroe la ROM las ignoraba; ahora
    ; cambian el paso, y lo cambian para siempre: RM2k repone la frecuencia al
    ; terminar la ruta y la velocidad no.
    cmp #29
    beq vel_menos
    jsr hero_vel_leer
    cmp #6
    bcs vel_guardar
    inc a
    bra vel_guardar
vel_menos:
    jsr hero_vel_leer
    cmp #2
    bcc vel_guardar
    dec a
vel_guardar:
    jsr hero_vel_escribir
    jmp otra_orden
.endproc

; Si queda alguna ruta forzada sin terminar, la del héroe incluida. Devuelve A
; distinto de cero si la hay. Es `Game_Map::IsAnyMovePending`, que es a lo que
; espera `ProceedWithMovement`.
;
; Del héroe cuentan tres cosas, y la última no es obvia: que le queden órdenes,
; que esté en el aire, y que tenga un paso en curso **que haya arrancado la
; ruta**. Lo último hace falta porque el último paso de una ruta sigue siendo la
; ruta aunque ya no queden órdenes —sin eso la página seguiría ocho cuadros
; antes de tiempo—, y tiene que ser sólo el de la ruta porque, terminada ésta,
; el jugador puede ponerse a caminar mientras otra ruta sigue corriendo, y un
; paso del pad no es una ruta pendiente.
;
; El salto no necesita ese cuidado y por eso se mira pelado: el único que pone
; `ruta_salto` en algo distinto de cero es `armar_salto_heroe`, y a ése lo llama
; sólo `paso_de_ruta`, así que un salto del héroe es siempre de una ruta. Del
; pad no sale ninguno. Faltaba, y un `ProceedWithMovement` pegado detrás de un
; salto soltaba la página con el héroe todavía arriba: allá `MoveRouteFinished`
; se prende adentro de `UpdateMovement`, o sea al aterrizar.
.proc hay_rutas
.a8
.i16
    lda ruta_espera
    bne si                      ; el héroe está en medio de un `wait`
    lda ruta_salto
    bne si                      ; o está en el aire
    lda ruta_i
    cmp ruta_n
    bcc si                      ; al héroe le quedan órdenes
    lda ruta_paso
    beq de_eventos
    lda step_left
    bne si                      ; y el paso que está dando es de la ruta

de_eventos:
    ldx #$0000
otra:
    lda ruta_ev, x
    cmp #RUTA_EV_LIBRE
    beq siguiente
    lda ruta_ev + 18, x
    and #$01
    bne siguiente               ; la ruta propia de la página no se espera
    lda ruta_ev + 7, x          ; un paso en curso
    bne si
    lda ruta_ev + 9, x          ; o una espera
    bne si
    lda ruta_ev + 13, x         ; o un salto
    bne si
    lda ruta_ev + 5, x
    cmp ruta_ev + 4, x
    bcc si                      ; le quedan órdenes
siguiente:
    rep #$20
.a16
    txa
    clc
    adc #RUTA_EV_STRIDE
    tax
    cmp #RUTA_EV_MAX * RUTA_EV_STRIDE
    sep #$20
.a8
    bcc otra
    lda #0
    rts
si:
    lda #1
    rts
.endproc

