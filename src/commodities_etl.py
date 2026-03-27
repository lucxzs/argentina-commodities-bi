

import yfinance as yf
import pandas as pd
import os
from datetime import datetime, date

# Configuración  

# Carpeta donde se guardan los CSV (ajustá la ruta a tu máquina)
OUTPUT_DIR = "data"

# Tickers de Yahoo Finance para cada commodity
COMMODITIES = {
    "soja":  "ZS=F",   # Soybean Futures
    "maiz":  "ZC=F",   # Corn Futures
    "trigo": "ZW=F",   # Wheat Futures
}

# Días de historia que se descargan en cada ejecución
HISTORY_DAYS = "5d"  # 1 año (puede ser "5d", "1mo", "3mo", "6mo", "1y", "2y", etc.)

# Funciones 

def descargar_precios(ticker: str, periodo: str) -> pd.DataFrame:
    """Descarga el historial de precios de Yahoo Finance."""
    data = yf.Ticker(ticker).history(period=periodo)
    if data.empty:
        raise ValueError(f"No se obtuvieron datos para {ticker}")
    data = data[["Close"]].copy() # solo nos quedamos con el precio de cierre
    data.index = pd.to_datetime(data.index).tz_localize(None) # quita timezone para evitar problemas al guardar/leer CSV
    data.index.name = "fecha"
    data.columns = ["precio_cierre"]
    return data


def calcular_kpis(df: pd.DataFrame) -> pd.DataFrame:
    # 
    # Agrega columnas de KPIs sobre el DataFrame de precios.
    df = df.copy()

    # Variación % diaria
    df["variacion_pct_diaria"] = df["precio_cierre"].pct_change() * 100

    # Promedios móviles
    df["promedio_movil_30d"] = df["precio_cierre"].rolling(window=30).mean()
    df["promedio_movil_90d"] = df["precio_cierre"].rolling(window=90).mean()

    # Volatilidad histórica (desv. estándar de retornos diarios, ventana 30 días)
    retornos_diarios = df["precio_cierre"].pct_change()
    df["volatilidad_30d"] = retornos_diarios.rolling(window=30).std() * 100

    # Máximo y mínimo del mes en curso
    mes_actual = date.today().month
    anio_actual = date.today().year
    mask_mes = (df.index.month == mes_actual) & (df.index.year == anio_actual)
    max_mes = df.loc[mask_mes, "precio_cierre"].max()
    min_mes = df.loc[mask_mes, "precio_cierre"].min()
    df["maximo_mes"] = None
    df["minimo_mes"] = None
    df.loc[mask_mes, "maximo_mes"] = max_mes
    df.loc[mask_mes, "minimo_mes"] = min_mes

    # Redondear columnas numéricas
    cols_num = [
        "precio_cierre", "variacion_pct_diaria",
        "promedio_movil_30d", "promedio_movil_90d",
        "volatilidad_30d", "maximo_mes", "minimo_mes",
    ]
    df[cols_num] = df[cols_num].round(4)

    return df


def guardar_csv(df: pd.DataFrame, nombre: str, output_dir: str) -> str:
    """
    Guarda el DataFrame en CSV.
    Si el archivo ya existe, solo agrega las filas nuevas (sin duplicar).
    """
    os.makedirs(output_dir, exist_ok=True)
    ruta = os.path.join(output_dir, f"{nombre}.csv")

    if os.path.exists(ruta):
        existente = pd.read_csv(ruta, index_col="fecha", parse_dates=True)
        combinado = pd.concat([existente, df])
        combinado = combinado[~combinado.index.duplicated(keep="last")]
        combinado.sort_index(inplace=True)
        combinado.to_csv(ruta)
    else:
        df.to_csv(ruta)

    return ruta


def log(mensaje: str):
    """Imprime con timestamp. El Task Scheduler puede redirigir esto a un .log"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {mensaje}")


# Pipeline principal 

def main():
    log("=== Inicio de extracción de commodities ===")

    for nombre, ticker in COMMODITIES.items():
        try:
            log(f"Descargando {nombre} ({ticker})...")

            df_nuevo = descargar_precios(ticker, HISTORY_DAYS)
            log(f"{nombre}: última fecha descargada = {df_nuevo.index.max()}")

            ruta = os.path.join(OUTPUT_DIR, f"{nombre}.csv")

            if os.path.exists(ruta):
                existente = pd.read_csv(ruta, index_col="fecha", parse_dates=True)

                ultima_existente = existente.index.max()
                ultima_nueva = df_nuevo.index.max()

                # 🧠 OPCIÓN 1 → validación
                if ultima_nueva <= ultima_existente:
                    log(f"{nombre}: No hay datos nuevos (última: {ultima_existente})")
                    continue

                # descarga una ventana corta de datos recientes y mantiene un histórico persistido localmente.

                combinado = pd.concat([existente, df_nuevo]) 
                combinado = combinado[~combinado.index.duplicated(keep="last")]
                combinado.sort_index(inplace=True)

            else:
                log(f"{nombre}: creando dataset inicial")
                combinado = df_nuevo

            # recalculamos KPIs sobre todo el histórico
            combinado = calcular_kpis(combinado)

            combinado.to_csv(ruta)

            log(f"{nombre}: actualizado correctamente → {len(combinado)} filas")

        except Exception as e:
            log(f"ERROR en {nombre}: {e}")

    log("=== Extracción finalizada ===")


if __name__ == "__main__":
    main()