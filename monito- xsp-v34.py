import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
from datetime import datetime, time, date
import requests
import pytz

# --- CONFIGURACIÓN ---
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'
ZONA_HORARIA = pytz.timezone('Europe/Madrid')

st.set_page_config(page_title="XSP 0DTE Terminal v4.1 - IBKR Edition", layout="wide")

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
            
            rsi_val = 50.0
            if k == "XSP" and len(df) > 14:
                df['RSI'] = calculate_rsi(df['Close'])
                rsi_val = float(df['RSI'].iloc[-1])

            actual = float(df['Close'].iloc[-1])
            apertura = float(df['Open'].iloc) if not df.empty else actual
            
            vals[k] = {
                "actual": actual, 
                "apertura": apertura,
                "min": float(df['Low'].min()),
                "max": float(df['High'].max()),
                "vol_actual": float(df['Volume'].iloc[-1]) if 'Volume' in df.columns else 0.0,
                "vol_avg": float(df['Volume'].tail(20).mean()) if 'Volume' in df.columns else 0.0,
                "rsi": rsi_val,
                "prev_close": float(df['Close'].iloc[-2]) if len(df) > 1 else actual,
                "hist": df['Close']
            }
        except: 
            vals[k] = {"actual": 0.0, "apertura": 0.0, "min": 0.0, "max": 0.0, "vol_actual": 0.0, "vol_avg": 0.0, "rsi": 50.0, "prev_close": 0.0, "hist": pd.Series()}
    return vals

# --- INTERFAZ ---
st.title("🏛️ XSP 0DTE Institutional Terminal v4.1 (IBKR Optimized)")
st.caption("Calibrado para Interactive Brokers: Comisiones netas y Spreads Bid-Ask 2026")

with st.sidebar:
    st.header("Risk Engine (IBKR)")
    capital = st.number_input("Capital Cuenta (€)", value=10000.0, step=500.0)
    agresividad = st.select_slider("Multiplicador Sigma (Bias)", options=[1.1, 1.2, 1.3, 1.4, 1.5], value=1.3)
    btn_analizar = st.button("🚀 INICIAR ESCANEO IBKR")

if btn_analizar:
    with st.spinner("Sincronizando con flujo de Interactive Brokers..."):
        noticias = check_noticias_tactico(FINNHUB_API_KEY)
        d = obtener_datos()
        ahora = datetime.now(ZONA_HORARIA).time()

    if d["XSP"]["actual"] == 0:
        st.error("Error de datos. ¿Está el mercado abierto?")
        st.stop()

    # --- VARIABLES ---
    xsp, ndx, spy = d["XSP"], d["NDX"], d["SPY"]
    vix, vix1d, vvix = d["VIX"]["actual"], d["VIX1D"]["actual"], d["VVIX"]["actual"]
    vix_ref = vix1d if vix1d > 0 else (vix if vix > 0 else 15.0)
    
    rango_pct = abs((xsp["actual"] - xsp["apertura"]) / xsp["apertura"] * 100) if xsp["apertura"] != 0 else 0.0
    gap_ap = ((xsp["apertura"] - xsp["prev_close"]) / xsp["prev_close"] * 100) if xsp["prev_close"] != 0 else 0.0
    std_reciente = xsp["hist"].tail(15).std()
    regime = "EXPANSIÓN 📈" if std_reciente > xsp["hist"].std() else "COMPRESIÓN 📉"
    vix_invertido = d["VIX9D"]["actual"] > vix
    vol_ratio = spy["vol_actual"] / spy["vol_avg"] if spy["vol_avg"] > 0 else 0.0
    bonos_subiendo = d["TNX"]["actual"] > d["TNX"]["prev_close"]

    # --- DASHBOARD ---
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("XSP Actual", f"{xsp['actual']:.2f}")
        st.write(f"**Gap:** {gap_ap:+.2f}%")
    with c2:
        st.metric("Volumen SPY", f"{vol_ratio:.2f}x")
        st.write(f"**VVIX:** {vvix:.1f}")
    with c3:
        st.metric("VIX / VIX1D", f"{vix:.2f} / {vix1d:.2f}")
        st.write(f"**VIX Estructura:** {'⚠️ Invertida' if vix_invertido else '✅ Normal'}")
    with c4:
        st.metric("SKEW Index", f"{d['SKEW']['actual']:.2f}")
        st.write(f"**RSI:** {xsp['rsi']:.1f}")

    st.divider()

    # --- TABLA DE NIVELES IBKR ---
    if noticias["bloqueo"] or (vix_invertido and d["SKEW"]["actual"] > 148):
        st.error("### 🛑 BLOQUEO: Riesgo Crítico en 2026.")
    else:
        cond_ic = (regime == "COMPRESIÓN 📉" and vix < 19 and vol_ratio < 1.2 and rango_pct < 0.40)
        bias = (xsp["actual"] > xsp["apertura"])
        if bonos_subiendo: bias = False 
        
        sigma = (vix_ref / 100) / (252**0.5)
        lotes = max(1, int((capital * 0.02) // 200))
        
        st.subheader("⚡ Tabla de Niveles y Prima Neta (Estimada IBKR)")
        niveles = []
        for sig_mult in [1.1, 1.2, 1.3, 1.4, 1.5]:
            dist_t = xsp["actual"] * sigma * sig_mult
            pop = (norm.cdf(sig_mult) - norm.cdf(-sig_mult)) if cond_ic else norm.cdf(sig_mult)
            
            # CALIBRACIÓN IBKR: Factor 0.65 y resta de comisión (~1.5€ por spread)
            prima_est = ((1 - pop) * 200 * 0.65) - 1.50 
            prima_est = max(0, prima_est) # Evitar valores negativos
            
            label = f"Sigma {sig_mult}"
            if cond_ic:
                v_up, v_down = round(xsp["actual"] + dist_t), round(xsp["actual"] - dist_t)
                niveles.append({"Perfil": label, "POP": f"{pop*100:.1f}%", "Prima Neta Est.": f"{prima_est:.1f}€", "CALL (V/C)": f"{v_up}/{v_up+2}", "PUT (V/C)": f"{v_down}/{v_down-2}"})
            else:
                tipo = "BULL PUT" if bias else "BEAR CALL"
                v = round(xsp["actual"] - dist_t) if bias else round(xsp["actual"] + dist_t)
                c = v - 2 if bias else v + 2
                niveles.append({"Perfil": label, "POP": f"{pop*100:.1f}%", "Prima Neta Est.": f"{prima_est:.1f}€", "Estrategia": tipo, "Vender": v, "Comprar": c})
        
        st.table(pd.DataFrame(niveles))
        
        # --- RECOMENDACIÓN FINAL ---
        st.divider()
        dist_rec = xsp["actual"] * sigma * agresividad
        pop_rec = (norm.cdf(agresividad) - norm.cdf(-agresividad)) if cond_ic else norm.cdf(agresividad)
        
        if cond_ic:
            st.success(f"### 🎯 RECOMENDACIÓN ({agresividad}σ): IRON CONDOR | POP: {pop_rec*100:.1f}%")
        else:
            st.info(f"### 🎯 RECOMENDACIÓN ({agresividad}σ): {'BULL PUT' if bias else 'BEAR CALL'} | POP: {pop_rec*100:.1f}%")

        score = 0
        if vol_ratio > 1.3: score += 1
        if regime == "EXPANSIÓN 📈": score += 1
        if not bonos_subiendo: score += 1
        if (bias and xsp["rsi"] < 65) or (not bias and xsp["rsi"] > 35): score += 2
        
        conf_labels = ["EVITAR ❌", "MUY BAJA 📉", "BAJA ⚠️", "MEDIA 🟡", "ALTA ✅", "INSTITUCIONAL 🔥"]
        st.write(f"**Confianza:** {conf_labels[min(score, 5)]} | **Lotes IBKR:** {lotes}")

else:
    st.info("Terminal lista. Calibrado para Interactive Brokers.")
