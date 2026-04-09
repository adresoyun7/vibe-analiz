import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Pro Expert v4.1", layout="wide")

def style_engine(val):
    if val is None: return ''
    val_str = str(val)
    if 'Over' in val_str or 'Yes' in val_str or 'Home' in val_str or '1/' in val_str or '2/' in val_str: 
        return 'background-color: #27ae60; color: white;'
    if 'Under' in val_str or 'No' in val_str or 'Away' in val_str: 
        return 'background-color: #c0392b; color: white;'
    if 'Draw' in val_str or 'Tie' in val_str or 'X/' in val_str: 
        return 'background-color: #f39c12; color: white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi v4.1")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)

st.sidebar.markdown("---")
yillar = st.sidebar.multiselect("Sezonlar", options=['2122', '2223', '2324', '2425', '2526'], default=['2324', '2425', '2526'])
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=1)
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.00, 0.30, 0.08, step=0.01)

# --- VERİ MOTORLARI ---
@st.cache_data(ttl=86400)
def futbol_arsiv_yukle(sezonlar):
    ligler = {'E0':'EN1','E1':'EN2','SP1':'ES1','SP2':'ES2','D1':'DE1','D2':'DE2','I1':'IT1','I2':'IT2','F1':'FR1','F2':'FR2','T1':'TR1','N1':'NL1','B1':'BE1','P1':'PT1','SC0':'SC1','AUT':'AT1'}
    liste = []
    for k in ligler.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url, on_bad_lines='skip')
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC']
                df = df[df.columns.intersection(cols)]
                temp = df.dropna(subset=['B365H','B365D','B365A']).copy()
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()

def bulten_cek(key, t):
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
                    res.append({'ID': f"{tm.strftime('%H:%M')} | {m['home_team']} - {m['away_team']}", 'h': h, 'b': b, 'a': a, 'ev': m['home_team'], 'dep': m['away_team'], 'saat': tm.strftime('%H:%M')})
                except: continue
        return pd.DataFrame(res)
    except: return pd.DataFrame()

# --- ANA EKRAN ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY: st.error("API Key girin.")
    else:
        with st.spinner("📊 Veriler işleniyor..."):
            arsiv = futbol_arsiv_yukle(yillar)
            bulten = bulten_cek(API_KEY, secili_tarih)

        if not bulten.empty:
            for i, m in bulten.iterrows():
                b = arsiv[(arsiv['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (arsiv['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (arsiv['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))].copy()
                
                if len(b) >= min_ornek:
                    with st.expander(f"🔍 {m['ID']}"):
                        # Rakamları Hazırla
                        iy05 = (b['HTHG']+b['HTAG']>=1).mean(); ms25 = (b['FTHG']+b['FTAG']>=3).mean(); kg = ((b['FTHG']>0)&(b['FTAG']>0)).mean()
                        ms_m = b['FTR'].mode()[0]; iy_m = b['HTR'].mode()[0]

                        # 1. BÖLÜM: VİBE TAHMİN RAPORU (KART)
                        ana_t = "2.5 ÜST" if ms25 > 0.65 else "KG VAR" if kg > 0.6 else "MS " + ms_m.replace('H','1').replace('A','2').replace('D','X')
                        alt_t = f"MS {ms_m.replace('H','1').replace('A','2').replace('D','X')} & KG VAR" if kg > 0.55 else "MS 1 & 1.5 ÜST"
                        
                        st.markdown(f"""
                        <div style="background-color: #1e272e; padding: 15px; border-radius: 10px; border-left: 8px solid #27ae60; margin-bottom: 20px;">
                            <h4 style="color: white; margin-top: 0;">🎯 VİBE EXPERT RAPORU</h4>
                            <p style="color: white; margin: 5px 0;">🎯 <b>ANA TERCİH :</b> <span style="color: #27ae60;">{ana_t}</span></p>
                            <p style="color: white; margin: 5px 0;">🥈 <b>ALTERNATİF :</b> <span style="color: #f39c12;">{alt_t}</span></p>
                            {"<p style='color: #e74c3c; margin: 5px 0;'>📍 <b>CANLI :</b> İY 0.5 ÜST</p>" if iy05 > 0.75 else ""}
                        </div>
                        """, unsafe_allow_html=True)

                        # 2. BÖLÜM: GEÇMİŞ MAÇ DETAYLARI (TABLO)
                        st.subheader("📚 Geçmiş Maç Analizi")
                        dt = pd.DataFrame()
                        dt['Tarih'] = b['Date'].dt.strftime('%d.%m.%Y')
                        dt['Maç'] = b['HomeTeam'] + "-" + b['AwayTeam']
                        dt['İY'] = b['HTHG'].astype(int).astype(str)+"-"+b['HTAG'].astype(int).astype(str)
                        dt['MS'] = b['FTHG'].astype(int).astype(str)+"-"+b['FTAG'].astype(int).astype(str)
                        dt['1Y_05'] = (b['HTHG']+b['HTAG']>=1).map({True:'Over', False:'Under'})
                        dt['MS_25'] = (b['FTHG']+b['FTAG']>=3).map({True:'Over', False:'Under'})
                        dt['KG'] = ((b['FTHG']>0)&(b['FTAG']>0)).map({True:'Yes', False:'No'})
                        dt['Krn'] = (b.get('HC',0)+b.get('AC',0)).astype(int)
                        st.dataframe(dt.style.map(style_engine, subset=['1Y_05','MS_25','KG']), use_container_width=True, hide_index=True)

                        # 3. BÖLÜM: SÜRPRİZ & HT/FT RADARI (TABLO)
                        st.subheader("🔥 HT/FT & Sürpriz Radarı")
                        hf_df = pd.DataFrame()
                        hf_df['Tarih'] = b['Date'].dt.strftime('%d.%m.%Y')
                        hf_df['HT/FT'] = b['HTR'].replace({'H':'1','A':'2','D':'X'}) + "/" + b['FTR'].replace({'H':'1','A':'2','D':'X'})
                        
                        # Sürpriz Uyarıları (2/1 veya 1/2 %10 üzerindeyse)
                        surpriz_oran = ((b['HTR']=='H')&(b['FTR']=='A')|(b['HTR']=='A')&(b['FTR']=='H')).mean()
                        if surpriz_oran >= 0.10:
                            st.warning(f"⚠️ DİKKAT: Bu oran eşleşmesinde %{int(surpriz_oran*100)} oranında 1/2 veya 2/1 sürprizi saptandı!")
                        
                        st.dataframe(hf_df.style.map(style_engine, subset=['HT/FT']), use_container_width=True, hide_index=True)
        else: st.warning("Seçilen tarihte maç bulunamadı.")
