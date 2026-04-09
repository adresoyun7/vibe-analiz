import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra - Romania Edition", layout="wide")

st.markdown("<style>div[data-testid='stDataFrame'] { width: 100%; }</style>", unsafe_allow_html=True)

st.title("⚽ Profesyonel Global Analiz & Sürpriz Dedektörü")

# --- YAN MENÜ ---
st.sidebar.header("⚙️ Ayarlar")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

# GENİŞLETİLMİŞ LİG HAVUZU (Romanya Eklendi)
Lig_Kategorileri = {
    "TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "ROMANYA": {'Liga I (Romanya)': 'soccer_romania_liga_1'},
    "AVRUPA (MAJÖR)": {'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'İtalya': 'soccer_italy_serie_a', 'Fransa': 'soccer_france_ligue_one'},
    "AVRUPA (DİĞER)": {'Hollanda': 'soccer_netherlands_ere_divisie', 'Portekiz': 'soccer_portugal_primeira_liga', 'Belçika': 'soccer_belgium_first_division', 'İskoçya': 'soccer_scotland_premier_league', 'Avusturya': 'soccer_austria_bundesliga', 'İsviçre': 'soccer_switzerland_league', 'Danimarka': 'soccer_denmark_superliga', 'Yunanistan': 'soccer_greece_super_league', 'Polonya': 'soccer_poland_ekstraklasa'},
    "GLOBAL": {'Suudi Arabistan': 'soccer_saudi_arabia_pro_league', 'BAE': 'soccer_uae_pro_league', 'ABD MLS': 'soccer_usa_mls', 'Brezilya': 'soccer_brazil_campeonato_serie_a', 'Meksika': 'soccer_mexico_ligamx'}
}

secili_kodlar = []
for kat, ligler in Lig_Kategorileri.items():
    with st.sidebar.expander(kat):
        for isim, kod in ligler.items():
            # Romanya varsayılan olarak seçili gelsin istiyorsan burayı güncelleyebiliriz
            is_default = (kat == "TÜRKİYE" or kat == "ROMANYA")
            if st.checkbox(isim, value=is_default, key=kod):
                secili_kodlar.append(kod)

TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.45, 0.20)

# --- 1. VERİ MOTORU ---
@st.cache_data(ttl=86400)
def global_veri_motoru():
    # Romanya ve diğer global veriler için havuzu genişlettik
    ligler = {'T1':'TR','E0':'EN1','E1':'EN2','SP1':'ES1','SP2':'ES2','D1':'DE1','I1':'IT1','F1':'FR1','N1':'NL1','B1':'BE1','P1':'PT1','SC0':'SC1','AUT':'AT','GRE':'GR','SWZ':'CH','DNK':'DK','POL':'PL','BRA':'BR','ROM':'RO'}
    sezonlar = ['2324', '2425', '2526']
    liste = []
    for k in ligler.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
                temp = df[cols].dropna().copy()
                temp['COL_1Y05'] = (temp['HTHG'] + temp['HTAG']) > 0.5
                temp['COL_1Y15'] = (temp['HTHG'] + temp['HTAG']) > 1.5
                temp['COL_MS15'] = (temp['FTHG'] + temp['FTAG']) > 1.5
                temp['COL_MS25'] = (temp['FTHG'] + temp['FTAG']) > 2.5
                temp['COL_MS35'] = (temp['FTHG'] + temp['FTAG']) > 3.5
                temp['COL_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['COL_FLIP'] = ((temp['HTR'] == 'H') & (temp['FTR'] == 'A')) | ((temp['HTR'] == 'A') & (temp['FTR'] == 'H'))
                temp['COL_KRN'] = temp['HC'] + temp['AC']
                temp['COL_KRT'] = temp['HY'] + temp['AY']
                temp['S1Y'] = temp['HTHG'].astype(int).astype(str)+"-"+temp['HTAG'].astype(int).astype(str)
                temp['SMS'] = temp['FTHG'].astype(int).astype(str)+"-"+temp['FTAG'].astype(int).astype(str)
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).sort_values(by='Date', ascending=False) if liste else pd.DataFrame()

def bulten_cek(key, kodlar):
    res = []
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h').json()
            for m in r:
                t = datetime.strptime(m['commence_time'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=3)
                o = m['bookmakers'][0]['markets'][0]['outcomes']
                res.append({'lig': m['sport_title'], 'zaman': t, 'ev': m['home_team'], 'dep': m['away_team'], 
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

# --- ANA PROGRAM ---
if API_KEY and secili_kodlar:
    if st.button("🚀 TÜM BÜLTENİ ANALİZ ET"):
        gecmis = global_veri_motoru()
        bulten = bulten_cek(API_KEY, secili_kodlar)
        
        if not bulten.empty:
            final_list, flips = [], []
            bulten = bulten.sort_values(by='zaman')
            
            for i, m in bulten.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & 
                           (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & 
                           (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                
                if not b.empty:
                    final_list.append({
                        'ID': i, 'SAAT': m['zaman'].strftime('%d/%m %H:%M'),
                        'LİG': m['lig'], 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                        '1Y 0.5': 'Over' if b['COL_1Y05'].mean() > 0.5 else 'Under',
                        '1Y 1.5': 'Over' if b['COL_1Y15'].mean() > 0.5 else 'Under',
                        'MS 1.5': 'Over' if b['COL_MS15'].mean() > 0.5 else 'Under',
                        'MS 2.5': 'Over' if b['COL_MS25'].mean() > 0.5 else 'Under',
                        'MS 3.5': 'Over' if b['COL_MS35'].mean() > 0.5 else 'Under',
                        'KG': 'Yes' if b['COL_KG'].mean() > 0.5 else 'No',
                        '1Y SKOR': b['S1Y'].mode()[0], 'MS SKOR': b['SMS'].mode()[0],
                        'KRN (ORT)': round(b['COL_KRN'].mean(), 1), 'KRT (ORT)': round(b['COL_KRT'].mean(), 1),
                        '1Y': 'Home' if b['HTR'].mode()[0]=='H' else ('Draw' if b['HTR'].mode()[0]=='D' else 'Away'),
                        'MS': 'Home' if b['FTR'].mode()[0]=='H' else ('Draw' if b['FTR'].mode()[0]=='D' else 'Away'),
                        'ÖRNEK': len(b)
                    })
                    if b['COL_FLIP'].any():
                        flips.append({'maç': f"{m['ev']} - {m['dep']}", 'oran': b['COL_FLIP'].mean()})

            if final_list:
                st.subheader("📊 Tarihe Göre Sıralı Geniş Analiz Tablosu")
                df_res = pd.DataFrame(final_list)
                st.dataframe(df_res.style.map(style_engine, subset=['1Y 0.5','1Y 1.5','MS 1.5','MS 2.5','MS 3.5','KG','1Y','MS']), use_container_width=True)
                
                st.markdown("### 📚 Maç Detayları ve Geçmiş Skorlar")
                for row in final_list:
                    with st.expander(f"👁️ {row['SAAT']} | {row['EV SAHİBİ']} - {row['DEPLASMAN']}"):
                        m_orig = bulten.loc[row['ID']]
                        b_det = gecmis[(gecmis['B365H'].between(m_orig['h']-TOLERANS, m_orig['h']+TOLERANS)) & 
                                       (gecmis['B365D'].between(m_orig['b']-TOLERANS, m_orig['b']+TOLERANS)) & 
                                       (gecmis['B365A'].between(m_orig['a']-TOLERANS, m_orig['a']+TOLERANS))]
                        st.table(b_det[['Date', 'HomeTeam', 'AwayTeam', 'S1Y', 'SMS', 'COL_KRN', 'COL_KRT']].rename(columns={'S1Y':'1Y Skor','SMS':'MS Skor','COL_KRN':'Korner','COL_KRT':'Kart'}).head(10))

                if flips:
                    st.markdown("---")
                    st.subheader("🔥 HT/FT Sürpriz Radarı (1/2 - 2/1)")
                    for f in flips:
                        st.warning(f"**{f['maç']}**: Geçmiş örneklerin %{int(f['oran']*100)} kadarı HT/FT sürpriz bitmiş!")
            else: st.warning("Eşleşen örnek bulunamadı.")
else: st.info("Lig seçip API Key girin.")
