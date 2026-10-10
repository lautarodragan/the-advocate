---
name: "El común 35 y la música de la radio"
description: "Lo que dejó abierto Yarará en los sistemas de batalla: ResetAfterBattles, para que la invocación devuelva a Lerle, y los tres temas de Play Radio en la pelea"
type: feature
assignee: taro
---

De taro, el 2026-09-30, al contestar sobre `testing/eventos-de-tropa-en-la-pelea.md`
(Yarará):

- **El común 35 (`ResetAfterBattles`).** Sin él, la invocación queda en el
  grupo en lugar de Lerle después de la pelea. Sus comandos ya compilan; lo
  que lo traba es que las variables que sólo nombra un común no tienen ranura
  en la partida, y sumarlas corre las de las demás. taro: romper la
  compatibilidad de las partidas **nunca es un problema**.
- **La música de `Play Radio` (809).** Su `PlayBGM` hoy se acepta y no se
  hace. taro: con la calidad tan baja como haga falta en la ROM y tan alta
  como se pueda en el `.msu`; si separarlas es más difícil que bajarle la
  calidad al tema de batalla u otros, se baja y listo.

Ver `decisiones/primero-el-juego-entero-despues-la-calidad.md`.

Sale de `main` en el commit que lanza la tarea. Ahí: `NO_CACHE=1 just
cartuchos` da `abl.sfc` `e20182d1bd905de7…`; `just pruebas` 893,
`just -f tools/justfile test` 46.

# El común 35 (Aguará, 2026-09-30)

**Cómo corre en RM2k**, confirmado en el LDB y en los mapas: no hay nada
especial después de la pelea. 162 de las 300 tropas traen una página de
turno 0 que prende el 498 al abrir la pelea (en EasyRPG, `CheckTurns` con
0 y 0 es el turno 0: corre antes de las primeras órdenes). Y 74 mapas —82
páginas— traen la automática `AfterBattleMint`, con el 498 como condición,
que sólo hace `CallEvent` al común 35; al volver al mapa, la automática
corre y el común apaga el 498 al final. En `release` son 16 de sus mapas,
entre ellos el 60 del caso `pelea-invocacion`.

**Lo que hace**, además de devolver a Lerle: cura a las 18 invocaciones
(36 a 53), saca a la que esté y agrega a Lerle (26); apaga los switches de
Talan y le rearma los HP y SP desde las variables 134 a 138; le saca a
Emily (25) el accesorio y las cuatro cintas (385 a 388); y le rearma a AG7
(18) las habilidades de sus piezas.

**El arreglo**: el barrido de variables (`variables`, en `indices.rs` de
`rm2k-snes-events`) mira también los comunes. Las del juego pasaron de 132
a 169 y la más alta, de 201 a 204. Corre las ranuras: las partidas de los
cartuchos de antes no cargan bien en éste, y está aprobado.

**La prueba**: `test_despues_de_la_pelea_lerle_vuelve_al_grupo`, en
`test_sistemas_de_tropa.py`. **En rojo antes del arreglo**, medido: el 498
quedaba prendido después de la pelea. `test_la_invocacion_cambia_...`, que
miraba el grupo recién cerrada la pelea, ahora apaga el 498 antes de
cerrar, porque si no el común ya corrió cuando mira.

**El costo**: el común compila en el lugar de cada `CallEvent`, así que va
copiado en cada mapa con encuentros. `just espacio` en `release`: bancos de
datos de 116 a 117 usados (7 libres), huecos de 8.799 a 7.678 B. El banco 0
y el banco 1 no se movieron (13 B y 5.054 B). Es deuda: un cuerpo
compartido lo pagaría una sola vez.

**Ninguna golden se movió**: la tanda dio 893 en verde y la de las ranuras
en rojo, que es la que cuenta las variables (actualizada).

# La radio (Aguará, 2026-09-30)

**Qué pone**: la página del 809 prende un tema según la cinta —806
`dd2shad2`, 807 `patchb`, 808 el de Ryan Bury— antes de mirar la
variable, así que suena en los tres caminos.

**Lo que se probó primero, y se descartó**: dejar que los tres temas entren
al paquete de la pelea con el de batalla. El de batalla bajaba de ~11,5 a
**~4,5 kHz** en sus muestras (NYLON48A, STLGT57B, DSTGT48…), y el banco
entero se reacomodaba.

**Lo que quedó**: el compilador de eventos hace el `PlayBGM` de una página
de tropa y anota sus temas como `troop_songs`; el plan de `rm2k-snes-audio`
(`cartridge::plan`) los pone **aparte** en el paquete de la pelea, igual que
los `apart_themes` de un mapa: los sube su `PlayBGM` solos con los efectos
del paquete. Así el tema de batalla no les hace lugar, y separarlos de la
calidad del `.msu` no costó nada: **con el MSU-1 los tres tienen su pista**
(38, 142 y 161), porque la numeración sale de `Music/` y el conversor las
renderizó solo.

**La deuda de calidad**, medida comparando `conversor.log` de `release`
antes y después (script descartable, por muestra y por tema): tres temas
más dejan menos entradas del directorio de muestras para copias, y muestras
que otros temas tenían en su propia copia pasan a la del peor paquete. El
tema de batalla: su muestra más baja pasa de 11,5 a **10,0 kHz**
(MMBAS40, 13,3 → 10,0), aunque otras suben un poco (NYLON48A 11,5 → 12,2).
Los tres de la radio quedan entre **6,8 y ~10,5 kHz**. Y bajan, en alguna
muestra, 34 temas más; los peores:

    Astpgmarch                11 muestras; OBOE_69A 13,6 → 6,8 kHz
    lufsorr, iknow, prepara   OBOE_69A 20,4 → 6,8 kHz
    hzstream                  OCARI72A 16,1 → 8,0 kHz
    rshinld, Lunar_Pyramid    STRNG71B 22,1 → 10,6 kHz
    cd2, Story Music, vswar   golpes de batería 22,0 → 10,6 kHz
    3D-Galax, wb3mlair        MMBAS40 16,7 → 10,0 kHz
    TF3_1_awe, escape_newyork golpes 14,3 → 10,6 kHz

Se ajusta cuando el juego entero se pueda jugar
(`decisiones/primero-el-juego-entero-despues-la-calidad.md`). Para
escuchar: `/shared/audio/2026-09-30-radio/`, los tres temas y el de batalla
por el SPC700.

**La prueba**: `test_la_radio_pone_el_tema_de_la_cinta`, en
`test_sistemas_de_tropa.py`, una por cinta: `song_current` es el tema, la
música no está callada y sus muestras están en la ARAM, como
`test_tema_del_mapa.py`. **En rojo sin el arreglo**, medido con el
compilador de `main`: el cartucho no llevaba los temas.

**El banco 0**: los tres temas le costaban 4 B cada uno —`song_lo`,
`song_hi`, `song_bk` y `song_msu`— y lo dejaban con **1 B** en `release`.
Esas cuatro tablas pasaron a RODATA y se leen con `f:` (commit aparte).

# Cómo quedó (sobre `main` en dc5810b7, con Tatú)

Commits: e0100423 (el común 35), d6f3342d (las tablas de los temas fuera
del banco 0), 92c3f95f (la radio) y el merge de `main`.

`NO_CACHE=1 just cartuchos` y `just cartuchos` con caché dan los 1035
archivos de `rom/build/` iguales. `abl.sfc` `30ae28d9cff39cd3…`.

`just espacio`, `release`: bancos de datos **120 de 124, 4 libres** (116
antes del común y la radio: uno es el común copiado en cada mapa con
encuentros, casi tres son los streams de los tres temas); huecos 21.391 B;
**banco 0 182 B** (14 en `main`); banco 1 4.697 B.

**Las tandas**: `just pruebas` da **897 en verde y 1 en rojo**,
`test_musica_techos.py`: le faltan en la tabla los tres temas de la radio.
**No se corrió `just techos`.** `just -f tools/justfile test`: 46.
`cargo test -p rm2k-snes-events -p rm2k-snes-audio` en verde.
`test_cores.py` en verde. **Ninguna golden se movió.**

**Al mergear, instalar** `just -f tools/justfile install events
rm2k-snes-audio`. Cambió el runtime (`music.s`, `msu1.s`), que no pide
nada. Ningún `.py` se renombró ni se agregó.

**Números usados**: ninguno —ni opcodes, ni RAM lejana, ni tuplas de
prueba, ni casos nuevos—.

# Qué tiene que probar taro

- **Una invocación de Lerle**: después de la pelea, Lerle vuelve al grupo
  y la invocación sale, curada. Al volver al mapa corre el común 35 entero:
  también le saca a Emily las cintas y el accesorio, y a Talan le rearma
  los HP y SP; eso no lo mira ninguna prueba.
- **`Play Radio` de Emily**, con cada cinta: suena su tema en la pelea, y
  con el MSU-1 entero. Y de oído: el tema de batalla y los de la lista de
  arriba, por el SPC700.
