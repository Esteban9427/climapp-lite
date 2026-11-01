// Mapa de reportes verificados (TASK-018): datos embebidos por el servidor en #map-data.
window.addEventListener("load", function () {
  const box = document.getElementById("map");
  const data = JSON.parse(document.getElementById("map-data").textContent);
  if (typeof L === "undefined") { box.textContent = "No se pudo cargar el mapa base; los reportes siguen en la lista."; return; }
  box.textContent = "";
  const map = L.map(box);
  L.tileLayer(data.tile_url, {
    maxZoom: 18,
    attribution: '<a href="' + data.attribution_url + '">' + data.attribution + "</a>",
  }).addTo(map);
  // Popup como texto (nunca HTML): título, resultado y una línea por fuente de evidencia
  function popup(m) {
    const box = document.createElement("div");
    [m.label].concat(m.details || []).forEach(function (line, i) {
      const row = document.createElement(i === 0 ? "strong" : "div");
      row.textContent = line;
      box.appendChild(row);
    });
    return box;
  }
  const points = data.markers.map(function (m) {
    L.marker([m.lat, m.lon]).addTo(map).bindPopup(popup(m));
    return [m.lat, m.lon];
  });
  let outline = null;
  if (data.basin && data.basin.length) {
    outline = L.polygon(data.basin, { color: "#1d4ed8", weight: 2, dashArray: "6 4", fill: false }).addTo(map);
    outline.bindTooltip(data.basin_label, { sticky: true });
  }
  if (outline) { map.fitBounds(outline.getBounds(), { padding: [16, 16] }); }
  else if (points.length) { map.fitBounds(points, { padding: [32, 32], maxZoom: 14 }); }
  else if (data.center) { map.setView(data.center, 12); }
  else { map.fitWorld(); }
});
