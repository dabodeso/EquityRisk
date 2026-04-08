"""
download_data.py
----------------
Script independiente para descargar y precalcular todos los datos
del universo completo de 50 tickers.

Uso:
    python download_data.py           # usa caché si existe
    python download_data.py --force   # borra caché y recalcula todo

Ejecutar este script una sola vez antes de abrir la app Streamlit
para que la interfaz arranque instantáneamente desde caché local.
"""

import argparse
import logging
import sys
import time

import analytics
import config
import data_manager

# ── Logging con formato legible ──────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main(force: bool) -> None:
    t0 = time.time()

    logger.info("━" * 60)
    logger.info("EquityRisk — Descarga y precálculo de datos")
    logger.info("Universo: %d tickers  |  force=%s", len(config.UNIVERSE_TICKERS), force)
    logger.info("━" * 60)

    # ── Limpiar caché si se pide ─────────────────────────────────────────────
    if force:
        logger.info("Borrando caché existente…")
        data_manager.clear_cache()

    # ── Precios ──────────────────────────────────────────────────────────────
    logger.info("")
    logger.info("── PASO 1/3: Precios de acciones (Yahoo Finance) ──────────")
    prices = data_manager.fetch_prices(
        config.UNIVERSE_TICKERS,
        force_refresh=False,
    )
    n_days, n_cols = prices.shape
    logger.info(
        "Descargados: %d columnas (tickers + petróleo) × %d días",
        n_cols, n_days,
    )
    missing_tickers = set(config.UNIVERSE_TICKERS) - set(prices.columns)
    if missing_tickers:
        logger.warning("Tickers sin datos: %s", sorted(missing_tickers))

    # ── Macro ─────────────────────────────────────────────────────────────────
    logger.info("")
    logger.info("── PASO 2/3: Series macro (FRED) ──────────────────────────")
    macro = data_manager.fetch_macro(force_refresh=False)
    logger.info(
        "Series macro: %s",
        ", ".join(f"{c} ({macro[c].notna().sum()} obs.)" for c in macro.columns),
    )

    # ── Alineación ───────────────────────────────────────────────────────────
    prices_al, macro_al = data_manager.align_data(prices, macro)
    logger.info(
        "Rango común: %s → %s  (%d días)",
        prices_al.index[0].date(), prices_al.index[-1].date(), len(prices_al),
    )

    # ── Sensibilidades ────────────────────────────────────────────────────────
    logger.info("")
    logger.info("── PASO 3/3: Vectores de sensibilidad ─────────────────────")
    logger.info(
        "Parámetros: n_shocks=%d  ventana=%d días",
        config.N_SHOCKS, config.SHOCK_WINDOW_DAYS,
    )

    for mode in ("post", "during"):
        logger.info("Calculando sensibilidad modo=%s…", mode)
        result = analytics.compute_sensitivity(
            prices_al,
            macro_al,
            config.UNIVERSE_TICKERS,
            n_shocks=config.N_SHOCKS,
            window=config.SHOCK_WINDOW_DAYS,
            window_mode=mode,
        )
        data_manager.save_sensitivity(result.raw_returns, result.vectors, mode=mode)

    # ── Resumen final ─────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    logger.info("")
    logger.info("━" * 60)
    logger.info("COMPLETADO en %.1f s", elapsed)
    logger.info("  Caché guardada en: %s/", config.CACHE_DIR)
    logger.info("    %-36s %d días × %d tickers", "prices.csv", *prices_al.shape[::-1])
    logger.info("    %-36s %d días × %d series", "macro.csv", *macro_al.shape[::-1])
    logger.info(
        "    %-36s %d tickers × %d factores",
        "sensitivity_raw_{post,during}.csv",
        *result.raw_returns.shape,
    )
    logger.info("━" * 60)
    logger.info("")
    logger.info("Ahora puedes arrancar la app sin descargas:")
    logger.info("    streamlit run app.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Descarga y precalcula todos los datos de EquityRisk."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Borra la caché existente y vuelve a descargar todo desde cero.",
    )
    args = parser.parse_args()
    main(force=args.force)
