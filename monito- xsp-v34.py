import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, time, date
import requests
import pytz

# --- CONFIGURACIÓN ---
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'
ZONA_HORARIA = pytz.timezone('Europe/Madrid')

st.set_page_config(page_title="Monitor Táctico XSP 0DTE Ultra Pro", layout="wide")

# --- FUNCIONES DE LÓGICA ---
def check_noticias_tactico(api_key):
    eventos_prohibidos = ["CPI", "FED", "FOMC", "NFP", "POWELL", "PPI", "INTEREST RATE", "JOBLESS"]
    hoy = str(date.today())
    # URL corregida para 2026
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
    # Tickers: XSP (Mini S&P), VIX (Volatilidad), NDX (Nasdaq), SPY (Volumen), SKEW (Riesgo Cisne Negro)
    tickers = {
        "XSP": "^XSP", "VIX": "^VIX", "VIX9D": "^VIX9D", 
        "VVIX": "^VVIX", "VIX1D": "^VIX1D", "NDX": "^NDX", 
        "SPY": "SPY", "SKEW": "^SKEW"
    }
    vals = {}
    for k, v in tickers.items():
        try:
            df = yf.Ticker(v).history(period="1d", interval="1m")
            if df.empty: # Fallback si no hay datos de 1m
                df = yf.Ticker(v).history(period="2d", interval="1h")
            
            if not df.empty:
                vals[k] = {
                    "actual": df['Close'].iloc[-1], 
                    "apertura": df['Open'].iloc[0],
                    "min": df['Low'].min(),
                    "max": df['High'].max(),
                    "vol_actual": df['Volume'].iloc[-1] if 'Volume' in df.columns else 0,
                    "vol_avg": df['Volume'].tail(20).mean() if 'Volume' in df.columns else 0,
                    "change": (df['Close'].iloc[-1] - df['Close'].iloc[-2]) if len(df) > 1 else 0
                }
            else:
                vals[k] = {"actual": 0, "apertura": 0, "min": 0, "max": 0, "vol_actual": 0, "vol_avg": 0, "change": 0}
        except:
            vals[k] = {"actual": 0, "apertura": 0, "min": 0, "max": 0, "vol_actual": 0, "vol_avg": 0, "change": 0}
    return vals

def calcular_niveles(precio, vix_ref, delta_target):
    sigma_1d = (vix_ref / 100) / (252**0.5)
    mult = 1.15 if delta_target == 5 else 1.30
    dist = precio * sigma_1d * mult
    ancho = 2 
    v_up, v_down = round(precio + dist), round(precio - dist)
    return {"v_up": v_up, "c_up": v_up + ancho, "v_down": v_down, "c_down": v_down - ancho, "ancho": ancho}

# --- INTERFAZ STREAMLIT ---
st.title("🎯 Monitor XSP 0DTE Institucional (SMT + Flujo de Opciones)")

with st.sidebar:
    st.header("Configuración de Cuenta")
    capital = st.number_input("Capital de la cuenta (€)", min_value=0.0, value=10000.0, step=500.0)
    btn_analizar = st.button("🔄 EJECUTAR ANÁLISIS COMPLETO")

if btn_analizar:
    with st.spinner("Analizando Flujo de Opciones, SMT y Riesgo Sistémico..."):
        noticias = check_noticias_tactico(FINNHUB_API_KEY)
        d = obtener_datos()

    if d["XSP"]["actual"] == 0:
        st.error("No se pudieron obtener datos. Mercado cerrado o error de API.")
        st.stop()

    # --- VARIABLES CLAVE ---
    xsp, vix, vvix = d["XSP"]["actual"], d["VIX"]["actual"], d["VVIX"]["actual"]
    ndx, spy, skew = d["NDX"]["actual"], d["SPY"]["actual"], d["SKEW"]["actual"]
    vix1d = d["VIX1D"]["actual"] if d["VIX1D"]["actual"] > 0 else (vix if vix > 0 else 15)
    
    # 1. Ratio VIX/VIX9D (Estructura temporal)
    vix_invertido = d["VIX9D"]["actual"] > d["VIX"]["actual"]
    
    # 2. Volumen Institucional SPY
    vol_ratio = d["SPY"]["vol_actual"] / d["SPY"]["vol_avg"] if d["SPY"]["vol_avg"] > 0 else 0
    confirmacion_vol = vol_ratio > 1.3

    # 3. Divergencia SMT (NDX vs XSP)
    smt_alcista = (ndx < d["NDX"]["min"] * 1.001) and (xsp > d["XSP"]["min"] * 1.003)
    smt_bajista = (ndx > d["NDX"]["max"] * 0.999) and (xsp < d["XSP"]["max"] * 0.997)

    # 4. GEX y EM
    move_pts = xsp * (vix1d / 100) / (252**0.5)
    em_up, em_down = xsp + move_pts, xsp - move_pts
    gamma_flip = round(xsp * (1 - (vix/1000)))
    gex_status = "POSITIVO 🟢" if xsp > gamma_flip else "NEGATIVO 🔴"

    # --- DISEÑO DE DASHBOARD ---
    col1, col2, col3 = st.columns(3)

    with col1:
        st.subheader("📊 Precio y SMT")
        st.metric("XSP Actual", f"{xsp:.2f}")
        st.write(f"**Divergencia SMT:** {'ALCISTA 🟢' if smt_alcista else 'BAJISTA 🔴' if smt_bajista else 'Neutral'}")
        st.write(f"**Volumen SPY:** {vol_ratio:.2f}x")

    with col2:
        st.subheader("📉 Volatilidad y GEX")
        st.metric("VIX / VIX1D", f"{vix:.2f} / {vix1d:.2f}")
        st.write(f"**Estructura VIX:** {'INVERTIDA ⚠️' if vix_invertido else 'Normal ✅'}")
        st.write(f"**Status GEX:** {gex_status}")

    with col3:
        st.subheader("🔔 Riesgo y Noticias")
        st.metric("SKEW Index", f"{skew:.2f}")
        if noticias["eventos"]:
            for ev in noticias["eventos"]: st.warning(ev)
        else: st.success("Sin noticias de alto impacto")

    # --- LÓGICA ESTRATÉGICA MEJORADA ---
    st.divider()
    st.subheader("⚡ Estrategia Recomendada")

    # Bloqueo total por pánico
    if vix_invertido and skew > 145:
        st.error("### 🛑 BLOQUEO DE SEGURIDAD: Pánico detectado (VIX Invertido + Skew Alto). No vender Puts.")
    elif noticias["bloqueo"]:
        st.error("🛑 BLOQUEO POR NOTICIA: No operar en este horario.")
    elif vvix > 120:
        st.warning("### ⚠️ RIESGO EXTREMO: Volatilidad del VIX muy alta. Reducir lotaje.")
    else:
        # Definición de Sesgo
        alcista = (xsp > d["XSP"]["apertura"])
        if smt_alcista: alcista = True
        if smt_bajista or vix_invertido: alcista = False # El riesgo sistémico prioriza el lado bajista
        
        # Selección de Tramos
        c_ic = vix1d < d["VIX9D"]["actual"] < vix and vix < 18 and vvix < 95
        
        if c_ic:
            n = calcular_niveles(xsp, vix1d, 5)
            lotes = max(1, int((capital * 0.02) // (n["ancho"] * 100)))
            st.success(f"### 🎯 ESTRATEGIA: IRON CONDOR (Neutral)")
            st.write(f"**Vender CALL:** {n['v_up']} | **Vender PUT:** {n['v_down']}")
            st.write(f"**Lotes:** {lotes} | **Confianza:** Media (Baja Volatilidad)")
        else:
            n = calcular_niveles(xsp, vix1d, 3)
            lotes = max(1, int((capital * 0.02) // (n["ancho"] * 100)))
            tipo = "BULL PUT (Alcista)" if alcista else "BEAR CALL (Bajista)"
            v, c = (n["v_down"], n["c_down"]) if alcista else (n["v_up"], n["c_up"])
            
            # Puntuación de Confianza
            score = 0
            if confirmacion_vol: score += 1
            if (alcista and smt_alcista) or (not alcista and smt_bajista): score += 1
            if not vix_invertido: score += 1
            
            conf_text = "ALTA ✅" if score >= 2 else "BAJA ⚠️"
            
            st.info(f"### 🎯 ESTRATEGIA: {tipo}")
            st.write(f"**Vender:** {v} / **Comprar:** {c}")
            st.write(f"**Confianza Institucional:** {conf_text} (Basada en SMT, Volumen y VIX)")
            st.write(f"**Operativa:** {lotes} Contrato(s) | **EM (1 SD):** {em_down:.2f} - {em_up:.2f}")

else:
    st.info("Introduce el capital y ejecuta el análisis para recibir la recomendación institucional.")
