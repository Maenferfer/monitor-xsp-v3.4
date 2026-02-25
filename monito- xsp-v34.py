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
    # CORRECCIÓN DE URL: Se restauró la ruta /api/v1/calendar/economic
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

# --- INTERFAZ ---
st.title("🏛️ XSP 0DTE Institutional Terminal (Triple Tier Levels)")
st.caption("Estrategia 2026: SMT, Volumen, Bonos, RSI y Tabla de Niveles Comparativa")

with st.sidebar:
    st.header("Configuración")
    capital = st.number_input("Capital Cuenta (€)", value=10000.0, step=500.0)
    btn_analizar = st.button("🚀 EJECUTAR ESCANEO TOTAL")

if btn_analizar:
    with st.spinner("Analizando flujo de órdenes y niveles sigma..."):
        noticias = check_noticias_tactico(FINNHUB_API_KEY)
        d = obtener_datos()
        ahora = datetime.now(ZONA_HORARIA).time()

    if d["XSP"]["actual"] == 0:
        st.error("Error de datos. ¿Está el mercado abierto?")
        st.stop()

    # --- VARIABLES ---
    xsp, ndx, spy = d["XSP"], d["NDX"], d["SPY"]
    vix, vix1d, vix9d = d["VIX"]["actual"], d["VIX1D"]["actual"], d["VIX9D"]["actual"]
    vix_ref = vix1d if vix1d > 0 else (vix if vix > 0 else 15)
    rango_pct = abs((xsp["actual"] - xsp["apertura"]) / xsp["apertura"] * 100) if xsp["apertura"] != 0 else 0
    std_reciente = xsp["hist"].tail(15).std()
    regime = "EXPANSIÓN 📈" if std_reciente > xsp["hist"].std() else "COMPRESIÓN 📉"
    vix_invertido = vix9d > vix
    vol_ratio = spy["vol_actual"] / spy["vol_avg"] if spy["vol_avg"] > 0 else 0
    bonos_subiendo = d["TNX"]["actual"] > d["TNX"]["prev_close"]

    # --- DASHBOARD ---
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("XSP Actual", f"{xsp['actual']:.2f}")
        st.write(f"**Régimen:** {regime}")
    with c2:
        st.metric("Volumen SPY", f"{vol_ratio:.2f}x")
        st.write(f"**SMT:** {'ALCISTA 🟢' if xsp['actual'] > xsp['min']*1.002 else 'BAJISTA 🔴'}")
    with c3:
        st.metric("VIX / VIX1D", f"{vix:.2f} / {vix1d:.2f}")
        st.write(f"**Bonos:** {'⚠️ Presión' if bonos_subiendo else '✅ Ok'}")
    with c4:
        st.metric("SKEW Index", f"{d['SKEW']['actual']:.2f}")
        st.write(f"**Noticias:** {'🔴 Bloqueo' if noticias['bloqueo'] else '✅ Limpio'}")

    if noticias["eventos"]:
        for ev in noticias["eventos"]:
            st.warning(f"Impacto detectado: {ev}")

    st.divider()

    # --- LÓGICA DE NIVELES COMPARATIVOS ---
    st.subheader("⚡ Tabla Comparativa de Niveles (XSP)")
    
    sigma = (vix_ref / 100) / (252**0.5)
    lotes = max(1, int((capital * 0.02) // 200))
    
    niveles = []
    for sig_mult in [1.1, 1.3, 1.5]:
        dist = xsp["actual"] * sigma * sig_mult
        niveles.append({
            "Perfil": "Agresivo (1.1σ)" if sig_mult == 1.1 else "Profesional (1.3σ)" if sig_mult == 1.3 else "Conservador (1.5σ)",
            "Venta CALL": round(xsp["actual"] + dist),
            "Venta PUT": round(xsp["actual"] - dist),
            "Distancia Pts": round(dist, 1)
        })
    
    st.table(pd.DataFrame(niveles))

    # --- RECOMENDACIÓN ESTRATÉGICA ---
    if noticias["bloqueo"] or (vix_invertido and d["SKEW"]["actual"] > 148):
        st.error("### 🛑 BLOQUEO DE SEGURIDAD: Riesgo Sistémico o Noticia Crítica.")
    else:
        cond_ic = (regime == "COMPRESIÓN 📉" and vix < 19 and vol_ratio < 1.2 and rango_pct < 0.40)
        
        if cond_ic:
            st.success(f"### 🎯 ESTRATEGIA: IRON CONDOR (Día Lateral)")
            st.info(f"Recomendado Perfil **Profesional (1.3σ)** | Lotes: {lotes}")
        else:
            bias = (xsp["actual"] > xsp["apertura"])
            if bonos_subiendo or vix_invertido: bias = False
            
            tipo = "BULL PUT SPREAD" if bias else "BEAR CALL SPREAD"
            st.info(f"### 🎯 ESTRATEGIA: {tipo}")
            
            score = 0
            if vol_ratio > 1.3: score += 1
            if regime == "EXPANSIÓN 📈": score += 1
            if not bonos_subiendo: score += 1
            if (bias and xsp["rsi"] < 65) or (not bias and xsp["rsi"] > 35): score += 2
            
            conf_labels = ["EVITAR ❌", "MUY BAJA 📉", "BAJA ⚠️", "MEDIA 🟡", "ALTA ✅", "INSTITUCIONAL 🔥"]
            st.write(f"**Confianza:** {conf_labels[score]} | **Lotes:** {lotes}")

else:
    st.info("Introduce capital y ejecuta para ver los niveles comparativos.")
