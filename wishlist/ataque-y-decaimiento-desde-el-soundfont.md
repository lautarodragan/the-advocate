# Qué

Leer el **ataque y el decaimiento** de cada instrumento del SoundFont, en vez de
sacarlos de las ocho familias de `sdsp.py`.

# Status

Anotado, sin empezar. Estaba en "Lo que falta del port" de `ESTADO.md`.

# Por qué

Las ocho familias de `sdsp.py` se eligieron **a ojo, cuando el banco era
sintético**. El SoundFont trae los suyos por instrumento y todavía no se leen.

**El release no entra acá**, y no por olvido: el del ADSR del DSP no se puede
configurar y la nota se suelta por GAIN, que es un problema resuelto y con su
propia explicación —"Cómo se suelta una nota", en `README.md`—.
