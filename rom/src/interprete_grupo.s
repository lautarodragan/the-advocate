.proc op_party
    lda [cod_ptr], y            ; 0 = agregar, 1 = sacar
    sta temp
    iny
    lda [cod_ptr], y            ; el actor
    iny
    phy
    jsr cambiar_grupo
    ply
    jmp correr_codigo::otro     ; `bra` no llega: el lazo quedó lejos

.endproc

; `ChangeSpriteAssociation`: el actor y el índice del gráfico en la tabla del
; mapa, la misma que resuelve la orden 34 de una ruta. Ver OP_ACTOR_SPRITE en
; eventos.py.
;
; El `ResetGraphic()` que RM2k le hace al `Game_Player` es el `jsr
; elegir_grafico_heroe` de acá abajo, y va sólo si el que cambió es el que
; lidera: el que no lidera no se dibuja, y lo guardado lo va a leer
; `elegir_grafico_heroe` cuando le toque —al cambiar el grupo o al cargar otro
; mapa—.
;
; `aplicar_tinte` detrás por lo mismo que en `cambiar_grupo`: la fila de CGRAM
; que el líder tenía prestada queda con sus quince colores encima de los del
; mapa, y hay que reponerla desde el cartucho.
.proc op_actor_sprite
.a8
.i16
    lda [cod_ptr], y            ; el actor
    iny
    sta temp
    lda [cod_ptr], y            ; el gráfico
    iny
    sta temp + 1
    phy
    lda temp
    jsr actor_graf_escribir
    lda temp
    cmp grupo                   ; ¿es el líder?
    bne graf_no_lidera
    jsr elegir_grafico_heroe
    jsr aplicar_tinte
graf_no_lidera:
    ply
    jmp correr_codigo::otro

.endproc

; `FullHeal` y `ChangeHP` que suma. Acá está sólo la entrada: el cuerpo es
; `curar`, fuera del banco 0, y lee sus operandos y avanza el cursor él mismo,
; con Y en la mano.
.proc op_heal
    jsl f:curar
    jmp correr_codigo::otro

.endproc

; `ChangeEquipment` y `ChangeSkills`: como `op_heal`, sólo la entrada. Los
; cuerpos son `equipo_quitar` y `habilidad_cambiar`, fuera del banco 0.
.proc op_equipment
    jsl f:equipo_quitar
    jmp correr_codigo::otro

.endproc

.proc op_skill
    jsl f:habilidad_cambiar
    jmp correr_codigo::otro

.endproc

