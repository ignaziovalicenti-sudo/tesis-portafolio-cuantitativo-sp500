# Script 0: Instalación de librerías
!pip install yfinance openpyxl -q

Script 2
# ==========================================
# SCRIPT 1: SELECCIÓN Y CARGA DEL ARCHIVO
# El archivo debe ser extraido del simulador y 
# almacenado en la computadora
# ==========================================

try:
    # Método para Google Colab
    from google.colab import files

    print("Por favor, selecciona tu archivo CSV desde tu computadora:")

    uploaded = files.upload()

    archivo_csv_seleccionado = list(uploaded.keys())[0]

    print(
        f"✅ Archivo '{archivo_csv_seleccionado}' cargado con éxito. Ya puedes ejecutar el Script 2."
    )

except ImportError:

    # Método para Jupyter Notebook local

    import ipywidgets as widgets
    from IPython.display import display

    print(
        "Por favor, selecciona tu archivo CSV desde tu computadora:"
    )

    uploader = widgets.FileUpload(
        accept=".csv",
        multiple=False
    )

    display(uploader)

    archivo_csv_seleccionado = None

    def on_upload_change(change):

        global archivo_csv_seleccionado

        if uploader.value:

            # Compatibilidad diferentes versiones

            if isinstance(
                uploader.value,
                (list, tuple)
            ):

                uploaded_file = uploader.value[0]

                archivo_csv_seleccionado = (
                    uploaded_file["name"]
                )

                contenido = (
                    uploaded_file["content"]
                )

            else:

                archivo_csv_seleccionado = (
                    list(
                        uploader.value.keys()
                    )[0]
                )

                contenido = (
                    uploader.value[
                        archivo_csv_seleccionado
                    ]["content"]
                )

            with open(
                archivo_csv_seleccionado,
                "wb"
            ) as f:

                f.write(contenido)

            print(
                f"\n✅ Archivo '{archivo_csv_seleccionado}' cargado con éxito. Ya puedes ejecutar el Script 2."
            )

    uploader.observe(
        on_upload_change,
        names="value"
    )

# ============================================================
# SCRIPT 2 FINAL UNIFICADO
# RENDIMIENTO DEL PORTAFOLIO VS. SPMO
#
# Incluye:
# - Operaciones cerradas
# - Posiciones abiertas al 25/09/2026
# - Dividendos
# - Control de cantidades
# - Exportación de la serie diaria para el script de alfa
# - Gráfico en 600 DPI
# ============================================================

!pip -q install yfinance openpyxl

import warnings
warnings.filterwarnings("ignore")

import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

from google.colab import files
from IPython.display import display


# ============================================================
# 1. PARÁMETROS
# ============================================================

CAPITAL_INICIAL = 100000.00

BENCHMARK = "SPMO"

FECHA_VALUACION = pd.Timestamp("2026-09-25")

# yfinance interpreta end como fecha exclusiva
FECHA_FIN_DESCARGA = (
    FECHA_VALUACION + pd.Timedelta(days=1)
)

ARCHIVO_SERIE_DIARIA = (
    "serie_diaria_portafolio_spmo.csv"
)

ARCHIVO_EXCEL = (
    "reconstruccion_portafolio_spmo.xlsx"
)

ARCHIVO_GRAFICO = (
    "rendimiento_portafolio_vs_spmo.png"
)


# ============================================================
# 2. CARGAR CSV
# ============================================================

# Si archivo_csv_seleccionado ya fue definido
# en el script anterior, se utiliza directamente.
#
# Si no existe, se solicita el archivo.

try:

    archivo_csv_seleccionado

except NameError:

    print("Seleccione el CSV de Wall Street Survivor:")

    archivos_subidos = files.upload()

    archivo_csv_seleccionado = next(
        iter(archivos_subidos)
    )


df = pd.read_csv(archivo_csv_seleccionado)

print(
    f"\nArchivo cargado: "
    f"{archivo_csv_seleccionado}"
)

print(
    f"Cantidad de registros: {len(df)}"
)

print("\nColumnas encontradas:")

print(df.columns.tolist())

display(df.head())


# ============================================================
# 3. VALIDAR COLUMNAS
# ============================================================

df.columns = df.columns.str.strip()

columnas_requeridas = [
    "CreateDate",
    "Symbol",
    "TransactionType",
    "Quantity",
    "Price"
]

columnas_faltantes = [
    columna
    for columna in columnas_requeridas
    if columna not in df.columns
]

if columnas_faltantes:

    raise ValueError(
        "Faltan las siguientes columnas: "
        f"{columnas_faltantes}\n"
        "Columnas disponibles: "
        f"{df.columns.tolist()}"
    )


# ============================================================
# 4. LIMPIEZA DEL ARCHIVO
# ============================================================

df["Symbol"] = (
    df["Symbol"]
    .astype(str)
    .str.strip()
    .str.upper()
)

df["TransactionType"] = (
    df["TransactionType"]
    .astype(str)
    .str.strip()
)

df["Tipo"] = (
    df["TransactionType"]
    .str.lower()
)

df["CreateDate"] = pd.to_datetime(
    df["CreateDate"],
    format="%m/%d/%Y - %H:%M",
    errors="coerce"
)

# Segundo intento para formatos diferentes

mascara_fechas = df["CreateDate"].isna()

df.loc[
    mascara_fechas,
    "CreateDate"
] = pd.to_datetime(
    df.loc[
        mascara_fechas,
        "CreateDate"
    ],
    errors="coerce"
)

df["Fecha"] = (
    df["CreateDate"]
    .dt.normalize()
)

df["Price"] = (
    df["Price"]
    .astype(str)
    .str.replace("$", "", regex=False)
    .str.replace(",", "", regex=False)
    .str.strip()
)

df["Price"] = pd.to_numeric(
    df["Price"],
    errors="coerce"
)

df["Quantity"] = pd.to_numeric(
    df["Quantity"],
    errors="coerce"
)

df = df.dropna(
    subset=[
        "CreateDate",
        "Fecha",
        "Symbol",
        "Quantity",
        "Price"
    ]
)

df = (
    df
    .sort_values("CreateDate")
    .reset_index(drop=True)
)

fecha_inicio = df["Fecha"].min()

if df["Fecha"].max() > FECHA_VALUACION:

    raise ValueError(
        "Existen operaciones posteriores a la "
        "fecha de valuación."
    )

print("\nPeríodo analizado:")

print(
    "Primera operación:",
    fecha_inicio.date()
)

print(
    "Última operación:",
    df["Fecha"].max().date()
)

print(
    "Fecha de valuación:",
    FECHA_VALUACION.date()
)

print("\nTipos de transacción:")

print(
    df["TransactionType"]
    .value_counts()
)


# ============================================================
# 5. TICKERS
# ============================================================

# Excluir eventuales símbolos vacíos

tickers = sorted(
    df.loc[
        df["Symbol"].notna(),
        "Symbol"
    ].unique()
)

print(
    "\nCantidad de activos:",
    len(tickers)
)

print(tickers)


# ============================================================
# 6. DESCARGAR PRECIOS DE LOS ACTIVOS
# ============================================================

# Se utilizan precios Close.
# No se utilizan precios ajustados para valorar
# las cantidades físicas mantenidas.

data = yf.download(
    tickers=tickers,
    start=fecha_inicio.strftime("%Y-%m-%d"),
    end=FECHA_FIN_DESCARGA.strftime("%Y-%m-%d"),
    auto_adjust=False,
    progress=False,
    group_by="column"
)

if data.empty:

    raise ValueError(
        "Yahoo Finance no devolvió precios."
    )

if isinstance(data.columns, pd.MultiIndex):

    if "Close" not in data.columns.get_level_values(0):

        raise ValueError(
            "No se encontró el nivel Close "
            "en los datos descargados."
        )

    precios = data["Close"].copy()

elif "Close" not in data.columns:

    raise ValueError(
        "No se encontró la columna Close."
    )

else:

    precios = data[["Close"]].copy()

    precios.columns = [tickers[0]]


precios.index = pd.to_datetime(
    precios.index
).tz_localize(None)

precios.columns = [
    str(columna).strip().upper()
    for columna in precios.columns
]

precios = precios.sort_index()

# Completar solamente precios posteriores
# al primer precio disponible

precios = precios.ffill()


# ============================================================
# 7. DESCARGAR SPMO
# ============================================================

data_spmo = yf.download(
    tickers=BENCHMARK,
    start=fecha_inicio.strftime("%Y-%m-%d"),
    end=FECHA_FIN_DESCARGA.strftime("%Y-%m-%d"),
    auto_adjust=False,
    progress=False
)

if data_spmo.empty:

    raise ValueError(
        "No se pudo descargar el benchmark SPMO."
    )

if isinstance(
    data_spmo.columns,
    pd.MultiIndex
):

    data_spmo.columns = (
        data_spmo.columns
        .get_level_values(0)
    )

# Para rendimiento total del benchmark se utiliza
# Adj Close. Si no estuviera disponible, utiliza Close.

if "Adj Close" in data_spmo.columns:

    spmo = data_spmo["Adj Close"].copy()

elif "Close" in data_spmo.columns:

    spmo = data_spmo["Close"].copy()

else:

    raise ValueError(
        "No se encontró la columna Close ni Adj Close para SPMO."
    )

if isinstance(spmo, pd.DataFrame):

    spmo = spmo.iloc[:, 0]

spmo.index = pd.to_datetime(
    spmo.index
).tz_localize(None)

spmo.name = BENCHMARK

spmo = spmo.sort_index()


# ============================================================
# 8. CALENDARIO BURSÁTIL
# ============================================================

fechas_bursatiles = spmo.index[
    (spmo.index >= fecha_inicio) &
    (spmo.index <= FECHA_VALUACION)
]

if len(fechas_bursatiles) == 0:

    raise ValueError(
        "No se encontraron fechas bursátiles."
    )

fecha_final_real = fechas_bursatiles.max()

print(
    "\nÚltima fecha bursátil utilizada:",
    fecha_final_real.date()
)

precios = (
    precios
    .reindex(fechas_bursatiles)
    .ffill()
)

spmo = (
    spmo
    .reindex(fechas_bursatiles)
    .ffill()
)


# ============================================================
# 9. ASIGNAR FECHA BURSÁTIL
# ============================================================

def siguiente_fecha_bursatil(
    fecha,
    calendario
):

    fechas_validas = calendario[
        calendario >= fecha
    ]

    if len(fechas_validas) == 0:

        return pd.NaT

    return fechas_validas[0]


df["FechaBursatil"] = df["Fecha"].apply(
    lambda fecha: siguiente_fecha_bursatil(
        fecha,
        fechas_bursatiles
    )
)

df = df.dropna(
    subset=["FechaBursatil"]
)


# ============================================================
# 10. RECONSTRUCCIÓN DEL PORTAFOLIO
# ============================================================

cash = CAPITAL_INICIAL

shares = {
    ticker: 0.0
    for ticker in tickers
}

historial = []

operaciones_no_reconocidas = []

for fecha in fechas_bursatiles:

    operaciones = (
        df[
            df["FechaBursatil"] == fecha
        ]
        .sort_values("CreateDate")
    )

    for _, op in operaciones.iterrows():

        ticker = op["Symbol"]

        qty = float(
            op["Quantity"]
        )

        precio_operacion = float(
            op["Price"]
        )

        tipo = op["Tipo"]

        # ----------------------------------------------------
        # DIVIDENDOS
        # ----------------------------------------------------

        if "dividend" in tipo:

            ingreso_dividendo = (
                abs(qty) *
                precio_operacion
            )

            cash += ingreso_dividendo

        # ----------------------------------------------------
        # COMPRAS Y VENTAS
        #
        # El archivo utiliza:
        # Compra: cantidad positiva
        # Venta: cantidad negativa
        #
        # Por eso una venta negativa incrementa el efectivo.
        # ----------------------------------------------------

        elif (
            "buy" in tipo
            or "sell" in tipo
        ):

            cash -= (
                qty *
                precio_operacion
            )

            shares[ticker] += qty

        else:

            operaciones_no_reconocidas.append({
                "Fecha": fecha,
                "Ticker": ticker,
                "Tipo": op["TransactionType"],
                "Cantidad": qty,
                "Precio": precio_operacion
            })

    # --------------------------------------------------------
    # VALUACIÓN DIARIA DE POSICIONES
    # --------------------------------------------------------

    valor_activos = 0.0

    registro = {
        "Date": fecha,
        "Cash": cash
    }

    for ticker in tickers:

        cantidad = shares[ticker]

        if ticker not in precios.columns:

            if abs(cantidad) > 1e-8:

                raise ValueError(
                    f"No se descargaron precios "
                    f"para {ticker}."
                )

            continue

        precio_dia = precios.loc[
            fecha,
            ticker
        ]

        if (
            abs(cantidad) > 1e-8
            and pd.isna(precio_dia)
        ):

            raise ValueError(
                f"Falta el precio de {ticker} "
                f"para {fecha.date()}."
            )

        if pd.isna(precio_dia):

            valor_ticker = 0.0

        else:

            valor_ticker = (
                cantidad *
                float(precio_dia)
            )

        valor_activos += valor_ticker

        registro[
            f"Cantidad_{ticker}"
        ] = cantidad

        registro[
            f"Precio_{ticker}"
        ] = precio_dia

        registro[
            f"Valor_{ticker}"
        ] = valor_ticker

    patrimonio = (
        cash +
        valor_activos
    )

    registro["Assets"] = valor_activos

    registro["PortfolioValue"] = patrimonio

    registro[BENCHMARK] = float(
        spmo.loc[fecha]
    )

    historial.append(registro)


# ============================================================
# 11. DATAFRAME DEL PORTAFOLIO
# ============================================================

portfolio = pd.DataFrame(
    historial
)

portfolio = (
    portfolio
    .set_index("Date")
    .sort_index()
)

print("\nÚltimos registros del portafolio:")

display(
    portfolio[
        [
            "Cash",
            "Assets",
            "PortfolioValue",
            BENCHMARK
        ]
    ].tail()
)


# ============================================================
# 12. POSICIONES ABIERTAS
# ============================================================

lista_posiciones_abiertas = []

for ticker, cantidad in shares.items():

    if abs(cantidad) > 1e-8:

        precio_final = float(
            precios.loc[
                fecha_final_real,
                ticker
            ]
        )

        valor_final = (
            cantidad *
            precio_final
        )

        lista_posiciones_abiertas.append({
            "Ticker": ticker,
            "Cantidad": cantidad,
            "Precio final": precio_final,
            "Valor final": valor_final
        })


posiciones_abiertas = pd.DataFrame(
    lista_posiciones_abiertas
)

if posiciones_abiertas.empty:

    posiciones_abiertas = pd.DataFrame(
        columns=[
            "Ticker",
            "Cantidad",
            "Precio final",
            "Valor final"
        ]
    )

else:

    posiciones_abiertas = (
        posiciones_abiertas
        .sort_values(
            "Valor final",
            ascending=False
        )
        .reset_index(drop=True)
    )


print(
    "\nPOSICIONES ABIERTAS AL",
    fecha_final_real.date()
)

display(posiciones_abiertas)

valor_posiciones_abiertas = (
    posiciones_abiertas[
        "Valor final"
    ].sum()
    if not posiciones_abiertas.empty
    else 0.0
)

print(
    "Valor de posiciones abiertas:",
    f"USD {valor_posiciones_abiertas:,.2f}"
)


# ============================================================
# 13. CONTROL DE POSICIONES
# ============================================================

control_posiciones = []

for ticker in tickers:

    operaciones_ticker = df[
        df["Symbol"] == ticker
    ]

    operaciones_no_dividendos = (
        operaciones_ticker[
            ~operaciones_ticker[
                "Tipo"
            ].str.contains(
                "dividend",
                na=False
            )
        ]
    )

    cantidad_neta = (
        operaciones_no_dividendos[
            "Quantity"
        ].sum()
    )

    control_posiciones.append({
        "Ticker": ticker,
        "Cantidad neta CSV": cantidad_neta,
        "Cantidad reconstruida": shares[ticker],
        "Diferencia": (
            cantidad_neta -
            shares[ticker]
        ),
        "Estado": (
            "Abierta"
            if abs(shares[ticker]) > 1e-8
            else "Cerrada"
        )
    })


control_posiciones = pd.DataFrame(
    control_posiciones
)

print("\nControl de cantidades:")

display(control_posiciones)


# ============================================================
# 14. COMPARACIÓN PORTAFOLIO VS. SPMO
# ============================================================

comparacion = portfolio[
    [
        "PortfolioValue",
        BENCHMARK
    ]
].copy()

comparacion = comparacion.dropna()

# ------------------------------------------------------------
# PORTAFOLIO
#
# Se calcula contra el capital inicial real de USD 100.000.
# ------------------------------------------------------------

comparacion["Portafolio"] = (
    comparacion["PortfolioValue"]
    / CAPITAL_INICIAL
    - 1
) * 100

# ------------------------------------------------------------
# SPMO
#
# Se normaliza a 0% en la primera fecha.
# ------------------------------------------------------------

comparacion["SPMO_Ret"] = (
    comparacion[BENCHMARK]
    / comparacion[BENCHMARK].iloc[0]
    - 1
) * 100


# ============================================================
# 15. RESULTADOS
# ============================================================

ret_port = comparacion[
    "Portafolio"
].iloc[-1]

ret_spmo = comparacion[
    "SPMO_Ret"
].iloc[-1]

diferencia_acumulada = (
    ret_port -
    ret_spmo
)

patrimonio_final = portfolio[
    "PortfolioValue"
].iloc[-1]

cash_final = portfolio[
    "Cash"
].iloc[-1]

assets_final = portfolio[
    "Assets"
].iloc[-1]


print("\n" + "=" * 60)

print("RESULTADOS")

print("=" * 60)

print(
    f"Portafolio:          "
    f"{ret_port:.2f}%"
)

print(
    f"SPMO:                "
    f"{ret_spmo:.2f}%"
)

print(
    f"Diferencia acumulada:"
    f" {diferencia_acumulada:.2f}%"
)

print()

print(
    "Patrimonio final:",
    f"USD {patrimonio_final:,.2f}"
)

print(
    "Cash final:",
    f"USD {cash_final:,.2f}"
)

print(
    "Posiciones abiertas:",
    f"USD {assets_final:,.2f}"
)

print(
    "Control patrimonio:",
    f"USD {(cash_final + assets_final):,.2f}"
)


# ============================================================
# 16. GRÁFICO
# MISMA ARQUITECTURA VISUAL
# ============================================================

fig, ax = plt.subplots(
    figsize=(16, 9)
)

ax.plot(
    comparacion.index,
    comparacion["Portafolio"],
    color="blue",
    linewidth=3.5,
    label="Portafolio"
)

ax.plot(
    comparacion.index,
    comparacion["SPMO_Ret"],
    color="orange",
    linewidth=3.5,
    label="SPMO"
)

ultimo_indice = comparacion.index[-1]

ax.text(
    ultimo_indice,
    ret_port + 0.8, # Adjusted from 1.8
    f"{ret_port:.2f}%",
    color="blue",
    fontweight="bold",
    fontsize=16,
    va="bottom",
    ha="center"
)

ax.text(
    ultimo_indice,
    ret_spmo + 0.8, # Adjusted from 1.8
    f"{ret_spmo:.2f}%",
    color="orange",
    fontweight="bold",
    fontsize=16,
    va="bottom",
    ha="center"
)

ax.axhline(
    y=0,
    color="black",
    linestyle="--",
    linewidth=1.2
)

ax.set_title(
    "Rendimiento Comparativo: "
    "Portafolio vs. SPMO "
    "(27/07/2026 - 25/09/2026)",
    fontsize=20,
    fontweight="bold",
    pad=20
)

ax.set_ylabel(
    "Rendimiento (%)",
    fontsize=16,
    labelpad=15
)

ax.set_xlabel(
    "Fecha",
    fontsize=16,
    labelpad=15
)

ax.xaxis.set_major_formatter(
    mdates.DateFormatter("%Y-%m-%d")
)

ax.tick_params(
    axis="both",
    which="major",
    labelsize=14
)

plt.setp(
    ax.get_xticklabels(),
    rotation=35,
    ha="right"
)

ax.grid(
    True,
    alpha=0.3
)

ax.legend(
    loc="upper left",
    fontsize=15
)

plt.tight_layout()

plt.savefig(
    ARCHIVO_GRAFICO,
    dpi=600,
    bbox_inches="tight"
)

print(
    f"\nGráfico guardado como "
    f"'{ARCHIVO_GRAFICO}'."
)

plt.show()


# ============================================================
# 17. EXPORTAR SERIE DIARIA
#
# El script de alfa debe utilizar este archivo para garantizar
# exactamente el mismo rendimiento y patrimonio final.
# ============================================================

serie_diaria = portfolio[
    [
        "Cash",
        "Assets",
        "PortfolioValue",
        BENCHMARK
    ]
].copy()

serie_diaria.index.name = "Fecha"

serie_diaria.to_csv(
    ARCHIVO_SERIE_DIARIA
)


# ============================================================
# 18. EXPORTAR EXCEL DE CONTROL
# ============================================================

resumen = pd.DataFrame({
    "Indicador": [
        "Capital inicial",
        "Patrimonio final",
        "Cash final",
        "Valor posiciones abiertas",
        "Rendimiento portafolio",
        "Rendimiento SPMO",
        "Diferencia acumulada",
        "Fecha final"
    ],
    "Valor": [
        CAPITAL_INICIAL,
        patrimonio_final,
        cash_final,
        assets_final,
        ret_port / 100,
        ret_spmo / 100,
        diferencia_acumulada / 100,
        fecha_final_real
    ]
})

with pd.ExcelWriter(
    ARCHIVO_EXCEL,
    engine="openpyxl"
) as writer:

    resumen.to_excel(
        writer,
        sheet_name="Resumen",
        index=False
    )

    serie_diaria.to_excel(
        writer,
        sheet_name="Serie diaria"
    )

    posiciones_abiertas.to_excel(
        writer,
        sheet_name="Posiciones abiertas",
        index=False
    )

    control_posiciones.to_excel(
        writer,
        sheet_name="Control posiciones",
        index=False
    )

    df.to_excel(
        writer,
        sheet_name="Operaciones depuradas",
        index=False
    )
