import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Analiz')
    writer.close()
    return output.getvalue()

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol")
spor_turu = st.sidebar.radio("Tür", ["⚽ Futbol", "🏀 Basketbol"])
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Tarih", value=bugun)
min_ornek = st.sidebar.number_input("Min. Örnek", min_value=1, value=2)
TOLERANS = st.sidebar.slider("Hassasiyet", 0.05, 0.45, 0.15)

# --- LİG HAVUZLARI (GÜNCEL KODLARLA) ---
FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {'Şampiyonlar Ligi': 'soccer_uefa_champs_league', 'Avrupa Ligi': 'soccer_uefa_europa_league', 'Konferans Ligi': 'soccer_uefa_europa_conference_league'},
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'İtalya': 'soccer_italy_serie_a', 'Fransa': 'soccer_france_ligue_one'},
    "🇪🇺 AVRUPA DİĞER": {'Romanya': 'soccer_romania_liga_1', 'Hollanda': 'soccer_netherlands_ere_divisie', 'Belçika': 'soccer_belgium_first_division', 'Portekiz': 'soccer_portugal_primeira_liga', 'İskoçya': 'soccer_scotland_premier_league'}
}

BASKETBOL_LIGLERI = {
    "🏆 ULUSLARARASI": {'Euroleague': 'basketball_euroleague', 'NBA': 'basketball_nba'},
    "🇪🇺 AVRUPA": {'Türkiye BSL': 'basketball_turkey_bsl', 'İspanya ACB': 'basketball_spain_liga_endesa'}
}

lig_havuzu = FUTBOL_LIGLERI if "Futbol" in spor_turu else BASKETBOL_LIGLERI
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
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO','N1':'NL','B1':'BE','P1':'PT'}
    liste = []
    for k in lig_map.keys():
        try:
            url = f"https://www.football-data.co.uk/mmz4281/2425/{k}.csv"
            df = pd.read_csv(url)
            cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
            temp = df[cols].dropna().copy()
            ms_gol, iy_gol = (temp['FTHG'] + temp['FTAG']), (temp['HTHG'] + temp['FTAG'])
            temp['C_1Y05'], temp['C_1Y15'] = iy_gol > 0.5, iy_gol > 1.5
            temp['C_MS15'], temp['C_MS25'], temp['C_MS35'] = ms_gol > 1.5, ms_gol > 2.5, ms_gol > 3.5
            temp['C_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
            temp['C_KRN'], temp['C_KRT'] = (temp['HC'] + temp['AC']), (temp['HY'] + temp['AY'])
            temp['S1Y'], temp['SMS'] = temp['HTHG'].astype(int).astype(str)+"-"+temp['HTAG'].astype(int).astype(str), temp['FTHG'].astype(int).astype(str)+"-"+temp['FTAG'].astype(int).astype(str)
            temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
            liste.append(temp)
        except: continue
    return pd.concat(liste) if liste else pd.DataFrame()

def bulten_cek(key, kodlar, t, spor):
    res = []
    loglar = []
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h')
            if r.status_code == 200:
                data = r.json()
                for m in data:
                    tm = datetime.strptime(m['commence_time'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=3)
                    if tm.date() == t:
                        o = m['bookmakers'][0]['markets'][0]['outcomes']
                        h = next((x['price'] for x in o if x['name']==m['home_team']), 0)
                        a = next((x['price'] for x in o if x['name']==m['away_team']), 0)
                        b = next((x['price'] for x in o if x['name'].lower() == 'draw'), 0) if spor == "⚽ Futbol" else 0
                        res.append({'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
            elif r.status_code == 429: loglar.append(f"⏸️ {k}: Kota doldu (429)")
            elif r.status_code == 401: loglar.append(f"❌ {k}: Key geçersiz (401)")
            else: loglar.append(f"⚠️ {k}: Hata {r.status_code}")
        except: continue
    return pd.DataFrame(res), loglar

# --- ANA PROGRAM ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if API_KEY and secili_kodlar:
        bulten, logs = bulten_cek(API_KEY, secili_kodlar, secili_tarih, spor_turu)
        
        if logs:
            with st.expander("📡 Sistem Günlüğü (API Durumu)"):
                for l in logs: st.write(l)
        
        if not bulten.empty:
            if "Futbol" in spor_turu:
                gecmis = futbol_veri_motoru()
                final_list = []
                for i, m in bulten.iterrows():
                    b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                    if len(b) >= min_ornek:
                        final_list.append({
                            'SAAT': m['zaman'].strftime('%H:%M'), 'LİG': m['lig'], 'EV': m['ev'], 'DEP': m['dep'],
                            '1Y 0.5': 'Over' if b['C_1Y05'].mean() > 0.5 else 'Under', 'MS 2.5': 'Over' if b['C_MS25'].mean() > 0.5 else 'Under',
                            'KG': 'Yes' if b['C_KG'].mean() > 0.5 else 'No', '1Y SKOR': b['S1Y'].mode()[0], 'MS SKOR': b['SMS'].mode()[0],
                            'KRN (ORT)': round(b['C_KRN'].mean(), 1), 'KRT (ORT)': round(b['C_KRT'].mean(), 1), 'ÖRNEK': len(b)
                        })
                if final_list:
                    st.dataframe(pd.DataFrame(final_list), use_container_width=True)
            else:
                st.dataframe(bulten, use_container_width=True)
        else: st.error("Maç bülteni alınamadı. Günlüğü kontrol et.")
else: st.info("Key girin ve lig seçin.")
