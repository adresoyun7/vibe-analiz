import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

def style_engine(val):
    if val is None: return ''
    val_str = str(val)
    if 'Over' in val_str or 'Yes' in val_str or 'Home' in val_str: return 'background-color: #27ae60; color: white;'
    if 'Under' in val_str or 'No' in val_str or 'Away' in val_str: return 'background-color: #c0392b; color: white;'
    if 'Draw' in val_str or 'Tie' in val_str: return 'background-color: #f39c12; color: white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Veri Havuzu")
yillar = st.sidebar.multiselect("Sezonlar", options=['2122','2223','2324','2425','2526'], default=['2324','2425','2526'])
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=1)
TOLERANS = st.sidebar.slider("Hassasiyet (0.00=Birebir)", 0.00, 0.30, 0.05, step=0.01)

# --- NESİNE FULL PAKET LİGLER ---
FUTBOL_LIGLERI = {
    "🏆 MAJÖR & TR": {'Süper Lig': 'soccer_turkey_super_league', 'TR 1. Lig': 'soccer_turkey_pTT_1_lig', 'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'İtalya': 'soccer_italy_serie_a', 'Fransa': 'soccer_france_ligue_one'},
    "⚽ AVRUPA (GOLCÜ)": {'Hollanda': 'soccer_netherlands_eredivisie', 'Hollanda 2': 'soccer_netherlands_erste_divisie', 'Belçika': 'soccer_belgium_first_division', 'Portekiz': 'soccer_portugal_primeira_liga', 'Avusturya': 'soccer_austria_bundesliga', 'İskoçya': 'soccer_scotland_premiership', 'İsviçre': 'soccer_switzerland_superleague'},
    "🌍 DİĞER": {'Brezilya': 'soccer_brazil_campeonato_serie_a', 'Arjantin': 'soccer_argentina_primera_division', 'Japonya': 'soccer_japan_j_league', 'ABD MLS': 'soccer_usa_mls', 'Meksika': 'soccer_mexico_liga_mx'}
}

secili_kodlar = []
for kat, ligler in FUTBOL_LIGLERI.items():
    with st.sidebar.expander(kat):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"): secili_kodlar.append(kod)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru(sezonlar):
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT'}
    liste = []
    for k, v in lig_map.items():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
                df = df[df.columns.intersection(cols)]
                temp = df.dropna(subset=['B365H','B365D','B365A']).copy()
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()

# --- KOTA DOSTU BÜLTEN ÇEKİCİ ---
def bulten_cek_optimized(key, t):
    # Tüm futbol maçlarını TEK SEFERDE çekiyoruz (Kota tasarrufu!)
    url = f'https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={key}&regions=eu&markets=h2h'
    try:
        r = requests.get(url, timeout=15)
        if r.status_code != 200: return pd.DataFrame()
        data = r.json()
        res = []
        for m in data:
            tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
            if tm.date() == t:
                bookies = m.get('bookmakers', [])
                if not bookies: continue
                o = bookies[0]['markets'][0]['outcomes']
                h = next((x['price'] for x in o if x['name'] == m['home_team']), 0)
                a = next((x['price'] for x in o if x['name'] == m['away_team']), 0)
                b = next((x['price'] for x in o if x['name'].lower() in ['draw', 'tie']), 0)
                res.append({'key': m['sport_key'], 'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        return pd.DataFrame(res)
    except: return pd.DataFrame()

# --- ANA PROGRAM ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ Key ve Lig seçin.")
    else:
        with st.spinner("📊 Analiz ediliyor..."):
            gecmis = futbol_veri_motoru(yillar)
            # Sadece seçili ligleri içeren bülteni tek istekte filtreliyoruz
            tum_bulten = bulten_cek_optimized(API_KEY, secili_tarih)
            if not tum_bulten.empty:
                bulten = tum_bulten[tum_bulten['key'].isin(secili_kodlar)]
            else: bulten = pd.DataFrame()

        if bulten.empty:
            st.warning("ℹ️ Seçili liglerde veya tarihte maç bulunamadı.")
        else:
            final_list, flips = [], []
            for i, m in bulten.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))].copy()
                if len(b) >= min_ornek:
                    b['FTHG'] = b['FTHG'].fillna(0); b['FTAG'] = b['FTAG'].fillna(0)
                    b['HTHG'] = b['HTHG'].fillna(0); b['HTAG'] = b['HTAG'].fillna(0)
                    
                    # Yüzdeler
                    iy05 = (b['HTHG']+b['HTAG']>=1).mean(); iy15 = (b['HTHG']+b['HTAG']>=2).mean()
                    ms15 = (b['FTHG']+b['FTAG']>=2).mean(); ms25 = (b['FTHG']+b['FTAG']>=3).mean(); ms35 = (b['FTHG']+b['FTAG']>=4).mean()
                    kg = ((b['FTHG']>0)&(b['FTAG']>0)).mean()
                    
                    iy_mod = b['HTR'].mode()[0]; ms_mod = b['FTR'].mode()[0]
                    iy_p = b['HTR'].value_counts(normalize=True).get(iy_mod,0); ms_p = b['FTR'].value_counts(normalize=True).get(ms_mod,0)

                    final_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'EV': m['ev'], 'DEP': m['dep'],
                        '1Y_05': f"{'Over' if iy05>=0.5 else 'Under'} ({int(iy05*100)}%){'🔥' if iy05>=0.8 else ''}",
                        'İY_15': f"{'Over' if iy15>=0.5 else 'Under'} ({int(iy15*100)}%){'🔥' if iy15>=0.8 else ''}",
                        'MS_15': f"{'Over' if ms15>=0.5 else 'Under'} ({int(ms15*100)}%){'🔥' if ms15>=0.8 else ''}",
                        'MS_25': f"{'Over' if ms25>=0.5 else 'Under'} ({int(ms25*100)}%){'🔥' if ms25>=0.8 else ''}",
                        'MS_35': f"{'Over' if ms35>=0.5 else 'Under'} ({int(ms35*100)}%){'🔥' if ms35>=0.8 else ''}",
                        'KG': f"{'Yes' if kg>=0.5 else 'No'} ({int(kg*100)}%){'🔥' if kg>=0.8 else ''}",
                        '1Y_SKOR': (b['HTHG'].astype(int).astype(str)+"-"+b['HTAG'].astype(int).astype(str)).mode()[0],
                        'MS_SKOR': (b['FTHG'].astype(int).astype(str)+"-"+b['FTAG'].astype(int).astype(str)).mode()[0],
                        '1Y_V': f"{iy_mod.replace('H','Home').replace('A','Away').replace('D','Draw')} ({int(iy_p*100)}%){'🔥' if iy_p>=0.6 else ''}",
                        'MS_V': f"{ms_mod.replace('H','Home').replace('A','Away').replace('D','Draw')} ({int(ms_p*100)}%){'🔥' if ms_p>=0.6 else ''}",
                        'ÖRNEK': len(b), 'idx': i
                    })
                    if ((b['HTR']=='H')&(b['FTR']=='A')|(b['HTR']=='A')&(b['FTR']=='H')).any():
                        flips.append({'m': f"{m['ev']}-{m['dep']}", 'p': int(((b['HTR']=='H')&(b['FTR']=='A')|(b['HTR']=='A')&(b['FTR']=='H')).mean()*100)})

            if final_list:
                df_ana = pd.DataFrame(final_list)
                st.subheader(f"⚽ {secili_tarih} Vibe Analiz")
                st.dataframe(df_ana.drop(columns=['idx']).style.map(style_engine, subset=['1Y_05','İY_15','MS_15','MS_25','MS_35','KG','1Y_V','MS_V']), use_container_width=True)
                # ... (Expander ve Radar kısımları aynı mantıkla eklenebilir)
