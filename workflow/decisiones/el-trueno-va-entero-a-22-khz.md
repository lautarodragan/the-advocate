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
sonido" en `main.s`.

# Lo que todavía no está

El trueno entero **sólo existe en la rama `worktree-agent-af7bb3c8b214b75b1`**,
como un alias `Thunder9@entero` que `_compilar` pone sólo en el mapa 1. No es
un mecanismo general. Llevarlo a `main` bien es el paso 2 de
`tasks/todo/efectos-de-sonido-sin-recortes.md`: qué efectos van enteros y a
qué tasa, cumpliendo que todos los mapas tengan todos sus efectos.
