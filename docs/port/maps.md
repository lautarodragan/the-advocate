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
multiplicar ni armar una dirección de 24 bits desde cero, que es incómodo
porque la grilla cruza de banco y los bancos no son contiguos: pasarse del
`$FFFF` lleva al `$8000` del siguiente, y lo saben sólo `ptr_more` y
`ptr_minus`.

#### La grilla vive en la WRAM, y el cartucho la trae comprimida

Desde el 2026-09-26 la grilla viaja en el cartucho en LZ2 y se descomprime
entera al cargar el mapa en `$7E8000`, siguiendo en `$7F8000` si pasa de 32 KB
(`GRID` en `tools/runtime/far_ram.s`, `lz2_grid` en `decompress.s`). La
mitad alta de dos bancos seguidos de la WRAM tiene la forma de dos bancos de
LoROM, así que los lectores no cambiaron: antes el puntero apuntaba al
cartucho, ahora a la WRAM. La pelea pisa la mitad del `$7F`, y
`back_from_battle` la vuelve a descomprimir. Qué costó reservar esa RAM y cómo
se revierte: `workflow/decisiones/la-grilla-vive-en-la-wram.md`.

Lo mismo pasa con los tiles del fondo, de la capa de encima, de los sprites y
con los dibujos de la animación del ChipSet: viajan en LZ2, se descomprimen a
`$7F0000` y se suben con el mismo DMA de antes. Los dibujos de la animación
quedan en `$7F6000` mientras dure el mapa, porque se suben cada vez que cambia
el reloj. Cómo se parte cada bloque en flujos y con qué topes de la WRAM: el
`materials.rs` de `tools/rm2k-snes/mapdata/`; el formato y el compresor:
`tools/snes/lz2/`, que la emisión usa como biblioteca.

Y desde el 2026-10-01, **la tabla de bloques y su pasabilidad**: la CPU las
lee mientras se juega, así que no se suben a la VRAM sino que viven en la
WRAM **justo detrás de la grilla**, en la mitad del `$7F`. Viajan como un
tercer flujo pegado a los dos de la grilla, `lz2_grid` lo descomprime donde
terminó el segundo, y vuelven con ella después de una pelea. La dirección no
la calcula la ROM: la pone el conversor en el registro del mapa
(`map_ram_pointers` en `record.rs`), y la prueba de abajo mira que coincida
con dónde quedó. El conversor corta si un mapa no entra: lo que la grilla
ocupa del `$7F` más lo que va detrás no puede pasar de sus 32 KB.

Lo que queda en la VRAM y en la WRAM después de cargar lo compara
`rom/pruebas/rpgmaker/test_carga_descomprimida.py` contra lo que el conversor deja
sin comprimir en `rom/build/<cartucho>/crudos/`.
