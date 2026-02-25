import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, time, date
import requests
import pytz

# --- CONFIGURACIÓN ---
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'
ZONA_HORARIA = pytz.timezone('Europe/Madrid')

st.set_page_config(page_title="XSP 0DTE Institutional Terminal v2026", layout="wide")

# --- FUNCIONES DE CÁLCULO ---
def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def check_noticias_tactico(api_key):
    eventos_prohibidos = ["CPI", "FED", "FOMC", "NFP", "POWELL", "PPI", "INTEREST RATE", "JOBLESS"]
    hoy = str(date.today())
    url = f"https://finnhub.io{hoy}&to={hoy}&token={api_key}"
    estado = {"bloqueo": False, "tipo": "NORMAL", "eventos": []}
    try:
        r = requests.get(url, timeout=5).json().get('economicCalendar', [])
        for ev in r:
            if ev.get('country') == 'US' and ev.get('impact') == 'high':
                nombre = ev['event'].upper()
                if any(k in nombre for k in eventos_prohibidos):
                    h_utc = datetime.strptime(ev['time'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=pytz.utc)
                    h_es = h_utc.astimezone(ZONA_HORARIA).time()
                    estado["eventos"].append(f"{ev['event']} ({h_es.strftime('%H:%M')})")
                    if h_es < time(15, 30): estado["tipo"] = "PRE_MERCADO"
                    elif h_es > time(19, 30): estado["tipo"] = "TARDE_FED"
                    else: estado["bloqueo"] = True
        return estado
    except: return estado

def obtener_datos():
    tickers = {
        "XSP": "^XSP", "VIX": "^VIX", "VIX9D": "^VIX9D", 
        "VVIX": "^VVIX", "VIX1D": "^VIX1D", "NDX": "^NDX", 
        "SPY": "SPY", "SKEW": "^SKEW", "TNX": "^TNX"
    }
    vals = {}
    for k, v in tickers.items():
        try:
            df = yf.Ticker(v).history(period="1d", interval="1m")
            if df.empty: df = yf.Ticker(v).history(period="2d", interval="1h")
            
            rsi_val = 50
            if k == "XSP" and len(df) > 14:
                df['RSI'] = calculate_rsi(df['Close'])
                rsi_val = df['RSI'].iloc[-1]

            vals[k] = {
                "actual": df['Close'].iloc[-1], 
                "apertura": df['Open'].iloc[0] if not df.empty else 0,
                "min": df['Low'].min(),
                "max": df['High'].max(),
                "vol_actual": df['Volume'].iloc[-1] if 'Volume' in df.columns else 0,
                "vol_avg": df['Volume'].tail(20).mean() if 'Volume' in df.columns else 0,
                "rsi": rsi_val,
                "prev_close": df['Close'].iloc[-2] if len(df) > 1 else df['Close'].iloc[-1],
                "hist": df['Close']
            }
        except: vals[k] = {"actual": 0, "apertura": 0, "min": 0, "max": 0, "vol_actual": 0, "vol_avg": 0, "rsi": 50, "prev_close": 0, "hist": pd.Series()}
    return vals

# --- INTERFAZ STREAMLIT ---
st.title("🏛️ XSP 0DTE Institutional Terminal (All-In-One)")
st.caption("Filtros: Gamma, SMT, Volatilidad Inversa, Bonos, RSI e Intraday Regime")

# Auto-refresh cada 60 segundos
if st.sidebar.checkbox("Auto-actualizar (60s)", value=False):
    st.empty()
    st.info("Refrescando datos automáticamente...")

with st.sidebar:
    st.header("Risk Management")
    capital = st.number_input("Capital Cuenta (€)", value=10000.0, step=500.0)
    agresividad = st.select_slider("Buffer de Seguridad (Sigma)", options=[1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 2.0], value=2.0)
    btn_analizar = st.button("🚀 EJECUTAR ESCANEO TOTAL")

if btn_analizar:
    with st.spinner("Calculando niveles Gamma y Flujo Institucional..."):
        noticias = check_noticias_tactico(FINNHUB_API_KEY)
        d = obtener_datos()
        ahora = datetime.now(ZONA_HORARIA).time()

    if d["XSP"]["actual"] == 0:
        st.error("Error de datos. ¿Está el mercado abierto?")
        st.stop()

    # --- VARIABLES CLAVE ---
    xsp, ndx, spy = d["XSP"], d["NDX"], d["SPY"]
    vix, vix1d, vix9d = d["VIX"]["actual"], d["VIX1D"]["actual"], d["VIX9D"]["actual"]
    vix_ref = vix1d if vix1d > 0 else (vix if vix > 0 else 15)
    rango_pct = abs((xsp["actual"] - xsp["apertura"]) / xsp["apertura"] * 100) if xsp["apertura"] != 0 else 0
    
    # Análisis de Régimen (Compresión vs Expansión)
    std_reciente = xsp["hist"].tail(15).std()
    regime = "EXPANSIÓN 📈" if std_reciente > xsp["hist"].std() else "COMPRESIÓN 📉"

    # Filtros Institucionales
    vol_ratio = spy["vol_actual"] / spy["vol_avg"] if spy["vol_avg"] > 0 else 0
    vix_invertido = vix9d > vix
    bonos_subiendo = d["TNX"]["actual"] > d["TNX"]["prev_close"]
    
    # Niveles Gamma (Zero GEX Simulado)
    move_expected = xsp["actual"] * (vix_ref/100) / (252**0.5)
    zero_gex = xsp["actual"] - (move_expected * 0.5) if xsp["actual"] > xsp["apertura"] else xsp["actual"] + (move_expected * 0.5)

    # --- DASHBOARD ---
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("XSP / RSI", f"{xsp['actual']:.2f}", f"RSI: {xsp['rsi']:.1f}")
        st.write(f"**Régimen:** {regime}")
    with c2:
        st.metric("Volumen SPY", f"{vol_ratio:.2f}x", "vs 20m avg")
        st.write(f"**Zero Gamma:** {zero_gex:.2f}")
    with c3:
        st.metric("VIX / VIX9D", f"{vix:.2f} / {vix9d:.2f}")
        st.write(f"**Estructura:** {'⚠️ INVERTIDA' if vix_invertido else '✅ Normal'}")
    with c4:
        st.metric("SKEW Index", f"{d['SKEW']['actual']:.2f}")
        st.write(f"**Noticias:** {'🔴 BLOQUEO' if noticias['bloqueo'] else '✅ Limpio'}")

    st.divider()

    # --- LÓGICA DE TRIPLE DECISIÓN ---
    st.subheader("⚡ Recomendación Estratégica Alpha")

    if noticias["bloqueo"] or (vix_invertido and d["SKEW"]["actual"] > 148):
        st.error("### 🛑 BLOQUEO: No operar. Riesgo sistémico extremadamente alto.")
    else:
        sigma = (vix_ref / 100) / (252**0.5)
        dist = xsp["actual"] * sigma * agresividad
        lotes = max(1, int((capital * 0.02) // 200))

        # 1. LÓGICA IRON CONDOR (Días de Rango/Compresión)
        # Se activa si el régimen es compresión, VIX bajo y no hay noticias
        condicion_ic = (regime == "COMPRESIÓN 📉" and vix < 19 and vol_ratio < 1.1 and rango_pct < 0.35)

        if condicion_ic:
            v_up, v_down = round(xsp["actual"] + dist), round(xsp["actual"] - dist)
            st.success("### 🎯 OPERACIÓN: IRON CONDOR (Lateral)")
            st.write(f"**Call Side:** {v_up} / {v_up+2} | **Put Side:** {v_down} / {v_down-2}")
            st.info("💡 Justificación: El mercado está en compresión y la volatilidad es estable. Alta probabilidad de que el precio expire en el rango.")
        
        else:
            # 2. LÓGICA DIRECCIONAL (Días de Expansión/Volatilidad)
            bias_final = (xsp["actual"] > xsp["apertura"])
            if bonos_subiendo: bias_final = False 
            if vix_invertido: bias_final = False 
            
            tipo = "BULL PUT SPREAD" if bias_final else "BEAR CALL SPREAD"
            vend = round(xsp["actual"] - dist) if bias_final else round(xsp["actual"] + dist)
            comp = vend - 2 if bias_final else vend + 2
            
            # Puntuación de Confianza
            score = 0
            if vol_ratio > 1.2: score += 1
            if regime == "EXPANSIÓN 📈": score += 1
            if not bonos_subiendo: score += 1
            if (bias_final and xsp["rsi"] < 65) or (not bias_final and xsp["rsi"] > 35): score += 2

            st.info(f"### 🎯 OPERACIÓN: {tipo}")
            st.write(f"**Vender:** {vend} | **Comprar:** {comp} (Tramo 2 pts)")
            
            conf_labels = ["EVITAR ❌", "MUY BAJA 📉", "BAJA ⚠️", "MEDIA 🟡", "ALTA ✅", "INSTITUCIONAL 🔥"]
            st.subheader(f"Nivel de Confianza: {conf_labels[score]}")

        st.write(f"**Gestión de Capital:** Operar con {lotes} contrato(s). Riesgo máximo estimado: {capital*0.02:.2f}€")

else:
    st.info("Esperando análisis de mercado... Pulsa el botón para procesar.")
