---
name: "Efectos de calidad con MSU-1"
description: "Con MSU-1, los efectos a la tasa que entre, enteros, desde el .msu, y las ocho voces del DSP cuando el SPC700 no toca música"
type: feature
assignee: taro
---

# Qué

Pedido de taro, el 2026-09-26: **cuando la música va por MSU-1, los efectos
de sonido tienen que sonar a su calidad máxima, con su longitud completa, y
con todas las voces posibles.** Sin MSU-1 no cambia nada.

Absorbe el punto 1 de `todo/mas-voces-para-los-efectos.md` (con MSU-1, todas
las voces para efectos) y el plan B de
`testing/con-msu-1-no-se-suben-las-muestras-del-tema.md` ("los efectos de
calidad desde el `.msu`").

# El diseño, con sus números

Medido sobre `release` en `b521ffb` y otra vez después de mergear `d44b906`
—los efectos enteros del otro agente—. Los números de abajo son de ese
momento: **las tasas de cada paquete las imprime el conversor** ("efectos de
calidad del paquete N" en `conversor.log`), y cambian con los temas y los
efectos de cada paquete.

## Qué ARAM hay: la calidad máxima no entra en los paquetes grandes

Con MSU-1 las muestras de los temas con pista no se suben, así que para los
efectos hay la ARAM entera: 63.419 B de muestras, menos el margen de 1 KB
que la música también deja. Los 92 efectos de `release` enteros a la tasa de
sus WAV (22.050 Hz, salvo `clap` a 11.025) son **1.142.208 B**; el cartucho
lleva 420.399. Por paquete:

| paquete | efectos | enteros a 22 kHz | ¿entra? |
|---|---:|---:|---|
| 3 | 20 | 291 KB | no, ni cerca: le entra un quinto |
| 2 | 18 | 201 KB | no |
| 19, 11, pelea, 1, 32, 261, 26, 9, 7 | 5–11 | 66–90 KB | no, por poco |
| 20, 52 | 7, 3 | 65, 46 KB | casi |
| los otros diecisiete con efectos | 1–8 | 6–60 KB | sí |

O sea que "calidad máxima y enteros" entra en la mitad de los paquetes, y en
el 3 y el 2 hay que elegir entre la tasa y el largo. **Se eligió el largo**,
que es lo que taro pidió primero: todos los efectos van enteros, y la tasa es
la más alta que entra.

Lo único que daría calidad máxima en el 3 es subir cada efecto cuando se
pide, y no se puede: el puerto del SPC700 sube unos 41 KB por segundo con la
CPU entera dedicada (1,45 cuadros por KB, medido en el paso 6 de la música),
así que un efecto de 17 KB congelaría el juego un tercio de segundo cada vez;
y tocarlo mientras se sube —un búfer circular— se comería un tercio de la CPU
por efecto sonando. No se intentó.

## Cómo se reparte: una versión por paquete

Cada paquete tiene su versión de cada efecto, a la tasa que le entra: una
sola para todos sus efectos —de `TASAS`, en `tools/audio/efectos_msu.py`—,
con un piso por efecto: **si el cartucho ya lo lleva entero, no puede quedar
peor que sin MSU-1**. Uno que el cartucho lleva recortado puede quedar a
menos tasa que allá, pero entero.

La alternativa era una versión por efecto, la que le entra a su peor
paquete, que le ahorra a la ROM saber qué versión está en la ARAM. Medido:
**48 de los 159 pares (paquete, efecto) perdían**, casi todos por compartir
efectos con el mapa 3, que dejaba a 4,7 kHz efectos del 11, el 19, el 20, el
23, el 32, el 33, el 52, el 74 y el 133 que tienen lugar de sobra. Lo que
cuesta la versión por paquete es que la ROM no guarda qué versión quedó en la
ARAM —no hay RAM: son 32 bytes para todo esto—, así que **con el `.msu` los
efectos de cada paquete se vuelven a subir siempre**, aunque ya estuvieran.

Lo que quedó en `release` después de mergear `d44b906`: a 22.050 Hz los
paquetes 8, 10, 12, 13, 14, 16, 17, 18, 21, 23, 28, 30, 33, 74, 133, 255 y
269; a 14–20 kHz el 1, 7, 9, 11, 19, 20, 26, 32, 52 y la pelea; **el 2 a 6,5
kHz, el 3 a 6 y 4 kHz** —los nueve que el cartucho ya lleva enteros a 6, los
once que lleva recortados a 4—, y el 261 y el 121 bajos porque sus temas no
tienen pista y ocupan la ARAM. Cuando todos los temas tengan pista
(`todo/todos-los-temas-tienen-pista-de-msu-1.md`) esos dos suben solos.

## De dónde salen: el `.msu`

Las dos opciones del encargo:

* **(a) en el `.msu`**, subidos a la ARAM por el puerto de datos, con la firma
  y la caída a la ROM de los fondos de batalla. Es la elegida.
* **(b) en la ROM.** Las versiones de todos los paquetes son **1,25 MB**
  —lo que ocupan en el `.msu`—, y a `release` le quedan unos 1,7 MB libres de
  sus 4 (medido contando el relleno del final de cada banco; los 4 MB son el
  tope de LoROM). Entraría, pero serían 1,25 MB de cartucho que sin MSU-1 no
  sirven para nada, y dejarían a la ROM a medio mega del techo.

**El tiempo de subida es el mismo por byte en los dos**: el cuello es el
puerto del SPC700, no de dónde sale el byte. Lo que el `.msu` agrega son las
búsquedas, y se hacen **una por paquete**: cada paquete tiene sus efectos
contiguos en el `.msu`, en orden de SRCN, que es el orden en que
`subir_colocadas` los sube, así que la ROM busca el primero y lee de corrido
(un efecto que está en dos paquetes va dos veces; el archivo no tiene tope).
En Mednafen una búsqueda son uno o dos cuadros; en snes9x y bsnes, nada; en
el FX Pak, leer la tarjeta —no medido—.

**Si el `.msu` no coincide** —de otro build, vacío, o sin MSU-1— la firma no
está y todo sale de la ROM como siempre (`MSU_SE` en 2). Se mira una vez por
encendido, en la primera carga de paquete. Si una búsqueda no llega a tiempo,
ese efecto no se sube y no suena: la ROM no puede caer a su versión, que
tiene otra altura. Ningún emulador de acá tarda tanto; ese camino no lo corre
ninguna prueba.

## Cuántas voces: las ocho, cuando el SPC700 no toca música

La 7 y la 6 siguen siendo las de siempre, con su estado y su sombra. Las 0 a
5 son de los efectos **mientras hay MSU-1 y `music_apagada` está prendido**
—suena una pista, o nada—. La regla para el efecto nuevo, en
`sonido_tocar`:

1. la 7 o la 6 si ya tocan esa misma muestra (la lluvia);
2. una de las 0 a 5 que ya toque esa muestra;
3. la 7 o la 6 si está libre;
4. una de las 0 a 5 libre;
5. si no, lo de siempre entre la 7 y la 6: la que termina antes.

La 7 y la 6 primero porque son las que sobreviven a un cambio de tema.

Lo que había que cuidar:

* **Un tema sin pista en el mismo momento**, o una pista que falta
  (`MSU_FALTA`): el tema suena por el SPC700, `music_apagada` está en cero y
  las 0 a 5 son de la música. No se toman.
* **Un tema que pasa al SPC700 a mitad de un efecto** en una de las 0 a 5:
  el efecto sigue. Lo que la música le escribe a esa voz queda en
  `MUS_SOMBRA` y no se manda —`dsp_musica`, con una tabla que da el bit de
  la voz de cada registro—, sus KON y KOF salen sin ese bit, y al terminar el
  efecto se le devuelve desde `MUS_SOMBRA`. Es lo que ya pasaba con la 7 y la
  6, con la sombra de la música en vez de una propia. **Esto no lo corre
  ninguna prueba**: haría falta un tema sin pista que arranque mientras
  suenan tres efectos.
* **Un tema que pasa al MSU-1** a mitad de un efecto: `music_start` escribe
  KOF en $FF, que corta todos los efectos, los de la 7 y la 6 incluidos. Es
  de antes, y no se tocó.
* **La pelea**: su tema tiene pista, así que con MSU-1 sus efectos tienen las
  ocho voces y su paquete su versión de calidad.

## La RAM y el banco 0

`$7E78B0-$7E78CF`, la que se repartió para esto, está entera:
`ram_lejana.s`. El estado de las 0 a 5 guarda el índice del sonido y no la
copia de la fila, y la interrupción la lee al arrancarlo.

El código vive en el banco 1 (`rom/src/efectos_con_msu.s`), con `jsl` desde
los ganchos. **Banco 0: 93 bytes**, medidos con `.res` en `release` —de 619
libres a 526— y en `test-special` —de 1.317 a 1.224—.

# Lo que cuesta

**Cargas más largas con el `.msu`**, porque la ARAM se llena de efectos y se
suben siempre. Cuadros con el lazo quieto, en snes9x, `release` con MSU-1 y
todas las pistas, desde el 5, con un `.msu` vacío (los efectos de la ROM,
que es lo de antes) y con el del cartucho:

| salto | efectos de la ROM | del `.msu` |
|---|---:|---:|
| al 2 | 73 | 107 |
| al 3 | 71 | 107 |
| al 26 | 80 | 100 |
| al 8 | 47 | 108 |
| al 10 | 21 | 51 |
| entrar a la pelea (hasta el menú) | 113 | 161 |

Lo que se puede tocar si pesa: el techo de `TASAS` —con 16 kHz de tope el
8 bajaría a unos 80 cuadros— o volver a la versión por efecto.

**Sin MSU-1, el audio sale con los mismos pares al DSP pero corrido algunos
ciclos**: los ganchos agregan instrucciones adentro de `irq_musica` (un
`lda` y un salto por escritura de la música, dos `jsl` por cuadro). Medido
contra `main` en 6.000 cuadros del título y la apertura sin MSU-1: la
envolvente correlaciona en 0,99978 y 8 de 6.193 cuadros difieren en más de un
5%, alrededor del cambio del título a la partida; las muestras sueltas no
son iguales byte a byte.

# Cómo se prueba

`pruebas/abl/test_msu_efectos.py`, con MSU-1 y todas las pistas sobre una
copia de `release`, y dos casos nuevos:

* `efecto-de-calidad`: `Success2` en el mapa 10. Con el `.msu` del cartucho
  arranca con la altura de 22.050 Hz, su envolvente sigue la del WAV y
  termina callada —el recortado repite su último tramo hasta el final—, y
  con las muestras del `.msu` cambiadas y la firma intacta suena distinto.
* el mismo caso con un `.msu` de otro build (firma recalculada) suena igual
  que con uno vacío, con la fila de `sonido_tabla`.
* `tres-efectos`: `Glass`, `Flash3` y `Earth4` en el mismo cuadro, en el 3
  con `evilrhys` por la pista: la 7, la 6 y una de las 0 a 5, tres muestras
  distintas, y la misma corrida con las 0 a 5 apagadas justo antes suena
  distinto.

**Vistas fallar**, rearmando `release` con una pieza apagada cada vez:

* sin las voces 0 a 5 ni el `.msu`: fallan la de calidad (`MSU_SE` en 2) y la
  de tres efectos (ninguna voz de las 0 a 5);
* aceptando cualquier `.msu` sin mirar la firma: falla la de otro build;
* subiendo de la ROM con la altura de la ROM: falla la de calidad (altura
  768 contra 2.822);
* subiendo de la ROM con la altura del `.msu`: falla la de calidad (la
  envolvente correlaciona 0,23 con la del WAV).

`test_msu_datos.py` cuenta ahora las entradas de fondos con `MSU_FONDOS_N`:
el `.msu` lleva los efectos detrás.

Corrido sobre la rama con `d44b906` mergeado: `just cartuchos`, `just
pruebas` en verde y `test_cores.py` dos veces; y `release` armado con
`SIN_CACHE=1` sale con el `.sfc` y el `.msu` iguales byte por byte, porque
las versiones de calidad pasan por el caché del BRR.

**Lo que no corre ninguna prueba**: la espera de la búsqueda en el `.msu` y
su corte por tope (como la de los fondos), y un tema que pasa al SPC700 con
un efecto sonando en las voces 0 a 5.

# Para taro

En el FX Pak, con las pistas y el `abl.msu` del build al lado:

* **el tiempo de las cargas**, sobre todo entrar al 2, al 3, al 8 y a la
  pelea: acá cada una es una búsqueda en la tarjeta y un paquete lleno; si se
  sienten largas, se baja el techo de la tasa;
* que los efectos suenen, y enteros: el trueno y la lluvia de la apertura,
  `Sword3` en el 26, los de la pelea, los del 3;
* la escena de `evilrhys` del mapa 3, que ahora puede tocar tres efectos a
  la vez.

Y escuchar `/shared/audio/2026-09-26-efectos-con-msu/`, con su `LEEME.txt`.
