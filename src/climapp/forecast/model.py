"""Random forest de clasificación calibrado con isotónica en validación (ADR-001 §1)."""

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


def _observed(samples: Sequence[Sample]) -> list[Sample]:
    """Muestras con objetivo observado y sin imputar."""
    return [s for s in samples if s.observed is not None and not s.imputed]


def _matrix(samples: Sequence[Sample]) -> np.ndarray:
    """Matriz de variables (NaN = faltante)."""
    return np.array([s.x for s in samples], dtype=float)


@dataclass(frozen=True)
class CalibratedForest:
    """Bosque ajustado en entrenamiento y calibrado en validación.

    Attributes:
        forest: clasificador de scikit-learn.
        calibrator: regresión isotónica de la probabilidad cruda a la calibrada.
        fitted_dates: fechas objetivo usadas para ajustar el bosque.
        calibrated_dates: fechas objetivo usadas para calibrar.
    """

    forest: RandomForestClassifier
    calibrator: IsotonicRegression
    fitted_dates: frozenset[date]
    calibrated_dates: frozenset[date]

    def raw(self, samples: Sequence[Sample]) -> np.ndarray:
        """Probabilidad cruda del bosque para la clase evento."""
        proba: np.ndarray = self.forest.predict_proba(_matrix(samples))
        return proba[:, list(self.forest.classes_).index(True)]

    def predict(self, samples: Sequence[Sample]) -> list[float]:
        """Probabilidad calibrada del evento para cada muestra."""
        if not samples:
            return []
        return [float(p) for p in self.calibrator.predict(self.raw(samples))]


def fit_forest(
    train: Sequence[Sample], valid: Sequence[Sample], params: RFParams
) -> CalibratedForest:
    """Ajusta el bosque en `train` y la calibración isotónica en `valid`.

    Solo entran muestras con objetivo observado y no imputadas.

    Raises:
        ValueError: si alguno de los dos conjuntos queda vacío.
    """
    fit, cal = _observed(train), _observed(valid)
    if not fit or not cal:
        msg = "entrenamiento y validación necesitan días con objetivo observado"
        raise ValueError(msg)
    forest = RandomForestClassifier(
        n_estimators=params.n_estimators,
        min_samples_leaf=params.min_samples_leaf,
        random_state=params.random_state,
        n_jobs=1,  # en paralelo la suma de árboles varía en el último decimal
    ).fit(_matrix(fit), [bool(s.observed) for s in fit])
    model = CalibratedForest(
        forest,
        IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip"),
        frozenset(s.target_date for s in fit),
        frozenset(s.target_date for s in cal),
    )
    model.calibrator.fit(model.raw(cal), [float(bool(s.observed)) for s in cal])
    return model
