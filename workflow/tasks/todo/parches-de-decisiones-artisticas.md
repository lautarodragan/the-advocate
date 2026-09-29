---
name: "Parches de decisiones artísticas"
description: "Lo que se pierde al convertir, como archivos versionados"
type: feature
---

# Qué

Las **decisiones artísticas** —lo que se pierde al pasar de RPG Maker a la
SNES— salen del conversor como **archivos versionados**, y con el tiempo pasan
a ser la fuente: el conversor las **lee** en vez de volver a tomarlas.

Taro lo resumió así: *"es como un terraform o liquibase pero para juegos de
RPG Maker"*.

# Status

Decidido el 2026-09-20, en dos fases. La fase 2 **está decidida**, no es una
posibilidad.

**La fase 1 está hecha para tres clases**: los colores que se fusionan en las
dos capas de un mapa, el tamaño al que se dibuja cada animación de batalla, y
—desde el 2026-09-21, con la escena de la pelea compuesta en la consola— los
quince colores de cada battler. Salen a `parches/mapas/<id>.toml`,
`parches/animaciones/<n>.toml` y `parches/battlers/<nombre>.toml`, los escribe el conversor al lado de cada ROM
que arma, `just parches` copia a git los del ROM jugable, y
`just parches-check` —y `test_parches.py`, adentro de la tanda— fallan diciendo
**qué decisión cambió**. Las otras dos siguen sin dejar rastro; al final está
qué cuesta cada una.

# La distinción que lo ordena

Al pasar de RM2k a la SNES hay dos clases de transformación:

* **No-lossy**: no piden criterio y no cambian lo que se ve. El horneado de
  eventos opacos en el mapa, `separar_del_heroe`, el reuso de tiles espejados.
  **No son parches**: son optimizaciones y se quedan donde están.
* **Lossy, o "decisiones artísticas"**: algo se pierde y alguien eligió qué.
  **Ésas son los parches.**

Las cinco que hay hoy, todas automáticas; las tres primeras ya dejan rastro
escrito y las dos últimas todavía no:

* los **colores que se fusionan** cuando una imagen no entra en las paletas
  (`tools/port/asignador.py`) — escritas, por mapa;
* las **animaciones dibujadas a otro tamaño**, como la del Emitter Room
  (`tools/port/animacion.py`) — escritas, por número de animación;
* los **quince colores de cada battler** en la escena de la pelea
  (`tools/port/escena.py`) — escritos, por imagen y tono;
* las **voces que se caen de un MIDI** y las **muestras recortadas** cuando no
  entran en la ARAM (`tools/rm2k-snes-audio/`);
* **`DECORAR_TRANSLUCIDO`**: un CharSet translúcido reemplazado por otro
  gráfico.

# Fase 1: reflejo

El conversor **escribe** lo que decidió, estructurado y versionado, y la tanda
falla si lo commiteado no coincide —como `protocolo --check`—. No cambia
comportamiento.

Lo que gana, y es el punto: **el diff avisa**. Si un cambio hace que un mapa
pierda dos colores más o que un tema se quede sin una voz, se ve en el diff en
vez de sólo en la ROM. Es lo que las goldens hacen con los pixeles, para las
decisiones.

# Fase 2: manda el archivo

El conversor **lee** lo decidido y lo aplica; volver a decidir es un comando
explícito, como un `plan`/`apply`. Con eso las decisiones **dejan de cambiar
solas** cuando cambia un algoritmo, y se pueden **editar a mano** cuando una no
gusta.

Por eso la fase 1 tiene que escribir **el estado deseado y no un informe**: qué
color se fusiona con cuál, qué voz se cae, a qué tamaño va esa animación, con
una **clave estable** que permita leerlo de vuelta. Un texto para humanos no
sirve para la fase 2.

# Y el porqué de fondo

Es lo mismo que se hizo con `data/`: primero un volcado, después la fuente. Y
encaja con los dos repos: el motor sabe **cómo** convertir; los parches dicen
**qué** se decidió para este juego.

# Lo que quedó hecho de la fase 1

## La forma, que era el punto delicado

Un archivo por mapa y una sección por capa, en TOML. Cada fusión dice a qué
color se va el que se pierde —RGB de 15 bits, que es la profundidad de la
consola— y van **en orden**: aplicarlas de arriba a abajo reconstruye el mapeo
entero que hoy devuelve `merge_least_visible`, así que la fase 2 es recorrer la
lista y no volver a decidir. El orden importa de verdad y no es prolijidad: en
el mapa 2 un color se fusiona con otro que más abajo se fusiona a su vez.

La clave es el **id del mapa**, que es del juego: no se mueve con el orden
interno del conversor, ni con la lista de mapas del cartucho, ni con el
algoritmo del asignador. Los colores van por valor y no por índice en ninguna
paleta, por lo mismo.

**Y el cartucho no entra en la clave**, por la regla de taro del 2026-09-21: la
decisión versionada es siempre la del ROM jugable y los cartuchos de prueba se
adaptan como puedan. Son los 29 mapas de `abl`; los once que los cartuchos de
prueba llevan de más son situaciones que el juego no tiene, y ahí cada uno
decide solo. Para esta clase la pregunta ni se llega a hacer —las fusiones de
las capas dependen del mapa y de su ChipSet y de nada más—, y está medido:
`abl` y los tres cartuchos de prueba emiten los mismos 29 archivos byte por
byte.

El formato no le estorba al rumbo de que qué mapas entran, dónde arranca y con
qué grupo dejen de ser argumentos sueltos: una clave que nombra la situación
del juego sigue sirviendo, y lo que cambiaría es de dónde sale la lista de
situaciones, no cómo se identifica cada una.

## Las animaciones, que fueron la segunda

Hecha el 2026-09-21, y salió como estaba previsto: la nota de arriba decía que
el tamaño es función de la caja y de nada más, y al mirarlo resultó cierto.
`animacion.tamano(ancho, alto)` mira la caja que la animación ocupa en RM2k
—la unión de todas las celdas de todos sus cuadros— y la caja de la consola,
que es **una sola para toda la ROM** y no del mapa: el porqué está en
`animacion.py` y es que los `ShowBattleAnimation` de todos los mapas comparten
los cuadros ya convertidos. Así que la clave es el número de animación de RM2k
y nada más, igual que el id del mapa en la otra clase.

**Lo que sí depende del mapa es otra decisión**, y quedó afuera a propósito: si
la animación se dibuja o no. `animacion_de_mapa` devuelve "no va" cuando el
mapa ya se llevó las ocho paletas de sprite, y eso sí mira el cartucho. Meterlo
en el archivo de la animación sería volver a mezclar el cartucho con el juego;
es una clase aparte, y de las que no están escritas.

El archivo dice **a qué rectángulo va** —`tamano = [64, 49]`, que es lo que la
fase 2 lee en vez de volver a calcularlo, con `parches.leer_animacion`— y, para
que el diff se entienda, de qué venía: la caja en pixeles de RM2k y cuántos
cuadros son. El porcentaje no se escribe: es para leer y no para aplicar, y
sale de los otros dos.

Que el cartucho no entre en la clave **no se supone**, como con las capas:
`--check` compara todos los cartuchos que muestren una animación versionada, y
una prueba de la tanda rehace `tamano(*original)` desde lo escrito, que es lo
que cobraría el día que el tamaño empiece a depender de algo más.

Lo medido el 2026-09-21, para no volver a medirlo: `abl` muestra trece
animaciones y lo emitido ocupa 10.435 B; la 91 la muestra sólo un caso de la
tanda, así que no se versiona y `--check` la informa; los cuatro cartuchos
emiten lo mismo byte por byte, y las ROMs no se movieron ni con caché ni con
`SIN_CACHE=1`.

Lo que queda de esta clase sin escribir son **los quince colores** a los que se
reduce cada animación: es una decisión artística de las de verdad —se pierden
colores y alguien eligió cuáles—, tiene la misma clave, y es casi el mismo
formato que las fusiones de las capas. No se hizo acá porque la tarea era el
tamaño.

## Los battlers, que fueron la tercera

Salieron el 2026-09-21 con la escena de la pelea compuesta en la consola, que
lleva cada monstruo a quince colores. Van en su forma mínima: la paleta que
quedó y cuántas fusiones hicieron falta, no la lista entera de fusiones, que
medía 179 KB. La clave es la imagen y su tono (`battler_hue`), que es lo que
distingue a dos battlers con el mismo dibujo.

## Lo que falta, con lo que cuesta

* **Las paletas de los personajes.** La que más se parece a lo que viene:
  depende del cartucho de verdad —quién le paga la entrada al cronómetro lo
  decide `npcs_dibujables` mirando el mapa entero, y con `--heroe-encima` o con
  otros líderes posibles el reparto es otro—. Con la regla de taro puesta, lo
  versionado es lo que decide `abl` y el cartucho que no pueda aplicarlo decide
  solo; lo que hay que diseñar es qué pasa cuando **sí** se puede aplicar pero
  la paleta que reserva no está libre. Ése es el caso que taro pidió mirar y en
  las capas no existe, así que ahí se va a decidir de verdad.
* **Las voces que se caen de un MIDI y las muestras recortadas.** Tiene su
  propia tarea, `el-audio-en-dos-pasos-lossy.md`. La más cara, y
  la que conviene parar antes de forzarla. Lo que se cae no lo decide un tema
  sino el reparto de la ARAM entre **todos** los del cartucho, con una prioridad
  que depende de dónde arranca la ROM: la clave "el tema" no alcanza para
  identificar la decisión, y la clave "el cartucho" es la que taro descartó. Con
  `abl` como única situación versionada se puede hacer, pero el archivo tendría
  que describir el reparto entero y no una pérdida por tema, y eso es otro
  formato.
* **Los quince colores de cada animación.** La barata que quedó servida: misma
  clave que el tamaño —el número de animación—, mismo formato que las fusiones
  de las capas, y la decisión también se ve. Está descrita arriba.
* **`DECORAR_TRANSLUCIDO`.** Mirado, y rinde poco: la decisión ya está
  versionada y se edita a mano, en la lista `SIN_TRAMA` de `rpgmaker/rm2k.py`,
  y lo otro que hace —hornear el gráfico contra el fondo de su celda— es de lo
  no-lossy. Lo que faltaría emitir es qué gráfico quedó tratado así en cada
  mapa, que es poco más que repetir la lista.
