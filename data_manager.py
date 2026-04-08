"""
data_manager.py
---------------
Descarga, caché y preprocesado de datos de precios (Yahoo Finance)
y series macroeconómicas (FRED via pandas_datareader).

Los datos se persisten en CSV para evitar llamadas repetidas a la red.
"""

import os
import logging
from typing import Optional

import pandas as pd
import yfinance as yf

import config

logger = logging.getLogger(__name__)

# ── Utilidades de caché ──────────────────────────────────────────────────────

def _ensure_cache_dir() -> None:
    """Crea el directorio de caché si no existe."""
    os.makedirs(config.CACHE_DIR, exist_ok=True)


def _load_csv(path: str) -> Optional[pd.DataFrame]:
    """Intenta cargar un DataFrame desde CSV; devuelve None si no existe."""
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, index_col=0, parse_dates=True)
            logger.info("Caché cargada desde %s", path)
            return df
        except Exception as exc:
            logger.warning("Error leyendo caché %s: %s", path, exc)
    return None


def clear_cache() -> None:
    """
    Elimina todos los archivos CSV de caché.

    Llamar antes de re-descargar datos cuando force_refresh=True,
    para garantizar que no queden datos parciales o desactualizados.
    """
    for path in (
        config.PRICES_CACHE,
        config.MACRO_CACHE,
        config.RAW_RETURNS_CACHE_POST,
        config.NORM_VECTORS_CACHE_POST,
        config.RAW_RETURNS_CACHE_DURING,
        config.NORM_VECTORS_CACHE_DURING,
        # legado (antes de separar post/during)
        f"{config.CACHE_DIR}/sensitivity_raw.csv",
        f"{config.CACHE_DIR}/sensitivity_normalized.csv",
    ):
        if os.path.exists(path):
            os.remove(path)
            logger.info("Caché eliminada: %s", path)


def _save_csv(df: pd.DataFrame, path: str) -> None:
    """Guarda un DataFrame en CSV."""
    _ensure_cache_dir()
    df.to_csv(path)
    logger.info("Datos guardados en %s", path)


# ── Precios de acciones ──────────────────────────────────────────────────────

def fetch_prices(
    tickers: list[str],
    start: str = config.START_DATE,
    end: str = config.END_DATE,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Descarga precios de cierre ajustados para los tickers indicados.

    Si existe caché válida y no se fuerza refresco, la usa directamente.

    Parameters
    ----------
    tickers:
        Lista de símbolos de Yahoo Finance.
    start, end:
        Rango de fechas ISO-8601.
    force_refresh:
        Si True, ignora la caché y descarga de nuevo.

    Returns
    -------
    pd.DataFrame
        Índice: fechas; columnas: un ticker por columna (precios de cierre ajustados).
    """
    if not force_refresh:
        cached = _load_csv(config.PRICES_CACHE)
        if cached is not None:
            if set(tickers).issubset(set(cached.columns)):
                return cached

    all_tickers = list(set(tickers))
    logger.info("Descargando precios para %d tickers…", len(all_tickers))

    raw = yf.download(
        all_tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
    )

    # yfinance devuelve MultiIndex cuando hay varios tickers
    if isinstance(raw.columns, pd.MultiIndex):
        prices = raw["Close"].copy()
    else:
        prices = raw[["Close"]].copy()
        prices.columns = [all_tickers[0]]

    prices = prices.dropna(how="all")
    _save_csv(prices, config.PRICES_CACHE)
    return prices


# ── Series macroeconómicas ───────────────────────────────────────────────────

def fetch_macro(
    start: str = config.START_DATE,
    end: str = config.END_DATE,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """
    Descarga series macro de FRED via pandas_datareader.

    Cada serie se devuelve en la unidad más interpretable para detectar shocks:

    - ``Spread_10Y2Y``, ``UNRATE``: nivel en puntos porcentuales (pp).
      analytics aplicará diff() → cambio en pp.
      Así, pasar del 1% al 2% computa +1 pp (no +100%).

    - ``Inflacion_CPI``, ``Gasto_Defensa`` y ``Petroleo_WTI`` (WTI vía Yahoo ``CL=F``):
      primero se interpolan a diario y luego se convierten a YoY rodante
      usando pct_change(365). Esto produce un dato por cada día del año,
      no solo un dato por mes, por lo que se detectan shocks que empiezan
      en cualquier mes (ej.: subida de junio a mayo del año siguiente).

    Parameters
    ----------
    start, end:
        Rango de fechas ISO-8601.
    force_refresh:
        Si True, ignora la caché y descarga de nuevo.

    Returns
    -------
    pd.DataFrame
        Índice: fechas; columnas: nombre legible de cada serie macro.
        Series de frecuencia mensual interpoladas a frecuencia diaria.
    """
    expected_cols = set(config.FRED_SERIES) | {config.OIL_SERIES_NAME}
    if not force_refresh:
        cached = _load_csv(config.MACRO_CACHE)
        if cached is not None and set(cached.columns) == expected_cols:
            return cached
        if cached is not None:
            logger.info(
                "Caché macro ignorada (columnas distintas al esquema actual); se regenera."
            )

    try:
        import pandas_datareader.data as web  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "pandas_datareader no está instalado. Ejecuta: pip install pandas-datareader"
        ) from exc

    frames: dict[str, pd.Series] = {}
    for name, fred_id in config.FRED_SERIES.items():
        try:
            series = web.DataReader(fred_id, "fred", start, end)[fred_id]
            series.name = name
            frames[name] = series
            logger.info("FRED '%s' descargada (%d obs.)", fred_id, len(series))
        except Exception as exc:
            logger.warning("No se pudo descargar FRED '%s': %s", fred_id, exc)

    if not frames:
        raise RuntimeError("No se pudieron descargar datos de FRED.")

    macro = pd.DataFrame(frames)

    # Primero interpolamos a frecuencia diaria para que el YoY rodante
    # se calcule desde cada día del año, no solo desde cada mes calendario.
    # Así un movimiento que va de junio de un año a mayo del siguiente
    # queda capturado igual que uno que va de enero a enero.
    macro = macro.resample("D").interpolate(method="time")
    macro = macro.loc[start:end]

    # WTI: mismo índice diario que el macro (interpolación temporal)
    try:
        raw_oil = yf.download(
            config.OIL_TICKER,
            start=start,
            end=end,
            auto_adjust=True,
            progress=False,
        )
        oil_close = raw_oil["Close"]
        oil_s = oil_close if isinstance(oil_close, pd.Series) else oil_close.iloc[:, 0]
        oil_s = oil_s.reindex(macro.index).interpolate(method="time")
        macro[config.OIL_SERIES_NAME] = oil_s
        logger.info(
            "Petróleo WTI '%s' añadido al macro (%d obs. válidas)",
            config.OIL_TICKER,
            macro[config.OIL_SERIES_NAME].notna().sum(),
        )
    except Exception as exc:
        raise RuntimeError(
            f"No se pudo descargar el petróleo WTI ({config.OIL_TICKER}). "
            "Comprueba la conexión o vuelve a intentar."
        ) from exc

    if config.OIL_SERIES_NAME not in macro.columns or macro[config.OIL_SERIES_NAME].notna().sum() == 0:
        raise RuntimeError(
            f"Serie de petróleo vacía ({config.OIL_TICKER}). No se puede construir el panel macro."
        )

    # YoY rodante diario (365 días naturales) para series de nivel:
    #   - CPI: nivel → tasa de inflación YoY (%)
    #   - Gasto_Defensa: nivel → crecimiento YoY (%)
    #   - Petroleo_WTI: precio → variación YoY (%)
    #
    # pct_change(365) sobre datos diarios compara cada día con el mismo
    # día exactamente un año antes, produciendo un YoY para cada jornada.
    #
    # Spread_10Y2Y y UNRATE se mantienen como niveles en pp;
    # analytics aplicará diff() → cambio en pp (1%→2% = +1pp, no +100%).
    pct_change_cols = ["Inflacion_CPI", "Gasto_Defensa", config.OIL_SERIES_NAME]
    for col in pct_change_cols:
        if col in macro.columns:
            macro[col] = macro[col].pct_change(365) * 100  # YoY % rodante diario

    _save_csv(macro, config.MACRO_CACHE)
    return macro


# ── Caché de sensibilidades ──────────────────────────────────────────────────

def save_sensitivity(
    raw_returns: pd.DataFrame,
    normalized: pd.DataFrame,
    mode: str = "post",
) -> None:
    """
    Persiste las matrices de sensibilidad en CSV para el modo indicado.

    Parameters
    ----------
    mode:
        ``post`` (retorno tras el shock) o ``during`` (retorno en la ventana del shock).
    """
    raw_path, norm_path = config.sensitivity_cache_paths(mode)
    _save_csv(raw_returns, raw_path)
    _save_csv(normalized, norm_path)


def load_sensitivity(mode: str = "post") -> tuple[pd.DataFrame, pd.DataFrame] | None:
    """
    Carga sensibilidades desde CSV para el modo ``post`` o ``during``.
    """
    raw_path, norm_path = config.sensitivity_cache_paths(mode)
    raw = _load_csv(raw_path)
    norm = _load_csv(norm_path)
    if raw is not None and norm is not None:
        return raw, norm
    return None


# ── Sincronización de índices ────────────────────────────────────────────────

def align_data(
    prices: pd.DataFrame,
    macro: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Alinea precios y macro al mismo índice de fechas (intersección).

    Parameters
    ----------
    prices:
        DataFrame de precios diarios.
    macro:
        DataFrame de series macro (diarias tras resample).

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        prices y macro con el mismo índice de fechas.
    """
    common_idx = prices.index.intersection(macro.index)
    return prices.loc[common_idx], macro.loc[common_idx]
