#### El mapa no se guarda como tilemap

Expandido no entraría en el cartucho: 1000×80 celdas por dos bytes son 156 KB,
más que la ROM entera. Lo que se guarda es la **celda de 16×16 de RM2k**, que es
la unidad con la que el juego fue dibujado y que se repite muchísimo.

    mapa 52, 1000x80 celdas    tilemap expandido   160.000 B
                               grilla de bloques    40.000 B + 1.744 B de tabla

El bloque lleva sus cuatro celdas de fondo, sus cuatro de la capa de encima y su
pasabilidad, todo junto. En todo el juego el máximo son 512 bloques distintos.

Que la pasabilidad viaje en el bloque **borró la tabla de colisión entera** —un
byte por celda, hasta 20 KB. Y no es un atajo: dos celdas que se dibujan igual
podrían tener permisos distintos si vinieran de tiles distintos del ChipSet, así
que la pasabilidad va en la clave con la que se deduplica y esas dos se separan
solas.

Dónde está el héroe dentro de la grilla tampoco es un índice sino un **puntero
que se mueve con él**, una celda o una fila por paso. Así nunca hay que
multiplicar ni armar una dirección de 24 bits desde cero, que en LoROM es
incómodo porque los bancos no son contiguos.
