# Qué

Los dos relojes de la animación del ChipSet —el agua y los tiles animados— no
llevan un contador propio: salen de dividir `vueltas`, el tick del juego, con
el divisor del hardware. `vueltas` es de dieciséis bits y ni 24 ni 6 dividen a
65536, así que **cada 65536 ticks —dieciocho minutos de juego— la cuenta da la
vuelta y el ciclo se saltea un dibujo**. En RM2k el contador es de treinta y
dos bits y eso no pasa.

El porqué está en `anim_paso` de `rom/src/main.s` y en `TICK_MASCARA` de
`tools/rpgmaker/rm2k.py`: la animación no gasta un byte de RAM, que hacía falta
porque la BSS estaba llena.

# Medido

Nada: es aritmética. Un salto de un dibujo del agua, una vez cada dieciocho
minutos.

# Cómo se ve hoy

No lo ve nadie, y ningún caso de la tanda corre dieciocho minutos.

# Cuándo deja de alcanzar

Si algún día `vueltas` pasa a treinta y dos bits —porque el reloj del juego lo
pida por otra cosa— esto se cae solo.
