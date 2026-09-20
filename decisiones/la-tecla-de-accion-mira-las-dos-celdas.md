# Qué

**La tecla de acción mira las dos celdas, y cada una pide la capa contraria.**
`CheckEventTriggerHere` quiere `GetLayer() != Layers_same` y
`CheckEventTriggerThere` quiere `== Layers_same`.

# Por qué

No es simetría de adorno: un evento de la capa del héroe le cierra el paso, así
que nunca se podría parar encima; uno de otra capa no lo frena y se le camina
por arriba.

El filtro **vive en la ROM y no en el conversor**, porque la misma página vale o
no según qué celda la esté mirando.
