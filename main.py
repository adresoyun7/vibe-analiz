import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Max", layout="wide")

st.markdown("<style>div[data-testid='stDataFrame'] { width: 100%; }</style>", unsafe_allow_html=True)

st.title("⚽ Profesyonel Oran Analiz Üssü")

# --- YAN MENÜ ---
st.sidebar.header("⚙️ Ayarlar")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

Dunya_Ligleri = {
    "TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "MAJÖR": {'İngiltere Premier': 'soccer_epl', 'İspanya La Liga': 'soccer_spain_la_liga', 'Almanya Bundesliga': 'soccer_germany_bundesliga', 'İtalya Serie A': 'soccer_italy_serie_a', 'Fransa Ligue 1': 'soccer_france_ligue_one'},
    "DİĞER": {'Hollanda': 'soccer_netherlands_ere_divisie', 'Suudi Arabistan': 'soccer_saudi_arabia_pro_league', 'BAE': 'soccer_uae_pro_league', 'ABD MLS': 'soccer_usa_mls', 'Brezilya': 'soccer_brazil_campeonato_serie_a'}
}

secili_kodlar = []
for kat, ligler in Dunya_Ligleri.items():
    with st.sidebar.expander(kat):
        for isim, kod in ligler.items():
            if st.checkbox(isim, value=(kat == "TÜRKİYE"), key=kod):
                secili_kodlar.append(kod)

TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.45, 0.20)

# --- 1. VERİ MOTORU ---
@st.cache_data(ttl=86400)
def veri_hazirla():
    ligler = {'T1':'Tür','E0':'İng1','E1':'İng2','SP1':'İsp1','D1':'Alm1','I1':'İta1','F1':'Fra1','N1':'Hol1','BRA':'Brz'}
    sezonlar = ['2324', '2425', '2526']
    liste = []
    for k in ligler.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
                temp = df[cols].dropna().copy()
                # Sütunları standartlaştırıyoruz (KeyError'u önlemek için)
                ms_gol = temp['FTHG'] + temp['FTAG']
                iy_gol = temp['HTHG'] + temp['HTAG']
                temp['COL_1Y05'] = iy_gol > 0.5
                temp['COL_1Y15'] = iy_gol > 1.5
                temp['COL_MS15'] = ms_gol > 1.5
                temp['COL_MS25'] = ms_gol > 2.5
                temp['COL_MS35'] = ms_gol > 3.5
                temp['COL_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['COL_KRN'] = temp['HC'] + temp['AC']
                temp['COL_KRT'] = temp['HY'] + temp['AY']
                temp['SKOR_1Y'] = temp['HTHG'].astype(int).astype(str) + "-" + temp['HTAG'].astype(int).astype(str)
                temp['SKOR_MS'] = temp['FTHG'].astype(int).astype(str) + "-" + temp['FTAG'].astype(int).astype(str)
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).sort_values(by='Date', ascending=False) if liste else pd.DataFrame()

def bulten_cek(key, kodlar):
    res = []
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu').json()
            for m in r:
                o = m['bookmakers'][0]['markets'][0]['outcomes']
                res.append({'lig': m['sport_title'], 'zaman': m['commence_time'], 'ev': m['home_team'], 'dep': m['away_team'], 
                            'h': next(x['price'] for x in o if x['name']==m['home_team']),
                            'a': next(x['price'] for x in o if x['name']==m['away_team']),
                            'b': next(x['price'] for x in o if x['name']=='Draw')})
        except: continue
    return pd.DataFrame(res)

def style_engine(val):
    if val in ['Over', 'Yes', 'Home']: return 'background-color: #27ae60; color: white;'
    if val in ['Under', 'No', 'Away']: return 'background-color: #c0392b; color: white;'
    if val == 'Draw': return 'background-color: #f39c12; color: white;'
    return ''

# --- 4. ANA PROGRAM ---
if API_KEY and secili_kodlar:
    if st.button("🚀 ANALİZİ BAŞLAT"):
        gecmis = veri_hazirla()
        bulten = bulten_cek(API_KEY, secili_kodlar)
        
        if not bulten.empty:
            final_list = []
            for i, m in bulten.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & 
                           (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & 
                           (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                
                if not b.empty:
                    final_list.append({
                        'ID': i, 'LİG': m['lig'], 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                        '1Y 0.5': 'Over' if b['COL_1Y05'].mean() > 0.5 else 'Under',
                        '1Y 1.5': 'Over' if b['COL_1Y15'].mean() > 0.5 else 'Under',
                        'MS 1.5': 'Over' if b['COL_MS15'].mean() > 0.5 else 'Under',
                        'MS 2.5': 'Over' if b['COL_MS25'].mean() > 0.5 else 'Under',
                        'MS 3.5': 'Over' if b['COL_MS35'].mean() > 0.5 else 'Under',
                        'KG': 'Yes' if b['COL_KG'].mean() > 0.5 else 'No',
                        '1Y SKOR': b['SKOR_1Y'].mode()[0],
                        'MS SKOR': b['SKOR_MS'].mode()[0],
                        'KRN (ORT)': round(b['COL_KRN'].mean(), 1),
                        'KRT (ORT)': round(b['COL_KRT'].mean(), 1),
                        '1Y': 'Home' if b['HTR'].mode()[0]=='H' else ('Draw' if b['HTR'].mode()[0]=='D' else 'Away'),
                        'MS': 'Home' if b['FTR'].mode()[0]=='H' else ('Draw' if b['FTR'].mode()[0]=='D' else 'Away'),
                        'ÖRNEK': len(b)
                    })

            if final_list:
                df_res = pd.DataFrame(final_list)
                st.subheader("📊 Genişletilmiş Analiz Tablosu")
                # Görseldeki geniş tablo düzeni (Tüm sütunlar renkli)
                st.dataframe(df_res.style.map(style_engine, subset=['1Y 0.5','1Y 1.5','MS 1.5','MS 2.5','MS 3.5','KG','1Y','MS']), use_container_width=True)
                
                st.markdown("---")
                st.subheader("📚 Maç Detayları ve Geçmiş Skorlar")
                for row in final_list:
                    with st.expander(f"👁️ {row['EV SAHİBİ']} - {row['DEPLASMAN']}"):
                        m_orig = bulten.loc[row['ID']]
                        b_det = gecmis[(gecmis['B365H'].between(m_orig['h']-TOLERANS, m_orig['h']+TOLERANS)) & 
                                       (gecmis['B365D'].between(m_orig['b']-TOLERANS, m_orig['b']+TOLERANS)) & 
                                       (gecmis['B365A'].between(m_orig['a']-TOLERANS, m_orig['a']+TOLERANS))]
                        st.table(b_det[['Date', 'HomeTeam', 'AwayTeam', 'SKOR_MS', 'COL_KRN', 'COL_KRT']].rename(columns={'SKOR_MS':'Skor','COL_KRN':'Korner','COL_KRT':'Kart'}).head(10))
            else: st.warning("Eşleşen örnek bulunamadı.")
        else: st.error("Bülten boş.")
else: st.info("Lig seçip API Key girerek başlayın.")
