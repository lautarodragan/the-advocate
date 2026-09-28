---
name: "Mundo 3: el espacio"
description: "El hito 3 de el-mundo-y-lo-que-sigue: el acomodo de bancos con first-fit decreasing, la tabla de alturas del .msu por paquete, el bloque de textos de a cuatro bytes y `just espacio`"
type: refactor
assignee: taro
---

# Qué

El hito 3 de `todo/el-mundo-y-lo-que-sigue.md`, que tiene lo medido antes
(sección "Espacio"). Sale de `2ca861a`, con los hitos 1 y 2 ya en `release`.
Un commit por cosa, cada uno con su antes y su después en el mensaje:

1. **`just espacio`** (`tools/ensamblado/espacio.py`): imprime, para cada
   cartucho o para la ruta de una ROM armada aparte, los bancos de datos
   usados y libres, los huecos, banco 0, banco 1, BSS, ZEROPAGE y el bloque
   de textos. Lee el `.dbg` y el `memoria.cfg`; no relinkea. Los textos salen
   de dos constantes que el conversor emite al lado de `mensajes`
   (`MENSAJES_BYTES`, `MENSAJES_TOPE`). `test_espacio.py` la compara con el
   `.res` linkeado a mano, y AGENTS.md apunta a la receta.
2. **El acomodo de bancos con first-fit decreasing** (`bancos.resolver`). Las
   restricciones son las que ya declaraba el conversor: un `.bloque` de hasta
   un banco entero en uno; uno de más (el bloque de textos) arrancando banco
   y siguiendo en los siguientes; un `.cruza` partido sólo entre bancos
   consecutivos (`spc_block`, `advance`), entero en un hueco si entra y si no
   en una cadena al final. No se encontró ninguna otra restricción de orden
   (ver el mensaje del commit: restas de etiquetas, `*`, `#^` de otra
   etiqueta). Los bancos se escriben al final de `mapdata.inc`.
3. **`se_msu_altura` por paquete**: pares (índice, altura) sólo de los
   sonidos del paquete, ordenados y cerrados con $FFFF; listas iguales
   compartidas. `altura_msu` la recorre. Se descartó partirla entre bancos.
4. **Los textos de a cuatro bytes**: `MENSAJES_PASO = 4`, y `msg_empezar`
   saca los dos bits de arriba con `rol` para que el de más de 128 KB corra
   el mismo código que el de más de 64 KB. Se midieron el paso 3, un operando
   de 24 bits y un segundo bloque con otro opcode (ver el commit). `empujon`
   se volvió a medir.

# Lo medido

Con `just espacio`, en bancos de datos usados (entran 124, del $02 al $7D).
"Camino" es `release` más el camino principal del mundo —85 a 95, 99 a 102 y
259; el 74 y el 255 ya estaban—, armado aparte y sin commitear. Antes del
punto 4 el camino no convierte por los textos, así que sus dos primeras
filas se armaron con el paso 4 puesto a mano sólo para medir.

    después de            release        test-special   camino
    2ca861a               113 (312,9 KB  24 (66,1 KB    no linkea: pide 125
                          de huecos)     de huecos)     (339,9 KB de huecos)
    first-fit decreasing  104 (18,0 KB)  22 (0,6 KB)    115
    alturas del .msu      103            22             114
    textos de a 4         103            22             114

    banco 0 (release)     175 -> 165 B (el `msg_empezar` nuevo)
    banco 0 (camino)      136 B
    banco 1 (release)     7.761 -> 7.744 B (`altura_msu`)
    BSS / ZEROPAGE        138 / 4 B, sin cambios
    se_msu_altura         release 22.484 -> 1.614 B; camino 29.202 -> 1.852 B
    textos (camino)       137.822 de 262.144 B

**Al camino principal le quedan 10 bancos.** Lo opcional, sumado de a una
zona encima del camino (el 67 sin los dígitos del cronómetro, porque con ellos
no convierte —`args.timer_en`, ver el plan—; eso no es de este hito):

    + Yun Town (67 71 72)            117 bancos, quedan 7, banco 0 100 B
    + Drust Camp (68 103 199-201)    119, quedan 5, banco 0 56 B
    + Tangle Forest (310 a 313)      119, quedan 5, banco 0 90 B
    + las tres                       125: no entra por un banco

Así que después de este hito entran el camino y cualquiera de las tres
zonas, o dos; las tres juntas, no. Lo siguiente que da espacio está en el
plan: las poses espejadas y la música.

# Qué mirar (taro)

La ROM cambió de lugar casi todos sus datos y el bloque de textos se lee de
otra manera, así que lo que conviene jugar es lo que ninguna golden cubre
entero: **textos largos del final de Lashe City y de Sorbe** (los que caen
pasados los 64 KB del bloque) y **efectos de sonido con MSU-1**, que ahora
buscan su altura en una lista. Las goldens y la tanda pasan (`just pruebas`,
878).

# Lo que no cubre `just pruebas`

* El bit de más de 128 KB de `msg_empezar`: ningún cartucho de la tanda llega
  a ese desplazamiento. Corre las mismas instrucciones que el de 64 KB, que sí
  se ejecuta (con él roto dan rojo ocho goldens).
* Los números del camino y de las zonas opcionales: son variantes que ninguna
  receta arma.
