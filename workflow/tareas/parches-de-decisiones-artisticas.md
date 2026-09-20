# Qué

Las **decisiones artísticas** —lo que se pierde al pasar de RPG Maker a la
SNES— salen del conversor como **archivos versionados**, y con el tiempo pasan
a ser la fuente: el conversor las **lee** en vez de volver a tomarlas.

Taro lo resumió así: *"es como un terraform o liquibase pero para juegos de
RPG Maker"*.

# Status

Decidido el 2026-09-20, en dos fases. La fase 2 **está decidida**, no es una
posibilidad.

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
