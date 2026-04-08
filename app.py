"""
app.py
------
Interfaz Streamlit para el análisis de sensibilidad macro de carteras.

Flujo de caché:
  - Primera ejecución: descarga precios (Yahoo) + macro (FRED), calcula
    sensibilidades y guarda TODO en cache/*.csv.
  - Ejecuciones posteriores: carga directamente desde CSV local, sin
    llamadas a la red, salvo que se active "Forzar recarga".
"""

import logging

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sklearn.decomposition import PCA
from sklearn.manifold import TSNE
from sklearn.preprocessing import StandardScaler

import analytics
import covariance_analysis
import config
import data_manager
import sector_analysis

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_NINGUNO = "(ninguno)"
_TEXT_TPL = "%{text}"

# Streamlit reejecuta todo el script al cambiar cualquier widget. El botón
# "Ejecutar" solo devuelve True en ese rerun; sin estado persistente, un
# selectbox en el cuerpo de la página provocaba st.stop() y la UI "desaparecía".
_SS_ANALYSIS_READY = "_equityrisk_analysis_ready"
_SS_SENSITIVITY_RESULT = "_equityrisk_sensitivity_result"
_SS_PIPELINE_SIG = "_equityrisk_pipeline_sig"

# ── Configuración de la página ───────────────────────────────────────────────

st.set_page_config(
    page_title="EquityRisk – Sensibilidad Macro",
    page_icon="📊",
    layout="wide",
)

st.title("📊 EquityRisk — Sensibilidad de Cartera a Shocks Macroeconómicos")
st.markdown(
    "Analiza cómo reaccionó cada acción ante los mayores shocks históricos "
    "de factores macro en el rango configurado."
)

with st.expander("ℹ️ Cómo se calcula la sensibilidad"):
    st.markdown(
        f"""
1. **Shock macro**  
   Para cada serie (spread, CPI, desempleo, gasto en defensa, petróleo WTI, etc.) se calcula en cada día el
   cambio en **W días hábiles**: `macro[t] − macro[t−W]` (misma W que el deslizador
   *Ventana de retorno*). Se eligen los **N** días con mayor subida y los **N** con
   mayor bajada. Entre dos shocks del **mismo factor y la misma dirección** debe haber
   al menos **{config.SHOCK_MIN_SEPARATION_CALENDAR_DAYS} días naturales** (~12 meses),
   para no contar varias fechas del mismo episodio.

2. **Retorno de la acción en cada episodio** (elige uno en la barra lateral):
   - **Después del shock:** precio el día del shock (o el primer día con dato) →
     precio **W días de trading más adelante**. Mide la **reacción inmediata** tras el hito.
   - **Durante el shock:** precio **W días hábiles antes** del shock → precio **el día
     del shock**. Misma ventana temporal que resume el movimiento del factor macro.

3. **Sensibilidad mostrada**  
   Para cada factor y dirección (↑/↓) se hace la **media** del retorno de la acción
   en los N episodios históricos. Eso se muestra en **%** en el heatmap.  
   Luego, **por columna**, se escala a **[-1, 1]** (dividiendo por el máximo |valor|
   de esa columna) para el gráfico 3D y comparaciones relativas entre acciones.
        """
    )

# ── Barra lateral ────────────────────────────────────────────────────────────

with st.sidebar:
    st.header("⚙️ Configuración")

    # Etiquetas "TICKER – Nombre empresa" para el selector
    ticker_labels = {
        t: f"{t} – {config.TICKER_NAMES.get(t, t)}"
        for t in config.UNIVERSE_TICKERS
    }
    label_to_ticker = {v: k for k, v in ticker_labels.items()}

    selected_labels = st.multiselect(
        "Selecciona acciones para tu cartera",
        options=list(ticker_labels.values()),
        default=list(ticker_labels.values())[:20],
    )
    selected_tickers = [label_to_ticker[lb] for lb in selected_labels]

    st.divider()
    st.subheader("📐 Cartera para análisis de correlación")
    portfolio_labels = st.multiselect(
        "Activos (2-10) para el análisis de covarianza",
        options=list(ticker_labels.values()),
        default=list(ticker_labels.values())[:5],
        key="portfolio_stress",
        help="Selecciona entre 2 y 10 activos. Puedes elegir activos fuera de la cartera principal.",
    )
    portfolio_tickers = [label_to_ticker[lb] for lb in portfolio_labels]

    n_shocks = st.slider("Nº de shocks por factor/dirección", 1, 5, config.N_SHOCKS)
    window_days = st.slider("Ventana de retorno (días)", 21, 126, config.SHOCK_WINDOW_DAYS)

    dim_method = st.selectbox(
        "Algoritmo de reducción 3D",
        ["PCA", "t-SNE"],
        index=0,
    )

    sensitivity_mode = st.radio(
        "Medición de sensibilidad (acción)",
        options=["post", "during"],
        format_func=lambda m: (
            "Después del shock (W días hacia adelante)"
            if m == "post"
            else "Durante el shock (misma ventana W que el macro)"
        ),
        index=0,
        help=(
            "Post: retorno desde la fecha del shock hacia delante. "
            "Durante: retorno de la acción entre t−W y t, alineado con diff(W) del macro."
        ),
    )

    force_refresh = st.checkbox(
        "Forzar recarga de datos",
        value=False,
        help="Borra la caché y vuelve a descargar todo desde Yahoo / FRED.",
    )

    run_button = st.button("▶ Ejecutar análisis", type="primary", use_container_width=True)
    if run_button:
        st.session_state[_SS_ANALYSIS_READY] = True

    st.divider()
    st.caption(
        "Fuentes: Yahoo Finance · FRED (St. Louis Fed)  \n"
        f"Rango: {config.START_DATE} → {config.END_DATE}  \n"
        f"Universo: {len(config.UNIVERSE_TICKERS)} acciones"
    )


# ── Pipeline ─────────────────────────────────────────────────────────────────

def run_pipeline(
    tickers: list[str],
    n_shocks: int,
    window_days: int,
    force_refresh: bool,
    sensitivity_mode: str,
) -> analytics.SensitivityResult:
    """
    Pipeline con caché basada exclusivamente en CSV locales.

    Regla única:
      - force_refresh=False → usa CSV si existe; si no, descarga/calcula y guarda.
      - force_refresh=True  → borra todos los CSV y vuelve a hacer todo desde cero.

    El usuario no necesita gestionar ninguna otra caché: con forzar recarga
    una vez ya queda todo actualizado para las siguientes sesiones.
    """
    if force_refresh:
        data_manager.clear_cache()

    with st.status("Cargando datos…", expanded=True) as status:

        status.update(label="📥 Precios de acciones…")
        prices = data_manager.fetch_prices(tickers, force_refresh=False)

        status.update(label="📥 Series macro (FRED)…")
        macro = data_manager.fetch_macro(force_refresh=False)

        status.update(label="🔗 Alineando series…")
        prices, macro = data_manager.align_data(prices, macro)

        # Sensibilidades: CSV por modo (post / during)
        cached_sens = data_manager.load_sensitivity(mode=sensitivity_mode)
        if cached_sens is not None:
            raw_returns_cached, normalized_cached = cached_sens
            present = [t for t in tickers if t in raw_returns_cached.index]
            if set(tickers) == set(present):
                status.update(label="✅ Sensibilidades cargadas desde caché", state="complete")
                events = analytics.find_shocks(macro, n_shocks=n_shocks, window=window_days)
                return analytics.SensitivityResult(
                    raw_returns=raw_returns_cached.loc[present],
                    vectors=normalized_cached.loc[present],
                    shock_events=events,
                    factor_names=list(macro.columns),
                    window_mode=sensitivity_mode,
                )

        status.update(label="🧮 Calculando vectores de sensibilidad…")
        result = analytics.compute_sensitivity(
            prices,
            macro,
            tickers,
            n_shocks=n_shocks,
            window=window_days,
            window_mode=sensitivity_mode,
        )
        status.update(label="💾 Guardando en caché local…")
        data_manager.save_sensitivity(
            result.raw_returns, result.vectors, mode=sensitivity_mode
        )
        status.update(label="✅ Listo", state="complete")

    return result


# ── Visualización 1: Heatmap de retornos reales ───────────────────────────────

def render_heatmap(raw_returns: pd.DataFrame, window_mode: str = "post") -> None:
    """
    Heatmap donde cada celda muestra el retorno medio real (%) de cada acción
    durante los N eventos históricos de cada factor/dirección.

    El color va de rojo (caída) a verde (subida) escalado simétricamente
    al máximo absoluto del dataset, de modo que el 0 siempre es blanco.
    """
    st.subheader("🌡️ Retorno Medio en Shocks Históricos (%)")
    _wm = (
        "**Ventana:** desde el shock hasta W días de trading adelante."
        if window_mode == "post"
        else "**Ventana:** W días hábiles antes del shock hasta el día del shock (alineado con el diff macro)."
    )
    st.caption(
        "Cada celda = retorno medio de la acción en los N episodios de shock de ese factor. "
        "**Rojo = pérdida media · Verde = ganancia media · Blanco = neutral.**  \n"
        + _wm
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        sort_by = st.selectbox(
            "Ordenar acciones por factor",
            options=[_NINGUNO] + list(raw_returns.columns),
            key="heatmap_sort",
        )
    with col2:
        selected_factors = st.multiselect(
            "Filtrar factores visibles",
            options=list(raw_returns.columns),
            default=list(raw_returns.columns),
            key="heatmap_filter",
        )

    display = raw_returns[selected_factors].copy() if selected_factors else raw_returns.copy()

    if sort_by != _NINGUNO and sort_by in display.columns:
        display = display.sort_values(sort_by, ascending=False)

    # Escala simétrica en torno a 0
    max_abs = display.abs().max().max()
    max_abs = max_abs if max_abs > 0 else 1.0

    # Texto de celda formateado
    text_matrix = display.map(lambda v: f"{v:+.1f}%")

    fig = go.Figure(
        data=go.Heatmap(
            z=display.values,
            x=display.columns.tolist(),
            y=display.index.tolist(),
            text=text_matrix.values,
            texttemplate=_TEXT_TPL,
            textfont={"size": 9},
            colorscale=[
                [0.0, "rgb(220,  50,  47)"],   # rojo  → mayor pérdida
                [0.5, "rgb(255, 255, 255)"],   # blanco → 0 %
                [1.0, "rgb( 38, 166,  91)"],   # verde  → mayor ganancia
            ],
            zmin=-max_abs,
            zmax=max_abs,
            hoverongaps=False,
            hovertemplate=(
                "<b>%{y}</b><br>"
                "Factor: %{x}<br>"
                "Retorno medio: <b>%{text}</b>"
                "<extra></extra>"
            ),
            colorbar={"title": "Retorno (%)"},
        )
    )

    n_tickers = len(display)
    fig.update_layout(
        height=max(450, n_tickers * 24),
        xaxis={"tickangle": -45, "tickfont": {"size": 11}},
        yaxis={"tickfont": {"size": 11}},
        margin={"l": 110, "r": 40, "t": 40, "b": 120},
    )

    st.plotly_chart(fig, width="stretch")

    with st.expander("📋 Ver tabla completa"):
        fmt = display.style.background_gradient(
            cmap="RdYlGn",
            vmin=-max_abs,
            vmax=max_abs,
        ).format("{:+.2f}%")
        st.dataframe(fmt, width="stretch")


# ── Visualización 2: Subespacio 3D ───────────────────────────────────────────

def _qualitative_palette() -> list[str]:
    """Paleta cíclica suficiente para muchos sectores."""
    return (
        px.colors.qualitative.Plotly
        + px.colors.qualitative.Dark24
        + px.colors.qualitative.Set3
        + px.colors.qualitative.Pastel1
    )


def render_3d_subspace(
    vectors: pd.DataFrame,
    method: str,
    sector_map: dict[str, str],
) -> None:
    """
    Reduce el espacio de sensibilidades normalizado a 3 componentes y lo
    visualiza en un scatter 3D interactivo. Acciones próximas = riesgo similar.
    Colorea cada punto por sector (GICS simplificado en config).
    """
    st.subheader(f"🔭 Subespacio 3D de Riesgo Macro ({method})")
    st.markdown(
        "Cada punto es una acción. **La proximidad indica perfil de riesgo similar.** "
        "El color es el **sector**. Pasa el ratón para ver ticker y sector."
    )

    x_raw = vectors.fillna(0).values
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x_raw)

    if x_scaled.shape[0] < 4:
        st.warning("Se necesitan al menos 4 acciones para la reducción de dimensionalidad.")
        return

    if method == "PCA":
        reducer = PCA(n_components=3, random_state=42)
        coords = reducer.fit_transform(x_scaled)
        explained = reducer.explained_variance_ratio_ * 100
        axis_labels = [
            f"PC1 ({explained[0]:.1f}%)",
            f"PC2 ({explained[1]:.1f}%)",
            f"PC3 ({explained[2]:.1f}%)",
        ]
    else:
        perplexity = min(30, max(5, x_scaled.shape[0] // 3))
        reducer = TSNE(n_components=3, random_state=42, perplexity=perplexity)
        coords = reducer.fit_transform(x_scaled)
        axis_labels = ["t-SNE 1", "t-SNE 2", "t-SNE 3"]

    df_3d = pd.DataFrame(coords, columns=["x", "y", "z"], index=vectors.index).reset_index()
    idx_col = "Ticker" if "Ticker" in df_3d.columns else df_3d.columns[0]
    df_3d.rename(columns={idx_col: "ticker"}, inplace=True)
    df_3d["sector"] = df_3d["ticker"].map(lambda t: sector_map.get(str(t), "Sin sector"))

    fig = px.scatter_3d(
        df_3d,
        x="x", y="y", z="z",
        text="ticker",
        color="sector",
        color_discrete_sequence=_qualitative_palette(),
        labels={"x": axis_labels[0], "y": axis_labels[1], "z": axis_labels[2]},
        hover_data={
            "ticker": True,
            "sector": True,
            "x": ":.3f",
            "y": ":.3f",
            "z": ":.3f",
        },
    )
    fig.update_traces(
        marker={"size": 7, "opacity": 0.85, "line": {"width": 0.5, "color": "white"}},
        textposition="top center",
        textfont={"size": 9},
    )
    grid_color = "rgba(255,255,255,0.1)"
    fig.update_layout(
        height=700,
        legend={"title": "Sector", "itemsizing": "constant"},
        scene={
            "xaxis_title": axis_labels[0],
            "yaxis_title": axis_labels[1],
            "zaxis_title": axis_labels[2],
            "bgcolor": "rgb(15, 17, 26)",
            "xaxis": {"gridcolor": grid_color},
            "yaxis": {"gridcolor": grid_color},
            "zaxis": {"gridcolor": grid_color},
        },
        paper_bgcolor="rgb(15, 17, 26)",
        font={"color": "white"},
    )
    st.plotly_chart(fig, width="stretch")

    if method == "PCA":
        with st.expander("Varianza explicada por componente"):
            ev_df = pd.DataFrame({
                "Componente": [f"PC{i+1}" for i in range(3)],
                "Varianza explicada (%)": [f"{v:.2f}" for v in explained],
                "Varianza acumulada (%)": [f"{v:.2f}" for v in np.cumsum(explained)],
            })
            st.dataframe(ev_df, width="stretch", hide_index=True)


# ── Tabla de shocks identificados ───────────────────────────────────────────

def render_shock_table(events: list[analytics.ShockEvent]) -> None:
    """Muestra los shocks históricos identificados en una tabla expandible."""
    with st.expander("🔍 Shocks macro identificados"):
        rows = [
            {
                "Factor": e.factor,
                "Dirección": "⬆ Subida" if e.direction == "up" else "⬇ Bajada",
                "Fecha inicio": e.start_date.date(),
                "Magnitud (pp)": f"{e.shock_magnitude:+.4f}",
            }
            for e in sorted(events, key=lambda x: (x.factor, x.direction, x.start_date))
        ]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)



# ── Visualización 3: Correlación en stress ───────────────────────────────────

def _shock_shapes(
    stress_result: covariance_analysis.StressCorrelationResult,
) -> list[dict]:
    """Genera vrect de Plotly para sombrear cada ventana de shock."""
    shapes = []
    for pc in stress_result.stress_periods:
        end_date = pc.start_date + pd.Timedelta(days=stress_result.window + 30)
        shapes.append({
            "type": "rect",
            "xref": "x", "yref": "paper",
            "x0": str(pc.start_date.date()), "x1": str(end_date.date()),
            "y0": 0, "y1": 1,
            "fillcolor": "rgba(255,80,80,0.12)",
            "line": {"width": 0},
        })
    return shapes


def _dark_layout(**kwargs) -> dict:
    """Layout base con fondo oscuro reutilizable."""
    dark_bg = "rgb(20,22,30)"
    base = {
        "paper_bgcolor": dark_bg,
        "plot_bgcolor": dark_bg,
        "font": {"color": "white"},
        "hovermode": "x unified",
    }
    base.update(kwargs)
    return base


def _render_rolling_avg(sr: covariance_analysis.StressCorrelationResult) -> None:
    rolling = sr.rolling_avg_pairwise.dropna()
    baseline_val = sr.baseline.avg_pairwise

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rolling.index, y=rolling.values,
        mode="lines", name="Corr. media pares",
        line={"color": "#4C9BE8", "width": 1.5},
    ))
    fig.add_hline(
        y=baseline_val, line_dash="dash",
        line_color="rgba(255,255,255,0.5)",
        annotation_text=f"Mercado normal: {baseline_val:.3f}",
        annotation_position="top left",
    )
    fig.update_layout(
        shapes=_shock_shapes(sr),
        height=340,
        yaxis={"title": "Correlación media", "range": [-1, 1]},
        margin={"t": 30, "b": 40},
        **_dark_layout(),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        "Zonas rojas = ventanas de shock macro. "
        "Cuanto más alta la línea, más correladas las acciones (menos diversificación real)."
    )


def _render_effective_factors(sr: covariance_analysis.StressCorrelationResult) -> None:
    rolling = sr.rolling_eff_factors.dropna()
    n_assets = len(sr.tickers)
    baseline_val = sr.baseline.effective_factors

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=rolling.index, y=rolling.values,
        mode="lines", name="Factores efectivos",
        line={"color": "#7BCF72", "width": 1.5},
        fill="tozeroy", fillcolor="rgba(123,207,114,0.08)",
    ))
    fig.add_hline(
        y=baseline_val, line_dash="dash",
        line_color="rgba(255,255,255,0.5)",
        annotation_text=f"Mercado normal: {baseline_val:.2f}",
        annotation_position="top left",
    )
    fig.update_layout(
        shapes=_shock_shapes(sr),
        height=320,
        yaxis={"title": "Nº efectivo factores", "range": [1, n_assets]},
        margin={"t": 30, "b": 40},
        **_dark_layout(),
    )
    st.plotly_chart(fig, width="stretch")
    st.caption(
        f"Rango: 1 (todo correlado) → {n_assets} (todo independiente). "
        "En crisis este número converge a 1: la cartera se comporta como un solo activo."
    )


def _render_pair_correlations(sr: covariance_analysis.StressCorrelationResult) -> None:
    pairs = list(sr.rolling_pairs.columns)
    selected_pair = st.selectbox("Par de activos", options=pairs, key="pair_sel")
    series = sr.rolling_pairs[selected_pair].dropna()

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=series.index, y=series.values,
        mode="lines", name=selected_pair,
        line={"color": "#F5A623", "width": 1.5},
    ))
    fig.add_hline(y=0, line_dash="dot", line_color="rgba(255,255,255,0.3)")
    fig.update_layout(
        shapes=_shock_shapes(sr),
        height=300,
        yaxis={"title": f"Correlación {selected_pair}", "range": [-1, 1]},
        margin={"t": 20, "b": 40},
        **_dark_layout(),
    )
    st.plotly_chart(fig, width="stretch")


def _corr_heatmap_figure(
    pc: covariance_analysis.PeriodCorr,
    color_scale: list,
    *,
    showscale: bool,
    height: int = 320,
) -> go.Figure:
    title = (
        f"<b>{pc.label}</b><br>"
        f"<sup>avg={pc.avg_pairwise:+.3f}  "
        f"N_eff={pc.effective_factors:.2f}  "
        f"({pc.n_obs} obs.)</sup>"
    )
    fig = go.Figure(go.Heatmap(
        z=pc.corr_matrix.values,
        x=pc.corr_matrix.columns.tolist(),
        y=pc.corr_matrix.index.tolist(),
        text=pc.corr_matrix.round(2).values.astype(str),
        texttemplate=_TEXT_TPL,
        colorscale=color_scale,
        zmin=-1, zmax=1,
        showscale=showscale,
    ))
    fig.update_layout(
        title={"text": title, "font": {"size": 11}},
        height=height,
        margin={"t": 70, "b": 20, "l": 60, "r": 20},
        **_dark_layout(),
    )
    return fig


def _render_corr_heatmaps(sr: covariance_analysis.StressCorrelationResult) -> None:
    """Mercado normal + stress agregado separado por factor macro (ventanas concatenadas por factor)."""
    color_scale = [
        [0.0, "rgb(220,50,47)"],
        [0.5, "rgb(255,255,255)"],
        [1.0, "rgb(38,166,91)"],
    ]

    st.markdown("##### Mercado normal")
    st.plotly_chart(
        _corr_heatmap_figure(sr.baseline, color_scale, showscale=True),
        width="stretch",
    )

    if not sr.stress_by_factor:
        st.info(
            "No se pudo construir stress agregado por factor (pocas observaciones por ventana). "
            "Solo se muestra el régimen normal."
        )
        return

    st.markdown("##### Stress agregado por factor de shock")
    st.caption(
        "Por cada factor macro se encadenan solo las ventanas de shock **de ese factor** "
        "(subidas y bajadas); la correlación resume el co-movimiento conjunto en esos episodios."
    )
    summary_rows = [
        {
            "Factor": fac,
            "Corr. media (pares)": f"{pc.avg_pairwise:+.3f}",
            "Nº efectivo": f"{pc.effective_factors:.2f}",
            "Observaciones": pc.n_obs,
        }
        for fac, pc in sr.stress_by_factor.items()
    ]
    st.dataframe(pd.DataFrame(summary_rows), width="stretch", hide_index=True)

    items = list(sr.stress_by_factor.items())
    ncols = min(3, max(1, len(items)))
    for i in range(0, len(items), ncols):
        row_cols = st.columns(ncols)
        for j in range(ncols):
            idx = i + j
            if idx >= len(items):
                break
            _fac, pc = items[idx]
            with row_cols[j]:
                st.plotly_chart(
                    _corr_heatmap_figure(pc, color_scale, showscale=False),
                    width="stretch",
                )


def render_stress_correlations(
    result: analytics.SensitivityResult,
    portfolio_tickers: list[str],
    window_days: int,
) -> None:
    """
    Visualiza cómo evoluciona la estructura de correlaciones de la cartera
    seleccionada durante los eventos de shock macro vs. mercado normal.
    """
    if len(portfolio_tickers) < 2:
        st.warning("Selecciona al menos 2 activos en 'Cartera para análisis de correlación'.")
        return

    prices = data_manager.fetch_prices(portfolio_tickers, force_refresh=False)

    with st.spinner("Calculando correlaciones en stress…"):
        try:
            stress_result = covariance_analysis.compute_stress_correlations(
                prices=prices,
                tickers=portfolio_tickers,
                events=result.shock_events,
                window=window_days,
                rolling_window=window_days,
            )
        except ValueError as exc:
            st.error(str(exc))
            return

    tickers = stress_result.tickers
    st.caption(
        f"Cartera analizada: **{' · '.join(tickers)}**  |  "
        f"Ventana rolling: **{window_days} días**"
    )

    st.subheader("Correlación media de pares (rolling)")
    _render_rolling_avg(stress_result)

    st.subheader("Nº efectivo de factores independientes (rolling)")
    _render_effective_factors(stress_result)

    if len(tickers) > 2:
        st.subheader("Correlación por par individual")
        _render_pair_correlations(stress_result)

    st.subheader("Matrices de correlación: mercado normal vs. stress por factor")
    st.caption(
        "El **stress agregado** va **por factor macro**: solo se encadenan las ventanas de shock "
        "de ese factor (⬆ y ⬇). Abajo, tabla resumen y un heatmap por factor."
    )
    _render_corr_heatmaps(stress_result)


# ── PCA 3D sobre filas agregadas por sector ─────────────────────────────────

def render_sector_pca_3d(sector_vectors: pd.DataFrame) -> None:
    """
    PCA en 3D donde cada punto es un sector y las features son los factores
    macro (media normalizada de las empresas del sector en el análisis actual).
    """
    st.subheader("🔭 PCA 3D — agregado por sector")
    st.caption(
        "Cada punto es un **sector**. Coordenadas = PCA sobre la **media** del vector "
        "normalizado [-1, 1] de las acciones de ese sector presentes en tu selección."
    )
    if len(sector_vectors) < 4:
        st.warning(
            "Se necesitan al menos **4 sectores** con al menos una empresa en la "
            "selección actual para un PCA 3D estable."
        )
        return

    x_raw = sector_vectors.fillna(0).values
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x_raw)

    reducer = PCA(n_components=3, random_state=42)
    coords = reducer.fit_transform(x_scaled)
    explained = reducer.explained_variance_ratio_ * 100
    axis_labels = [
        f"PC1 ({explained[0]:.1f}%)",
        f"PC2 ({explained[1]:.1f}%)",
        f"PC3 ({explained[2]:.1f}%)",
    ]

    df_3d = pd.DataFrame(coords, columns=["x", "y", "z"], index=sector_vectors.index)
    df_3d = df_3d.reset_index()
    sec_col = "Sector" if "Sector" in df_3d.columns else df_3d.columns[0]
    df_3d.rename(columns={sec_col: "sector"}, inplace=True)

    fig = px.scatter_3d(
        df_3d,
        x="x", y="y", z="z",
        text="sector",
        color="sector",
        color_discrete_sequence=_qualitative_palette(),
        labels={"x": axis_labels[0], "y": axis_labels[1], "z": axis_labels[2]},
        hover_data={"sector": True, "x": ":.3f", "y": ":.3f", "z": ":.3f"},
    )
    fig.update_traces(
        marker={"size": 11, "opacity": 0.9, "line": {"width": 0.5, "color": "white"}},
        textposition="top center",
        textfont={"size": 11},
    )
    grid_color = "rgba(255,255,255,0.1)"
    fig.update_layout(
        height=700,
        legend={"title": "Sector"},
        scene={
            "xaxis_title": axis_labels[0],
            "yaxis_title": axis_labels[1],
            "zaxis_title": axis_labels[2],
            "bgcolor": "rgb(15, 17, 26)",
            "xaxis": {"gridcolor": grid_color},
            "yaxis": {"gridcolor": grid_color},
            "zaxis": {"gridcolor": grid_color},
        },
        paper_bgcolor="rgb(15, 17, 26)",
        font={"color": "white"},
    )
    st.plotly_chart(fig, width="stretch")

    ev_df = pd.DataFrame({
        "Componente": [f"PC{i+1}" for i in range(3)],
        "Varianza explicada (%)": [f"{v:.2f}" for v in explained],
        "Varianza acumulada (%)": [f"{v:.2f}" for v in np.cumsum(explained)],
    })
    with st.expander("Varianza explicada (PCA sectorial)"):
        st.dataframe(ev_df, width="stretch", hide_index=True)


# ── Visualización 4: Análisis por Sectores ───────────────────────────────────

def render_sector_analysis(
    result: analytics.SensitivityResult,
    prices: pd.DataFrame,
    window_days: int,
) -> None:
    """
    Dos visualizaciones agregadas por sector:
      1. Heatmap de sensibilidad media por sector (misma escala que el individual).
      2. Correlación entre sectores durante shocks (usa índices igual-ponderados).
    """
    sector_map = config.SECTOR_MAP

    # ── 1. Sensibilidad media por sector ─────────────────────────────────────
    st.subheader("📊 Sensibilidad media por sector (%)")
    _sect_wm = (
        "Misma medición **post-shock** que en la pestaña de sensibilidad."
        if result.window_mode == "post"
        else "Misma medición **durante el shock** que en la pestaña de sensibilidad."
    )
    st.caption(
        "Media del retorno de todas las empresas del sector en cada tipo de shock. "
        "Permite identificar qué sectores son más vulnerables a cada factor macro. "
        + _sect_wm
    )

    with st.spinner("Agregando sensibilidades por sector…"):
        sector_sens = sector_analysis.compute_sector_sensitivity(
            result.raw_returns, sector_map
        )

    if sector_sens.empty:
        st.warning("No hay suficientes datos para el análisis sectorial.")
        return

    col1, col2 = st.columns([2, 1])
    with col1:
        sort_sect = st.selectbox(
            "Ordenar sectores por factor",
            options=[_NINGUNO] + list(sector_sens.columns),
            key="sect_sort",
        )
    with col2:
        filt_sect = st.multiselect(
            "Filtrar factores",
            options=list(sector_sens.columns),
            default=list(sector_sens.columns),
            key="sect_filter",
        )

    display = sector_sens[filt_sect].copy() if filt_sect else sector_sens.copy()
    if sort_sect != _NINGUNO and sort_sect in display.columns:
        display = display.sort_values(sort_sect, ascending=False)

    max_abs = display.abs().max().max()
    max_abs = max_abs if max_abs > 0 else 1.0
    text_m = display.map(lambda v: f"{v:+.1f}%")

    fig = go.Figure(go.Heatmap(
        z=display.values,
        x=display.columns.tolist(),
        y=display.index.tolist(),
        text=text_m.values,
        texttemplate=_TEXT_TPL,
        textfont={"size": 10},
        colorscale=[
            [0.0, "rgb(220,50,47)"],
            [0.5, "rgb(255,255,255)"],
            [1.0, "rgb(38,166,91)"],
        ],
        zmin=-max_abs, zmax=max_abs,
        hoverongaps=False,
        hovertemplate=(
            "<b>%{y}</b><br>Factor: %{x}<br>"
            "Retorno medio: <b>%{text}</b><extra></extra>"
        ),
        colorbar={"title": "Retorno (%)"},
    ))
    fig.update_layout(
        height=max(300, len(display) * 40),
        xaxis={"tickangle": -45, "tickfont": {"size": 11}},
        yaxis={"tickfont": {"size": 12}},
        margin={"l": 160, "r": 40, "t": 30, "b": 120},
    )
    st.plotly_chart(fig, width="stretch")

    with st.expander("📋 Tabla de sensibilidades sectoriales"):
        fmt = display.style.background_gradient(
            cmap="RdYlGn", vmin=-max_abs, vmax=max_abs
        ).format("{:+.2f}%")
        st.dataframe(fmt, width="stretch")

    sector_vectors_agg = sector_analysis.aggregate_by_sector(result.vectors, sector_map)
    render_sector_pca_3d(sector_vectors_agg)

    st.divider()

    # ── 2. Correlación entre sectores en stress ───────────────────────────────
    st.subheader("🔗 Correlación entre sectores en episodios de stress")
    st.caption(
        "Índices de sector construidos como media igual-ponderada de sus componentes. "
        "Muestra si los sectores se mueven juntos o divergen durante shocks macro."
    )

    with st.spinner("Calculando correlación inter-sectorial…"):
        try:
            sect_stress = sector_analysis.compute_sector_stress_correlations(
                prices=prices,
                sector_map=sector_map,
                events=result.shock_events,
                window=window_days,
                rolling_window=window_days,
            )
        except ValueError as exc:
            st.error(str(exc))
            return

    st.caption(
        f"Sectores: **{' · '.join(sect_stress.tickers)}**  |  "
        f"Ventana rolling: **{window_days} días**"
    )

    st.subheader("Correlación media entre sectores (rolling)")
    _render_rolling_avg(sect_stress)

    st.subheader("Nº efectivo de sectores independientes (rolling)")
    _render_effective_factors(sect_stress)

    st.subheader("Matrices de correlación entre sectores: normal vs. stress por factor")
    st.caption(
        "Misma lógica que en la cartera: por cada factor macro, ventanas de shock concatenadas "
        "sobre índices sectoriales; tabla resumen y heatmap por factor."
    )
    _render_corr_heatmaps(sect_stress)


# ── Ejecución principal ──────────────────────────────────────────────────────

if not st.session_state.get(_SS_ANALYSIS_READY, False):
    st.info(
        "👈 Selecciona las acciones en la barra lateral y pulsa **Ejecutar análisis**.  \n"
        "La primera ejecución descarga datos de Yahoo Finance y FRED (~1-2 min). "
        "Las siguientes cargan desde caché local al instante."
    )
    st.stop()

if len(selected_tickers) < 2:
    st.error("Selecciona al menos 2 acciones.")
    st.stop()

_pipeline_sig = (
    tuple(sorted(selected_tickers)),
    int(n_shocks),
    int(window_days),
    str(sensitivity_mode),
)
_cache_ok = (
    st.session_state.get(_SS_PIPELINE_SIG) == _pipeline_sig
    and _SS_SENSITIVITY_RESULT in st.session_state
)

if run_button:
    try:
        result = run_pipeline(
            tickers=selected_tickers,
            n_shocks=n_shocks,
            window_days=window_days,
            force_refresh=force_refresh,
            sensitivity_mode=sensitivity_mode,
        )
    except Exception as exc:
        st.error(f"Error durante el análisis: {exc}")
        logger.exception("Error en pipeline")
        st.stop()
    st.session_state[_SS_SENSITIVITY_RESULT] = result
    st.session_state[_SS_PIPELINE_SIG] = _pipeline_sig
elif _cache_ok:
    result = st.session_state[_SS_SENSITIVITY_RESULT]
else:
    st.warning(
        "Los parámetros del análisis principal (acciones, N shocks, ventana o modo de sensibilidad) "
        "cambiaron respecto a la última ejecución. Pulsa **Ejecutar análisis** para recalcular; "
        "mientras tanto se muestra el último resultado válido."
    )
    result = st.session_state.get(_SS_SENSITIVITY_RESULT)
    if result is None:
        st.info("No hay ningún resultado en caché de sesión; pulsa **Ejecutar análisis**.")
        st.stop()

n_actions = len(result.raw_returns)
n_factors = len(result.raw_returns.columns)
_mode_label = (
    "después del shock (W días hacia adelante)"
    if result.window_mode == "post"
    else "durante el shock (t−W → t)"
)
st.success(
    f"✅ **{n_actions}** acciones · **{n_factors}** combinaciones factor/dirección  ·  "
    f"medición: {_mode_label}"
)

# Cargamos precios desde caché (necesarios en varias pestañas)
all_tickers = list(set(selected_tickers) | set(config.UNIVERSE_TICKERS))
prices_full = data_manager.fetch_prices(all_tickers, force_refresh=False)

tab_sens, tab_3d, tab_cov, tab_sect = st.tabs([
    "🌡️ Sensibilidad macro",
    "🔭 Subespacio 3D",
    "📐 Correlación en stress",
    "🏭 Por Sectores",
])

with tab_sens:
    render_heatmap(result.raw_returns, window_mode=result.window_mode)
    render_shock_table(result.shock_events)

with tab_3d:
    render_3d_subspace(result.vectors, method=dim_method, sector_map=config.SECTOR_MAP)

with tab_cov:
    render_stress_correlations(
        result=result,
        portfolio_tickers=portfolio_tickers,
        window_days=window_days,
    )

with tab_sect:
    render_sector_analysis(
        result=result,
        prices=prices_full,
        window_days=window_days,
    )
