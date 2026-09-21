# Qué

Las **decisiones artísticas** —lo que se pierde al pasar de RPG Maker a la
SNES— salen del conversor como **archivos versionados**, y con el tiempo pasan
a ser la fuente: el conversor las **lee** en vez de volver a tomarlas.

Taro lo resumió así: *"es como un terraform o liquibase pero para juegos de
RPG Maker"*.

# Status

Decidido el 2026-09-20, en dos fases. La fase 2 **está decidida**, no es una
posibilidad.

**La fase 1 está hecha para una de las cuatro clases**: los colores que se
fusionan en las dos capas de un mapa. Salen a `parches/mapas/<id>.toml`, los
escribe el conversor al lado de cada ROM que arma, `just parches` copia a git
los del ROM jugable, y `just parches-check` —y `test_parches.py`, adentro de la
tanda— fallan diciendo **qué decisión cambió**. Las otras tres siguen sin dejar
rastro; al final está qué cuesta cada una.

# La distinción que lo ordena

Al pasar de RM2k a la SNES hay dos clases de transformación:

* **No-lossy**: no piden criterio y no cambian lo que se ve. El horneado de
  eventos opacos en el mapa, `separar_del_heroe`, el reuso de tiles espejados.
  **No son parches**: son optimizaciones y se quedan donde están.
* **Lossy, o "decisiones artísticas"**: algo se pierde y alguien eligió qué.
  **Ésas son los parches.**

Las que hay hoy, todas automáticas y sin dejar rastro:

* los **colores que se fusionan** cuando una imagen no entra en las paletas
  (`tools/port/asignador.py`);
* las **voces que se caen de un MIDI** y las **muestras recortadas** cuando no
  entran en la ARAM (`tools/audio/snes_music.py`);
* las **animaciones dibujadas a otro tamaño**, como la del Emitter Room;
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

## Lo que falta, con lo que cuesta

* **Las paletas de los personajes.** La que más se parece a lo que viene:
  depende del cartucho de verdad —quién le paga la entrada al cronómetro lo
  decide `npcs_dibujables` mirando el mapa entero, y con `--heroe-encima` o con
  otros líderes posibles el reparto es otro—. Con la regla de taro puesta, lo
  versionado es lo que decide `abl` y el cartucho que no pueda aplicarlo decide
  solo; lo que hay que diseñar es qué pasa cuando **sí** se puede aplicar pero
  la paleta que reserva no está libre. Ése es el caso que taro pidió mirar y en
  las capas no existe, así que ahí se va a decidir de verdad.
* **Las voces que se caen de un MIDI y las muestras recortadas.** La más cara, y
  la que conviene parar antes de forzarla. Lo que se cae no lo decide un tema
  sino el reparto de la ARAM entre **todos** los del cartucho, con una prioridad
  que depende de dónde arranca la ROM: la clave "el tema" no alcanza para
  identificar la decisión, y la clave "el cartucho" es la que taro descartó. Con
  `abl` como única situación versionada se puede hacer, pero el archivo tendría
  que describir el reparto entero y no una pérdida por tema, y eso es otro
  formato.
* **Las animaciones dibujadas a otro tamaño.** Barata y bien acotada: el tamaño
  sale de `animacion.tamano(ancho, alto)`, que es función pura de la caja de la
  animación, así que la clave es el número de animación de RM2k y no hace falta
  nada del cartucho. Es la candidata obvia para la próxima.
* **`DECORAR_TRANSLUCIDO`.** Mirado, y rinde poco: la decisión ya está
  versionada y se edita a mano, en la lista `SIN_TRAMA` de `rpgmaker/rm2k.py`,
  y lo otro que hace —hornear el gráfico contra el fondo de su celda— es de lo
  no-lossy. Lo que faltaría emitir es qué gráfico quedó tratado así en cada
  mapa, que es poco más que repetir la lista.
