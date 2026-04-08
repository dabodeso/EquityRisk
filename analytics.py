"""
analytics.py
------------
Lógica del Event Study macroeconómico:
  1. Identificar los N mayores shocks (al alza y a la baja) de cada factor.
  2. Medir el retorno de la acción con una ventana ``post`` o ``during``.
  3. Normalizar los retornos a [-1, 1] → vector de sensibilidad.

**post:** retorno desde la fecha del shock hacia adelante W días de trading.

**during:** retorno en la misma ventana W que el macro: de precio en t−W a
precio en t (el shock en t es ``macro[t] - macro[t-W]``).
"""

import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np
import pandas as pd

import config

logger = logging.getLogger(__name__)


# ── Estructuras de datos ─────────────────────────────────────────────────────

@dataclass
class ShockEvent:
    """Representa un evento de shock macro."""
    factor: str
    direction: str          # "up" | "down"
    start_date: pd.Timestamp
    shock_magnitude: float  # Cambio del factor en ese punto


@dataclass
class SensitivityResult:
    """
    Resultados del análisis de sensibilidad para todos los activos.

    Attributes
    ----------
    raw_returns:
        Retorno medio real (en %) de cada acción durante los N eventos de shock
        de cada factor/dirección. Ejemplo: MSFT × Inflacion_CPI_down = -12.4 %
        significa que MSFT cayó de media un 12.4 % en los 3 shocks bajistas de CPI.
    vectors:
        Misma matriz normalizada a [-1, 1] columna a columna. Se usa para la
        reducción de dimensionalidad (PCA / t-SNE) en el gráfico 3D.
    shock_events:
        Lista de todos los shocks identificados.
    factor_names:
        Nombres de los factores macro (sin dirección).
    window_mode:
        ``post`` o ``during`` (ver docstring del módulo).
    """
    raw_returns: pd.DataFrame       # retornos medios reales en %
    vectors: pd.DataFrame           # normalizado [-1, 1]
    shock_events: list[ShockEvent]
    factor_names: list[str] = field(default_factory=list)
    window_mode: str = "post"


# ── Identificación de shocks ─────────────────────────────────────────────────

def _compute_changes(series: pd.Series, window: int = 63) -> pd.Series:
    """
    Calcula el cambio absoluto de la serie en una ventana rodante.

    Todas las series macro llegan de data_manager ya en su unidad natural
    (pp para tipos/spreads, YoY % para nivel de precios / petróleo / gasto), por lo que diff()
    produce siempre cambios en puntos porcentuales, que son comparables
    entre sí y económicamente interpretables.
    """
    return series.diff(window)


def _select_dispersed_dates(
    sorted_changes: pd.Series,
    n_shocks: int,
    min_separation_calendar_days: int,
) -> list[tuple[pd.Timestamp, float]]:
    """
    Selecciona hasta `n_shocks` fechas de `sorted_changes` separadas al menos
    `min_separation_calendar_days` días naturales entre cualquier par ya elegido,
    para evitar solapar el mismo episodio (p. ej. varios picos dentro de un año).

    Returns
    -------
    list[tuple[Timestamp, float]]
        Pares (fecha, magnitud) seleccionados (pueden ser menos de `n_shocks`
        si no hay suficientes candidatos que cumplan la separación).
    """
    selected: list[pd.Timestamp] = []
    result: list[tuple[pd.Timestamp, float]] = []

    for date, magnitude in sorted_changes.items():
        if len(selected) >= n_shocks:
            break
        too_close = any(
            abs((date - prev).days) < min_separation_calendar_days for prev in selected
        )
        if not too_close:
            selected.append(date)
            result.append((date, float(magnitude)))

    return result


def find_shocks(
    macro: pd.DataFrame,
    n_shocks: int = config.N_SHOCKS,
    window: int = config.SHOCK_WINDOW_DAYS,
) -> list[ShockEvent]:
    """
    Identifica los N shocks más extremos (alza y baja) por factor macro.

    Aplica una separación mínima en **días naturales** entre shocks del mismo
    factor y la misma dirección (p. ej. 365 días ≈ 12 meses), definida en
    ``config.SHOCK_MIN_SEPARATION_CALENDAR_DAYS``.

    Parameters
    ----------
    macro:
        DataFrame de series macro alineadas y diarias.
    n_shocks:
        Número de shocks por dirección y factor.
    window:
        Ventana en días usada para calcular el cambio del factor.

    Returns
    -------
    list[ShockEvent]
        Lista de shocks ordenados por factor y dirección.
    """
    events: list[ShockEvent] = []

    logger.info("=" * 60)
    logger.info(
        "SHOCKS MACRO  (diff macro W=%d días hábiles; separación mín. mismo factor/dirección=%d días naturales)",
        window,
        config.SHOCK_MIN_SEPARATION_CALENDAR_DAYS,
    )
    logger.info("=" * 60)

    for factor in macro.columns:
        series = macro[factor].dropna()
        changes = _compute_changes(series, window).dropna()

        for direction in ("up", "down"):
            # Orden global por magnitud: con separación anual hace falta recorrer
            # muchos candidatos, no solo los 10·N primeros.
            candidates = changes.sort_values(ascending=(direction == "down"))
            selected = _select_dispersed_dates(
                candidates,
                n_shocks,
                config.SHOCK_MIN_SEPARATION_CALENDAR_DAYS,
            )
            label = "⬆ SUBIDA" if direction == "up" else "⬇ BAJADA"
            logger.info("  %s  %s", factor, label)
            for date, magnitude in selected:
                logger.info("      %s  magnitud=%+.4f pp", date.date(), magnitude)
                events.append(
                    ShockEvent(
                        factor=factor,
                        direction=direction,
                        start_date=date,
                        shock_magnitude=magnitude,
                    )
                )
            if len(selected) < n_shocks:
                logger.warning(
                    "      %s %s: solo %d shock(s) cumplen separación ≥ %d días (pedidos %d).",
                    factor,
                    label,
                    len(selected),
                    config.SHOCK_MIN_SEPARATION_CALENDAR_DAYS,
                    n_shocks,
                )

    logger.info("Total: %d shocks identificados.", len(events))
    return events


# ── Retornos en ventana de shock ─────────────────────────────────────────────

def _window_return_post(
    price_series: pd.Series,
    shock_date: pd.Timestamp,
    window: int,
) -> float:
    """
    Retorno **después** del shock: desde el primer precio en ``shock_date`` (o
    posterior) hasta W días de trading **hacia adelante**.
    """
    future = price_series.loc[shock_date:]
    if len(future) < 2:
        return float("nan")
    end_idx = min(window, len(future) - 1)
    p0 = future.iloc[0]
    p1 = future.iloc[end_idx]
    if p0 == 0 or np.isnan(p0):
        return float("nan")
    return (p1 - p0) / p0


def _window_return_during(
    price_series: pd.Series,
    shock_date: pd.Timestamp,
    window: int,
) -> float:
    """
    Retorno **durante** la ventana que define el shock macro.

    En la fecha ``shock_date``, el shock es ``macro[t] - macro[t-W]`` (``diff``).
    Se mide el retorno de la acción entre el precio W días hábiles **antes**
    y el precio en la fecha del shock (inclusive).
    """
    past = price_series.loc[:shock_date].dropna()
    if len(past) < window + 1:
        return float("nan")
    p_start = past.iloc[-(window + 1)]
    p_end = past.iloc[-1]
    if p_start == 0 or np.isnan(p_start):
        return float("nan")
    return (p_end - p_start) / p_start


# ── Normalización ────────────────────────────────────────────────────────────

def _normalize_to_unit(series: pd.Series) -> pd.Series:
    """
    Mapea los valores de una Serie al rango [-1, 1] usando el máximo absoluto.

    Si todos los valores son 0 o NaN, devuelve una serie de ceros.
    """
    valid = series.dropna()
    if valid.empty:
        return series.fillna(0.0)
    max_abs = valid.abs().max()
    if max_abs == 0:
        return series.fillna(0.0)
    return (series / max_abs).clip(-1, 1).fillna(0.0)


# ── Cálculo del vector de sensibilidad ──────────────────────────────────────

def compute_sensitivity(
    prices: pd.DataFrame,
    macro: pd.DataFrame,
    tickers: list[str],
    n_shocks: int = config.N_SHOCKS,
    window: int = config.SHOCK_WINDOW_DAYS,
    window_mode: Literal["post", "during"] = "post",
) -> SensitivityResult:
    """
    Calcula los vectores de sensibilidad macro para cada ticker.

    Para cada par (factor, dirección) calcula el retorno medio de la acción
    en los N periodos de shock históricos y lo normaliza a [-1, 1].

    Parameters
    ----------
    prices:
        DataFrame de precios de cierre ajustados (incluye petróleo como columna).
    macro:
        DataFrame de series macro alineadas.
    tickers:
        Lista de tickers de acciones a analizar (sin petróleo).
    n_shocks:
        Número de shocks por dirección y factor.
    window:
        Días hábiles de la ventana (misma W que en el ``diff`` del macro).
    window_mode:
        ``post``: retorno W días **después** del shock.
        ``during``: retorno en la ventana **W días hasta** el shock (alineado al macro).

    Returns
    -------
    SensitivityResult
        Objeto con la matriz de vectores y la lista de shocks.
    """
    events = find_shocks(macro, n_shocks=n_shocks, window=window)
    ret_fn = _window_return_post if window_mode == "post" else _window_return_during

    # Construye columnas: "Factor_up" y "Factor_down"
    factors = list(macro.columns)
    columns = [f"{f}_{d}" for f in factors for d in ("up", "down")]

    # Filtra tickers que realmente existen en el DataFrame de precios
    valid_tickers = [t for t in tickers if t in prices.columns]
    missing = set(tickers) - set(valid_tickers)
    if missing:
        logger.warning("Tickers sin datos de precios: %s", missing)

    records: dict[str, dict[str, float]] = {t: {} for t in valid_tickers}

    for factor in factors:
        for direction in ("up", "down"):
            col_name = f"{factor}_{direction}"
            relevant = [e for e in events if e.factor == factor and e.direction == direction]

            for ticker in valid_tickers:
                series = prices[ticker].dropna()
                returns = [ret_fn(series, e.start_date, window) for e in relevant]
                valid_returns = [r for r in returns if not np.isnan(r)]
                mean_ret = float(np.mean(valid_returns)) if valid_returns else 0.0
                records[ticker][col_name] = mean_ret

    raw_df = pd.DataFrame.from_dict(records, orient="index", columns=columns)
    raw_df.index.name = "Ticker"

    # Convierte a % para lectura directa (ej. -0.124 → -12.4 %)
    raw_returns_pct = raw_df * 100

    # Normaliza columna a columna para el espacio 3D
    normalized = raw_df.apply(_normalize_to_unit, axis=0)
    normalized.index.name = "Ticker"

    _log_sensitivity_summary(raw_returns_pct, factors, events, window_mode)

    return SensitivityResult(
        raw_returns=raw_returns_pct,
        vectors=normalized,
        shock_events=events,
        factor_names=factors,
        window_mode=window_mode,
    )


def _log_sensitivity_summary(
    raw_pct: pd.DataFrame,
    factors: list[str],
    events: list[ShockEvent],
    window_mode: str = "post",
) -> None:
    """
    Imprime por factor un resumen de las 3 acciones más sensibles
    (al alza y a la baja) junto con los retornos individuales por shock.
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info(
        "SENSIBILIDADES POR FACTOR  (retorno medio en %, modo=%s)",
        window_mode,
    )
    logger.info("=" * 60)

    for factor in factors:
        for direction in ("up", "down"):
            col = f"{factor}_{direction}"
            if col not in raw_pct.columns:
                continue
            label = "⬆ subida" if direction == "up" else "⬇ bajada"
            logger.info("  %s  %s", factor, label)

            relevant_events = [e for e in events if e.factor == factor and e.direction == direction]
            dates_str = "  |  ".join(str(e.start_date.date()) for e in relevant_events)
            logger.info("    Fechas shocks: %s", dates_str)

            series = raw_pct[col].sort_values(ascending=(direction == "down"))
            top3 = series.head(3)
            bot3 = series.tail(3)
            logger.info("    Más sensibles positivos: %s",
                        "  ".join(f"{t}={v:+.1f}%" for t, v in top3.items()))
            logger.info("    Más sensibles negativos: %s",
                        "  ".join(f"{t}={v:+.1f}%" for t, v in bot3.items()))
    logger.info("=" * 60)
