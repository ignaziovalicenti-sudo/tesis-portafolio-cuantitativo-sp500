import datetime
import numpy as np
import pandas as pd
import yfinance as yf
import warnings
warnings.filterwarnings('ignore') # Evita advertencias visuales de Pandas al calcular ATR

# ==============================================================================
# 1. CONFIGURACIÓN DEL PORTAFOLIO Y CONSTANTES SINCRONIZADAS
# ==============================================================================
FILTRO_MACRO = "SPY"             # Semáforo de riesgo del mercado
BENCHMARK_MOMENTUM = "SPMO"      # Para medición de performance histórica
COBERTURA_BAJISTA = "SH"
REFUGIO_RENTA_FIJA = "SHY"
REFUGIO_CASH_LIQUIDEZ = "BIL"

# Estructura del portafolio actual
PORTAFOLIO_ACTUAL = {
    "FILTRO_MACRO": FILTRO_MACRO,
    "CORE": ["VLO", "STT", "IQV"],
    "SATELITE": ["SKYY"],
}

# Precios y fechas de entrada
POSICIONES_INFO = {
    "VLO": {"precio_entrada": 360.11, "fecha_entrada": "2026-08-31"},
    "STT": {"precio_entrada": 184.31, "fecha_entrada": "2026-08-31"},
    "IQV": {"precio_entrada": 270.87, "fecha_entrada": "2026-08-31"},
    "SKYY": {"precio_entrada": 165.78, "fecha_entrada": "2026-08-31"},
}

# Parámetros Operativos
UMBRAL_BREAKEVEN_PCT = 0.025      # Cuándo asegurar el capital (2.5% de subida)
VENTANA_EMA_MACRO = 30
BANDA_TOLERANCIA_EMA = 0.985
DIAS_BLACKOUT_BALANCE = 30
TICKERS_BLACKLIST = ["SNDK", "TECH", "CNC"]

# Parámetros Cuantitativos de Salida (100% ATR para el Trailing)
MULTIPLICADOR_ATR = 3.0           # Margen de respiración basado en volatilidad
VENTANA_ATR = 14

# ==============================================================================
# 2. FUNCIONES TÉCNICAS Y EVENTOS BINARIOS
# ==============================================================================
def obtener_datos_ohlc(tickers, dias_calendario=500):
    hoy = datetime.date.today()
    inicio = hoy - datetime.timedelta(days=dias_calendario)
    fin = hoy + datetime.timedelta(days=1)

    tickers_limpios = [t for t in tickers if t not in TICKERS_BLACKLIST]

    datos = yf.download(tickers_limpios, start=inicio, end=fin, progress=False, auto_adjust=True)

    if len(tickers_limpios) == 1:
        cierre = datos[["Close"]].rename(columns={"Close": tickers_limpios[0]})
        maximo = datos[["High"]].rename(columns={"High": tickers_limpios[0]})
        minimo = datos[["Low"]].rename(columns={"Low": tickers_limpios[0]})
    else:
        cierre = datos["Close"].dropna(thresh=int(len(datos["Close"]) * 0.75), axis=1)
        maximo = datos["High"][cierre.columns]
        minimo = datos["Low"][cierre.columns]

    return cierre, maximo, minimo

def balance_inminente(ticker_str, dias_peligro=30):
    if ticker_str in [FILTRO_MACRO, BENCHMARK_MOMENTUM, COBERTURA_BAJISTA, REFUGIO_RENTA_FIJA, REFUGIO_CASH_LIQUIDEZ]:
        return False, None
    try:
        tkr = yf.Ticker(ticker_str)
        cal = tkr.calendar
        if isinstance(cal, dict) and 'Earnings Date' in cal:
            fechas = cal['Earnings Date']
            if len(fechas) > 0 and isinstance(fechas[0], datetime.date):
                dias_faltantes = (fechas[0] - datetime.date.today()).days
                if 0 <= dias_faltantes <= dias_peligro:
                    return True, dias_faltantes
    except Exception:
        pass
    return False, None

def calcular_atr(cierre, maximo, minimo, ventana=VENTANA_ATR):
    tr1 = maximo - minimo
    tr2 = (maximo - cierre.shift(1)).abs()
    tr3 = (minimo - cierre.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(ventana).mean()

def evaluar_regimen_macro(precios_spy):
    s_limpia = precios_spy.dropna()
    ema_30 = s_limpia.ewm(span=VENTANA_EMA_MACRO, adjust=False).mean()
    p_hoy, ema_hoy = float(s_limpia.iloc[-1]), float(ema_30.iloc[-1])
    p_ayer, ema_ayer = float(s_limpia.iloc[-2]), float(ema_30.iloc[-2])

    quiebre_profundo = p_hoy < (BANDA_TOLERANCIA_EMA * ema_hoy)
    dos_cierres_debajo = (p_hoy < ema_hoy) and (p_ayer < ema_ayer)

    if quiebre_profundo or dos_cierres_debajo:
        return False, "🔴 RISK-OFF (Confirmado quiebre o 2 cierres < EMA30)"
    elif p_hoy < ema_hoy:
        return True, "⚠️ ALERTA: SPY bajo EMA30 (Dentro de tolerancia)"
    return True, "🟢 RISK-ON (Estructura Alcista SPY > EMA30)"

# ==============================================================================
# 3. ESCÁNER DE SANIDAD Y MATRIZ OPERATIVA
# ==============================================================================
def evaluar_salud_y_trailing_stops(portafolio, posiciones_info):
    activos_cartera = list(set(portafolio["CORE"] + portafolio.get("SATELITE", [])))
    activos_totales = list(set([portafolio["FILTRO_MACRO"]] + activos_cartera))

    cierre, maximo, minimo = obtener_datos_ohlc(activos_totales, dias_calendario=365)
    fecha_hoy_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

    sp_risk_on, sp_motivo = evaluar_regimen_macro(cierre[portafolio["FILTRO_MACRO"]])

    print("\n" + "=" * 125)
    print(f" 🛡️  MONITOREO ADAPTATIVO DE SANIDAD Y STOPS (Régimen ATR Libre) | {fecha_hoy_str}")
    print(f" RÉGIMEN MACRO (SPY): {sp_motivo}")
    print("=" * 125)

    reporte_stops = []
    acciones_a_liquidar = []

    for ticker in activos_cartera:
        if ticker not in cierre.columns:
            continue

        serie_cierre = cierre[ticker].dropna()
        serie_max = maximo[ticker].dropna()
        serie_min = minimo[ticker].dropna()

        if len(serie_cierre) < VENTANA_EMA_MACRO:
            continue

        p_cierre_hoy = float(serie_cierre.iloc[-1])
        ema30_hoy = float(serie_cierre.ewm(span=VENTANA_EMA_MACRO, adjust=False).mean().iloc[-1])
        ema10_hoy = float(serie_cierre.ewm(span=10, adjust=False).mean().iloc[-1])

        atr_serie = calcular_atr(serie_cierre, serie_max, serie_min, VENTANA_ATR)
        atr_actual = float(atr_serie.iloc[-1])

        info = posiciones_info.get(ticker, {"precio_entrada": p_cierre_hoy, "fecha_entrada": fecha_hoy_str[:10]})
        p_entrada = info["precio_entrada"]
        fecha_ent = info["fecha_entrada"]

        hay_balance, dias_balance = balance_inminente(ticker, DIAS_BLACKOUT_BALANCE)
        alerta_balance = f"🚨 {dias_balance}d" if hay_balance else "OK"

        try:
            fecha_datetime = pd.to_datetime(fecha_ent)
            serie_max_desde_fecha = serie_max.loc[fecha_datetime:]
            maximo_desde_compra = float(serie_max_desde_fecha.max()) if not serie_max_desde_fecha.empty else float(serie_max.iloc[-15:].max())
        except Exception:
            maximo_desde_compra = float(serie_max.iloc[-15:].max())

        ret_pct = ((p_cierre_hoy - p_entrada) / p_entrada) * 100.0

        activo_breakeven = maximo_desde_compra >= (p_entrada * (1.0 + UMBRAL_BREAKEVEN_PCT))

        # El Trailing Stop se calcula 100% en función de la volatilidad actual
        stop_trailing_atr = maximo_desde_compra - (MULTIPLICADOR_ATR * atr_actual)

        if activo_breakeven:
            stop_breakeven = p_entrada * 1.005 # Asegurar comisiones
            stop_calculado = max(stop_breakeven, stop_trailing_atr)

            if np.isclose(stop_calculado, stop_trailing_atr) or stop_trailing_atr > stop_breakeven:
                estado_stop = "🛡️ TRAILING ATR"
            else:
                estado_stop = "🛡️ BREAKEVEN"
        else:
            # ==============================================================================
            # MODIFICACIÓN APLICADA: Mande directamente el ATR sin floor fijo porcentual
            # ==============================================================================
            stop_calculado = stop_trailing_atr
            estado_stop = "🛡️ DINÁMICO ATR (3x)"

        distancia_pct = ((stop_calculado - p_cierre_hoy) / p_cierre_hoy) * 100.0

        quiebre_profundo = p_cierre_hoy < (BANDA_TOLERANCIA_EMA * ema30_hoy)

        if p_cierre_hoy < stop_calculado:
            accion = "🛑 EJECUTAR STOP-LOSS"
        elif hay_balance and dias_balance <= 7:
             accion = "⚠️ RIESGO BALANCE INMINENTE"
        elif quiebre_profundo:
            accion = "🔴 QUIEBRE PROFUNDO EMA30"
        elif p_cierre_hoy < ema30_hoy:
            accion = "⚠️ ALERTA TENDENCIA (EMA30)"
        elif p_cierre_hoy < ema10_hoy:
             accion = "🟡 PÉRDIDA IMPULSO CORTO (EMA10)"
        else:
            accion = "🟢 MANTENER"

        reporte_stops.append({
            "Ticker": ticker,
            "P. Entrada": f"${p_entrada:.2f}",
            "P. Actual": f"${p_cierre_hoy:.2f}",
            "P/L %": f"{ret_pct:+.2f}%",
            "Stop Nivel": f"${stop_calculado:.2f}",
            "Dist. al Stop": f"{distancia_pct:+.2f}%",
            "Modo Stop": estado_stop,
            "Balance": alerta_balance,
            "Acción Hoy": accion,
        })

        if accion in ["🛑 EJECUTAR STOP-LOSS", "⚠️ RIESGO BALANCE INMINENTE", "🔴 QUIEBRE PROFUNDO EMA30"]:
            acciones_a_liquidar.append((ticker, accion))

    df_reporte = pd.DataFrame(reporte_stops)
    print(df_reporte.to_string(index=False))
    print("=" * 125)

    return df_reporte, not sp_risk_on, acciones_a_liquidar

# ==============================================================================
# 4. EJECUCIÓN PRINCIPAL AL CIERRE DEL MERCADO
# ==============================================================================
if __name__ == "__main__":
    df_reporte_final, risk_off_confirmado, acciones_a_liquidar = evaluar_salud_y_trailing_stops(PORTAFOLIO_ACTUAL, POSICIONES_INFO)

    print("\n📋 INSTRUCCIONES DE EJECUCIÓN REQUERIDAS HOY:")

    if risk_off_confirmado:
        print("🚨 ACTIVACIÓN PROTOCOLO DEFENSIVO MACRO:")
        satelite_tickers = ", ".join(PORTAFOLIO_ACTUAL['SATELITE'])
        print(f" 1. Vender Satélite ({satelite_tickers}) -> Asignar 25% NAV a ETF Inverso {COBERTURA_BAJISTA} (SH).")
        print(f" 2. Vender Módulo Core -> Asignar 50% NAV a Renta Fija {REFUGIO_RENTA_FIJA} (SHY) y 25% NAV a Liquidez {REFUGIO_CASH_LIQUIDEZ} (BIL).")
    elif acciones_a_liquidar:
        print("⚠️ REBALANCEO PARCIAL REQUERIDO AL CIERRE:")
        for t, motivo in acciones_a_liquidar:
            print(f" -> VENDER POSICIÓN EN {t} | Motivo: {motivo}")
        print(" -> ACCIÓN: Si se ejecuta la venta, utilizar el Escáner de Compras para buscar reemplazo.")
    else:
        print("✅ SIN ACCIONES DE LIQUIDACIÓN HOY. Mantener órdenes de Trailing Stop actualizadas en la plataforma.")

    print("=" * 125 + "\n")
