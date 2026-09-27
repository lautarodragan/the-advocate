.segment "CODE"

; --- el menú de pausa --------------------------------------------------------
;
; `Scene_Menu`, sobre el banco de la pantalla de ranuras: la geometría y los
; bloques salen de `titulo.py`, y `render_menu` es la referencia. Se abre con
; B, cuando el héroe está quieto: `pedir_menu` anota el pedido y `move_hero`
; lo atiende, que es como lo hace RM2k con `menu_calling`. El reloj del juego
; no corre mientras se ve —como en la pantalla de ranuras— así que el menú no
; cuesta ningún tick.
;
; Hoy hacen algo usar ítems —la pantalla de ítems, en `items.s`— y guardar, que
; abre la pantalla de ranuras y vuelve al menú. Las otras tres se dibujan en
; gris y A no hace nada con ellas.

; El byte de permisos, en A. Sólo A, y las banderas del `lda`: el bit 7 queda
; en N.
.proc acceso_leer
.a8
.i16
    rep #$20
.a16
    lda #FAR_ACCESO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; --- el sprite que un `ChangeSpriteAssociation` le puso a un actor -----------
;
; Un byte por número de actor en `FAR_ACTOR_GRAF`, con el índice en la tabla de
; gráficos del mapa o `ACTOR_GRAF_NINGUNO`. Vive lejos, así que se apunta WMADD
; y se pasa por el puerto, como las variables.

; A: el actor. Deja WMADD apuntando a su byte.
.proc actor_graf_apuntar
.a8
.i16
    rep #$20
.a16
    and #$00FF
    clc
    adc #FAR_ACTOR_GRAF
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; A: el actor. Vuelve con su gráfico en A, o `ACTOR_GRAF_NINGUNO`.
.proc actor_graf_leer
.a8
.i16
    jsr actor_graf_apuntar
    lda WMDATA
    rts
.endproc

; A: el actor; `temp + 1`: el gráfico.
.proc actor_graf_escribir
.a8
.i16
    jsr actor_graf_apuntar
    lda temp + 1
    sta WMDATA
    rts
.endproc

; Ningún actor con el sprite cambiado. Corre en el reset, antes de cargar la
; partida, que lo pisa.
.proc actor_graf_limpiar
.a8
.i16
    rep #$20
.a16
    lda #FAR_ACTOR_GRAF
    sta WMADDL
    ldx #ACTORES_N
    sep #$20
.a8
    stz WMADDH
    lda #ACTOR_GRAF_NINGUNO
otro:
    sta WMDATA
    dex
    bne otro
    rts
.endproc

; El valor que `KeyInputProc` le guarda a la variable, en A, o 0 si todavía no
; hay tecla. `temp + 1` trae las banderas.
;
; **Las tres cosas**: cancelar, la tecla de acción y la cruceta. Por flanco en
; la forma que espera y por lo apretado en la que no —ver más abajo—. El orden es el de `CheckInput` —de mayor valor a menor, que es lo
; que dice "RPG processes keys from highest variable value to lowest"— y es el
; mismo que corre `eventos.tecla_de` del lado del modelo; los números salen del
; conversor y no están escritos acá dos veces.
;
; Hasta el 2026-09-13 esto miraba sólo la tecla de acción, y lo que lo tenía
; cortado no era la ROM sino el arnés: la tanda sostenía una dirección desde el
; arranque, así que un flanco de cruceta no lo podía producir ningún caso.
; Ahora lo produce `--tocar`, y lo cobra el caso `tecla-dir` de la tanda.
;
; El flanco es `Input::IsTriggered`: `pad` contra `pad_ant` para B y las
; direcciones, `pad_a` contra `pad_a_ant` para A —A vive en el otro byte del
; control—, que es lo mismo con lo que se cierra un mensaje.
;
; `temp + 3` es el único de los cuatro que está libre acá: `temp` trae la
; ranura y `temp + 1` las banderas, y `op_key` guarda la respuesta en
; `temp + 2` **después** de volver de acá.
.proc tecla_valor
.a8
.i16
    ; La forma que no espera mira lo **apretado** y no el flanco: es el `wait
    ; ? IsTriggered : IsPressed` de `KeyInputState::CheckInput`, easyrpg
    ; `game_interpreter.cpp:3222`. Es el volante de la carrera, que se sostiene:
    ; por flanco, el auto cambiaba de carril una sola vez por apretada.
    ;
    ; El acarreo lleva la bandera de espera **hasta la tecla de acción**, sin
    ; guardarla: ningún `lda`, `and`, `eor` ni `sta` del medio lo toca. Guardada
    ; en `temp + 2` costaba cuatro bytes más de banco 0.
    .assert TECLA_ESPERA = $01, error, "tecla_valor la saca con un lsr"
    lda temp + 1
    lsr a                       ; TECLA_ESPERA es el bit 0: al acarreo
    lda pad
    bcc joy_listo               ; sin espera: lo apretado, tal cual
    eor pad_ant
    and pad
joy_listo:
    sta temp + 3                ; JOY1H: B y las cuatro flechas
    lda temp + 1
    and #TECLA_CANCELAR
    beq sin_cancelar
    lda temp + 3
    and #PAD_B
    beq sin_cancelar
    lda #TECLA_VALOR_CANCELAR
    rts
sin_cancelar:
    lda temp + 1
    and #TECLA_DECISION
    beq sin_decision
    lda pad_a
    bcc a_lista                 ; el acarreo de arriba, todavía entero
    eor pad_a_ant
    and pad_a
a_lista:
    beq sin_decision
    lda #TECLA_VALOR_DECISION
    rts
sin_decision:
    lda temp + 1
    and #TECLA_DIRS
    beq ninguna
    ; Las cuatro, en el orden de `CheckInput`, por tabla: escritas a mano son
    ; cuatro `bit`/`bne` más cuatro `lda`/`rts`, y el banco 0 no los tiene.
    ; La tabla termina en cero, que no es ningún botón.
    ldx #$0000
dir_otra:
    lda f:tecla_dir_bit, x
    beq ninguna
    and temp + 3
    bne dir_hay
    inx
    bra dir_otra
dir_hay:
    lda f:tecla_dir_val, x
    rts
ninguna:
    lda #0
    rts
.endproc

; A: el byte de permisos nuevo.
.proc acceso_escribir
.a8
.i16
    pha
    rep #$20
.a16
    lda #FAR_ACCESO
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    rts
.endproc

; Se tira el pedido de menú, si había. Sólo A.
.proc menu_olvidar
.a8
.i16
    jsr acceso_leer
    bpl listo
    and #$7F
    jsr acceso_escribir
listo:
    rts
.endproc

; B recién apretado pide el menú, si está permitido, no hay mensaje y no hay
; página corriendo: es el final de `Game_Player::Update`. Corre después de
; `move_hero`, así que el menú se abre en el cuadro que viene —o cuando
; termine el paso, si se estaba caminando—.
.proc pedir_menu
.a8
.i16
    lda pad
    eor pad_ant
    and pad
    and #PAD_B
    beq listo
    lda msg_abierto
    bne listo
    lda ev_activo
    bne listo
    jsr acceso_leer
    bit #ACCESO_SIN_MENU
    bne listo
    ora #ACCESO_PEDIDO
    jsr acceso_escribir
listo:
    rts
.endproc

; ¿La orden A hace algo? Vuelve con A = 1 y Z=0 si sí. Se lleva X.
.proc menu_habilitada
.a8
.i16
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda menu_hecha, x
    beq listo
    cpx #MENU_GUARDAR
    bne listo
    jsr acceso_leer
    and #ACCESO_SIN_GUARDAR
    eor #ACCESO_SIN_GUARDAR     ; 1 si está permitido
listo:
    rts
.endproc

; El cursor en la orden A: `temp + 3` en 1 lo pinta y en 0 lo borra. Son dos
; celdas, una abajo de la otra, escritas de a una palabra. Con la pantalla
; apagada o adentro del vblank.
.proc menu_cursor_escribir
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda menu_cursor_vram, x
    tay
    sep #$20
.a8
    lda #$80
    sta VMAIN
    sty VMADDL
    lda temp + 3
    rep #$20
.a16
    beq borra
    lda menu_cursor_celdas
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda menu_cursor_celdas + 2
    sta VMDATAL
    sep #$20
.a8
    rts
.a16
borra:
    stz VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    stz VMDATAL
    sep #$20
.a8
    rts
.endproc

; El oro, alineado a la derecha contra la moneda: se divide por diez de a un
; byte —el divisor del hardware es de 16 por 8, y con el resto de arrastre el
; dividendo nunca pasa de 2559— y cada resto es una cifra, de derecha a
; izquierda. El cero se escribe "0".
.proc menu_oro_escribir
.a8
.i16
    rep #$20
.a16
    lda oro
    sta temp
    sep #$20
.a8
    lda oro + 2
    sta temp + 2
    lda #$80
    sta VMAIN
    ldy #(MENU_MONEDA_VRAM - 1)
cifra:
    stz temp + 3                ; el resto que se arrastra
    ldx #2
dividir:
    lda temp, x
    sta WRDIVL
    lda temp + 3
    sta WRDIVH
    lda #10
    sta WRDIVB                  ; arranca: el cociente tarda dieciséis ciclos
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    nop
    lda RDDIVL
    sta temp, x
    lda RDMPYL                  ; el resto
    sta temp + 3
    dex
    bpl dividir
    rep #$20
.a16
    sty VMADDL
    lda temp + 3
    and #$00FF
    asl a
    asl a
    tax
    lda f:ranura_glifo_celdas + GLIFO_CIFRA_0, x
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda f:ranura_glifo_celdas + GLIFO_CIFRA_0 + 2, x
    sta VMDATAL
    dey
    lda temp                    ; ¿queda algo?
    bne otra
    sep #$20
.a8
    lda temp + 2
    bne cifra
    rts
.a16
otra:
    sep #$20
.a8
    bra cifra
.endproc

; La pantalla entera, con la pantalla apagada: el banco, las cinco órdenes, el
; cursor en `titulo_sel`, el oro y el grupo. Al final la prende.
.proc menu_subir
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsr ranura_banco_subir

    ; --- las órdenes, cada una en su variante ---
    lda #0
otra_opcion:
    pha
    jsr menu_habilitada
    eor #1
    sta temp + 3                ; 1 si va en gris
    pla
    pha
    asl a
    ora temp + 3
    clc
    adc #MENU_BLQ_OPCION
    sta temp + 3                ; el bloque
    pla
    pha
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda menu_opcion_vram, x
    tay
    lda temp + 3
    and #$00FF
    tax
    lda #(MENU_OPC_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #2
    sta temp + 2
    jsr ranura_rect_subir
    pla
    inc a
    cmp #MENU_OPCIONES
    bcc otra_opcion

    ; --- el cursor ---
    lda #1
    sta temp + 3
    lda titulo_sel
    jsr menu_cursor_escribir

    ; --- el oro y la moneda ---
    jsr menu_oro_escribir
    rep #$20
.a16
    ldx #MENU_BLQ_MONEDA
    ldy #MENU_MONEDA_VRAM
    lda #(MENU_MONEDA_COLS * 2)
    sta temp
    sep #$20
.a8
    lda #2
    sta temp + 2
    jsr ranura_rect_subir

    jsr menu_grupo_pintar
    jsr ranura_ppu_prender
    lda #1
    sta menu_abierto
    rts
.endproc

; El grupo, de a una fila por actor: el bloque fijo de la fila, la cara, y
; encima el nombre, el nivel, los HP de ahora y el máximo. Lo comparten el
; menú y la elección de actor.
;
; **El bloque es uno solo para las cuatro filas y para todos los actores**:
; lleva el término del nivel, el estado y el de los HP, que no dependen de
; nadie. Lo que sí depende del actor —su nombre, su nivel y su máximo— se
; compone con glifos, y eso es lo que hace que el banco de tiles no crezca
; con la cantidad de actores; ver `ranura_texto_escribir`.
;
; La fila se queda en la pila toda la vuelta y cada paso vuelve a sacar de
; ella la celda y el actor en vez de guardarlos: la página directa está llena
; —`temp` y `temp + 2` los usan las dos rutinas que escriben— y cada paso
; corre una vez por fila, con el PPU apagado.
.proc menu_grupo_pintar
.a8
.i16
    lda #0
otro_miembro:
    cmp grupo_n
    bcs grupo_listo
    cmp #MENU_FILAS_GRUPO
    bcc entra
grupo_listo:
    rts
entra:
    pha                         ; la fila, hasta el final de la vuelta
    jsr actor_de
    cmp #MENU_ACTORES_N
    bcc conocido
    jmp siguiente               ; uno que esta ROM no conoce
conocido:

    ; --- el bloque fijo de la fila ---
    pla
    pha
    jsr fila_vram
    lda #(MENU_ACTOR_COLS * 2)
    sta temp
    lda #MENU_ACTOR_FILAS
    sta temp + 2
    ldx #MENU_BLQ_FILA
    jsr ranura_rect_subir

    ; --- la cara, en la esquina de arriba a la izquierda de la fila ---
    pla
    pha
    jsr fila_vram
    pla
    pha
    jsr actor_de
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ranura_cara_bloque, x
    cmp #$FF
    beq sin_cara
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda #(MENU_CARA_CELDAS * 2)
    sta temp
    lda #MENU_CARA_CELDAS
    sta temp + 2
    jsr ranura_rect_subir
sin_cara:

    ; --- el nombre ---
    pla
    pha
    jsr fila_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_NOMBRE_DESPL
    tay
    sep #$20
.a8
    pla
    pha
    jsr actor_de
    ldx #RANURA_TEXTO_NOMBRE
    jsr ranura_texto_de
    lda #MENU_NOMBRE_COLS
    jsr ranura_texto_escribir

    ; --- el nivel ---
    pla
    pha
    jsr fila_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_NIVEL_DESPL
    tay
    sep #$20
.a8
    pla
    pha
    jsr actor_de
    jsl f:texto_nivel           ; el de ahora: sube peleando
    lda #RANURA_NIVEL_CIFRAS
    jsr ranura_texto_escribir

    ; --- el máximo, detrás de la barra ---
    pla
    pha
    jsr fila_vram
    rep #$20
.a16
    tya
    clc
    adc #MENU_MAX_DESPL
    tay
    sep #$20
.a8
    pla
    pha
    jsr actor_de
    jsl f:texto_maximo          ; el de su nivel de ahora, como el nivel
    lda #MENU_MAX_CIFRAS
    jsr ranura_texto_escribir

    ; --- y los HP de ahora, que no son texto del cartucho sino estado ---
    pla
    pha
    sta temp + 2                ; la fila
    jsr actor_de
    sta temp                    ; el actor
    jsl f:menu_hp_escribir
siguiente:
    pla
    inc a
    jmp otro_miembro

; El actor de la fila que trae A, y la celda donde arranca esa fila en el
; tilemap. Las dos se vuelven a preguntar en cada paso; ver el comentario de
; arriba.
actor_de:
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    rts

fila_vram:
    rep #$20
.a16
    and #$00FF
    asl a                       ; dos bytes por entrada
    tax
    lda menu_fila_vram, x
    tay
    sep #$20
.a8
    rts
.endproc

; El menú, hasta que el jugador lo cierra con B. Vuelve al mapa repuesto,
; como la pantalla de ranuras desde el save point.
.proc menu_pantalla
.a8
.i16
    phb
    phk
    plb
    sep #$20
    rep #$10
    stz titulo_sel              ; RM2k abre con el cursor en la primera
armar:
    jsr menu_subir
espera:
    jsr wait_vblank
    jsr read_pad
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    bne sube
    lda #MENU_OPCIONES          ; desde la primera, arriba da la vuelta
sube:
    dec a
    jsr mover
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp #MENU_OPCIONES
    bcc baja
    lda #0
baja:
    jsr mover
    bra espera
no_abajo:
    lda titulo_flancos
    and #PAD_B
    bne cerrar
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; ya lo tenía apretado: no es un flanco
    lda titulo_sel
    jsr menu_habilitada
    beq espera                  ; en gris: RM2k suena y no hace nada
    lda titulo_sel
    cmp #2
    bne no_equipo
    ; El equipo: a quién, y su pantalla. Las dos vuelven al menú.
    lda #1
    sta eleg_cancel             ; para elegir
    jsr objetivo_pantalla
    cmp #$FF
    beq volver_de_equipo
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    jsl f:equipo_pantalla
volver_de_equipo:
    lda #2
    sta titulo_sel
    jmp armar
no_equipo:
    lda titulo_sel
    bne no_items
    ; Los ítems: B vuelve al menú, y usar uno vuelve derecho al mapa.
    jsr items_pantalla
    beq volver_de_items
    jmp cerrar
volver_de_items:
    stz titulo_sel
    jmp armar
no_items:
    ; Guardar: la pantalla de ranuras y, elija
    ; o cancele, de vuelta al menú con el cursor en "Save", como `Scene_Save`
    ; cuando vuelve a `Scene_Menu`.
    lda #1
    jsr ranuras_pantalla
    cmp #$FF
    beq guardar_listo
    jsr poner_ranura
    jsr guardar_partida
guardar_listo:
    lda #MENU_GUARDAR
    sta titulo_sel
    jmp armar
cerrar:
    ; El B que cierra y el A de antes quedan consumidos: sin esto `pedir_menu`
    ; vería el flanco en esta misma vuelta y el menú se volvería a abrir.
    lda pad
    sta pad_ant
    lda pad_a
    sta pad_a_ant
    stz menu_abierto
    lda boot_cuadros
    sta nmi_visto
    ; El equipo pudo cambiar: los eventos comunes que sólo lo miran corren
    ; ahora, con el banco de datos todavía en el 0. Ver `COMUNES_DEL_EQUIPO`
    ; en eventos.py.
    jsl f:comunes_del_equipo
    plb
    jsr volver_al_mapa
    rts

; El cursor a la orden que trae A: se borra de donde estaba y se pinta ahí.
mover:
    pha
    stz temp + 3
    lda titulo_sel
    jsr menu_cursor_escribir
    pla
    sta titulo_sel
    lda #1
    sta temp + 3
    lda titulo_sel
    jmp menu_cursor_escribir
.endproc

; --- la elección de actor ----------------------------------------------------
;
; `Scene_ActorTarget`, sobre el banco del menú: el panel del grupo y un cursor
; al costado de la fila marcada. `eleg_cancel` dice para qué: en 1, para elegir
; a quién equipar, y A vuelve con la fila; en 0, para la medicina de `k` en
; `eleg_flancos`, y A la usa sobre la fila —`medicina_usar`— y **se queda**,
; con los HP de esa fila repintados, que es lo que hace `UpdateItem`. B vuelve
; con $FF. `render_objetivo` en titulo.py es la referencia.
;
; Hasta el 2026-09-21 A no hacía nada con una medicina: estaba escrito cuando
; fuera de la pelea nadie podía tener los HP por debajo del máximo, y siguió
; así cuando las peleas los bajaron. Es el "el sándwich no cura desde el menú"
; de taro.

; El cursor en la fila A del grupo: `temp + 3` en 1 lo pinta y en 0 lo borra.
.proc objetivo_cursor_escribir
.a8
.i16
    rep #$20
.a16
    and #$00FF
    asl a
    tax
    lda menu_fila_vram, x
    clc
    adc #OBJETIVO_CURSOR_DESPL
    tay
    sep #$20
.a8
    lda #$80
    sta VMAIN
    sty VMADDL
    lda temp + 3
    rep #$20
.a16
    beq borra
    lda menu_cursor_celdas
    sta VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    lda menu_cursor_celdas + 2
    sta VMDATAL
    sep #$20
.a8
    rts
.a16
borra:
    stz VMDATAL
    tya
    clc
    adc #32
    sta VMADDL
    stz VMDATAL
    sep #$20
.a8
    rts
.endproc

.proc objetivo_pantalla
.a8
.i16
    lda #$80
    sta INIDISP
    stz HDMAEN
    stz TM
    jsr ranura_banco_subir
    jsr menu_grupo_pintar
    stz titulo_sel
    lda #1
    sta temp + 3
    lda #0
    jsr objetivo_cursor_escribir
    jsr ranura_ppu_prender
espera:
    jsr wait_vblank
    jsr read_pad
    lda pad
    eor pad_ant
    and pad
    sta titulo_flancos
    and #PAD_UP
    beq no_arriba
    lda titulo_sel
    beq espera
    dec a
    jsr mover
    bra espera
no_arriba:
    lda titulo_flancos
    and #PAD_DOWN
    beq no_abajo
    lda titulo_sel
    inc a
    cmp grupo_n
    bcs espera
    cmp #MENU_FILAS_GRUPO
    bcs espera
    jsr mover
    bra espera
no_abajo:
    lda titulo_flancos
    and #PAD_B
    beq mira_a
    lda #$FF                    ; B: sin elegir
    rts
mira_a:
    lda pad_a
    beq espera
    lda pad_a_ant
    bne espera                  ; ya lo tenía apretado: no es un flanco
    lda eleg_cancel
    beq medicina
    lda titulo_sel              ; eligiendo: la fila elegida
    rts
medicina:
    jsr actor_de_la_fila
    jsl f:medicina_usar
    beq espera                  ; no sirvió: RM2k suena y no hace nada
    ; Los HP de la fila, en el vblank que viene: el uso se llevó el de ahora.
    jsr wait_vblank
    jsr actor_de_la_fila
    sta temp
    lda titulo_sel
    sta temp + 2
    jsl f:menu_hp_escribir
    jmp espera

actor_de_la_fila:
    rep #$20
.a16
    lda titulo_sel
    and #$00FF
    tax
    sep #$20
.a8
    lda grupo, x
    rts

mover:
    pha
    stz temp + 3
    lda titulo_sel
    jsr objetivo_cursor_escribir
    pla
    sta titulo_sel
    lda #1
    sta temp + 3
    lda titulo_sel
    jmp objetivo_cursor_escribir
.endproc

