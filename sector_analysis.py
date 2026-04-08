"""
sector_analysis.py
------------------
Análisis de sensibilidad macro y correlación en stress agregados por sector.

Flujo:
  1. build_sector_indices()  → precios de índices de sector (igual-peso)
  2. compute_sector_sensitivity() → sensibilidad media por sector
  3. compute_sector_stress_correlations() → cómo cambia la correlación
     ENTRE sectores durante shocks (reutiliza covariance_analysis)
"""

import logging

import numpy as np
import pandas as pd

import covariance_analysis
from analytics import ShockEvent

logger = logging.getLogger(__name__)


# ── Índices de sector ────────────────────────────────────────────────────────

def build_sector_indices(
    prices: pd.DataFrame,
    sector_map: dict[str, str],
) -> pd.DataFrame:
    """
    Construye series de precio para cada sector como media igual-ponderada
    de los retornos acumulados de sus componentes.

    Cada componente se normaliza a base 100 en su primera fecha válida para
    que acciones con precios nominales muy distintos no dominen el índice.

    Parameters
    ----------
    prices:
        DataFrame de precios de cierre ajustados (tickers × fechas).
    sector_map:
        Diccionario ticker → nombre de sector.

    Returns
    -------
    pd.DataFrame
        Índice de fechas, columnas = nombre de sector.
    """
    # Agrupa tickers por sector filtrando los que tengan precio
    groups: dict[str, list[str]] = {}
    for ticker, sector in sector_map.items():
        if ticker in prices.columns:
            groups.setdefault(sector, []).append(ticker)

    sector_series: dict[str, pd.Series] = {}
    for sector, tickers in groups.items():
        sub = prices[tickers].copy()
        normalized_cols = []
        valid_names = []
        for t in tickers:
            col = sub[t].dropna()
            # Salta columnas vacías o con un único valor (no normalizables)
            if len(col) < 2:
                logger.warning("Ticker '%s' sin datos suficientes para índice sectorial.", t)
                continue
            col = col / col.iloc[0] * 100
            normalized_cols.append(col)
            valid_names.append(t)
        if not normalized_cols:
            continue
        idx_df = pd.concat(normalized_cols, axis=1)
        sector_series[sector] = idx_df.mean(axis=1)
        logger.info(
            "Índice sector '%s': %d componentes (%s)",
            sector, len(normalized_cols), ", ".join(valid_names),
        )

    return pd.DataFrame(sector_series).sort_index()


# ── Agregación por sector (media de filas) ───────────────────────────────────

def aggregate_by_sector(
    df: pd.DataFrame,
    sector_map: dict[str, str],
    *,
    log_members: bool = False,
) -> pd.DataFrame:
    """
    Agrega por sector la media de las filas (tickers) presentes en ``df``.

    Útil para ``raw_returns`` (%), ``vectors`` normalizados [-1,1], etc.
    """
    available = set(df.index)
    groups: dict[str, list[str]] = {}
    for ticker, sector in sector_map.items():
        if ticker in available:
            groups.setdefault(sector, []).append(ticker)

    rows: dict[str, pd.Series] = {}
    for sector, tickers in sorted(groups.items()):
        rows[sector] = df.loc[tickers].mean()
        if log_members:
            logger.info(
                "Agregado sector '%s': media de %s",
                sector, ", ".join(tickers),
            )

    out = pd.DataFrame(rows).T
    out.index.name = "Sector"
    return out


# ── Sensibilidad media por sector ────────────────────────────────────────────

def compute_sector_sensitivity(
    raw_returns: pd.DataFrame,
    sector_map: dict[str, str],
) -> pd.DataFrame:
    """
    Agrega la matriz de sensibilidades individuales por sector.

    Para cada sector calcula la media de los retornos de sus componentes
    que estén presentes en raw_returns.

    Parameters
    ----------
    raw_returns:
        DataFrame de retornos medios reales en % (tickers × factores).
    sector_map:
        Diccionario ticker → nombre de sector.

    Returns
    -------
    pd.DataFrame
        Filas = sectores, columnas = factores/dirección, valores en %.
    """
    return aggregate_by_sector(raw_returns, sector_map, log_members=True)


# ── Correlación entre sectores en stress ─────────────────────────────────────

def compute_sector_stress_correlations(
    prices: pd.DataFrame,
    sector_map: dict[str, str],
    events: list[ShockEvent],
    window: int = 63,
    rolling_window: int = 63,
) -> covariance_analysis.StressCorrelationResult:
    """
    Calcula cómo cambia la correlación ENTRE sectores durante shocks macro.

    Construye índices de precio por sector y delega en
    covariance_analysis.compute_stress_correlations usando los sectores
    como "activos" del portfolio.

    Parameters
    ----------
    prices:
        DataFrame de precios individuales.
    sector_map:
        Diccionario ticker → sector.
    events:
        Lista de ShockEvent de analytics.find_shocks().
    window, rolling_window:
        Ventanas en días de trading.

    Returns
    -------
    StressCorrelationResult con sectores como "tickers".
    """
    sector_prices = build_sector_indices(prices, sector_map)
    sector_names = list(sector_prices.columns)
    logger.info("Calculando correlación entre %d sectores…", len(sector_names))

    return covariance_analysis.compute_stress_correlations(
        prices=sector_prices,
        tickers=sector_names,
        events=events,
        window=window,
        rolling_window=rolling_window,
    )
