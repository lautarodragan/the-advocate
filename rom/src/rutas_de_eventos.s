.segment "CODE"

; --- las rutas forzadas de los eventos --------------------------------------
;
; Un evento con ruta forzada camina como el héroe: girar no consume cuadro,
; esperar sí, y moverse arranca un paso de una celda que dura CUADROS_POR_CELDA.
; La diferencia con el héroe es que su posición vive en celdas y no en pixeles,
; y que —por ahora— no se dibuja: las rutas que compilan son sobre eventos sin
; gráfico. Lo único que se ve de ellas es cuánto tardan, que es lo que espera
; `ProceedWithMovement`.

; Le da una ruta al evento `ruta_blanco - 1`: busca su ranura, y si no la tiene
; agarra una libre. Pisar la que ya tenía es lo correcto —RM2k sobrescribe la
; ruta forzada anterior, no la encadena— y si no hay ninguna libre la ruta se
; descarta, que es preferible a escribir al lado de la tabla.
;
; Lo que se conserva al pisarla es lo que `ForceMoveRoute` conserva: el paso o
; el salto en curso se terminan, hacia dónde mira queda, y atravesar paredes y
; la animación parada siguen como estaban. Se cortan la espera —la primera
; orden corre ya— y las órdenes. Antes se reseteaba la ranura entera, y el
; evento volvía a mirar adonde decía su página hasta que la ruta nueva lo
; girara: era el centinela que dejaba afuera a `face_hero`.
;
; Entra con Y apuntando a la primera orden dentro del bytecode.
.proc ruta_para_evento
.a8
.i16
    phy
    lda ruta_blanco
    dec a
    jsr giro_por_ruta           ; con ruta, adónde mira lo decide ella
    ply
    lda ruta_blanco
    dec a
    sta temp                    ; el índice del evento

    ; Primero la ranura que ya sea suya, y si no una libre. Las dos búsquedas
    ; estaban copiadas acá y son exactamente `ranura_del_evento` y
    ; `ranura_libre`: llamarlas ahorra banco 0 y, la primera, se lleva de
    ; regalo el tope de `ruta_ev_tope`.
    lda temp
    jsr ranura_del_evento
    cpx #$FFFF
    bne reusada
    jsr ranura_libre
    cpx #$FFFF
    bne puesta
    rts                         ; no hay lugar: la ruta se pierde

puesta:
    lda temp
    sta ruta_ev + 0, x
    stz ruta_ev + 6, x
    stz ruta_ev + 7, x          ; sin paso en curso
    stz ruta_ev + 22, x
    stz ruta_ev + 23, x
    lda #RUTA_EV_SIN_MIRAR
    sta ruta_ev + 8, x          ; mira adonde diga su página hasta que gire
    stz ruta_ev + 12, x         ; sin banderas
    stz ruta_ev + 13, x         ; ni salto
    lda #1
    sta ruta_ev + 10, x         ; el frame del medio, como `animate_hero`
    stz ruta_ev + 11, x
    stz ruta_ev + 18, x
    stz ruta_ev + 27, x         ; sin página a la que volver
    rep #$20
.a16
    lda #$FFFF
    sta ruta_ev + 20, x
    sep #$20
.a8
    ; A la velocidad de la página con que se dibuja, que la fila del NPC trae
    ; en +13: es la que RM2k le deja a una ruta forzada. Un evento sin fila
    ; —sin gráfico— va a la 3, la de una página por defecto.
    phy                         ; Y es el cursor del bytecode, y se necesita
    lda temp                    ; después: `npc_de_evento` lo pisa
    jsr npc_de_evento           ; Y = su fila, o $FFFF; A se pierde
    cpy #$FFFF
    beq sin_fila
    lda npc_buf + 13, y
    bra con_velocidad
sin_fila:
    lda #3
con_velocidad:
    ply
    sta ruta_ev + 17, x
    lda temp
    jsr capa_activa             ; su capa, una vez y no en cada paso
    sta ruta_ev + 31, x
reusada:
    lda ruta_ev + 18, x
    and #$FE                    ; la forzada pisa a la de página, si había
    ora #$04                    ; y lo bloqueado se saltea
    sta ruta_ev + 18, x
    ; El puntero a la primera orden: el del código más lo que Y llevaba andado.
    ; La suma no se lleva nada al byte de banco porque el bloque de código del
    ; mapa entra entero en uno —lo garantiza el acomodo de bancos del
    ; conversor, `tools/ensamblado/bancos.py`—, que es el mismo argumento que el del bloque de mensajes.
    rep #$20
.a16
    tya
    clc
    adc cod_ptr
    sta ruta_ev + 1, x
    sep #$20
.a8
    lda cod_ptr + 2
    sta ruta_ev + 3, x
    lda ruta_cuantas
    sta ruta_ev + 4, x
    stz ruta_ev + 5, x          ; recién empieza
    stz ruta_ev + 9, x          ; y sin espera en curso: la primera orden corre ya
    lda ruta_frec_op
    sta ruta_ev + 16, x
    rts
.endproc

; Cuántos cuadros se queda quieto un personaje después de un paso y después de
; un giro con la frecuencia que trae A. Es el contador de parada de RM2k
; —`SetMaxStopCountForStep` y `ForTurn`— y con la 8 los dos dan cero, que es
; por lo que "girar es gratis y los pasos van seguidos" era exacto sin saberlo.
; Las tablas las emite el conversor con las mismas funciones que usa la
; referencia. Usan Y y no X, porque X es la ranura de quien pregunta.
.proc tras_paso
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda ruta_tras_paso, y
    rts
.endproc

.proc tras_giro
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda ruta_tras_giro, y
    rts
.endproc

; Hacia dónde mira quien está en (celda_x, celda_y) para encarar al héroe. Es
; `GetDirectionToCharacter`: manda el eje con más distancia y en empate el
; vertical; sobre la misma celda, o con el héroe más abajo, mira abajo.
; Devuelve la dirección en A.
.proc hacia_el_heroe
.a8
.i16
    rep #$20
.a16
    lda celda_x
    sec
    sbc tile_x
    sta temp                    ; sx, con signo: positivo es "el héroe está a la izquierda"
    bpl :+
    eor #$FFFF
    inc a
:   sta cmp_a                   ; |sx|
    lda celda_y
    sec
    sbc tile_y
    sta temp + 2                ; sy: positivo es "el héroe está más arriba"
    bpl :+
    eor #$FFFF
    inc a
:   sta cmp_b                   ; |sy|
    lda cmp_a
    cmp cmp_b
    beq vertical
    bcc vertical                ; |sx| <= |sy|: manda el eje vertical
    sep #$20
.a8
    lda temp + 1                ; el signo de sx
    bmi derecha
    lda #DIR_LEFT
    rts
derecha:
    lda #DIR_RIGHT
    rts
vertical:
.a16
    sep #$20
.a8
    lda temp + 3                ; el signo de sy
    bmi abajo
    lda temp + 2
    ora temp + 3
    beq abajo                   ; la misma celda: abajo
    lda #DIR_UP
    rts
abajo:
    lda #DIR_DOWN
    rts
.endproc

; Un cuadro de todas las rutas de eventos que estén corriendo.
.proc mover_eventos
.a8
.i16
    stz rutas_movieron
    ldx #$0000
otra:
    lda ruta_ev, x
    cmp #RUTA_EV_LIBRE
    beq siguiente
    ; El que ya dio su paso pegado a su intérprete paralelo no lo da otra vez:
    ; la marca se consume acá, así que dura un cuadro. Ver `un_paralelo`.
    lda ruta_ev + 18, x
    and #$40
    beq no_movido
    lda ruta_ev + 18, x
    and #$BF
    sta ruta_ev + 18, x
    bra siguiente
no_movido:
    phx
    jsr cuadro_de_ruta_ev
    plx
    phx
    jsr animar_ruta_ev
    plx
    phx
    jsr refrescar_npc
    plx
    lda #1
    sta rutas_movieron
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
    ; De acá en adelante el que se mueve es el héroe otra vez.
    lda #MOVIL_HEROE
    sta movil
    lda #CAPA_HEROE
    sta movil_capa
    rts
.endproc

; Un cuadro de la ruta de la ranura que apunta X. Es el mismo programa que
; `paso_de_ruta` para el héroe, y por eso las dos hacen lo mismo con las mismas
; órdenes: si acá se contara distinto, una ruta terminaría en otro cuadro que en
; la referencia y `ProceedWithMovement` soltaría la página cuando no toca.
; Los saltos de acá adentro van con `jmp` y no con `bra`, por lo mismo que en
; `paso_de_ruta`: el cuerpo creció y los 127 bytes de alcance se quedaron cortos.
.proc cuadro_de_ruta_ev
.a8
.i16
    stz ruta_ev + 6, x
    lda ruta_ev + 18, x
    and #$DF                    ; la recarga de `repeat`, una por cuadro
    sta ruta_ev + 18, x
    lda ruta_ev + 7, x
    beq sin_paso
    ; El paso avanza lo que dice la velocidad, de 256 por celda; +7 sólo dice
    ; que hay uno en curso.
    jsr paso_de_ranura
    rep #$20
.a16
    lda ruta_ev + 22, x
    sec
    sbc temp
    bcs no_negativo
    lda #0
no_negativo:
    sta ruta_ev + 22, x
    sep #$20
.a8
    bne moviendo
    stz ruta_ev + 7, x          ; el paso terminó en este cuadro
    lda ruta_ev + 5, x
    cmp ruta_ev + 4, x
    bcc con_ordenes
    lda ruta_ev + 18, x         ; sin órdenes: sólo la de página que se repite
    and #$03                    ; sigue esperando
    cmp #$03
    bne moviendo
con_ordenes:
    lda ruta_ev + 16, x
    jsr tras_paso
    sta ruta_ev + 9, x
moviendo:
    lda #1
    sta ruta_ev + 6, x
    rts
sin_paso:
    lda ruta_ev + 13, x
    beq sin_salto
    jsr salto_de_ranura
    sta temp
    lda ruta_ev + 13, x
    sec
    sbc temp
    bcs guardar_salto
    lda #0
guardar_salto:
    sta ruta_ev + 13, x
    rts
sin_salto:
    ; Y un `wait` en curso se lleva el cuadro entero, igual que el del héroe.
    lda ruta_ev + 9, x
    beq sin_espera
    dec a
    sta ruta_ev + 9, x
    rts
sin_espera:
    ; La ruta propia de la página no lee órdenes nuevas mientras el intérprete
    ; tiene una página corriendo: es el `IsRunning()` de
    ; `UpdateNextMovementAction`. El paso en curso ya se terminó arriba y las
    ; esperas siguen contando.
    lda ruta_ev + 18, x
    and #$01
    beq no_congelada
    lda ev_activo
    bne congelada
    lda esperando_n
    bne congelada
no_congelada:
    ; El puntero de la ruta a la página directa, que es de donde se puede leer
    ; con `[ptr], y`.
    rep #$20
.a16
    lda ruta_ev + 1, x
    sta ruta_ptr
    sep #$20
.a8
    lda ruta_ev + 3, x
    sta ruta_ptr + 2

otra_orden:
    lda ruta_ev + 5, x          ; en cuál va
    cmp ruta_ev + 4, x          ; cuántas trae
    bcc hay_orden
    ; Se acabaron las órdenes. La de página que se repite vuelve al principio
    ; en el mismo cuadro, y una sola vez por cuadro —el `current_index ==
    ; start_index` de `UpdateMoveRoute`—; y una forzada que termina sobre un
    ; evento con ruta propia le devuelve la suya, desde el principio.
    lda ruta_ev + 18, x
    and #$23
    cmp #$03
    bne no_repite
    stz ruta_ev + 5, x
    lda ruta_ev + 18, x
    ora #$20
    sta ruta_ev + 18, x
    jmp otra_orden
no_repite:
    lda ruta_ev + 18, x
    and #$01
    bne congelada               ; la de página, terminada: listo
    lda ruta_ev + 27, x
    beq congelada               ; sin página a la que volver
    jsr retomar_pagina
congelada:
    jmp listo
hay_orden:
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [ruta_ptr], y
    inc ruta_ev + 5, x

    cmp #23                     ; wait: éste y los RUTA_ESPERA - 1 que siguen,
    bne no_es_wait              ; más los del giro si la frecuencia es baja
    lda ruta_ev + 16, x
    jsr tras_giro
    clc
    adc #(RUTA_ESPERA - 1)
    sta ruta_ev + 9, x
    jmp listo
no_es_wait:
    cmp #12
    bcs no_mueve
    cmp #9
    bne :+
    ; `move_towards_hero`. No es una orden aparte sino las dos que ya están
    ; pegadas: `UpdateMoveRoute` hace `TurnTowardCharacter(hero)` y después
    ; `Move(GetDirection())`, o sea la 21 y un `move_*` en el mismo cuadro.
    ; Por eso sale la dirección de acá y cae en `mover` sin tocar nada más:
    ; el giro, el paso y lo que cuesta son los de siempre.
    ; `hacia_el_heroe` no pisa X, que es la ranura.
    jsr celda_del_evento
    jsr hacia_el_heroe
:   jmp mover                   ; 0..3 son los move_*, y la 9 ya trae la suya
no_mueve:
    cmp #16
    bcs :+
    jmp face                    ; 12..15 son los face_*; queda lejos
:
    cmp #21
    bne no_encara
    ; face_hero: la celda del evento contra la del héroe, y a `mirar` con la
    ; dirección en A.
    jsr celda_del_evento
    jsr hacia_el_heroe
    jmp mirar
no_encara:
    ; Girar sin moverse no se compila: acá no llega.
    cmp #24
    bne no_es_salto
    jsr preparar_movil          ; quién salta, para chocar con los demás
    lda ruta_ev + 5, x
    dec a
    sta salto_orden             ; dónde está el 24, por si hay que volver
    jsr armar_salto_ev
    lda ruta_ev + 13, x
    bne salto_arranco
    ; No se pudo caer ahí. Con la ruta salteable el salto se saltea; sin eso
    ; RM2k vuelve el cursor al `begin_jump` y corta el cuadro —`current_index
    ; = saved_index`—, y el salto se reintenta cuadro a cuadro hasta que la
    ; celda se libere. Sin `end_jump` no hay a qué volver: se saltea siempre.
    lda salto_trabado
    beq saltear
    lda ruta_ev + 18, x
    and #$04
    bne saltear
    lda salto_orden
    sta ruta_ev + 5, x
    jmp listo
saltear:
    jmp otra_orden
salto_arranco:
    jmp listo
no_es_salto:
    cmp #25
    beq seguir
    cmp #26
    bcc seguir                  ; los demás no hacen nada
    cmp #32
    bcc fijar_o_velocidad       ; 26 y 27 la mirada, 28 y 29 la velocidad,
    cmp #34                     ; 30 y 31 la frecuencia
    bne no_es_grafico           ; y la 34 el gráfico, que lleva operando
    jmp cambiar_grafico         ; queda lejos para un salto corto
no_es_grafico:
    cmp #36
    bcc seguir
    cmp #38
    bcs anim
    ; 36 prende atravesar y 37 lo apaga.
    and #$01
    eor #$01
    beq apagar_atraviesa
    lda ruta_ev + 12, x
    ora #$01
    bra guardar_banderas
apagar_atraviesa:
    lda ruta_ev + 12, x
    and #$FE
    bra guardar_banderas
anim:
    cmp #40
    bcs seguir
    ; 38 para la animación y 39 la sigue.
    cmp #38
    bne seguir_anim
    lda ruta_ev + 12, x
    ora #$02
    bra guardar_banderas
seguir_anim:
    lda ruta_ev + 12, x
    and #$FD
guardar_banderas:
    sta ruta_ev + 12, x
seguir:
    jmp otra_orden
fijar_o_velocidad:
    cmp #30
    bcs ev_frecuencia
    cmp #28
    bcs velocidad
    ; 26 fija hacia dónde mira, 27 lo suelta: `lock_facing`.
    and #$01
    beq fijar
    lda ruta_ev + 18, x
    and #$F7
    bra guardar_18
fijar:
    lda ruta_ev + 18, x
    ora #$08
    bra guardar_18
velocidad:
    ; 28 sube la velocidad y 29 la baja, entre 1 y 6.
    and #$01
    bne mas_lenta
    lda ruta_ev + 17, x
    cmp #6
    bcs seguir
    inc ruta_ev + 17, x
    bra seguir
mas_lenta:
    lda ruta_ev + 17, x
    cmp #2
    bcc seguir
    dec ruta_ev + 17, x
    bra seguir
ev_frecuencia:
    ; 30 sube la frecuencia y 31 la baja, entre 1 y 8. Ver `frecuencia` en
    ; `paso_de_ruta`, que es lo mismo para el héroe: de acá salen los cuadros
    ; quieto tras cada orden, y la 1 la rechaza el conversor.
    and #$01
    bne menos_frec
    lda ruta_ev + 16, x
    cmp #RUTA_FRECUENCIA
    bcs seguir
    inc ruta_ev + 16, x
    bra seguir
menos_frec:
    lda ruta_ev + 16, x
    cmp #2
    bcc seguir
    dec ruta_ev + 16, x
    bra seguir
guardar_18:
    sta ruta_ev + 18, x
    bra seguir

; `change_graphic`: la única orden con operando. Detrás del 34 va el índice del
; gráfico en la tabla del mapa —dos bytes por gráfico, ver `load_ruta_graficos`—
; y de ahí salen de qué personaje sacar las doce poses y con qué paleta
; dibujarlas.
;
; No cuesta un cuadro: en `UpdateMoveRoute` cae en la rama que no toca el
; contador de parada, así que la orden que sigue corre en este mismo cuadro.
; Tampoco toca la pose: el ciclo de caminata sigue donde estaba, que es lo que
; hace `SetSpriteGraphic`.
cambiar_grafico:
    lda ruta_ev + 5, x          ; el cursor ya avanzó al leer la orden
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [ruta_ptr], y
    inc ruta_ev + 5, x          ; y ahora por el operando
    asl a                       ; dos bytes por entrada
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda ruta_graf_buf, y
    sta graf_k                  ; su entrada en `npc_poses`, o $FF
    lda ruta_graf_buf + 1, y
    sta graf_pal

    lda ruta_ev + 0, x
    phx
    jsr npc_de_evento           ; su fila, que es lo que hay que cambiar
    plx
    cpy #$FFFF
    beq listo_graf              ; un evento sin gráfico no tiene fila
    lda #$FF
    sta npc_buf + 15, y         ; un CharSet no le impone nada a la celda
    lda graf_k
    cmp #$FF
    bne con_grafico
    ; Un CharSet sin un solo pixel opaco: el evento desaparece. Es lo mismo
    ; que hace `esconder_npc`, y son 185 de las 437 órdenes 34 del juego
    ; —`nobodyhere`—, así que no es el caso raro sino el más común.
    lda #0
    sta npc_buf + 14, y
    bra listo_graf
con_grafico:
    sta npc_buf + 9, y          ; de qué personaje salen sus poses
    lda npc_buf + 7, y
    and #$F1                    ; la paleta vive en los bits 1 a 3 de vhoopppN
    sta temp
    lda graf_pal
    asl a
    and #$0E
    ora temp
    sta npc_buf + 7, y
    lda #$FF
    sta npc_buf + 12, y         ; la pose que hay en la VRAM ya no es la suya
    lda #1
    sta npc_buf + 14, y         ; y se ve, por si venía escondido
listo_graf:
    jmp otra_orden
face:
    sec
    sbc #12
mirar:
    sta ruta_ev + 8, x          ; face_*: con la frecuencia 8 es instantáneo y
    lda ruta_ev + 16, x         ; sigue el que viene; con otra, se queda
    jsr tras_giro               ; quieto los cuadros del giro
    bne giro_espera
    jmp otra_orden
giro_espera:
    dec a
    sta ruta_ev + 9, x
    jmp listo


mover:
    sta ruta_dir
    stz ruta_dir + 1
    lda ruta_ev + 18, x
    and #$08
    bne sin_girar               ; mira siempre igual: `lock_facing` o el tipo
                                ; de animación de la página
    lda ruta_dir
    cmp #4
    bcc derecho                 ; los cuatro de siempre miran hacia donde van
    jsr encarar_diagonal        ; una diagonal no tiene pose propia: ver ahí
derecho:
    sta ruta_ev + 8, x          ; move_* mira hacia donde va
sin_girar:
    phx
    jsr celda_del_evento        ; deja su posición en celda_x/celda_y
    jsr preparar_movil          ; y quién es, para chocar con los demás
    lda ruta_ev + 12, x
    and #$01
    sta atravesando             ; walk_everywhere: `puede_celda` lo mira
    stz atravesando + 1
    lda ruta_dir
    cmp #4
    bcc recto
    jsr puede_celda_diag        ; las dos eles: nadie mira la celda diagonal
    bra probado
recto:
    jsr puede_celda
probado:
    plx
    stz atravesando
    stz atravesando + 1
    ; `plx` pone Z según lo que saca de la pila, así que la respuesta hay que
    ; volver a mirarla: con el `beq` pegado al `plx`, la ranura 0 —que es X = 0—
    ; daba "bloqueado" siempre y ninguna ruta se movía nunca.
    cmp #0
    bne no_bloqueado
    ; Bloqueado. Con `skippable` —las forzadas, y las de página que lo pidan—
    ; se saltea y se prueba la siguiente; sin él, la orden se reintenta el
    ; cuadro que viene, y así hasta que el paso salga.
    lda ruta_ev + 18, x
    and #$04
    beq reintenta
    jmp otra_orden
reintenta:
    dec ruta_ev + 5, x
    jmp listo
no_bloqueado:
    phx
    lda ruta_dir
    jsr mover_celda_del_evento
    plx
    lda ruta_dir
    sta ruta_ev + 30, x         ; hacia dónde va el paso, que con la mirada
    lda #1                      ; fija no es hacia donde mira
    sta ruta_ev + 7, x          ; hay un paso en curso
    jsr paso_de_ranura
    rep #$20
.a16
    lda #SALTO_PASO
    sec
    sbc temp
    sta ruta_ev + 22, x         ; y ya avanzó lo de este cuadro
    sep #$20
.a8
    lda #1
    sta ruta_ev + 6, x
listo:
    rts
.endproc

; La ruta forzada terminó sobre un evento que tiene ruta propia: vuelve la de
; la página, guardada en +24 a +29, desde el principio y con la espera del
; giro. RM2k la retoma por donde iba; acá arranca de nuevo.
.proc retomar_pagina
.a8
.i16
    lda ruta_ev + 24, x
    sta ruta_ev + 1, x
    lda ruta_ev + 25, x
    sta ruta_ev + 2, x
    lda ruta_ev + 26, x
    sta ruta_ev + 3, x
    lda ruta_ev + 27, x
    sta ruta_ev + 4, x
    stz ruta_ev + 5, x
    lda ruta_ev + 28, x
    sta ruta_ev + 16, x
    lda ruta_ev + 29, x
    sta ruta_ev + 17, x
    lda ruta_ev + 18, x
    ora #$01
    sta ruta_ev + 18, x
    lda ruta_ev + 28, x
    jsr tras_giro
    sta ruta_ev + 9, x
    rts
.endproc

; La posición del evento de la ranura X, a celda_x/celda_y.
.proc celda_del_evento
.a8
.i16
    lda ruta_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a                       ; EV_STRIDE bytes por evento
    tay
    lda ev_pos_buf, y
    sta celda_x
    lda ev_pos_buf + 2, y
    sta celda_y
    sep #$20
.a8
    rts
.endproc

; Y la mueve una celda en la dirección que trae A. Se hace al **empezar** el
; paso, no al terminarlo: es lo que hace `begin_step` con el héroe, y contarlo
; distinto dejaría a los dos lados con la celda cambiada en cuadros distintos.
; Pone la celda del evento de la ranura X en `celda_x`, `celda_y`. Lo usa el
; salto, que la mueve de una en vez de de a un paso.
.proc mover_celda_a_evento
.a8
.i16
    lda ruta_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tay
    lda celda_x
    sta ev_pos_buf + 0, y
    lda celda_y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
    rts
.endproc

.proc mover_celda_del_evento
.a8
.i16
    sta ruta_dir
    stz ruta_dir + 1            ; se usa como índice de dieciséis
    lda ruta_ev + 0, x
    rep #$20
.a16
    and #$00FF
    asl a
    asl a
    tay
    sep #$20
.a8
    ; Por tabla y no por cuatro comparaciones: con las diagonales la celda se
    ; corre en los dos ejes a la vez, y así el caso derecho es el que tiene un
    ; cero de un lado. X queda pisado; el que llama ya lo guardó.
    ldx ruta_dir
    lda f:paso_dx, x
    beq sin_dx
    jsr con_signo_16
.a16
    clc                         ; vuelve con el acumulador en dieciséis
    adc ev_pos_buf + 0, y
    sta ev_pos_buf + 0, y
    sep #$20
.a8
sin_dx:
    lda f:paso_dy, x
    beq sin_dy
    jsr con_signo_16
.a16
    clc
    adc ev_pos_buf + 2, y
    sta ev_pos_buf + 2, y
    sep #$20
.a8
sin_dy:
    rts
.endproc

; El byte con signo que trae A, extendido a dieciséis bits. Sale con el
; acumulador **en dieciséis**, que es donde lo quieren los que suman celdas.
.proc con_signo_16
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc listo
    ora #$FF00
listo:
    rts
.endproc

