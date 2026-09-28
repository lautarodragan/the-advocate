---
name: "La partida guardada con MSU-1 arranca muda"
description: "Guardar mientras suena una pista del MSU-1 guarda music_apagada en 1, y al cargar la partida no suena nada"
type: bug
---

Visto leyendo el código el 2026-09-26, al arreglar "la pista del título sigue
al empezar"; no se corrió. La partida guarda `music_apagada` y `tema_actual`
(`partida_tabla`, en `rom/src/banco1.s`), y con una pista del MSU-1 sonando
`music_apagada` vale 1 porque el SPC700 está callado a propósito. Al cargar,
`music_boot_ya` (`rom/src/musica.s`) ve `music_apagada` y toma el camino
callado: la partida arranca muda hasta el próximo `PlayBGM` o el tema propio
de un mapa. Antes del arreglo de la pista del título seguía sonando la pista
del título, que tampoco era la que correspondía.

Es la misma pregunta que ya contestan `mapa_tema_callar` y `op_battle`
—"¿está sonando?" es `MSU_SUENA` o `music_apagada` en cero—, y se la puede
contestar al guardar o al cargar. Cobrarlo con una prueba con `msu=True`
(`pruebas/abl/test_msu.py`), guardando en un mapa con tema de pista.

## Hecho, el 2026-09-27

**La intención**, por `git blame`: `music_apagada` y `tema_actual` entraron a
`partida_tabla` en `a51d2980` (2026-09-10), con el byte queriendo decir "se
guardó sin música". El MSU-1 llegó al día siguiente (`e6bb4bc`) y le dio a
`music_apagada` un segundo sentido —"el SPC700 está callado porque suena la
pista"—, y la partida lo siguió guardando tal cual.

**El arreglo**, en `guardar_partida` (`rom/src/partida.s`): con `MSU_SUENA`
prendido, `music_apagada` se pone en cero mientras dura la copia a la SRAM y
se repone después, con las interrupciones cerradas —si `irq_musica` lo viera
en cero correría el stream del SPC700—. Lo guardado vuelve a ser "¿está
sonando?", sin decir por dónde: al cargar, `music_boot_ya` llama a
`music_start`, que elige la pista si hay MSU-1 y el SPC700 si no.

**El formato no cambia**: los mismos bytes en el mismo lugar, con el sentido
que ya tenían sin MSU-1. `PARTIDA_BYTES` y `PARTIDA_FIRMA` salen iguales, así
que no se subió nada. Una partida guardada con la pista sonando **por un build
de antes** sigue cargando muda: guardó un 1, y al cargar no hay forma de
distinguirlo de un silencio de verdad.

**Los cruces**, medidos con la prueba:

* con MSU-1 a con MSU-1: vuelve la pista. Antes, muda.
* con MSU-1 a sin MSU-1 (un `.srm` del FX Pak en un emulador sin pistas):
  el tema por el SPC700, con sus muestras en la ARAM. Antes, muda.
* sin MSU-1 a con MSU-1: la pista. Ya andaba —se guardaba un 0—; queda
  cobrado.

**La prueba**: `test_la_partida_guardada_vuelve_con_su_tema`, en
`pruebas/abl/test_msu.py`, con las tres variantes. Llega al mapa 26 —prende
`KSSMKEND`, que tiene pista—, guarda por el menú, pasa la SRAM a otra consola
si la combinación lo pide, y carga con "Resume the Story". Contra la ROM sin
el arreglo, `msu-a-msu` y `msu-a-spc700` dan rojo (`music_apagada` en 1 y
`MSU_SUENA` en 0 al cargar) y `spc700-a-msu` verde.

## Qué tiene que mirar taro

Con las pistas al lado, en Mednafen (`-force_module snes_faust`) y en el FX
Pak: llegar a un lugar con tema de pista, guardar, resetear, "Resume the
Story", y oír que el tema vuelve. Y el cruce que importa en la práctica: el
`.srm` guardado en el FX Pak, cargado en Mednafen **sin** las pistas, tiene
que sonar por el SPC700. Una partida guardada con un build anterior mientras
sonaba una pista va a cargar muda igual: hay que guardarla de nuevo.
