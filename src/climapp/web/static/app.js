// Formulario de reporte: ubicación del navegador y botón deshabilitado hasta tener datos.
(function () {
  const form = document.getElementById("report-form");
  if (!form) return;
  const submit = form.querySelector("button[type=submit]");
  const text = form.querySelector("#report-text");
  const photo = form.querySelector("#report-photo");
  const lat = form.querySelector("[name=lat]");
  const lon = form.querySelector("[name=lon]");
  const where = document.getElementById("location-status");
  function refresh() {
    const content = text.value.trim() !== "" || photo.files.length > 0;
    submit.disabled = !(content && lat.value && lon.value);
  }
  document.getElementById("use-location").addEventListener("click", function () {
    if (!navigator.geolocation) { where.textContent = "Tu navegador no comparte la ubicación."; return; }
    where.textContent = "Buscando tu ubicación…";
    navigator.geolocation.getCurrentPosition(function (pos) {
      lat.value = pos.coords.latitude.toFixed(6);
      lon.value = pos.coords.longitude.toFixed(6);
      where.textContent = "Ubicación lista.";
      refresh();
    }, function () { where.textContent = "No pudimos obtener tu ubicación."; });
  });
  text.addEventListener("input", refresh);
  photo.addEventListener("change", refresh);
  form.addEventListener("htmx:beforeRequest", function () { submit.disabled = true; submit.textContent = "Enviando…"; });
  form.addEventListener("htmx:afterRequest", function () { submit.textContent = "Enviar reporte"; refresh(); });
  refresh();
})();
