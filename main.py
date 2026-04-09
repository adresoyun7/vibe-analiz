import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe & Poisson Pro Ultra", layout="wide")

# 1. GERÇEK POISSON MOTORU (Olasılık Hesaplar)
def poisson_analiz(ev_avg, dep_avg):
    if ev_avg <= 0 and dep_avg <= 0: return "0-0", 0, 0
    ev_avg, dep_avg = max(ev_avg, 0.1), max(dep_avg, 0.1)
    
    # 0-5 gol arası olasılıklar
    max_g = 6
    ev_probs = [poisson.pmf(i, ev_avg) for i in range(max_g)]
    dep_probs = [poisson.pmf(i, dep_avg) for i in range(max_g)]
    
    # Skor Matrisi
    m = np.outer(ev_probs, dep_probs)
    ev_s, dep_s = np.unravel_index(m.argmax(), m.shape)
    
    # Üst ve KG Olasılıkları
    ust_prob = (1 - (m[0,0] + m[0,1] + m[0,2] + m[1,0] + m[1,1] + m[2,0])) * 100
    kg_prob = (1 - (sum(m[0,:]) + sum(m[:,0]) - m[0,0])) * 100
    
    return f"{ev_s}-{dep_s}", round(ust_prob, 1), round(kg_prob, 1)

def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Analiz')
    writer.close()
    return output.getvalue()

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe & Poisson")
spor_turu = st.sidebar.radio("Tür", ["⚽ Futbol", "🏀 Basketbol"])
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Tarih", value=bugun)
min_ornek = st.sidebar.number_input("Min. Örnek", min_value=1, value=2)
TOLERANS = st.sidebar.slider("Hassasiyet", 0.05, 0.30, 0.10)

# --- LİG HAVUZLARI ---
FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {'Şampiyonlar Ligi': 'soccer_uefa_champs_league', 'Avrupa Ligi': 'soccer_uefa_europa_league', 'Konferans Ligi': 'soccer_uefa_europa_conference_league'},
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇸🇦 ARAP LİGLERİ": {'Suudi Arabistan': 'soccer_saudi_arabia_pro_league', 'BAE': 'soccer_uae_pro_league'},
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
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT'}
    sezonlar = ['2425', '2526']
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
                temp = df[cols].dropna().copy()
                temp['C_FLIP'] = ((temp['HTR'] == 'H') & (temp['FTR'] == 'A')) | ((temp['HTR'] == 'A') & (temp['FTR'] == 'H'))
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste)

def bulten_cek(key, kodlar, t):
    res = []
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
                    res.append({'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(res)

def style_engine(val):
    if isinstance(val, str):
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
            f_list, flips = [], []
            for i, m in bulten.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                if len(b) >= min_ornek:
                    # Poisson Verisi
                    ev_a, dep_a = b['FTHG'].mean(), b['FTAG'].mean()
                    iy_e_a, iy_d_a = b['HTHG'].mean(), b['HTAG'].mean()
                    ms_p_skor, ms_p_ust, ms_p_kg = poisson_analiz(ev_a, dep_a)
                    iy_p_skor, _, _ = poisson_analiz(iy_e_a, iy_d_a)
                    
                    f_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                        '1Y SKOR': iy_p_skor, 'MS SKOR': ms_p_skor,
                        'P. ÜST %': f"%{ms_p_ust}", 'P. KG %': f"%{ms_p_kg}",
                        '1Y 0.5': 'Over' if (iy_e_a + iy_d_a) >= 1 else 'Under',
                        'MS 2.5': 'Over' if ms_p_ust >= 50 else 'Under',
                        'KG': 'Yes' if ms_p_kg >= 50 else 'No',
                        'KRN (ORT)': round((b['HC'] + b['AC']).mean(), 1),
                        'KRT (ORT)': round((b['HY'] + b['AY']).mean(), 1),
                        'ÖRNEK': len(b), 'idx': i
                    })
                    if b['C_FLIP'].any(): flips.append({'m': f"{m['ev']} - {m['dep']}", 'p': int(b['C_FLIP'].mean()*100)})
            
            if f_list:
                df = pd.DataFrame(f_list)
                st.subheader(f"⚽ {secili_tarih} Vibe & Poisson Analizleri")
                st.dataframe(df.drop(columns=['idx']).style.map(style_engine, subset=['1Y 0.5','MS 2.5','KG']), use_container_width=True)
                
                st.markdown("---")
                st.subheader("📚 Maç Detayları (Geçmiş Skor, Korner ve Kart)")
                for row in f_list:
                    with st.expander(f"👁️ {row['SAAT']} | {row['EV SAHİBİ']} - {row['DEPLASMAN']}"):
                        m_o = bulten.loc[row['idx']]
                        b_d = gecmis[(gecmis['B365H'].between(m_o['h']-TOLERANS, m_o['h']+TOLERANS)) & (gecmis['B365D'].between(m_o['b']-TOLERANS, m_o['b']+TOLERANS)) & (gecmis['B365A'].between(m_o['a']-TOLERANS, m_o['a']+TOLERANS))]
                        b_d['1Y'] = b_d['HTHG'].astype(int).astype(str) + "-" + b_d['HTAG'].astype(int).astype(str)
                        b_d['MS'] = b_d['FTHG'].astype(int).astype(str) + "-" + b_d['FTAG'].astype(int).astype(str)
                        b_d['Krn'] = (b_d['HC'] + b_d['AC']).astype(int)
                        b_d['Krt'] = (b_d['HY'] + b_d['AY']).astype(int)
                        st.table(b_d[['Date', 'HomeTeam', 'AwayTeam', '1Y', 'MS', 'Krn', 'Krt']].head(10))
                
                if flips:
                    st.subheader("🔥 Sürpriz Radarı")
                    for f in flips: st.warning(f"⚠️ **{f['m']}**: %{f['p']} sürpriz potansiyeli!")
            else: st.warning("Maç bulunamadı.")
