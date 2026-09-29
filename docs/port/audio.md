# El audio

Qué pieza hace qué y dónde está su porqué. Todo lo demás vive en el código.

El audio lo maneja el **SPC700**, un procesador aparte con sus 64 KB de ARAM;
el 65816 no toca el DSP, sólo le habla al SPC700 por cuatro puertos. **La
lógica vive en Python**: el conversor decide qué nota va a qué voz, con qué
muestra y con qué envolvente, y la consola sólo reproduce.

    MIDI + SoundFont  --snes_music.py-->  musicdata.inc: el banco, un stream por
                                          tema, los paquetes de cada mapa
    stream por nota   --music_frame-->    escrituras al DSP, cuadro a cuadro
    escrituras        --dsp_music-->      el driver del SPC700

* **El arranque**: `spc_upload` (`tools/runtime/spc700.s`) sube por el IPL el
  driver y el directorio de muestras, nada más. Qué atiende el driver —pares
  (registro, valor) para el DSP, ternas para la ARAM, volver al IPL— está en
  `DRIVER`, en `tools/audio/snes_music.py`. Cuánto espera la ROM al encender
  es `BOOT_FRAMES` (`tools/runtime/far_ram.s`), y el conversor se corta si no
  alcanza: ver
  `workflow/decisiones/el-arranque-esta-dimensionado-para-el-paquete-de-arranque.md`.
* **El stream es por nota**: notas, releases, cambios de volumen o de altura,
  y esperas, que el 65816 expande a las mismas escrituras que antes iban en el
  stream. El formato está en "el formato por nota" de `snes_music.py` y los
  opcodes en `tools/protocol/music.toml`; `irq_music` (`tools/runtime/music.s`)
  corre un cuadro de música por cuadro de video.
* **Las ocho voces son de todos los canales** y se reparten nota a nota: una
  nota toma una voz libre o le roba a otra por prioridad. Ver `assign`,
  `_victim` y `_frame_order` en `snes_music.py`.
* **El volumen tiene un techo por tema**, medido y versionado en
  `rom/parches/auto/musica/techos.toml` (`just techos`): ver `read_ceilings`.
* **Las muestras salen del SoundFont** con el que se compuso el juego
  (`tools/audio/snes_samples.py`; `ABL_SOUNDFONT` apunta a otro), y las pasa a
  BRR Gunter, por `tools/audio/brr_samples.py`.
* **Un solo banco de muestras para todo el cartucho, subido de a paquetes, uno
  por mapa**, y cada muestra con el presupuesto de su peor paquete: `Bank` y
  `allocate` en `snes_music.py`, y el porqué en
  `workflow/decisiones/un-solo-banco-de-muestras.md`. Lo sube
  `package_load` (`tools/runtime/audio_package.s`) mientras la música suena;
  si el tema que viene sonando y el paquete nuevo no entran juntos, gana el
  tema: `workflow/decisiones/el-tema-que-suena-gana-y-los-efectos-esperan.md`.
* **El directorio del SPC700** tiene una entrada por muestra de la música
  —su número en el cartucho, que es el SRCN del stream— y detrás unos
  **lugares que comparten los efectos**: dos efectos que nunca van en el
  mismo paquete van al mismo lugar, así que alcanzan tantos como efectos
  tiene el paquete más cargado, y lo que queda del directorio es para las
  copias. `effect_places` en `snes_music.py`; la ROM anota qué efecto
  subió a cada lugar en `FAR_EFFECT_IN` (`record_effect`, en
  `tools/runtime/audio_package.s`).
* **Los efectos de sonido** —`PlaySound`— le roban dos voces a la música
  mientras duran, las que el reparto llena primero con la percusión:
  `tools/runtime/sound_effects.s` y `build_sound_effects` en `snes_music.py`. Los
  que van enteros y a más tasa —`[sound_effects.whole]` del archivo de
  proyecto, `rm2k-snes.toml`— se acomodan en lo que la música
  deja libre en cada paquete, así que no le bajan la tasa a ningún
  instrumento. Los de `paid_by_music` —el trueno de la apertura y los
  que taro eligió enteros aunque costaran— sí los paga la música de su
  paquete: `workflow/decisiones/el-trueno-va-entero-y-paga-la-lluvia.md`. Uno que en
  un mapa suena con otra muestra es un alias: `per_map`. Las tres son del
  juego, y cada entrada lleva su porqué en el archivo.
* **El `FadeOutBGM` baja el tema y nada más**: el volumen de cada voz de la
  música, o el de la pista del MSU-1, y nunca el general del DSP, que es
  también el de los efectos. `bgm_fade_tick`, en `tools/runtime/music.s`.
* **El MSU-1**: todo tema suena desde un PCM al lado de la ROM, y la ROM
  calla el SPC700 mientras tanto. El número de cada pista es el lugar del
  tema en `Music/` del juego —`msu_track` en `snes_music.py`—, así que no
  depende del cartucho; las arma `tools/audio/msu.py`. Con MSU-1, el paquete no sube las muestras de los
  temas con pista, salvo que la pista haya faltado en la tarjeta:
  `song_per_msu`, en `tools/runtime/audio_package.s`.
* **Los efectos con MSU-1**: mientras el SPC700 no toca música, los efectos
  tienen también las voces 0 a 5; y si el `.msu` es el de este cartucho, los
  de cada paquete se suben de ahí, enteros y a la tasa que les entra ahora
  que la música no ocupa la ARAM —una versión por paquete—. Sin MSU-1, o con
  otro `.msu`, lo de siempre. El reparto, en `tools/audio/msu_effects.py`; la
  ROM, en `tools/runtime/msu_effects.s`.

Qué prueba cubre qué: `rom/pruebas/rpgmaker/test_musica_*.py` corren la ROM
—las escrituras, el reparto, el paquete, los techos— y
`tools/tests/test_music_stream.py` mira el stream sin ROM.
