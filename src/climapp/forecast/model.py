"""Random forest calibrado con isotónica fuera de muestra (ADR-001 §1, revisado 2026-10-30).

Para cada año de calibración `Y` se entrena un bosque con las fechas objetivo
anteriores a `Y` y se predice `Y`; la isotónica se ajusta sobre esas predicciones fuera
de muestra. El bosque final se entrena con todo lo previo a la prueba.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.isotonic import IsotonicRegression

from climapp.forecast.dataset import Sample


@dataclass(frozen=True, slots=True)
class RFParams:
    """Hiperparámetros del bosque (`RF_*`, SUPUESTO)."""

    n_estimators: int
    min_samples_leaf: int
    random_state: int


@dataclass(frozen=True, slots=True)
class CalibrationFold:
    """Un pliegue anual: el bosque vio objetivos hasta `train_max` y predijo `predicted`."""

    train_max: date
    predicted: frozenset[date]


def _observed(samples: Sequence[Sample]) -> list[Sample]:
    """Muestras con objetivo observado y sin imputar."""
    return [s for s in samples if s.observed is not None and not s.imputed]


def _matrix(samples: Sequence[Sample], columns: Sequence[int]) -> np.ndarray:
    """Matriz de las columnas pedidas (NaN = faltante)."""
    return np.array([[s.x[i] for i in columns] for s in samples], dtype=float)


def _fit(
    samples: Sequence[Sample], columns: Sequence[int], params: RFParams
) -> RandomForestClassifier:
    """Ajusta un bosque con las muestras dadas."""
    return RandomForestClassifier(
        n_estimators=params.n_estimators,
        min_samples_leaf=params.min_samples_leaf,
        random_state=params.random_state,
        n_jobs=1,  # en paralelo la suma de árboles varía en el último decimal
    ).fit(_matrix(samples, columns), [bool(s.observed) for s in samples])


def _votes(
    forest: RandomForestClassifier, samples: Sequence[Sample], columns: Sequence[int]
) -> np.ndarray:
    """Probabilidad cruda del bosque para la clase evento."""
    proba: np.ndarray = forest.predict_proba(_matrix(samples, columns))
    return proba[:, list(forest.classes_).index(True)]


@dataclass(frozen=True)
class CalibratedForest:
    """Bosque final con su calibración fuera de muestra.

    Attributes:
        forest: bosque final (todas las fechas objetivo previas a la prueba).
        calibrator: isotónica ajustada sobre las predicciones fuera de muestra.
        columns: columnas de `FEATURE_NAMES` que usa la variante.
        fitted_dates: fechas objetivo del bosque final.
        folds: pliegues anuales de calibración.
        validation_raw: probabilidad cruda fuera de muestra por fecha de calibración.
    """

    forest: RandomForestClassifier
    calibrator: IsotonicRegression
    columns: tuple[int, ...]
    fitted_dates: frozenset[date]
    folds: tuple[CalibrationFold, ...]
    validation_raw: dict[date, float]

    @property
    def calibrated_dates(self) -> frozenset[date]:
        """Fechas usadas para calibrar."""
        return frozenset(self.validation_raw)

    def raw(self, samples: Sequence[Sample]) -> np.ndarray:
        """Probabilidad cruda del bosque final."""
        return _votes(self.forest, samples, self.columns)

    def predict(self, samples: Sequence[Sample], calibrated: bool = True) -> list[float]:
        """Probabilidad del evento del bosque final, calibrada o cruda."""
        if not samples:
            return []
        raw = self.raw(samples)
        return [float(p) for p in (self.calibrator.predict(raw) if calibrated else raw)]

    def validation_probs(self, samples: Sequence[Sample], calibrated: bool = True) -> list[float]:
        """Probabilidades fuera de muestra de los días de calibración (para fijar umbrales)."""
        raw = np.array([self.validation_raw[s.target_date] for s in samples], dtype=float)
        return [float(p) for p in (self.calibrator.predict(raw) if calibrated else raw)]


def _calibration_folds(
    history: Sequence[Sample], cal: Sequence[Sample], columns: Sequence[int], params: RFParams
) -> tuple[tuple[CalibrationFold, ...], dict[date, float]]:
    """Predicciones fuera de muestra por año de calibración."""
    folds: list[CalibrationFold] = []
    raw: dict[date, float] = {}
    for year in sorted({s.target_date.year for s in cal}):
        fit_set = [s for s in history if s.target_date.year < year]
        predicted = [s for s in cal if s.target_date.year == year]
        votes = _votes(_fit(fit_set, columns, params), predicted, columns)
        raw.update({s.target_date: float(v) for s, v in zip(predicted, votes, strict=True)})
        train_max = max(s.target_date for s in fit_set)
        folds.append(CalibrationFold(train_max, frozenset(s.target_date for s in predicted)))
    return tuple(folds), raw


def fit_forest(
    train: Sequence[Sample], valid: Sequence[Sample], params: RFParams, columns: Sequence[int]
) -> CalibratedForest:
    """Ajusta los bosques por pliegue, la isotónica y el bosque final.

    Solo entran muestras con objetivo observado y no imputadas.

    Raises:
        ValueError: si entrenamiento o calibración quedan vacíos.
    """
    history, cal = _observed([*train, *valid]), _observed(valid)
    if not _observed(train) or not cal:
        msg = "entrenamiento y calibración necesitan días con objetivo observado"
        raise ValueError(msg)
    folds, raw = _calibration_folds(history, cal, columns, params)
    calibrator = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
    calibrator.fit([raw[s.target_date] for s in cal], [float(bool(s.observed)) for s in cal])
    return CalibratedForest(
        forest=_fit(history, columns, params),
        calibrator=calibrator,
        columns=tuple(columns),
        fitted_dates=frozenset(s.target_date for s in history),
        folds=folds,
        validation_raw=raw,
    )
