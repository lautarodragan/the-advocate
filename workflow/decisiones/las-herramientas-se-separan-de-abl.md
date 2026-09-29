# Las herramientas se separan de ABL, en dos repos

De taro, el 2026-09-28, al leer el research
`docs/research/el-mapa-de-las-herramientas-de-python.md` (Quebracho), que
tiene el plan de seis pasos y las preguntas con sus opciones.

- **El plan es el de seis pasos del research.**
- **Se separa antes del juego golden**, que es la opción b) de la pregunta 1:
  el repo de herramientas sale sin pruebas de ROM propias, y las corre el
  repo de ABL hasta que exista el juego golden. El research recomendaba
  esperar al juego golden para el corte; taro eligió no esperar.
- **El lado agnóstico es un solo repo**: las herramientas de RM2k, el
  conversor y el motor de SNES juntos.
- **El repo de herramientas va en inglés**, como los proyectos de Rust.
  Cuándo se traduce —antes del corte o al reescribir cada parte— no se
  decidió todavía.
- **Los límites del motor medidos sobre ABL se quedan fijos** (`ITEMS_N`,
  `ENC_RATE`, `FUNDIDO_CUADROS`, los anchos…), con un comentario que diga
  que se midieron contra A Blurred Line. En una segunda etapa pasan a ser
  parámetros, y los mide una herramienta sobre el juego ya volcado a JSON.
  La idea de taro es que **la estimación no se separe de la implementación**:
  si un binario es el que decide cómo repartir paletas, la medición sale de
  ese mismo binario, y no de un "medir-juego" aparte que duplique la regla.
  Es "Parse, Don't Validate" aplicado a algo más complejo.
- **La historia de git se conserva si es gratis.** Si cuesta, se discute.
- **Cómo consume ABL a las herramientas**: primero, todo en el mismo repo
  con dos raíces (el paso 5 del plan). Después, lo estable como ejecutables
  en el PATH. **Submódulos de git, nunca**: a taro no le gustan. Además, hoy
  no hay una buena forma de asociar un mismo ambiente de trabajo a dos repos.
  Queda por resolver cómo consigue ABL la versión del motor en ensamblador si
  no es por submódulo.
- **ABL sólo conoce ejecutables del PATH, no `tools/`.** Es la idea de taro
  para el primer paso: el `justfile` no sabe que existe Python, y los `.py`
  que se ejecutan pasan a ser ejecutables de verdad, con hashbang y
  `chmod +x`. Una prueba simple con grep hace fallar la tanda si algo del
  lado de ABL nombra la ruta de `tools/`.
- **Los comentarios del motor que nombran a ABL se quedan por ahora**, por
  cuidado. Tampoco se toca todavía lo que se emite al `.inc` ni los `help=`.

Lo que quedó abierto:

- **`cartuchos.py`** (pregunta 6): taro no ve una responsabilidad clara en
  ese archivo. Mezcla datos de ABL, que podrían ir a un `.toml`, con la
  clave del caché y cosas de pruebas. Le parece que no debería existir:
  lo reemplazarían un par de recetas del `justfile`, los datos en un
  `.toml`, y una clave de caché que no dependa del hash de un binario sino
  de su versión (por ejemplo, que cada binario la emita, o guardar
  `gunter --version`). En la misma línea, `tiles_bin.py` y `comprimir.py`
  parecen envoltorios de `voodoo` y `lz2` sin mucho sentido. Queda por
  decidir si se sube a la raíz y después se desarma, o al revés.
- **`decisiones/` y `divergencias/`** (pregunta 8): algunas son de ABL y
  otras no. Hay que revisarlas una por una.
