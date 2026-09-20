### Las animaciones de batalla: el sonido y la luz

`ShowBattleAnimation` son dos mitades, y ésta es la del **sonido y la luz**: sus
efectos y sus destellos, en el cuadro en que RM2k los pone. El dibujo está en la
sección que sigue. Son once en la intro —tres en el Linkage Block, ocho en el
Emitter Room, todas de fuego— y sin ellas esas escenas son silencio y nada.

Compila a `OP_ANIMATION` con la línea de tiempo adentro: por cada `timing` de
la animación, en el cuadro par `2 * (frame - 1)`, su efecto y su destello, de
la pantalla o del evento objetivo. Hay una sola a la vez, como en
`Game_Screen::ShowBattleAnimation`, y avanza una vez por cuadro antes que los
destellos (`animacion_tick`). Con "esperar", la
página espera lo que dura. Tres cosas son nuestras:

* **El destello es un `FlashScreen` o un `FlashSprite`** que arranca en la
  fuerza que RM2k le da al primer cuadro y baja lineal en diez; allá baja a
  escalones. Diez, y par a propósito: el destello de pantalla trabaja en dos
  fases según la paridad de lo que le queda, y con once arrancaba por la que
  ninguna página del juego toma, que es la que quedó sin probar.
* **Al héroe no se lo destella.** Con quién comparte paleta depende del grupo,
  que el compilador no ve; para los `FlashSprite` el conversor lo mira y corta
  la ROM entera, y una animación no vale eso. Tampoco a un evento que comparta
  gráfico con otro, y eso **quedó conservador** desde que el destello pasó a ser
  por fila de paleta (ver abajo): hoy el del objetivo se podría emitir igual. No
  se hizo en la misma vuelta porque cambia qué se dibuja en los mapas donde dos
  eventos comparten gráfico, y eso pide medir la tanda de nuevo.
* **El dibujo no está.** Son celdas de 96x96 con zoom de hasta el doble y su
  propia paleta; es el sistema de al lado, y está abajo.

Lo cobra `animacion` en la tanda —la 82 sobre el héroe, que destella la
pantalla—, por la página de prueba de `pruebas/casos/animacion.json`: la escena
del Emitter Room no se puede disparar desde una prueba. Los efectos los cobra
el paquete de audio de cada mapa, que los cuenta como uno más.

### El dibujo de las animaciones de batalla

También se dibujan. El sistema entero está en
`tools/port/animacion.py`, que es el único lugar donde se decide dónde cae y de qué
color es cada pixel; la ROM no decide nada de eso.

**Una caja de 64x64, la misma para toda la ROM.** Son cuatro objetos de 32x32
en 64 tiles, que es una fila de bloques de la grilla de nombres de OAM: un
objeto de 32x32 lee cuatro tiles de cuatro filas seguidas, así que en una fila
entran cuatro objetos y ni uno más. Más que eso tampoco había: la VRAM de
sprites que le queda libre al mapa 2 son 101 tiles y una caja de 96x96 son 144.
Que la caja **no dependa del mapa** es lo que deja que los 388
`ShowBattleAnimation` de los 81 mapas del juego compartan los mismos cuadros ya
convertidos en el cartucho.

**La animación se achica entera hasta entrar**, con su proporción, y cuánto se
achicó lo emite el conversor animación por animación. Las de la intro:

| animación | de       | a     | cuadros | en el cartucho |
|-----------|----------|-------|---------|----------------|
| 77        | 192x192  | 64x64 | 20      | 40 KB          |
| 78        | 144x176  | 52x64 | 24      | 48 KB          |
| 79        | 512x384  | 64x48 | 28      | 56 KB          |
| 82        | 536x416  | 64x49 | 28      | 56 KB          |

Achicarlas es lo que hace que las grandes existan: al 11% la 82 es un brillo y
no un incendio, pero está, y la alternativa medida era que no estuviera.

**Los cuadros van prerenderizados en el cartucho y se suben por DMA.** Uno cada
dos cuadros de consola, que es lo que dura un cuadro de RM2k: 2 KB, o sea
cuatro de las cinco poses del presupuesto del vblank, y se le **descuentan** a
`vq_tope` en vez de fijarlo, igual que un paso de la animación del ChipSet. Van
uno por cuadro y no un bloque seguido por animación porque 28 cuadros son 57 KB
y un banco tiene 32.

**Una paleta de sprite entera para ella sola**, como el cartel: sus quince
colores son de la animación y se pisan cuando empieza otra, así que un
personaje metido ahí cambiaría de color con ella. Los mapas 2 y 3 llenaban las
ocho, así que en los mapas que muestran animaciones **los personajes se
reparten siete**; lo que eso fusiona está en `assets/LIMITACIONES.md`. Si con
siete no entra el cronómetro manda el cronómetro, se vuelve a ocho y ese mapa
no dibuja: le pasa al mapa 9, y lo dice.

**Dónde cae.** Con alcance "pantalla" va al centro de la de la consola, que es
`DrawAt(screen_width / 2, screen_height / 2)`; con el otro, sobre el objetivo,
que es `GetScreenX()` y `GetScreenY(false)` menos medio personaje y la corrida
de `Animation::Position`. Esa corrida va **horneada en el ancla** que lleva la
tabla, así que la consola sólo resta. Un objetivo sin fila de NPC, o escondido,
no tiene de dónde sacar la posición y la animación no se dibuja.

Lo que se pierde está en `assets/LIMITACIONES.md`: la transparencia de una
celda, el destello sobre la animación y las `global`.

En la tanda lo cobran `animacion-dibujo` —la 78 sobre el héroe, con uno de sus
cuadros vacíos y los tres más cargados— y `animacion-evento` —la misma sobre
Manta, pegada al borde izquierdo, donde `emit_object` recorta la caja—. Son dos
casos y no uno porque en la ROM son dos caminos: el héroe sale de `hero_x` y un
evento de su fila, por `npc_de_evento`.
