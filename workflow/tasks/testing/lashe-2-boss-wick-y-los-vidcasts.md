---
name: "Lashe 2: Boss Wick y los vidcasts"
description: "Del vecino de Talan al favor de Boss Wick: mapas 40 a 45 y las transiciones"
type: feature
assignee: taro
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

# Status

2026-09-27, en `testing/`: hecho sobre `bd5b6a6`, en la rama del agente. Lo
que queda es de taro: jugarlo (abajo, "Qué tiene que mirar taro jugando") y
mirar las fotos sin golden de `pruebas/snapshots/playthrough/lashe-wick-*/`.
Lo que sigue de acá abajo hasta "Lo hecho" es el plan como estaba.

# Lo que faltaba

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

# Lo hecho

**Los seis mapas en `MAPAS_DEL_JUEGO`** (`tools/ensamblado/cartuchos.py`), y
con eso en `release`. Todas sus páginas compilan, y también la que el hito 1
había dejado muerta: la puerta del vecino, página 3 del evento 13 del 37.
Ninguna página de estos mapas queda sin compilar. Lo que compila y no hace lo
del original: el "REC" del 45 (`ShowPicture 'ABLrec'`, deuda decidida) y
`ChangeHeroTitle` a 'Fugitive' (no hay pantalla que lo muestre).

**`ChangeScreenTransitions`**, con un opcode nuevo, `OP_TRANSITION` (**0x2E**),
y dos bytes de RAM lejana, `TRANSICION_BORRAR` y `TRANSICION_MOSTRAR`
(**$7E7920** y **$7E7921**, del tramo $7E7920-$7E793F). El conversor decide:
el 17 es el mosaico, el resto es el fundido (el zoom incluido, como decidió
taro); el corte (19), "ninguna" (20) y los de la pelea no compilan, y no hay
ninguno en `release`. El mosaico se escribe en el vblank desde
`fundido_mosaico` (`rom/src/transicion_del_teletransporte.s`), atado al brillo
como el de la pelea; `fundido_tick` no se tocó. No viaja en la partida: entre
la página que la pone en mosaico y la que la devuelve no hay un momento en que
se pueda guardar (ver el comentario en `ram_lejana.s`). La divergencia
—el mosaico oscurece, los sprites no se pixelan, el zoom es fundido— está en
`divergencias/las-transiciones-del-teletransporte.md`.

**El tope de teletransportes encadenados, de 8 a 32** (`SALTOS_MAX` en
`rom/src/pagina_cero.s`). De la puerta del vecino hasta volver al 37 son doce
saltos entre mapas sin que el jugador tome el control, y con 8 la ROM entraba
en pánico en el segundo paso por el 43: la pantalla se congelaba con el
mensaje de Talan.

**Los líderes posibles se miran al final de cada tanda de
`ChangePartyMembers` seguidos**, no después de cada comando
(`_cambios_del_mapa` en `tools/port/snes_convert.py`). El 41 saca a todos
antes de volver a meter a Talan, en dos páginas seguidas, y la simulación los
dejaba pasar por líderes a Arden, Saldra y AG7: tres personajes más en todos
los mapas del cartucho y dos goldens de la tanda (`tram`, `mecanico`) con los
colores corridos. Con la regla nueva también dejan de ser líderes el 12 y el
13 (Core y Manta) en `release`, que sólo lo eran por lo mismo —un paso
intermedio de los grupos de prueba en el mapa 4—; la tanda no movió ninguna
golden.

# Lo medido

**Banco 0** (`TABLAS`, el método de `AGENTS.md`): `release` de 342 B libres a
**317**; `test-special` tiene 1041. **Banco 1**: el último símbolo pasa de
$01:F874 a $01:F8C1 (~1,85 KB libres). **BSS** y **ZEROPAGE** sin cambio.
**Cartucho**: de 2.747.611 B (65,5%) a 2.857.944 (68,1%), +110 KB, sumando
los segmentos del `.dbg`.

**Cuadros perdidos**, fuera de los fundidos, en la escena entera por la rama
de aceptar (el jugador nunca camina por estos mapas): 40, 34 en 3390 ticks
(el peor tramo de 10 ticks, 5); 42, 8 en 680, de una vez; 43, 44 y 45, cero; el
41 está siempre adentro de un fundido.

**Audio.** `Kfmus5` y `tsmedit` entran con sus muestras y con pista de MSU-1
(la 100 y la 204). Comparando las tasas del `conversor.log` contra `main`,
casi nada cambia: `PCKBS50A` en `TF3_1_awe` pierde su copia (15,2 -> 14,0 kHz),
`EORG268` en `Deflector1` gana una (16,4 -> 22,9), y el resto se mueve una o dos
décimas —los platillos de `evilrhys` de 4,6 a 4,5—. El conversor no sabe que
`Kfmus5` sigue sonando del 41 al 45 —sale de la página del 37 y la regla de
`temas_heredados` corta en el 41, que tiene `PlayBGM` propios— así que esos
paquetes no le reservan lugar. Nadie lo escuchó sin MSU-1: va con la pasada
de audio (`todo/el-audio-despues-de-lashe-city.md`). `just techos` rehecho: ningún
tema recorta.

# Pruebas

* `pruebas/abl/test_recorrido_lashe_wick_golden.py`: desde el 37 con el 151,
  la puerta, la escena 1, los vidcasts, el video, y el favor por las dos
  ramas: **aceptar** con Saldra (164, el cirujano, 267, y el 41 no lo hace
  renguear) y **rechazar** con Arden (162, sin 164 ni 267, y un punto menos de
  velocidad). Cobra por la RAM la transición que deja cada página, el grupo al
  volver y el comentario del compañero, que apaga el 163.
* `test_transicion` en `pruebas/rpgmaker/test_comandos_golden.py`: los casos
  `transicion-mosaico` y `transicion-zoom`, con goldens nuevas a mitad de cada
  rampa, y los mismos en `test_cores.py`.

Las fotos, sin golden:

    lashe-wick-acepta   la guarida, el mosaico de los vidcasts, el video,
                        el favor, el cirujano, de vuelta en el 37
    lashe-wick-rechaza  lo mismo sin el cirujano

Lo que **no** cubren: la segunda confirmación con "No" (que también prende el
162), la rama sin compañero, y el Bum del 37 con el 164 (la página 4).

# Qué tiene que mirar taro jugando

La escena de Wick entera y las dos ramas del favor; el mosaico al saltar
dentro de los vidcasts (con el héroe nítido encima); la entrada a los vidcasts
con fundido donde el original hace zoom; el video de seguridad sin el "REC"; y
cómo suenan `Kfmus5` y `tsmedit` con y sin MSU-1.
