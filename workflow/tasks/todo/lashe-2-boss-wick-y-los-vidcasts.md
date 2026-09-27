---
name: "Lashe 2: Boss Wick y los vidcasts"
description: "Del vecino de Talan al favor de Boss Wick: mapas 40 a 45 y las transiciones"
type: feature
---

# Qué

El hito 2 de `lashe-city-hasta-la-carrera.md` —el contexto y lo medido están
ahí—. Va después del 1 y en paralelo con el 3.

El tramo obligatorio de las tres ramas: la puerta del vecino en el Sector 35
(evento 13 del 37, pide el 151 del pad de Talan) lleva a la guarida de **Boss
Wick**, los vidcasts, el video de seguridad con la escena del director, y **el
favor**: Wick te cura el tobillo si aceptás deberle uno. Prende el 161
(`DoneWithVidcast`), que las tres ramas piden para irse.

Mapas: **40** (Boss Wick's Den), **41** (ScreenToneAdjuster, negro), **42**
(The Vidcasts), **43** (Vidcasts Office: los tiles del 34), **44** (Talan Stats,
negro) y **45** (Security Footage: el 19 entero, tiles y eventos). El 46 y el 98
no los alcanza nadie. El orden en que se pasa por ellos está en el plan,
"Tramo por tramo".

**El mafia boss no es una pelea.** Es el evento 7 del 40: dos
`ShowChoice` anidados; aceptar prende el 164 y corre la página 5 (el cirujano,
`ChangeHeroTitle` a 'Fugitive', el 267); rechazar prende el 162. Los dos
terminan en el 41 y de ahí al 37, donde el compañero comenta (evento 17, switch
163).

# Lo que falta

Con los seis mapas en el cartucho compilan todas las páginas menos cuatro, y
las cuatro caen por lo mismo:

**`ChangeScreenTransitions`** (10690): la página 1 del 40 (la escena 1 de
Wick), la 4 (el favor), la 1 del 42 y la 1 del 45. Pide `[0, 16]`/`[1, 16]`
—zoom para borrar y para mostrar en el teletransporte—, `[0, 17]`/`[1, 17]`
—mosaico— y `[0, 0]`/`[1, 0]` —volver al fundido—. Es `SetTransition` en
EasyRPG (`game_system.cpp`, la tabla `fades`). En todo el juego frena 15
páginas y destraba 14 él solo.

Lo que se puede hacer y lo que no (pregunta 4 del plan):

- **el mosaico es de la consola**: el registro `MOSAIC` hace los bloques, y
  crecerlos durante el fundido es barato;
- **el zoom no existe en modo 3**; lo razonable es fundido y declararlo en
  `divergencias/`;
- la transición elegida es estado que cruza el teletransporte: va a la RAM
  lejana (la BSS tiene ~100 bytes libres), y se guarda en la partida si el
  original la guarda.

Y la deuda de `wishlist/las-otras-transiciones-de-rm2k.md` se achica: el
mosaico deja de estar ahí.

**Dos temas nuevos sin muestras en el banco**: `Kfmus5` (la guarida, suena
con el 8% de las notas por el SPC700) y `tsmedit` (el cirujano, 53%). La
pista de MSU-1 la tienen solos —desde el 2026-09-26 todo tema tiene la suya,
con el número que da `pista_msu`—, y se mira cómo suenan sin MSU-1.

**El "REC" del 45** (`ShowPicture 'ABLrec'`, un paralelo que lo hace
parpadear): la ROM lleva un cartel solo y es el de "One year previously", así
que queda aceptado sin hacer (pregunta 5).

# Números a repartir

Un opcode (la transición) y dos pistas de MSU-1. Una dirección de RAM lejana.

# Pruebas

- **Casos de tanda** para la transición: un `Teleport` con mosaico y uno con
  zoom, con goldens a mitad del efecto —fuera de los primeros veinte cuadros de
  un mensaje—.
- **El recorrido**: desde el 37 con el 151 puesto —o entrando al 39 y tocando
  la computadora—, hasta volver al 37 con el 161 prendido, **por las dos
  ramas** del favor (necesita el hito 0 para "Refuse"). Comprobar 162 o 164 y
  267, y fotos en la escena 1, el video, y el cirujano.
- La prueba de dos núcleos (`test_cores.py`) sobre la transición nueva: el
  estado vive en RAM que hay que inicializar.

# Qué tiene que mirar taro jugando

La escena de Wick entera y las dos ramas del favor; el mosaico al entrar a los
vidcasts; el zoom como fundido; el video de seguridad sin el "REC"; y cómo
suenan los dos temas con y sin MSU-1.
