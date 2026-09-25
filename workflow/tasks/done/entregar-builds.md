---
name: "Los builds para taro salen de una receta"
description: "just entregar deja el release en /shared/builds/ con el .dbg y el rom/src/ del commit, para que Mesen2 muestre el fuente desde ahí"
---

Los builds de `/shared/builds/<fecha>-<commit>/` se armaban a mano y se
equivocaban. Ahora los arma `just entregar "<qué mirar>"`
(`tools/ensamblado/entregar.py`), y suman el `rom/src/` del commit, sacado con
`git archive`, que taro aprobó el 2026-09-25: Mesen2 busca el fuente subiendo
de carpeta desde el `.dbg`, así que con eso lo muestra también desde `/shared`.

# Hecho

- Se niega con cambios sin commitear en `rom/src/`, `tools/`, `parches/` o
  `data/`, y si no existe `/shared`.
- Si el directorio del commit ya existe, pisa sólo `abl.sfc`, `abl.sfc.dbg`,
  `LEEME.txt` y `rom/`: la partida que taro deja ahí se queda.
- Borra los directorios `<fecha>-<commit>` menos el nuevo y el más nuevo de
  los demás; lo que no tenga ese formato no lo toca.
- Compara la huella de las pistas con la de `/shared/msu/LEEME.txt`, corriendo
  el mismo comando que dice ahí. Si no coincide avisa al final y lo dice el
  LEEME del build; `--actualizar-msu` las copia, borra las que sobran y le
  cambia al LEEME de ahí el commit y la huella.

# Medido

- Contra un `/shared` falso en el scratchpad: los casos de arriba, más la
  huella que no coincide con y sin `--actualizar-msu`.
- La búsqueda de Mesen2 reimplementada (`mesen_busca.py`) sobre el `.dbg` del
  build: encuentra todos los `.s` y le faltan sólo `mapdata.inc` y
  `musicdata.inc`, que no se copian a propósito. En la interfaz de Mesen2 no
  se miró.
