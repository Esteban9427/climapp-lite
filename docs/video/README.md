# Video de demo de ClimApp Lite

Guion: [`guion_v2.md`](guion_v2.md) (fuente) y [`guion.json`](guion.json) (versión que usan los scripts de `scripts/video/`). El MP4, los audios y los clips se generan en `video/`, que no se versiona.

## Narración
- Narra Juan Manuel Nogales con sus grabaciones reales en las filas 1, 2, 5, 6 y 7.
- **Filas 3 y 4: voz clonada con IA.** Consentimiento escrito de Juan Manuel Nogales del 2026-11-03, limitado a clonar su voz para narrar las filas 3 y 4 de este video. No cubre otros textos, otros videos ni otros usos. Modelo: Chatterbox Multilingual (open source), en local; el audio generado lleva la marca de agua Perth del modelo. La tarjeta final del video lo declara.
- Laura y el vecino son personajes ficticios.

## Imágenes
- `pance_01.jpg` (filas 1 y 7): río Pance, rápidos con guadua y piedras. **Foto: Juan Esteban Gallego** (autor del proyecto), uso propio. Se eliminaron todos los metadatos EXIF, GPS incluido, antes de usarla. En el video aparece con el rótulo "Pance river · Photo: Juan Esteban Gallego". La foto vive en `~/video/assets/`, fuera del repositorio.
- No se usan imágenes generadas con IA.

## Reproducir
```bash
uv run python scripts/video/preparar_audio.py docs/video/guion.json ~/voz/jm video/audio
uv run --project ~/tools/voz-tts python scripts/video/narrar.py docs/video/guion.json ~/voz/jm/ref_jm_6y7.wav video/audio/clon 3 4
# elegir la toma que pase la verificación de cifras (ver guion.json → audio.generacion) e igualarla:
(cd scripts/video && uv run python igualar_clon.py ../../docs/video/guion.json ../../video/audio/clon/seg03_t1.wav ../../video/audio/seg03_clon.wav \
    --referencias ../../video/audio/seg01.wav ../../video/audio/seg06.wav ../../video/audio/seg07.wav)
uv run --project ~/tools/asr python scripts/video/subtitular.py docs/video/guion.json video/audio 1 2 3 4 5 6 7
uv run --project ~/tools/video python scripts/video/grabar.py docs/video/guion.json video/clips 3 4 5 6
uv run python scripts/video/componer.py docs/video/guion.json ~/voz/jm video
```
