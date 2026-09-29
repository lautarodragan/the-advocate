.segment "CODE"

; --- el héroe --------------------------------------------------------------
; RM2k no mueve al personaje libremente: se compromete a una celda vecina y
; recorre los 16 pixeles hasta ella sin poder frenar. Por eso el estado es la
; celda donde está más cuántos pixeles le faltan del paso en curso, y mientras
; falten no se acepta otra dirección.
;
; Los cuatro bits de pasabilidad son: abajo $01, izquierda $02, derecha $04,
; arriba $08. Cruzar de una celda a la de al lado pide permiso a las dos: la de
; origen tiene que dejar salir por ese lado y la de destino dejar entrar por el
; opuesto. Todo lo demás —que la capa alta manda salvo que sea decorado, que las
; caras de pared se cruzan siempre— ya lo resolvió el conversor.

PASS_DOWN  = $01
PASS_LEFT  = $02
PASS_RIGHT = $04
PASS_UP    = $08

.proc move_hero
.a8
.i16
    ; Si hay un paso en curso, se termina: no se puede frenar a mitad de celda.
    lda step_left
    beq quieto
    jsr advance_step
    rts

quieto:
    stz moving
    ; Sin paso en curso no hay paso de ruta que anotar. Se limpia acá y no al
    ; terminar la ruta porque lo que interesa es el paso, no la ruta.
    stz ruta_paso
    ; Un salto en el aire se lleva el cuadro entero, y se mira **antes** que el
    ; contador de órdenes: en RM2k estar saltando no es estar quieto
    ; —`IsStopping()` es `!(IsMoving() || IsJumping())`— así que `Update` baja el
    ; salto sin pasar por `UpdateNextMovementAction`. Con esto adentro de
    ; `paso_de_ruta`, que sólo se llama con `ruta_i < ruta_n`, un salto que era
    ; la última orden de la ruta no lo bajaba nadie. Ver `salto_avanzar_heroe`.
    lda ruta_salto
    beq sin_salto
    jsr salto_avanzar_heroe
    rts
sin_salto:
    ; Una ruta forzada manda sobre el pad: mientras quede, el jugador no mueve
    ; al héroe. Es lo que hace RM2k, y es lo que permite que una cinemática lo
    ; camine sola.
    ;
    ; Un `wait` pendiente también es ruta, aunque ya no queden órdenes: una
    ; ruta que **termina** en `wait` —hay 21 en el juego, la primera en el
    ; mapa 1— deja `ruta_i` igual a `ruta_n` con `ruta_espera` cargada, y sin
    ; esto no la bajaba nadie: `paso_de_ruta` es el único que la descuenta. En
    ; RM2k el `wait` es una orden más y la ruta sigue siendo del héroe hasta
    ; que se cumple. Quedaba pegada para siempre, y `hay_rutas` y la tecla de
    ; acción, que la miran, contestaban "hay ruta" hasta la próxima.
    lda ruta_espera
    bne con_ruta
    lda ruta_i
    cmp ruta_n
    bcs sin_ruta
con_ruta:
    jsr paso_de_ruta
    rts
sin_ruta:
    ; El pedido de menú, en el orden de `UpdateNextMovementAction`: con una
    ; página corriendo se tira; con un mensaje abierto espera; y si no, se
    ; abre el menú y el héroe no camina en este cuadro. Va antes de mirar
    ; `esperando_n` porque RM2k mira `IsAnyEventStarting` después.
    lda ev_activo
    beq menu_sin_pagina
    jsr menu_olvidar
    rts
menu_sin_pagina:
    lda msg_abierto
    bne no_derecha
    ; El encuentro que quedó pendiente se cobra acá: sin página corriendo, sin
    ; mensaje abierto y sin ruta forzada, que es el orden de
    ; `Game_Player::UpdateNextMovementAction` —el encuentro va **antes** del
    ; pedido de menú—. `encuentro_probar` deja la tropa en `BA_TROPA`.
    jsl f:encuentro_probar
    cmp #0                      ; el `plx` de allá dejó sus propias banderas
    beq sin_encuentro
    ; Y perderla es Game Over, igual que una pelea de página sin manejador de
    ; derrota: un encuentro al azar **nunca** los trae, porque no hay página
    ; que los emita. Sin esto la derrota devolvía el control al mapa con todo
    ; el grupo en cero HP, y de ahí en más cada pelea se perdía sola antes de
    ; abrirse —`batalla_correr` contesta derrota con nadie en pie—. Lo cobra
    ; `pelea_arrancar`: ver tools/runtime/game_over.s.
    jsl f:game_over_siempre
    jmp pelea_arrancar
sin_encuentro:
    jsr acceso_leer
    bpl menu_sin_pedido         ; el bit 7 es el pedido
    and #$7F
    jsr acceso_escribir
    jsr menu_pantalla
    rts
menu_sin_pedido:
    ; Y un mensaje en pantalla manda sobre el pad, igual que la ruta forzada.
    ; Es lo que hace `Game_Player::UpdateNextMovementAction` de easyrpg, que
    ; vuelve sin mirar el input si `Game_Message::IsMessageActive()`. Va acá
    ; abajo y no arriba de todo a propósito: la ruta forzada **sí** camina con
    ; el mensaje abierto —`UpdateMoveRoute` corre antes del guard— y un paso ya
    ; empezado se termina, porque en RM2k no se frena a mitad de celda.
    lda msg_abierto
    bne no_derecha
    ; Y una página corriendo también manda sobre el pad. Es el
    ; `if (Game_Map::IsAnyEventStarting()) return;` de
    ; `Game_Player::UpdateNextMovementAction`: mientras el intérprete tiene algo
    ; en el frente, el jugador no camina.
    ;
    ; Sin esto, un evento de contacto se disparaba y el héroe daba **un paso
    ; más** mientras el mensaje se componía: el mensaje tarda unos cuadros en
    ; abrirse y `msg_abierto` recién se prende al final.
    lda ev_activo
    bne no_derecha
    lda esperando_n
    bne no_derecha
    lda pad
    and #PAD_UP
    beq no_arriba
    lda #DIR_UP
    sta hero_dir
    jsr try_up
    bra tras_paso
no_arriba:
    lda pad
    and #PAD_DOWN
    beq no_abajo
    lda #DIR_DOWN
    sta hero_dir
    jsr try_down
    bra tras_paso
no_abajo:
    lda pad
    and #PAD_LEFT
    beq no_izquierda
    lda #DIR_LEFT
    sta hero_dir
    jsr try_left
    bra tras_paso
no_izquierda:
    lda pad
    and #PAD_RIGHT
    beq no_derecha
    lda #DIR_RIGHT
    sta hero_dir
    jsr try_right
tras_paso:
    ; Un paso que arrancó de verdad —`step_left` lo dice— es un paso de RM2k:
    ; `IncSteps` y `UpdateEncounterSteps`, que allá corren después de `Move()`
    ; y sólo si el héroe se movió. Va en la rama del pad y no adentro de
    ; `advance_step` porque **los pasos de una ruta forzada no cuentan**: allá
    ; se vuelve antes, por `IsMoveRouteOverwritten`.
    lda step_left
    beq no_derecha
    jsl f:encuentro_paso
no_derecha:
    rts
.endproc

; Cada intento comprueba el borde del mapa, después los dos permisos, y recién
; ahí arranca el paso.
; Los cuatro trabajan con el acumulador de 16 bits: la celda del héroe ya no
; entra en un byte —hay mapas de 500 celdas de ancho— y los permisos se buscan
; con índices de 16.
.proc try_up
.a8
.i16
    rep #$20
.a16
    lda tile_y
    beq no                      ; ya está en la fila de arriba
    lda #PASS_UP
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda tira_paso_col
    jsr ptr_menos               ; el destino: una fila de bloques más arriba
    lda #PASS_DOWN              ; y esa celda tiene que dejar entrar
    jsr can_enter
    beq no
    lda tile_x
    sta dest_x
    lda tile_y
    dec a
    sta dest_y
    sep #$20
.a8
    jsr heroe_bloqueado         ; alguien parado ahí lo frena como una pared
    bne no8
    rep #$20
.a16
    dec tile_y
    lda #0
    sta step_dx
    lda #$FFFF              ; -1: ca65 no acepta un inmediato negativo
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_down
.a8
.i16
    rep #$20
.a16
    lda tile_y
    inc a
    cmp mapa_alto
    bcs no
    lda #PASS_DOWN
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda tira_paso_col
    jsr ptr_mas                 ; una fila de bloques más abajo
    lda #PASS_UP
    jsr can_enter
    beq no
    lda tile_x
    sta dest_x
    lda tile_y
    inc a
    sta dest_y
    sep #$20
.a8
    jsr heroe_bloqueado         ; alguien parado ahí lo frena como una pared
    bne no8
    rep #$20
.a16
    inc tile_y
    lda #0
    sta step_dx
    lda #1
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_left
.a8
.i16
    rep #$20
.a16
    lda tile_x
    beq no
    lda #PASS_LEFT
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda #2
    jsr ptr_menos               ; la celda de al lado
    lda #PASS_RIGHT
    jsr can_enter
    beq no
    lda tile_x
    dec a
    sta dest_x
    lda tile_y
    sta dest_y
    sep #$20
.a8
    jsr heroe_bloqueado         ; alguien parado ahí lo frena como una pared
    bne no8
    rep #$20
.a16
    dec tile_x
    lda #$FFFF              ; -1: ca65 no acepta un inmediato negativo
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
no8:
    rts
.endproc

.proc try_right
.a8
.i16
    rep #$20
.a16
    lda tile_x
    inc a
    cmp mapa_ancho
    bcs no
    lda #PASS_RIGHT
    jsr can_leave
    beq no
    jsr ptr_desde_hero
    lda #2
    jsr ptr_mas
    lda #PASS_LEFT
    jsr can_enter
    beq no
    lda tile_x
    inc a
    sta dest_x
    lda tile_y
    sta dest_y
    sep #$20
.a8
    jsr heroe_bloqueado         ; alguien parado ahí lo frena como una pared
    bne no8
    rep #$20
.a16
    inc tile_x
    lda #1
    sta step_dx
    lda #0
    sta step_dy
    sep #$20
.a8
    jsr begin_step
    rts
no:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
no8:
    rts
.endproc

; --- la pasabilidad --------------------------------------------------------
; Ya no hay una tabla con un byte por celda: los permisos viajan en el bloque.
; Son dos saltos —la celda dice qué bloque es, el bloque dice qué permisos
; tiene— y a cambio el mapa más grande se ahorra veinte kilobytes. Que dos
; celdas dibujadas igual pero con permisos distintos no se confundan lo
; garantiza el conversor, que mete la pasabilidad en la clave del bloque.
;
; Dónde está el héroe dentro de la grilla tampoco es un índice: es un puntero
; que se mueve con él, una celda o una fila por paso. Así nunca hay que
; multiplicar ni recalcular una dirección de 24 bits desde cero, que en LoROM
; es incómodo porque los bancos no son contiguos.

; A = el bit que hace falta. Devuelve con Z apagado si la celda lo tiene.
.proc can_leave
.a16
.i16
    sta temp
    lda tile_x                  ; la celda que se deja, para lo que un evento
    sta pasa_x                  ; de tile le imponga
    lda tile_y
    sta pasa_y
    jsr ptr_desde_hero
    jsr pass_del_ptr
    jsr pasa_con_evento
    and temp
    ora atravesando             ; con walk_everywhere la respuesta es que sí
    rts
.endproc

; Igual, pero sobre la celda a la que celdas_ptr ya quedó apuntando: cada
; dirección lo corre por su cuenta antes de llamar, y si el paso se acepta
; begin_step lo copia a hero_ptr. Así el destino se calcula una sola vez.
.proc can_enter
.a16
.i16
    sta temp
    ; La celda de destino: la del héroe más el paso en `hero_dir`, que es
    ; siempre la dirección del paso, también en una ruta forzada.
    lda tile_x
    sta pasa_x
    lda tile_y
    sta pasa_y
    sep #$20
.a8
    lda hero_dir
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda f:paso_dx, x
    jsr sumar_a_pasa_x
    lda f:paso_dy, x
    jsr sumar_a_pasa_y
    rep #$20
.a16
    jsr pass_del_ptr
    jsr pasa_con_evento
    and temp
    ora atravesando
    rts
.endproc

; Los bits de paso de la celda `pasa_x`/`pasa_y`: los que trae A —los del
; terreno, de `pass_del_ptr`— salvo que un evento de tile en la capa de abajo
; le imponga los suyos. Es `Game_Map::IsPassableTile`: de los eventos parados
; ahí con página activa y gráfico de tile en esa capa gana el de id más alto,
; y si su tile no es de los que van por encima, manda. Los bits los dejó el
; refresco en la fila del NPC, +15, o $FF si no impone nada; así esto es un
; recorrido de la tabla de NPCs por paso y no una pasada por las páginas. Lo
; que no se modela: el "conflicto consigo mismo" de un evento de tile que
; camina, porque ninguno camina. Entra y sale en dieciséis bits.
.proc pasa_con_evento
.a16
.i16
    ; De la última fila para atrás y en dieciséis bits: gana la última que
    ; imponga, así que la primera que aparezca así es la respuesta. Corre dos
    ; veces por cada paso que empieza, y de adelante para atrás y con un
    ; `rep`/`sep` por fila eran nueve líneas por vez en la carrera, con
    ; cuarenta autos: ver workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
    sta temp + 2
    lda pasa_hay
    and #$00FF
    beq ninguno                 ; ninguna fila de este mapa impone nada
    ldy npc_total
    bra siguiente
otra:
    lda npc_buf + 14, y         ; si está, y arriba lo que impone
    cmp #$FF00
    bcs siguiente               ; $FF: no impone nada
    bit #$00FF
    beq siguiente               ; escondido: no está
    lda npc_buf + 8, y          ; su evento, y con él su celda
    and #$00FF
    asl a
    asl a                       ; por EV_STRIDE
.assert EV_STRIDE = 4, error, "la cuenta de arriba multiplica por cuatro a mano"
    tax
    lda ev_pos_buf, x
    cmp pasa_x
    bne siguiente
    lda ev_pos_buf + 2, x
    cmp pasa_y
    bne siguiente
    lda npc_buf + 14, y
    xba
    and #$00FF                  ; los bits de paso que impone
    rts
siguiente:
    tya
    sec
    sbc #NPC_STRIDE
    tay
    bpl otra
ninguno:
    lda temp + 2                ; ninguno: los del terreno
    rts
.endproc

.proc sumar_a_pasa_x
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positivo
    ora #$FF00
positivo:
    clc
    adc pasa_x
    sta pasa_x
    sep #$20
.a8
    rts
.endproc
.proc sumar_a_pasa_y
.a8
.i16
    rep #$20
.a16
    and #$00FF
    cmp #$0080
    bcc positivo
    ora #$FF00
positivo:
    clc
    adc pasa_y
    sta pasa_y
    sep #$20
.a8
    rts
.endproc

.proc pass_del_ptr
.a16
.i16
    lda [celdas_ptr]            ; qué bloque es esta celda
    jsr celda_sustituida
    tay
    sep #$20
.a8
    lda [pass_ptr], y
    rep #$20
.a16
    and #$00FF
    rts
.endproc

.proc ptr_desde_hero
.a16
.i16
    lda hero_ptr
    sta celdas_ptr
    sep #$20
.a8
    lda hero_ptr + 2
    sta celdas_ptr + 2
    rep #$20
.a16
    rts
.endproc

.proc ptr_a_hero
.a16
.i16
    lda celdas_ptr
    sta hero_ptr
    sep #$20
.a8
    lda celdas_ptr + 2
    sta hero_ptr + 2
    rep #$20
.a16
    rts
.endproc

; El puntero a la celda (celda_x, celda_y) de la grilla.
;
; Está separado de `init_hero_ptr` porque ahora hay más de uno que camina: las
; rutas forzadas de los eventos consultan celdas que no son la del héroe, y
; tener la cuenta escrita dos veces es cómo se separan.
;
; El desplazamiento es `celda_y * tira_paso_col + celda_x * 2`, con el
; multiplicador de la CPU —ocho por ocho bits, así que en tres productos: el
; de los dos bytes bajos y los dos cruzados, que caen corridos un byte; el de
; los dos altos cae fuera de los dieciséis— y no sumando una fila por cada
; fila que baja, que es lo que hacía hasta el 2026-09-27: en la fila 26 eran
; cuatro líneas por paso de cada evento que anda, y en la carrera arrancan
; cinco pasos en el mismo cuadro. Ninguna interrupción usa el multiplicador:
; ver el fundido de `irq_musica`.
;
; La grilla cabe en 64 KB y vive en la mitad alta de los dos bancos —ver
; `ptr_mas`—, así que el desplazamiento entra en dieciséis bits y su bit 15
; dice el banco: sin él, la mitad alta del $7E (se le prende el bit), y con
; él la del $7F (ya lo tiene).
.proc ptr_de_celda
.a8
.i16
    lda celda_y
    sta WRMPYA
    lda tira_paso_col
    sta WRMPYB                  ; ocho ciclos: los paga lo que sigue
    rep #$20
.a16
    lda celda_x
    asl a                       ; cada celda ocupa dos bytes
    sta celdas_ptr
    lda RDMPYL                  ; y bajo por paso bajo
    clc
    adc celdas_ptr
    sta celdas_ptr
    sep #$20
.a8
    lda tira_paso_col + 1
    beq sin_paso_alto
    sta WRMPYB                  ; y bajo por paso alto: WRMPYA sigue siendo y
    nop
    nop
    nop
    nop
    lda RDMPYL
    clc
    adc celdas_ptr + 1
    sta celdas_ptr + 1
sin_paso_alto:
    lda celda_y + 1
    beq sin_y_alta
    sta WRMPYA
    lda tira_paso_col
    sta WRMPYB                  ; y alto por paso bajo
    nop
    nop
    nop
    nop
    lda RDMPYL
    clc
    adc celdas_ptr + 1
    sta celdas_ptr + 1
sin_y_alta:
    lda celdas_ptr + 1
    bmi alta
    ora #>$8000
    sta celdas_ptr + 1
    lda #^GRILLA
    sta celdas_ptr + 2
    rts
alta:
    lda #^GRILLA_ALTA
    sta celdas_ptr + 2
    rts
.endproc
.assert .loword(GRILLA) = $8000 && .loword(GRILLA_ALTA) = $8000 && ^GRILLA_ALTA = ^GRILLA + 1, error, "ptr_de_celda arma el puntero con la grilla en las dos mitades altas"

; Dónde arranca el héroe dentro de la grilla.
.proc init_hero_ptr
.a8
.i16
    rep #$20
.a16
    lda tile_x
    sta celda_x
    lda tile_y
    sta celda_y
    sep #$20
.a8
    jsr ptr_de_celda
    rep #$20
.a16
    jsr ptr_a_hero
    sep #$20
.a8
    rts
.endproc

; Arranca el paso: una celda entera por recorrer —128 medias unidades, ver
; `paso_medio_por_vel`— y el índice ya en la celda nueva, que es como RM2k
; lleva la cuenta.
.proc begin_step
.a8
.i16
    lda #128
    sta step_left
    rep #$20
.a16
    jsr ptr_a_hero              ; RM2k cuenta desde la celda de destino, que es
    sep #$20                    ; adonde can_enter dejó apuntado el puntero
.a8
    jsr advance_step
    rts
.endproc

; Avanza los pixeles de este cuadro y, si con eso se completa el paso, deja al
; personaje exactamente sobre la celda.
.proc advance_step
.a8
.i16
    lda #$01
    sta moving
    ; Lo que falta del paso baja lo que diga la velocidad, y los pixeles se
    ; **recalculan** desde la celda de destino y no se acumulan: con medio
    ; pixel por cuadro no hay nada entero que sumar. `step_dx` y `step_dy` son
    ; el sentido del paso, -1, 0 o 1.
    jsr anim_cuadros_del_heroe  ; de paso deja X en la velocidad menos uno
    lda step_left
    sec
    sbc paso_medio_por_vel, x
    bcs no_negativo
    lda #0
no_negativo:
    sta step_left
    lsr a
    lsr a
    lsr a                       ; los pixeles que faltan
    rep #$20
.a16
    and #$00FF
    sta temp                    ; nadie lo tiene tomado en un paso
    lda tile_x
    asl a
    asl a
    asl a
    asl a
    ldx step_dx
    beq x_listo
    bmi x_desde_la_derecha
    sec
    sbc temp
    bra x_listo
x_desde_la_derecha:
    clc
    adc temp
x_listo:
    sta hero_x
    lda tile_y
    asl a
    asl a
    asl a
    asl a
    ldx step_dy
    beq y_listo
    bmi y_desde_abajo
    sec
    sbc temp
    bra y_listo
y_desde_abajo:
    clc
    adc temp
y_listo:
    sta hero_y
    sep #$20
.a8
    lda step_left
    bne sigue                   ; el paso todavía no terminó
    ; Mientras al héroe le quede ruta forzada no se pisa nada: ni puerta ni
    ; evento de contacto. Es el `!IsMoveRouteOverwritten()` de
    ; `Game_Player::UpdateMovement`, y el último paso sí cuenta porque en
    ; `Game_Character::UpdateMovement` un movimiento que es la última orden
    ; cancela la ruta entera **antes** del chequeo —está comentado ahí: "If
    ; the last command of a move route is a move or jump, RPG_RT cancels the
    ; entire move route immediately"—. Con `ruta_i` ya pasado de la última
    ; orden, la ruta está cancelada; con órdenes por leer, no. Es lo que deja
    ; a la cinemática de apertura pisar el evento que apaga el tinte: son tres
    ; celdas para arriba y el evento está en la tercera.
    lda ruta_i
    cmp ruta_n
    bcs sin_ruta                ; no quedan órdenes: puerta y contacto
    ; Quedan: el paso es del medio, y la frecuencia dice cuántos cuadros
    ; quieto antes de leer la siguiente. Vale aunque el paso lo haya arrancado
    ; el pad: en RM2k `UpdateMovement` pone el contador en cero al terminar
    ; cualquier paso, y `ForceMoveRoute` ya dejó el tope de la ruta.
    lda ruta_frec
    jsr tras_paso
    sta ruta_espera
    bra sigue
sin_ruta:
    ; Recién parado en la celda: ¿hay un evento de contacto? Una puerta es uno
    ; de ésos —una página de contacto cuyo único comando es el `Teleport`— así
    ; que no tiene camino propio: cruza por el intérprete, como cualquier otro
    ; teletransporte.
    jsr probar_contacto
sigue:
    rts
.endproc

; --- animación de caminata -------------------------------------------------
; El ciclo son cuatro pasos sobre tres frames del CharSet: 0, 1, 2, 1. El del
; medio es la pose parada, y es a la que se vuelve al soltar la cruceta.
.proc animate_hero
.a8
.i16
    ; Con la animación parada por una ruta la pose se queda en la del medio,
    ; camine o no: RM2k llama a `ResetAnimation` en cada cuadro mientras
    ; `IsAnimPaused()`, que deja el frame del medio y el contador en cero.
    lda ruta_anim_para
    bne quieto
    lda moving
    bne caminando
quieto:
    lda #1                      ; quieto: el frame del medio
    sta anim_step
    stz anim_timer
    rts

caminando:
    ; La cuenta sube y se compara con el tope **de la velocidad de ahora**,
    ; como `GetAnimCount() >= stationary_limit`: si una ruta cambia la
    ; velocidad a mitad de un frame, el frame que viene ya sale con la nueva.
    ; Contando para abajo desde el tope, como antes, la nueva recién valía un
    ; frame después: un cuadro de diferencia con RM2k.
    inc anim_timer
    jsr anim_cuadros_del_heroe
    cmp anim_timer
    beq cambia
    bcs listo                   ; la cuenta todavía no llegó al tope
cambia:
    stz anim_timer
    lda anim_step
    inc a
    and #$03                    ; el ciclo son cuatro pasos
    sta anim_step
listo:
    rts
.endproc

