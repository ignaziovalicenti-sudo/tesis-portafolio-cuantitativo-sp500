#Script 0
pip install scipy

#Script 1
import datetime as dt
import json
import logging
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from scipy.stats import linregress
from tqdm import tqdm

# ============================== CONFIGURACION ==============================
FILTRO_MACRO = "SPY"
BENCHMARK_MOMENTUM = "SPMO"
REFUGIO_RENTA_FIJA = "SHY"
REFUGIO_CASH_LIQUIDEZ = "BIL"
COBERTURA_BAJISTA = "SH"

ETFS_SATELITE = [
    "SPHB",
    "QQQ", "QQQM", "VGT", "XLK", "IYW", "SMH", "SOXX", "XSD",
    "VUG", "IWF", "SCHG",
    "IWM", "IJR", "VB",
    "XLY", "XLC", "XLI", "XLF", "XLE", "XME",
    "IGV", "SKYY", "CLOU", "BOTZ", "ROBO", "ARKK",
]

VENTANA_EMA_MACRO = 30
BANDA_TOLERANCIA_EMA = 0.985
PRESUPUESTO_CORE = 0.75
PRESUPUESTO_SATELITE = 0.25

VENTANA_BETA = 126
BETA_MINIMA_SATELITE = 1.10
VENTANA_R2 = 60
R2_MINIMO = 0.45
MAX_DISTANCIA_EMA_PCT = 0.10
CERCANIA_MAXIMO_PCT = 0.96
DOLLAR_VOLUME_MINIMO = 20_000_000
DIAS_BLACKOUT_BALANCE = 30

STOP_LOSS_INICIAL_PCT = 0.05
UMBRAL_BREAKEVEN_PCT = 0.025
BUFFER_BREAKEVEN_PCT = 0.005
TRAILING_STOP_MAX_PCT = 0.04

TICKERS_BLACKLIST = {
    "SNDK", "TECH", "CNC", "TMUS", "SYY", "INVH", "WELL", "HUM", "SBUX", "EW"
}
ARCHIVO_ESTADO = Path("estado_momentum.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)


# ============================== ESTADO DEL STOP ==============================
def cargar_estado(path=ARCHIVO_ESTADO):
    if not path.exists():
        return {"maximos_desde_entrada": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            estado = json.load(f)
        estado.setdefault("maximos_desde_entrada", {})
        return estado
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("No se pudo leer el estado: %s", exc)
        return {"maximos_desde_entrada": {}}


def guardar_estado(estado, path=ARCHIVO_ESTADO):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(estado, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


# ============================== DATOS ==============================
def obtener_universo_sp500():
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; MomentumScanner/3.0)"}
    try:
        response = requests.get(url, headers=headers, timeout=20)
        response.raise_for_status()
        tabla = pd.read_html(StringIO(response.text), match="Symbol")[0]
        tickers = tabla["Symbol"].astype(str).str.replace(".", "-", regex=False)
        sectores = tabla["GICS Sector"].astype(str)
        return dict(zip(tickers, sectores))
    except Exception as exc:
        raise RuntimeError(f"No se pudo obtener el S&P 500: {exc}") from exc


def extraer_campo(datos, campo):
    if not isinstance(datos.columns, pd.MultiIndex):
        if campo not in datos.columns:
            raise KeyError(f"Falta {campo}")
        return datos[[campo]].copy()
    if campo not in datos.columns.get_level_values(0):
        raise KeyError(f"Falta {campo}")
    df = datos[campo].copy()
    return df.to_frame() if isinstance(df, pd.Series) else df


def obtener_datos_masivos(dias_calendario=500, tickers_extra=None):
    mapa = obtener_universo_sp500()
    extras = tickers_extra or []
    vitales = [FILTRO_MACRO, BENCHMARK_MOMENTUM, REFUGIO_RENTA_FIJA,
               REFUGIO_CASH_LIQUIDEZ, COBERTURA_BAJISTA]
    tickers = list(dict.fromkeys(list(mapa) + ETFS_SATELITE + extras + vitales))
    tickers = [t for t in tickers if "." not in t]

    hoy = dt.date.today()
    datos = yf.download(
        tickers=tickers,
        start=hoy - dt.timedelta(days=dias_calendario),
        end=hoy + dt.timedelta(days=1),
        auto_adjust=True,
        group_by="column",
        multi_level_index=True,
        threads=True,
        progress=True, # Changed from False to True
        repair=True,
        timeout=30,
    )
    if datos is None or datos.empty:
        raise RuntimeError("Yahoo Finance no devolvio datos")

    cierre = extraer_campo(datos, "Close").sort_index()
    maximo = extraer_campo(datos, "High").reindex_like(cierre)
    minimo = extraer_campo(datos, "Low").reindex_like(cierre)
    volumen = extraer_campo(datos, "Volume").reindex_like(cierre)

    validos = cierre.tail(20).dropna(axis=1, thresh=18).columns
    dollar_volume = (cierre[validos] * volumen[validos]).tail(20).median()
    liquidos = set(dollar_volume[dollar_volume >= DOLLAR_VOLUME_MINIMO].index)
    finales = [t for t in cierre.columns if t in liquidos]

    # Los vitales, ETFs satelite y posiciones actuales se conservan si tienen datos.
    for ticker in vitales + ETFS_SATELITE + extras:
        if ticker in cierre.columns and ticker not in finales and cierre[ticker].notna().any():
            finales.append(ticker)

    if FILTRO_MACRO not in finales:
        raise RuntimeError("No hay datos utilizables para SPY")
    return cierre[finales], maximo[finales], minimo[finales], volumen[finales], mapa


# ============================== INDICADORES ==============================
def calcular_momentum_suavizado(precios):
    return (0.60 * precios.pct_change(21, fill_method=None)
            + 0.30 * precios.pct_change(63, fill_method=None)
            + 0.10 * precios.pct_change(126, fill_method=None))


def calcular_r2_log(serie):
    serie = serie.dropna().tail(VENTANA_R2)
    if len(serie) < VENTANA_R2 or (serie <= 0).any():
        return np.nan, np.nan
    x = np.arange(len(serie), dtype=float)
    pendiente, _, r, _, _ = linregress(x, np.log(serie.to_numpy(dtype=float)))
    return float(r ** 2), float(pendiente)


def calcular_beta(precios_activo, precios_spy, ventana=VENTANA_BETA):
    retornos = pd.concat([
        precios_activo.pct_change(fill_method=None).rename("activo"),
        precios_spy.pct_change(fill_method=None).rename("spy"),
    ], axis=1, join="inner").dropna().tail(ventana)
    if len(retornos) < ventana:
        return np.nan
    var_spy = float(retornos["spy"].var(ddof=1))
    if not np.isfinite(var_spy) or var_spy <= 0:
        return np.nan
    return float(retornos["activo"].cov(retornos["spy"]) / var_spy)


def evaluar_regimen_macro(spy):
    s = spy.dropna()
    if len(s) < VENTANA_EMA_MACRO + 2:
        raise ValueError("Historial insuficiente para SPY")
    ema = s.ewm(span=VENTANA_EMA_MACRO, adjust=False).mean()
    p0, p1 = float(s.iloc[-1]), float(s.iloc[-2])
    e0, e1 = float(ema.iloc[-1]), float(ema.iloc[-2])
    risk_off = p0 < BANDA_TOLERANCIA_EMA * e0 or (p0 < e0 and p1 < e1)
    motivo = "RISK-OFF confirmado" if risk_off else "RISK-ON / sin confirmacion bajista"
    return not risk_off, p0, e0, motivo


def pesos_iguales(tickers, presupuesto):
    return {} if not tickers else {t: presupuesto / len(tickers) for t in tickers}

def calcular_atr(cierre, maximo, minimo, ventana=14):
    """Calcula el Average True Range (ATR) de una serie de precios."""
    tr1 = maximo - minimo
    tr2 = (maximo - cierre.shift(1)).abs()
    tr3 = (minimo - cierre.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(window=ventana).mean()


# ============================== EARNINGS ==============================
def balance_inminente(ticker, dias_peligro=30):
    if ticker in set(ETFS_SATELITE) | {FILTRO_MACRO, BENCHMARK_MOMENTUM,
                                      REFUGIO_RENTA_FIJA, REFUGIO_CASH_LIQUIDEZ,
                                      COBERTURA_BAJISTA}:
        return False
    try:
        cal = yf.Ticker(ticker).calendar
        fechas = cal.get("Earnings Date", []) if isinstance(cal, dict) else []
        if not isinstance(fechas, (list, tuple, pd.Series, np.ndarray)):
            fechas = [fechas]
        hoy = dt.date.today()
        return any(0 <= (pd.Timestamp(f).date() - hoy).days <= dias_peligro
                   for f in fechas if pd.notna(f))
    except Exception as exc:
        logger.warning("No se pudo verificar earnings de %s: %s", ticker, exc)
        return False


# ============================== ESCANER ==============================
def diagnosticar_y_escanear_universo(cierre, maximo, minimo, volumen, mapa):
    del minimo, volumen
    risk_on, p_spy, ema_spy, motivo = evaluar_regimen_macro(cierre[FILTRO_MACRO])
    print("\n" + "=" * 95)
    print(f"REGIMEN: {motivo} | SPY: ${p_spy:.2f} | EMA30: ${ema_spy:.2f}")
    print("=" * 95)

    excluidos = {FILTRO_MACRO, BENCHMARK_MOMENTUM, REFUGIO_RENTA_FIJA,
                 REFUGIO_CASH_LIQUIDEZ, COBERTURA_BAJISTA}
    elegibles = [t for t in cierre.columns if t not in excluidos]
    momentum = calcular_momentum_suavizado(cierre[elegibles]).iloc[-1]
    aprobados, r2_map = {}, {}

    for ticker in tqdm(elegibles, desc="Escaneando", unit="ticker"):
        if ticker in TICKERS_BLACKLIST:
            continue
        s, h = cierre[ticker].dropna(), maximo[ticker].dropna()
        if len(s) < 127 or len(h) < 20:
            continue
        p = float(s.iloc[-1])
        ema10 = s.ewm(span=10, adjust=False).mean()
        ema30 = s.ewm(span=VENTANA_EMA_MACRO, adjust=False).mean()
        e10, e30 = float(ema10.iloc[-1]), float(ema30.iloc[-1])
        r2, pend = calcular_r2_log(s)
        mom = float(momentum.get(ticker, np.nan))
        condiciones = [
            p >= BANDA_TOLERANCIA_EMA * e30,
            p / e30 - 1 <= MAX_DISTANCIA_EMA_PCT,
            p > e10, e10 > e30,
            e10 > float(ema10.iloc[-4]), e30 > float(ema30.iloc[-6]),
            p >= CERCANIA_MAXIMO_PCT * float(h.tail(20).max()),
            float(s.pct_change(21, fill_method=None).iloc[-1]) > 0,
            np.isfinite(r2) and r2 >= R2_MINIMO,
            np.isfinite(pend) and pend > 0,
            np.isfinite(mom),
        ]
        if all(condiciones):
            aprobados[ticker], r2_map[ticker] = mom, r2

    if not risk_on:
        objetivo = {COBERTURA_BAJISTA: 0.25, REFUGIO_RENTA_FIJA: 0.50,
                    REFUGIO_CASH_LIQUIDEZ: 0.25}
        print("PROTOCOLO DEFENSIVO: 25% SH / 50% SHY / 25% BIL")
        return risk_on, objetivo

    ranking = sorted(aprobados, key=aprobados.get, reverse=True)

    core, sectores = [], set()
    for ticker in ranking:
        if ticker in ETFS_SATELITE or ticker not in mapa:
            continue
        sector = mapa[ticker]
        if sector in sectores or balance_inminente(ticker, DIAS_BLACKOUT_BALANCE):
            continue
        core.append(ticker)
        sectores.add(sector)
        if len(core) == 3:
            break

    objetivo = pesos_iguales(core, PRESUPUESTO_CORE)
    faltante_core = PRESUPUESTO_CORE - sum(objetivo.values())
    if faltante_core > 1e-12:
        objetivo[REFUGIO_CASH_LIQUIDEZ] = faltante_core

    beta_map, satelites = {}, []
    for ticker in ranking:
        if ticker not in ETFS_SATELITE:
            continue
        beta = calcular_beta(cierre[ticker], cierre[FILTRO_MACRO])
        beta_map[ticker] = beta
        if np.isfinite(beta) and beta >= BETA_MINIMA_SATELITE:
            satelites.append(ticker)

    satelite = satelites[0] if satelites else REFUGIO_CASH_LIQUIDEZ
    objetivo[satelite] = objetivo.get(satelite, 0.0) + PRESUPUESTO_SATELITE

    print("\nCORE:")
    for ticker in core:
        print(f"  {ticker:6s} | {mapa[ticker]:25s} | Mom {aprobados[ticker]:+.2%} | "
              f"R2 {r2_map[ticker]:.2f} | Peso {objetivo[ticker]:.2%}")

    if satelite == REFUGIO_CASH_LIQUIDEZ:
        print(f"SATELITE: BIL | Ningun ETF aprobo tendencia y beta >= {BETA_MINIMA_SATELITE:.2f}")
    else:
        print(f"SATELITE: {satelite} | Mom {aprobados[satelite]:+.2%} | "
              f"R2 {r2_map[satelite]:.2f} | Beta {beta_map[satelite]:.2f} | Peso 25.00%")

    print("\nDIAGNOSTICO DE ETFs QUE SUPERARON TENDENCIA:")
    candidatos = [t for t in ranking if t in ETFS_SATELITE]
    if not candidatos:
        print("  Ningun ETF supero los filtros previos de momentum, R2 y tendencia.")
    for ticker in candidatos:
        beta = beta_map.get(ticker, calcular_beta(cierre[ticker], cierre[FILTRO_MACRO]))
        beta_txt = f"{beta:.2f}" if np.isfinite(beta) else "N/D"
        estado = "APTO" if np.isfinite(beta) and beta >= BETA_MINIMA_SATELITE else "NO APTO"
        print(f"  {ticker:5s} | Mom {aprobados[ticker]:+.2%} | R2 {r2_map[ticker]:.2f} | "
              f"Beta {beta_txt} | {estado}")

    if not np.isclose(sum(objetivo.values()), 1.0):
        raise RuntimeError("Los pesos objetivo no suman 100%")
    return risk_on, objetivo


# ============================== REBALANCEO ==============================
def calcular_instrucciones_operativas(objetivo, actual, entradas, cash, cierre, maximo, minimo, estado):
    max_estado = estado.setdefault("maximos_desde_entrada", {})
    valor = sum(q * float(cierre[t].dropna().iloc[-1]) for t, q in actual.items()
                if t in cierre.columns and not cierre[t].dropna().empty)
    nav = valor + cash
    filas = []

    # 1. Definimos el multiplicador de volatilidad (margen de respiro)
    multiplo_atr = 3.0

    for ticker in list(dict.fromkeys(list(objetivo) + list(actual))):
        if ticker not in cierre.columns or cierre[ticker].dropna().empty:
            logger.error("Sin precio para %s", ticker)
            continue

        p = float(cierre[ticker].dropna().iloc[-1])
        q = int(actual.get(ticker, 0))
        entrada = float(entradas.get(ticker, p))
        peso = float(objetivo.get(ticker, 0.0))
        protegido = ticker in {COBERTURA_BAJISTA, REFUGIO_RENTA_FIJA,
                               REFUGIO_CASH_LIQUIDEZ} or peso == 0
        stop, stop_activo, tipo = None, False, "N/A"

        if not protegido:
            # 2. Calculamos el ATR actual para el activo en cuestión
            # Asume que la función calcular_atr ya está definida en el scope global
            atr_actual = calcular_atr(cierre[ticker], maximo[ticker], minimo[ticker]).iloc[-1]

            if q == 0 or ticker not in entradas:
                stop, tipo = p * (1 - STOP_LOSS_INICIAL_PCT), "INICIAL"
            else:
                max_alc = max(float(max_estado.get(ticker, entrada)),
                              float(maximo[ticker].dropna().iloc[-1]), p, entrada)
                max_estado[ticker] = max_alc

                # Mantenemos las barreras de protección estáticas como red de seguridad
                inicial = entrada * (1 - STOP_LOSS_INICIAL_PCT)
                breakeven = (entrada * (1 + BUFFER_BREAKEVEN_PCT)
                             if max_alc >= entrada * (1 + UMBRAL_BREAKEVEN_PCT) else inicial)

                # 3. Nueva lógica: Trailing Stop dinámico ajustado por volatilidad (ATR)
                trailing = max_alc - (atr_actual * multiplo_atr)

                stop = max(inicial, breakeven, trailing)
                stop_activo = p <= stop

                # Actualizamos la etiqueta para reflejar que es un trailing por ATR
                tipo = "TRAILING ATR" if np.isclose(stop, trailing) and trailing > entrada else (
                    "BREAKEVEN" if np.isclose(stop, breakeven) and breakeven > inicial else "INICIAL")

        target = 0 if stop_activo else int((nav * peso) // p)
        delta = target - q
        if stop_activo:
            orden = f"VENDER ALL ({q}) | STOP ACTIVADO"
        elif delta > 0:
            orden = f"COMPRAR {delta}"
        elif delta < 0:
            orden = f"VENDER ALL ({abs(delta)})" if target == 0 else f"VENDER {abs(delta)}"
        else:
            orden = "MANTENER" if q else "NO OPERAR"

        filas.append({"Ticker": ticker, "P. Compra": f"${entrada:.2f}" if ticker in entradas else "N/A",
                      "P. Actual": f"${p:.2f}", "Acc. Hoy": q, "Acc. Target": target,
                      "ORDEN NETA": orden, "Monto Delta": f"${abs(delta*p):,.2f}",
                      "Peso Target": f"{peso:.1%}",
                      "Stop Dinamico": "N/A" if stop is None else f"${stop:.2f}",
                      "Estado Stop": tipo})

    reporte = pd.DataFrame(filas)
    print("\n" + "=" * 120)
    print(f"MATRIZ DE REBALANCEO | NAV TOTAL: ${nav:,.2f}")
    print(reporte.to_string(index=False))
    print("=" * 120)
    return reporte, estado


if __name__ == "__main__":
    PORTAFOLIO_ACTUAL_CANTIDADES = {
        "VLO": 60,
        "IQV": 71,
        "SKYY": 135

    }

    PRECIOS_ENTRADA = {
        "VLO": 360.11,
        "IQV": 270.87,
        "SKYY": 165.78

    }

    CASH_DISPONIBLE_USD = 84654.33

    estado = cargar_estado()
    p_cierre, p_max, p_min, p_volumen, mapa = obtener_datos_masivos(
        dias_calendario=500,
        tickers_extra=list(PORTAFOLIO_ACTUAL_CANTIDADES),
    )
    _, target = diagnosticar_y_escanear_universo(p_cierre, p_max, p_min, p_volumen, mapa)
    reporte, estado = calcular_instrucciones_operativas(
        target, PORTAFOLIO_ACTUAL_CANTIDADES, PRECIOS_ENTRADA,
        CASH_DISPONIBLE_USD, p_cierre, p_max, p_min, estado
    )
    guardar_estado(estado)
    reporte.to_csv("reporte_rebalanceo.csv", index=False, encoding="utf-8-sig")
