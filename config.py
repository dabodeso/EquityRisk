"""
config.py
---------
Configuración central: universo de tickers, series macro (FRED + WTI Yahoo),
rangos de fechas y parámetros del análisis.
"""

from datetime import date

# ── Rango temporal ──────────────────────────────────────────────────────────
# 50 años de historia macro: cubre el shock del petróleo del 73-74 (con margen),
# la inflación de Volcker, el crash del 87, la crisis del 94, el 2000, el 2008
# y el ciclo inflacionario del 2022.
START_DATE: str = "1975-01-01"
END_DATE: str = date.today().isoformat()

# ── Universo fijo de tickers ────────────────────────────────────────────────
# Todas llevan cotizando al menos desde los 80 (la mayoría desde los 60-70).
# Nota: este universo se usa como lista cerrada en la UI.
UNIVERSE_TICKERS: list[str] = [
    # ── Tecnología / Industrial clásico ───────────────────────────────────
    "IBM",   # International Business Machines  (NYSE desde ~1916)
    "TXN",   # Texas Instruments                (NYSE desde 1972)
    "INTC",  # Intel                            (IPO 1971)
    "HPQ",   # HP Inc                           (HP desde 1957, split 2015)
    "GLW",   # Corning                          (NYSE desde 1945)
    "EMR",   # Emerson Electric                 (NYSE desde 1956)
    # ── Finanzas ──────────────────────────────────────────────────────────
    "JPM",   # JPMorgan Chase                   (Chase Manhattan desde 1969)
    "BAC",   # Bank of America                  (historia continua desde 1960s)
    "WFC",   # Wells Fargo                      (NYSE desde 1962)
    "AXP",   # American Express                 (NYSE desde 1977)
    "BRK-B", # Berkshire Hathaway               (desde 1965)
    "USB",   # U.S. Bancorp                     (NYSE desde 1929)
    # ── Salud ─────────────────────────────────────────────────────────────
    "JNJ",   # Johnson & Johnson                (NYSE desde 1944)
    "PFE",   # Pfizer                           (NYSE desde 1944)
    "ABT",   # Abbott Laboratories              (NYSE desde 1929)
    "MRK",   # Merck                            (NYSE desde 1946)
    "LLY",   # Eli Lilly                        (NYSE desde 1952)
    "BMY",   # Bristol-Myers Squibb             (NYSE desde 1929)
    "MDT",   # Medtronic                        (NYSE/NASDAQ desde 1960)
    "BDX",   # Becton Dickinson                 (NYSE desde 1926)
    # ── Energía ───────────────────────────────────────────────────────────
    "XOM",   # ExxonMobil                       (Exxon desde 1970)
    "CVX",   # Chevron                          (historia larga)
    "SLB",   # SLB / Schlumberger               (NYSE desde 1962)
    "HAL",   # Halliburton                      (NYSE desde 1948)
    # ── Consumo básico ────────────────────────────────────────────────────
    "KO",    # Coca-Cola                        (NYSE desde 1919)
    "PEP",   # PepsiCo                          (NYSE desde 1977)
    "PG",    # Procter & Gamble                 (NYSE desde 1891)
    "CL",    # Colgate-Palmolive                (NYSE desde 1964)
    "MO",    # Altria / Philip Morris           (NYSE desde 1925)
    "GIS",   # General Mills                    (NYSE desde 1928)
    "CPB",   # Campbell Soup                    (NYSE desde 1954)
    "HRL",   # Hormel Foods                     (NYSE desde 1927)
    "CLX",   # Clorox                           (NYSE desde 1928)
    "HSY",   # Hershey                          (NYSE desde 1927)
    # ── Consumo discrecional ──────────────────────────────────────────────
    "MCD",   # McDonald's                       (NYSE desde 1966)
    "WMT",   # Walmart                          (NYSE desde 1970)
    "LOW",   # Lowe's                           (NYSE desde 1961)
    "DIS",   # Walt Disney                      (NYSE desde 1957)
    "F",     # Ford Motor                       (NYSE desde 1956)
    # ── Industrial / Defensa ──────────────────────────────────────────────
    "MMM",   # 3M                               (NYSE desde 1946)
    "CAT",   # Caterpillar                      (NYSE desde 1929)
    "HON",   # Honeywell                        (NYSE desde 1920s)
    "BA",    # Boeing                           (NYSE desde 1934)
    "GD",    # General Dynamics                 (NYSE desde 1952)
    "ITW",   # Illinois Tool Works              (NYSE desde 1967)
    "GE",    # GE Aerospace                     (NYSE desde ~1900)
    # ── Materiales / Diversificado ────────────────────────────────────────
    "PPG",   # PPG Industries                   (NYSE desde 1968)
    "SHW",   # Sherwin-Williams                 (NYSE desde 1964)
    "NUE",   # Nucor Steel                      (NYSE desde 1969)
    "ECL",   # Ecolab                           (NYSE desde 1957)
    "APD",   # Air Products & Chemicals         (NYSE desde 1961)
    # ── Energía (añadido para completar 5) ────────────────────────────────
    "OXY",   # Occidental Petroleum             (NYSE desde 1964)
    # ── Añadidos: 50 tickers extra (historia ≥ 1980) ──────────────────────
    # Tecnología
    "AAPL",  # Apple (IPO 1980)
    "MSFT",  # Microsoft (IPO 1986)
    "ORCL",  # Oracle (IPO 1986)
    "ADBE",  # Adobe (IPO 1986)
    "AMAT",  # Applied Materials (IPO 1972)
    "LRCX",  # Lam Research (IPO 1984)
    "KLAC",  # KLA (IPO 1980)
    "ADI",   # Analog Devices (NYSE desde 1965)
    # Finanzas / Bancos / Brokers
    "C",     # Citigroup (listado moderno desde 1986)
    "PNC",   # PNC Financial (listado desde 1983)
    "SCHW",  # Charles Schwab (IPO 1987)
    "BK",    # Bank of New York Mellon (BK desde 1973)
    "STT",   # State Street (listado desde 1986)
    "MS",    # Morgan Stanley (IPO 1986)
    "BEN",   # Franklin Resources (NYSE desde 1947)
    # Seguros (sector nuevo)
    "AIG",   # American International Group (listado desde 1984)
    # Salud
    "AMGN",  # Amgen (IPO 1983)
    "CI",    # Cigna (listado desde 1982)
    "HUM",   # Humana (listado desde 1971)
    "SYK",   # Stryker (desde 1979)
    "TFX",   # Teleflex (listado desde 1983)
    # Energía
    "COP",   # ConocoPhillips (historia larga; reestructuras)
    "EOG",   # EOG Resources (1985)
    "OKE",   # ONEOK (1980)
    "WMB",   # Williams Companies (1974)
    # Consumo básico
    "KMB",   # Kimberly-Clark (1928)
    "KR",    # Kroger (1977)
    "SYY",   # Sysco (1970)
    "ADM",   # Archer-Daniels-Midland (1924)
    "CAG",   # Conagra Brands (1982)
    # Telecom (sector nuevo)
    "T",     # AT&T (1983 como ticker moderno)
    "VZ",    # Verizon (1983 como Bell Atlantic)
    "CMCSA", # Comcast (listado desde 1972)
    # Transporte (sector nuevo)
    "UNP",   # Union Pacific (1969)
    "CSX",   # CSX (1980)
    "NSC",   # Norfolk Southern (1982)
    "FDX",   # FedEx (1978)
    "LUV",   # Southwest Airlines (1972)
    # Aeroespacial/Defensa (subsector nuevo)
    "NOC",   # Northrop Grumman (historia larga)
    # Materiales / minería / packaging (sectores nuevos dentro de Materiales)
    "NEM",   # Newmont (1925)
    "IFF",   # IFF (1968)
    "IP",    # International Paper (1969)
    "BALL",  # Ball Corporation (NYSE; yfinance ya no sirve BLL)
]

# Nombres legibles para el selector de la UI
TICKER_NAMES: dict[str, str] = {
    "IBM":   "IBM",
    "TXN":   "Texas Instruments",
    "INTC":  "Intel",
    "HPQ":   "HP Inc",
    "GLW":   "Corning",
    "EMR":   "Emerson Electric",
    "JPM":   "JPMorgan Chase",
    "BAC":   "Bank of America",
    "WFC":   "Wells Fargo",
    "AXP":   "American Express",
    "BRK-B": "Berkshire Hathaway",
    "USB":   "U.S. Bancorp",
    "JNJ":   "Johnson & Johnson",
    "PFE":   "Pfizer",
    "ABT":   "Abbott",
    "MRK":   "Merck",
    "LLY":   "Eli Lilly",
    "BMY":   "Bristol-Myers Squibb",
    "MDT":   "Medtronic",
    "BDX":   "Becton Dickinson",
    "XOM":   "ExxonMobil",
    "CVX":   "Chevron",
    "SLB":   "SLB / Schlumberger",
    "HAL":   "Halliburton",
    "KO":    "Coca-Cola",
    "PEP":   "PepsiCo",
    "PG":    "Procter & Gamble",
    "CL":    "Colgate-Palmolive",
    "MO":    "Altria",
    "GIS":   "General Mills",
    "CPB":   "Campbell Soup",
    "HRL":   "Hormel",
    "CLX":   "Clorox",
    "HSY":   "Hershey",
    "MCD":   "McDonald's",
    "WMT":   "Walmart",
    "LOW":   "Lowe's",
    "DIS":   "Disney",
    "F":     "Ford Motor",
    "MMM":   "3M",
    "CAT":   "Caterpillar",
    "HON":   "Honeywell",
    "BA":    "Boeing",
    "GD":    "General Dynamics",
    "ITW":   "Illinois Tool Works",
    "GE":    "GE Aerospace",
    "PPG":   "PPG Industries",
    "SHW":   "Sherwin-Williams",
    "NUE":   "Nucor Steel",
    "ECL":   "Ecolab",
    "APD":   "Air Products",
    "OXY":   "Occidental Petroleum",
    "AAPL":  "Apple",
    "MSFT":  "Microsoft",
    "ORCL":  "Oracle",
    "ADBE":  "Adobe",
    "AMAT":  "Applied Materials",
    "LRCX":  "Lam Research",
    "KLAC":  "KLA",
    "ADI":   "Analog Devices",
    "C":     "Citigroup",
    "PNC":   "PNC Financial",
    "SCHW":  "Charles Schwab",
    "BK":    "BNY Mellon",
    "STT":   "State Street",
    "MS":    "Morgan Stanley",
    "BEN":   "Franklin Resources",
    "AIG":   "AIG",
    "AMGN":  "Amgen",
    "CI":    "Cigna",
    "HUM":   "Humana",
    "SYK":   "Stryker",
    "TFX":   "Teleflex",
    "COP":   "ConocoPhillips",
    "EOG":   "EOG Resources",
    "OKE":   "ONEOK",
    "WMB":   "Williams Companies",
    "KMB":   "Kimberly-Clark",
    "KR":    "Kroger",
    "SYY":   "Sysco",
    "ADM":   "Archer-Daniels-Midland",
    "CAG":   "Conagra Brands",
    "T":     "AT&T",
    "VZ":    "Verizon",
    "CMCSA": "Comcast",
    "UNP":   "Union Pacific",
    "CSX":   "CSX",
    "NSC":   "Norfolk Southern",
    "FDX":   "FedEx",
    "LUV":   "Southwest Airlines",
    "NOC":   "Northrop Grumman",
    "NEM":   "Newmont",
    "IFF":   "IFF",
    "IP":    "International Paper",
    "BALL":  "Ball Corporation",
}

# ── Mapa de sectores ─────────────────────────────────────────────────────────
# Usado para el análisis agregado por sector.
# Mínimo 5 empresas por sector; todas con historial largo (ver comentarios arriba).
SECTOR_MAP: dict[str, str] = {
    # Tecnología
    "IBM":   "Tecnología",
    "TXN":   "Tecnología",
    "INTC":  "Tecnología",
    "HPQ":   "Tecnología",
    "GLW":   "Tecnología",
    "EMR":   "Tecnología",
    "AAPL":  "Tecnología",
    "MSFT":  "Tecnología",
    "ORCL":  "Tecnología",
    "ADBE":  "Tecnología",
    "AMAT":  "Tecnología",
    "LRCX":  "Tecnología",
    "KLAC":  "Tecnología",
    "ADI":   "Tecnología",
    # Finanzas
    "JPM":   "Finanzas",
    "BAC":   "Finanzas",
    "WFC":   "Finanzas",
    "AXP":   "Finanzas",
    "BRK-B": "Finanzas",
    "USB":   "Finanzas",
    "C":     "Finanzas",
    "PNC":   "Finanzas",
    "SCHW":  "Finanzas",
    "BK":    "Finanzas",
    "STT":   "Finanzas",
    "MS":    "Finanzas",
    "BEN":   "Finanzas",
    # Seguros (sector nuevo)
    "AIG":   "Seguros",
    # Salud
    "JNJ":   "Salud",
    "PFE":   "Salud",
    "ABT":   "Salud",
    "MRK":   "Salud",
    "LLY":   "Salud",
    "BMY":   "Salud",
    "MDT":   "Salud",
    "BDX":   "Salud",
    "AMGN":  "Salud",
    "CI":    "Salud",
    "HUM":   "Salud",
    "SYK":   "Salud",
    "TFX":   "Salud",
    # Energía
    "XOM":   "Energía",
    "CVX":   "Energía",
    "SLB":   "Energía",
    "HAL":   "Energía",
    "OXY":   "Energía",
    "COP":   "Energía",
    "EOG":   "Energía",
    "OKE":   "Energía",
    "WMB":   "Energía",
    # Consumo Básico
    "KO":    "Consumo Básico",
    "PEP":   "Consumo Básico",
    "PG":    "Consumo Básico",
    "CL":    "Consumo Básico",
    "MO":    "Consumo Básico",
    "GIS":   "Consumo Básico",
    "CPB":   "Consumo Básico",
    "HRL":   "Consumo Básico",
    "CLX":   "Consumo Básico",
    "HSY":   "Consumo Básico",
    "KMB":   "Consumo Básico",
    "KR":    "Consumo Básico",
    "SYY":   "Consumo Básico",
    "ADM":   "Consumo Básico",
    "CAG":   "Consumo Básico",
    # Consumo Discrecional
    "MCD":   "Cons. Discrecional",
    "WMT":   "Cons. Discrecional",
    "LOW":   "Cons. Discrecional",
    "DIS":   "Cons. Discrecional",
    "F":     "Cons. Discrecional",
    # Industrial / Defensa
    "MMM":   "Industrial",
    "CAT":   "Industrial",
    "HON":   "Industrial",
    "BA":    "Industrial",
    "GD":    "Industrial",
    "ITW":   "Industrial",
    "GE":    "Industrial",
    "NOC":   "Industrial",
    # Materiales
    "PPG":   "Materiales",
    "SHW":   "Materiales",
    "NUE":   "Materiales",
    "ECL":   "Materiales",
    "APD":   "Materiales",
    "NEM":   "Materiales",
    "IFF":   "Materiales",
    "IP":    "Materiales",
    "BALL":  "Materiales",
    # Telecom (sector nuevo)
    "T":     "Telecom",
    "VZ":    "Telecom",
    "CMCSA": "Telecom",
    # Transporte (sector nuevo)
    "UNP":   "Transporte",
    "CSX":   "Transporte",
    "NSC":   "Transporte",
    "FDX":   "Transporte",
    "LUV":   "Transporte",
}

# ── Series macro de FRED ─────────────────────────────────────────────────────
FRED_SERIES: dict[str, str] = {
    "Spread_10Y2Y":  "T10Y2Y",      # Diferencial tipos 10Y-2Y (pp) — desde 1976
    "Inflacion_CPI": "CPIAUCSL",    # IPC — desde 1947
    "Desempleo":     "UNRATE",      # Tasa desempleo — desde 1948
    "Gasto_Defensa": "FDEFX",       # Gasto federal en Defensa — desde 1947
}

# Petróleo WTI (futuro continuo) vía Yahoo Finance — se fusiona en fetch_macro
OIL_TICKER: str = "CL=F"
OIL_SERIES_NAME: str = "Petroleo_WTI"

# ── Parámetros del Event Study ───────────────────────────────────────────────
N_SHOCKS: int = 3
SHOCK_WINDOW_DAYS: int = 63   # ~3 meses de trading (diff del macro y retornos)
# Días naturales entre shocks del mismo factor y dirección (~12 meses)
SHOCK_MIN_SEPARATION_CALENDAR_DAYS: int = 365

# ── Rutas de caché ───────────────────────────────────────────────────────────
CACHE_DIR: str = "cache"
PRICES_CACHE: str          = f"{CACHE_DIR}/prices.csv"
MACRO_CACHE: str           = f"{CACHE_DIR}/macro.csv"
# Sensibilidad: un CSV por modo (post-shock vs durante shock)
RAW_RETURNS_CACHE_POST: str   = f"{CACHE_DIR}/sensitivity_raw_post.csv"
NORM_VECTORS_CACHE_POST: str  = f"{CACHE_DIR}/sensitivity_normalized_post.csv"
RAW_RETURNS_CACHE_DURING: str = f"{CACHE_DIR}/sensitivity_raw_during.csv"
NORM_VECTORS_CACHE_DURING: str = f"{CACHE_DIR}/sensitivity_normalized_during.csv"


def sensitivity_cache_paths(mode: str) -> tuple[str, str]:
    """Rutas (raw %, normalizado) para el modo de ventana: ``post`` o ``during``."""
    if mode == "post":
        return RAW_RETURNS_CACHE_POST, NORM_VECTORS_CACHE_POST
    if mode == "during":
        return RAW_RETURNS_CACHE_DURING, NORM_VECTORS_CACHE_DURING
    raise ValueError(f"mode debe ser 'post' o 'during', recibido: {mode!r}")
