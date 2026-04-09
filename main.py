import streamlit as st
import pandas as pd
import requests
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

def style_engine(val):
    if val is None: return ''
    val_str = str(val)
    if 'Over' in val_str or 'Yes' in val_str: return 'background-color: #27ae60; color: white;'
    if 'Under' in val_str or 'No' in val_str: return 'background-color: #c0392b; color: white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)

st.sidebar.markdown("---")
st.sidebar.subheader("📅 Veri Havuzu")
# Önemli: Geçmiş veri olan sezonları geniş tutalım
yillar = st.sidebar.multiselect("Sezonlar", options=['2122','2223','2324','2425','2526'], default=['2223','2324','2425','2526'])
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=1)
TOLERANS = st.sidebar.slider("Hassasiyet (0.05 önerilir)", 0.00, 0.30, 0.08, step=0.01)

# --- ARŞİV DESTEKLİ LİGLER (Bu liglerde analiz çalışır) ---
FUTBOL_LIGLERI = {
    "✅ ANALİZ EDİLEBİLİR (ARŞİV VAR)": {
        'Türkiye Süper Lig': 'soccer_turkey_super_league',
        'İngiltere Premier': 'soccer_epl',
        'İspanya La Liga': 'soccer_spain_la_liga',
        'Almanya Bundesliga': 'soccer_germany_bundesliga',
        'İtalya Serie A': 'soccer_italy_serie_a',
        'Fransa Ligue 1': 'soccer_france_ligue_one',
        'Hollanda Eredivisie': 'soccer_netherlands_eredivisie',
        'Belçika Pro League': 'soccer_belgium_first_division',
        'Portekiz Primeira': 'soccer_portugal_primeira_liga',
        'Avusturya Bundesliga': 'soccer_austria_bundesliga',
        'İskoçya Premiership': 'soccer_scotland_premiership'
    },
    "⚠️ SADECE BÜLTEN (ARŞİV YOK)": {
        'Copa Libertadores': 'soccer_conmebol_copa_libertadores',
        'Copa Sudamericana': 'soccer_conmebol_copa_sudamericana',
        'Çin Super League': 'soccer_china_superleague',
        'Avustralya A-League': 'soccer_australia_aleague'
    }
}

secili_kodlar = []
for kat, ligler in FUTBOL_LIGLERI.items():
    with st.sidebar.expander(kat):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"): secili_kodlar.append(kod)

# --- VERİ MOTORU (Geliştirilmiş Hata Yönetimi) ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru(sezonlar):
    lig_map = {
        'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1',
        'N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT'
    }
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

def bulten_cek_optimized(key, t):
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
                markets = bookies[0].get('markets', [])
                if not markets: continue
                o = markets[0]['outcomes']
                try:
                    h = next(x['price'] for x in o if x['name'] == m['home_team'])
                    a = next(x['price'] for x in o if x['name'] == m['away_team'])
                    b = next(x['price'] for x in o if x['name'].lower() in ['draw', 'tie', 'beraberlik'])
                    res.append({'key': m['sport_key'], 'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
                except: continue
        return pd.DataFrame(res)
    except: return pd.DataFrame()

# --- ANA PROGRAM ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ API Key girin ve analiz edilebilir liglerden seçin.")
    else:
        with st.spinner("📊 Veriler eşleştiriliyor..."):
            gecmis = futbol_veri_motoru(yillar)
            tum_bulten = bulten_cek_optimized(API_KEY, secili_tarih)
            
            if not tum_bulten.empty:
                bulten = tum_bulten[tum_bulten['key'].isin(secili_kodlar)]
            else: bulten = pd.DataFrame()

        if bulten.empty:
            st.warning(f"ℹ️ {secili_tarih} tarihinde seçilen liglerde maç yok.")
        else:
            final_list = []
            for i, m in bulten.iterrows():
                # Oran kıyaslama motoru
                b = gecmis[
                    (gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & 
                    (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & 
                    (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))
                ].copy()
                
                if len(b) >= min_ornek:
                    iy05 = (b['HTHG']+b['HTAG']>=1).mean()
                    ms25 = (b['FTHG']+b['FTAG']>=3).mean()
                    kg = ((b['FTHG']>0)&(b['FTAG']>0)).mean()
                    ms_mod = b['FTR'].mode()[0]
                    
                    final_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'LİG': m['lig'], 'EV': m['ev'], 'DEP': m['dep'],
                        '1Y_05': f"{'Over' if iy05>=0.5 else 'Under'} ({int(iy05*100)}%)",
                        'MS_25': f"{'Over' if ms25>=0.5 else 'Under'} ({int(ms25*100)}%)",
                        'KG': f"{'Yes' if kg>=0.5 else 'No'} ({int(kg*100)}%)",
                        'MS_VİBE': ms_mod.replace('H','Ev').replace('A','Dep').replace('D','Beraberlik'),
                        'ÖRNEK': len(b)
                    })

            if final_list:
                st.dataframe(pd.DataFrame(final_list).style.map(style_engine, subset=['1Y_05','MS_25','KG']), use_container_width=True)
            else:
                st.error("❌ Eşleşme Bulunamadı: Seçtiğin liglerin arşivi sistemde yok veya oranlar geçmişle örtüşmüyor. Lütfen Majör Ligleri seçtiğinden emin ol.")
