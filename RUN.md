## Comandos para ejecutar el proyecto (Windows)

### 1) Crear y activar un entorno virtual (recomendado)

```powershell
cd "C:\Users\dabod\OneDrive\Documents\Code\EquityRisk"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

### 2) Instalar dependencias

```powershell
pip install -r requirements.txt
```

### 3) (Opcional pero recomendado) Descargar y precalcular datos

La **primera vez** conviene ejecutar el script de precálculo para que la app arranque desde caché local.

```powershell
python download_data.py
```

Si quieres **borrar caché y recalcular todo desde cero**:

```powershell
python download_data.py --force
```

### 4) Ejecutar la aplicación web

```powershell
streamlit run app.py
```

### 5) Notas rápidas

- Los archivos de caché se guardan en la carpeta `cache/` (CSV).
- Si cambias `config.py` (tickers/rango/factores) y quieres regenerar todo, usa `--force`.

