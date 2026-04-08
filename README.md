# EquityRisk

Aplicación web (**Streamlit**) para analizar la **sensibilidad de acciones estadounidenses** frente a **shocks macroeconómicos** históricos, visualizar el perfil de riesgo en un espacio 3D y estudiar cómo cambia la **correlación** de una cartera (y de sectores) en periodos de estrés.

---

## Qué hace la aplicación

1. **Descarga y alinea datos**  
   Precios de cierre ajustados (Yahoo Finance) y series macro (principalmente [FRED](https://fred.stlouisfed.org/), más petróleo WTI vía Yahoo). Todo se puede cachear en CSV bajo `cache/` para no repetir descargas.

2. **Identifica shocks macro**  
   Para cada serie macro se calcula el cambio en una ventana de **W** días hábiles (configurable). Se seleccionan los **N** episodios de mayor movimiento al alza y los **N** a la baja. Entre dos shocks del **mismo factor y la misma dirección** debe haber al menos **365 días naturales** (~12 meses), para no contar varias fechas del mismo episodio.

3. **Mide sensibilidad de cada acción**  
   Para cada combinación factor + dirección (↑/↓) se calcula el **retorno medio** de la acción en esos episodios (en porcentaje). Hay dos modos de ventana:
   - **Post-shock:** del día del shock a **W** días de trading hacia adelante.  
   - **Durante el shock:** de **t−W** a **t**, alineado con la misma ventana que define el cambio del factor macro.

   Esos retornos se **normalizan columna a columna** a **[-1, 1]** para comparar activos en el gráfico 3D (PCA o t-SNE).

4. **Visualización en cuatro bloques**
   - **Sensibilidad macro:** heatmap de retornos medios (%), tabla de shocks detectados.  
   - **Subespacio 3D:** cada acción como punto según su vector normalizado; color por sector.  
   - **Correlación en estrés:** correlación rolling, pares, matrices **mercado normal** frente a **stress agregado por factor** (ventanas de shock de ese factor concatenadas).  
   - **Por sectores:** agregación por sector (sensibilidad media, PCA sectorial, correlación entre índices sectoriales con la misma lógica de stress por factor).

---

## Fuentes de datos

| Origen | Uso |
|--------|-----|
| **Yahoo Finance** | Precios de acciones del universo definido en `config.py` |
| **FRED** | Spread 10Y–2Y, CPI, desempleo, gasto federal en defensa |
| **Yahoo (`CL=F`)** | Petróleo WTI, integrado en el panel macro con el mismo tratamiento de frecuencia que el resto |

El rango temporal por defecto va desde **1975** hasta la fecha actual (`config.py`).

---

## Estructura del código

| Archivo | Función |
|---------|---------|
| `app.py` | Interfaz Streamlit, pestañas, gráficos Plotly, orquestación del pipeline y caché en sesión |
| `config.py` | Universo de tickers, mapa de sectores, IDs FRED, fechas, parámetros de shocks y rutas de caché |
| `data_manager.py` | Descarga, alineación de series, lectura/escritura de CSV en `cache/` |
| `analytics.py` | Detección de shocks, retornos post/durante, vectores de sensibilidad |
| `covariance_analysis.py` | Correlaciones rolling, baseline, stress por factor |
| `sector_analysis.py` | Índices sectoriales, agregados y correlación inter-sector |
| `download_data.py` | Script opcional para precargar caché (universo completo, modos post y during) |

---

## Cómo ejecutarlo en local

Requisitos: **Python 3.10+** (recomendado).

```powershell
cd ruta\al\proyecto
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Opcional (primera vez, para llenar `cache/` sin abrir la app):

```powershell
python download_data.py
```

Arrancar la app:

```powershell
streamlit run app.py
```

Para forzar borrado de caché y recálculo desde cero: en la barra lateral de la app, **Forzar recarga de datos**, o `python download_data.py --force`.

La carpeta `cache/` está en `.gitignore`; en un despliegue nuevo (p. ej. Streamlit Cloud) los datos se generan en la primera ejecución.

---

## Despliegue en Streamlit Community Cloud

1. Sube el repositorio a **GitHub** (rama `main`, entrada `app.py`).  
2. En [share.streamlit.io](https://share.streamlit.io), conecta el repo y elige **Main file:** `app.py`.  
3. Las dependencias se instalan desde `requirements.txt`.  
4. No hace falta API key para las series públicas de FRED/Yahoo en el uso típico; si en el futuro añades claves, configúralas en **App settings → Secrets**.

---

## Parámetros que suele tocar el usuario

En la interfaz: selección de acciones, cartera para correlación, **N** de shocks, ventana **W**, modo post/durante, PCA vs t-SNE.

En `config.py` (requiere regenerar datos si cambias series o universo): `UNIVERSE_TICKERS`, `FRED_SERIES`, `START_DATE` / `END_DATE`, `N_SHOCKS`, `SHOCK_WINDOW_DAYS`, `SHOCK_MIN_SEPARATION_CALENDAR_DAYS`, `SECTOR_MAP`.

---

## Licencia

Especifica aquí la licencia del repositorio si aplica (por ejemplo MIT).
