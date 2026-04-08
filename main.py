import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro", layout="wide")

st.title("⚽ Oran Analiz & Skor Tahmin Paneli")
st.markdown("---")

# --- YAN MENÜ ---
st.sidebar.header("⚙️ Ayarlar")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
LIGLER = st.sidebar.multiselect(
    "Takip Edilecek Ligler",
    ['soccer_turkey_super_league', 'soccer_epl', 'soccer_spain_la_liga', 'soccer_germany_bundesliga', 'soccer_italy_serie_a', 'soccer_france_ligue_one'],
    default=['soccer_turkey_super_league', 'soccer_epl', 'soccer_spain_la_liga']
)
TOLERANS = st.sidebar.slider("Oran Toleransı", 0.05, 0.20, 0.12)

# --- 1. GEÇMİŞ VERİLERİ ÇEKME ---
@st.cache_data(ttl=86400)
def gecmis_verileri_yukle():
    lig_dosyalari = {'İngiltere': 'E0', 'İspanya': 'SP1', 'Almanya': 'D1', 'İtalya': 'I1', 'Türkiye': 'T1', 'Fransa': 'F1'}
    sezonlar = ['2324', '2425', '2526']
    liste = []
    for lig, kod in lig_dosyalari.items():
        for sezon in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{sezon}/{kod}.csv"
                df = pd.read_csv(url)
                cols = ['HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HTHG', 'HTAG', 'FTR', 'HTR', 'B365H', 'B365D', 'B365A']
                temp = df[cols].copy()
                temp['MS_GOL'] = temp['FTHG'] + temp['FTAG']
                temp['1Y_GOL'] = temp['HTHG'] + temp['HTAG']
                temp['1Y_0.5_UST'] = temp['1Y_GOL'] > 0.5
                temp['1Y_1.5_UST'] = temp['1Y_GOL'] > 1.5
                temp['MS_1.5_UST'] = temp['MS_GOL'] > 1.5
                temp['MS_2.5_UST'] = temp['MS_GOL'] > 2.5
                temp['MS_3.5_UST'] = temp['MS_GOL'] > 3.5
                temp['KG_VAR'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['MS_SKOR'] = temp['FTHG'].astype(int).astype(str) + "-" + temp['FTAG'].astype(int).astype(str)
                temp['1Y_SKOR'] = temp['HTHG'].astype(int).astype(str) + "-" + temp['HTAG'].astype(int).astype(str)
                liste.append(temp)
            except: continue
    return pd.concat(liste) if liste else pd.DataFrame()

# --- 2. CANLI BÜLTENİ ÇEKME ---
def guncel_bulten_cek(key, secili_ligler):
    sonuc = []
    bugun = datetime.now()
    yarin = bugun + timedelta(days=1)
    for lig in secili_ligler:
        try:
            url = f'https://api.the-odds-api.com/v4/sports/{lig}/odds/?apiKey={key}&regions=eu&markets=h2h'
            resp = requests.get(url).json()
            if isinstance(resp, list):
                for mac in resp:
                    mac_zamani = datetime.strptime(mac['commence_time'], '%Y-%m-%dT%H:%M:%SZ')
                    if bugun.date() <= mac_zamani.date() <= yarin.date():
                        oranlar = mac['bookmakers'][0]['markets'][0]['outcomes']
                        h = next(o['price'] for o in oranlar if o['name'] == mac['home_team'])
                        a = next(o['price'] for o in oranlar if o['name'] == mac['away_team'])
                        b = next(o['price'] for o in oranlar if o['name'] == 'Draw')
                        sonuc.append({'lig': mac['sport_title'], 'ev': mac['home_team'], 'dep': mac['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(sonuc)

# --- 3. RENKLENDİRME FONKSİYONU ---
def style_vibe(val):
    green = 'background-color: #2ecc71; color: white; font-weight: bold; text-align: center;'
    red = 'background-color: #e74c3c; color: white; font-weight: bold; text-align: center;'
    orange = 'background-color: #f39c12; color: white; font-weight: bold; text-align: center;'
    
    if val in ['Over', 'Yes', 'Home']: return green
    if val in ['Under', 'No', 'Away']: return red
    if val == 'Draw': return orange
    return 'text-align: center;'

# --- 4. ANA PROGRAM ---
if API_KEY:
    if st.button("🚀 ANALİZİ BAŞLAT"):
        with st.spinner('Veriler harmanlanıyor...'):
            gecmis = gecmis_verileri_yukle()
            yarin = guncel_bulten_cek(API_KEY, LIGLER)
            
            if not yarin.empty and not gecmis.empty:
                final_list = []
                for _, m in yarin.iterrows():
                    benzerler = gecmis[
                        (gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) &
                        (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) &
                        (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))
                    ]
                    
                    if len(benzerler) >= 3:
                        iy_05_v = 'Over' if (benzerler['1Y_0.5_UST'].mean() > 0.5) else 'Under'
                        iy_15_v = 'Over' if (benzerler['1Y_1.5_UST'].mean() > 0.5) else 'Under'
                        ms_15_v = 'Over' if (benzerler['MS_1.5_UST'].mean() > 0.5) else 'Under'
                        ms_25_v = 'Over' if (benzerler['MS_2.5_UST'].mean() > 0.5) else 'Under'
                        ms_35_v = 'Over' if (benzerler['MS_3.5_UST'].mean() > 0.5) else 'Under'
                        kg_v = 'Yes' if (benzerler['KG_VAR'].mean() > 0.5) else 'No'
                        
                        iy_res = 'Home' if (benzerler['HTR'].mode()[0] == 'H') else ('Draw' if benzerler['HTR'].mode()[0] == 'D' else 'Away')
                        ms_res = 'Home' if (benzerler['FTR'].mode()[0] == 'H') else ('Draw' if benzerler['FTR'].mode()[0] == 'D' else 'Away')
                        
                        final_list.append({
                            'LİG': m['lig'], 'EV': m['ev'], 'DEP': m['dep'],
                            'İY 0.5': iy_05_v, 'İY 1.5': iy_15_v, 'MS 1.5': ms_15_v, 
                            'MS 2.5': ms_25_v, 'MS 3.5': ms_35_v, 'KG': kg_v,
                            '1Y SKOR': benzerler['1Y_SKOR'].mode()[0],
                            'MS SKOR': benzerler['MS_SKOR'].mode()[0],
                            '1Y': iy_res, 'MS': ms_res, 'ÖRNEK': len(benzerler)
                        })
                
                if final_list:
                    df_res = pd.DataFrame(final_list)
                    st.success(f"Analiz Tamamlandı! {len(final_list)} maç bulundu.")
                    # BURADA MAP KULLANIYORUZ (Hata düzeldi)
                    st.dataframe(df_res.style.map(style_vibe, subset=['İY 0.5', 'İY 1.5', 'MS 1.5', 'MS 2.5', 'MS 3.5', 'KG', '1Y', 'MS']))
                else:
                    st.warning("Eşleşen benzer maç bulunamadı. Toleransı artırmayı dene.")
            else:
                st.error("Veri çekilemedi veya seçilen liglerde maç yok.")
else:
    st.info("👋 Hoş geldin Ersin! Sol menüden API Key girerek analizi başlatabilirsin.")
