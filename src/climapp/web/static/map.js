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
  const points = data.markers.map(function (m) {
    L.marker([m.lat, m.lon]).addTo(map).bindPopup(m.label);
    return [m.lat, m.lon];
  });
  if (points.length) { map.fitBounds(points, { padding: [32, 32], maxZoom: 14 }); }
  else if (data.center) { map.setView(data.center, 12); }
  else { map.fitWorld(); }
});
