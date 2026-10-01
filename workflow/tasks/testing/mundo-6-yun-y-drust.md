---
name: "Mundo 6: Yun Town y Drust Camp"
description: "Lo opcional del mundo en release: Yun Town (67, 70 a 73) y Drust Camp (68, 103, 199 a 201); el cronómetro por alcance, el InputNumber y comparar contra más de 32767"
type: feature
assignee: taro
---

De taro, el 2026-10-01: "sumemos mapas primero". Con el cartucho en 8 MB y
la fase 1 de compresión, `release` usa 58 de 128 bancos. El plan es
`todo/el-mundo-y-lo-que-sigue.md`, hito 5: Yun Town (el cronómetro por
alcance, y el reparto del 2 para su capa de encima) y Drust Camp (comparar
contra más de 32767, el `InputNumber` del 68 ev10).

Sale de `main` en `2de10ea4`, mergeado `a0863e9e` (Mulita) al rato.

# Qué faltaba, contado

Con el compilador instrumentado (un `eprintln` en el `scan` con el último
comando de nivel 0 de cada página que no compila, en un `target/` del
scratchpad, no commiteado), sobre el request que arma `release` con los diez
mapas: **en Yun y Drust no compila una sola página**, el 68 ev10. Y no
compila por el `InputNumber`, antes de llegar a la comparación contra 35421:
la ROM no tenía `InputNumber`.

Lo que el plan contaba y ya no hacía falta:

* **El reparto del 2 para la capa de encima del 67** (163 tiles) ya está:
  lo trajo Sorbe (el hito 2). El 67 convierte sin tocar nada.
* **El cronómetro del 67** sí: con los dígitos en todos los mapas el
  conversor corta ("the timer doesn't fit: the map already uses the 8 sprite
  palettes"). Ver abajo.

Las condiciones de página de los mapas nuevos son de switches, de actor (68
ev7) y de ítem (71 y 103): las tres las evalúa la ROM.

# El cronómetro por alcance

Los dígitos del cronómetro ocupan lugar en una paleta de sprite, y hasta hoy
iban en **todos** los mapas de `release`. Ahora van en los que el cronómetro
puede estar corriendo: `timer_reach` en `tools/port/game_scan.py`, con las
páginas que compilan (la respuesta del `scan`).

Cada página se recorre en orden y sin mirar sus ramas, siguiendo el mapa en
que está: un arranque después de un `Teleport` es del destino —las latas del
311 lo arrancan después de saltar al 312—, y un `Teleport` después de una
parada no lo lleva —la salida del 312 lo para y después va al 313—. Una
página de un mapa al que llega el cronómetro empieza con él corriendo; un
`CallEvent` a un común recorre el común.

**Por mapa solo no alcanza**, medido: desde el 7, por las puertas, se llega a
los 96 mapas de `release` (Lashe City lleva al 64, el 64 al mundo). Ni con el
corte en los mapas que paran. Hace falta decir dónde no corre nunca, y es
una lista del proyecto: `[graphics] timer_never_runs_in = [66]`, con su
porqué (el de la mañana para al llegar al trabajo, días antes de salir de
Lashe; el del bosque en llamas para en la salida del 312). Con eso:

* llevan los dígitos 56 de los 105 mapas (el conversor lo imprime: "the
  timer's digits go in…"): Lashe City, el 64, el 164, el 312, el 133 (un
  mapa de prueba) y el 95, por el contador;
* no los llevan el mundo y todo lo que cuelga de él, el 17, el 18, el 310,
  el 311 y el 313, ni los demás mapas de prueba.

**El contador de Fortitude del 95 usa los mismos dígitos** (`OP_COUNTER`), y
la primera versión lo dejó sin ellos: lo cobró `test_contador`. Los mapas
que llaman a un común de `[events] counters` los llevan siempre; se miran por
la llamada y no por el bytecode porque el `scan` no conoce los contadores y
ahí la compila en el lugar.

La aproximación **sólo puede fallar dejando un mapa sin dígitos**, que
entonces no se ven: no rompe nada más.

# El `InputNumber`

Es el 68 ev10, la puerta de la tienda de Net:

    VOICE  "What's the password?"
    InputNumber: seis dígitos a la variable 143
    si la 143 es 35421: "Fine... come on in." y al 201

El otro del juego es el 278 ev8 (cuatro dígitos, contra 727), que no está en
ningún cartucho.

**En RM2k el número va en la ventana del mensaje**, en la línea de abajo de
su texto, y el mensaje no espera la A: `CommandShowMessage` mira el comando
siguiente, y si es un `InputNumber` y el mensaje deja una línea, lo mete
adentro. Así que el compilador junta los dos en un opcode: `OP_NUMBER`
(`0x38`), con la ranura de la variable, cuántos dígitos y la caja del
mensaje. Un `InputNumber` suelto, o después de un mensaje de cuatro líneas,
sigue sin compilar (no hay ninguno en el juego), y más de seis dígitos
tampoco.

En la ROM (`tools/runtime/number_input.s`): `op_number` abre la ventana del
mensaje como `op_message`, y cuando sus líneas están, la de los dígitos se
compone **con el mismo compositor del texto**, desde una línea en la RAM
lejana (`NUMBER_LINE`, `$7E25B0`) en vez del bloque de textos. Es
`pick_active` en `PICK_NUMBER`: la elección y el número comparten la ventana,
la página bloqueada y los bytes de `pick_`. El cursor es el de la elección,
un `>` en la columna de antes del dígito: no hay sprite ni dibujo.

Las teclas son las de `Window_NumberInput::Update`: arriba y abajo cambian el
dígito y dan la vuelta, izquierda y derecha mueven el cursor y dan la vuelta,
A entra el número, B no hace nada. Arranca en cero con el cursor en el último
dígito (`SetNumber(0)`, `ResetIndex`). La A refresca las páginas siempre,
como `Window_Message::InputNumber`.

Dos diferencias declaradas, en los comentarios: las teclas cuentan por
**flanco**, como la elección, y easyrpg las repite sostenidas; y el número
se guarda **saturado en 65535**, porque las variables son de dieciséis bits.

**Comparar contra 35421**: el compilador acepta en "igual" y "distinto" una
constante de 32768 a 65534, como los dieciséis bits de la variable —la ROM
compara las palabras, y ahí el signo no importa—. 65535 no, porque sería
también cualquier número saturado; y ninguna comparación de orden, que sería
con signo. Saturar es lo que hace que 100957 (35421 + 65536) no abra.

Confirmado contra el fuente de easyrpg (no está compilado acá):
`CommandShowMessage` (el `InputNumber` en la misma ventana si
`pm.NumLines() < 4`), `CommandInputNumber`, `Window_NumberInput::Update`,
`SetMaxDigits` y `ResetIndex`, y `Window_Message::InputNumber` (la variable,
`SetNeedRefresh(true)` y `SetNumber(0)`).

# Pruebas

Lo de Mulita entró al rato de empezar, así que hay casos nuevos posibles;
no hizo falta ninguno: las pruebas usan las páginas del juego.

* `rpgmaker/test_numero.py`: la puerta del 68. Los dígitos arrancan en cero
  con el cursor en el último, y las teclas dan la vuelta; 35421 abre y lleva
  al 201; 100957 queda en 65535 y no abre. **Las tres en rojo** con el
  compilador global (la página no compila: los dígitos no se abren), y en
  verde con el de esta rama.
* `abl/test_yun_y_drust.py`: el 67, el 68 y las minas (103) recién llegados,
  con golden y `celdas_mal_dibujadas` en cero; y las dos entradas del mundo
  (66 ev9 y ev11), caminando, que llevan al pueblo.
* Las tres del compilador en `compile.rs`: el número en la ventana del
  mensaje, los que no compilan, y la comparación como dieciséis bits.

`just pruebas`: 952 en verde, y **`test_musica_techos.py` en rojo**, que es lo
esperado: faltan los temas nuevos, `arc1_v2` y `piperdun`. No se corrió `just
techos`. `just -f tools/justfile test`: 39 en verde. `cargo test -p
rm2k-snes-events` en verde. `NO_CACHE=1 just cartuchos` da las tres ROMs
iguales que con caché (difieren los `.o` y `.dbg`, que llevan la fecha de los
`.inc` generados).

# Goldens

* **Nuevas**: `yun-67-llegada`, `drust-68-llegada` y `drust-103-llegada`.
* **Movidas**: las cinco del Hover-Tram (mapa 13: `tram-900`, `tram-1200`,
  `tram-viaje-10`, `-30` y `-60`), 183 pixeles —61 en la de 1200— de la fila
  de pasajeros de abajo. No es el cronómetro: el 13 lo sigue llevando, y para
  hacerle lugar baja a trece colores un personaje. Era Future3:5, el 53% de
  sus pixeles; desde que está también en la posada de Yun (72), el conversor
  elige uno que esté en menos mapas, Future3:1, el 25%, con un banco de
  poses propio.

En su commit, sólo de goldens; el antes y el después en
`/shared/capturas/2026-10-01-yun-y-drust/`, con la ventana de la clave.
**El merge espera a taro.**

# Espacio

Con `just espacio`. La base es `a0863e9e` (la ROM de `main`, `6809f47d…`).

    release        bancos   banco 0   banco 1    textos
    la base        58/128   245 B     3.828 B     94.417 B
    esta rama      62/128   101 B     3.423 B    101.513 B

BSS 128 B y ZEROPAGE 4 B en las dos. De los 144 bytes del banco 0, 42 son el
código (`op_number` y la entrada de `choice_tick`; medido en `test-special`,
que no cambia de mapas: 1.045 → 1.003) y unos 100 las tablas de los mapas
nuevos —ítems y temas, como dice el plan—. **El banco 0 queda en 101 bytes**:
las tablas de ítems al banco 1, que el plan pone en este hito, no se hicieron
(son diecinueve lecturas en el runtime); con Puma sumando tres mapas
encima, conviene medirlo al mergear.

# Lo que no está hecho

* **`test_musica_techos.py` falla** (ver arriba).
* **La música de antes baja un poco**: comparando las tasas del
  `conversor.log` contra el de la base, cuatro muestras de la base
  "limited by 311" bajan de ~19 a 17,6 kHz (COWBL66, METRO60, SBRS160A,
  SYBS233), una copia de CRASH60B a 22 kHz se va, y suben dos (SIDE_60,
  ATMOS60A). Es el paquete del 311 otra vez, ahora con las muestras nuevas
  de los temas de Yun y Drust en la base. No se cambió nada; lo decide taro
  escuchando.
* **Las tablas de ítems al banco 1** (ver "Espacio").
* **Un `InputNumber` suelto** o después de un mensaje de cuatro líneas no
  compila: el juego no tiene ninguno.

# Lo que no cubre `just pruebas`

* Las peleas de las minas (103) y del ring (199): los encuentros, sus
  fondos y los battlers nuevos (Slime2, bat, krawlie, spider, anima).
* Las tiendas de la armería (71) y de Net (201), y la posada (72).
* Las demás páginas de Yun y Drust: se cobra que compilan, no que hagan lo
  que tienen que hacer.
* Un `InputNumber` desde una página paralela (la espera, como la de un
  mensaje): el juego no lo hace.

# Al mergear

Instalar `events` (`just -f tools/justfile install events`). `cartridge` no
cambió: arma `number_input.s` desde el runtime del checkout. Los `.py` sólo
cambiaron de contenido.

# Qué tiene que probar taro

* Entrar a Yun Town y a Drust Camp desde el mundo, caminar, hablar, la
  armería, la posada, la casa del alcalde y la fiambrería.
* La puerta de la tienda de Net, en Drust: la ventana de los dígitos, el
  cursor (un `>`), y la clave (35421) que abre; un número equivocado te
  devuelve un paso.
* Las minas: los encuentros y sus peleas.
* Que el cronómetro de la mañana se siga viendo en Lashe City, y el del
  bosque en llamas en el 312.
* Escuchar los temas que bajan (ver arriba).
