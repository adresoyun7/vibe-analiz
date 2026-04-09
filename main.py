import streamlit as st
import pandas as pd
import requests
import numpy as np
from scipy.stats import poisson
from datetime import datetime, timedelta

st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

# --- POISSON ---
def poisson_analiz(ev_avg, dep_avg):
    if ev_avg <= 0 and dep_avg <= 0:
        return "0-0", 0.0, 0.0

    ev_avg, dep_avg = max(ev_avg, 0.05), max(dep_avg, 0.05)

    max_g = 6
    ev_probs = [poisson.pmf(i, ev_avg) for i in range(max_g)]
    dep_probs = [poisson.pmf(i, dep_avg) for i in range(max_g)]

    m = np.outer(ev_probs, dep_probs)

    ev_s, dep_s = np.unravel_index(m.argmax(), m.shape)

    ust_prob = (1 - (m[0,0] + m[0,1] + m[0,2] + m[1,0] + m[1,1] + m[2,0])) * 100
    kg_prob = (1 - (sum(m[0,:]) + sum(m[:,0]) - m[0,0])) * 100

    return f"{ev_s}-{dep_s}", round(ust_prob, 1), round(kg_prob, 1)


def style_engine(val):
    if val in ['Over', 'Yes', 'Home']:
        return 'background-color: #27ae60; color: white;'
    if val in ['Under', 'No', 'Away']:
        return 'background-color: #c0392b; color: white;'
    if val in ['Draw', 'Tie']:
        return 'background-color: #f39c12; color: white;'
    return ''


# --- SIDEBAR ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)

min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=5)
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.30, 0.10)


# 🔥 TÜM LİGLER GERİ GELDİ
FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {
        'Şampiyonlar Ligi': 'soccer_uefa_champs_league',
        'Avrupa Ligi': 'soccer_uefa_europa_league',
        'Konferans Ligi': 'soccer_uefa_europa_conference_league'
    },
    "🇹🇷 TÜRKİYE": {
        'Süper Lig': 'soccer_turkey_super_league',
        '1. Lig': 'soccer_turkey_pTT_1_lig'
    },
    "🇸🇦 ARAP LİGLERİ": {
        'Suudi Arabistan': 'soccer_saudi_arabia_pro_league',
        'BAE': 'soccer_uae_pro_league'
    },
    "🇪🇺 AVRUPA MAJÖR": {
        'İngiltere': 'soccer_epl',
        'İspanya': 'soccer_spain_la_liga',
        'Almanya': 'soccer_germany_bundesliga',
        'İtalya': 'soccer_italy_serie_a',
        'Fransa': 'soccer_france_ligue_one'
    }
}

secili_kodlar = []
for kat, ligler in FUTBOL_LIGLERI.items():
    with st.sidebar.expander(kat):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=kod):
                secili_kodlar.append(kod)


# --- DATA ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    sezonlar = ['2324', '2425', '2526']
    ligler = ['E0','SP1','D1','I1','F1','T1','N1','B1','P1','SC0','D1']

    liste = []

    for lig in ligler:
        for sezon in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{sezon}/{lig}.csv"
                df = pd.read_csv(url)

                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A']
                df = df[cols].dropna()

                df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)
                liste.append(df)
            except:
                continue

    return pd.concat(liste)


def bulten_cek(key, kodlar, t):
    res = []

    for k in kodlar:
        try:
            r = requests.get(
                f'https://api.the-odds-api.com/v4/sports/{k}/odds/',
                params={'apiKey': key, 'regions': 'eu', 'markets': 'h2h'},
                timeout=10
            )

            for m in r.json():
                tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)

                if tm.date() != t:
                    continue

                o = m['bookmakers'][0]['markets'][0]['outcomes']

                h = next(x['price'] for x in o if x['name'] == m['home_team'])
                a = next(x['price'] for x in o if x['name'] == m['away_team'])
                d = next(x['price'] for x in o if x['name'].lower() in ['draw','tie'])

                res.append({
                    'ev': m['home_team'],
                    'dep': m['away_team'],
                    'h': h,
                    'd': d,
                    'a': a,
                    'zaman': tm
                })

        except:
            continue

    return pd.DataFrame(res)


# --- MAIN ---
if st.button("🚀 ANALİZİ BAŞLAT"):

    if not API_KEY or not secili_kodlar:
        st.error("Key gir ve lig seç")
        st.stop()

    gecmis = futbol_veri_motoru()
    bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)

    if bulten.empty:
        st.warning("Maç yok")
    else:
        final = []

        lig_ev_ort = gecmis['FTHG'].mean()
        lig_dep_ort = gecmis['FTAG'].mean()

        for _, m in bulten.iterrows():

            b = gecmis[
                (gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) &
                (gecmis['B365D'].between(m['d']-TOLERANS, m['d']+TOLERANS)) &
                (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))
            ]

            if len(b) < max(min_ornek, 10):
                continue

            # ✅ DOĞRU POISSON
            ev_atak = b['FTHG'].mean() / lig_ev_ort
            ev_savunma = b['FTAG'].mean() / lig_dep_ort

            dep_atak = b['FTAG'].mean() / lig_dep_ort
            dep_savunma = b['FTHG'].mean() / lig_ev_ort

            lambda_ev = ev_atak * dep_savunma * lig_ev_ort
            lambda_dep = dep_atak * ev_savunma * lig_dep_ort

            skor, ust, kg = poisson_analiz(lambda_ev, lambda_dep)

            final.append({
                "Saat": m['zaman'].strftime("%H:%M"),
                "Maç": f"{m['ev']} - {m['dep']}",
                "Skor": skor,
                "Üst %": ust,
                "KG %": kg,
                "Örnek": len(b)
            })

        df = pd.DataFrame(final)
        st.dataframe(df, use_container_width=True)
