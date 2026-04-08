"""
covariance_analysis.py
----------------------
Análisis de cómo evoluciona la matriz de covarianzas / correlaciones
de una cartera durante los eventos de shock macroeconómico.

Métricas calculadas:
  1. Matriz en **mercado normal** y **stress agregado por factor macro** (por cada
     factor se concatenan solo las ventanas de shock de ese factor, subidas y bajadas).
  2. Correlación media de pares (rolling) sobre toda la historia: mide
     cuándo se destruye la diversificación.
  3. Ratio de diversificación (basado en el determinante): det=1 cuando
     los activos están perfectamente no correlados, det→0 cuando todo
     converge hacia el mismo movimiento.
  4. Número efectivo de factores independientes (eigenvalores de la
     matriz de correlación): en stress el portfolio "se reduce" a 1.
"""

import logging
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from analytics import ShockEvent

logger = logging.getLogger(__name__)

# ── Tipos de salida ──────────────────────────────────────────────────────────

@dataclass
class PeriodCorr:
    """Correlación calculada en un periodo concreto."""
    label: str                  # ej. "Inflacion_CPI ⬆  2022-06-10"
    factor: str
    direction: str
    start_date: pd.Timestamp
    corr_matrix: pd.DataFrame   # n×n matriz de correlación
    avg_pairwise: float         # media de los pares off-diagonal
    effective_factors: float    # nº efectivo de factores independientes
    n_obs: int                  # observaciones disponibles en la ventana


@dataclass
class StressCorrelationResult:
    """Resultados completos del análisis de correlación en stress."""
    tickers: list[str]
    baseline: PeriodCorr                    # periodo "normal" (excluye shocks)
    stress_periods: list[PeriodCorr]        # uno por shock (zonas en gráficos rolling)
    rolling_avg_pairwise: pd.Series         # serie temporal de correlación media
    rolling_eff_factors: pd.Series          # serie temporal de factores efectivos
    rolling_pairs: pd.DataFrame             # correlación por par (columnas)
    window: int = field(default=63)
    stress_by_factor: dict[str, PeriodCorr] = field(default_factory=dict)


# ── Utilidades ───────────────────────────────────────────────────────────────

def _returns(prices: pd.DataFrame, tickers: list[str]) -> pd.DataFrame:
    """Retornos diarios de log para los tickers seleccionados (solo filas con todos válidos)."""
    return np.log(prices[tickers] / prices[tickers].shift(1)).dropna(how="any")


def _tickers_with_valid_prices(prices: pd.DataFrame, tickers: list[str], min_obs: int = 252) -> list[str]:
    """Tickers presentes en `prices` con al menos `min_obs` precios no nulos."""
    out: list[str] = []
    for t in tickers:
        if t not in prices.columns:
            continue
        if int(prices[t].notna().sum()) >= min_obs:
            out.append(t)
    return out


def _corr_from_returns(ret: pd.DataFrame) -> pd.DataFrame:
    """Matriz de correlación. Devuelve identidad si no hay datos suficientes."""
    if len(ret) < 5:
        return pd.DataFrame(np.eye(len(ret.columns)), index=ret.columns, columns=ret.columns)
    return ret.corr()


def _avg_pairwise(corr: pd.DataFrame) -> float:
    """Media de los elementos off-diagonal (correlación media entre pares)."""
    n = len(corr)
    if n < 2:
        return 0.0
    mask = ~np.eye(n, dtype=bool)
    return float(corr.values[mask].mean())


def _effective_factors(corr: pd.DataFrame) -> float:
    """
    Número efectivo de factores independientes basado en el ratio de entropía
    de los eigenvalores normalizados:

        N_eff = exp( -Σ p_i * log(p_i) )

    donde p_i = λ_i / Σ λ_j.  Rango: [1, n].
    N_eff=n cuando las correlaciones son 0; N_eff=1 cuando el primer
    eigenvalor explica todo (activos perfectamente correlados).
    """
    eigenvalues = np.linalg.eigvalsh(corr.values)
    eigenvalues = np.maximum(eigenvalues, 0)  # evita negativos por ruido numérico
    total = eigenvalues.sum()
    if total == 0:
        return 1.0
    p = eigenvalues / total
    p = p[p > 0]
    entropy = -np.sum(p * np.log(p))
    return float(np.exp(entropy))


def _build_period_corr(
    label: str,
    factor: str,
    direction: str,
    start: pd.Timestamp,
    ret: pd.DataFrame,
    window: int,
) -> PeriodCorr | None:
    """
    Construye un PeriodCorr para un rango concreto.

    Devuelve None si no hay al menos `MIN_OBS` observaciones disponibles
    (por ejemplo, porque el ticker no cotizaba en esa época).
    """
    MIN_OBS = 10

    # Busca la primera fecha del índice >= start
    future = ret.loc[start:]
    if len(future) < MIN_OBS:
        return None  # ticker no tenía datos en esa época

    window_ret = future.head(window)
    # Descarta la ventana si algún ticker tiene demasiados NaN
    valid_cols = window_ret.columns[window_ret.notna().mean() >= 0.8]
    window_ret = window_ret[valid_cols]
    if len(valid_cols) < 2 or len(window_ret) < MIN_OBS:
        return None

    corr = _corr_from_returns(window_ret)
    return PeriodCorr(
        label=label,
        factor=factor,
        direction=direction,
        start_date=start,
        corr_matrix=corr,
        avg_pairwise=_avg_pairwise(corr),
        effective_factors=_effective_factors(corr),
        n_obs=len(window_ret),
    )


# ── Función principal ────────────────────────────────────────────────────────

def compute_stress_correlations(
    prices: pd.DataFrame,
    tickers: list[str],
    events: list[ShockEvent],
    window: int = 63,
    rolling_window: int = 63,
) -> StressCorrelationResult:
    """
    Calcula cómo cambia la estructura de correlaciones de la cartera
    en cada evento de shock macro comparado con el mercado normal.

    Parameters
    ----------
    prices:
        DataFrame de precios de cierre ajustados.
    tickers:
        Lista de tickers que forman la cartera (2-10 activos).
    events:
        Lista de ShockEvent procedente de analytics.find_shocks().
    window:
        Días de trading usados en cada ventana de shock.
    rolling_window:
        Días de trading para la correlación rolling sobre toda la historia.

    Returns
    -------
    StressCorrelationResult
        Incluye ``stress_by_factor``: por cada factor macro, correlación sobre los
        retornos de todas sus ventanas de shock concatenadas.
    """
    available = _tickers_with_valid_prices(prices, tickers)
    if len(available) < 2:
        raise ValueError(
            "Se necesitan al menos 2 tickers con precios suficientes (≥252 días con dato). "
            f"Pedidos: {tickers}. Válidos: {available}"
        )
    if len(available) < len(tickers):
        logger.warning(
            "Tickers ignorados (sin columna o pocos datos): %s",
            set(tickers) - set(available),
        )

    ret = _returns(prices, available)
    if ret.empty or len(ret) < rolling_window + 1:
        raise ValueError(
            "No hay solape de retornos válidos entre los activos seleccionados "
            f"(filas tras dropna: {len(ret)}). Prueba otros tickers o amplía la caché de precios."
        )

    # ── Rolling correlación media y factores efectivos ───────────────────────
    logger.info("Calculando correlación rolling (%d días)…", rolling_window)

    pairs = [(available[i], available[j])
             for i in range(len(available))
             for j in range(i + 1, len(available))]

    pair_corr_dict: dict[str, pd.Series] = {}
    for a, b in pairs:
        pair_corr_dict[f"{a}|{b}"] = (
            ret[a].rolling(rolling_window).corr(ret[b])
        )
    rolling_pairs_df = pd.DataFrame(pair_corr_dict).dropna()

    rolling_avg = rolling_pairs_df.mean(axis=1)
    rolling_avg.name = "avg_pairwise_corr"

    # Número efectivo de factores rolling (ventana deslizante)
    eff_series: dict[pd.Timestamp, float] = {}
    for i in range(rolling_window, len(ret)):
        window_ret = ret.iloc[i - rolling_window: i]
        corr = _corr_from_returns(window_ret)
        eff_series[ret.index[i]] = _effective_factors(corr)
    rolling_eff = pd.Series(eff_series, name="effective_factors")

    # ── Correlación por ventana de shock ─────────────────────────────────────
    min_obs_window = 10  # alineado con _build_period_corr
    stress_periods: list[PeriodCorr] = []
    dir_arrow = {"up": "⬆", "down": "⬇"}
    skipped = 0
    for e in sorted(events, key=lambda x: x.start_date):
        label = f"{e.factor} {dir_arrow.get(e.direction, '')}  {e.start_date.date()}"
        pc = _build_period_corr(label, e.factor, e.direction, e.start_date, ret, window)
        if pc is None:
            skipped += 1
            continue
        stress_periods.append(pc)
        logger.info(
            "  Shock %s: avg_corr=%.3f  N_eff=%.2f  (n=%d obs.)",
            label, pc.avg_pairwise, pc.effective_factors, pc.n_obs,
        )

    if skipped:
        logger.info(
            "  (%d shocks omitidos: tickers del portfolio no tenían datos en esas fechas)",
            skipped,
        )

    # ── Stress agregado por factor macro ──────────────────────────────────────
    # Por cada factor, solo los shocks de ese factor (⬆ y ⬇); se concatenan las
    # ventanas de W días y se calcula una correlación conjunta.
    stress_by_factor: dict[str, PeriodCorr] = {}
    factor_order: list[str] = []
    seen_f: set[str] = set()
    for e in sorted(events, key=lambda x: x.start_date):
        if e.factor not in seen_f:
            seen_f.add(e.factor)
            factor_order.append(e.factor)

    for fac in factor_order:
        pool_chunks: list[pd.DataFrame] = []
        fac_events = [e for e in events if e.factor == fac]
        for e in sorted(fac_events, key=lambda x: x.start_date):
            future = ret.loc[e.start_date:]
            if len(future) < min_obs_window:
                continue
            window_ret = future.head(window)[available].dropna(how="any")
            if len(window_ret) < min_obs_window:
                continue
            pool_chunks.append(window_ret.reset_index(drop=True))

        if not pool_chunks:
            continue
        pooled_df = pd.concat(pool_chunks, axis=0, ignore_index=True)
        if len(pooled_df) < min_obs_window:
            continue
        corr_f = _corr_from_returns(pooled_df)
        pool_start = min(e.start_date for e in fac_events)
        pc_f = PeriodCorr(
            label=f"Stress agregado · {fac} ({len(pool_chunks)} vent. · {len(pooled_df)} obs.)",
            factor=fac,
            direction="none",
            start_date=pool_start,
            corr_matrix=corr_f,
            avg_pairwise=_avg_pairwise(corr_f),
            effective_factors=_effective_factors(corr_f),
            n_obs=len(pooled_df),
        )
        stress_by_factor[fac] = pc_f
        logger.info(
            "  Stress agregado [%s]: %d ventanas → %d filas; avg_corr=%.3f  N_eff=%.2f",
            fac,
            len(pool_chunks),
            len(pooled_df),
            pc_f.avg_pairwise,
            pc_f.effective_factors,
        )

    # ── Correlación en mercado normal (excluye ventanas de shock) ────────────
    shock_dates: set[pd.Timestamp] = set()
    for e in events:
        end_e = e.start_date + pd.Timedelta(days=window + 30)
        dates_in_window = ret.loc[e.start_date: end_e].index
        shock_dates.update(dates_in_window)

    normal_ret = ret.loc[~ret.index.isin(shock_dates)]
    if normal_ret.empty:
        logger.warning(
            "Todas las fechas caen dentro de ventanas de shock; baseline usa la serie completa."
        )
        normal_ret = ret

    baseline_corr = _corr_from_returns(normal_ret)
    baseline_start = normal_ret.index[0] if len(normal_ret) else ret.index[0]
    baseline = PeriodCorr(
        label="Mercado normal",
        factor="baseline",
        direction="none",
        start_date=baseline_start,
        corr_matrix=baseline_corr,
        avg_pairwise=_avg_pairwise(baseline_corr),
        effective_factors=_effective_factors(baseline_corr),
        n_obs=len(normal_ret),
    )
    logger.info(
        "Baseline (mercado normal, %d obs.): avg_corr=%.3f  N_eff=%.2f",
        baseline.n_obs, baseline.avg_pairwise, baseline.effective_factors,
    )

    return StressCorrelationResult(
        tickers=available,
        baseline=baseline,
        stress_periods=stress_periods,
        rolling_avg_pairwise=rolling_avg,
        rolling_eff_factors=rolling_eff,
        rolling_pairs=rolling_pairs_df,
        window=window,
        stress_by_factor=stress_by_factor,
    )
