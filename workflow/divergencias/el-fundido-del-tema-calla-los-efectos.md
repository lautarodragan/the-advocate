# Qué

En RM2k, `FadeOutBGM` baja el tema y nada más: un `PlaySound` que venga
después suena igual. En la ROM, **sin MSU-1**, el fundido baja el volumen
general del DSP —`bgm_fundido_tick`, en `rom/src/musica.s`, escribe
`DSP_MVOL_L` y `DSP_MVOL_R`—, que es también el que oyen los efectos, y al
llegar a cero lo deja ahí hasta que arranca otro tema —un `PlayBGM`, o el
tema propio de un mapa—, que lo repone con la puesta a punto del stream.
Mientras tanto los efectos suenan a lo que quede del fundido, y terminado,
mudos.

Con MSU-1 no pasa: el fundido baja el volumen de la pista y no el del DSP, y
el comentario de ese camino ya lo dice.

# Medido

El 2026-09-26, grabando un efecto después de un `FadeOutBGM` de un cuadro
escrito desde afuera (`bgm_fundido`, `bgm_paso`) en la ROM de `main` en
955b186: **cero** muestras distintas de cero en toda la grabación, con el
efecto sonando según `SE_CUADROS`. Reponiendo `MVOL` a mano se oye.

En el juego, un `PlaySound` después de un `FadeOutBGM` y antes del próximo
`PlayBGM` de la misma página (un script que lee `data/maps/`): el `Thunder9`
del mapa 3, en la secuencia de "Core...?"; `Wind1` y `clap` en el 18; y en
mapas que el cartucho no lleva todavía, `Wind8` en el 105, `Explosion6` en el
124, `Dark5` en el 132 y `clap` en el 145. Si el efecto cae adentro del
fundido o después depende de cuánto dura cada uno y de las esperas del medio:
no se midió en cada página.

# Cómo reproducirlo

Jugar la secuencia del final del mapa 3 sin MSU-1 y escuchar el trueno de
después del fundido. Ninguna prueba lo mira: la tanda compara imágenes.

# Cómo se arreglaría

Que el fundido baje el volumen de las voces de la música y no el general, o
que al terminar reponga el general con el tema ya callado. No se estudió
cuánto cuesta ninguna de las dos.
