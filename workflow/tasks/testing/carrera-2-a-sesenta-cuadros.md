---
name: "Carrera 2: a 60 cuadros"
description: "Las tres vueltas de la carrera (49, 52, 54) sin perder cuadros manejando: perfilar dónde se va el tiempo y medir el límite de cada camino"
type: refactor
assignee: taro
---

# Qué

El hito 2 de `todo/la-carrera-y-lo-que-sigue.md`. Sale de `main` en `69e66ed`.
Se da por hecho con los cuadros perdidos en cero o casi en el 49, el 52 y el 54
manejando, y lo tiene que cobrar una prueba: el recorrido
`pruebas/abl/test_recorrido_carrera_golden.py` ya maneja con un piloto.

Lo medido antes de empezar (hito 1), manejando y sólo en ticks con el switch
170, sin mensaje ni fundido:

    mapa   cuadros de hardware por tick
    49     2,07
    52     2,04
    54     2,04
    51     1,00   (13 páginas)

Números reservados: opcode 0x31 (y 0x33 si hace falta un segundo) y la RAM
lejana $7E7980-$7E799F. Se usaron el 0x31 (`OP_CELL_TEST`) y los primeros 16
bytes de la RAM (`NPC_FILA_APARTE`); el 0x33 no hizo falta.

# Dónde se va el tiempo

Medido con un perfilador de líneas que no se commitea: una marca en cada
frontera lee el contador vertical del PPU (`SLHV`/`OPVCT`) y suma las líneas
desde la marca anterior al cubo que corresponde. Cada marca cuesta ~1,4 líneas,
así que se corre dos veces —una marca por sitio y dos— y el costo se descuenta
(`2 * simple - doble`). El trabajo del cuadro es todo lo que no es esperar el
vblank; **entra en un cuadro si es menos de 262 líneas**.

Líneas por tick, en `69e66ed`:

    cubo                               49     52     54     51
    bytecode de los paralelos         201    195    196     27
    lazo de paralelos (estado, lista)  66     68     69     12
    buscar la ranura de ruta + cola    41     36     10      2
    refrescar_npc de los que andan     37     28      -      -
    cuadro_de_ruta_ev de los que andan  9      6      -      -
    build_oam                          44     43     40     20
    cámara y stream                    26     21     20     15
    héroe, menú, cronómetro            15     13     13      1
    principio del vblank               16     14     12     11
    lo demás                           ~9     ~8     ~9     ~6
    TRABAJO                           464    432    367     94

Por página paralela de auto (41 en cada vuelta): ~4,8 líneas de bytecode
—`OP_VAR` clase 6 dos veces, un `OP_IF_VAR` que falla y el `OP_DONE`—, ~1,6
del lazo que carga y guarda su estado, y ~0,25 de buscar si tiene ranura de
ruta. Los cinco autos que andan en el 49 (cuatro en el 52) cuestan ~16 líneas
cada uno entre su ruta y `refrescar_npc`, y eso no es de los paralelos: sería
igual con las páginas sin compilar.

Para entrar en un cuadro el 49 tiene que bajar de 464 a menos de 262, o sea
~200 líneas, y con margen para los ticks más pesados.

# Los caminos, cada uno con su límite medido

Cada fila es un paso sobre el anterior, en el orden en que se hizo: líneas de
trabajo por tick (promedio, corregido por las marcas) y cuadros de hardware
por tick manejando. Lo que cada paso ahorra está medido, no estimado.

    paso                                        trabajo 49/52/54   cuadros/tick 49/52/54
    69e66ed                                       464/432/367       2,07/2,04/2,04
    1 variables por direccionamiento largo,       417/ - /325       2,03/2,03/2,04
      igualdad sin comparar_var, clase 6 primero
    2 OP_CELL_TEST por el despacho                352/324/262       2,02/2,01/1,53
    3 lista y estado de paralelos, largo          337/ - /248       2,02/1,92/1,36
    4 la ranura de ruta recordada (PAR_RANURA)    303/280/ -        2,00/1,75/1,23
    5 el atajo: OP_CELL_TEST sin el intérprete    280/252/207       1,61/1,29/1,07
    6 la fila del NPC recordada en la ranura      262/243/ -        1,32/1,18/1,07
    7 el banco 1 por el espejo rápido, OP_CELL_TEST                 1,18/1,13/1,05
      con desplazamientos, par_dir de una vez     236/ - / -        1,12/1,09/1,05
    8 clear_oam desenrollado en el banco 1        226/ - / -        1,10/1,08/1,04
    9 los choques y el paso de a dos ciclos       220/ - / -        1,07/1,05/1,04
      menos: celda_bloqueada y pasa_con_evento de
      atrás para adelante, npc_swap desenrollado,
      el descarte por X de build_oam en el lazo
   10 pasa_hay: sin eventos de tile que impongan,                  1,03/1,03/1,04
      pasa_con_evento no recorre nada
   11 ptr_de_celda con el multiplicador                            1,03/1,03/1,04
   12 los paralelos de OP_CELL_TEST de corrido     p50 197/186/157  1,03/1,02/1,04
      (paralelos_celda, en el banco 1)
   13 acomodar: buscar el lugar y correr las                        1,02/1,02/1,04
      demás con mvn/mvp, en vez de intercambiar

(Los 1,04 del 54 son un solo tick de 27 cuadros al largar la vuelta, cuando
suena el tema y se suben sus muestras: con el auto quieto en la largada. Sin
los ticks de antes de que el auto salga, ver abajo.)

Lo que dice cada camino, como límite:

* **El intérprete general** (pasos 1 y, estimado, un despacho más corto): el
  bytecode baja de 201 a 155 líneas en el 49, un 23%, y el despacho con el
  opcode ya duplicado en el bytecode ahorraría ~10 ciclos por opcode, unas
  ocho líneas más. Con eso el 49 queda en ~410 líneas: **sigue a dos cuadros
  por tick**. No alcanza solo, pero es general y quedó.
* **El opcode fundido por el despacho** (paso 2): baja el bytecode a ~90
  líneas, 2,3 por página. Solo, el 49 y el 52 **siguen a dos cuadros**: lo
  que quedaba era el lazo de los paralelos (cargar y guardar el estado de
  cada uno), buscar la ranura de ruta y el paso de los autos que andan.
* **El fundido sin el intérprete** (pasos 5 y 12): una página que empieza con
  `OP_CELL_TEST`, no está a mitad de nada y no pasa de la condición no
  necesita ni `correr_codigo` ni guardar su estado. El piso de este diseño es
  la condición misma —dos escrituras y una comparación, ~200 ciclos, una
  línea— más leer la lista y el estado: **~1,7 líneas por página**, ~70 para
  las 41 de una vuelta, contra ~310 al empezar.
* **"Correr las paralelas sólo cuando algo cambia de celda"** (la idea 2 de
  `wishlist/optimizar-los-eventos-paralelos-al-compilar.md`): no se hizo, y
  su límite es cero para lo que importa. El héroe avanza media celda por tick,
  así que cambia de celda cada dos ticks y en ésos corren las 41 igual: el
  tick más pesado no baja. Además las 41 escriben las mismas dos variables
  (la 36 y la 37) en cada cuadro, y saltearlas cambia lo que queda en ellas.
* **El resto del cuadro**, que no es de los paralelos: los autos que andan
  (su ruta, `refrescar_npc`, reacomodar su fila), `build_oam`, la cámara.
  Con los paralelos ya en ~70, lo que perdía cuadros eran **los ticks en que
  cuatro o cinco autos que andan arrancan su paso a la vez**: cada paso nuevo
  pregunta si puede entrar en la celda (`puede_celda`: la grilla, los eventos
  de tile, quién está parado ahí) y el auto que cambia de carril pasa de una
  vez a los siete u ocho del carril de al lado en el orden de dibujado. Los
  pasos 6 y 8 a 13 son eso, y son generales: cualquier mapa con eventos que
  andan los aprovecha.

# Cómo quedó

Dos commits: `2345738` (las variables y `OP_CELL_TEST`, con el compilador) y
`da466bb` (los paralelos sin el intérprete, las ranuras y las filas
recordadas, los choques, `acomodar_npc` y la OAM); después el merge con
`main` y los techos. Lo que hace cada pieza
está en su comentario; acá, lo que no se ve en el código.

* **`OP_CELL_TEST` no cambia la semántica.** Hace las dos escrituras —con su
  refresco— y las dos comparaciones, cada una con su destino, igual que los
  cuatro opcodes sueltos. El compilador lo arma con lo que emitirían ellos
  (`_pieza_de_celdas`), así que las validaciones son las mismas.
* **El atajo tampoco**: es la primera vuelta del intérprete y la segunda
  (`OP_DONE`), sin pasar por el despacho. Lo que se saltea es guardar un
  estado que queda igual: sin espera y sin página a medio correr.
* **`PAR_RANURA` se borra en `limpiar_paralelos`**, pegado a `load_npcs`, que
  es donde se sueltan todas las ranuras: dentro de un mapa una ranura no se
  suelta nunca. La fila recordada de `npc_de_ranura` y `pasa_hay` sí pueden
  quedar viejas, y por eso la fila se valida y `pasa_hay` sólo se prende.
* **`acomodar_npc` deja el mismo orden** que los intercambios uno por uno:
  busca con la clave de la fila que cambió y corre las del medio. Lo cobran
  las goldens de los recorridos que caminan NPC.

## Cuadros por tick al final

Manejando: con el 170, sin mensaje ni fundido, en el mismo mapa al empezar y
al terminar el tick, **y con el auto fuera de la largada** (x >= 4). Esto
último saca los ticks en que la vuelta pone su tema y se suben sus muestras,
con el auto quieto: uno de 27 cuadros en el 54 y uno de 8 en el 52, que ya
estaban en `69e66ed` y no son de manejar.

    mapa   69e66ed        al final
    49     2,06 (979)     1,02   (21 de 979 ticks con un cuadro de más)
    52     2,04 (546)     1,004  (2 de 546)
    54     2,00 (574)     1,00   (0)
    51     1,00           1,00

Lo que le queda al 49: los ticks en que los cinco autos que andan arrancan su
paso a la vez —cinco `puede_celda`, y el reacomodo de sus filas—, que pasan
de 262 líneas por 1 a 35.

## La prueba

`test_la_carrera_entera` cuenta los cuadros de hardware de los ticks
manejando de cada vuelta, con el mismo criterio, y falla con más de
`CUADROS_DE_MAS` (5) de más por cada cien. Contra `69e66ed` falla: "la vuelta
del mapa 49 gastó 2017 cuadros de hardware en 977 ticks: 1040 de más".

## Espacio

Medido con el método de `AGENTS.md` sobre el merge con `main` (`fdf7593`):

    cartucho      banco 0            BSS   ZEROPAGE   banco 1
    release       344 B (189 antes)  138   4          ~9,3 KB
    test-special  1.120 B            138   4          ~10,4 KB

(Los 29 bytes de BSS de más son de `main`: la ruta del héroe dejó de copiarse
a un búfer.) El banco 0 ganó: `clear_oam`, `npc_swap`, `npc_va_antes` y el
lazo de `acomodar_npc` se fueron al banco 1, y lo nuevo vive allá.

## Los techos

Sobre el merge, `test_el_tema_no_recorta_en_su_pico[dcbest]` dio rojo (dos
muestras en el tope); por separado las dos ramas pasaban. Es lo que avisa esa
prueba: el pico se mueve con cuándo cae cada escritura al DSP dentro del
cuadro, y el hito cambió la duración de casi todos los cuadros con NPC que
andan. `just techos` lo remidió (`33e78c4`).

# Pruebas

`just pruebas` en verde sobre `da466bb`, y sobre el merge con `main` con la
tabla de techos remedida. Ninguna golden cambió. Casos nuevos en `pruebas/herramientas/test_paginas.py`: la
forma de `OP_CELL_TEST`, el destino del `else` de la rama de adentro, y que
sin la forma exacta no se funde.

# Qué tiene que probar taro jugando

* Las tres vueltas: que se sientan a velocidad entera y no a media, y que el
  volante responda igual que antes. Chocar, y que el 50 vuelva a la vuelta.
* Que los autos que andan (los que suben y bajan de carril) se dibujen bien
  al cruzarse con los otros: quién tapa a quién cambia con `acomodar_npc`.
* En cualquier otro mapa con gente caminando —Lashe City, el 11— que el orden
  de dibujado y los choques con los NPC sigan como antes.
* Las luces del mapa 11 y cualquier página que mire si el héroe está en una
  celda: van por `OP_CELL_TEST`.
