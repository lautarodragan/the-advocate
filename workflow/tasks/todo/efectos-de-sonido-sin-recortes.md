---
name: "Efectos de sonido sin recortes"
description: "Revisar los límites que se les pusieron a los efectos y ver cuáles se pueden levantar"
---

# Qué

Mejorar cómo suenan los efectos de sonido. Los límites que tienen hoy —ver
`done/audio-sound-effects.md`— fueron intencionales, todos por la ARAM:

* van en el paquete de audio de cada mapa;
* a 6 kHz y a lo sumo tres cuartos de segundo, y uno más largo repite sus
  últimos 0,4 s hasta durar lo que dura en RM2k;
* le roban la voz 7 a la música, así que suena uno solo a la vez.

La pregunta es cuáles de ésos se pueden quitar ahora, a qué costo, y con qué
riesgo.

# El caso de prueba

**Los truenos de la apertura**, apenas empieza el juego, suenan cortados. Es
muy notorio y bastante molesto —de taro, el 2026-09-24—, y es la prueba más
rápida para él: arrancar `abl.sfc` y escuchar.

# Status

Anotada el 2026-09-24, sin empezar. La investigación de abajo la hizo un
sub-agente ese día, sobre `main` en 7303f2b, sin tocar el árbol. Los números
son de ese día: al retomarla hay que volver a medirlos.

# Por qué se cortan los truenos

Los dispara el evento paralelo 12 del mapa 1 (`EV0013`) en bucle: `Rain1`,
espera 4 s, `Thunder9` con tempo 80, `FlashScreen` de 1,2 s, `Rain1` otra vez.
Aparte, el evento 8 (`EV0009`, switch 14) dispara `Rain1` cada 3,5 y 2,5 s.
`Thunder9` dura 1,9 s, que con tempo 80 en RM2k son 144 cuadros.

**Causa principal: el efecto que llega le roba la voz al que suena.**
`sonido_tocar` deja el pendiente y `se_despues` lo arranca en la misma voz 7.
En RM2k —y en EasyRPG, con 31 canales de efectos— la lluvia se suma al trueno.
Grabando la apertura de `abl` con snes9x durante 3000 cuadros:

| El trueno arranca | Lo pisa                     | Sonó | De  |
|-------------------|-----------------------------|------|-----|
| cuadro 330        | `Rain1` del mismo evento    | 73   | 144 |
| cuadro 1521       | `Rain1` del mismo evento    | 73   | 144 |
| cuadro 2559       | `Rain1` del evento 8        | 7    | 144 |

Con una variante que deja todos los efectos enteros, el trueno **se sigue
cortando a los 73 cuadros**: la duración sola no arregla el síntoma.

**Causa secundaria: el tope de 0,75 s y su bucle** (`build_efecto` en
`tools/audio/snes_music.py`). Del trueno quedan los primeros 0,75 s, y después se
repiten los 0,35–0,75 s, que son el tramo más fuerte, hasta cumplir los
cuadros. Termina en un `KOF` seco. La cola que decae se reemplaza por una
meseta y un corte. Esto sale de leer el WAV y el código; no se grabó aislado.

**Menor:** cada `Rain1` se re-dispara antes de terminar y vuelve a arrancar
desde su fade-in, así que la lluvia tiene baches periódicos.

No son la tasa, ni la música recuperando la voz, ni la ARAM del mapa 1.

**Confirmado sin la lluvia**, el 2026-09-24: una ROM de `main` en cf1ade0 con
el `PlaySound` de `Rain1` compilado como "(OFF)", grabada igual, 3000 cuadros.
Los tres truenos (cuadros 326, 1517 y 2555) suenan sus 144 cuadros y terminan
solos. Es `pruebas-manuales/2026-09-24-cf1ade0-sin-lluvia/`, para que taro lo
confirme de oído.

# Por qué se decidió cada límite

* **6 kHz, voz 7 y el bucle** son de `19e7dcc`, cuando los efectos compartían
  el banco con la música y entraban 5 de 38. El bucle se pensó para la lluvia.
  La voz se le roba a la percusión para que la música no sepa de efectos.
* **0,75 s (antes 1 s)** es de `45971df`, el del paquete por mapa. Ya no es por
  espacio sino por **tiempo de subida** en el fundido, a unos 55 KB/s.
* **Uno solo a la vez** está asumido también en la pelea: `BA_SE2_CUADROS`
  separa el segundo golpe 24 cuadros porque el nuevo pisa al anterior.
* `SE_ARAM = 16*1024` quedó muerto: `build_varios` pasa `1 << 30`.

# Lo que cuesta cada camino

**Subir tope o tasa para todos no entra**: rompe los mapas 2 y 3 en cualquier
variante con más duración o más tasa. El mapa 1 entra en todas, incluso con los
efectos enteros a 11 kHz. Por la cuenta —no medido en la ROM—, al entrar al 3
desde el 2 ya hoy no le entraría todo con el tema anterior fijo.

**Carga, medido:** con los efectos enteros el paquete del mapa 1 crece unos
18 KB, y el salto 4→1 suma 23 cuadros de negro, unos 800 B por cuadro.

**Código:** el runtime de efectos ocupa unos 350 B de banco 0 y su estado vive
en la RAM lejana. Duplicarlo para dos voces entra con holgura en todos los
cartuchos. Esto es una estimación: no se implementó.

**Ninguna prueba ejecuta lo que sale del DSP.** La tanda compara imágenes, y
`pruebas/UNTESTED.md` lo reconoce. Lo único que lo mide es una grabación
anotando `SE_CUADROS`/`SE_NUEVO` por cuadro, que hoy es un script descartable.

# Lo que decidió taro, el 2026-09-24

* **Todos los mapas tienen que tener todos sus efectos.** Nada de efectos
  enteros sólo donde entran. Si algo no entra, el camino es deduplicar o
  comprimir las muestras, con el MSU-1 como expansión opcional si sin él
  pierden demasiada calidad.
* **El fundido en vez del bucle es plan B.** Si no se puede decidir por
  programa qué efecto se repite y cuál se apaga, pide decidirlo a mano, y eso
  no se encara ahora. Hay que apuntar a que no haga falta.
* El mapa 3 quedó como tarea aparte: `al-mapa-3-le-falta-un-efecto.md`.

# Plan, en orden

1. **Dos voces de efectos, la 6 y la 7**, asignando la libre primero, si no la
   que termina antes, y la misma muestra re-disparada reusa su voz. Arregla el
   corte del trueno por la lluvia. No cuesta ARAM.
   * Costo: mientras suenan dos efectos, la percusión se queda sin voces. En la
     apertura la 7 ya está tomada casi siempre por la lluvia; lo nuevo es perder
     la 6 durante los 2,4 s de cada trueno. Con MSU-1 no cuesta nada.
   * Toca `dsp_musica` y su sombra, `se_antes`/`se_despues`, `se_callar`, el
     camino del MSU-1 y `BA_SE2_CUADROS`. `test_batalla.py` lee `SE_NUEVO`.
   * Conviene hacer una receta de la grabación, porque es la única red.
2. **Efectos más largos en todos los mapas**, sin el bucle de 0,4 s. Como
   subir el tope para todos no entra en los mapas 2 y 3, esto pide antes
   deduplicar o comprimir muestras. Se acerca a
   `wishlist/presupuesto-de-muestras-por-paquete.md`.
3. **Plan B, si lo anterior no alcanza:** fundido horneado en vez de bucle para
   los efectos que decaen, con la lluvia todavía en bucle. Sólo si se puede
   decidir por programa cuál es cuál.
4. Más adelante, la tasa: subirla para todos tampoco entra hoy.
