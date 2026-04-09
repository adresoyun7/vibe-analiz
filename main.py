import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz - Pro Max", layout="wide")

st.markdown("""
    <style>
    div[data-testid="stDataFrame"] { width: 100%; }
    .stExpander { border: 1px solid #444; border-radius: 5px; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

st.title("⚽ Profesyonel Oran Analiz Üssü")

# --- YAN MENÜ ---
st.sidebar.header("⚙️ Ayarlar")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

# GENİŞ LİG LİSTESİ (Legal Bülten Odaklı)
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
def veri_motoru_yukle():
    ligler = {'T1':'Tür1','E0':'İng1','E1':'İng2','SP1':'İsp1','D1':'Alm1','I1':'İta1','F1':'Fra1','N1':'Hol1','BRA':'Brz'}
    sezonlar = ['2324', '2425', '2526']
    liste = []
    for k in ligler.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
                temp = df[cols].dropna().copy()
                # Analiz Sütunları
                temp['GOL_MS'] = temp['FTHG'] + temp['FTAG']
                temp['GOL_1Y'] = temp['HTHG'] + temp['HTAG']
                temp['1Y_05'] = temp['GOL_1Y'] > 0.5
                temp['1Y_15'] = temp['GOL_1Y'] > 1.5
                temp['MS_15'] = temp['GOL_MS'] > 1.5
                temp['MS_25'] = temp['GOL_MS'] > 2.5
                temp['MS_35'] = temp['GOL_MS'] > 3.5
                temp['KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['KORNER'] = temp['HC'] + temp['AC']
                temp['KART'] = temp['HY'] + temp['AY']
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

def style_row(val):
    if val in ['Over', 'Yes', 'Home']: return 'background-color: #27ae60; color: white;'
    if val in ['Under', 'No', 'Away']: return 'background-color: #c0392b; color: white;'
    if val == 'Draw': return 'background-color: #f39c12; color: white;'
    return ''

# --- 4. ANA PROGRAM ---
if API_KEY and secili_kodlar:
    if st.button("🚀 GENİŞLETİLMİŞ ANALİZİ BAŞLAT"):
        gecmis = veri_motoru_yukle()
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
                        '1Y 0.5': 'Over' if b['1Y_05'].mean() > 0.5 else 'Under',
                        '1Y 1.5': 'Over' if b['1Y_15'].mean() > 0.5 else 'Under',
                        'MS 1.5': 'Over' if b['MS_15'].mean() > 0.5 else 'Under',
                        'MS 2.5': 'Over' if b['MS_2.5'].mean() > 0.5 else 'Under',
                        'MS 3.5': 'Over' if b['MS_3.5'].mean() > 0.5 else 'Under',
                        'K/G': 'Yes' if b['KG'].mean() > 0.5 else 'No',
                        '1Y SKOR': b['SKOR_1Y'].mode()[0],
                        'SKOR': b['SKOR_MS'].mode()[0],
                        'KRN (ORT)': round(b['KORNER'].mean(), 1),
                        'KRT (ORT)': round(b['KART'].mean(), 1),
                        '1Y': 'Home' if b['HTR'].mode()[0]=='H' else ('Draw' if b['HTR'].mode()[0]=='D' else 'Away'),
                        'MS': 'Home' if b['FTR'].mode()[0]=='H' else ('Draw' if b['FTR'].mode()[0]=='D' else 'Away'),
                        'ÖRNEK': len(b)
                    })

            if final_list:
                df_res = pd.DataFrame(final_list)
                st.subheader("📊 Analiz Edilen Tüm Maçlar (Geniş Tablo)")
                st.dataframe(df_res.style.map(style_row, subset=['1Y 0.5','1Y 1.5','MS 1.5','MS 2.5','MS 3.5','K/G','1Y','MS']), use_container_width=True)
                
                st.markdown("### 📚 Maç Bazlı Geçmiş Sonuçlar (Tıkla ve Gör)")
                for row in final_list:
                    with st.expander(f"👁️ {row['EV SAHİBİ']} - {row['DEPLASMAN']}"):
                        m_orig = bulten.loc[row['ID']]
                        b_det = gecmis[(gecmis['B365H'].between(m_orig['h']-TOLERANS, m_orig['h']+TOLERANS)) & 
                                       (gecmis['B365D'].between(m_orig['b']-TOLERANS, m_orig['b']+TOLERANS)) & 
                                       (gecmis['B365A'].between(m_orig['a']-TOLERANS, m_orig['a']+TOLERANS))]
                        st.table(b_det[['Date', 'HomeTeam', 'AwayTeam', 'SKOR_MS', 'KORNER', 'KART']].head(10))
            else: st.warning("Maç bulunamadı.")
else: st.info("Lig seç ve API Key gir.")
