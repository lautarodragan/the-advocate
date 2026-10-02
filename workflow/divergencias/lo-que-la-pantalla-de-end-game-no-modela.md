# Qué

End Game, la última orden del menú de pausa, abre en RM2k `Scene_End`: la
pregunta —el término `exit_game_message`— y "Yes"/"No" en dos ventanas sobre
negro. "Yes" funde el tema y la pantalla y va al título; "No" o cancelar
vuelven al menú.

Desde el 2026-09-28 la ROM lo hace —ver `tools/runtime/end_game.s` y
el `end_game.rs` de `rm2k-snes-screens`—, con las ventanas, el texto y la barra del
System en los mismos pixeles que el original, corridos al centro de 256x224.
Hasta ese día la orden iba en gris y no hacía nada.

Lo que queda distinto:

* **Se abre y se cierra sin fundido.** El RPG_RT funde el menú y funde la
  pantalla de End Game al entrar, unos seis cuadros cada uno; la ROM cambia de
  una a otra de golpe, como hace con todas las pantallas del menú.
* **No suenan los efectos del sistema**: ni el del cursor, ni el de decidir,
  ni el de cancelar. Tampoco suenan en el resto del menú.
* **Entra con el cursor en "Yes"**, que es lo que hace el RPG_RT de 2015.
  easyrpg-player entra en "No" (`SetIndex(1)` en `Scene_End`). El RPG_RT de
  2000, el que usó el autor, no se pudo mirar: con Wine se cae al cambiar el
  modo de video.
* **La pantalla se funde en 20 cuadros** por una rampa de brillo; el tema en
  400 ms, que es el `BgmFade(400)` de easyrpg. El RPG_RT de 2015 tarda unos
  330 ms en llegar a negro, medido con capturas cada 18 ms.
* **La letra y la franja del fondo** son las de `ventana.py` y la fuente del
  port, que valen para todas las ventanas: comparadas contra la captura del
  original a 320x240, difieren un par de glifos —la "g"— y la franja clara del
  fondo estirado cae unas filas corrida.

# Medido

Con el RPG_RT de 2015 corriendo con Wine, sobre una copia del juego cuyo mapa
4 arranca con Kersh y Core en el grupo: la pregunta en una ventana de 70x32 en
(125, 72), "Yes" y "No" en una de 34x48 en (143, 120), el cursor en "Yes" al
entrar, B y "No" de vuelta al menú con el cursor en End Game. El dibujo de
`fin_del_juego.dibujar` a 320x240 cae en esas mismas cajas.

Lo cubren `pruebas/rpgmaker/test_fin_del_juego.py` de ABL —la pantalla contra
`fin_del_juego.render` con el cursor en cada orden, "No", B, y "Yes" hasta la
golden `titulo`— y las goldens `fin` y `fin-no` de `test_menu_golden.py`.

# Cuándo deja de alcanzar

Un juego con una pregunta más larga: la ventana mide lo que el texto, y a seis
pixeles por letra entran 40 en los 256 de la pantalla. El conversor se corta
si no entra.
