# Qué

Un evento quieto con animación continua deja de compartir la ranura de VRAM de
su (CharSet, índice, pose) y necesita **las doce poses suyas**, como los que
caminan. El tope es `ANIMA_QUIETO_MAX` en `tools/port/snes_convert.py`, y es
**por mapa y todo o nada**: con más de ésos, el mapa no anima ninguno. En RM2k
animan todos.

Por qué todo o nada está en el comentario del tope: animar unos sí y otros no
se ve peor que no animar —dos fuentes iguales, una moviéndose y la otra
congelada— y pediría una regla para elegir cuáles.

# Medido

El 2026-09-09, con el tope en cuatro: el mapa 52 tiene treinta y pedía 572
tiles de sprite contra los 384 que entraban. De los 328 mapas del juego, 312
tenían cuatro o menos, y de los que llevaban las ROMs el único que se pasaba
era el 52, que no es de los primeros diez minutos.

# Cómo se ve hoy

En el mapa 52 los quietos que animan en RM2k están quietos.

# Cuándo deja de alcanzar

Un mapa con más del tope que sí importe. Ahí hay que mirar el presupuesto de
sprites de ese mapa y subir el tope, no cambiar la regla: el conversor corta con
el número en el mensaje si no entran.
