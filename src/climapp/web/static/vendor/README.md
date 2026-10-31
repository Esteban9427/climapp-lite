# Bibliotecas de terceros (sin paso de build, ADR-005)

| Biblioteca | Versión | Origen | Licencia | SHA-256 |
|------------|---------|--------|----------|---------|
| htmx | 2.0.4 | https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js | Zero-Clause BSD (`htmx.LICENSE`) | `e209dda5c8235479f3166defc7750e1dbcd5a5c1808b7792fc2e6733768fb447` |
| Leaflet | 1.9.4 | https://unpkg.com/leaflet@1.9.4/dist/ (`leaflet.js`, `leaflet.css`, `images/`) | BSD 2-Clause (`leaflet/LICENSE`) | `db49d009c841f5ca34a888c96511ae936fd9f5533e90d8b2c4d57596f4e5641a` (`leaflet.js`) |

Se sirven desde la propia app para que la demo no dependa de un CDN. Las teselas del mapa sí vienen de OpenStreetMap (ODbL) y necesitan red.
