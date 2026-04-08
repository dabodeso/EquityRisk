Actúa como un experto en Ingeniería de Software, Data Science y Quant Finance. Necesito crear una aplicación web en Python (usando Streamlit) para analizar y visualizar la sensibilidad de una cartera de 50 acciones americanas frente a shocks macroeconómicos de los últimos 30 años.

Requisitos Funcionales y Lógica de Cálculo:
Entrada: El usuario introduce una lista de hasta 50 tickers (ej: AAPL, TSLA, MSFT).

Fuentes de Datos (USA):

Usa yfinance para precios de acciones y Petróleo WTI (CL=F).

Usa pandas_datareader (o fredapi) para obtener de la FRED (St. Louis Fed): Tipos de interés (ej: T10Y2Y), Inflación (CPIAUCSL), Desempleo (UNRATE), Tipos de cambio (USD/JPY, EUR/USD) y Gasto en Defensa.

Metodología de Sensibilidad (Event Study):

Para cada variable macro, identifica los 3 periodos históricos de mayor cambio (shocks) tanto al alza (subidas drásticas) como a la baja (caídas drásticas) en los últimos 30 años.

Calcula el retorno de cada acción durante esos periodos específicos.

Normaliza el resultado en un valor entre -1 y 1, donde -1 es una caída máxima y 1 una subida máxima comparada con el histórico de la propia acción en esos eventos.

Vector de Riesgo: Cada activo tendrá un vector detallado con pares de valores: (sensibilidad_subida, sensibilidad_bajada) para cada uno de los 7 factores macro.

Arquitectura del Código (Modular y Limpio):
Quiero el código separado en archivos pequeños, con tipado de datos y docstrings, usando Pandas para las series temporales:

app.py: Interfaz de Streamlit y orquestación.

data_manager.py: Descarga y gestión de datos (Yahoo/FRED). Implementa caché y guardado en un archivo CSV local como base de datos temporal.

analytics.py: Lógica para encontrar los shocks macro y calcular los vectores de sensibilidad (-1 a 1).

config.py: Tickers, IDs de FRED y rangos de fechas.

Requisitos de Visualización (Para Exposición):
Necesito dos visualizaciones potentes en la web:

Heatmap Interactivo (con Plotly): Una matriz donde el eje Y sean las acciones y el eje X los factores de riesgo (subidas/bajadas). Los colores deben ir de rojo (-1) a verde (1) pasando por blanco (0). Debe permitir filtrar y ordenar.

Representación en Subespacio 3D (Reducción de Dimensionalidad):

Toma la matriz completa de vectores de riesgo (50 acciones x 14 variables).

Usa un algoritmo de reducción de dimensionalidad como PCA (Principal Component Analysis) o t-SNE (usando scikit-learn) para reducir las 14 dimensiones a 3 componentes principales.

Visualiza esto en un gráfico de dispersión 3D interactivo de Plotly. Cada punto es una acción, y su posición 3D representa su perfil de riesgo macro comparativo. Las acciones cercanas tendrán riesgos similares. Al pasar el ratón, debe mostrar el ticker.

Por favor, genera primero la estructura de archivos y luego el código completo de cada uno.