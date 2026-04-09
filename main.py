import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

# Excel indirme fonksiyonu
def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Analiz')
    writer.close()
    return output.getvalue()

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
spor_turu = st.sidebar.radio("Analiz Türü", ["⚽ Futbol", "🏀 Basketbol"])
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=2)
TOLERANS = st.sidebar.slider("Oran Hassasiyeti (Tolerans)", 0.05, 0.30, 0.10)

# --- LİG HAVUZLARI ---
FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {'Şampiyonlar Ligi': 'soccer_uefa_champs_league', 'Avrupa Ligi': 'soccer_uefa_europa_league', 'Konferans Ligi': 'soccer_uefa_europa_conference_league'},
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇸🇦 ARAP LİGLERİ": {'Suudi Arabistan Pro Lig': 'soccer_saudi_arabia_pro_league', 'BAE Pro Lig': 'soccer_uae_pro_league'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'İtalya': 'soccer_italy_serie_a', 'Fransa': 'soccer_france_ligue_one'}
}

lig_havuzu = FUTBOL_LIGLERI if "Futbol" in spor_turu else {}
secili_kodlar = []

st.sidebar.markdown("---")
if "genel_secici" not in st.session_state: st.session_state["genel_secici"] = False
def toggler_all():
    for kat in lig_havuzu.values():
        for kod in kat.values(): st.session_state[f"cb_{kod}"] = st.session_state["genel_secici"]

st.sidebar.checkbox(f"🚀 Bütün Ligleri Seç", key="genel_secici", on_change=toggler_all)

for kat_isim, ligler in lig_havuzu.items():
    with st.sidebar.expander(kat_isim):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"): secili_kodlar.append(kod)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    sezonlar = ['2324', '2425', '2526']
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT'}
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
                temp = df[cols].dropna().copy()
                ms_gol, iy_gol = (temp['FTHG'] + temp['FTAG']), (temp['HTHG'] + temp['HTAG'])
                temp['İS_İY05'] = iy_gol >= 1
                temp['İS_İY15'] = iy_gol >= 2
                temp['İS_MS15'] = ms_gol >= 2
                temp['İS_MS25'] = ms_gol >= 3
                temp['İS_MS35'] = ms_gol >= 4
                temp['İS_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['S1Y'] = temp['HTHG'].astype(int).astype(str) + "-" + temp['HTAG'].astype(int).astype(str)
                temp['SMS'] = temp['FTHG'].astype(int).astype(str) + "-" + temp['FTAG'].astype(int).astype(str)
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste)

def bulten_cek(key, kodlar, t):
    all_res = []
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h', timeout=10)
            data = r.json()
            for m in data:
                tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                if tm.date() == t:
                    o = m['bookmakers'][0]['markets'][0]['outcomes']
                    h = next((x['price'] for x in o if x['name'] == m['home_team']), 0)
                    a = next((x['price'] for x in o if x['name'] == m['away_team']), 0)
                    b = next((x['price'] for x in o if x['name'].lower() in ['draw', 'tie']), 0)
                    all_res.append({'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(all_res)

def style_engine(val):
    if val in ['Over', 'Yes', 'Home']: return 'background-color: #27ae60; color: white;'
    if val in ['Under', 'No', 'Away']: return 'background-color: #c0392b; color: white;'
    if val in ['Draw', 'Tie']: return 'background-color: #f39c12; color: white;'
    return ''

# --- ANA PROGRAM ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ Key girin ve lig seçin.")
    else:
        gecmis = futbol_veri_motoru()
        bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)
        if not bulten.empty:
            final_list = []
            for i, m in bulten.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                if len(b) >= min_ornek:
                    final_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'LİG': m['lig'], 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                        '1Y 0.5': 'Over' if b['İS_İY05'].mean() >= 0.5 else 'Under',
                        'MS 1.5': 'Over' if b['İS_MS15'].mean() >= 0.5 else 'Under',
                        'MS 2.5': 'Over' if b['İS_MS25'].mean() >= 0.5 else 'Under',
                        'KG': 'Yes' if b['İS_KG'].mean() >= 0.5 else 'No',
                        '1Y SKOR': b['S1Y'].mode()[0], 'MS SKOR': b['SMS'].mode()[0],
                        '1Y': b['HTR'].mode()[0].replace('H','Home').replace('A','Away').replace('D','Draw'),
                        'MS': b['FTR'].mode()[0].replace('H','Home').replace('A','Away').replace('D','Draw'),
                        'ÖRNEK': len(b), 'idx': i
                    })
            
            if final_list:
                st.subheader(f"⚽ {secili_tarih} Tarihli Futbol Analizleri")
                df_ana = pd.DataFrame(final_list)
                st.dataframe(df_ana.drop(columns=['idx']).style.map(style_engine, subset=['1Y 0.5','MS 1.5','MS 2.5','KG','1Y','MS']), use_container_width=True)
                
                st.markdown("---")
                st.subheader("📚 Maç Detaylı Analizi (Alt Bülten)")
                
                for row in final_list:
                    with st.expander(f"🔍 {row['SAAT']} | {row['EV SAHİBİ']} vs {row['DEPLASMAN']}"):
                        m_o = bulten.loc[row['idx']]
                        b_det = gecmis[(gecmis['B365H'].between(m_o['h']-TOLERANS, m_o['h']+TOLERANS)) & (gecmis['B365D'].between(m_o['b']-TOLERANS, m_o['b']+TOLERANS)) & (gecmis['B365A'].between(m_o['a']-TOLERANS, m_o['a']+TOLERANS))].copy()
                        
                        # Detay tablosunu image_64cb61.jpg formatına dönüştürüyoruz
                        detay_tablo = b_det[['Date', 'HomeTeam', 'AwayTeam']].copy()
                        detay_tablo['İY 0.5'] = b_det['İS_İY05'].map({True: 'Over', False: 'Under'})
                        detay_tablo['İY 1.5'] = b_det['İS_İY15'].map({True: 'Over', False: 'Under'})
                        detay_tablo['MS 1.5'] = b_det['İS_MS15'].map({True: 'Over', False: 'Under'})
                        detay_tablo['MS 2.5'] = b_det['İS_MS25'].map({True: 'Over', False: 'Under'})
                        detay_tablo['MS 3.5'] = b_det['İS_MS35'].map({True: 'Over', False: 'Under'})
                        detay_tablo['KG'] = b_det['İS_KG'].map({True: 'Yes', False: 'No'})
                        detay_tablo['1Y SKOR'] = b_det['S1Y']
                        detay_tablo['MS SKOR'] = b_det['SMS']
                        detay_tablo['1Y'] = b_det['HTR'].replace({'H':'Home','A':'Away','D':'Draw'})
                        detay_tablo['MS'] = b_det['FTR'].replace({'H':'Home','A':'Away','D':'Draw'})
                        
                        # Detay tablosunu renklendirerek göster
                        st.dataframe(
                            detay_tablo.style.map(style_engine, subset=['İY 0.5','İY 1.5','MS 1.5','MS 2.5','MS 3.5','KG','1Y','MS']),
                            use_container_width=True
                        )
            else: st.warning("Eşleşen örnek bulunamadı.")
