.segment "CODE"

; --- las variables ---------------------------------------------------------
;
; Viven en la RAM lejana, así que no se indexan: se apunta WMADD a la ranura y
; se lee o escribe la palabra por el puerto. Son pocas operaciones por página y
; el precio no se nota. `var_leer` devuelve en A de dieciséis bits **y deja M
; en dieciséis**; `var_escribir` toma el valor de `temp + 2`.

; A: la ranura. Deja WMADD apuntando a su palabra.
.proc var_apuntar
.a8
.i16
    rep #$20
.a16
    and #VAR_RANURA             ; el byte de la ranura, sin lo que traiga B
    asl a                       ; dos bytes por variable
    clc
    adc #FAR_VARIABLES
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    rts
.endproc

; A: la ranura. Vuelve con su valor en A de dieciséis bits, y M en dieciséis.
.proc var_leer
.a8
.i16
    jsr var_apuntar
    lda WMDATA                  ; el byte bajo
    pha
    lda WMDATA                  ; y el alto
    xba
    pla                         ; C = alto:bajo
    rep #$20
.a16
    rts
.endproc

; A: la ranura; B: el byte de banderas del opcode, con `VAR_REFRESCO` en el
; bit de arriba si esta escritura pide el refresco de páginas; `temp + 2`: el
; valor.
;
; El refresco se marca **acá y no en cada opcode** porque por acá pasan todas
; las escrituras —`op_var`, las dos ramas de `op_key`, `op_terrain` y
; `op_location`— y así el bit se mira una sola vez. Es
; `Game_Map::SetNeedRefreshForVarChange`, que tampoco marca por cualquier
; escritura: le pregunta al `map_cache` si alguna condición de página del mapa
; mira esa variable. Acá esa pregunta la contestó el conversor; ver
; VAR_REFRESCO en eventos.py.
;
; Hasta el 2026-09-27 el bit venía en la ranura, y eso topaba las variables en
; 128: ver VAR_RANURA_MAX en eventos.py.
.proc var_escribir
.a8
.i16
    xba                         ; las banderas
    and #VAR_REFRESCO
    beq sin_refresco
    lda #1
    sta refresco
sin_refresco:
    xba                         ; y la ranura de vuelta; `var_apuntar` tira B
    jsr var_apuntar
    lda temp + 2
    sta WMDATA
    lda temp + 3
    sta WMDATA
    rts
.endproc

; Enciende o apaga el switch de temp según A.
;
; **Pisa X e Y**, y quien llama desde el intérprete tiene que salvar Y, que es el
; cursor del bytecode: por eso el `phy`/`ply` de `op_switch`. Sin él el lazo de
; `correr_codigo` sigue leyendo desde el byte que quedó en Y —un desplazamiento
; de la tabla de switches— así que la página se corta en su primer comando y el
; evento no hace nada. Las dos páginas del juego que hacen algo arrancan
; prendiendo switches, así que el síntoma es "ninguna página corre" y no "esta
; página falla".
.proc poner_switch
.a8
.i16
    pha
    rep #$20
.a16
    lda temp
    and #$0007
    tax
    lda temp
    lsr a
    lsr a
    lsr a
    tay
    sep #$20
.a8
    pla
    beq apagar
    lda switches, y
    ora f:mascara, x
    sta switches, y
    lda #1
    sta refresco                ; las páginas que lo piden pueden cambiar
    rts
apagar:
    lda f:mascara, x
    eor #$FF
    and switches, y
    sta switches, y
    lda #1
    sta refresco
    rts
.endproc

; Todas en cero, la semilla del azar puesta, la velocidad del héroe en 4, el
; inventario vacío y el menú y guardar permitidos. Corre en el reset, antes de
; cargar la partida. Viven seguidos en la RAM lejana, así que es una sola
; pasada por el puerto.
.proc limpiar_variables
.a8
.i16
    rep #$20
.a16
    lda #FAR_ACCESO
    sta WMADDL
    ; Hasta el final del inventario, con el hueco que haya entre las
    ; variables y él: es una pasada en el reset y no importa.
    ldx #(FAR_ITEMS + ITEMS_N - FAR_ACCESO - 4)
    sep #$20
.a8
    stz WMADDH
    stz WMDATA                  ; guardar y el menú, permitidos
    lda #4                      ; la velocidad normal del héroe
    sta WMDATA
    lda #<AZAR_SEMILLA
    sta WMDATA
    lda #>AZAR_SEMILLA
    sta WMDATA
otra:
    stz WMDATA
    dex
    bne otra
    rts
.endproc

; El equipo inicial de todos los actores a `FAR_EQUIPO`: un DMA de la tabla
; del conversor a la ventana de la WRAM. Corre en el reset, antes de cargar
; la partida, que lo pisa.
.proc equipo_inicial_poner
.a8
.i16
    rep #$20
.a16
    lda #FAR_EQUIPO
    sta WMADDL
    lda #<(equipo_inicial)
    ora #(>(equipo_inicial) * 256)
    sta A1T0L
    lda #(ACTORES_N * 10)
    sta DAS0L
    sep #$20
.a8
    stz WMADDH
    lda #^(equipo_inicial)
    sta A1B0
    stz DMAP0                   ; de A a B, de a un byte
    lda #$80                    ; WMDATA
    sta BBAD0
    lda #$01
    sta MDMAEN
    rts
.endproc


; La velocidad del héroe, en A. Sólo A: quien la pide está en medio de un paso
; con X e Y ocupados.
.proc hero_vel_leer
.a8
.i16
    rep #$20
.a16
    lda #FAR_HERO_VEL
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    rts
.endproc

; A: la velocidad nueva.
.proc hero_vel_escribir
.a8
.i16
    pha
    rep #$20
.a16
    lda #FAR_HERO_VEL
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    pla
    sta WMDATA
    rts
.endproc

; Cuántos cuadros dura cada frame de la caminata a la velocidad del héroe:
; `anim_por_vel`, que es `GetStationaryAnimFrames`. Con la velocidad 4
; son los seis de siempre.
.proc anim_cuadros_del_heroe
.a8
.i16
    jsr hero_vel_leer
    rep #$20
.a16
    and #$00FF
    dec a
    tax
    sep #$20
.a8
    lda anim_por_vel, x
    rts
.endproc

; La comparación con signo de `ConditionalBranch` y de la condición de página
; por variable —RM2k usa `CheckOperator` para las dos—. A trae el valor de la
; variable en dieciséis bits, `temp + 2` contra qué se compara y `temp + 1` el
; código: ==, >=, <=, >, <, != en ese orden. Vuelve en ocho bits con A = 1 y
; Z=0 si se cumple, A = 0 y Z=1 si no. Pisa `temp + 1` a `temp + 3`.
.proc comparar_var
.a16
.i16
    sec
    sbc temp + 2                ; N, V y Z de la resta con signo
    sep #$20
.a8
    php
    pla                         ; A = las banderas: N $80, V $40, Z $02
    pha
    and #$C0
    beq no_menor                ; N y V en cero: no es menor
    cmp #$C0
    beq no_menor                ; los dos puestos: tampoco
    lda #1
    bra menor_listo
no_menor:
    lda #0
menor_listo:
    sta temp + 2                ; menor
    pla
    and #$02
    beq no_igual
    lda #1
no_igual:
    sta temp + 3                ; igual
    lda temp + 1                ; la comparación
    beq igual
    cmp #1
    beq mayor_igual
    cmp #2
    beq menor_igual
    cmp #3
    beq mayor
    cmp #4
    beq menor
    lda temp + 3                ; !=
    eor #1
    rts
igual:
    lda temp + 3
    rts
mayor_igual:
    lda temp + 2
    eor #1
    rts
menor_igual:
    lda temp + 2
    ora temp + 3
    rts
mayor:
    lda temp + 2
    ora temp + 3
    eor #1
    rts
menor:
    lda temp + 2
    rts
.endproc

; El paso del xorshift: x ^= x << 7; x ^= x >> 9; x ^= x << 8. Vuelve con el
; valor nuevo en A de dieciséis bits, y M en dieciséis. Es `azar_siguiente` de
; eventos.py, instrucción por instrucción. Usa `temp + 2` de escritorio: quien
; lo llama —`op_var`— todavía no lo cargó.
.proc azar_siguiente
.a8
.i16
    rep #$20
.a16
    lda #FAR_AZAR
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda WMDATA
    pha
    lda WMDATA
    xba
    pla                         ; C = x
    rep #$20
.a16
    sta temp + 2
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor temp + 2
    sta temp + 2
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    lsr a
    eor temp + 2
    sta temp + 2
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    asl a
    eor temp + 2
    sta temp + 2
    lda #FAR_AZAR
    sta WMADDL
    sep #$20
.a8
    stz WMADDH
    lda temp + 2
    sta WMDATA
    lda temp + 3
    sta WMDATA
    rep #$20
.a16
    lda temp + 2
    rts
.endproc
.a8
.i16



; Compone la ventana de la opción marcada. El cuadro sale de la tabla, en
; `eleg_tabla + eleg_sel * 4`; el destino está dos bytes más allá y lo lee
; `eleccion_tick`.
;
; Volver a llamar a `msg_empezar` con la ventana ya abierta es lo que mueve el
; cursor: `msg_abierto` no se apaga, así que la ventana no parpadea, y el
; compositor va pisando renglón por renglón lo que había. Un renglón de una
; opción son cinco o seis caracteres, o sea un par de cuadros: se ve como un
; cursor que se mueve, no como una ventana que se rehace.
.proc eleg_abrir
.a8
.i16
    lda eleg_sel
    asl
    asl                         ; cuatro bytes por opción
    rep #$20
.a16
    and #$00FF
    clc
    adc eleg_tabla
    tay
    lda [cod_ptr], y            ; el desplazamiento del cuadro, de 16 bits
    jsr msg_empezar             ; que lo espera en A y en modo 16
    sep #$20
.a8
    rts
.endproc

; Un cuadro de una elección abierta. Devuelve A distinto de cero cuando el
; jugador eligió, y ahí la página ya tiene el cursor puesto en el cuerpo de la
; opción y sigue en este mismo cuadro.
;
; El movimiento del cursor es `Window_Selectable::Update` con `column_max` en
; uno: arriba y abajo dan la vuelta, y valen por **flanco** y no por estado, que
; es el `Input::IsTriggered` de allá. Sostener abajo no baja de a un renglón por
; cuadro.
;
; Lo cubre `pruebas/rpgmaker/test_elegir.py`, que puede apretar cualquier
; botón.
.proc eleccion_tick
.a8
.i16
    lda msg_abierto
    bne abierta
    lda #0                      ; todavía se está componiendo: nadie elige
    rts
abierta:
    lda pad
    eor pad_ant
    and pad                     ; lo que se apretó **en este cuadro**
    sta eleg_flancos
    and #PAD_UP
    beq no_arriba
    lda eleg_sel
    bne sube_una
    lda eleg_n                  ; desde la primera, arriba da la vuelta
sube_una:
    dec a
    sta eleg_sel
    jsr eleg_abrir
    lda #0
    rts
no_arriba:
    lda eleg_flancos
    and #PAD_DOWN
    beq no_abajo
    lda eleg_sel
    inc a
    cmp eleg_n
    bcc baja_una
    lda #0                      ; y desde la última, abajo también
baja_una:
    sta eleg_sel
    jsr eleg_abrir
    lda #0
    rts
no_abajo:
    lda eleg_flancos
    and #PAD_B
    beq mira_a
    lda eleg_cancel
    beq mira_a                  ; esta elección no se deja cancelar
    dec a                       ; `choice_result = cancel_type - 1`
    sta eleg_sel
    ; Y el B se consume acá: en RM2k la ventana procesa la tecla **después**
    ; del héroe, que la vio con el mensaje abierto y no pidió el menú. Acá la
    ; elección corre antes que `pedir_menu`, así que se le borra el flanco.
    lda pad_ant
    ora #PAD_B
    sta pad_ant
    bra elige
mira_a:
    lda pad_a
    beq nada
    lda pad_a_ant
    bne nada                    ; ya lo tenía apretado: no es un flanco
elige:
    lda eleg_sel
    asl
    asl
    rep #$20
.a16
    and #$00FF
    clc
    adc eleg_tabla
    inc a
    inc a                       ; el destino va después del cuadro
    tay
    lda [cod_ptr], y
    sta ev_cur
    sep #$20
.a8
    stz eleg_activo
    stz msg_abierto             ; y con eso `flush_video` apaga el HDMA
    lda #1
    rts
nada:
    lda #0
    rts
.endproc

