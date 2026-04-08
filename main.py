import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #0e1117; }
    div[data-testid="stDataFrame"] { width: 100%; }
    </style>
    """, unsafe_allow_html=True)

st.title("⚽ Profesyonel Oran Analiz Paneli")
st.info("Bültendeki maçların geçmiş benzer oran analizleri, korner beklentileri ve sürpriz riskleri aşağıdadır.")

# --- YAN MENÜ ---
st.sidebar.header("⚙️ Kontrol Paneli")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

Dunya_Ligleri = {
    'Türkiye Süper Lig': 'soccer_turkey_super_league',
    'İngiltere Premier Lig': 'soccer_epl', 'İspanya La Liga': 'soccer_spain_la_liga',
    'Almanya Bundesliga': 'soccer_germany_bundesliga', 'İtalya Serie A': 'soccer_italy_serie_a',
    'Fransa Ligue 1': 'soccer_france_ligue_one', 'Hollanda Eredivisie': 'soccer_netherlands_ere_divisie',
    'Şampiyonlar Ligi': 'soccer_uefa_champions_league'
}

secili_etiketler = st.sidebar.multiselect("Ligleri Filtrele", list(Dunya_Ligleri.keys()), default=['Türkiye Süper Lig', 'İngiltere Premier Lig', 'İspanya La Liga'])
LIG_KODLARI = [Dunya_Ligleri[lig] for lig in secili_etiketler]
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.35, 0.18)

# --- 1. VERİ MOTORU ---
@st.cache_data(ttl=86400)
def veri_hazirla():
    ligler = {'E0': 'İng1', 'SP1': 'İsp1', 'D1': 'Alm1', 'I1': 'İta1', 'T1': 'Tür1', 'F1': 'Fra1', 'N1': 'Hol1'}
    sezonlar = ['2324', '2425', '2526']
    liste = []
    for kod in ligler.keys():
        for sezon in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{sezon}/{kod}.csv"
                df = pd.read_csv(url)
                cols = ['HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HTHG', 'HTAG', 'FTR', 'HTR', 'B365H', 'B365D', 'B365A', 'HC', 'AC', 'HY', 'AY']
                temp = df[cols].dropna().copy()
                temp['MS_GOL'] = temp['FTHG'] + temp['FTAG']
                temp['KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['SURPRIZ'] = ((temp['HTR'] == 'H') & (temp['FTR'] == 'A')) | ((temp['HTR'] == 'A') & (temp['FTR'] == 'H'))
                temp['KORNER'] = temp['HC'] + temp['AC']
                temp['SKOR'] = temp['FTHG'].astype(int).astype(str) + "-" + temp['FTAG'].astype(int).astype(str)
                liste.append(temp)
            except: continue
    return pd.concat(liste)

def bulten_cek(key, kodlar):
    sonuc = []
    bitis = datetime.now() + timedelta(days=2)
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu').json()
            for m in r:
                t = datetime.strptime(m['commence_time'], '%Y-%m-%dT%H:%M:%SZ')
                if t <= bitis:
                    o = m['bookmakers'][0]['markets'][0]['outcomes']
                    sonuc.append({'lig': m['sport_title'], 'ev': m['home_team'], 'dep': m['away_team'], 
                                  'h': next(x['price'] for x in o if x['name']==m['home_team']),
                                  'a': next(x['price'] for x in o if x['name']==m['away_team']),
                                  'b': next(x['price'] for x in o if x['name']=='Draw')})
        except: continue
    return pd.DataFrame(sonuc)

# --- 2. RENKLENDİRME ---
def color_engine(val):
    colors = {'Over': '#2ecc71', 'Yes': '#2ecc71', 'Home': '#2ecc71', 
              'Under': '#e74c3c', 'No': '#e74c3c', 'Away': '#e74c3c', 
              'RISK!': '#9b59b6', 'Draw': '#f39c12'}
    color = colors.get(val, '')
    return f'background-color: {color}; color: white; font-weight: bold; text-align: center;' if color else 'text-align: center;'

# --- 3. ANA EKRAN ---
if API_KEY:
    if st.button("🚀 ANALİZİ BAŞLAT VE TABLOYU OLUŞTUR"):
        gecmis = veri_hazirla()
        yarin = bulten_cek(API_KEY, LIG_KODLARI)
        
        if not yarin.empty:
            final = []
            for _, m in yarin.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & 
                           (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & 
                           (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                
                if len(b) >= 2:
                    final.append({
                        'LİG': m['lig'], 'MAÇ': f"{m['ev']} - {m['dep']}",
                        'MS 2.5': 'Over' if b['MS_GOL'].mean() > 2.5 else 'Under',
                        'KG VAR': 'Yes' if b['KG'].mean() > 0.5 else 'No',
                        'KORNER (ORT)': round(b['KORNER'].mean(), 1),
                        'SÜRPRIZ': 'RISK!' if b['SURPRIZ'].any() else 'Yok',
                        'EN ÇOK SKOR': b['SKOR'].mode()[0],
                        'ÖRNEK': len(b),
                        'ORANLAR': f"{m['h']} - {m['b']} - {m['a']}"
                    })
            
            if final:
                df_final = pd.DataFrame(final)
                st.success(f"Analiz Tamamlandı! Toplam {len(final)} maç bulundu.")
                st.dataframe(df_final.style.map(color_engine, subset=['MS 2.5', 'KG VAR', 'SÜRPRIZ']))
            else: st.warning("Benzer maç bulunamadı, toleransı artır.")
else: st.info("API Key giriniz.")
