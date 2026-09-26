.segment "CODE"

; --- armado de OAM ---------------------------------------------------------
; Un objeto por NPC más uno para el héroe, en el orden en que RM2k los dibuja:
; primero por capa y recién después por Y. En la consola el objeto con índice
; más bajo de OAM es el que se ve encima, así que se recorre del frente hacia el
; fondo — que es como el conversor dejó ordenada la tabla.
;
; El héroe se intercala donde le toca por su clave, no va siempre primero ni
; siempre último: un evento "below" tiene que quedar debajo de él aunque esté
; más adelante en pantalla, y uno "above" taparlo siempre.
.proc build_oam
.a8
.i16
    ; Todo escondido antes de empezar. Esconder sólo la cola al terminar deja
    ; los objetos que este cuadro no usó con los datos del anterior, y basta con
    ; que la cámara se mueva para que la cuenta cambie y alguno reaparezca donde
    ; no va. Son 128 escrituras y sacan de encima toda esa clase de error.
    jsr clear_oam
    stz high_acc
    stz hero_drawn
    rep #$20
.a16
    stz high_ptr
    stz oam_slot
    stz npc_ofs
    ; La clave del héroe: su capa arriba y su Y abajo, igual que en la tabla.
    lda hero_y
    and #$0FFF
    ora #(HERO_LAYER * 4096)
    sta hero_key
    sep #$20
.a8
    ; El cronómetro va antes que nadie: sus objetos son los de índice más bajo
    ; y por eso los que se ven adelante. Deja `obj_grande` en 32x32.
    lda #$02
    sta obj_grande
    jsr timer_oam
    jsr imagen_oam              ; y el cartel detrás de él: ver `imagen_oam`
    jsr animacion_dibujo_oam    ; y la animación de batalla detrás del cartel:
                                ; `Priority_BattleAnimation` es 110 contra los
                                ; 120 de `Priority_PictureOld`

recorrer:
    rep #$20
.a16
    lda npc_ofs
    cmp npc_total
    sep #$20
.a8
    beq ultimos

    lda hero_drawn
    bne toca_npc
    ; ¿Va el héroe antes que este NPC? Sí si su clave es mayor o igual, porque
    ; la tabla va de mayor a menor.
    ldx npc_ofs
    rep #$20
.a16
    lda hero_key
    cmp npc_buf + 4, x
    sep #$20
.a8
    bcc toca_npc
    jsr place_hero
    bra recorrer

toca_npc:
    ldx npc_ofs
    lda npc_buf + 14, x
    beq escondido               ; su página activa no dibuja nada
    jsr place_npc
escondido:
    rep #$20
.a16
    lda npc_ofs
    clc
    adc #NPC_STRIDE
    sta npc_ofs
    sep #$20
.a8
    bra recorrer

ultimos:
    lda hero_drawn
    bne cerrar
    jsr place_hero
cerrar:
    jsr lluvia_oam              ; las gotas, al final de todo
    jsr flush_high
    rts
.endproc

; El salto del héroe: consume las órdenes hasta `end_jump`, suma lo que aportan
; y lo pone del otro lado de una. Lo que dura no depende de la distancia:
; `remaining_step` baja de 256 a 0 a `salto_del_heroe` por cuadro, salte una
; celda o cinco; a la velocidad 4 son once cuadros.
.proc armar_salto_heroe
.a8
.i16
    stz salto_dx
    stz salto_dy
buscar:
    lda ruta_i
    cmp ruta_n
    bcs sin_fin
    rep #$20
.a16
    lda ruta_i
    and #$00FF
    tax
    sep #$20
.a8
    lda ruta, x
    inc ruta_i
    cmp #25
    beq con_fin
    jsr acumular_salto
    bra buscar
sin_fin:
    ; Sin `end_jump` el salto se saltea y lo que quedaba de ruta se pierde, que
    ; es lo que hace RM2k al llegar al final.
    stz ruta_salto
    rts

con_fin:
    jsr salto_a_celdas          ; el desplazamiento, con signo y en dieciséis
    rep #$20
.a16
    lda tile_x
    clc
    adc salto_dx16
    sta celda_x
    lda tile_y
    clc
    adc salto_dy16
    sta celda_y
    sep #$20
.a8
    ; Atravesando paredes se cae en cualquier celda: es el mismo
    ; `if (self.GetThrough()) return true;` que mira un paso, y `puede_caer`
    ; lo lee de `atravesando`, que acá nadie ponía. La ruta de EV0041 del mapa
    ; 8 —`through`, salto de una celda sobre la reja, cuatro pasos— en RM2k
    ; salta y en la ROM caminaba: el salto se salteaba por la reja y los pasos
    ; de después sí atravesaban. Medido el 2026-09-10, 40840
    ; pixeles en el cuadro 60.
    lda ruta_atraviesa
    beq sin_atravesar
    lda #1
sin_atravesar:
    sta atravesando
    stz atravesando + 1
    jsr puede_caer
    php
    stz atravesando
    stz atravesando + 1
    plp
    bne se_puede
    stz ruta_salto              ; no se puede caer ahí: el salto se saltea
    rts
se_puede:
    rep #$20
.a16
    lda celda_x
    sta tile_x
    lda celda_y
    sta tile_y
    sep #$20
.a8
    jsr init_hero_ptr
    ; Hacia dónde queda mirando. En el lugar no cambia nada: RM2k sólo fija el
    ; mirado cuando el salto se mueve.
    lda salto_dx
    ora salto_dy
    beq sin_girar
    jsr direccion_del_salto
    sta hero_dir
sin_girar:
    ; El primer descuento va en el mismo cuadro que arma el salto, como en
    ; `Game_Character::Update`, que después de `UpdateNextMovementAction` ya lo
    ; ve saltando y llama a `UpdateMovement`. SALTO_PASO es 256 y no entra en
    ; un byte: `256 - s` en ocho bits es el complemento a dos de `s`, que
    ; nunca es cero.
    jsr salto_del_heroe
    eor #$FF
    inc a
    sta ruta_salto
    ; La celda ya es la de destino y los pixeles van detrás, igual que en un
    ; paso: así la cámara acompaña el arco en vez de saltar de una.
    jsr salto_posicion_heroe
    rts
.endproc

; Un cuadro de un salto del héroe que está en el aire: le baja el arco que le
; queda y lo redibuja donde toque. La celda ya se movió al empezar, así que lo
; único que pasa acá son los pixeles.
;
; Vive afuera de `paso_de_ruta` —y la llama `move_hero`— porque en RM2k el que
; baja el salto es `Game_Character::Update`, que mira `IsJumping()` **antes** de
; preguntar si quedan órdenes, y el que lo apaga es `UpdateMovement`. Mientras
; estuvo adentro de `paso_de_ruta`, un salto que era la última orden de la ruta
; no lo bajaba nadie: `move_hero` sólo entraba ahí con `ruta_i < ruta_n`, y con
; el salto al final el contador ya estaba al tope en el cuadro siguiente. El
; héroe quedaba flotando a mitad del arco para siempre, y 196 de las 410 rutas
; con salto del juego terminan en el salto. Ver `test_salto_colgado.py`.
;
; El descuento se lee de la velocidad cada cuadro, como `Update` de RM2k, que
; llama a `GetMoveSpeed()` cada vez. Hasta el 2026-09-26 era la constante de la
; velocidad 4 y un `increase_movement_speed` sobre el héroe le cambiaba el paso
; y no el salto. Ver `test_salto_velocidad.py`.
.proc salto_avanzar_heroe
.a8
.i16
    ; `ruta_salto - s` sin guardar `s` en ningún lado: `~s + 1` con el acarreo
    ; en uno es la resta, y el acarreo sale en cero si hubo préstamo.
    jsr salto_del_heroe
    eor #$FF
    sec
    adc ruta_salto
    bcs guardar
    lda #0
guardar:
    sta ruta_salto
    jmp salto_posicion_heroe
.endproc

; `hero_x` y `hero_y` desde la celda de destino y lo que le queda al salto. Es
; `GetSpriteX` de RM2k: `x * 256 - dx * restante` y **después** la división por
; dieciséis, que es lo que evita el pixel de más o de menos cada vez que el
; descuento no es múltiplo de dieciséis.
.proc salto_posicion_heroe
.a8
.i16
    jsr salto_a_celdas
    lda ruta_salto
    sta salto_resta
    rep #$20
.a16
    lda salto_dx16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda tile_x
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; la celda en las unidades de RM2k: por 256
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta hero_x
    lda salto_dy16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda tile_y
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta hero_y
    sep #$20
.a8
    rts
.endproc

; `salto_dx` y `salto_dy` con el signo extendido a dieciséis bits.
.proc salto_a_celdas
.a8
.i16
    rep #$20
.a16
    lda salto_dx
    and #$00FF
    cmp #$0080
    bcc dx_positivo
    ora #$FF00
dx_positivo:
    sta salto_dx16
    lda salto_dy
    and #$00FF
    cmp #$0080
    bcc dy_positivo
    ora #$FF00
dy_positivo:
    sta salto_dy16
    sep #$20
.a8
    rts
.endproc

; Hacia dónde queda mirando quien salta: gana el eje de mayor recorrido y con
; empate el vertical. Es el `if (abs(dy) >= abs(dx))` de `Game_Character::Jump`.
.proc direccion_del_salto
.a8
.i16
    rep #$20
.a16
    lda salto_dx16
    bpl dx_pos
    eor #$FFFF
    inc a
dx_pos:
    sta mirar_abs
    lda salto_dy16
    bpl dy_pos
    eor #$FFFF
    inc a
dy_pos:
    cmp mirar_abs
    bcc horizontal
    lda salto_dy16
    sep #$20
.a8
    bmi arriba
    lda #DIR_DOWN
    rts
arriba:
    lda #DIR_UP
    rts
.a16
horizontal:
    lda salto_dx16
    sep #$20
.a8
    bmi izquierda
    lda #DIR_RIGHT
    rts
izquierda:
    lda #DIR_LEFT
    rts
.endproc

; Corre `salto_px`/`salto_py` hacia atrás por lo que le falta al salto y deja en
; `salto_alto` cuánto hay que levantar el dibujo.
;
; La altura es `GetJumpHeight`: sube y baja con lo que queda, y la curva no es
; lineal sino la tabla de RM2k. Sólo mueve el **dibujo**: el orden contra los
; demás sale de `GetScreenY(false)`, o sea sin el salto, así que quien está en
; el aire no se adelanta.
.proc alto_del_salto
.a8
.i16
    stz salto_alto
    stz salto_alto + 1
    lda salto_resta
    bne hay
    rts
hay:
    ; Lo que queda o lo que se recorrió, el menor de los dos, sobre ocho; y
    ; después la tabla de RM2k, que no es lineal. Es `GetJumpHeight`, y sólo
    ; mueve el **dibujo**: el orden contra los demás sale de `GetScreenY(false)`,
    ; o sea sin el salto, así que quien está en el aire no se adelanta.
    cmp #(SALTO_PASO / 2)
    bcc de_bajada
    eor #$FF                    ; 256 - resta, con resta de un byte
    inc a
de_bajada:
    lsr a
    lsr a
    lsr a
    cmp #5
    bcs mediana
    asl a                       ; menos de cinco: el doble
    bra guardar
mediana:
    cmp #13
    bcs tope
    clc
    adc #4                      ; de cinco a doce: más cuatro
    bra guardar
tope:
    lda #16
guardar:
    sta salto_alto
    rts
.endproc

; `salto_val` por `salto_resta`, con signo, en `salto_prod`. La unidad de la
; consola multiplica sin signo y de a ocho bits, así que se hace sobre el valor
; absoluto y se le devuelve el signo al final.
.proc producto_salto
.a8
.i16
    rep #$20
.a16
    lda salto_val
    sta salto_signo
    bpl positivo
    eor #$FFFF
    inc a
    sta salto_val
positivo:
    sep #$20
.a8
    lda salto_val
    sta WRMPYA
    lda salto_resta
    sta WRMPYB                  ; arranca: el producto tarda ocho ciclos
    nop
    nop
    nop
    nop
    rep #$20
.a16
    lda RDMPYL
    sta salto_prod
    lda salto_signo
    bpl listo
    lda #0
    sec
    sbc salto_prod
    sta salto_prod
listo:
    sep #$20
.a8
    rts
.endproc

; El salto de un evento. Igual que el del héroe, pero leyendo la ruta del
; cartucho y guardando el estado en la ranura. X es la ranura y hay que
; devolverla intacta.
.proc armar_salto_ev
.a8
.i16
    stz salto_dx
    stz salto_dy
    stz salto_trabado
buscar:
    lda ruta_ev + 5, x
    cmp ruta_ev + 4, x
    bcs sin_fin
    rep #$20
.a16
    and #$00FF
    tay
    sep #$20
.a8
    lda [ruta_ptr], y
    inc ruta_ev + 5, x
    cmp #25
    beq con_fin
    phx
    jsr acumular_salto
    plx
    bra buscar
sin_fin:
    ; Sin `end_jump` el salto se saltea y lo que quedaba de ruta se pierde.
    stz ruta_ev + 13, x
    rts

con_fin:
    ; `walk_everywhere`: `CheckOrMakeWayEx` corta con `if (self.GetThrough())
    ; return true;` apenas pasa el chequeo de límites, así que el que atraviesa
    ; paredes cae donde sea. Sin esto, la piedra del recuerdo de Core es una
    ; celda cerrada y el salto se saltea; taro lo vio como que Core se mueve
    ; arriba de su islita y no salta nunca, y la ruta que lo mueve arranca
    ; justamente con un `atravesar_on`.
    lda ruta_ev + 12, x
    and #$01
    sta atravesando
    stz atravesando + 1
    phx
    jsr celda_del_evento        ; su celda, que `puede_caer` necesita
    jsr salto_a_celdas
    rep #$20
.a16
    lda celda_x
    clc
    adc salto_dx16
    sta celda_x
    lda celda_y
    clc
    adc salto_dy16
    sta celda_y
    sep #$20
.a8
    jsr puede_caer
    plx
    stz atravesando
    stz atravesando + 1
    cmp #0                      ; `plx` pone Z según lo que saca de la pila
    bne se_puede
    stz ruta_ev + 13, x
    inc salto_trabado           ; había `end_jump` y la celda está ocupada
    rts
se_puede:
    ; La celda de destino, que `celda_del_evento` dejó en celda_x/celda_y.
    phx
    jsr mover_celda_a_evento
    plx
    lda salto_dx
    sta ruta_ev + 14, x
    lda salto_dy
    sta ruta_ev + 15, x
    ; Hacia dónde queda mirando. En el lugar no cambia nada.
    lda salto_dx
    ora salto_dy
    beq sin_girar
    phx
    jsr direccion_del_salto
    plx
    sta ruta_ev + 8, x
sin_girar:
    jsr salto_de_ranura
    sta temp
    lda #0                      ; 256 menos lo de este cuadro, en ocho bits
    sec
    sbc temp
    sta ruta_ev + 13, x
    rts
.endproc

; `npc_px` y `npc_py` desde la celda de destino y lo que le queda al salto. Es
; la misma cuenta que `salto_posicion_heroe`, con la división al final.
.proc salto_posicion_npc
.a8
.i16
    jsr salto_a_celdas
    rep #$20
.a16
    lda salto_dx16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda celda_x
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a                       ; la celda en las unidades de RM2k: por 256
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta npc_px
    lda salto_dy16
    sta salto_val
    sep #$20
.a8
    jsr producto_salto
    rep #$20
.a16
    lda celda_y
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    sec
    sbc salto_prod
    lsr a
    lsr a
    lsr a
    lsr a
    sta npc_py
    sep #$20
.a8
    rts
.endproc

; --- el salto de una ruta --------------------------------------------------
; Suma al salto lo que aporta una orden. Es el lazo de `BeginMoveRouteJump`: lo
; que hay entre `begin_jump` y `end_jump` **no se camina**, se suma, y sólo
; cuentan los `move_*` y los que giran. Todo lo demás —una espera, parar la
; animación, cambiar la velocidad— RM2k lo consume ahí adentro sin hacer nada,
; y el juego mete de las tres cosas.
;
; Entra en A el código de la orden; deja `salto_dx` y `salto_dy`.
.proc acumular_salto
.a8
.i16
    cmp #8                      ; los cuatro derechos y las cuatro diagonales:
    bcs no_mueve                ; adentro de un salto una diagonal aporta sus
                                ; dos ejes, que es lo que suma RM2k
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda salto_dx
    clc
    adc f:paso_dx, x
    sta salto_dx
    lda salto_dy
    clc
    adc f:paso_dy, x
    sta salto_dy
    rts
no_mueve:
    ; Los `face_*` no aportan desplazamiento, y girar sin moverse no se
    ; compila, así que adentro de un salto no queda nada más que hacer: RM2k
    ; consume el resto sin tocar nada, ni siquiera un `wait`.
    rts
.endproc

; ¿Se puede caer en la celda `celda_x`, `celda_y`? Vuelve con Z=0 si sí.
;
; No es lo mismo que poder pisarla caminando: es `CheckOrMakeWayEx` con el
; personaje saltando, que **saltea la cara que se deja** —de ahí que se pueda
; saltar desde un lugar del que no se podría caminar— y pide que la de destino
; sea pasable por los cuatro lados, no sólo por la que se entra.
.proc puede_caer
.a8
.i16
    rep #$20
.a16
    lda celda_x
    bmi no_16
    cmp mapa_ancho
    bcs no_16
    lda celda_y
    bmi no_16
    cmp mapa_alto
    bcs no_16
    sep #$20
.a8
    ; El que atraviesa paredes cae en cualquier celda del mapa: es el
    ; `if (self.GetThrough()) return true;` de `CheckOrMakeWayEx`, que va
    ; **después** de mirar los límites y antes de todo lo demás.
    lda atravesando
    beq mira_el_paso
    lda #1
    rts
mira_el_paso:
    jsr ptr_de_celda
    rep #$20
.a16
    jsr pass_del_ptr
    sep #$20
.a8
    and #(PASS_UP | PASS_DOWN | PASS_LEFT | PASS_RIGHT)
    cmp #(PASS_UP | PASS_DOWN | PASS_LEFT | PASS_RIGHT)
    bne no
    ; Y que no haya nadie parado ahí: el salto también es `MakeWay`, y mira a
    ; los demás igual que un paso.
    rep #$20
.a16
    lda celda_x
    sta dest_x
    lda celda_y
    sta dest_y
    sep #$20
.a8
    jsr celda_bloqueada
    bne no
    lda #1
    rts
.a16
no_16:
    sep #$20
.a8
no:
    lda #0
    rts
.endproc


; --- un NPC ----------------------------------------------------------------
.proc place_npc
.a8
.i16
    ldx npc_ofs
    rep #$20
.a16
    lda npc_buf + 0, x        ; su posición en el mapa
    sec
    sbc pantalla_x
    sec
    sbc #SPRITE_OFF_X
    sta obj_x
    ; Lo que `emit_object` iba a descartar se descarta **acá**, con la misma
    ; comparación y antes de armar el resto de la fila. Descarta lo mismo que
    ; antes, objeto por objeto, así que la OAM sale idéntica; lo que cambia es
    ; cuánto cuesta un NPC que no se ve. Un mapa como el 11 tiene cincuenta
    ; filas dibujadas y treinta en pantalla, y las veinte de afuera pagaban la
    ; Y, el salto y los dos bytes del tile para que `emit_object` las tirara.
    ; Va partido en dos —primero la X, después la Y— porque la mitad sale por
    ; la primera y ésa no necesita leer nada más de la fila.
    clc
    adc #32
    cmp #(256 + 32)
    bcs fuera
    lda npc_buf + 2, x
    sec
    sbc camara_y
    sec
    sbc #SPRITE_OFF_Y
    sta obj_y
    ; Y el arco del salto, si está saltando. Va aparte y en ocho bits porque el
    ; byte 11 de la fila es el último de la ranura: leerlo de a dos se llevaría
    ; el primero de la siguiente.
    sep #$20
.a8
    stz temp + 1
    lda npc_buf + 11, x
    sta temp
    rep #$20
.a16
    lda obj_y
    sec
    sbc temp
    sta obj_y
    ; La otra mitad del descarte, ya con el salto sumado: el mismo corte en 224
    ; de `emit_object`, con el mismo porqué.
    clc
    adc #32
    cmp #(224 + 32)
    bcs fuera
    sep #$20
.a8
    lda npc_buf + 6, x
    sta obj_tile
    lda npc_buf + 7, x
    sta obj_attr
    jsr emit_object
    rts
.a16
fuera:
    sep #$20
.a8
    rts
.endproc

; --- el héroe --------------------------------------------------------------
.proc place_hero
.a8
.i16
    inc hero_drawn

    ; El frame del CharSet: los pasos 0 y 2 son los de los costados, y los
    ; pasos 1 y 3 son los dos la pose del medio.
    lda anim_step
    cmp #$03
    bne sin_ajuste
    lda #$01
sin_ajuste:
    sta temp

    ; La pose es dirección*3 + frame, y qué tile le toca lo dice la tabla del
    ; actor que está al frente del grupo. Antes se calculaba —el héroe era
    ; siempre el personaje 0 del banco, así que su bloque salía de una cuenta—,
    ; y eso dejó de valer cuando `ChangePartyMembers` puede cambiar el líder en
    ; caliente. La tabla además da lugar a tiles de más de ocho bits, que es lo
    ; que pasa en cuanto hay unos cuantos personajes en el banco.
    lda hero_dir
    asl a
    clc
    adc hero_dir                ; dirección * 3
    clc
    adc temp                    ; más el frame
    sta pose_heroe
    ; Sin grupo el puntero a la tabla queda en cero: no se dibuja nada.
    lda hero_poses + 2
    beq sin_dibujar
    ; El puntero a la pose: tres bytes por pose en la tabla del actor.
    lda pose_heroe
    asl a
    clc
    adc pose_heroe              ; por tres
    rep #$20
.a16
    and #$00FF
    tay
    lda [hero_poses], y
    sta vq_src
    sep #$20
.a8
    iny
    iny
    lda [hero_poses], y
    sta vq_src + 2
    ; $FFFFFF es el centinela de "este actor no tiene gráfico". Le pasa al
    ; actor 10, DummyHero, que es con el que el juego arranca: RM2k tampoco
    ; dibuja nada.
    lda vq_src
    and vq_src + 1
    cmp #$FF
    beq sin_dibujar

    ; El tile es fijo: el héroe vive en el bloque 0 del banco, y lo que cambia
    ; son los tiles del bloque. Si la pose que hay en VRAM es otra, se encola
    ; la nueva y sube en el vblank que viene, junto con esta OAM.
    stz obj_tile
    lda #HERO_PRIORITY          ; por debajo de la capa que lo tapa
    ora hero_pal
    sta obj_attr
    lda pose_heroe
    cmp hero_pose_vram
    beq misma_pose
    sta hero_pose_vram
    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_VRAM_SPRITE, x
    sta vq_dest
    sep #$20
.a8
    jsr vram_encolar
    bne misma_pose
    lda #$FF
    sta hero_pose_vram          ; la cola estaba llena: el cuadro que viene
misma_pose:

    ; Un salto en curso corre el dibujo hacia atrás y lo levanta. La posición
    ; es la de RM2k, con la división **al final**: `x * 256 - dx * restante`
    ; sobre 16. Dividir el descuento por separado da un pixel de más o de menos
    ; cada vez que no es múltiplo de 16, o sea la mitad de los cuadros.
    lda ruta_salto
    sta salto_resta
    jsr alto_del_salto
    rep #$20
.a16
    lda hero_x
    sec
    sbc pantalla_x
    sec
    sbc #SPRITE_OFF_X
    sta obj_x
    lda hero_y
    sec
    sbc camara_y
    sec
    sbc #SPRITE_OFF_Y
    sec
    sbc salto_alto              ; el arco levanta el dibujo, no el orden
    sta obj_y
    sep #$20
.a8
    jsr emit_object
sin_dibujar:
    rts
.endproc

; --- un objeto en OAM ------------------------------------------------------
; Descarta lo que caiga fuera de la pantalla: la X del objeto tiene nueve bits y
; la Y sólo ocho, así que un objeto lejano daría la vuelta y aparecería del otro
; lado. Se corren los rangos 32 pixeles para poder compararlos sin signo.
; El +32 de las dos comparaciones corre el origen para que un objeto que asoma
; por arriba o por la izquierda —y que llega acá con la coordenada negativa— dé
; un número chico en vez de uno gigante, y una sola comparación sin signo
; resuelva los dos bordes.
.proc emit_object
.a8
.i16
    rep #$20
.a16
    lda obj_x
    clc
    adc #32
    cmp #(256 + 32)
    sep #$20
.a8
    bcs fuera
    rep #$20
.a16
    lda obj_y
    clc
    adc #32
    ; El borde de abajo no se descarta en 256 sino en 224, y no es lo mismo. La
    ; Y de OAM tiene 8 bits y la pantalla 224 líneas, así que los valores 224 a
    ; 255 quedan ambiguos: el PPU los lee siempre como "un poco más arriba del
    ; borde de arriba" y dibuja el objeto envuelto. Con el corte en 256, un NPC
    ; que se iba por abajo se guardaba con una Y de esa banda y reaparecía
    ; arriba, mostrando primero los pies y después entero.
    ;
    ; La ambigüedad hace falta y no se puede sacar: es la que hace que un objeto
    ; en y = -31 muestre su última línea en la línea 0. Lo que no puede pasar es
    ; que le llegue un objeto que de verdad está abajo.
    cmp #(224 + 32)
    sep #$20
.a8
    bcs fuera

    rep #$20
.a16
    lda oam_slot
    asl a
    asl a
    tax                         ; cuatro bytes por objeto
    sep #$20
.a8
    lda obj_x
    sta oam, x
    lda obj_y
    sta oam + 1, x
    lda obj_tile
    sta oam + 2, x
    lda obj_attr
    sta oam + 3, x

    ; Sus dos bits en la tabla chica: el noveno de la X y el tamaño.
    lda obj_x + 1
    and #$01
    ora obj_grande              ; 32x32 los personajes, 8x8 los dígitos
    jsr push_high
    rep #$20
.a16
    inc oam_slot
    sep #$20
.a8
fuera:
    rts
.endproc

; Mete dos bits arriba del acumulador y lo corre. Después de cuatro objetos el
; byte queda armado en el orden que la consola espera.
.proc push_high
.a8
.i16
    pha
    lda high_acc
    lsr a
    lsr a
    sta high_acc
    pla
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    ora high_acc
    sta high_acc

    lda oam_slot
    and #$03
    cmp #$03
    bne listo                   ; todavía no se completó el byte
    jsr store_high
listo:
    rts
.endproc

.proc store_high
.a8
.i16
    lda high_acc
    ldx high_ptr
    sta oam_high, x
    stz high_acc
    rep #$20
.a16
    inc high_ptr
    sep #$20
.a8
    rts
.endproc

; Al cerrar puede quedar un byte a medias. Se completa con objetos escondidos,
; que igual van a quedar con la Y fuera de pantalla.
.proc flush_high
.a8
.i16
completar:
    lda oam_slot
    and #$03
    beq listo
    lda #$02
    jsr push_high
    rep #$20
.a16
    inc oam_slot
    sep #$20
.a8
    bra completar
listo:
    rts
.endproc

