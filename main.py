import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz - Multi-Sport Ultra", layout="wide")

st.markdown("<style>div[data-testid='stDataFrame'] { width: 100%; }</style>", unsafe_allow_html=True)

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
spor_turu = st.sidebar.radio("Analiz Türü", ["⚽ Futbol", "🏀 Basketbol"])
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun, min_value=bugun)
min_ornek = st.sidebar.number_input("Min. Örnek (Geçmiş Veri)", min_value=1, value=2)
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.45, 0.15)

# --- LİG HAVUZLARI ---
FUTBOL_LIGLERI = {
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere Premier': 'soccer_epl', 'İspanya La Liga': 'soccer_spain_la_liga', 'Almanya Bundesliga': 'soccer_germany_bundesliga', 'İtalya Serie A': 'soccer_italy_serie_a', 'Fransa Ligue 1': 'soccer_france_ligue_one'},
    "🇪🇺 AVRUPA DİĞER": {'Romanya Liga I': 'soccer_romania_liga_1', 'Hollanda': 'soccer_netherlands_ere_divisie', 'Portekiz': 'soccer_portugal_primeira_liga', 'Belçika': 'soccer_belgium_first_division', 'İskoçya': 'soccer_scotland_premier_league', 'Avusturya': 'soccer_austria_bundesliga', 'İsviçre': 'soccer_switzerland_league', 'Danimarka': 'soccer_denmark_superliga', 'Yunanistan': 'soccer_greece_super_league', 'Polonya': 'soccer_poland_ekstraklasa'},
    "🌎 GLOBAL": {'Suudi Arabistan': 'soccer_saudi_arabia_pro_league', 'BAE': 'soccer_uae_pro_league', 'ABD MLS': 'soccer_usa_mls', 'Brezilya Serie A': 'soccer_brazil_campeonato_serie_a', 'Meksika': 'soccer_mexico_ligamx', 'Japonya': 'soccer_japan_j_league'}
}

BASKETBOL_LIGLERI = {
    "🏆 ULUSLARARASI": {'Euroleague': 'basketball_euroleague', 'NBA': 'basketball_nba'},
    "🇪🇺 AVRUPA LİGLERİ": {'Türkiye BSL': 'basketball_turkey_bsl', 'İspanya ACB': 'basketball_spain_liga_endesa', 'İtalya Lega A': 'basketball_italy_lega_a', 'Almanya BBL': 'basketball_germany_bbl', 'Fransa LNB': 'basketball_france_lnb', 'Yunanistan GBL': 'basketball_greece_basket_league'},
    "🌎 GLOBAL": {'Çin CBA': 'basketball_china_cba', 'Avustralya NBL': 'basketball_australia_nbl'}
}

# --- SEÇİM MANTIĞI (SESSION STATE) ---
lig_havuzu = FUTBOL_LIGLERI if "Futbol" in spor_turu else BASKETBOL_LIGLERI
secili_kodlar = []

st.sidebar.markdown("---")

# 1. Bütün Kategorileri Seç Fonksiyonu
def toggler_all():
    state = st.session_state["genel_secici"]
    for kat in lig_havuzu.values():
        for kod in kat.values():
            st.session_state[f"cb_{kod}"] = state

genel_sec = st.sidebar.checkbox(f"🚀 Bütün {spor_turu} Liglerini Seç", value=False, key="genel_secici", on_change=toggler_all)

# 2. Kategorilere Göre Seçim
for kat_isim, ligler in lig_havuzu.items():
    with st.sidebar.expander(kat_isim):
        # Kategori bazlı seçim fonksiyonu
        def toggler_kat(k=kat_isim, l=ligler):
            state = st.session_state[f"kat_sec_{k}"]
            for kod in l.values():
                st.session_state[f"cb_{kod}"] = state

        st.checkbox(f"Hepsini Seç ({kat_isim})", value=genel_sec, key=f"kat_sec_{kat_isim}", on_change=toggler_kat)
        
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"):
                secili_kodlar.append(kod)

# --- VERİ MOTORU (FUTBOL) ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT','GRE':'GR','SWZ':'CH','DNK':'DK','POL':'PL','BRA':'BR'}
    sezonlar = ['2324', '2425', '2526']
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
                temp = df[cols].dropna().copy()
                ms_gol = temp['FTHG'] + temp['FTAG']
                iy_gol = temp['HTHG'] + temp['FTAG']
                temp['C_1Y05'] = iy_gol > 0.5
                temp['C_1Y15'] = iy_gol > 1.5
                temp['C_MS15'] = ms_gol > 1.5
                temp['C_MS25'] = ms_gol > 2.5
                temp['C_MS35'] = ms_gol > 3.5
                temp['C_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['C_FLIP'] = ((temp['HTR'] == 'H') & (temp['FTR'] == 'A')) | ((temp['HTR'] == 'A') & (temp['FTR'] == 'H'))
                temp['C_KRN'] = temp['HC'] + temp['AC']
                temp['C_KRT'] = temp['HY'] + temp['AY']
                temp['S1Y'] = temp['HTHG'].astype(int).astype(str)+"-"+temp['HTAG'].astype(int).astype(str)
                temp['SMS'] = temp['FTHG'].astype(int).astype(str)+"-"+temp['FTAG'].astype(int).astype(str)
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).sort_values(by='Date', ascending=False) if liste else pd.DataFrame()

def bulten_cek(key, kodlar, hedef_tarih):
    res = []
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h').json()
            for m in r:
                t = datetime.strptime(m['commence_time'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=3)
                if t.date() == hedef_tarih:
                    o = m['bookmakers'][0]['markets'][0]['outcomes']
                    h = next((x['price'] for x in o if x['name']==m['home_team']), 0)
                    a = next((x['price'] for x in o if x['name']==m['away_team']), 0)
                    b = next((x['price'] for x in o if x['name'].lower() == 'draw'), 0)
                    res.append({'lig': m['sport_title'], 'zaman': t, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(res)

def style_engine(val):
    if val in ['Over', 'Yes', 'Home']: return 'background-color: #27ae60; color: white;'
    if val in ['Under', 'No', 'Away']: return 'background-color: #c0392b; color: white;'
    if val == 'Draw': return 'background-color: #f39c12; color: white;'
    return ''

# --- ANA PROGRAM ---
st.title(f"{spor_turu} Profesyonel Analiz")

if API_KEY and secili_kodlar:
    if st.button("🚀 ANALİZİ BAŞLAT"):
        if "Futbol" in spor_turu:
            gecmis = futbol_veri_motoru()
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)
            if not bulten.empty:
                final_list, flips = [], []
                for i, m in bulten.sort_values(by='zaman').iterrows():
                    b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                    if not b.empty and len(b) >= min_ornek:
                        final_list.append({
                            'SAAT': m['zaman'].strftime('%H:%M'), 'LİG': m['lig'], 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                            '1Y 0.5': 'Over' if b['C_1Y05'].mean() > 0.5 else 'Under', '1Y 1.5': 'Over' if b['C_1Y15'].mean() > 0.5 else 'Under',
                            'MS 1.5': 'Over' if b['C_MS15'].mean() > 0.5 else 'Under', 'MS 2.5': 'Over' if b['C_MS25'].mean() > 0.5 else 'Under',
                            'MS 3.5': 'Over' if b['C_MS35'].mean() > 0.5 else 'Under', 'KG': 'Yes' if b['C_KG'].mean() > 0.5 else 'No',
                            '1Y SKOR': b['S1Y'].mode()[0], 'MS SKOR': b['SMS'].mode()[0], 'KRN (ORT)': round(b['C_KRN'].mean(), 1),
                            '1Y': 'Home' if b['HTR'].mode()[0]=='H' else ('Draw' if b['HTR'].mode()[0]=='D' else 'Away'),
                            'MS': 'Home' if b['FTR'].mode()[0]=='H' else ('Draw' if b['FTR'].mode()[0]=='D' else 'Away'), 'ÖRNEK': len(b),
                            'orig_idx': i
                        })
                        if b['C_FLIP'].any(): flips.append({'m': f"{m['ev']} - {m['dep']}", 'o': b['C_FLIP'].mean()})
                
                if final_list:
                    df_res = pd.DataFrame(final_list)
                    st.dataframe(df_res.drop(columns=['orig_idx']).style.map(style_engine, subset=['1Y 0.5','1Y 1.5','MS 1.5','MS 2.5','MS 3.5','KG','1Y','MS']), use_container_width=True)
                    for row in final_list:
                        with st.expander(f"👁️ {row['SAAT']} | {row['EV SAHİBİ']} - {row['DEPLASMAN']}"):
                            m_orig = bulten.loc[row['orig_idx']]
                            b_det = gecmis[(gecmis['B365H'].between(m_orig['h']-TOLERANS, m_orig['h']+TOLERANS)) & (gecmis['B365D'].between(m_orig['b']-TOLERANS, m_orig['b']+TOLERANS)) & (gecmis['B365A'].between(m_orig['a']-TOLERANS, m_orig['a']+TOLERANS))]
                            st.table(b_det[['Date', 'HomeTeam', 'AwayTeam', 'S1Y', 'SMS', 'C_KRN', 'C_KRT']].rename(columns={'S1Y':'1Y','SMS':'MS','C_KRN':'Krn','C_KRT':'Krt'}).head(10))
                    if flips:
                        st.markdown("---")
                        st.subheader("🔥 HT/FT Sürpriz Radarı")
                        for f in flips: st.warning(f"**{f['m']}**: Geçmiş örneklerin %{int(f['o']*100)} kadarı sürpriz bitmiş!")
            else: st.warning("Eşleşen örnek bulunamadı.")
        else:
            bulten_bsk = bulten_cek(API_KEY, secili_kodlar, secili_tarih)
            if not bulten_bsk.empty:
                st.subheader(f"🏀 {secili_tarih} Basketbol Bülteni")
                st.dataframe(bulten_bsk[['lig', 'zaman', 'ev', 'dep', 'h', 'a']].rename(columns={'h':'Ev','a':'Dep'}), use_container_width=True)
            else: st.warning("Basketbol maçı bulunamadı.")
else:
    st.info("Sol menüden spor türü ve ligleri seçip API Key girin.")
