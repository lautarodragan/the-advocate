; `OpenSaveMenu`: la pantalla de ranuras en modo guardar, y la partida a la
; que el jugador elija. Sin operandos. La referencia hace lo mismo con el mismo
; opcode: ver `OP_SAVE` en tools/port/eventos.py.
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

