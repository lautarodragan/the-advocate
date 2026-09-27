.segment "CODE"
.a8
.i16

; --- el intérprete: la música y los efectos de sonido ----------------------
;
; Manejadores de opcodes: el despacho de `correr_codigo`, en interprete.s,
; salta a cada uno con Y en su primer operando, y cada uno vuelve al lazo
; con `jmp correr_codigo::otro` o corta el cuadro con `rts`.

; `PlayBGM`. El operando es el índice del tema en `Temas`, y el cartucho lleva
; los que hayan entrado en la ARAM: los primeros `TEMA_TOTAL`. Un índice más
; alto es un tema que no entró y no suena, que es lo que pasaba con todos menos
; uno hasta el 2026-09-06. Ver `temas_de_la_rom` en el conversor.
.proc op_bgm
    lda [cod_ptr], y
    iny
    cmp #TEMA_TOTAL
    bcs otro_tema
    phy
    jsr music_start
    ply
otro_tema:
    jmp correr_codigo::otro

.endproc

; `FadeOutBGM`. El operando es cuánto baja el volumen por cuadro; lo baja
; `bgm_fundido_tick`, no acá, y la página sigue de largo en este mismo cuadro,
; que es lo que hace `CommandFadeOutBGM` devolviendo true.
;
; Con el tema apagado no se arranca nada: el fundido escribiría el volumen de un
; tema que no suena, y encima lo dejaría en cero para el `PlayBGM` que venga.
;
; Con una pista del MSU-1 sonando, en cambio, sí hay qué fundir: `music_apagada`
; vale 1 —el SPC700 está callado a propósito— y el que baja es el volumen del
; MSU-1. Sin esta salida, un `FadeOutBGM` no hacía nada y la pista seguía
; sonando para siempre.
.proc op_fade_bgm
    lda f:MSU_SUENA
    bne fundir
    lda music_apagada
    bne fundir_nada
fundir:
    php
    sei                         ; lo lee `irq_musica`: todo junto o nada
    lda [cod_ptr], y
    sta bgm_paso
    iny
    lda [cod_ptr], y
    sta bgm_paso + 1
    iny
    lda #$FF
    sta bgm_nivel               ; el volumen entero, que es de donde baja
    sta bgm_nivel + 1
    lda #1
    sta bgm_fundido
    plp
    jmp correr_codigo::otro
fundir_nada:
    iny
    iny
    jmp correr_codigo::otro

.endproc

; `OP_SOUND`: el índice en `sonido_tabla`. Queda pendiente y arranca al
; final de `music_tick`, detrás de lo que la música escriba en el cuadro.
.proc op_sound
    jsr sonido_de_codigo
    jmp correr_codigo::otro

.endproc

