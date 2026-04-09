import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Pro Ultra v3.0", layout="wide")

def style_engine(val):
    if val is None: return ''
    val_str = str(val)
    if 'Over' in val_str or 'Yes' in val_str or 'Home' in val_str or '🔥' in val_str: return 'background-color: #27ae60; color: white;'
    if 'Under' in val_str or 'No' in val_str or 'Away' in val_str: return 'background-color: #c0392b; color: white;'
    if 'Draw' in val_str or 'Tie' in val_str: return 'background-color: #f39c12; color: white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi v3.0")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Arşiv Ayarları")
yillar = st.sidebar.multiselect("Sezonlar", options=['2122', '2223', '2324', '2425', '2526'], default=['2324', '2425', '2526'])
TOLERANS = st.sidebar.slider("Hassasiyet", 0.00, 0.30, 0.08, step=0.01)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_arsiv_motoru(sezonlar):
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT'}
    liste = []
    for k, v in lig_map.items():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url, on_bad_lines='skip')
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A']
                df = df[df.columns.intersection(cols)]
                temp = df.dropna(subset=['B365H','B365D','B365A']).copy()
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()

def bulten_cek_hibrit(key, t):
    url = f'https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={key}&regions=eu&markets=h2h'
    try:
        r = requests.get(url, timeout=20)
        data = r.json()
        res = []
        for m in data:
            tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
            if tm.date() == t:
                bookies = m.get('bookmakers', [])
                if not bookies: continue
                o = bookies[0]['markets'][0]['outcomes']
                try:
                    h = next(x['price'] for x in o if x['name'] == m['home_team'])
                    a = next(x['price'] for x in o if x['name'] == m['away_team'])
                    b = next(x['price'] for x in o if x['name'].lower() in ['draw', 'tie', 'beraberlik'])
                    res.append({'ID': f"{tm.strftime('%H:%M')} | {m['home_team']} - {m['away_team']}", 'h': h, 'b': b, 'a': a, 'ev': m['home_team'], 'dep': m['away_team']})
                except: continue
        return pd.DataFrame(res)
    except: return pd.DataFrame()

# --- ANALİZ EKRANI ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY: st.error("API Key girin.")
    else:
        with st.spinner("📊 Bülten ve Arşiv taranıyor..."):
            arsiv = futbol_arsiv_motoru(yillar)
            bulten = bulten_cek_hibrit(API_KEY, secili_tarih)

        if not bulten.empty:
            for i, m in bulten.iterrows():
                b = arsiv[(arsiv['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (arsiv['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (arsiv['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))].copy()
                
                if len(b) >= 1:
                    with st.expander(f"🔍 {m['ID']}"):
                        # İstatistikler
                        iy05 = (b['HTHG']+b['HTAG']>=1).mean()
                        ms15 = (b['FTHG']+b['FTAG']>=2).mean()
                        ms25 = (b['FTHG']+b['FTAG']>=3).mean()
                        kg = ((b['FTHG']>0)&(b['FTAG']>0)).mean()
                        ms_vibe = b['FTR'].mode()[0]
                        
                        # --- TERCİH MOTORU (Senin İstediğin Kısım) ---
                        ana_tercih = "Bülten Bekleniyor"
                        alt_tercih = "Riskli"
                        canli_tercih = "İY 0.5 ÜST" if iy05 > 0.7 else "Beklemede"

                        # Ana Tercih Mantığı
                        if ms_vibe == 'H' and (b['FTR'] == 'H').mean() > 0.6: ana_tercih = "MS 1"
                        elif ms_vibe == 'A' and (b['FTR'] == 'A').mean() > 0.6: ana_tercih = "MS 2"
                        elif ms25 > 0.7: ana_tercih = "2.5 ÜST"
                        else: ana_tercih = "KG VAR" if kg > 0.6 else "MS 1.5 ÜST"

                        # Alternatif Tercih Mantığı
                        if kg > 0.75: alt_tercih = "KG VAR"
                        elif ms15 > 0.85: alt_tercih = "1.5 ÜST"
                        else: alt_tercih = "Çifte Şans"

                        # GÖRSEL KART TASARIMI
                        st.markdown(f"""
                        <div style="background-color: #1e272e; padding: 20px; border-radius: 10px; border-left: 5px solid #27ae60;">
                            <h3 style="color: white; margin-bottom: 10px;">🎯 VİBE TAHMİN RAPORU</h3>
                            <p style="font-size: 18px;">🎯 <b>ANA TERCİH :</b> <span style="color: #27ae60;">{ana_tercih}</span></p>
                            <p style="font-size: 18px;">🥈 <b>ALTERNATİF :</b> <span style="color: #f39c12;">{alt_tercih}</span></p>
                            <p style="font-size: 18px;">📍 <b>CANLI TERCİH :</b> <span style="color: #e74c3c;">{canli_tercih}</span></p>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        st.write(f"📊 **İstatistikler:** İY 0.5: %{int(iy05*100)} | MS 2.5: %{int(ms25*100)} | KG: %{int(kg*100)} | Örnek: {len(b)}")
                        st.dataframe(b[['Date','HomeTeam','AwayTeam','FTHG','FTAG','FTR']].head(10), use_container_width=True)
        else: st.warning("Maç bulunamadı.")
