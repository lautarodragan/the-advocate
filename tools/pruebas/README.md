# Las pruebas de las herramientas

    just -f tools/justfile pruebas               todas; parado en tools/, `just pruebas`
    just -f tools/justfile pruebas -k escapes    lo de siempre de pytest pasa tal cual

Las de Python: el conversor, el ensamblado y el motor, probados sin el juego.
Las de los proyectos de Rust tienen su receta cada uno (`protocolo-pruebas`,
`ditto-pruebas`…).

**Una prueba va acá si no lee el juego** —ni `ABL_GAME_DIR`, ni el RTP—, **ni
`data/`, ni `parches/`, ni un cartucho armado, ni la tanda**. Todo lo que
mira lo arma adentro, o lo lee de `tools/` y del motor. Las que necesitan
algo de eso son de las pruebas de A Blurred Line, en `pruebas/` de la raíz,
aunque prueben una herramienta. Un archivo que mezcla se parte: los dos lados
del mismo tema pueden tener el mismo nombre —`test_bancos.py`— o uno que
diga qué mira del juego —`test_protocolo_contra_el_juego.py`—.

No corren ninguna ROM y tardan menos de un segundo, así que van en serie y
sin xdist. La tanda de la raíz no las corre, y ellas no necesitan nada de
ABL: por eso tampoco dependen de `cartuchos`.

Lo que sí usan de afuera: `test_protocolo.py` corre `protocol` del PATH, y
`test_musica_stream.py` lee el SoundFont de las muestras con `gunter`, del
PATH, de donde diga `ABL_SOUNDFONT`. El SoundFont no es del juego sino
material del conversor, aunque la variable todavía lleve el nombre de ABL.
`test_protocolo.py` y `test_sustituciones.py` leen además el motor, en
`rom/src/`, que viaja con las herramientas.

## Qué prueba cubre qué

Todo `test_*.py` de esta carpeta tiene que estar nombrado acá, y todo lo
nombrado tiene que existir: lo cobra `test_indice.py`.

* `test_protocolo.py`: el bytecode: las declaraciones, los generados al día,
  que las dos puntas digan los mismos números y que el motor no use un opcode
  sin declarar
* `test_ensamblar.py`: `ensamblado/ensamblar.py`: el checksum, la cabecera,
  los símbolos del `.dbg` y qué fuentes se incluyen
* `test_bancos.py`: el acomodo de bancos que hace el conversor, y el mapa de
  memoria del `.cfg`
* `test_repartos.py`: los repartos de VRAM, su orden y los mapas que los
  estrenaron
* `test_sustituciones.py`: el tope de `TileSubstitution`, igual en el
  conversor y en el motor
* `test_textos.py`, `test_escapes.py`: los cuadros de texto rearmados y los
  escapes `\|` y `\^`
* `test_temas_heredados.py`: qué tema puede venir sonando al cargar el
  paquete de cada mapa, que es lo que el reparto le reserva
* `test_musica_stream.py`: el stream que arma el conversor: a qué voz va cada
  nota, cuándo se suelta y con qué envolvente
* `test_indice.py`: que esta lista esté al día
