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
