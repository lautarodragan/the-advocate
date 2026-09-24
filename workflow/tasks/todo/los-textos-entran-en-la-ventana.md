---
name: "Los textos entran en la ventana"
description: "Rearmar los saltos de línea de los mensajes para el ancho de la SNES, como parche"
---

# Qué

Que los mensajes del juego entren enteros en la ventana de la SNES, en vez de
cortarse. Hoy `Mensajes.agregar` (`tools/port/eventos.py`) **trunca** cada
renglón a `ventana.COLUMNAS` y cada cuadro a `ventana.LINEAS`: el porqué de los
39 caracteres está en `tools/port/ventana.py`, y es el banco de tiles, no el
ancho de la ventana. RM2k no tiene auto-wrap: cada salto lo puso el autor a
mano, pensando en 320 px de pantalla.

Es una decisión artística —cambia lo que se lee— así que va como **parche**,
en la línea de `parches-de-decisiones-artisticas.md`.

# Status

Anotada el 2026-09-24. Ese mismo día, con taro:

* **Primero una función, y la infraestructura sólo si hace falta.**
  `tools/port/textos.py` es pura: recibe un cuadro y devuelve uno o más.
  Está en `main` con sus pruebas, pero todavía no la llama el conversor.
* **El TOML que mapea texto queda decidido**, y el mapeo tiene que ser
  determinístico. Es el modelo de gettext: la clave es el original exacto, la
  traducción puede ser más de un cuadro, y un contexto desambigua el día que
  el mismo cuadro tenga que salir distinto en dos lugares. Con la función
  sola ese día no llega: el mismo cuadro da siempre lo mismo.
* **Un cuadro partido repite la línea del que habla**, porque el juego lo
  hace así: de los 564 cuadros seguidos del mismo personaje, todos repiten el
  nombre.
* La idea de que Ditto extraiga los textos con ids, con ida y vuelta byte por
  byte, sirve para traducciones de verdad. Hoy no hace falta.

**El experimento está en la rama `textos-experimento`**: forks en
`juego/mapas/` de los mapas 1 a 16 que cambian, sin el 11. Es temporal y no
va a `main`, porque un fork tapa a `data/`. La ROM y un antes y después de
cada cuadro están en `pruebas-manuales/2026-09-24-0aeb917-textos/`.

# Lo que complica, y cómo se resuelve

**La línea del que habla.** Casi todos los cuadros que no entran arrancan con
una: el nombre en mayúsculas —`KERSH`, `MANTA`— o `?????` cuando todavía no se
sabe quién es. Esa línea no se toca, y el cuerpo tiene tres renglones en vez de
cuatro. Detectarla con "todo en mayúsculas, corta, sin punto final" alcanzó en
los mapas 1 a 16, pero es una heurística: el parche dice cuál es, así que un
caso mal detectado se arregla a mano.

**Los saltos que el autor quiso.** Dos reglas:

1. **Un cuadro que entra no se toca.** Así se conservan todos los saltos de
   todos los cuadros que ya andaban, que son la mayoría.
2. En un cuadro que no entra, **un salto original es un buen lugar para cortar,
   pero no uno obligado.** Tratarlos como obligados dejaba huérfanas —"it still
   / is."— y hacía que más cuadros no entraran.

**Lo que no entra ni reajustado.** El cuerpo pasa de tres renglones. Hay dos
salidas y es una decisión por caso: partirlo en dos cuadros, lo que le suma una
tecla al jugador, o editar el texto a mano. El parche tiene que poder decir las
dos cosas.

# Dónde vive el parche

**No se editan los JSON de `data/`.** Son derivados: `just datos` los vacía y
los vuelve a escribir desde los `.lmu`, así que una edición ahí se pierde en la
próxima regeneración, y además el `git diff` de `data/` dejaría de decir "el
juego no cambió".

Lo que propongo es un **archivo de textos que el conversor aplica en memoria**,
después de leer `data/` y antes de compilar:

    parches/textos/<mapa>.toml     uno por mapa, como parches/mapas/
    parches/textos/comunes.toml    los eventos comunes
    parches/textos/tropas.toml     las páginas de pelea: otro ancho

Cada entrada es un cuadro: **el texto original como clave** y el que lo
reemplaza —uno o más cuadros—. Que la clave sea el contenido y no una
posición (mapa, evento, página, índice de comando) es lo que evita copiar los
eventos:

* no hace falta copiar nada del evento, sólo el texto;
* sobrevive a que cambie el orden de los eventos o de los comandos;
* un cuadro que el juego repite en varios lados se arregla una vez;
* una entrada cuyo original ya no aparece en el juego es un parche viejo, y el
  chequeo falla diciéndolo, como `just parches-check`.

Una entrada podría verse así:

    [[cuadro]]
    original = ["MANTA", "I already told you. He didn't go this way."]
    nuevo = [["MANTA", "I already told you.", "He didn't go this way."]]
    a_mano = false

Se aplica **reemplazando el `ShowMessage` y sus `ShowMessage_2`** por los
cuadros nuevos, antes de `agrupar`. Así partir un cuadro en dos son dos
`ShowMessage` más, y la ROM no se entera. La cola de escapes —`\|`, `\^`— va al
final del último cuadro.

**Dos pasos, como los otros parches:** una receta propone el reajuste de todo
lo que no entra y escribe las entradas; lo que se edita a mano lleva
`a_mano = true` y la receta no lo vuelve a pisar. El chequeo de la tanda falla
si un cuadro no entra y no tiene entrada. Con eso el truncado de
`Mensajes.agregar` deja de ser el camino normal y pasa a ser un error.

# El experimento, sólo sobre el texto

Contando los cuadros por página, con repetidos, el 2026-09-24:

| | Cuadros con un renglón de más de 39 | Arrancan con el que habla | Reajustados siguen sin entrar |
|---|---|---|---|
| Mapas 1 a 16 (introducción y Lashe City) | 157 | 155 | 4 |
| El resto del juego | 1.353 | 1.297 | ~310 |

La forma de cortar pesó mucho en cuántos quedan sin entrar. Con los mismos
cuadros de los mapas 1 a 16:

* si los saltos originales se tratan como obligados, no entran 9;
* si se rearma todo el cuerpo, no entran 4, pero se pierden todos los saltos del
  autor;
* con el algoritmo de abajo, no entran 4.

El algoritmo elige los cortes minimizando un costo, como un párrafo de TeX:

* cortar después de un fin de oración es gratis;
* cortar después de una coma cuesta un poco, y en cualquier otro lado más;
* donde cortaba el original, el corte sale más barato;
* un renglón corto y una palabra huérfana al final penalizan.

Ejemplos de los mapas 1 y 2:

    KERSH                                          KERSH
    Time is running out. There's no turning back.  Time is running out.
                                                   There's no turning back.

    CORE                                           CORE
    No sweat, Boss! You want a door removed,       No sweat, Boss!
    I'm your MAN!!                                 You want a door removed, I'm your MAN!!

    In the beginning, life was simple.             In the beginning, life was simple.
    Perhaps, for the computers, it still is.       Perhaps, for the computers,
    Imagination is not easily represented          it still is. Imagination is not easily
    with ones and zeroes.                          represented with ones and zeroes.

El tercero muestra el límite: el original tenía una oración por renglón, y el
reajuste lo convierte en prosa corrida. **Los pesos son gusto**: con otros
valores el mismo cuadro sale de otra forma y otros quedan peor. Ésa es la razón
para que la salida sea un archivo que se lee y se edita, y no algo que el
conversor decide solo en cada build.

# Plan

1. **El formato y la aplicación**, sin reajustar nada: el conversor lee
   `parches/textos/`, reemplaza los cuadros y el chequeo detecta parches viejos.
   Con el directorio vacío la ROM tiene que salir byte por byte igual.
2. **La receta que propone**, corrida sobre los mapas 1 a 16. taro lee el diff,
   corrige a mano lo que no le gusta y lo juega. Es el experimento de verdad.
3. **El resto del juego**, de a tandas. Los cerca de 310 cuadros que no entran
   piden una decisión cada uno.
4. **Las opciones de `ShowChoice` y los textos de la pelea**, con su propio
   ancho. Es lo que pide `los-textos-de-la-pelea-no-entran.md`, y el mismo
   mecanismo lo resuelve.

# Preguntas abiertas

* Para los cuadros que no entran: ¿partir en dos, o editar el texto?
* ¿Un archivo por mapa, o uno solo para todo el juego? Por mapa se lee mejor en
  el diff, pero un cuadro repetido en varios mapas queda en uno solo, o en todos.
* Los tres `\V` —el valor de una variable— no tienen ancho conocido hasta
  correr. Hoy no compilan; cuando compilen, el reajuste tiene que suponer un
  ancho para ellos.
