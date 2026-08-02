import datetime
import pandas as pd
import yfinance as yf

# ==============================================================================
# 1. PARÁMETROS Y DESCARGA DE DATOS EN TIEMPO REAL
# ==============================================================================
BENCHMARK = "SPY"

# Opcional: Indicar el estado previo del portafolio ("RISK_ON" o "RISK_OFF")
# Esto permite saber si el gatillo requiere ejecutar un rebalanceo o solo mantener.
REGIMEN_ACTUAL = "RISK_OFF"  

print(f"🔄 Consultando datos en tiempo real de {BENCHMARK} desde Yahoo Finance...")

spy = yf.Ticker(BENCHMARK)
df = spy.history(period="1y", auto_adjust=False)
df.index = df.index.tz_localize(None)

precios = df["Close"].dropna()
ema20 = precios.ewm(span=20, adjust=False).mean()

# ==============================================================================
# 2. CAPTURA DE LOS ÚLTIMOS CIERRES (T-1 y T-0)
# ==============================================================================
p_1, ema_1 = float(precios.iloc[-1]), float(ema20.iloc[-1])  # Cierre más reciente (T-0)
p_2, ema_2 = float(precios.iloc[-2]), float(ema20.iloc[-2])  # Cierre previo (T-1)

ultima_fecha = precios.index[-1].strftime('%Y-%m-%d')

# ==============================================================================
# 3. REGLAS DE GATILLO (CAPÍTULO 2)
# ==============================================================================

# 1. Gatillo Risk-Off: 1 cierre <= -0.5% por debajo O 2 cierres consecutivos < EMA20
gatillo_risk_off = (p_1 < 0.995 * ema_1) or ((p_2 < ema_2) and (p_1 < ema_1))

# 2. Gatillo Risk-On: 2 cierres consecutivos > EMA20
gatillo_risk_on = (p_2 > ema_2) and (p_1 > ema_1)

# ==============================================================================
# 4. DESPLIEGUE DE RESULTADOS Y DIAGNÓSTICO
# ==============================================================================
print("\n" + "=" * 75)
print(f"📅 FECHA DE EVALUACIÓN: {ultima_fecha}")
print(f"📊 PRECIO CIERRE SPY (T-0): ${p_1:.2f} | EMA20: ${ema_1:.2f} (Diferencia: {((p_1/ema_1)-1)*100:+.2f}%)")
print(f"📊 PRECIO CIERRE SPY (T-1): ${p_2:.2f} | EMA20: ${ema_2:.2f}")
print("=" * 75)

if gatillo_risk_off:
    print("🚨 ALERTA: GATILLO RISK-OFF ACTIVADO")
    print("   └─ Se cumple la condición de quiebre bajista.")
    print("   └─ ACCIÓN: Migrar al Protocolo Defensivo Híbrido ($PSQ / $SHY / $BIL).")

elif gatillo_risk_on:
    print("🟢 ALERTA: GATILLO RISK-ON ACTIVADO")
    print("   └─ Consolidación de 2 cierres consecutivos por encima de EMA20.")
    print("   └─ ACCIÓN: Rotar a la Estructura Alcista 75/25 (Core / Satélite).")

else:
    print("✅ SIN CAMBIO DE GATILLO")
    print("   └─ El mercado no cumple las condiciones de confirmación para un giro de régimen.")
    print(f"   └─ ESTADO DE CARTERA: Mantener posición actual ({REGIMEN_ACTUAL}).")

print("=" * 75)
