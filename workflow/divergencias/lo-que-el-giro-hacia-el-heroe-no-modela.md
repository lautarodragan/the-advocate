# Qué

Desde el 2026-09-11 el evento que el héroe dispara **gira hacia él**, como el
`SetFacing(GetDirectionToCharacter(GetPlayer()))` de
`Game_Event::ScheduleForegroundExecution`. Las reglas están en GIRO, en
`tools/port/eventos.py`, y en `giro_disparar` de `rom/src/giro_hacia_el_heroe.s`. Lo que queda
afuera:

* **Los que caminan solos no giran.** Su ruta propia está siempre andando, y
  con una ruta andando adónde mira lo decide ella. En RM2k la página que corre
  los **pausa** —`SetPaused(true)`— y entonces sí giran; la pausa no está
  modelada, así que acá siguen caminando mientras hablan, que es la deuda de
  fondo. Uno al que una escena ya movió sí gira: la ranura de ruta le queda
  hasta el mapa que viene, pero vacía.
* **Otro CharSet con la misma pose.** Si un refresco le cambia la página a una
  que dibuja otro CharSet con la misma dirección y columna, RM2k lo deja girado
  con el dibujo nuevo; acá el giro se deshace.
* **Si la cola de subidas a VRAM está llena** en el cuadro del disparo, el
  quieto no gira.

# Medido

La cola llena no pasa en el juego en ese momento. El `GangMember1` de Lashe
City fue el que mostró el caso de la ruta ya terminada: hasta el 2026-09-11 no
giraba nunca más.

Antes de girar, el evento contestaba mirando para donde estaba, y antes de eso
la página directamente no compilaba: el 2026-09-08 eso costaba **1572 páginas
de acción en 1224 eventos de 220 mapas**, la mitad de los NPCs del juego mudos.

# Cómo se ve hoy

Un NPC que camina solo contesta sin darse vuelta y sin frenar.
