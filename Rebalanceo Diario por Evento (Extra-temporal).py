import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

# ==============================================================================
# 1. CONFIGURACIÓN DEL PORTAFOLIO ACTUAL (ESTADO DEL DÍA ANTERIOR)
# ==============================================================================
# Define aquí los activos que integran actualmente tu cartera
PORTAFOLIO_ACTUAL = {
    "REGIMEN_ACTUAL": "RISK_ON",  # Opciones: "RISK_ON", "RISK_OFF"
    "BENCHMARK": "SPY",
    "CORE": ["SHY", "XLF", "EFA"],  # Activos en el Módulo Core (75% NAV)
    "SATELITE": "PSQ",                # Activo en el Módulo Satélite (25% NAV)
    # Historial de cierres consecutivos por debajo de EMA20 para control de persistencia
    "DIAS_BAJO_EMA": {
        "SPY": 0,
        "SHY": 0,
        "XLF": 0,
        "EFA": 0,
        "PSQ": 0
    }
}

# Instrumentos tácticos de cobertura
DEFENSIVOS = {
    "COBERTURA_CORTA": "PSQ",  # Short QQQ
    "RENTA_FIJA": "SHY",       # 1-3 Year Treasury
    "CASH_LIQUIDEZ": "BIL"     # 1-3 Month T-Bill
}

# ==============================================================================
# 2. FUNCIONES DE CÁLCULO TÉCNICO Y EVALUACIÓN DE REGLAS
# ==============================================================================
def obtener_datos_cierre(tickers, dias=50):
    """Descarga los precios ajustados de cierre para el universo relevante."""
    datos = yf.download(tickers, period=f"{dias}d", progress=False)["Close"]
    return datos

def calcular_ema(serie_precios, ventana=20):
    """Calcula la Media Móvil Exponencial de 20 días."""
    return serie_precios.ewm(span=ventana, adjust=False).mean()

def evaluar_eventos_diarios(portafolio):
    """
    Evalúa las reglas de evento extra-temporal diario:
    1. Filtro SPY (Régimen Global Risk-On / Risk-Off)
    2. Filtro Individual (Ruptura de EMA20 en activos Core/Satélite)
    """
    # Recopilar todos los tickers a monitorear
    tickers = list(set([portafolio["BENCHMARK"]] + portafolio["CORE"] + [portafolio["SATELITE"]]))
    precios = obtener_datos_cierre(tickers)

    # DataFrame para almacenar el diagnóstico
    diagnostico = []

    print(f"\n=== EVALUACIÓN DIARIA DE EVENTOS AL CIERRE: {datetime.now().strftime('%Y-%m-%d')} ===")

    # --------------------------------------------------------------------------
    # A. EVALUACIÓN DEL RÉGIMEN GENERAL (SPY)
    # --------------------------------------------------------------------------
    spy_precio = precios[portafolio["BENCHMARK"]].iloc[-1]
    spy_ema20 = calcular_ema(precios[portafolio["BENCHMARK"]]).iloc[-1]
    spy_precio_prev = precios[portafolio["BENCHMARK"]].iloc[-2]
    spy_ema20_prev = calcular_ema(precios[portafolio["BENCHMARK"]]).iloc[-2]

    # Condiciones del SPY
    quiebre_violento_spy = spy_precio < (0.995 * spy_ema20) # Caída > 0.5% abajo de EMA20
    persistencia_spy = (spy_precio < spy_ema20) and (spy_precio_prev < spy_ema20_prev)

    evento_risk_off = False

    if quiebre_violento_spy or persistencia_spy:
        evento_risk_off = True
        motivo = "Quiebre Violento (< -0.5%)" if quiebre_violento_spy else "Persistencia (2 cierres < EMA20)"
        print(f"\n[ALERTA MÁXIMA] CAMBIO DE RÉGIMEN A RISK-OFF DETECTADO EN SPY.")
        print(f"-> Motivo: {motivo}")
        print(f"-> SPY Cierre: ${spy_precio:.2f} vs EMA20: ${spy_ema20:.2f}")
    else:
        print(f"\n[OK] Régimen de Mercado: RISK-ON (SPY ${spy_precio:.2f} > EMA20 ${spy_ema20:.2f})")

    # --------------------------------------------------------------------------
    # B. EVALUACIÓN DE ACTIVOS INDIVIDUALES (Si seguimos en Risk-On)
    # --------------------------------------------------------------------------
    acciones_a_liquidar = []

    if not evento_risk_off:
        activos_cartera = portafolio["CORE"] + [portafolio["SATELITE"]]

        for ticker in activos_cartera:
            p_actual = precios[ticker].iloc[-1]
            ema_actual = calcular_ema(precios[ticker]).iloc[-1]
            p_prev = precios[ticker].iloc[-2]
            ema_prev = calcular_ema(precios[ticker]).iloc[-2]

            # Condición 1: Cierre violento individual (-1.0% abajo de EMA20)
            quiebre_violento_ind = p_actual < (0.99 * ema_actual)

            # Condición 2: Persistencia (2 cierres bajo EMA20)
            persistencia_ind = (p_actual < ema_actual) and (p_prev < ema_prev)

            if quiebre_violento_ind or persistencia_ind:
                acciones_a_liquidar.append(ticker)
                causa = "Cierre Violento (< -1.0%)" if quiebre_violento_ind else "Persistencia (2 cierres < EMA20)"
                print(f"[ALERTA INDIVIDUAL] Venta requerida en {ticker}: {causa}")
                print(f"   Precio: ${p_actual:.2f} | EMA20: ${ema_actual:.2f}")

    # --------------------------------------------------------------------------
    # C. EMISIÓN DE ÓRDENES Y REBALANCEO DE EMERGENCIA
    # --------------------------------------------------------------------------
    print("\n--- ORDENES DE EJECUCIÓN REQUERIDAS ---")

    if evento_risk_off:
        print(">> EJECUTAR PROTOCOLO DEFENSIVO HÍBRIDO <<")
        print(f"1. Vender Módulo Satélite ({portafolio['SATELITE']}) -> Rotar 25% NAV a {DEFENSIVOS['COBERTURA_CORTA']} (PSQ)")

        # Evaluar resiliencia en el Core
        resilientes = []
        for ticker in portafolio["CORE"]:
            p = precios[ticker].iloc[-1]
            ema = calcular_ema(precios[ticker]).iloc[-1]
            if p > ema:
                resilientes.append(ticker)

        if len(resilientes) > 0:
            print(f"2. Módulo Core Resiliente ({len(resilientes)} activos con P > EMA20): Mantener {resilientes} (hasta 25% NAV total).")
            print(f"3. Rotar 50% sobrante del Core a Renta Fija: {DEFENSIVOS['RENTA_FIJA']} (SHY)")
        else:
            print(f"2. PÁNICOS SISTÉMICO (0 activos Core resilientes): Rotar 75% NAV del Core a Liquidez {DEFENSIVOS['CASH_LIQUIDEZ']} (BIL)")

    elif len(acciones_a_liquidar) > 0:
        print(f">> REBALANCEO PARCIAL POR EVENTO INDIVIDUAL <<")
        for act in acciones_a_liquidar:
            print(f"-> VENDER {act} inmediatamente al cierre.")
            print(f"-> ACCIÓN: Correr script quincenal para seleccionar sustituto o liquidar temporalmente a {DEFENSIVOS['CASH_LIQUIDEZ']} (BIL).")
    else:
        print(">> NO SE REQUIEREN ACCIONES EXTRA-TEMPORALES HOY. MANTENER PORTAFOLIO. <<")

# ==============================================================================
# 3. EJECUCIÓN
# ==============================================================================
if __name__ == "__main__":
    evaluar_eventos_diarios(PORTAFOLIO_ACTUAL)
