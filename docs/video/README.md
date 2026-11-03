# Video de demo de ClimApp Lite

Guion: [`guion_v2.md`](guion_v2.md) (fuente) y [`guion.json`](guion.json) (versión que usan los scripts de `scripts/video/`). El MP4, los audios y los clips se generan en `video/`, que no se versiona.

## Narración
- Narra Juan Manuel Nogales con sus grabaciones reales en las filas 1, 2, 5, 6 y 7.
- **Filas 3 y 4: voz clonada con IA.** Consentimiento escrito de Juan Manuel Nogales del 2026-11-03, limitado a clonar su voz para narrar las filas 3 y 4 de este video. No cubre otros textos, otros videos ni otros usos. Modelo: Chatterbox Multilingual (open source), en local; el audio generado lleva la marca de agua Perth del modelo. La tarjeta final del video lo declara.
- Laura y el vecino son personajes ficticios.

## Reproducir
```bash
uv run python scripts/video/preparar_audio.py docs/video/guion.json ~/voz/jm video/audio
uv run --project ~/tools/voz-tts python scripts/video/narrar.py docs/video/guion.json ~/voz/jm/ref_jm.wav video/audio/clon 3 4
uv run --project ~/tools/asr python scripts/video/subtitular.py docs/video/guion.json video/audio 1 2 3 4 5 6 7
uv run --project ~/tools/video python scripts/video/grabar.py docs/video/guion.json video/clips 3 4 5 6
uv run python scripts/video/componer.py docs/video/guion.json ~/voz/jm video
```
