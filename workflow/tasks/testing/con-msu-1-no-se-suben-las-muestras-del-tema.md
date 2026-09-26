---
name: "Con MSU-1 no se suben las muestras del tema"
description: "Si hay MSU-1 y el tema tiene pista, sus muestras de música no hacen falta en la ARAM: cargas más rápidas y más lugar para los efectos"
type: feature
---

Con MSU-1, un tema que tiene pista (`PISTAS_MSU`, 22 temas) suena desde el
PCM y el SPC700 no toca su música. Pero la ROM igual sube sus muestras al
cargar el paquete del mapa o de la pelea: tiempo y ARAM perdidos.

Que la subida del paquete (`paquete_cargar_ya`, `tema_asegurar`) se saltee las
muestras de música de los temas que van a sonar por MSU-1 cuando el MSU-1
está presente (la ROM ya lo detecta: `rom/src/msu1.s`). Los efectos siguen
subiendo siempre.

Lo que gana, a medir:
* **cuadros de carga con MSU-1**: el paso 6 dejó la pelea en 58 cuadros al
  entrar y 63 al salir, y el mapa 3 en 84; con MSU-1 deberían bajar mucho;
* **la ARAM entera para los efectos** mientras suena un tema por MSU-1.

Lo que hay que cuidar: un tema **sin** pista que suene en el mismo paquete
(sigue necesitando sus muestras), el paso de MSU-1 a SPC700 si una pista falta
en la tarjeta (el MSU-1 lo dice con su bit de error: ¿la ROM cae al SPC700?,
entonces las muestras tienen que estar), y que sin MSU-1 no cambie nada (las
goldens corren sin MSU-1). La prueba con `msu=True` de `pruebas/abl/test_msu.py`
es el lugar para cobrarlo.

Idea de taro, el 2026-09-26: en el peor caso, con MSU-1 la música va por la
pista y los efectos entran enteros en la ARAM sin competir con la música.

## Y la otra mitad: los efectos de calidad desde el `.msu`

También de taro, el mismo día: **los efectos livianos en la ROM y los de
calidad en el `.msu`**, con el mecanismo de los fondos de batalla
(`docs/port/msu-datos.md`: la ROM lee el `.msu` por el puerto de datos si hay
MSU-1 y la firma coincide, y si no usa lo suyo).

Encaja con lo de arriba: con MSU-1 las muestras del tema no ocupan la ARAM, así
que hay lugar para los efectos de calidad; sin MSU-1, los efectos más livianos
dejan lugar para las muestras de la música, que es justo la pelea de hoy entre
los efectos del mapa 3 y el oboe, la flauta y la batería. Y achica la ROM: los
efectos son ~211 KB de los ~262 de `muestra`.

Ojo: esto no reproduce los efectos por el audio del MSU-1 (tiene un solo
flujo de audio, que es el de la música): los sube a la ARAM desde el puerto de
datos y los sigue tocando el SPC700. Y sin MSU-1 los efectos quedarían más
livianos que hoy, que es lo que taro no quería perder: decidirlo con
grabaciones de las dos versiones delante (como el trueno).

## Hecho, el 2026-09-26: la primera mitad

Sólo lo de arriba —no subir las muestras del tema—; la segunda sección es un
plan B que taro no pidió todavía, y no se tocó.

**Cómo**: `tema_por_msu` (`rom/src/paquete_de_audio.s`) contesta si un tema va
a sonar por el MSU-1 —hay MSU-1, el tema tiene pista en `tema_msu` y esa pista
no faltó nunca—, y `paquete_cargar_ya` saltea esos temas en sus listas de
temas y de temas de salida. **El tema extra no pasa por ahí**: si se pide es
porque va a sonar por el SPC700. Sin MSU-1 contesta siempre que no, así que
el paquete es el de siempre.

**Lo que había que cuidar**:

* *Un tema sin pista en el mismo paquete*: no se saltea, porque la pregunta es
  por tema. En `release` no hay ningún paquete que mezcle temas con y sin
  pista (los sin pista son de mapas de más adelante), así que la prueba borra
  la pista de `Gaden` en una copia del cartucho y mira el mapa 19, que prende
  `Gaden` y comparte paquete con `3D-Galax`.
* *Una pista que falta en la tarjeta*: la ROM **sí** cae al SPC700 —
  `msu_arrancar` mira el bit 3 de `$2000` y los topes de espera—, y ya lo
  hacía antes. Ahora además prende el bit del tema en `MSU_FALTA`
  (`$7E7820`, un bit por tema), y `music_start` sigue por `tema_asegurar`,
  que ve las muestras sin subir y rearma el paquete con el tema adelante:
  **esa vez congela lo que tarde en subir** (una carga de paquete entera,
  como un `PlayBGM` de un tema que el mapa no traía). De ahí en más ese tema
  no se saltea, así que no se repite.
* *Sin MSU-1 no cambia nada*: las goldens no se movieron, y la sonda da los
  mismos cuadros que antes.

**Lo medido**, con la sonda del paso 6 (cuadros de `paquete_cargar_ya`),
`release`, snes9x, con MSU-1, antes → después:

| | antes | después |
|---|---:|---:|
| mapa 3 (desde el 5) | 84 | 56 |
| mapa 26 | 82 | 21 |
| entrar a la pelea del droide | 82 | 20 |
| salir de la pelea (al 2) | 82 | 48 |

Sin MSU-1, los cuatro iguales antes y después (84, 82, 82, 82). Lo que queda
con MSU-1 son los efectos: el mapa 3 lleva 20 y el 2, 18.

**Lo cobran** tres pruebas nuevas en `pruebas/abl/test_msu.py`, con el
MSU-1 encendido sobre una copia de `release`: las dos primeras fallan sin el
cambio, y la de la pista faltante falla si el extra también se saltea y la
falta no se anota.

**Visto de paso, y no arreglado**: con MSU-1, la pista del título **sigue
sonando** al empezar la partida. `music_boot` (`rom/src/musica.s`), cuando
el mapa arranca callado, pone `music_apagada` y baja el volumen del DSP pero
no llama a `msu_parar`, así que `Fantasia_Of_The_Wind` sigue por la pista
hasta el primer `PlayBGM`, y la pelea la anota como el tema a reponer.

**Para taro**, con MSU-1 (FX Pak o un emulador que lo tenga) y las pistas al
lado: que la música de los mapas y de la pelea suene como antes, que los
efectos suenen, y que las cargas del mapa 3, el 26 y la pelea se sientan más
cortas. Y, si quiere probar la caída: sacar de la tarjeta una pista —la de
`KSSMKEND` es `abl-18.pcm`— y entrar al 26: el tema tiene que sonar por el
SPC700, con un congelado más largo esa primera vez.
