import datetime
import pandas as pd
import yfinance as yf
import numpy as np
import requests

# ==============================================================================
# 1. DEFINICIÓN DE PARÁMETROS Y OBTENCIÓN DINÁMICA DEL UNIVERSO S&P 500
# ==============================================================================
BENCHMARK = "SPY"
REFUGIO_RENTA_FIJA = "SHY"    # Treasuries 1-3 Años (Preservación Táctica - 50% en Risk-Off)
REFUGIO_CASH_LIQUIDEZ = "BIL" # Treasuries 1-3 Meses / Cash (Preservación Absoluta / Pánico)
COBERTURA_BAJISTA = "PSQ"     # Cobertura Activa Inversa (-1x QQQ)

def obtener_tickers_sp500():
    """Obtiene la lista actualizada de los componentes del S&P 500."""
    print("🔍 Obteniendo componentes actualizados del S&P 500...")
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        tabla = pd.read_html(response.text)[0]
    except requests.exceptions.RequestException as e:
        print(f"❌ Error al acceder a la URL: {e}")
        return []
    except ValueError as e:
        print(f"❌ Error al parsear la tabla HTML: {e}")
        return []

    tickers = tabla['Symbol'].str.replace('.', '-', regex=False).tolist()
    print(f"✅ Se cargaron {len(tickers)} componentes del S&P 500.\n")
    return tickers

# ==============================================================================
# 2. DESCARGA MASIVA DE DATOS DE MERCADO
# ==============================================================================
def obtener_datos_masivos(dias=365):
    tickers_sp500 = obtener_tickers_sp500()
    todos_los_tickers = list(set(
        tickers_sp500 + [BENCHMARK, REFUGIO_RENTA_FIJA, REFUGIO_CASH_LIQUIDEZ, COBERTURA_BAJISTA]
    ))

    hoy = datetime.date.today()
    fin_download = hoy + datetime.timedelta(days=1)
    inicio = hoy - datetime.timedelta(days=dias)

    print(f"🔄 Descargando precios de cierre históricos ({inicio} a {hoy})...")
    print("⏱️ Esto puede demorar unos segundos debido al volumen de datos...")

    datos_raw = yf.download(
        todos_los_tickers, start=inicio, end=fin_download, auto_adjust=False, progress=True
    )

    if "Close" in datos_raw:
        precios = datos_raw["Close"]
    else:
        precios = datos_raw

    # Elimina columnas sin datos suficientes (mantenemos mínimo 80% de datos cargados)
    precios_limpios = precios.dropna(thresh=int(len(precios) * 0.8), axis=1)
    return precios_limpios

# ==============================================================================
# 3. ALGORITMOS CUANTITATIVOS Y MÉTRICAS ROBUSTAS (EMA20 Y GATILLOS)
# ==============================================================================
def calcular_momentum_agresivo(precios_df):
    """Fórmula Acelerada: 70% Retorno 1 Mes (21d) + 30% Retorno 3 Meses (63d)."""
    r_1m = precios_df.pct_change(21)
    r_3m = precios_df.pct_change(63)
    score = (0.70 * r_1m) + (0.30 * r_3m)
    return score.iloc[-1]

def verificar_tendencia_ema20_robusta(precios_ticker):
    """Filtro Técnico Individual: Comprueba si P > EMA20 limpiando NaNs."""
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

    # Evaluación de cláusulas bajistas
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

def calcular_betas_masivos(precios_df, benchmark_ticker="SPY", dias=252):
    """Calcula el Beta rolling de 1 año respecto al SPY para todos los activos."""
    retornos = precios_df.pct_change().dropna().tail(dias)
    if benchmark_ticker not in retornos.columns:
        return pd.Series(1.0, index=precios_df.columns)

    covarianzas = retornos.cov()[benchmark_ticker]
    varianza_bm = retornos[benchmark_ticker].var()
    if varianza_bm == 0:
        return pd.Series(1.0, index=precios_df.columns)

    return covarianzas / varianza_bm

# ==============================================================================
# 4. ESCÁNER GLOBAL Y REBALANCEO DE CARTERA (REGLAS CAPÍTULO 2 - EMA20)
# ==============================================================================
def diagnosticar_y_escanear_sp500(datos):
    sp_risk_on, sp_precio, sp_ema, sp_motivo = evaluar_regimen_benchmark_spy(datos[BENCHMARK])
    fecha_evaluada = datos.index[-1].strftime("%Y-%m-%d")

    print("\n" + "=" * 80)
    print("   ESCÁNER CUANTITATIVO REBALANCEO S&P 500 | SISTEMA EMA20")
    print("=" * 80)
    print(f"Fecha Evaluada: {fecha_evaluada}")
    print(f"Estado SPY -> Cierre: ${sp_precio:.2f} | EMA20: ${sp_ema:.2f}")
    print(f"Diagnóstico de Régimen -> {sp_motivo}")

    portafolio_objetivo = {}

    # Excluir activos tácticos e instrumentos de control del cálculo general
    activos_excluidos = [BENCHMARK, REFUGIO_RENTA_FIJA, REFUGIO_CASH_LIQUIDEZ, COBERTURA_BAJISTA]
    tickers_elegibles = [col for col in datos.columns if col not in activos_excluidos]
    precios_elegibles = datos[tickers_elegibles]

    # Cálculo masivo de métricas
    scores_momentum = calcular_momentum_agresivo(precios_elegibles)
    betas = calcular_betas_masivos(datos, benchmark_ticker=BENCHMARK)

    # Evaluación continua de empresas con P > EMA20
    activos_tendencia = {}
    for t in tickers_elegibles:
        es_alcista, _, _ = verificar_tendencia_ema20_robusta(datos[t])
        if es_alcista and not np.isnan(scores_momentum.get(t, np.nan)):
            activos_tendencia[t] = scores_momentum[t]

    print(f"\n📊 Total de empresas en el S&P 500 que cumplen la condición P > EMA20: {len(activos_tendencia)}")
    print("-" * 80)

    # --------------------------------------------------------------------------
    # ESCENARIO A: MERCADO ALCISTA ($SPY > EMA20) - RISK-ON
    # --------------------------------------------------------------------------
    if sp_risk_on:
        # --- MÓDULO CORE (75% Total -> Top 3 Momentum con P > EMA20) ---
        ranking_core = sorted(activos_tendencia.items(), key=lambda x: x[1], reverse=True)
        top_3_core = [t for t, _ in ranking_core[:3]]

        print("\n🔥 MÓDULO CORE SELECCIONADO (75% NAV - Top 3 Momentum Alcistas):")
        for t in top_3_core:
            portafolio_objetivo[t] = 0.25
            print(f" -> {t:6s} | Score Momentum: {scores_momentum[t]:7.4f} | Beta vs SPY: {betas.get(t, 1.0):.2f} | Peso: 25.0%")

        # Relleno a cash/liquidez si en todo el S&P 500 hay menos de 3 acciones alcistas
        if len(top_3_core) < 3:
            faltantes = 3 - len(top_3_core)
            peso_refugio = faltantes * 0.25
            portafolio_objetivo[REFUGIO_CASH_LIQUIDEZ] = portafolio_objetivo.get(REFUGIO_CASH_LIQUIDEZ, 0.0) + peso_refugio
            print(f" -> {REFUGIO_CASH_LIQUIDEZ:6s} (Falta de cuotas Core -> Liquidez) | Peso: {peso_refugio*100:.1f}%")

        # --- MÓDULO SATÉLITE (25% Total -> Top 1 Alto Beta >= 1.20 + P > EMA20) ---
        candidatos_cohetes = {}
        for t, score in activos_tendencia.items():
            beta_t = betas.get(t, 1.0)
            if beta_t >= 1.20:
                candidatos_cohetes[t] = (score, beta_t)

        print("\n🚀 MÓDULO SATÉLITE SELECCIONADO (25% NAV - Top 1 Cohete Alto Beta):")
        if candidatos_cohetes:
            top_1_sat = max(candidatos_cohetes, key=lambda x: candidatos_cohetes[x][0])
            score_win, beta_win = candidatos_cohetes[top_1_sat]
            portafolio_objetivo[top_1_sat] = 0.25
            print(f" -> {top_1_sat:6s} | Score Momentum: {score_win:7.4f} | Beta vs SPY: {beta_win:.2f} | Peso: 25.0%")
        else:
            portafolio_objetivo[REFUGIO_CASH_LIQUIDEZ] = portafolio_objetivo.get(REFUGIO_CASH_LIQUIDEZ, 0.0) + 0.25
            print(f" -> {REFUGIO_CASH_LIQUIDEZ:6s} (Sin acciones Beta >= 1.2 en tendencia -> Liquidez) | Peso: 25.0%")

    # --------------------------------------------------------------------------
    # ESCENARIO B: MERCADO BAJISTA ($SPY < EMA20 / GATILLOS) - PROTOCOLO DEFENSIVO HÍBRIDO
    # --------------------------------------------------------------------------
    else:
        print("\n🛡️ EJECUTANDO PROTOCOLO DEFENSIVO HÍBRIDO (Estrategia Bajista - EMA20):")

        # --- MÓDULO SATÉLITE (25% NAV) -> Rotación a Cobertura Activa ($PSQ) ---
        portafolio_objetivo[COBERTURA_BAJISTA] = 0.25
        print(f"\n⚡ MÓDULO SATÉLITE (25% NAV - Cobertura Activa Inversa):")
        print(f" -> {COBERTURA_BAJISTA:6s} | Alfa Bajista (Inverse -1x QQQ) | Peso: 25.0%")

        # --- MÓDULO CORE (75% NAV) -> Acciones Resilientes vs Renta Fija / Cash ---
        ranking_core = sorted(activos_tendencia.items(), key=lambda x: x[1], reverse=True)

        print(f"\n🛡️ MÓDULO CORE (75% NAV - Resiliencia / Renta Fija / Cash):")
        if ranking_core:
            # Asignación máxima de 25% combinado a las Top 2 acciones que sostienen P > EMA20
            top_2_resilientes = [t for t, _ in ranking_core[:2]]
            peso_por_activo = 0.25 / len(top_2_resilientes)

            for t in top_2_resilientes:
                portafolio_objetivo[t] = peso_por_activo
                print(f" -> {t:6s} | Resiliente (P > EMA20) | Score: {scores_momentum[t]:7.4f} | Peso: {peso_por_activo*100:.1f}%")

            # Asignación del 50% a Renta Fija Refugio ($SHY - Treasuries 1-3 Años)
            peso_rf = 0.50
            portafolio_objetivo[REFUGIO_RENTA_FIJA] = peso_rf
            print(f" -> {REFUGIO_RENTA_FIJA:6s} | Refugio Renta Fija (Treasuries 1-3 años) | Peso: {peso_rf*100:.1f}%")
        else:
            # Pánico Sistémico: 100% del Módulo Core (75% NAV) a Liquidez/Cash ($BIL)
            peso_liquidez_core = 0.75
            portafolio_objetivo[REFUGIO_CASH_LIQUIDEZ] = peso_liquidez_core
            print(f" ⚠️ PÁNICO SISTÉMICO: Ningún activo sostiene P > EMA20.")
            print(f" -> {REFUGIO_CASH_LIQUIDEZ:6s} | Preservación Absoluta: 100% Core a Cash ($BIL) | Peso: {peso_liquidez_core*100:.1f}%")

    return portafolio_objetivo, datos.iloc[-1]

# ==============================================================================
# 5. GENERACIÓN DE ÓRDENES Y CÁLCULO DE CAPITAL
# ==============================================================================
def calcular_instrucciones(portafolio_objetivo, precios_actuales, nav_actual):
    print("\n" + "=" * 80)
    print(f"  ÓRDENES DE REBALANCEO | NAV ACTUAL EN SIMULADOR: ${nav_actual:,.2f} USD")
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
                "Cash / Liquidez" if ticker == REFUGIO_CASH_LIQUIDEZ else "Acción RV"
            )
        )
