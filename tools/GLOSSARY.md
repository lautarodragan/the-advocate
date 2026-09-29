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
