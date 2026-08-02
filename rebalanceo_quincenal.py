import datetime
import pandas as pd
import yfinance as yf
import numpy as np
import requests

# ==============================================================================
# 1. PARÁMETROS Y DEFINICIÓN DE UNIVERSOS DE INVERSIÓN (TESIS OFICIAL)
# ==============================================================================
BENCHMARK = "SPY"
REFUGIO_RENTA_FIJA = "SHY"    # Treasuries 1-3 Años (Preservación Táctica - 50% en Risk-Off)
REFUGIO_CASH_LIQUIDEZ = "BIL" # Treasuries 1-3 Meses / Cash (Preservación Absoluta / Pánico)
COBERTURA_BAJISTA = "PSQ"     # ProShares Short QQQ (-1x Inverso para Alfa Bajista)

# Universo Sectorial / Factores Core Admisibles (75% NAV)
UNIVERSO_CORE_SECTORIAL = [
    "XLF", "XLE", "XLC", "XLI", "XLP", "XLV", "XLU", "EFA"
]

# Universo Satélite Agresivo / Alto Beta (25% NAV en Risk-On)
UNIVERSO_SATELITE_ALTO_BETA = [
    "XLK", "XLY", "SOXX"
]

FECHA_CORTE_SIMULACION = "2026-07-30"  # Fecha de prueba
NAV_ACTUAL = 99040.40                  # NAV simulador

def obtener_tickers_sp500():
    """Obtiene la lista actualizada de los componentes individuales del S&P 500."""
    print("🔍 Cargando componentes del S&P 500...")
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        tabla = pd.read_html(response.text)[0]
        tickers = tabla['Symbol'].str.replace('.', '-', regex=False).tolist()
        print(f"✅ Se cargaron {len(tickers)} componentes.")
        return tickers
    except Exception as e:
        print(f"⚠️ Error al cargar tickers del S&P 500: {e}. Se operará con universo sectorial y táctico.")
        return []

# ==============================================================================
# 2. DESCARGA DE DATOS HISTÓRICOS Y CORTE
# ==============================================================================
def obtener_datos_corte_historico(fecha_corte_str, dias_atras=365):
    fecha_corte = datetime.datetime.strptime(fecha_corte_str, "%Y-%m-%d").date()
    inicio = fecha_corte - datetime.timedelta(days=dias_atras)
    fin_download = fecha_corte + datetime.timedelta(days=2)

    tickers_sp500 = obtener_tickers_sp500()
    todos_los_tickers = list(set(
        tickers_sp500 +
        UNIVERSO_CORE_SECTORIAL +
        UNIVERSO_SATELITE_ALTO_BETA +
        [BENCHMARK, REFUGIO_RENTA_FIJA, REFUGIO_CASH_LIQUIDEZ, COBERTURA_BAJISTA]
    ))

    print(f"\n🔄 Descargando datos de mercado ({inicio} al {fecha_corte})...")
    datos_raw = yf.download(
        todos_los_tickers, start=inicio, end=fin_download, auto_adjust=False, progress=True
    )

    if "Close" in datos_raw:
        precios = datos_raw["Close"]
    else:
        precios = datos_raw

    precios_filtrados = precios.loc[:pd.Timestamp(fecha_corte)].dropna(how="all", axis=1)
    return precios_filtrados

# ==============================================================================
# 3. MÉTRICAS CUANTITATIVAS (EMA20, MOMENTUM, BETA Y EVALUACIÓN DE GATILLOS)
# ==============================================================================
def verificar_tendencia_ema20_robusta(precios_ticker):
    """Filtro Técnico Individual: Comprueba si P > EMA20 para activos individuales."""
    s_limpia = precios_ticker.dropna()
    if len(s_limpia) < 20:
        return False, 0.0, 0.0

    ema_20 = s_limpia.ewm(span=20, adjust=False).mean()
    precio_actual = float(s_limpia.iloc[-1])
    ema_actual = float(ema_20.iloc[-1])

    es_valido = not np.isnan(precio_actual) and not np.isnan(ema_actual)
    es_alcista = es_valido and (precio_actual > ema_actual)

    return es_alcista, precio_actual, ema_actual

def evaluar_regimen_benchmark_spy(precios_spy):
    """
    Evalúa el régimen del Benchmark ($SPY) aplicando las dos cláusulas de activación Risk-Off:
    1. Filtro de Amplitud del -0.5%: 1 cierre con P_SPY < 0.995 * EMA20 (Quiebre Violento)
    2. Persistencia: 2 cierres diarios consecutivos por debajo de la EMA20
    """
    s_limpia = precios_spy.dropna()
    if len(s_limpia) < 20:
        return False, 0.0, 0.0, "Datos insuficientes"

    ema_20 = s_limpia.ewm(span=20, adjust=False).mean()
    
    p_hoy = float(s_limpia.iloc[-1])
    ema_hoy = float(ema_20.iloc[-1])
    
    p_ayer = float(s_limpia.iloc[-2])
    ema_ayer = float(ema_20.iloc[-2])

    umbral_amplitud = 0.995 * ema_hoy  # P_SPY < 0.995 * EMA20 (-0.5%)

    quiebre_amplitud = p_hoy < umbral_amplitud
    dos_cierres_debajo = (p_hoy < ema_hoy) and (p_ayer < ema_ayer)

    if quiebre_amplitud:
        es_risk_on = False
        motivo = f"🔴 RISK-OFF (Gatillo Violento: Cierre con filtro -0.5% por debajo de EMA20 [${p_hoy:.2f} < ${umbral_amplitud:.2f}])"
    elif dos_cierres_debajo:
        es_risk_on = False
        motivo = f"🔴 RISK-OFF (Gatillo Persistencia: 2 cierres consecutivos por debajo de EMA20 [Ayer: ${p_ayer:.2f}, Hoy: ${p_hoy:.2f}])"
    else:
        es_risk_on = True
        motivo = f"🟢 RISK-ON (Estructura Alcista [${p_hoy:.2f} > EMA20 ${ema_hoy:.2f}])"

    return es_risk_on, p_hoy, ema_hoy, motivo

def calcular_momentum_agresivo(precios_df):
    """Fórmula: 70% Retorno 1 Mes (21d) + 30% Retorno 3 Meses (63d)."""
    r_1m = precios_df.pct_change(21)
    r_3m = precios_df.pct_change(63)
    score = (0.70 * r_1m) + (0.30 * r_3m)
    return score.iloc[-1]

def calcular_betas_masivos(precios_df, benchmark_ticker="SPY", dias=252):
    """Calcula el Coeficiente Beta de 1 año respecto al SPY."""
    retornos = precios_df.pct_change().dropna().tail(dias)
    if benchmark_ticker not in retornos.columns:
        return pd.Series(1.0, index=precios_df.columns)

    covarianzas = retornos.cov()[benchmark_ticker]
    varianza_bm = retornos[benchmark_ticker].var()
    if varianza_bm == 0:
        return pd.Series(1.0, index=precios_df.columns)

    return covarianzas / varianza_bm

# ==============================================================================
# 4. ESCÁNER TÁCTICO CON PROTOCOLO DEFENSIVO Y COBERTURA (CAPÍTULO 2 - EMA20)
# ==============================================================================
def diagnosticar_y_escanear_tactico(datos):
    sp_risk_on, sp_precio, sp_ema, sp_motivo = evaluar_regimen_benchmark_spy(datos[BENCHMARK])
    fecha_evaluada = datos.index[-1].strftime("%Y-%m-%d")

    print("\n" + "=" * 80)
    print(f"   ESCÁNER DE SELECCIÓN TÁCTICO CORE/SATÉLITE (EMA20) | FECHA CORTE: {fecha_evaluada}")
    print("=" * 80)
    print(f"Estado Benchmark ($SPY) -> Cierre: ${sp_precio:.2f} | EMA20: ${sp_ema:.2f}")
    print(f"Diagnóstico de Régimen -> {sp_motivo}")
    print("-" * 80)

    portafolio_objetivo = {}

    # Excluir activos de control e instrumentos tácticos del cálculo general
    activos_excluidos = [BENCHMARK, REFUGIO_RENTA_FIJA, REFUGIO_CASH_LIQUIDEZ, COBERTURA_BAJISTA]
    tickers_evaluables = [col for col in datos.columns if col not in activos_excluidos]

    scores_momentum = calcular_momentum_agresivo(datos[tickers_evaluables])
    betas = calcular_betas_masivos(datos, benchmark_ticker=BENCHMARK)

    # --------------------------------------------------------------------------
    # ESCENARIO A: MERCADO ALCISTA ($SPY > EMA20) - RISK-ON
    # --------------------------------------------------------------------------
    if sp_risk_on:
        print("\n📈 EJECUTANDO MATRIZ RISK-ON (Estrategia de Expansión):")

        # --- Módulo Core (75% NAV -> Top 3 Momentum con P > EMA20) ---
        activos_core_alcistas = {}
        universo_core = list(set(UNIVERSO_CORE_SECTORIAL + tickers_evaluables))
        for t in universo_core:
            if t in datos.columns:
                es_alcista, _, _ = verificar_tendencia_ema20_robusta(datos[t])
                if es_alcista and not np.isnan(scores_momentum.get(t, np.nan)):
                    activos_core_alcistas[t] = scores_momentum[t]

        ranking_core = sorted(activos_core_alcistas.items(), key=lambda x: x[1], reverse=True)
        top_3_core = [t for t, _ in ranking_core[:3]]

        print("\n🔹 MÓDULO CORE SELECCIONADO (75% NAV - Top 3 Momentum):")
        for t in top_3_core:
            portafolio_objetivo[t] = 0.25
            print(f" -> {t:6s} | Score Momentum: {scores_momentum[t]:7.4f} | Beta: {betas.get(t, 1.0):.2f} | Peso: 25.0%")

        if len(top_3_core) < 3:
            faltantes = 3 - len(top_3_core)
            peso_refugio = faltantes * 0.25
            portafolio_objetivo[REFUGIO_CASH_LIQUIDEZ] = portafolio_objetivo.get(REFUGIO_CASH_LIQUIDEZ, 0.0) + peso_refugio
            print(f" -> {REFUGIO_CASH_LIQUIDEZ:6s} (Liquidez/Cash por falta de activos Core) | Peso: {peso_refugio*100:.1f}%")

        # --- Módulo Satélite (25% NAV -> Top 1 Alto Beta >= 1.20 con P > EMA20) ---
        candidatos_satelite = {}
        universo_satelite = list(set(UNIVERSO_SATELITE_ALTO_BETA + tickers_evaluables))
        for t in universo_satelite:
            if t in datos.columns:
                es_alcista, _, _ = verificar_tendencia_ema20_robusta(datos[t])
                beta_t = betas.get(t, 1.0)
                if es_alcista and beta_t >= 1.20 and not np.isnan(scores_momentum.get(t, np.nan)):
                    candidatos_satelite[t] = scores_momentum[t]

        print("\n🚀 MÓDULO SATÉLITE SELECCIONADO (25% NAV - Top 1 Cohete Alto Beta):")
        if candidatos_satelite:
            top_1_sat = max(candidatos_satelite, key=candidatos_satelite.get)
            portafolio_objetivo[top_1_sat] = 0.25
            print(f" -> {top_1_sat:6s} | Score Momentum: {candidatos_satelite[top_1_sat]:7.4f} | Beta: {betas.get(top_1_sat, 1.0):.2f} | Peso: 25.0%")
        else:
            portafolio_objetivo[REFUGIO_CASH_LIQUIDEZ] = portafolio_objetivo.get(REFUGIO_CASH_LIQUIDEZ, 0.0) + 0.25
            print(f" -> {REFUGIO_CASH_LIQUIDEZ:6s} (Liquidez/Cash por falta de activos Satélite) | Peso: 25.0%")

    # --------------------------------------------------------------------------
    # ESCENARIO B: MERCADO BAJISTA ($SPY < EMA20 / GATILLOS) - PROTOCOLO DEFENSIVO HÍBRIDO
    # --------------------------------------------------------------------------
    else:
        print("\n🛡️ EJECUTANDO PROTOCOLO DEFENSIVO HÍBRIDO (Estrategia Bajista - EMA20):")

        # --- 1. Módulo Satélite (25% NAV) -> Rotación a Cobertura Activa ($PSQ) ---
        portafolio_objetivo[COBERTURA_BAJISTA] = 0.25
        print(f"\n⚡ MÓDULO SATÉLITE (25% NAV - Cobertura Activa Inversa):")
        print(f" -> {COBERTURA_BAJISTA:6s} | Motor de Alfa Bajista (Inverse -1x QQQ) | Peso: 25.0%")

        # --- 2. Módulo Core (75% NAV) -> Refugio Sectorial Resiliente vs Renta Fija / Cash ---
        sectores_resilientes = {}
        for t in UNIVERSO_CORE_SECTORIAL:
            if t in datos.columns:
                es_alcista, _, _ = verificar_tendencia_ema20_robusta(datos[t])
                if es_alcista and not np.isnan(scores_momentum.get(t, np.nan)):
                    sectores_resilientes[t] = scores_momentum[t]

        print(f"\n🛡️ MÓDULO CORE (75% NAV - Refugio Sectorial / Preservación):")

        # REGLA TESIS: Si existen sectores/activos resilientes con P > EMA20:
        if sectores_resilientes:
            ranking_resiliente = sorted(sectores_resilientes.items(), key=lambda x: x[1], reverse=True)
            top_2_resilientes = [t for t, _ in ranking_resiliente[:2]]
            peso_por_sector = 0.25 / len(top_2_resilientes)

            for t in top_2_resilientes:
                portafolio_objetivo[t] = peso_por_sector
                print(f" -> {t:6s} | Sector Resiliente (P > EMA20) | Score: {sectores_resilientes[t]:7.4f} | Peso: {peso_por_sector*100:.1f}%")

            # Asignación del 50% a Renta Fija Refugio ($SHY - Treasuries 1-3 Años)
            peso_rf_shy = 0.50
            portafolio_objetivo[REFUGIO_RENTA_FIJA] = peso_rf_shy
            print(f" -> {REFUGIO_RENTA_FIJA:6s} | Refugio Renta Fija (Treasuries 1-3 años) | Peso: {peso_rf_shy*100:.1f}%")

        # REGLA TESIS DE PRESERVACIÓN ABSOLUTA: Si ningún activo supera la EMA20 (Pánico Sistémico):
        else:
            peso_liquidez_bil = 0.75
            portafolio_objetivo[REFUGIO_CASH_LIQUIDEZ] = peso_liquidez_bil
            print(f" ⚠️ PÁNICO SISTÉMICO: Ningún activo sostiene P > EMA20.")
            print(f" -> {REFUGIO_CASH_LIQUIDEZ:6s} | Preservación Absoluta (100% Core/Refugio a Cash/BIL) | Peso: {peso_liquidez_bil*100:.1f}%")

    return portafolio_objetivo, datos.iloc[-1]

# ==============================================================================
# 5. CÁLCULO DE ÓRDENES Y CAPITAL
# ==============================================================================
def calcular_instrucciones(portafolio_objetivo, precios_actuales, nav_actual):
    print("\n" + "=" * 80)
    print(f"  ÓRDENES DE REBALANCEO | NAV SIMULADOR: ${nav_actual:,.2f} USD")
    print("=" * 80)

    resumen = []
    total_peso = sum(portafolio_objetivo.values())

    for ticker, peso in portafolio_objetivo.items():
        precio = float(precios_actuales[ticker])
        capital_target = nav_actual * peso
        acciones = int(capital_target // precio)

        if ticker in [COBERTURA_BAJISTA, REFUGIO_RENTA_FIJA, REFUGIO_CASH_LIQUIDEZ]:
            stop_loss_str = "N/A (Táctico/Refugio)"
        else:
            stop_loss = precio * 0.95
            stop_loss_str = f"${stop_loss:.2f}"

        funcao = "Cobertura Inversa" if ticker == COBERTURA_BAJISTA else (
            "Renta Fija Refugio" if ticker == REFUGIO_RENTA_FIJA else (
                "Cash / Liquidez" if ticker == REFUGIO_CASH_LIQUIDEZ else "Renta Variable"
            )
        )

        resumen.append(
            {
                "Ticker": ticker,
                "Función Táctica": funcao,
                "Peso Target": f"{peso * 100:.1f}%",
                "Monto Target": f"${capital_target:,.2f}",
                "Precio Cierre": f"${precio:.2f}",
                "Acciones Objetivo": acciones,
                "Stop-Loss (-5%)": stop_loss_str,
            }
        )

    df = pd.DataFrame(resumen)
    print(df.to_string(index=False))
    print("-" * 80)
    print(f"Suma Total de Pesos Asignados: {total_peso * 100:.1f}%")
    print("=" * 80)

# ==============================================================================
# 6. EJECUCIÓN
# ==============================================================================
if __name__ == "__main__":
    datos_mercado = obtener_datos_corte_historico(FECHA_CORTE_SIMULACION)
    target_portfolio, ultimos_precios = diagnosticar_y_escanear_tactico(datos_mercado)
    calcular_instrucciones(target_portfolio, ultimos_precios, nav_actual=NAV_ACTUAL)
