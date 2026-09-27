---
name: "Carrera 3: lo que se ve y se oye"
description: "El cartel de los controles de la carrera como mensaje, y los efectos de sonido adentro de las rutas forzadas"
type: feature
assignee: taro
---

# Qué

El hito 3 de `todo/la-carrera-y-lo-que-sigue.md`: las faltas 4 y 5. Sale de
`main` en `69e66ed`.

* **El cartel de los controles** (`EscapeInst`): decidido, la opción (a). Un
  fork del 49 que cambia el `ShowPicture` por `ShowMessage` con el mismo
  texto que la imagen.
* **Los sonidos adentro de las rutas**: lo que pedía
  `los-sonidos-adentro-de-las-rutas.md`. El caso que lo pide es el puente de
  la carrera, pero general.

Números reservados: opcode 0x32 y la RAM lejana $7E79A0-$7E79BF. No hizo
falta ninguno de los dos.

# Status

2026-09-27, en `testing/`: hecho. Lo que queda es de taro, jugando: ver
abajo.

# El cartel

El texto, leído de la imagen del juego:

    Escape from Lashe City

    Use the UP and DOWN arrow keys to change lanes, and avoid the
    traffic!

    Fewer crashes means better rewards!

    Press any key to begin.

No entra en una ventana de 39 columnas por cuatro renglones, así que son dos
cuadros: el título y los controles; los choques y "Press any key to begin."
Fork en `parches/manual/mapas/Map0049.json`, capas del original.

**El `KeyInputProc` que esperaba la tecla se sacó**, y el `ErasePicture` de
la imagen que ya no está. El mensaje se cierra con A y el `KeyInputProc`
pedía después otra tecla más, con la pantalla negra y nada que lo dijera:
dos toques donde el original pide uno. La variable 151, donde guardaba la
tecla, no la lee ningún mapa ni ningún evento común (medido sobre `data/`).
Lo que se pierde: en el original cualquier tecla arranca, y acá sólo la que
cierra el mensaje.

# Los sonidos de las rutas

## Cómo quedó

La orden 35 de un `MoveEvent` va con dos bytes detrás, el índice del efecto
en `Temas.sonidos` —el mismo de `OP_SOUND`—, y la ROM lo toca con
`sonido_tocar`, el camino de `OP_SOUND`: con MSU-1 y sin él, sin costar un
cuadro. `sonido_heroe` en `ruta_del_heroe.s` y `sonido_ev` en
`rutas_de_eventos.s`. Se sigue tirando adentro de un salto (RM2k no lo
ejecuta ahí) y en la ruta propia de una página (no hay dónde poner el
operando; sólo la pide una, la del evento 40 del mapa 2).

**Antes hizo falta que la ruta del héroe dejara de copiarse** a un búfer de
32 bytes: el corte caía callado, y con operandos de dos bytes podía caer en
el medio de uno. Ahora es un puntero al bytecode, como la de un evento. Nueve
rutas del héroe de `release` pasaban de 32 (las seis del puente, el
`SceneDriver` del 14, una del 19 y una del 45). Salió más barato en banco 0
y en BSS.

## Qué entra en cada paquete, y qué no

El efecto entra en el paquete de audio del mapa, como el de un `PlaySound`,
así que compite con la música. Se aplicó la regla de taro —ningún
instrumento pierde tasa— mapa por mapa, comparando la tasa de cada par
tema-instrumento del reparto de `release` antes y después (un script que
envuelve `build_varios`). Donde costaba, los efectos que sólo pide una ruta
no entran: `SE_DE_RUTA_SIN_PAQUETE` en `tools/audio/snes_music.py`, con el
porqué de cada mapa.

Suenan, con el reparto de la música igual par por par:

    mapa  efectos de ruta nuevos en el paquete
    13    Blow5
    21    Blow4
    28    Switch2
    33    Blow1, Blow6
    51    Wind7 (el puente de la carrera; Annihilation2 ya estaba)
    60    Blow6
    61    Blow6
    62    Blow6

y en el 8 y el 19, donde ya estaban por las páginas. No suenan:

    3     Decision1, Blow1 a Blow6, Shot2 (la escena de evilrhys): no entran
          ni con las muestras al mínimo. Switch1 sí, por las páginas.
    7     Blow2: le baja a Deflector1 un instrumento de 22,9 a 16,4 kHz
    13    Flash1  } cada efecto nuevo en el cartucho le saca una entrada
    21    Earth4  } del directorio a la primera tanda de `copias`; con dos
                    nuevos bajan dos golpes 7 kHz. Earth4 además dura 1,36 s
                    y entraría recortado
    14    Kill3, Sword1, Sword2, Explosion4: con ellos `hzbreach` deja de
          ser tema de salida y el paquete no entra
    121   Earth8 (mapa de prueba): le baja 25 pares

Todos los que entraron duran menos de tres cuartos de segundo, así que
suenan enteros. Y **Annihilation2** —el golpe contra el borde de los
carriles y el del final del puente— pasó a entero, a 8 kHz: sonaba recortado
y con bucle. Más alto hace esperar a los efectos del 49 al `PlayBGM`.

Lo que quedaría para un día: la primera tanda de `copias` cuenta los efectos
del cartucho, así que cada efecto nuevo le cuesta a la música aunque su
paquete tenga lugar. Es lo que dejó afuera a Flash1 y a Earth4. Cambiar eso
es decisión sobre el reparto, no de esta tarea.

## Oído

En la carrera entera (`test_la_carrera_entera`), en el puente arrancan seis
Wind7 de 14 cuadros y un Annihilation2 de 87, y el golpe arranca 101 ticks
antes del `Teleport` al 53: suena entero. El audio del puente queda en
`pruebas/snapshots/playthrough/carrera-entera/el-puente.wav`.

# Pruebas

`just cartuchos` y `just pruebas` en verde sobre cada commit y sobre el
merge con `main`.

* **Nuevo: `pruebas/rpgmaker/test_sonido_en_ruta.py`**, con los casos
  `sonido-en-ruta`, `sonido-en-ruta-evento` y `sonido-en-ruta-salto` (mapa
  10, `Close1`, que ya estaba en su paquete): sobre el héroe suena con el
  tercer paso arrancando, sobre un evento suena, y adentro de un salto no
  suena y la ruta sigue. Con el conversor tirando la orden, las dos primeras
  dan rojo.
* `pruebas/abl/test_msu_efectos.py`: con el `.msu`, el de la ruta suena a 22
  kHz con la envolvente del WAV.
* `pruebas/abl/test_recorrido_carrera_golden.py`: fotografía los dos cuadros
  del cartel (`el-cartel-1`, `el-cartel-2`) y cuenta los efectos del puente.
  Sus fotos siguen sin bendecir.
* Ninguna golden de la tanda cambió.

# Qué tiene que probar taro jugando

* La intro de la carrera: el cartel en dos cuadros sobre negro, que se lee
  bien, y que un toque de A después del segundo arranca la carrera.
* El puente: los seis vientos mientras el auto cruza y el golpe al final,
  con MSU-1 y sin él.
* El golpe contra el borde de los carriles (apretar hacia afuera en el carril
  de un borde): que suene entero y no tartamudee.
* Donde se pueda llegar, los mapas que ganaron efectos: 33 (Blow1 y Blow6),
  21, 28, 60 a 62, 13.
