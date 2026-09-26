---
name: "Juntar release y test-main"
description: "Un solo cartucho que se juega y que corre la tanda: medido lo que cuesta, y el espacio que manda"
type: refactor
---

# Qué

Que `release` y `test-main` sean un solo cartucho: el que se entrega, con
título y cronómetro, que además lleva todos los mapas y los casos de
`pruebas/casos/`, apagados en la partida de verdad. `test-special` queda como
está.

Lo que sigue se midió el 2026-09-25 sobre `d118bc8`, armando en un worktree un
`release` con `--grupo 10`, `--map-id 4` y los `MAPAS` de `cartuchos.py`, con
los `--grafico-de-prueba` y con todos los casos, y corriendo la tanda entera
con `PRUEBAS = RELEASE`. Los números son de ese día: el que retome esto los
vuelve a medir, no los copia (el método está al final).

# Qué diferencia es de fondo y cuál es configuración

| Diferencia | Qué es | Lo medido |
|---|---|---|
| `--grupo 10` | nada | Es el grupo por omisión (`system.json`: `party: [10]`): los dos cartuchos arrancan con el 10, y el 11 lo pone el caso `grupo-11`. |
| Título | configuración del arnés | Con el título pasado por "Begin the Story" antes de elegir el caso, **cero goldens se mueven**. Lo que pide es que `tanda.partida` pase `titulo=EMPEZAR` en el cartucho con título, y que `reiniciar()` vuelva por "Resume the Story" (sin eso caen 13 pruebas de "viaja en la partida", que eligen "Begin" al resetear y arrancan de cero). Y las dos de `test_game_over.py` que esperan el arranque después del GameOver: con título la ROM vuelve **al título**, que es lo que hace RM2k, así que la prueba tiene que pasarlo. |
| Cronómetro | configuración, más **un error de verdad** | 14 goldens se mueven con el cronómetro en todos los mapas (el comentario de `snes_convert.py` decía quince, en el 9f). 9 son recuantizaciones chicas —de 2 a 166 pixeles: `gemelo-20`, `gemelo-ruta-20`, `gemelo-fija-20`, `tram-200`, `tram-viaje-10`, `autos9-2`, `npc-diagonal-10`, `tram-26`, `puerta-8-9-120`—, porque los colores de los dígitos entran en el reparto de paletas. Las otras **5 son un error**: `sacudir-60`, `cerrar-400`, `cerrar-right-400`, `autocierre-63` y `autocierre-3-185`, la puerta del mapa 7 sin teñir en una pantalla teñida. Ver abajo. |
| Mapa de arranque (6 contra 4) | de fondo, pero barato | Los casos viven en el evento 0 del mapa de arranque. Los 24 de `test-main` que no empiezan con un `Teleport` corrían en el 6, y en el unido corren en el 4: 27 goldens se mueven, de 15 a 89%. **Con un `Teleport` al 6, (50,50) —la celda donde caía el héroe—, delante de cada uno, vuelven las 27 a cero**: el arnés ya cuenta desde la llegada. Son `anclada`, `animacion`, `animacion-dibujo`, `atravesar-sin-paso`, `grupo-11`, `pan*`, `rama-grupo*`, `ruta*`, `sacudir-fuerte`, `sacudir-lluvia`, `salto`, `switch-171`, `tropa-talan-aura`, `ventana-6`, `vuelta-ventana`. La cinemática del 4 no se mete: ninguno de los ~150 casos con `Teleport` se movió. |
| Gráficos de prueba | configuración | Van en los mapas donde corre un caso, y eso incluye mapas que el recorrido camina: aun así **ninguna golden de `release` se movió** —recorrido, título, escenas, pila, MSU-1, cores—. |
| Casos en la ROM que se juega | de fondo, chico | Ver la sección siguiente. |
| Mapas de más (52, 70, 73, 74, 119, 121, 133, 255, 261, 269, 348) | de fondo: espacio y parches | 282 KB en el cartucho, y `test_parches` exige que todo lo que entra en el jugable esté versionado. |

## Los casos en la ROM que se juega

La página 0 **no pide nada** y corre siempre, en el mapa de arranque, al
empezar; la k pide `VARIABLE_DE_CASO >= k`, y el juego no toca la 1000. Así
que el caso 0 no garantiza que no corran: **es el que corre**. Hoy es
`grupo-11`, que mete a Kersh y rompe la apertura. Para apagarlos alcanza con
que `PRIMERO` sea `nada`, que ya existe: la partida corre entonces una página
que sólo prende el switch 1023 y se apaga, y las demás no corren nunca. Medido:
con `PRIMERO = "nada"` las pruebas que juegan pasan todas sobre el unido.

Lo que queda, y no es gratis:

* **La ROM que taro juega lleva las páginas de prueba y los mapas de prueba**,
  inalcanzables pero adentro: 3,75 MB contra 3,01 MB de `release` hoy.
* **Las variables de los casos entran en el índice** —`datos.ranuras_de_variable`
  lo explica—, así que la disposición de la partida guardada del juego
  depende de qué casos haya. Un caso nuevo que nombre una variable nueva
  corre las ranuras de las que vienen detrás.
* La partida guardada lleva el switch 1023 prendido.

## El error que destapa el cronómetro

`tinte.s`, al final de `tenir`, vuelve a subir la paleta del cronómetro sin
teñir, y el comentario dice por qué: "los dígitos tienen una paleta para ellos
solos". Era cierto cuando se escribió (`5be4ade`, 2026-09-04); desde
`034d721` (2026-09-07) los dígitos **comparten** paleta con un personaje que
tenga lugar, así que ese personaje se queda sin teñir. En la tanda se ve en la
puerta del mapa 7. **Pasa hoy en `release`**, que lleva el cronómetro en todos
los mapas: en cualquier mapa teñido donde un personaje comparta la paleta de
los dígitos. Va antes que regenerar las 9 goldens restantes.

# Fuera de la tanda

* `just entregar` y `just video` leen `rom/build/release/` y no se rompen: el
  unido sale en el mismo lugar y con el mismo nombre. `test_msu` pasa.
* `test_parches` cae: los once mapas de prueba entran en el jugable sin parche
  versionado. O se versionan —`just parches` los copiaría a `parches/`—, o
  `parches.revisar` aprende qué mapas son de prueba. Es una decisión.
* **Los parches del directorio de build no se limpian**: al volver a armar
  `release` sin los mapas de prueba, `rom/build/release/parches/auto/mapas/`
  seguía teniendo el `0052.toml` y los demás, y `test_parches` cayó por eso.
  Cualquier cartucho que pierda un mapa lo va a tener; conviene arreglarlo con
  esto.
* `test_protocolo` y `test_ensamblar` se parametrizan por cartucho: dos casos
  menos.
* Nombran `test-main`: `cartuchos.py` (5), `pruebas/README.md` (3), `justfile`
  (2), `test_guardar_save_point.py` (1, con `en="test-main"`),
  `wishlist/la-carrera-en-release.md` (2). `conftest.py` afirma que `release`
  no lleva casos. Y `donde_esta` depende del orden del diccionario: con
  `test-special` primero, `parado-tapado` —que está en los dos— se corrió en
  el chico y movió su golden.

# Espacio

| | `release` | `test-main` | unido |
|---|---|---|---|
| Banco 0 libre (de 32.704) | 2.320 | 1.950 | 1.946 |
| `BSS` libre (de 7.808) | 108 | 108 | 108 |
| `ZEROPAGE` libre (de 256) | 3 | 3 | 3 |
| `FAR` libre (de 32.768) | 11.179 | 5.489 | 5.489 |
| Cartucho usado | 72% (98 bancos) | 87,7% (120) | 89,6% (124) |

`test-special`: banco 0 2.644, 27,5% del cartucho.

**Lo que manda no es el banco 0: es el cartucho.** `test-main` ya está en
87,7%, y `el-cartucho-se-queda-en-4-mb.md` dice que se revisa al 85-90%. Juntar
casi no lo cambia (+1,9 puntos: el título y el cronómetro), porque `test-main`
ya lleva todos los mapas de `release`; lo que cambia es que ese 89,6% pasa a
ser **la ROM que se entrega**, en vez del 72% de hoy.

## Qué ocupa cada región

**Banco 0**: 29.467 B son `CODE` —el 90%— y el conversor emite ahí sólo
~1.300 B de `TABLAS`. **No crece por mapa**: la diferencia entre `release` y
`test-main`, con once mapas de más, son 370 B, y son todos ítems (6 B cada uno:
`item_id`, `item_precio`, `item_tipo`, `item_uso`), temas (4 B: `tema_lo/hi/bk/msu`),
caras (1 B) y 6 B de `ranura_bloque_*`. Las tablas por mapa viven en sus
bancos. Si hace falta lugar, lo que hay que mover es código; el más pesado:
`paginas_de_eventos.s` 2.295, `oam.s` 1.261, `rutas_de_eventos.s` 1.235,
`menu.s` 1.188, `paquete_de_audio.s` 1.157, `tinte.s` 1.131, `items.s` 1.044.
Los candidatos naturales son pantallas que no corren con el mapa, como ya se
hizo con la tienda y el equipo en `FAR`: `menu.s`, `items.s`, `ranuras.s`
(884), `titulo.s` (422), `pantallas_de_texto.s` (264), unos 3,8 KB.

**`FAR`**: 10.729 B son tablas del conversor —`mensajes_tropa` 5.065,
`tropa_codigo` 4.541, `tpag_*` 1.000— y **crecen con las tropas** que pidan los
mapas; el resto es el código de la pelea, la tienda, el equipo y el nivel. En
el unido le quedan 5.489: las peleas de Lashe City van a comer de ahí.

**`BSS` y `ZEROPAGE`**: no dependen de los mapas, dependen del código, y están
al tope: 3 bytes de página cero. Lo grande de `BSS` es `texto_buf` 1.968,
`npc_buf` 1.664 (`NPC_MAX × NPC_STRIDE`), `oam`, `cgram_sombra` y `pal_buf` 512
cada uno, `ev_pos_buf` 480; el lugar para sacarlos es `ram_lejana`.

**El cartucho** (unido, 3,76 MB usados): `tema_stream` 789 KB (21%),
`anim_batalla` 561 KB (15%), `map_tiles` 470 KB (12,5%), `sprite_poses`
375 KB (10%), `sprite_tiles` 295 KB, `map_celdas` 285 KB, `muestra` 269 KB,
`fondo` 98 KB, `battler` 77 KB, `mensajes` 66 KB. Además hay 312 KB sueltos
adentro de bancos a medio llenar, que sólo sirven para piezas chicas.

**Cuánto pesa un mapa**: sumando lo que lleva el sufijo del mapa (tiles,
celdas, bloques, sprites, poses, eventos, NPCs), los 29 del juego dan 39,5 KB
de media —de 16 a 69 KB—, sin contar la música ni las animaciones de batalla
nuevas que traigan. En el unido quedan ~436 KB: **unos diez mapas medios**, y
menos si traen temas (~25 KB cada uno) o animaciones. Los once mapas de prueba
pesan 282 KB juntos; saber qué prueba necesita cada uno es la otra palanca.

# Tiempo

| | tres cartuchos (hoy) | dos (unido + `test-special`) |
|---|---|---|
| `cartuchos`, caché en frío | 177 s (137,7 + 12,7 + 27,0) | 149 s (136,8 + 12,4) |
| `cartuchos`, caché caliente, todo rearmado | 114 s (76,4 + 12,4 + 24,9) | 97 s (83,9 + 12,9) |
| pytest de `just pruebas` | 61 s, 623 casos | 57 s, 621 |

Las pistas de MSU-1 suman 71 s en frío a cualquiera de los dos. Tocar
`rom/src/` rearma todos, así que la vuelta típica ahorra unos 17 s.

# Recomendación

**Juntar vale la pena, con la forma "`release` es el unido"**: un cartucho con
título y cronómetro, `--map-id 4`, todos los mapas, los casos con `PRIMERO =
"nada"`, y el arnés pasando el título solo. Lo que cuesta, medido:

1. arreglar el tinte de la paleta compartida del cronómetro (un error de hoy,
   con o sin juntar);
2. un `Teleport` al 6 delante de 24 casos —cero goldens—;
3. en el arnés, el título automático y el reset por "Resume" —unas diez
   líneas—, y las dos pruebas del GameOver pasando el título;
4. regenerar a propósito las 9 goldens que recuantiza el cronómetro;
5. decidir qué hace `test_parches` con los mapas de prueba, y limpiar los
   parches viejos del build;
6. renombrar lo que dice `test-main`.

**Antes de Lashe City**, porque el costo en goldens es chico —14, y 5 de ésas
son un error que hay que arreglar igual— y crece con cada mapa que se agregue
sobre dos configuraciones distintas. Pero **el espacio va antes que los dos**:
`test-main` ya está en 87,7% y cada mapa nuevo entra en todos los cartuchos,
así que Lashe City choca contra los 4 MB con o sin juntar. Juntar sólo hace
que el choque se vea en la ROM que se entrega. El orden que sale de los
números es: el error del tinte, el espacio (dónde está el peso: música,
animaciones, tiles; y qué mapas de prueba se pueden sacar), juntar, Lashe City.

**La variante intermedia** —`test-main` con la misma configuración que
`release` pero siguiendo aparte— cuesta casi lo mismo: el cronómetro (14
goldens) y el título (arnés, GameOver), sin el `Teleport` si sigue arrancando
en el 6. Deja limpia la ROM que se entrega (72% y sin páginas de prueba) y
mantiene los tres cartuchos. Tiene sentido **sólo si se decide que la ROM que
se juega no puede llevar los mapas y las páginas de prueba**; si eso no
importa, no ahorra nada que valga dos cartuchos.

# Cómo se midió

El espacio sale del `.sym`/`.dbg` de `ld65`: los tamaños de los segmentos, y
lo que ocupa cada etiqueta sumando los `span` que tienen línea de fuente. El
libre de `FAR` es el relleno del `.align` que cierra `cabecera.s`. El banco 0
coincide con el método del `.res` de AGENTS.md. Los tiempos son de un worktree
con `rom/build/` vacío (frío) o con el caché lleno y los cartuchos borrados
(caliente), con otro agente usando CPU a la vez.

# Lo hecho (2026-09-25, en curso)

taro decidió juntar con la forma recomendada: `release` pasa a ser el unido y
`test-main` deja de existir. `test-special` queda.

Antes de empezar, sobre `cfb100e` (con el tinte ya arreglado y el respaldo
liviano adentro): `just cartuchos` en frío 266 s —`test-main` 154, 
`test-special` 13, `release` 28 y las pistas de MSU-1 71—, y `just pruebas`
632 casos en verde.

1. El `Teleport` al 6 delante de los 24 casos que corrían en el mapa de
   arranque: commit aparte, 632 en verde, ninguna golden se movió.
