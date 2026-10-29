# Historias de usuario — ClimApp Lite

> Formato Gherkin en español. Prioridad MoSCoW entre corchetes. Las referencias apuntan a `docs/PRD.md` y a los ADR.

## US-01 Consultar el pronóstico [Must]
```gherkin
Como turista que decide si va al río Pance mañana
Quiero ver la probabilidad de lluvia de 20 mm o más y el acumulado de 3 días
Para decidir con información y saber cuánto confiar en ella

Escenario: Pronóstico disponible
  Dado que el pronóstico para mañana fue calculado hoy
  Cuando abro la vista principal
  Entonces veo la probabilidad de lluvia de 20 mm o más en porcentaje
  Y veo el acumulado de 3 días con su nivel
  Y veo la explicación en lenguaje claro generada por Muse Spark y verificada
  Y veo el aviso "No es una alerta oficial" con el enlace a los canales oficiales

Escenario: Pronóstico desactualizado
  Dado que el último pronóstico tiene más de 24 horas
  Cuando abro la vista principal
  Entonces veo el estado "pronóstico desactualizado" con la fecha del último cálculo
  Y no se muestra ninguna probabilidad como vigente
```

## US-02 Reportar un evento [Must]
```gherkin
Como ciudadano que está en la cuenca
Quiero contar lo que veo con un texto o una foto
Para ayudar a confirmar o desmentir el pronóstico

Escenario: Reporte válido con texto
  Dado que escribo "Llueve muy fuerte hace una hora y el río viene crecido"
  Y la ubicación está dentro de la cuenca
  Cuando envío el reporte
  Entonces recibo un identificador y el estado "verificando"
  Y Muse Spark produce un registro estructurado con tipo de evento, intensidad y hora observada
  Y la compuerta de verificación aprueba el registro
  Y el reporte pasa a "verificado" con una confianza calculada por código

Escenario: Foto con metadatos
  Dado que adjunto una foto con EXIF de ubicación
  Cuando envío el reporte
  Entonces el EXIF se elimina antes de guardar o enviar la imagen al modelo
```

## US-03 Reporte rechazado por la verificación [Must]
```gherkin
Como ciudadano que reporta
Quiero saber por qué mi reporte no se aceptó
Para corregirlo si es un error

Escenario: Reporte fuera de la cuenca
  Dado que la ubicación del reporte está fuera de la cuenca
  Cuando envío el reporte
  Entonces el estado es "rechazado" con el motivo "fuera_de_cuenca"
  Y no se llama al modelo

Escenario: El modelo inventa una cifra
  Dado que la explicación generada cita una probabilidad distinta de la calculada por el modelo de pronóstico
  Cuando la comprobación determinista compara las cifras
  Entonces el intento falla con el motivo "cifra_no_coincide"
  Y se hace un nuevo intento
```

## US-04 Revisión humana tras 3 intentos [Must]
```gherkin
Como operador del sistema
Quiero que un reporte que no supera la verificación quede marcado para revisión humana
Para no publicar información no verificada

Escenario: Tres intentos fallidos
  Dado que la verificación falló en el intento 1, en el 2 y en el 3
  Cuando termina el tercer intento
  Entonces el estado del reporte es "requiere_revision_humana"
  Y el reporte no aparece como verificado en el mapa
  Y el historial guarda los motivos de cada intento

Escenario: El juez no encuentra evidencia
  Dado que el registro estructurado afirma "granizo" y el texto del ciudadano no lo menciona
  Cuando el juez Muse Spark revisa cada afirmación contra su evidencia
  Entonces el intento falla con el motivo "afirmacion_sin_evidencia"

Escenario: Respuesta truncada
  Dado que la respuesta del modelo llega con finish_reason distinto de "stop"
  Cuando la comprobación determinista la evalúa
  Entonces el intento falla con el motivo "respuesta_incompleta"
```

## US-05 Ver el acierto del pronóstico en el mapa [Must]
```gherkin
Como turista o validador científico
Quiero ver en el mapa si el pronóstico de cada día acertó
Para decidir cuánto confiar en él

Escenario: Día con evento observado
  Dado que para un día pasado el pronóstico dio 60 %
  Y las estaciones observaron 20 mm o más en la cuenca según la regla vigente del objetivo
  Cuando abro la vista de evaluación
  Entonces ese día aparece como "acierto"
  Y veo los reportes verificados de ese día en el mapa

Escenario: Métricas frente a las líneas base
  Dado que existe un periodo apartado evaluado
  Cuando consulto la evaluación
  Entonces veo aciertos, falsas alarmas, CSI, Brier, AUC y calibración del modelo
  Y veo las mismas métricas para climatología y persistencia
```

## US-06 Reproducir el evento histórico de la demo [Should]
```gherkin
Como presentador de la demo
Quiero reproducir un evento histórico documentado de punta a punta
Para mostrar el producto sin depender de datos en vivo

Escenario: Reproducción sin red
  Dado que DEMO_FALLBACK=1 y la fecha de reproducción es la del evento elegido
  Cuando ejecuto la demo
  Entonces veo el pronóstico, los reportes y la verificación con respuestas grabadas
  Y la vista indica "reproducción histórica"
```
