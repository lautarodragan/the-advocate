# Qué

**El runtime y las herramientas son un "RPG Maker 2000 PLUS"**: corren los
juegos de RM2k tal cual —compatible hacia atrás— y suman features que RM2k
no tiene. Esas features van **al proyecto central**, disponibles para
cualquier juego, y no como cambios propios de cada juego.

# Por qué

De taro, el 2026-10-02: "cualquier feature nuevo debería ser agregado al
proyecto central, cuando terminemos de separarlo del ABL. La idea no es que
cada juego pueda introducir cambios custom —aunque no estaría mal, pero no
es lo que yo tenía en mente—, sino tener una especie de RPG Maker 2000 PLUS,
que sea backwards-compatible pero agregue features —algo así como el 2003—,
y que cualquier juego se pueda beneficiar de ellas".

# Cómo se aplica

- **Una feature que RM2k no tiene es del motor**, aunque la pida ABL: la
  velocidad con L y R (que se apaga con `--no-speed-keys`), el menú custom
  del wishlist, una fuente para alta resolución. Un juego la prende o la
  apaga desde su `rm2k-snes.toml`; no la escribe.
- **Lo de un juego** sigue siendo de su proyecto: sus parches, sus casos, sus
  goldens, qué mapas lleva.
- **Agregar una feature es agregar opcodes** al bytecode de eventos, no
  declarar un bytecode nuevo: el bytecode es el formato de este runtime, no
  de RM2k.
- Ver `las-herramientas-se-separan-de-abl.md` y
  `el-juego-se-juega-sin-msu-1.md`.
