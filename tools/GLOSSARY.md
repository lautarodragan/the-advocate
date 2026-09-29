# Glossary

The tools were written in Spanish and are being translated. This file fixes
how each recurring term is translated, so that every module says it the same
way. When a term is missing, pick one, use it consistently, and add it here.

| Spanish | English | Notes |
|---|---|---|
| cartucho | cartridge | a ROM build: `release`, `test-special` |
| tanda | test suite, suite | the whole pytest run |
| caso | case | a test case under `pruebas/casos/` |
| golden | golden | a frozen capture a test compares against |
| conversor | converter | `snes_convert` and friends |
| runtime, motor | runtime | the 65816 code in `runtime/` |
| perilla | setting | a value from the project file |
| archivo de proyecto | project file | `rm2k-snes.toml` |
| huella | fingerprint | hash of the inputs of a build |
| sello | stamp | what a build records about its inputs |
| caché | cache | |
| reparto | VRAM layout, layout | how VRAM is split among BGs and sprites |
| capa | layer | a map layer (lower, upper) |
| paleta | palette | |
| líder | leader | the event that owns a CGRAM palette |
| ranura | slot | save slot, equipment slot, palette slot |
| banco | bank | ROM or WRAM bank |
| reserva | reservation | a reserved WRAM range |
| fundido | fade | |
| cuadro | frame | a hardware frame (60 per second) |
| vuelta, tick | tick | one step of the game loop |
| mapa de debug | debug map | map 900 |
| pelea, batalla | battle | |
| tropa | troop | |
| héroe | hero | the party leader on the map |
| grupo | party | |
| evento | event | |
| página | page | an event page |
| orden de ruta | move command | a command in a move route |
| comando | command | an event command |
| tinte | tint | a screen tint |
| destello | flash | a screen or character flash |
| cronómetro | timer | |
| techo | volume ceiling | the per-song volume limit |
| muestra | sample | a BRR sample |
| tema | song | a music track as RM2k calls it |
| pista | track | an MSU-1 audio track |
| efecto | sound effect | |
| ventana | window | a message or menu window |
| fuente | font | |
| glifo | glyph | |
| entregar | deliver | hand a build to a person |
| parche | patch | a file under `parches/` |
| volcado | dump | the JSON dump of the game |
| verificado | verified | always names what was run |
| armar, armado | build, built | |
| al día / viejo | up to date / stale | a cartridge against its inputs |
| arnés | harness | the test harness |
| cobrar (una regla) | enforce; catch (a bug) | "the suite caught it" |
| acomodo de bancos | bank packing | |
| hueco / relleno / pieza | gap / padding / piece | |
| presupuesto | budget | |
| tope | cap | |
| intérprete | interpreter | the event bytecode interpreter |
| rutina | routine | |
| llamador | caller | |
| pila | stack | |
| se lleva X | clobbers X | registers |
| escritorio (variables prestadas) | scratch space | |
| lazo | loop | |
| refresco | refresh | |
| sombra | shadow | a RAM copy of a register |
| espejo rápido | fast mirror | |
| trampa (el stub de LZ2) | trampoline | |
| flujo | stream | LZ2, audio |
| bitácora | log | |
| celda | cell | a text cell |
| grilla | grid | |
| renglón | line | |
| cuadro de texto | text box | "frame" is only the hardware frame |
| marco (de ventana) | border | not "frame" |
| desplazamiento | offset | |
| autocierre | auto-close | |
| flanco | edge | a button edge |
| cruceta | D-pad | |
| enrutador | router | map 4 |
| mapa de arranque | boot map | |
| página de prueba | test page | |
| página automática / paralela | autostart / parallel page | |
| evento común | common event | |
| orden (de pelea o de menú) | command | also "orden 34" = command 34 |
| elección | choice | |
| manejador | handler | |
| quieto | still | an event that doesn't move |
| giro / ranura de giro | turn / turn slot | TURN in `events.py` |
| ele / pata / codo | L-shape / leg / elbow | a diagonal step |
| cartel (ShowPicture) | picture | not "sign", which is the arithmetic sign |
| fondo de batalla | battle backdrop | |
| respaldo (liviano) | (light) fallback | |
| escena | scene | the battle scene |
| combatiente | combatant | |
| blanco | target | |
| alcance | scope | of a skill |
| tiro / azar | roll / randomness | |
| acierto | hit rate | |
| caído | fallen | |
| huida | escape | |
| oculto | hidden | |
| botín | drop | |
| página de tropa | troop page | |
| disparador | trigger | |
| posada / tienda / saludo | inn / shop / greeting | |
| pantalla de ranuras | slot screen | |
| ayuda | help window | |
| barra | bar | the cursor bar |
| RAM lejana | far RAM | |
| ROM jugable | playable ROM | |
| deuda | debt | |
| hablante | speaker | |
| cola (de escapes, del release) | tail | |
| umbral | threshold | |
| sacudida | shake | |
| fusión / volteo / espejado | merge / flip / mirrored | |
| degradé | gradient | |
| trama / damero | dither / checkerboard | |
| hornear | bake | |
| podar | prune | |
| receta (del fork) | recipe | |
| pasabilidad | passability | |
| asignador | allocator | |
| capa de abajo / de arriba | lower / upper layer | |
| reparto (de paletas, de CGRAM) | split | "layout" is only for VRAM |
| prestar paleta | lend a palette | |
| corrida (de tiles) | run | |
| dibujo (de una animación) | drawing | |
| banco de poses | pose bank | |
| tira | strip | |
| paquete de audio | audio package | |
| tema de salida / tema aparte | exit song / separate song | |
| efecto entero | whole sound effect | |
| aire | headroom | |
| recortar / pico | clip / peak | |
| reemplazo | replacement | |
| replegado / pasabajos | aliasing / low-pass | |
| reparto de voces / repartir | voice allocation / allocate | |
| robar una voz / víctima | steal / victim | |
| golpe | hit | a drum hit |
| rampa | ramp | |
| sostenido / decaimiento | sustain / decay | |
| altura | pitch | |
| paneo | pan | |
| nota raíz / do central | root key / middle C | |
| disparo (KON) | key-on | |
| terna | triplet | |
| vuelta (de `techos`) | round | not "tick" |
| vuelta (de la carrera) | lap | |
| testigo | token, marker | by context |
