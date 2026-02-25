import streamlit as st
import yfinance as yf
import pandas as pd
from datetime import datetime, time, date
import requests
import pytz

# --- CONFIGURACIÓN ---
FINNHUB_API_KEY = 'd6d2nn1r01qgk7mkblh0d6d2nn1r01qgk7mkblhg'
ZONA_HORARIA = pytz.timezone('Europe/Madrid')

st.set_page_config(page_title="Monitor Táctico XSP 0DTE", layout="wide")

# --- FUNCIONES DE LÓGICA ---
def check_noticias_tactico(api_key):
    eventos_prohibidos = ["CPI", "FED", "FOMC", "NFP", "POWELL", "PPI", "INTEREST RATE", "JOBLESS"]
    hoy = str(date.today())
    url = f"https://finnhub.io{hoy}&to={hoy}&token={api_key}"
    estado = {"bloqueo": False, "tipo": "NORMAL", "eventos": []}
    try:
        r = requests.get(url).json().get('economicCalendar', [])
        for ev in r:
            if ev['country'] == 'US' and ev['impact'] == 'high':
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
    # Añadido ^NDX para Divergencia SMT
    tickers = {"XSP": "^XSP", "VIX": "^VIX", "VIX9D": "^VIX9D", "VVIX": "^VVIX", "VIX1D": "^VIX1D", "NDX": "^NDX"}
    vals = {}
    for k, v in tickers.items():
        try:
            df = yf.Ticker(v).history(period="1d", interval="1m")
            if not df.empty:
                vals[k] = {
                    "actual": df['Close'].iloc[-1], 
                    "apertura": df['Open'].iloc[0],
                    "min": df['Low'].min(),
                    "max": df['High'].max()
                }
            else:
                vals[k] = {"actual": 0, "apertura": 0, "min": 0, "max": 0}
        except:
            vals[k] = {"actual": 0, "apertura": 0, "min": 0, "max": 0}
    return vals

def calcular_niveles(precio, vix_ref, delta_target):
    sigma_1d = (vix_ref / 100) / (252**0.5)
    mult = 1.15 if delta_target == 5 else 1.30
    dist = precio * sigma_1d * mult
    ancho = 2 
    v_up, v_down = round(precio + dist), round(precio - dist)
    return {"v_up": v_up, "c_up": v_up + ancho, "v_down": v_down, "c_down": v_down - ancho, "ancho": ancho}

# --- INTERFAZ STREAMLIT ---
st.title("🎯 Monitor Táctico Profesional XSP 0DTE")

with st.sidebar:
    st.header("Configuración de Cuenta")
    capital = st.number_input("Capital de la cuenta (€)", min_value=0.0, value=10000.0, step=500.0)
    btn_analizar = st.button("🔄 Ejecutar Análisis")

if btn_analizar:
    with st.spinner("Analizando mercado y noticias..."):
        noticias = check_noticias_tactico(FINNHUB_API_KEY)
        d = obtener_datos()

    xsp, vix, vvix = d["XSP"]["actual"], d["VIX"]["actual"], d["VVIX"]["actual"]
    ndx = d["NDX"]["actual"]
    vix1d = d["VIX1D"]["actual"] if d["VIX1D"]["actual"] > 0 else vix
    rango = abs((xsp - d["XSP"]["apertura"]) / d["XSP"]["apertura"] * 100) if d["XSP"]["apertura"] != 0 else 0

    # Lógica SMT (Divergencia Smart Money)
    # Comparamos si uno rompió el máximo/mínimo del día y el otro no
    smt_alcista = (ndx < d["NDX"]["min"] * 1.001) and (xsp > d["XSP"]["min"] * 1.005)
    smt_bajista = (ndx > d["NDX"]["max"] * 0.999) and (xsp < d["XSP"]["max"] * 0.995)

    # Cálculos Técnicos
    move_pts = xsp * (vix1d / 100) / (252**0.5)
    em_up, em_down = xsp + move_pts, xsp - move_pts
    call_wall, put_wall = round(em_up * 1.005), round(em_down * 0.995)
    gamma_flip = round(xsp * (1 - (vix/1000)))
    zero_gex = round(xsp - (move_pts * 0.5))
    gex_status = "POSITIVO (Estabilidad)" if xsp > gamma_flip else "NEGATIVO (Volatilidad)"

    # --- DISEÑO DE COLUMNAS ---
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📊 Datos de Mercado")
        metrics = {
            "XSP Actual": f"{xsp:.2f} ({rango:.2f}%)",
            "VIX1D / VVIX": f"{vix1d:.2f} / {vvix:.2f}",
            "Gamma Flip": gamma_flip,
            "Status GEX": gex_status,
            "Rango EM (1 SD)": f"{em_down:.2f} - {em_up:.2f}",
            "Divergencia SMT": "ALCISTA 🟢" if smt_alcista else "BAJISTA 🔴" if smt_bajista else "Neutral"
        }
        st.table(pd.DataFrame(metrics.items(), columns=["Métrica", "Valor"]))

    with col2:
        st.subheader("🔔 Noticias e Impacto")
        if noticias["eventos"]:
            for ev in noticias["eventos"]:
                st.warning(f"• {ev}")
        else:
            st.success("No hay noticias de alto impacto detectadas.")
        
        if noticias["bloqueo"]:
            st.error("🛑 BLOQUEO TOTAL: Noticia crítica en horario. NO OPERAR.")
            st.stop()

    # --- ESTRATEGIA ---
    st.divider()
    st.subheader("⚡ Estrategia Recomendada")

    c1, c2, c3, c4 = vix1d < d["VIX9D"]["actual"] < vix, vix < 18, vvix < 95, rango < 0.45
    
    if vvix > 125:
        st.error("### ⚠️ NO OPERAR: Riesgo Extremo (VVIX alto)")
    
    elif noticias["tipo"] == "TARDE_FED" or (c1 and c2 and c3 and c4):
        n = calcular_niveles(xsp, vix1d, 5)
        lotes = max(1, int((capital * 0.02) // (n["ancho"] * 100)))
        
        st.success(f"### 🎯 TRAMO 1: IRON CONDOR (Agresivo)")
        st.write(f"**CALL:** Vend {n['v_up']} / Comp {n['c_up']} | **PUT:** Vend {n['v_down']} / Comp {n['c_down']}")
        st.info(f"**Operativa:** {lotes} Contrato(s) | **Spread:** {n['ancho']} pts")
        
    else:
        n = calcular_niveles(xsp, vix1d, 3)
        lotes = max(1, int((capital * 0.02) // (n["ancho"] * 100)))
        
        # Lógica Profesional Integrada: Precio + SMT
        alcista = xsp > d["XSP"]["apertura"]
        if smt_alcista: alcista = True # SMT manda sobre el precio
        if smt_bajista: alcista = False # SMT manda sobre el precio
        
        tipo = "BULL PUT (Alcista)" if alcista else "BEAR CALL (Bajista)"
        # Si hay divergencia SMT, aumentamos la confianza
        calidad = "ALTA (Confirmación SMT)" if (smt_alcista and alcista) or (smt_bajista and not alcista) else "NORMAL"
        
        v, c = (n["v_down"], n["c_down"]) if alcista else (n["v_up"], n["c_up"])
        
        st.info(f"### 🎯 TRAMO 2: SPREAD VERTICAL ({tipo})")
        st.write(f"**Confianza:** {calidad}")
        st.write(f"**Vender:** {v} / **Comprar:** {c}")
        st.write(f"**Operativa:** {lotes} Contrato(s) | **Spread:** {n['ancho']} pts")

else:
    st.info("Introduce el capital y pulsa 'Ejecutar Análisis' para empezar.")
