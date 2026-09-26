# Qué

**El trueno de la apertura suena entero, sin bucle, a 22.050 Hz**: la tasa
de su WAV, así que no se remuestrea. Y **los efectos de sonido tienen dos
voces**, para que la lluvia no lo corte.

Las dos cosas son de taro, el 2026-09-24, escuchando las ROMs del
experimento en mednafen y en video.

# Por qué

Con el tope de 0,75 s y el bucle de 0,4 s, el trueno repetía su tramo más
fuerte hasta cumplir su duración y cortaba en seco: taro lo oyó tartamudear
aunque nada lo pisara. Entero a 16 kHz ya le sonó perfecto; eligió 22 kHz
porque tiene más agudos, y los nueve cuadros más de fundido al entrar al mapa
1 no le molestan.

Con una sola voz, la lluvia le cortaba el trueno, porque se vuelve a disparar
cada pocos segundos. Las dos voces ya están en `main`: ver "los efectos de
sonido" en `rom/src/efectos_de_sonido.s`.

# Cómo quedó

El trueno entero es un alias, `Thunder9@entero`, que `_compilar` pone sólo en
el mapa 1: el 3 también pide el trueno, y ahí entero no entra sin bajarle la
tasa a su tema. Desde el 2026-09-26 hay más efectos enteros (`SE_ENTEROS` en
`tools/audio/snes_music.py`), pero con otra regla: ésos van sólo en lo que la
música deja libre en cada paquete, y no le cuestan nada a ningún instrumento.
**El trueno es el único que la música paga si hace falta** —en `release` no
hace falta: su paquete no limita a ninguna muestra—, porque taro lo eligió
así antes de esa regla. Ver `tasks/*/efectos-de-sonido-sin-recortes.md`.
