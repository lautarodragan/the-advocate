.segment "CODE"
.a8
.i16

; --- el intérprete: permisos, saltos y switches ----------------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.

; `ChangeSaveAccess`, `ChangeMainMenuAccess` y `ChangeEscapeAccess`: **el bit**
; del permiso y si queda permitido. Prende o apaga ese bit de "prohibido" de
; `FAR_ACCESO`.
;
; El bit lo pone el conversor y acá no se calcula, y eso es lo que deja agregar
; permisos sin tocar este opcode: antes el operando era el número del permiso y
; el bit salía de un `inc a`, que da $01 y $02 para los dos primeros y **$03
; para el tercero**, o sea prohibir las otras dos cosas de una.
.proc op_access
.a8
.i16
    lda [cod_ptr], y            ; el bit: $01 guardar, $02 el menú, $04 escapar
    sta temp
    iny
    lda [cod_ptr], y            ; permitido
    iny
    sta temp + 1
    phy
    ; El permiso se mira con A de ocho bits y no con Y: con los índices en
    ; dieciséis, `ldy temp + 1` se llevaba también `temp + 2`, y un permiso
    ; en cero con basura al lado quedaba permitido.
    jsr acceso_leer
    xba                         ; B = los permisos, mientras se mira
    lda temp + 1
    beq acceso_prohibir
    lda temp
    eor #$FF
    sta temp
    xba
    and temp
    bra acceso_listo
acceso_prohibir:
    xba
    ora temp
acceso_listo:
    jsr acceso_escribir
    ply
    jmp correr_codigo::otro

.endproc

.proc op_switch
    rep #$20
.a16
    lda [cod_ptr], y            ; el número, de 16 bits
    sta temp
    sep #$20
.a8
    iny
    iny
    lda [cod_ptr], y            ; y si va encendido o apagado
    iny
    phy
    jsr poner_switch
    ply
    jmp correr_codigo::otro     ; `bra` no llega: el lazo quedó lejos

.endproc

