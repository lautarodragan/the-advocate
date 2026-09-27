# Qué

**El trueno de la apertura suena entero, sin bucle, a 8.800 Hz**, y lo que
eso le ahorra al paquete del mapa 1 paga **la lluvia entera**. Y **los
efectos de sonido tienen dos voces**, para que la lluvia no lo corte.

Entero y las dos voces son de taro, el 2026-09-24, escuchando las ROMs del
experimento en mednafen y en video. Los 8,8 kHz son de taro también, el
2026-09-26.

# Por qué

Con el tope de 0,75 s y el bucle de 0,4 s, el trueno repetía su tramo más
fuerte hasta cumplir su duración y cortaba en seco: taro lo oyó tartamudear
aunque nada lo pisara. Eso es lo que no se negocia: **entero**.

La tasa sí. El 2026-09-24 eligió 22.050 Hz —la de su WAV— porque tenía más
agudos que a 16 kHz. El 2026-09-26 la lluvia pasó a sonar entera (sus cinco
segundos, sin el bucle), y en el paquete del mapa 1, que ya estaba lleno, eso
le bajaba la tasa a casi todo `escape_newyork` —el polysynth de 21 a 8 kHz—.
Con el trueno a 8,8 kHz los dos efectos enteros ocupan lo mismo que antes
ocupaban el trueno a 22 kHz y la lluvia recortada, y **no baja ningún
instrumento**. taro ya había escuchado el trueno a menos calidad y le pareció
bastante aceptable.

Con una sola voz, la lluvia le cortaba el trueno, porque se vuelve a disparar
cada pocos segundos: ver "los efectos de sonido" en
`rom/src/efectos_de_sonido.s`.

# Cómo quedó

El trueno entero es un alias, `Thunder9@entero`, que `_compilar` pone sólo en
el mapa 1 (`SE_DEL_MAPA` en `tools/audio/snes_music.py`): el 3, el 20 y el 32
también piden el trueno, y ésos llevan el de siempre, entero a 6 kHz. Los dos,
y la lluvia, están en `SE_ENTEROS_PAGADOS`: los paga la música de su paquete
si hace falta. Si el trueno o la lluvia cambian de tasa, el paquete del mapa 1
vuelve a limitar: el conversor imprime qué muestras limita cada paquete. Ver
`tasks/*/efectos-de-sonido-sin-recortes.md`.
