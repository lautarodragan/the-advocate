.segment "CODE"

; ¿Está el actor de A en el grupo? Vuelve con Z=0 si sí.
.proc en_el_grupo
.a8
.i16
    ldx #$0000
busca:
    cpx grupo_n                 ; grupo_n es de 16 bits a propósito: con .i16
    beq no_esta                 ; esta comparación lee dos bytes igual
    cmp grupo, x
    beq esta
    inx
    bra busca
esta:
    lda #1                      ; Z=0
    rts
no_esta:
    lda #0                      ; Z=1
    rts
.endproc

; Agrega o saca un actor del grupo y recalcula con qué se dibuja el héroe.
; A = el actor, temp = 0 para agregar y 1 para sacar.
;
; Las reglas son las de `Game_Party::AddActor` y `RemoveActor`: agregar a
; alguien que ya está no lo duplica ni lo mueve de lugar, agregar con el grupo
; lleno no hace nada, y sacar a alguien que no está tampoco. El orden importa
; porque el primero es el que se dibuja.
.proc cambiar_grupo
.a8
.i16
    ldx #$0000
buscar:
    cpx grupo_n
    beq no_estaba
    cmp grupo, x
    beq estaba
    inx
    bra buscar

estaba:
    ; `temp` se mira con A y no con `ldy temp`: con .i16 eso leería dos bytes y
    ; el de al lado no es nuestro. Es la trampa del ancho de los índices, que ya
    ; está anotada arriba de main.s, y acá dio exactamente el síntoma que
    ; promete: ningún cambio de grupo tenía efecto y no había ningún error.
    pha
    lda temp
    beq era_agregar             ; agregar uno que ya está: nada que hacer
    pla
    ; Sacarlo: se corren los de atrás un lugar.
correr:
    inx
    cpx grupo_n
    beq acortar
    lda grupo, x
    sta grupo - 1, x
    bra correr
acortar:
    rep #$20
.a16
    dec grupo_n
    sep #$20
.a8
    bra listo
era_agregar:
    pla
    bra listo

no_estaba:
    pha
    lda temp
    bne era_sacar               ; sacar uno que no está: nada que hacer
    pla
    cpx #GRUPO_MAX
    beq listo                   ; lleno: RM2k tampoco lo agrega
    sta grupo, x
    rep #$20
.a16
    inc grupo_n
    sep #$20
.a8
    bra listo
era_sacar:
    pla

listo:
    jsr elegir_grafico_heroe
    ; El líder nuevo tiene otros colores y comparte la ranura con el anterior,
    ; así que hay que rearmar las paletas. No toca CGRAM: deja todo en
    ; `cgram_sombra` y lo sube `subir_tinte` en el vblank.
    jsr aplicar_tinte
    lda #1
    sta refresco                ; las páginas que piden un actor pueden cambiar
    rts
.endproc

; A: un índice de la tabla de gráficos del mapa —la que arma `ruta_grafico` y
; que `load_ruta_graficos` copia a `ruta_graf_buf`—. Deja `hero_poses`,
; `hero_pal` y `hero_cgram` apuntando a ese gráfico y vuelve con C=1; si el
; gráfico no está en el banco de sprites de este mapa vuelve con C=0 y sin
; tocar nada.
;
; Sale barata porque las dos tablas de poses tienen la misma forma: una entrada
; de `npc_poses` son doce punteros de tres bytes a las poses del personaje, y
; los doce que la tabla de actores le da al líder están escritos igual. O sea
; que alcanza con apuntar `hero_poses` treinta y seis bytes adentro de
; `npc_poses` y `place_hero` sigue sin enterarse.
;
; `hero_cgram` se apaga: los quince colores del líder los sube `aplicar_tinte`
; **en la fila que dice `hero_pal`**, así que dejarlo puesto con la paleta nueva
; le escribiría los colores de Talan encima a la paleta del gráfico al que se
; cambió. Mientras el cambio está puesto, el héroe se dibuja con la paleta del
; gráfico nuevo, que ya vive en CGRAM con el resto de los sprites del mapa.
;
; La usan los dos que le cambian el gráfico al héroe: la orden 34 de una ruta
; —`grafico_heroe`— y el `ChangeSpriteAssociation` sobre el actor que lidera
; —`elegir_grafico_heroe`—. Lo que cada uno hace con el C=0 es distinto y por
; eso queda afuera: la orden 34 esconde al héroe y el cambio de actor lo deja
; con el gráfico del LDB.
.proc hero_poses_de_grafico
.a8
.i16
    asl a                       ; dos bytes por entrada en `ruta_graf_buf`
    rep #$20
.a16
    and #$00FF
    tax
    sep #$20
.a8
    lda ruta_graf_buf, x        ; su entrada en `npc_poses`, o $FF
    cmp #$FF
    beq no_esta
    sta temp
    lda ruta_graf_buf + 1, x
    asl a
    and #$0E                    ; la paleta, corrida a su lugar en vhoopppN
    sta hero_pal
    rep #$20
.a16
    lda temp
    and #$00FF
    asl a
    asl a                       ; k por cuatro
    sta temp + 2
    asl a
    asl a
    asl a                       ; k por treinta y dos
    clc
    adc temp + 2                ; treinta y seis por personaje: doce punteros
    clc                         ; de tres bytes, como la tabla del actor
    adc poses_ptr
    sta hero_poses
    sep #$20
.a8
    lda poses_ptr + 2
    adc #0
    sta hero_poses + 2
    stz hero_cgram + 2          ; ver arriba: nadie sube colores encima
    sec
    rts
no_esta:
    clc
    rts
.endproc

; Con qué se dibuja el héroe: se busca al primero del grupo en la tabla de
; actores del mapa y se guardan sus doce poses y su paleta.
;
; Antes esto no existía: el héroe era siempre el personaje 0 del banco de
; sprites y el tile de cada pose salía de una cuenta. Con el grupo cambiando en
; caliente ya no alcanza, y además el tile puede pasar de ocho bits cuando hay
; varios personajes, así que se lee de una tabla.
.proc elegir_grafico_heroe
.a8
.i16
    lda #$FF
    sta hero_pose_vram          ; otro actor: su pose hay que subirla sí o sí
    stz hero_pal
    rep #$20
.a16
    stz hero_poses
    stz hero_cgram
    sep #$20
.a8
    stz hero_poses + 2
    stz hero_cgram + 2
    lda grupo_n
    beq sin_lider               ; grupo vacío: no se dibuja nada

    ldx mapa_ofs
    rep #$20
.a16
    lda f:mapa_tabla + M_ACTOR_COUNT, x
    beq sin_lider16
    sta temp + 2
    lda f:mapa_tabla + M_PTR_ACTOR_TABLE, x
    sta act_ptr
    sep #$20
.a8
    lda f:mapa_tabla + M_PTR_ACTOR_TABLE + 2, x
    sta act_ptr + 2

    ldy #$0000
    lda grupo                   ; el líder
    sta temp
cada_actor:
    lda [act_ptr], y
    cmp temp
    beq lo_encontre
    rep #$20
.a16
    tya
    clc
    adc #ACTOR_BYTES
    tay
    dec temp + 2
    sep #$20
.a8
    bne cada_actor
    bra sin_lider

lo_encontre:
    ; Antes que el LDB, el `ChangeSpriteAssociation` que le hayan hecho a este
    ; actor: es el `actor->SetSprite` de RM2k, y vive en el actor, así que
    ; **cruza el teletransporte**. Si su gráfico no está en el banco de sprites
    ; de este mapa se cae al del LDB, que es a lo que apunta el camino de
    ; abajo. Ver OP_ACTOR_SPRITE en eventos.py.
    phy                         ; la entrada del actor, por si no hay cambio
    lda temp                    ; el líder
    jsr actor_graf_leer
    cmp #ACTOR_GRAF_NINGUNO
    beq sin_cambio_de_sprite
    jsr hero_poses_de_grafico
    bcc sin_cambio_de_sprite
    ply
    rts
sin_cambio_de_sprite:
    ply
    iny
    lda [act_ptr], y            ; su paleta, ya corrida a su lugar en vhoopppN
    asl a
    and #$0E
    sta hero_pal
    iny                         ; y acá arrancan sus quince colores
    rep #$20
.a16
    tya
    clc
    adc act_ptr
    sta hero_cgram
    sep #$20
.a8
    lda act_ptr + 2
    adc #0
    sta hero_cgram + 2
    rep #$20
.a16
    tya
    clc
    adc #ACTOR_COLORES          ; y detrás, las doce palabras de las poses
    tay
    clc
    adc act_ptr
    sta hero_poses
    sep #$20
.a8
    lda act_ptr + 2
    adc #0
    sta hero_poses + 2
    rts

sin_lider16:
.a16
    ; se llega en dieciséis; el `sep` de abajo lo achica
    sep #$20
.a8
sin_lider:
    rts
.endproc

