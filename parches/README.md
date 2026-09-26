# `parches/`: lo que se le cambia al juego antes de convertirlo

`data/` es *A Blurred Line* tal como lo escribió su autor, y es derivado: `just
datos` lo rehace entero. Lo que el port le cambia vive acá, en dos carpetas que
se distinguen por **quién lo escribe**:

    auto/     lo que decidió el conversor: los colores que se fusionan, el
              tamaño de cada animación, los quince colores de cada battler.
              Lo escribe `just parches` y lo cobra `just parches-check`.
              Ver `tools/port/parches.py`. Y el techo de volumen de cada
              tema, `musica/techos.toml`, que no lo decide el conversor sino
              una medición sobre la ROM: lo escribe `just techos` y lo cobra
              `test_musica_techos.py`. Ver `tools/audio/techos.py`.
    manual/   lo que decidió una persona: hoy, mapas y ChipSets rediseñados
              para esquivar límites de la consola. **Ninguna herramienta
              escribe acá**, y lo de acá manda. Ver `manual/README.md`.

La separación es la regla: dos direcciones opuestas en un mismo directorio son
lo que alguien regenera sin mirar. Que hoy lo de `manual/` sean archivos
enteros y lo de `auto/` decisiones puntuales es cómo están hechos, no parte de
la regla.
