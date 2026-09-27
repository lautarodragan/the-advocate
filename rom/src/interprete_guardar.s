.segment "CODE"
.a8
.i16

; --- el intérprete: guardar y los permisos ---------------------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.

; `OpenSaveMenu`: la pantalla de ranuras en modo guardar, y la partida a la
; que el jugador elija. Sin operandos. Ver `OP_SAVE` en tools/port/eventos.py.
;
; **Bloquea adentro del intérprete y no cuesta ningún tick**, que es lo que hace
; RM2k: `OpenSaveMenu` apila `Scene_Save`, el mapa deja de actualizarse hasta
; que se cierra, y la página sigue por el comando siguiente. Acá
; `ranuras_pantalla` corre su propio lazo de cuadros —como desde el título— y
; `vueltas` no avanza mientras se ve, así que los dos intérpretes siguen en el
; mismo tick cuando vuelve. Cancelar con B vuelve al mapa sin guardar, que es
; también lo de RM2k; elegir guarda y vuelve, sin preguntar si la ranura estaba
; ocupada, porque `Scene_Save::Action` tampoco pregunta.
;
; La pantalla pisó la VRAM de los tiles y la paleta 0, y `volver_al_mapa` los
; repone. El estado del juego no se toca: la tabla de eventos, las rutas, la
; OAM y las poses en VRAM siguen como estaban, y por eso no se llama a
; `cargar_mapa`, que reiniciaría todo eso.
;
; Hasta el 2026-09-10 esto guardaba en la ranura cargada —o en la primera— sin
; mostrar nada, y el intento de abrir la pantalla dio "negro con basura": la
; ROM de prueba no llevaba título, y sin título el conversor emitía la pantalla
; de ranuras como un byte de relleno con `RANURA_TILES` en cero. Hoy va en toda
; ROM.
.proc op_save
    phy
    lda #1                      ; modo guardar
    jsr ranuras_pantalla
    cmp #$FF
    beq cancelado
    jsr poner_ranura
    jsr guardar_partida
cancelado:
    jsr volver_al_mapa
    ply
    jmp correr_codigo::otro

.endproc

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

