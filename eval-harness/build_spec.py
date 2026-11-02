"""Especificación del set de evaluación de reportes ciudadanos (TASK-021, paso 1).

Genera `spec_reportes.jsonl`: para cada reporte simulado, el día, la hora, el sector, los
hechos del día y la instrucción para quien escriba el texto. La etiqueta esperada sale
solo de los datos, con la regla de `eval-harness/README.md`; ningún modelo la decide.

Uso: `uv run python eval-harness/build_spec.py` (lee `.env`; variables `EVAL_*` en
`eval-harness/.env.example`).
"""

import csv
import json
import random
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import structlog
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from climapp.config import Settings
from climapp.data.daily import read_daily_csv
from climapp.data.imerg import read_imerg_csv
from climapp.data.level import read_level_csv
from climapp.forecast.target import basin_days
from climapp.logging import configure_logging

log = structlog.get_logger()

Row = dict[str, object]
AFTERNOON = [f"{h:02d}:{m:02d}" for h in range(14, 20) for m in range(0, 60, 10)]
PEAK_DELAY = timedelta(minutes=30)


class SpecError(Exception):
    """Los datos no alcanzan para la mezcla pedida o contradicen la clase de una fila."""


class EvalSettings(BaseSettings):
    """Parámetros del set (prefijo `EVAL_`, ver `eval-harness/.env.example`).

    Attributes:
        events_file: tabla de eventos de nivel de la entrega 2026-11-01, relativa a
            `DATA_DIR`. Su nombre real lleva el de la estación, así que solo vive en `.env`.
        dry_rise_m: subida máxima en 24 h de un día seco (SUPUESTO, 0,05 m).
        claimed_rise_m: subida que afirma un reporte exagerado (5 m).
        seed: semilla del sorteo determinista.
        sectors: posiciones de ADR-004 y lugares públicos de OSM sobre el río.
        output: archivo de salida, relativo a la raíz del repositorio.
    """

    model_config = SettingsConfigDict(
        env_prefix="EVAL_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    events_file: Path
    dry_rise_m: float = Field(gt=0)
    claimed_rise_m: float = Field(gt=0)
    seed: int
    sectors: list[str] = Field(min_length=1)
    output: Path
    n_coherente: int = Field(ge=0)
    n_exagerado: int = Field(ge=0)
    n_falso: int = Field(ge=0)
    n_dificil: int = Field(ge=0)


@dataclass(frozen=True, slots=True)
class LabelRules:
    """Umbrales de la regla de etiquetas (fuentes en `eval-harness/README.md`).

    Attributes:
        event_rain_mm: lluvia media de la cuenca de un día de evento (SP-10, 20 mm).
        event_rise_m: subida de nivel en 24 h de un día de evento (SP-17, 0,30 m, SUPUESTO).
        rain_day_mm: día con lluvia desde este valor ([OMM], SP-2, 1 mm).
        dry_rise_m: subida máxima de un día seco (SUPUESTO, 0,05 m).
        claimed_rise_m: subida que afirma un reporte exagerado.
    """

    event_rain_mm: float
    event_rise_m: float
    rain_day_mm: float
    dry_rise_m: float
    claimed_rise_m: float


@dataclass(frozen=True, slots=True)
class Mix:
    """Cantidad de filas por clase."""

    coherente: int
    exagerado: int
    falso: int
    dificil: int


@dataclass(frozen=True, slots=True)
class DayFacts:
    """Hechos observados de un día local.

    Attributes:
        day: día local.
        rain_mm: lluvia media de las estaciones válidas (`basin_mean`); `None` sin dato.
        n_stations: estaciones válidas que entran en la media.
        rise_m: subida máxima de nivel en 24 h de `LEVEL_SERIES_ID`; `None` sin dato.
        imerg_mm: IMERG Early del día; `None` si no existe.
        level_event: el día cae en un evento de la tabla de eventos de nivel.
        peak_time: hora local del pico de ese evento, si se conoce.
    """

    day: date
    rain_mm: float | None
    n_stations: int
    rise_m: float | None
    imerg_mm: float | None
    level_event: bool
    peak_time: datetime | None


@dataclass(frozen=True, slots=True)
class LevelEvent:
    """Un evento de la tabla de eventos de nivel: ventana de lluvia y hora del pico."""

    start: date
    end: date
    peak: datetime | None


def is_event_day(facts: DayFacts, rules: LabelRules) -> bool:
    """Indica si el día es de evento: ≥ 20 mm o subida ≥ 0,30 m, y con al menos 1 mm.

    Args:
        facts: hechos del día.
        rules: umbrales.

    Returns:
        `True` si los datos respaldan un reporte de lluvia fuerte o creciente.
    """
    if facts.rain_mm is None or facts.rain_mm < rules.rain_day_mm:
        return False
    rise_ok = facts.rise_m is not None and facts.rise_m >= rules.event_rise_m
    return facts.rain_mm >= rules.event_rain_mm or rise_ok


def is_dry_day(facts: DayFacts, rules: LabelRules) -> bool:
    """Indica si el día es seco: lluvia media < 1 mm y subida conocida < 0,05 m.

    Args:
        facts: hechos del día.
        rules: umbrales.

    Returns:
        `True` si los datos contradicen un reporte de lluvia fuerte o creciente.
    """
    if facts.rain_mm is None or facts.rise_m is None:
        return False
    return facts.rain_mm < rules.rain_day_mm and facts.rise_m < rules.dry_rise_m


def expected_label(kind: str, facts: DayFacts, rules: LabelRules) -> str:
    """Etiqueta esperada de una fila según su clase y los datos del día.

    Args:
        kind: `coherente`, `dificil`, `exagerado` o `falso`.
        facts: hechos del día.
        rules: umbrales.

    Returns:
        `verdadero`, `exagerado` o `falso`.

    Raises:
        SpecError: si los datos no respaldan la clase o la clase no existe.
    """
    if kind in {"coherente", "dificil"} and is_event_day(facts, rules):
        return "verdadero"
    if kind == "exagerado" and is_event_day(facts, rules) and _overstated(facts, rules):
        return "exagerado"
    if kind == "falso" and is_dry_day(facts, rules):
        return "falso"
    msg = f"los datos del {facts.day} no respaldan una fila {kind}"
    raise SpecError(msg)


def _overstated(facts: DayFacts, rules: LabelRules) -> bool:
    """La subida afirmada es más del doble de la observada (SUPUESTO, factor 2)."""
    return facts.rise_m is not None and 2 * facts.rise_m < rules.claimed_rise_m


def _parse_peak(raw: str) -> datetime | None:
    """Hora del pico `AAAA-MM-DD HH:MM`; `None` si el evento no tuvo respuesta."""
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def read_events(path: Path) -> list[LevelEvent]:
    """Lee la tabla de eventos de nivel (columnas `Periodo lluvia` y `Hora del pico`).

    Args:
        path: CSV de la entrega 2026-11-01.

    Returns:
        Eventos con su ventana de lluvia y su pico.

    Raises:
        SpecError: si falta una columna o un periodo no tiene el formato esperado.
    """
    events = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            try:
                start, end = (
                    date.fromisoformat(p.strip()) for p in row["Periodo lluvia"].split("→")
                )
                events.append(LevelEvent(start, end, _parse_peak(row["Hora del pico"])))
            except (KeyError, ValueError) as exc:
                msg = f"fila de eventos inválida en {path.name}: {row}"
                raise SpecError(msg) from exc
    return events


def _stratified(
    pool: Sequence[DayFacts], n: int, rng: random.Random, first: Callable[[DayFacts], bool]
) -> list[DayFacts]:
    """Toma `n` días repartidos por año, prefiriendo los que cumplen `first`.

    Raises:
        SpecError: si el grupo tiene menos de `n` días.
    """
    if len(pool) < n:
        msg = f"hay {len(pool)} días candidatos y se piden {n}"
        raise SpecError(msg)
    by_year: defaultdict[int, list[DayFacts]] = defaultdict(list)
    for facts in rng.sample(list(pool), len(pool)):
        by_year[facts.day.year].append(facts)
    queues = [sorted(days, key=lambda f: not first(f)) for _, days in sorted(by_year.items())]
    picked: list[DayFacts] = []
    while len(picked) < n:
        for queue in queues:
            if queue and len(picked) < n:
                picked.append(queue.pop(0))
    return picked


def _rise_phrase(rise_m: float) -> str:
    """Cifra plausible de subida, como la diría un ciudadano."""
    if abs(rise_m - 0.5) <= 0.07:  # noqa: PLR2004 (medio metro ± 7 cm)
        return "como medio metro"
    return f"unos {round(rise_m * 10) * 10} centímetros"


def _instruction(kind: str, facts: DayFacts, rules: LabelRules, rng: random.Random) -> str:
    """Lo que debe afirmar el ciudadano, según la clase y los hechos del día."""
    if kind == "exagerado":
        return rng.choice(_exaggerated(rules.claimed_rise_m))
    if kind == "falso":
        return rng.choice(FALSE_CLAIMS)
    if kind == "dificil":
        return _hard(facts, rng)
    river = facts.rise_m is not None and facts.rise_m >= rules.event_rise_m
    rain = facts.rain_mm is not None and facts.rain_mm >= rules.event_rain_mm
    key = "ambos" if river and rain else "rio" if river else "lluvia"
    return rng.choice(COHERENT_CLAIMS[key])


COHERENT_CLAIMS = {
    "ambos": [
        "dice que llovió fuerte toda la tarde y que el río creció y viene café; no da cifras",
        "cuenta que, tras un aguacero, el río está mucho más alto que en la mañana, turbio"
        " y con palos; no da cifras",
    ],
    "rio": [
        "dice que el río creció y viene café aunque donde está llovió poco; no da cifras",
        "cuenta que el río sonaba más fuerte y bajaba turbio y crecido; no da cifras",
    ],
    "lluvia": [
        "dice que cae un aguacero fuerte desde hace rato y los caminos tienen charcos;"
        " no habla de creciente ni da cifras",
        "cuenta que llovió muy fuerte con truenos y que corre agua por la vía;"
        " no habla del río ni da cifras",
    ],
}
FALSE_CLAIMS = [
    "dice que lleva horas lloviendo muy fuerte y que el río se creció; no da cifras",
    "afirma que el río se desbordó de golpe y viene café con palos; no da cifras",
    "cuenta que hubo un aguacero tremendo con granizo y que el agua tapó el camino; no da cifras",
]


def _exaggerated(claimed_rise_m: float) -> list[str]:
    """Instrucciones exageradas con la subida afirmada."""
    meters = f"{claimed_rise_m:g}".replace(".", ",")
    return [
        f"dice que el río subió más de {meters} metros y arrasó con las casas de la vereda;"
        " no para de llover",
        f"afirma que la creciente se llevó casas y puentes y que el agua subió {meters} metros",
    ]


def _hard(facts: DayFacts, rng: random.Random) -> str:
    """Instrucción coherente con una sola cifra plausible."""
    if facts.rise_m is not None and rng.random() < 0.6:  # noqa: PLR2004 (3 de cada 5)
        return f"dice que el río subió {_rise_phrase(facts.rise_m)} y viene café; es la única cifra"
    return (
        f"dice que llovió unas {rng.choice([2, 3])} horas seguidas y que el río está más alto;"
        " es la única cifra (no se puede verificar con datos diarios)"
    )


def _hour(kind: str, facts: DayFacts, rng: random.Random) -> str:
    """Hora local: 30 min después del pico si es ese día (no en exagerados), si no, tarde."""
    peak = facts.peak_time
    if kind != "exagerado" and peak is not None and peak.date() == facts.day and peak.hour < 23:  # noqa: PLR2004
        return (peak + PEAK_DELAY).strftime("%H:%M")
    return rng.choice(AFTERNOON)


def _facts_json(facts: DayFacts) -> dict[str, object]:
    """Hechos del día para la fila, redondeados como en la app."""
    return {
        "lluvia_media_cuenca_mm": None if facts.rain_mm is None else round(facts.rain_mm, 1),
        "estaciones_con_dato": facts.n_stations,
        "subida_nivel_24h_m": None if facts.rise_m is None else round(facts.rise_m, 3),
        "imerg_early_mm": None if facts.imerg_mm is None else round(facts.imerg_mm, 1),
        "dia_de_evento_de_nivel": facts.level_event,
    }


def _row(kind: str, facts: DayFacts, ctx: tuple[LabelRules, Sequence[str], random.Random]) -> Row:
    """Fila de la especificación (sin id)."""
    rules, sectors, rng = ctx
    return {
        "fecha": facts.day.isoformat(),
        "hora_local": _hour(kind, facts, rng),
        "sector": rng.choice(list(sectors)),
        "clase": kind,
        "etiqueta_esperada": expected_label(kind, facts, rules),
        "hechos": _facts_json(facts),
        "instruccion_texto": _instruction(kind, facts, rules, rng),
    }


def _pick_days(
    days: Sequence[DayFacts], rules: LabelRules, mix: Mix, rng: random.Random
) -> list[tuple[str, DayFacts]]:
    """Elige los días de cada clase (los exagerados repiten días coherentes)."""
    events = [f for f in days if is_event_day(f, rules)]
    both = [f for f in events if (f.rise_m or 0) >= rules.event_rise_m and _strong(f, rules)]
    hard = _stratified(both, mix.dificil, rng, lambda f: not f.level_event)
    rest = [f for f in events if f not in hard]
    coherent = _stratified(rest, mix.coherente, rng, lambda f: f.level_event)
    overstated = [f for f in coherent if _overstated(f, rules)]
    exaggerated = _stratified(overstated, mix.exagerado, rng, lambda f: f.level_event)
    dry = _stratified([f for f in days if is_dry_day(f, rules)], mix.falso, rng, lambda _: True)
    groups = {"coherente": coherent, "exagerado": exaggerated, "falso": dry, "dificil": hard}
    return [(kind, f) for kind, picked in groups.items() for f in picked]


def _strong(facts: DayFacts, rules: LabelRules) -> bool:
    """Lluvia media de la cuenca de al menos el umbral del objetivo."""
    return facts.rain_mm is not None and facts.rain_mm >= rules.event_rain_mm


def build_rows(  # noqa: PLR0913, PLR0917 - datos, regla, mezcla y sorteo explícitos
    facts: Iterable[DayFacts],
    rules: LabelRules,
    mix: Mix,
    excluded: frozenset[date],
    sectors: Sequence[str],
    seed: int,
) -> list[Row]:
    """Construye las filas de la especificación, deterministas para una semilla.

    Args:
        facts: hechos por día del periodo de prueba.
        rules: umbrales de la regla de etiquetas.
        mix: filas por clase.
        excluded: días que no entran (los de la demo).
        sectors: sectores posibles del reporte.
        seed: semilla del sorteo.

    Returns:
        Filas ordenadas por fecha y hora, con id `R01`…

    Raises:
        SpecError: si los datos no alcanzan para la mezcla.
    """
    rng = random.Random(seed)  # noqa: S311 (sorteo reproducible, no es secreto)
    days = sorted((f for f in facts if f.day not in excluded), key=lambda f: f.day)
    rows = [_row(kind, f, (rules, sectors, rng)) for kind, f in _pick_days(days, rules, mix, rng)]
    rows.sort(key=lambda r: (str(r["fecha"]), str(r["hora_local"]), str(r["clase"])))
    width = len(str(len(rows)))
    return [{"id": f"R{i:0{width}d}"} | row for i, row in enumerate(rows, start=1)]


def _in_event(day: date, events: Sequence[LevelEvent]) -> LevelEvent | None:
    """Evento de nivel cuya ventana incluye el día, si hay uno."""
    return next((e for e in events if e.start <= day <= e.end), None)


def excluded_days(settings: Settings, events: Sequence[LevelEvent]) -> frozenset[date]:
    """Días de la demo (emisión y objetivo) y la ventana del evento que los contiene."""
    demo = {settings.demo_report_time.date()}
    if settings.demo_replay_date is not None:
        demo.add(settings.demo_replay_date)
    days = set(demo)
    for event in events:
        if any(event.start <= d <= event.end for d in demo):
            days.update(
                event.start + timedelta(n) for n in range((event.end - event.start).days + 1)
            )
    return frozenset(days)


def load_facts(settings: Settings, events: Sequence[LevelEvent]) -> list[DayFacts]:
    """Hechos por día del periodo de prueba (`VALID_END` < día ≤ `TEST_END`).

    Args:
        settings: configuración de la app.
        events: eventos de nivel.

    Returns:
        Un `DayFacts` por día con lluvia de la cuenca o nivel.
    """
    base = settings.data_dir
    rain = basin_days(read_daily_csv(base / settings.daily_stations_file))
    level = {
        r.date: r.rise_24h_max_m
        for r in read_level_csv(base / settings.level_daily_file)
        if r.series_id == settings.level_series_id
    }
    imerg = read_imerg_csv(base / settings.imerg_early_file)
    period = [
        d for d in sorted(set(rain) | set(level)) if settings.valid_end < d <= settings.test_end
    ]
    return [
        _day_facts(d, rain.get(d), level.get(d), imerg.get(d), _in_event(d, events)) for d in period
    ]


def _day_facts(
    day: date, basin: object, rise: float | None, imerg: float | None, event: LevelEvent | None
) -> DayFacts:
    """Une las fuentes de un día en un `DayFacts`."""
    mean = getattr(basin, "mean_mm", None)
    return DayFacts(
        day=day,
        rain_mm=mean,
        n_stations=int(getattr(basin, "n_stations", 0)),
        rise_m=rise,
        imerg_mm=imerg,
        level_event=event is not None,
        peak_time=None if event is None else event.peak,
    )


def write_jsonl(rows: Iterable[Row], path: Path) -> Path:
    """Escribe una fila JSON por línea (UTF-8, sin escapar tildes)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(text, encoding="utf-8")
    return path


def main() -> None:
    """Genera `EVAL_OUTPUT` a partir de los datos de `DATA_DIR`."""
    configure_logging()
    settings, ev = Settings(), EvalSettings()
    events = read_events(settings.data_dir / ev.events_file)
    rules = LabelRules(
        settings.forecast_threshold_mm,
        settings.level_rise_threshold_m,
        settings.rain_day_mm,
        ev.dry_rise_m,
        ev.claimed_rise_m,
    )
    mix = Mix(ev.n_coherente, ev.n_exagerado, ev.n_falso, ev.n_dificil)
    facts = load_facts(settings, events)
    rows = build_rows(facts, rules, mix, excluded_days(settings, events), ev.sectors, ev.seed)
    path = write_jsonl(rows, ev.output)
    log.info("eval.spec_written", path=str(path), rows=len(rows))


if __name__ == "__main__":
    main()
