.segment "FAR"
.a8
.i16

; --- OP_CELL_TEST: "¿está este personaje en la celda de las variables?" -------
;
; Es el patrón con que las páginas paralelas de RM2k miran si dos personajes se
; tocan: dos `ControlVars` de clase 6 que copian la celda de uno a dos
; variables, y dos `ConditionalBranch` anidados que las comparan con otras dos.
; El conversor funde los cuatro en uno —ver `fundir_celdas` en eventos.py— y
; hace **exactamente lo mismo**: las dos escrituras, con su refresco, y las dos
; comparaciones, cada una con su destino.
;
; Existe por el costo, no por la semántica. Cada vuelta de la carrera (49, 52 y
; 54) tiene cuarenta páginas así corriendo en cada cuadro, y por los cuatro
; opcodes el intérprete se llevaba casi cinco líneas por página: la vuelta
; entera no entraba en un cuadro. Medido en
; workflow/tasks/*/carrera-2-a-sesenta-cuadros.md.
;
; Vive en el banco 1 porque en el banco 0 no hay lugar: `op_cell_test`, el
; manejador del despacho, es un `jsl` hasta acá. Por eso todo va con
; direccionamiento largo: el banco de datos es el del bytecode.
;
; Entra con Y en el primer operando y vuelve con Y en el opcode que sigue o en
; el destino de la condición que falló.
; Una de las dos escrituras: la variable, como desplazamiento, con la
; coordenada y el refresco en los dos bits de arriba. `temp` es la x del
; personaje y `temp + 2` su y. Entra y sale con A de dieciséis bits.
.macro CELDA_ESCRIBIR
.local refrescar, ya, es_y, poner
    lda [cod_ptr], y
    iny
    iny
    bmi refrescar               ; CELDA_REFRESCO, el bit 15
ya:
    bit #CELDA_Y
    bne es_y
    and #CELDA_VARIABLE
    tax
    lda temp
    bra poner
refrescar:
    pha
    sep #$20
    lda #1
    sta f:refresco
    rep #$20
    pla
    bra ya
es_y:
    and #CELDA_VARIABLE
    tax
    lda temp + 2
poner:
    sta f:FAR_LARGO + FAR_VARIABLES, x
.endmacro

; Una de las dos comparaciones: dos variables, como desplazamientos, y el
; destino si no son iguales. Si falla, deja Y en el destino y salta a `fin`.
.macro CELDA_PROBAR fin
.local falla
    lda [cod_ptr], y            ; la de la izquierda
    tax
    lda f:FAR_LARGO + FAR_VARIABLES, x
    sta temp                    ; la celda del personaje ya no hace falta
    iny
    iny
    lda [cod_ptr], y            ; y la de la derecha
    tax
    lda f:FAR_LARGO + FAR_VARIABLES, x
    cmp temp
    bne falla
    iny                         ; se cumple: saltea la derecha y el destino
    iny
    iny
    iny
    bra :+
falla:
    iny
    iny
    lda [cod_ptr], y            ; el destino, absoluto adentro de la página
    tay
    bra fin
:
.endmacro

; Lo que queda de una escritura sin los dos bits de arriba: el desplazamiento
; de la variable, que con 256 ranuras llega a 510.
CELDA_VARIABLE = $01FF
.assert CELDA_Y = $4000 && CELDA_REFRESCO = $8000, error, "celda_probar lee el refresco con el bit N y la coordenada con el 14"

.proc celda_probar
.a8
.i16
    rep #$20
.a16
    lda [cod_ptr], y            ; el blanco: 0 el héroe, o el evento más uno
    iny
    and #$00FF
    asl a
    asl a                       ; por EV_STRIDE
    tax
    beq heroe
    ; La celda viva, igual que la clase 6 de `op_var`.
    lda f:ev_pos_buf - EV_STRIDE + 0, x
    sta temp
    lda f:ev_pos_buf - EV_STRIDE + 2, x
    sta temp + 2
    bra escribir
heroe:
    lda tile_x
    sta temp
    lda tile_y
    sta temp + 2
escribir:
    ; Todo en línea y sin `jsr`: corre cuarenta veces por cuadro.
    CELDA_ESCRIBIR
    CELDA_ESCRIBIR
    CELDA_PROBAR listo
    CELDA_PROBAR listo
listo:
    sep #$20
.a8
    rtl
.endproc

