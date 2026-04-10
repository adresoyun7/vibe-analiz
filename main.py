import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Pro Expert v4.3", layout="wide")

def style_engine(val):
    if val is None: return ''
    val_str = str(val)
    # HT/FT ve Skor renklendirmeleri için esnek yapı
    if any(x in val_str for x in ['Over', 'Yes', 'Home', '1/1', '2/2', '1/2', '2/1']): 
        return 'background-color: #27ae60; color: white;'
    if any(x in val_str for x in ['Under', 'No', 'Away']): 
        return 'background-color: #c0392b; color: white;'
    if any(x in val_str for x in ['Draw', 'Tie', 'Beraberlik', 'X/', '/X']): 
        return 'background-color: #f39c12; color: white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi v4.3")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)

st.sidebar.markdown("---")
yillar = st.sidebar.multiselect("Sezonlar", options=['2122', '2223', '2324', '2425', '2526'], default=['2324', '2425', '2526'])
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.00, 0.30, 0.08, step=0.01)

# --- LİG SEÇİMİ ---
FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {'Şampiyonlar Ligi': 'soccer_uefa_champs_league', 'Avrupa Ligi': 'soccer_uefa_europa_league', 'Konferans Ligi': 'soccer_uefa_europa_conference_league'},
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere Premier': 'soccer_epl', 'İspanya La Liga': 'soccer_spain_la_liga', 'Almanya Bundesliga': 'soccer_germany_bundesliga', 'İtalya Serie A': 'soccer_italy_serie_a', 'Fransa Ligue 1': 'soccer_france_ligue_one'},
    "⚽ AVRUPA DİĞER": {'Hollanda': 'soccer_netherlands_eredivisie', 'Belçika': 'soccer_belgium_first_division', 'Portekiz': 'soccer_portugal_primeira_liga', 'İskoçya': 'soccer_scotland_premiership'}
}

secili_kodlar = []
for kat, ligler in FUTBOL_LIGLERI.items():
    with st.sidebar.expander(kat):
        select_all = st.checkbox(f"{kat} - Tümünü Seç", key=f"all_{kat}")
        for isim, kod in ligler.items():
            is_checked = st.checkbox(isim, value=select_all, key=f"cb_{kod}")
            if is_checked: secili_kodlar.append(kod)

@st.cache_data(ttl=86400)
def futbol_veri_motoru(sezonlar):
    if not sezonlar: return pd.DataFrame()
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT'}
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC']
                df = df[df.columns.intersection(cols)]
                temp = df.dropna(subset=['B365H','B365D','B365A']).copy()
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()

def bulten_cek(key, kodlar, t):
    res = []
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h', timeout=10)
            data = r.json()
            for m in data:
                tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                if tm.date() == t:
                    bookies = m.get('bookmakers', [])
                    if not bookies: continue
                    o = bookies[0]['markets'][0]['outcomes']
                    h = next((x['price'] for x in o if x['name'] == m['home_team']), 0)
                    a = next((x['price'] for x in o if x['name'] == m['away_team']), 0)
                    b = next((x['price'] for x in o if x['name'].lower() in ['draw', 'tie', 'beraberlik']), 0)
                    res.append({'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(res)

if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ Key girin ve yan menüden ligleri seçin.")
    else:
        with st.spinner("📊 Vibe Hesaplanıyor..."):
            gecmis = futbol_veri_motoru(yillar)
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)

        if not bulten.empty:
            for i, m in bulten.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))].copy()
                
                if len(b) >= 1:
                    with st.expander(f"🔍 {m['zaman'].strftime('%H:%M')} | {m['ev']} - {m['dep']}"):
                        # Rakamlar
                        iy05 = (b['HTHG']+b['HTAG']>=1).mean(); ms25 = (b['FTHG']+b['FTAG']>=3).mean(); kg = ((b['FTHG']>0)&(b['FTAG']>0)).mean()
                        ms_m = b['FTR'].mode()[0]; iy_m = b['HTR'].mode()[0]

                        # 1. BÖLÜM: TAHMİN RAPORU (METİN)
                        c1, c2 = st.columns(2)
                        with c1:
                            st.success(f"**ANA TERCİH:** {'2.5 ÜST' if ms25 > 0.65 else 'KG VAR' if kg > 0.6 else ms_m.replace('H','Ev').replace('A','Dep').replace('D','Beraberlik')}")
                            st.info(f"**HT/FT VİBE:** {(b['HTR'] + '/' + b['FTR']).mode()[0].replace('H','1').replace('A','2').replace('D','X')}")
                        with c2:
                            st.warning(f"**KOMBO:** {ms_m.replace('H','Ev').replace('A','Dep').replace('D','Beraberlik')} & {'KG VAR' if kg > 0.55 else 'KG YOK'}")
                            if ms25 > 0.65 and kg < 0.50: st.error("⚠️ TEK TARAFLI MAÇ RİSKİ (3-0 vb.)")

                        # 2. BÖLÜM: GEÇMİŞ MAÇ ANALİZİ (TABLO)
                        st.write("📚 **Geçmiş Maç Analizi**")
                        dt = pd.DataFrame()
                        dt['Tarih'] = b['Date'].dt.strftime('%d.%m.%Y')
                        dt['Maç'] = b['HomeTeam'] + "-" + b['AwayTeam']
                        dt['İY'] = b['HTHG'].astype(int).astype(str)+"-"+b['HTAG'].astype(int).astype(str)
                        dt['MS'] = b['FTHG'].astype(int).astype(str)+"-"+b['FTAG'].astype(int).astype(str)
                        dt['1Y_05'] = (b['HTHG']+b['HTAG']>=1).map({True:'Over', False:'Under'})
                        dt['MS_25'] = (b['FTHG']+b['FTAG']>=3).map({True:'Over', False:'Under'})
                        dt['KG'] = ((b['FTHG']>0)&(b['FTAG']>0)).map({True:'Yes', False:'No'})
                        dt['Krn'] = (b.get('HC',0)+b.get('AC',0)).astype(int)
                        st.dataframe(dt.style.map(style_engine, subset=['1Y_05', 'MS_25', 'KG']), use_container_width=True, hide_index=True)

                        # 3. BÖLÜM: HT/FT SÜRPRİZ RADARI (ÖZEL TABLO)
                        st.write("🔥 **HT/FT Sürpriz Radarı**")
                        hf_df = pd.DataFrame()
                        hf_df['Tarih'] = b['Date'].dt.strftime('%d.%m.%Y')
                        hf_df['Skor'] = b['FTHG'].astype(int).astype(str)+"-"+b['FTAG'].astype(int).astype(str)
                        hf_df['HT/FT'] = b['HTR'].replace({'H':'1','A':'2','D':'X'}) + "/" + b['FTR'].replace({'H':'1','A':'2','D':'X'})
                        
                        # Sürpriz yüzdesi
                        surpriz_p = ((b['HTR']=='H')&(b['FTR']=='A')|(b['HTR']=='A')&(b['FTR']=='H')).mean()
                        if surpriz_p >= 0.10:
                            st.error(f"⚠️ SÜRPRİZ RADARI: Bu oranda %{int(surpriz_p*100)} ihtimalle 1/2 veya 2/1 saptandı!")
                        
                        st.dataframe(hf_df.style.map(style_engine, subset=['HT/FT']), use_container_width=True, hide_index=True)

        else: st.warning("Maç bulunamadı.")
