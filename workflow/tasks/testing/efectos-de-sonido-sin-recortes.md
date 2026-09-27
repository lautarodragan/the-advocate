---
name: "Efectos de sonido sin recortes"
description: "Los efectos enteros y a más tasa donde no le cuesta a ningún instrumento; los demás, para que taro decida escuchando"
type: feature
assignee: taro
---

# Qué

Mejorar cómo suenan los efectos de sonido. Los límites que tenían —ver
`done/audio-sound-effects.md`— fueron intencionales, todos por la ARAM: van en
el paquete de audio de cada mapa, a 6 kHz y a lo sumo tres cuartos de segundo
(uno más largo repite sus últimos 0,4 s hasta durar lo que dura en RM2k).

**La condición es de taro**, del 2026-09-26: *"No me parece aceptable que
instrumentos pierdan calidad por un solo mapa, pero tampoco quiero perder
calidad en los efectos de sonido."* Desde el presupuesto por paquete los
efectos se restan antes de repartir, así que agrandar uno le baja la tasa a
las muestras de su paquete **si ese paquete es el que las limita**. La idea
que aprobó: elegir la calidad efecto por efecto, como con el trueno.

# Status

2026-09-26, en `testing/`: **hecho lo que no le cuesta nada a ningún
instrumento** —25 efectos enteros, casi todos a 22 kHz—, y **lo que costaría
un instrumento, medido y grabado para que taro decida escuchando**, abajo en
"Lo que decide taro". Lo que queda para él: escuchar
`/shared/audio/2026-09-26-efectos/` (tiene su `LEEME.txt`) y elegir.

Más tarde el mismo día taro eligió —todos enteros, a la media como mínimo—, y
con los números de eso a la vista cambió: **enteros sí, pero la media sólo
donde sea gratis para la música**. Está en la rama
`worktree-agent-afa6d748ca7a9d5ab`, sin mergear: ver "Los candidatos,
enteros" abajo. **Enteros a 6 kHz igual le cuestan a la música**; de las
propuestas de ahí taro eligió la del trueno, que deja la lluvia entera gratis.
Lo que les sigue costando la pelea y el mapa 3 espera a liberar entradas del
directorio, en otra tarea.

# Lo que estaba viejo el 2026-09-26

La tarea se escribió el 24, y desde entonces:

* **Una sola voz: viejo.** Son dos, la 6 y la 7, desde 8c9c182 (ver
  `rom/src/efectos_de_sonido.s`).
* **6 kHz, 0,75 s y el bucle de 0,4 s: seguía cierto** para todos menos el
  trueno de la apertura, que va entero a 22 kHz
  (`decisiones/el-trueno-va-entero-y-paga-la-lluvia.md`). El trueno **ya estaba en
  `main`**, no sólo en la rama del experimento como decía esa decisión.
* **El presupuesto de la ARAM** ya no es "cada efecto lo que entre": es por
  paquete y cada paquete llena la ARAM, así que no había lugar sobrante que
  usar sin mirar paquete por paquete. Ver `decisiones/un-solo-banco-de-muestras.md`.
* **`SE_ARAM` sigue muerto**: `build_varios` le pasa `1 << 30` a `build_efectos`.

**El caso de prueba —los truenos de la apertura cortados— ya estaba
resuelto.** Grabando la apertura quieta de `release` (955b186, sin MSU-1)
3000 cuadros y anotando por cuadro qué efecto suena en cada voz: los tres
truenos (cuadros 408, 1600 y 2638) suenan sus 144 cuadros enteros en la voz
6, con la lluvia en la 7, y la grabación baja 9 dB desde el pico hasta el
piso de la lluvia en vez de quedarse plana hasta el `KOF`.

# Los efectos que más se oyen

"Usos" son los `PlaySound` de las páginas de los mapas que lleva `release`
(un script sobre `data/maps/`); los de las animaciones de batalla y los de la
pelea no están contados. "22 kHz" es lo que pesaría entero a la tasa del WAV.

| Efecto | Mapas | Usos | Dura | 22 kHz | Hoy |
|---|---|---:|---:|---:|---|
| Sword3 | 26, 255 | 61 | 0,79 s | 9,8 KB | **entero a 22 kHz** |
| Bow2 | 2, 17, 20, 21, 26, 32, 133, 255, 261, 269 | 46 | 0,67 s | 8,4 KB | 6 kHz; espera: el 2 |
| Darkness | 2, 3, 32 | 16 | 1,38 s | 17,1 KB | 6 kHz con bucle; espera: el 2 y el 3 |
| Blow2 | 8, 11, 13, 19 | 12 | 0,28 s | 3,4 KB | 6 kHz; espera: el 19 |
| Holy5 | 2 y ocho más | 10 | 0,83 s | 10,3 KB | 6 kHz con bucle; espera: el 2 |
| Holy3 | 2, 11 | 9 | 0,54 s | 6,7 KB | 6 kHz; espera: el 2 |
| Switch1 | 3 | 9 | 0,40 s | 4,9 KB | 6 kHz; espera: el 3 |
| Decision1 | 2, 7, 17 | 8 | 0,25 s | 3,1 KB | 6 kHz; espera: el 2 |
| Earth2 | 2, 3, 74 | 8 | 1,22 s | 15,2 KB | 6 kHz con bucle; espera: el 2 y el 3 |
| Failure2 | 9 | 7 | 0,60 s | 7,4 KB | 6 kHz; el 9 no tiene lugar (herencia) |
| Earth8 | 14, 261 | 7 | 0,51 s | 6,4 KB | **entero a 22 kHz** |
| clap | 18 | 7 | 2,79 s | 17,3 KB (WAV a 11 kHz) | 6 kHz con bucle; el 18 no tiene lugar |
| Rain1 | 1 | 6, en bucle | 5,00 s | 62 KB | 6 kHz con bucle; espera: el 1 |
| Recovery4 | 23, 26 | 6 | 1,08 s | 13,4 KB | **entero a 22 kHz** |
| Success2 | 9, 10, 12, 16 | 6 | 1,30 s | 16,1 KB | 6 kHz con bucle; el 9 no tiene lugar |
| Item1 | 11, 13, 17, 20, 133 | 6 | 0,71 s | 8,8 KB | 6 kHz; el 20 no tiene lugar |
| Monster2 | 21, 26 | 5 | 1,52 s | 18,8 KB | **entero a 22 kHz** |
| Glass, Explosion4 | 3, 11, 19 | 5–6 | 1,5–1,9 s | 18–24 KB | 6 kHz con bucle; esperan: el 3 y el 19 |
| Thunder9 | 3, 20, 32 | 4 | 1,92 s | 23,8 KB | 6 kHz con bucle; espera: el 3 |
| La pelea: Attack2, Damage1, Evasion1, Escape, Item2, Bite, Monster1 | pelea | cada pelea | 0,4–3 s | 4,7–37 KB | 6 kHz; espera: la pelea |

"Espera: el N" es que el paquete N limita muestras y subirlo le baja la tasa
a algún instrumento: está en "Lo que decide taro". "No tiene lugar
(herencia)" es que su paquete tiene lugar solo, pero con algún tema que
puede venir sonando sus efectos **ya** no entran al lado, y agrandarlos haría
esperar más al `PlayBGM`: ver abajo.

# Lo hecho

**Lo que un efecto entero ocupa de más ya no entra en el presupuesto de la
música**: el banco se reparte contando cada efecto de `SE_ENTEROS` con el
tamaño de siempre, y lo de más tiene que entrar en lo que la música deja
libre en cada paquete donde está; si no, el conversor se corta diciendo cuál
(`_enteros_entran` en `tools/audio/snes_music.py`). Así ningún instrumento lo
paga **por construcción**, y si mañana la música crece en un paquete, el
conversor avisa en vez de bajarle la tasa a alguien. El trueno de la apertura
es la excepción, `SE_ENTEROS_PAGADOS`: taro lo eligió antes de esta regla, y
en `test-special` su paquete sí limita muestras.

**Qué entró**: los efectos que están sólo en paquetes que no limitan a ninguna
muestra, los que más se oyen primero, a la tasa más alta que entra —22.050
Hz, la de los WAV, o si no 16.000 u 11.025—, y sin que un paquete cuyos
efectos hoy entran al lado de un tema que puede venir sonando deje de entrar.
Primero se les sacó el bucle a todos los que lo tenían, y después se subió la
tasa. Son 24 más el trueno:

| Tasa | Efectos |
|---|---|
| 22 kHz | Sword3, Monster2, Recovery4, Flame5, Explosion5, Dark5, Cold2, Thunder6, Thunder4, Decision2, Earth8, Fall2, Buzzer1, Blow7, Failure1 |
| 16 kHz | Holy6, Kill3 |
| 11 kHz | Sword2, Dark1, Sword1 |
| 6 kHz, sin bucle | Numbness3, Refer Book, Earth1, Thunder5 |

**Lo que costó**, medido sobre `release` contra 955b186:

* **A los instrumentos, nada**: el reparto, las copias, la tasa y el tamaño de
  cada muestra salen iguales, en `release` y en `test-special` (un script que
  compara lo que devuelve `build_varios` en los dos commits).
* **Al fundido de entrada**, algunos cuadros más de negro en los mapas que
  crecieron —cuadros de hardware desde el pedido de salto hasta que termina
  el fundido, en el orden 7, 26, 261, 13, 269, 30, 33, 52, 11—: 7 de 93 a
  136, 261 de 131 a 165, 269 de 106 a 133, 33 de 99 a 117, 52 de 128 a 144,
  13 de 88 a 103, 30 de 92 a 103, 11 de 134 a 144; el 26 igual (163). Ningún
  paquete puede pasar de la ARAM, así que el peor no empeora: lo que cambia
  es que más mapas se le acercan.
* **Cartucho**: los efectos pasan de 211.509 B a 398.007 B.

Lo que se oye, contra el WAV original (la energía sobre 3 kHz, en dB contra
el total): antes, entre −22 y −55 dB, 20 a 40 dB por debajo del WAV; los de
22 kHz quedan a 1–6 dB de él, los de 16 a 2–3, y los de 11 más lejos (Dark1,
−26 contra −8). Los que siguen a 6 kHz suenan como estaban, pero enteros y
sin la meseta repetida.

**Lo que no cubre `just pruebas`**: nada de esto suena en la tanda. Lo miró un
script aparte que salta al mapa, calla la música y graba cada efecto saliendo
de la ROM, antes y después.

# Lo que decide taro

Cada candidato, con lo que pagarían los instrumentos. La cuenta rearma el
reparto de `release` con el efecto más grande (copias incluidas) y compara la
tasa de cada par (tema, instrumento); "bajan N" son los pares que pierden más
de 0,5 kHz, y los que más pierden van nombrados. Las copias se reacomodan con
cada cambio, así que un efecto chico puede mover muchos pares.

| Candidato | Pesa de más | Lo que paga |
|---|---:|---|
| **Rain1** a 11 kHz, con su bucle (mapa 1) | 2,1 KB | bajan 15: el taiko de `escape_newyork` y `vswar` 22,0 → 16,3, el polysynth 21,1 → 16,9, el piano (5 temas) 17,9 → 16,3 |
| Rain1 a 22 kHz, con su bucle | 6,8 KB | bajan 18: el polysynth de `escape_newyork` 21,1 → 12,6, el taiko 22,0 → 14,0, el piano 17,9 → 14,0 |
| Rain1 entera a 6 kHz, sin bucle | 14,3 KB | el polysynth de `escape_newyork` 21,1 → 8,4, el taiko → 10,4, el piano → 10,5 |
| **La pelea**: Attack2, Damage1, Evasion1 y Escape a 16 kHz | 12,1 KB | bajan 40: el bronce del tema de batalla 21,7 → 10,8, y platillos de otros temas 22 → 13,9 |
| Attack2 solo, a 22 kHz | 6,3 KB | bajan 42: el bronce de la batalla 21,7 → 16,3, las guitarras 19,9 → 15,2 |
| Damage1 solo, a 22 kHz | 5,5 KB | bajan 25: los mismos, parecido |
| Monster1 entero a 6 kHz | 7,6 KB | bajan 43: el bronce de la batalla → 16,3, las guitarras → 14,7 |
| Bite, Item2 y Monster1 enteros a 11 kHz | 24,2 KB | las guitarras de la batalla 19,9 → 8,2 |
| **Thunder9** entero a 6 kHz (mapas 3, 20, 32) | 3,9 KB | bajan 13, todos de `evilrhys` en el 3: arpa 12,2 → 9,5, cuerdas 12,5 → 10,0 |
| Thunder9 entero a 11 kHz | 9,4 KB | `evilrhys` a 6,1–6,6 kHz |
| **Darkness** entero a 6 kHz (2, 3, 32) | 2,1 KB | bajan 25: el polysynth de `TF3_1_awe` 16,9 → 12,6, `evilrhys` 12,5 → 11,1 |
| Darkness entero a 16 kHz | 9,9 KB | `TF3_1_awe` a 8,4, `evilrhys` a 5,9 |
| **Switch1** a 22 kHz (3) | 3,6 KB | bajan 13, `evilrhys`: 12,5 → 10,2 |
| **Bow2** a 11 kHz | 1,9 KB | bajan 12, `TF3_1_awe`: polysynth 16,9 → 12,6 |
| Bow2 a 22 kHz | 6,1 KB | `TF3_1_awe`: bajo 16,4 → 11,7, polysynth → 12,6 |
| Holy5 a 16 kHz | 4,9 KB | `TF3_1_awe`: polysynth → 12,6, bajo → 12,9 |
| Blow2 a 22 kHz (19) | 2,5 KB | bajan 41: un bajo de `hzbreach` y `vswar` 22,9 → 16,7, el polysynth → 16,9 |
| Explosion4 o Glass a 11 kHz | 6,5 / 9,4 KB | bajan 50: platillos 22 → 13,9, `evilrhys` a 6,6 |

**Bow2 y Holy5 tienen una trampa**: además del 2 están en el 26 y el 261, a
los que lo hecho les dejó ~1 KB libre. Subirlos pide también bajar algo de lo
hecho ahí (Monster2, Recovery4, Sword3 en el 26; Thunder4, Buzzer1 en el 261).

**Un camino más barato para los que comparten paquete**, como el trueno: un
alias —otra entrada del directorio para la misma WAV— entero sólo en los
paquetes que tienen lugar, y el de siempre en el que limita. Pero el
directorio está lleno (255 entradas, el tope del SRCN), así que cada alias
cuesta la última copia de `snes_music.copias`: **el primero, el `SPACE79` de
`T_ProjectJustice_DiscLoad` y `dcbest`, 17,9 → 16,0 kHz**; el segundo, la
copia de antes, y así. Liberar entradas es "darles a los efectos su propio
lugar en el directorio" (ver "Sin el techo del mapa 3" en
`done/la-calidad-de-la-musica.md`), que es rehacer `paquete_de_audio.s`.

**Los que no le cuestan a ningún instrumento pero sí a los efectos**: en
los paquetes 9, 18, 20, 28 y 32, con algún tema que puede venir sonando los
efectos del mapa **ya** no entran al lado y esperan al `PlayBGM`. Hay lugar
para agrandarlos —Cold7 a 22 kHz en el 32, Wind8 a 11 en el 28, Kill2 y Kill4
en el 20—, y lo que se paga es que esperen más: más efectos mudos entre la
llegada y el `PlayBGM`, y ese `PlayBGM` congelado más tiempo. No se hizo.

# Los candidatos, enteros (2026-09-26, en la rama, sin mergear)

taro, escuchando: *"tengo cero dudas de que tienen que tener su longitud
completa (todos)"*. Primero pidió la media (11 kHz) como mínimo; con los
números de eso —el tema de batalla y `evilrhys` a un cuarto, 196 pares
bajando— dijo que afectar tanto a la música no le agrada, y quedó así:
**todos enteros, a la media sólo donde sea gratis, y si no a los 6 kHz de
siempre**.

**No hubo ninguno gratis a la media**: cada candidato está en algún paquete
que limita muestras (el 1, el 2, el 3, el 19 o la pelea), y en ésos
cualquier byte de más le baja la tasa a alguien. Así que:

* **Enteros a 6 kHz** los que eran más largos que 0,75 s: Rain1, Bite,
  Item2, Monster1, Thunder9 (el del 3, el 20 y el 32), Darkness, Explosion4,
  Glass y Holy5 (`SE_ENTEROS_PAGADOS` en `tools/audio/snes_music.py`).
* **Igual que en `main`** los que ya sonaban enteros: Attack2, Damage1,
  Evasion1, Escape, Switch1, Bow2 y Blow2.
* **Sin alias**: con todos a una sola tasa no hacen falta, y cada uno cuesta
  una copia. `SE_DEL_MAPA` queda con el trueno del mapa 1, que ya estaba.

La primera versión —a la media, con alias en el mapa 3— está en 68c6818, y
sus grabaciones en `/shared/audio/2026-09-26-efectos-completos/`.

## La longitud completa sola ya le cuesta a la música

**Y no se puede evitar a 6 kHz**: los paquetes que limitan están llenos hasta
el margen, y un efecto entero a 6 kHz pesa unos 3.400 bytes por segundo,
contra los 2.529 del tope de 0,75 s con bucle. Para que la longitud completa
fuera gratis, Rain1 tendría que ir a menos de 1 kHz.

Cada uno solo, contra `main` (rearmando el reparto con ese efecto entero y
nada más cambiado):

| Efecto | Paquetes | De más | Lo que paga la música, solo |
|---|---|---:|---|
| **Rain1** (5 s) | 1 | 14,3 KB | `escape_newyork`: polysynth 21,1 → 8,4, taiko 22 → 10,4, piano 17,9 → 10,5, y siete más de ~16 a ~10. **Con el trueno a 8,8 kHz, nada**: ver abajo |
| Monster1 (3 s) | pelea | 7,6 KB | `T_VGFighterMAX_Masako`: bronce 21,7 → 16,3, guitarras 19,9 → 14,7 |
| Bite (1 s) | pelea, 8 | 0,8 KB | bronce 21,7 → 16,3 (por una copia), el resto ~1 kHz |
| Item2 (1,1 s) | pelea | 1,3 KB | bronce 21,7 → 16,3, toms 19,9 → 18,5 |
| **Los tres de la pelea** | pelea | 9,7 KB | guitarras 19,9 → 13,6, toms → 14,1, bronce → 16,3; veinte instrumentos |
| Thunder9 (1,9 s) | 3, 20, 32 | 3,9 KB | `evilrhys`: arpa 12,2 → 9,5, cuerdas 12,5 → 10,0 |
| Darkness (1,4 s) | 2, 3, 32 | 2,1 KB | `TF3_1_awe`: polysynth 16,9 → 12,6; `evilrhys` → 11,1 |
| Explosion4 (1,5 s) | 3, 19 | 2,4 KB | 54 pares por copias que se reacomodan: bajo de `hzbreach` y `vswar` 22,9 → 16,7, tuba de `Gaden` 17,2 → 14,7 |
| Glass (1,9 s) | 3, 11, 19 | 4,0 KB | 55 pares, los mismos, y `evilrhys` → 9,5 |
| **Los cuatro del mapa 3** | 3 | 12,4 KB | **`evilrhys` de 12,5 a 4,6**, y de rebote platillos de `Deflector1` y `Lunar_Pyramid` 22 → 13,9 |
| Holy5 (0,8 s) | 2, 8 más | 0,3 KB | una muestra de `TF3_1_awe` 16,4 → 15,7 |

**Todos juntos, como está en la rama** —con el trueno a 8,8 kHz—: bajan 175
pares, y **ninguno por el paquete del mapa 1**. Lo que queda es de la pelea,
el mapa 3, el 2 y el 19, y de rebote:

| Tema | Lo que más pierde | Lo limita | Instrumentos que bajan |
|---|---|---|---:|
| `evilrhys` | casi todo, 12,5 → ~4,5 | 3 | 13 |
| `T_VGFighterMAX_Masako` | guitarras 19,9 → 13,6, toms → 14,1, bronce 21,7 → 16,3 | pelea | 20 |
| `TF3_1_awe` | polysynth 16,9 → 12,6 | 2 | 12 |
| `escape_newyork`, `vswar` | polysynth 21,1 → 12,6 (muestra compartida con `TF3_1_awe`) | 2 | 7 y 9 |
| `hzbreach` | bajo 22,9 → 14,6 | 2 | 4 |
| `3D-Galax`, `Gaden` | bajo 16,7 → 13,3, tuba 17,2 → 14,7 | 19 | 13 y 6 |
| `cd2`, `Lunar_Pyramid`, `Deflector1`, `11h035` | ocarina 24,1 → 16,1, platillos 22 → 13,9 | 18+hzstream (copias que se reacomodan) | 4 a 11 |
| los otros 18 | ~16–20 → ~13–14, sobre todo muestras que limita la pelea | pelea | 1 a 9 |

Los que más pierden tienen pista de MSU-1, así que con MSU-1 no se oye.

## El trueno paga la lluvia (hecho)

**El trueno del mapa 1 va entero a 8,8 kHz en vez de 22**, y con eso la
lluvia entera es gratis: Rain1 entera a 6 kHz más `Thunder9@entero` a 8.800
Hz ocupan 63 bytes más que hoy, dentro del margen. Comprobado con el
conversor: con esos dos solos, el banco, las copias y la tasa y el tamaño de
cada muestra salen **iguales que en `main`**. Es de taro, el 2026-09-26: ya
había escuchado el trueno a menos calidad y le pareció bastante aceptable.
Ver `decisiones/el-trueno-va-entero-y-paga-la-lluvia.md`.

## Propuestas que quedan, medidas (sin implementar)

* **Menos de 6 kHz para los largos del mapa 3 y la pelea.** A 4 kHz enteros,
  los cuatro del mapa 3 cuestan 4,9 KB en vez de 12,4 (`evilrhys` a ~9,4 en
  vez de 4,6), y los tres de la pelea 3,9 en vez de 9,7 (bronce y guitarras a
  ~16,3 en vez de ~14). No es gratis ni así.
* **Lo de fondo**: liberar entradas del directorio para que las copias
  separen a los temas del paquete que los limita (casi todo el rebote), o
  los efectos largos por streaming, o versiones de calidad con MSU-1 (lo
  está haciendo otro agente).

## Carga y esperas

Los paquetes que limitan no crecen: lo que ganan los efectos lo pierde la
música. Medido saltando desde el título en el orden 1, 2, 3, 8, 11, 19, 20,
23, 26, 32, 261, 17, 255, 13 (cuadros desde el pedido de salto hasta el fin
del fundido), contra `main`: el 20 +13, el 32 +10, el 19 +9, el 11 +5; el 1
−10 y el 2 −11 (el trueno a 8,8 kHz pesa 14 KB menos, y la música del 2
bajó); los demás igual o uno menos. Cargar una partida en el mapa 1 entra en el
tope de `test_entrar_al_juego_devuelve_las_muestras_del_tema_del_mapa`, que
volvió a como estaba.

**Esperan al `PlayBGM` de más**: los efectos del 11 con `hzstream` o
`C3classi` sonando, que antes entraban, por Glass entero (faltan 1,9 y 3,6
KB; entero no puede pesar menos), y los del 20 con `3D-Galax` y los del 32
con `Lunar_Pyramid`, más que antes. El 28 con `wb3shop` mejora.

**Lo que no cubre `just pruebas`**: que los efectos suenen enteros; lo grabó
un script aparte, efecto por efecto, saliendo de la ROM, en
`/shared/audio/2026-09-26-efectos-enteros/`.

# Para escuchar

`/shared/audio/2026-09-26-efectos/`, con su `LEEME.txt`: los 24 de lo hecho,
antes y después, y los candidatos en dos o tres calidades, todos saliendo de
la ROM sin MSU-1, con la música callada, a volumen 100, tempo 100 y al
centro. Los candidatos salen de una ROM armada aparte que los mete en mapas
sin tema; en el juego pagarían lo de la tabla.

# Encontrado de paso

**Sin MSU-1, el `FadeOutBGM` calla también los efectos** hasta que arranca
otro tema. El trueno del final del mapa 3 es uno de los que caen ahí.
Arreglado el 2026-09-26: `tasks/testing/el-fundido-del-tema-calla-los-efectos.md`.

# Lo de antes: el 2026-09-24

La investigación de ese día (sobre 7303f2b) encontró las dos causas del
trueno cortado: la lluvia le robaba la única voz —se cortaba a los 73 de sus
144 cuadros, y una vez a los 7— y el tope con bucle le repetía el tramo más
fuerte hasta un `KOF` seco. taro lo oyó tartamudear aun sin lluvia. Se
arreglaron las dos: dos voces (8c9c182) y el trueno entero a 22 kHz, con los
números en la decisión. El resto de ese plan —efectos más largos en todos
los mapas, el fundido horneado como plan B, la tasa para todos— es lo que
reemplaza esta tarea: **efecto por efecto, y sólo donde no paga nadie**.
