---
name: "El juego golden y dos repos"
description: "Un juego de prueba para el motor, y ABL en su propio repo"
---

# Qué

**Un juego de RM2k hecho a propósito —el "juego golden"— que pruebe el motor**,
y **ABL en su propio repo**, separado de lo que no depende de él.

Dos capas de pruebas en vez de una:

* **Conformidad del motor**, contra el juego golden: un mapa por funcionalidad,
  chico y determinista, y el juego entero es el golden. Es **la regla del
  cartucho único resuelta de raíz** —un juego, un ROM— y es la especificación
  de qué soporta el port. Portar otro juego lo reusa entero.
* **Aceptación de ABL**: que sus primeros minutos se jueguen y se vean así.
  Sigue haciendo falta, porque los errores más caros salieron de contenido real
  que nadie escribiría a propósito. **El juego golden crece con ésos**: cada
  error que aparezca en un juego real se abstrae y se suma como un caso.

Y **dos repos**: lo que no depende de ABL —el motor, las herramientas, el juego
golden— se puede publicar, porque el juego golden usa material de dominio
público o con licencia que lo permita. ABL queda en el suyo, y si alguna vez hay
que bajarlo, se baja sin arrastrar lo valioso.

# Status

Idea de taro, el 2026-09-17. Anotada, sin empezar: **hoy lo único hecho es el
embrión**, `pruebas/casos/`, que son eventos de RM2k en el JSON de Ditto y no
una tabla especial de la ROM.

# Blockers

* **Lo que el juego golden no puede heredar sin revisar**: el RTP de Don Miguel
  es de Enterbrain; las muestras salen de los SoundFonts de
  `/extras/soundfonts`, cuya licencia hay que mirar una por una; y la fuente del
  sistema de RM2k tiene dueño. Los MIDIs de ABL son música de otros juegos:
  quedan del lado de ABL.
* **Hace falta armar el juego**, mapa por funcionalidad, con assets propios.

# Decisiones a tomar

* **Qué pruebas van con el motor y cuáles con ABL.** El reparto de hoy dejó
  casos del lado dudoso, y son éstos:

  Lo que quedó del lado dudoso, y conviene revisar al armar el juego golden:

  * **`rpgmaker/` es más "motor" que "RM2k"**: `test_cores`, `test_compositor`,
    `test_paralelos` y `test_musica_paquete` cuidan propiedades del port —la
    WRAM sin inicializar, el buffer del texto, el presupuesto del cuadro, las
    muestras en la ARAM— y no comportamiento de RM2k. Van con el motor igual.
  * **`abl/test_tanda_escenas.py` tiene casos que ejercitan comandos
    genéricos** —`elegir`, `tienda`, `savepoint-guarda`, las puertas— con
    páginas del juego, y `factoria`, que es el tercer reparto de VRAM. Partirlo
    por caso pedía duplicar la función de la familia; se partió sólo por
    familia: `hablar` se fue a `rpgmaker/test_tanda_hablar.py`.
  * **`herramientas/` se decidió por la forma** —no corre ROM— y varias miran
    el conversor sobre mapas de ABL: `test_lideres`, `test_destello_paleta`,
    `test_timer_paleta`, `test_encuentros`. `test_bancos` lee la tabla de
    símbolos del cartucho armado, sin correrlo. Si van "con su herramienta",
    el lugar natural es al lado de `tools/`, y eso se decide cuando `tools/`
    se reparta entre los dos repos.
* **Dónde queda `tools/`**, que es de las dos clases: el conversor es del motor,
  pero `port/` todavía sabe cosas de ABL.
* **Qué pasa con `golden/` y `casos/`**, que hoy sirven a las dos capas.
