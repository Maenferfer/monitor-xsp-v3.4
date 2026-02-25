import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, time, date
import requests
import pytz

# --- CONFIGURACIÓN ---
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'
ZONA_HORARIA = pytz.timezone('Europe/Madrid')

st.set_page_config(page_title="Monitor XSP 0DTE Total Alpha", layout="wide")

def obtener_datos():
    # Añadimos ^TNX (Bonos 10Y) y ^VIX1D para precisión extrema
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
            vals[k] = {
                "actual": df['Close'].iloc[-1], 
                "apertura": df['Open'].iloc[0],
                "min": df['Low'].min(),
                "max": df['High'].max(),
                "vol_actual": df['Volume'].iloc[-1] if 'Volume' in df.columns else 0,
                "vol_avg": df['Volume'].tail(20).mean() if 'Volume' in df.columns else 0,
                "prev_close": df['Close'].iloc[-2] if len(df) > 1 else df['Close'].iloc[-1]
            }
        except: vals[k] = {"actual": 0, "apertura": 0, "min": 0, "max": 0, "vol_actual": 0, "vol_avg": 0}
    return vals

st.title("🚀 XSP 0DTE: Total Alpha Monitor (Edición 2026)")

with st.sidebar:
    st.header("Gestión de Riesgo")
    capital = st.number_input("Capital Total (€)", value=10000.0)
    riesgo_per_trade = st.slider("Riesgo por operación (%)", 0.5, 5.0, 2.0)
    btn = st.button("🔥 ESCANEAR MERCADO")

if btn:
    d = obtener_datos()
    ahora_es = datetime.now(ZONA_HORARIA).time()
    
    # 1. Filtro de Tiempo (Hora Dorada)
    es_hora_peligrosa = ahora_es < time(16, 0) or ahora_es > time(21, 0)
    
    # 2. Análisis de Bonos (TNX)
    bonos_subiendo = d["TNX"]["actual"] > d["TNX"]["prev_close"]
    
    # 3. Flujo Institucional (SPY Vol + SMT)
    vol_ratio = d["SPY"]["vol_actual"] / d["SPY"]["vol_avg"] if d["SPY"]["vol_avg"] > 0 else 0
    smt_confirmado = (d["XSP"]["actual"] > d["XSP"]["min"]*1.002) and (d["NDX"]["actual"] > d["NDX"]["min"]*1.002)
    
    # 4. Estructura de Volatilidad
    vix_invertido = d["VIX9D"]["actual"] > d["VIX"]["actual"]
    
    # --- DASHBOARD ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("XSP Actual", f"{d['XSP']['actual']:.2f}")
        st.write(f"**SMT:** {'🟢 OK' if smt_confirmado else '🔴 No Confluencia'}")
    with col2:
        st.metric("Bonos 10Y (TNX)", f"{d['TNX']['actual']:.2f}%")
        st.write(f"**Presión Bonos:** {'⚠️ Bajista p/ Acciones' if bonos_subiendo else '✅ Neutral/Favor'}")
    with col3:
        st.metric("VIX / VIX1D", f"{d['VIX']['actual']:.2f} / {d['VIX1D']['actual']:.2f}")
        st.write(f"**Estructura:** {'⚠️ Invertida' if vix_invertido else '✅ Normal'}")
    with col4:
        st.metric("SKEW (Riesgo Cola)", f"{d['SKEW']['actual']:.2f}")
        st.write(f"**Estado:** {'🔥 Peligro' if d['SKEW']['actual'] > 145 else '✅ Estable'}")

    st.divider()

    # --- LÓGICA DE DECISIÓN ALPHA ---
    st.subheader("⚡ Recomendación Estratégica")

    # Reglas de bloqueo 2026
    if es_hora_peligrosa:
        st.warning("⚠️ **ATENCIÓN:** Estás fuera de la 'Ventana de Oro' (16:00 - 21:00 ES). La volatilidad es errática.")
    
    if vix_invertido or d["SKEW"]["actual"] > 150:
        st.error("### 🛑 ESTRATEGIA: NO TRADE (Pánico Sistémico Detectado)")
    else:
        # Definición del Sesgo (Bias)
        bias_alcista = (d["XSP"]["actual"] > d["XSP"]["apertura"]) and not bonos_subiendo
        
        # Cálculo de Niveles Dinámicos
        vix_ref = d["VIX1D"]["actual"] if d["VIX1D"]["actual"] > 0 else 15
        sigma = (vix_ref / 100) / (252**0.5)
        
        # Ajuste de desviación según volumen
        mult = 1.4 if vol_ratio > 1.5 else 1.2
        dist = d["XSP"]["actual"] * sigma * mult
        
        tipo = "BULL PUT SPREAD" if bias_alcista else "BEAR CALL SPREAD"
        vend = round(d["XSP"]["actual"] - dist) if bias_alcista else round(d["XSP"]["actual"] + dist)
        comp = vend - 2 if bias_alcista else vend + 2
        
        # Gestión de Lotes Profesional
        riesgo_euros = capital * (riesgo_per_trade / 100)
        lotes = max(1, int(riesgo_euros // 200)) # 200€ estimado de margen por spread de 2 pts
        
        st.success(f"### 🎯 OPERACIÓN: {tipo}")
        st.write(f"**Vender:** {vend} | **Comprar:** {comp} (Spread 2 pts)")
        
        # Puntuación de Confianza Final
        score = 0
        if smt_confirmado: score += 1
        if not bonos_subiendo: score += 1
        if vol_ratio > 1.2: score += 1
        if not es_hora_peligrosa: score += 1
        
        conf_map = {0: "Mínima ❌", 1: "Baja ⚠️", 2: "Media 🟡", 3: "Alta ✅", 4: "INSTITUCIONAL 🔥"}
        st.write(f"**Nivel de Confianza:** {conf_map.get(score)}")
        st.info(f"**Sugerencia:** Operar con {lotes} contratos para mantener riesgo del {riesgo_per_trade}%")

else:
    st.info("Esperando escaneo de flujo de órdenes 2026...")
