.segment "CODE"

; El bucle del intérprete: un opcode por vuelta hasta el FIN.
;
; Y es el cursor del bytecode y tiene que sobrevivir a todo el bucle, así que
; cada `jsr` que sale de acá lo guarda antes de irse. Las rutinas que se llaman
; usan X e Y para lo suyo —poner_switch indexa el bitmap de switches,
; aplicar_tinte recorre tres paletas— y ninguna tiene por qué saber que acá
; significan otra cosa. Sin esto, el primer OP_SWITCH dejaba a Y valiendo el
; número del switch dividido ocho, y lo que se leía como opcode siguiente era
; un byte cualquiera del medio de la página: el bucle cortaba ahí y el resto no
; corría.
.proc correr_codigo
.a8
.i16
    ldy ev_cur                  ; donde quedó el cuadro anterior
otro:
    lda [cod_ptr], y
    iny
    ; Cada opcode se despacha con `bne` al salteo y `jmp` al cuerpo, y no con un
    ; `beq` derecho al cuerpo, que es lo que había. La diferencia es el alcance:
    ; un `beq` llega a 127 bytes y el cuerpo del último opcode está detrás de
    ; todos los demás, así que el límite lo marca la suma de los otros seis.
    ;
    ; Eso ya cortó dos veces. La primera, al aparecer OP_MESSAGE, dejó a
    ; OP_TELEPORT a 140 bytes; se arregló ordenando las comparaciones como los
    ; cuerpos. La segunda fue darle su operando a OP_MESSAGE: 129 bytes, o sea
    ; que aquel arreglo duraba exactamente un opcode. Y faltan cuatro —MoveEvent
    ; sobre otro evento, FlashSprite, PlaySound y ControlVars, en ese orden y
    ; medidos con `just snes-destraba`—, así que el límite se saca del medio de
    ; una vez: un `jmp` llega a cualquier parte del banco.
    ;
    ; Sale tres bytes y cuatro ciclos por opcode que no matchea, en un despacho
    ; que corre unas pocas veces por cuadro. El orden ya no significa nada.
    cmp #OP_MESSAGE
    bne :+
    jmp op_message
:   cmp #OP_SWITCH
    bne :+
    jmp op_switch
:   cmp #OP_ROUTE
    bne :+
    jmp op_route
:   cmp #OP_PARTY
    bne :+
    jmp op_party
:   cmp #OP_DELAY
    bne :+
    jmp op_delay
:   cmp #OP_TINT
    bne :+
    jmp op_tint
:   cmp #OP_FLASH
    bne :+
    jmp op_flash
:   cmp #OP_WAIT_ROUTES
    bne :+
    jmp op_wait_routes
:   cmp #OP_BGM
    bne :+
    jmp op_bgm
:   cmp #OP_PLACE
    bne :+
    jmp op_place
:   cmp #OP_PLACE_VAR
    bne :+
    jmp op_place_var
:   cmp #OP_SWAP
    bne :+
    jmp op_swap
:   cmp #OP_SHAKE
    bne :+
    jmp op_shake
:   cmp #OP_FLASH_SCREEN
    bne :+
    jmp op_flash_screen
:   cmp #OP_FADE_BGM
    bne :+
    jmp op_fade_bgm
:   cmp #OP_PAN
    bne :+
    jmp op_pan
:   cmp #OP_TIMER
    bne :+
    jmp op_timer
:   cmp #OP_IF
    bne :+
    jmp op_if
:   cmp #OP_GOTO
    bne :+
    jmp op_goto
:   cmp #OP_CHOICE
    bne :+
    jmp op_choice
:   cmp #OP_GOLD
    bne :+
    jmp op_gold
:   cmp #OP_ITEM
    bne :+
    jmp op_item
:   cmp #OP_ACCESS
    bne :+
    jmp op_access
:   cmp #OP_ACTOR_SPRITE
    bne :+
    jmp op_actor_sprite
:   cmp #OP_KEY
    bne :+
    jmp op_key
:   cmp #OP_SHOP
    bne :+
    jmp op_shop
:   cmp #OP_BATTLE
    bne :+
    jmp op_battle
:   cmp #OP_WEATHER
    bne :+
    jmp op_weather
:   cmp #OP_ANIMATION
    bne :+
    jmp op_animation
:   cmp #OP_SOUND
    bne :+
    jmp op_sound
:   cmp #OP_PICTURE
    bne :+
    jmp op_picture
:   cmp #OP_PICTURE_MOVE
    bne :+
    jmp op_picture_move
:   cmp #OP_PICTURE_ERASE
    bne :+
    jmp op_picture_erase
:   cmp #OP_SAVE
    bne :+
    jmp op_save
:   cmp #OP_TELEPORT
    bne :+
    jmp op_teleport
:   cmp #OP_VAR
    bne :+
    jmp op_var
:   cmp #OP_IF_VAR
    bne :+
    jmp op_if_var
:   cmp #OP_IF_ACTOR
    bne :+
    jmp op_if_actor
:   cmp #OP_STOP_ROUTES
    bne :+
    jmp op_stop_routes
:   cmp #OP_HEAL
    bne :+
    jmp op_heal
:   cmp #OP_TILE_SUB
    bne :+
    jmp op_tile_sub
:   cmp #OP_TERRAIN
    bne :+
    jmp op_terrain
:   cmp #OP_EQUIPMENT
    bne :+
    jmp op_equipment
:   cmp #OP_SKILL
    bne :+
    jmp op_skill
:   cmp #OP_GAME_OVER
    bne :+
    jmp op_game_over
:   stz ev_activo              ; OP_DONE, o algo que no conocemos: se corta
    rts

.endproc

