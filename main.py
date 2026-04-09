import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz - Ultra Global", layout="wide")

st.markdown("<style>div[data-testid='stDataFrame'] { width: 100%; }</style>", unsafe_allow_html=True)

st.title("⚽ Maksimum Kapsamlı Global Analiz Sistemi")

# --- YAN MENÜ ---
st.sidebar.header("⚙️ Ayarlar")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")

# --- LİG KATEGORİLERİ ---
Dunya_Ligleri = {
    "🇹🇷 TÜRKİYE": {
        'Süper Lig': 'soccer_turkey_super_league',
        'TFF 1. Lig': 'soccer_turkey_pTT_1_lig'
    },
    "🏆 AVRUPA KUPALARI": {
        'Şampiyonlar Ligi': 'soccer_uefa_champions_league',
        'Avrupa Ligi': 'soccer_uefa_europa_league',
        'Konferans Ligi': 'soccer_uefa_europa_conference_league'
    },
    "🏴󠁧󠁢󠁥󠁮󠁧󠁿 İNGİLTERE": {
        'Premier League': 'soccer_epl',
        'Championship': 'soccer_efl_championship',
        'League One': 'soccer_efl_league_one',
        'League Two': 'soccer_efl_league_two',
        'FA Cup': 'soccer_fa_cup'
    },
    "🇪🇺 MAJÖR LİGLER": {
        'İspanya La Liga': 'soccer_spain_la_liga',
        'İspanya La Liga 2': 'soccer_spain_segunda_division',
        'Almanya Bundesliga': 'soccer_germany_bundesliga',
        'İtalya Serie A': 'soccer_italy_serie_a',
        'Fransa Ligue 1': 'soccer_france_ligue_one',
        'Hollanda Eredivisie': 'soccer_netherlands_ere_divisie',
        'Portekiz Primeira': 'soccer_portugal_primeira_liga'
    },
    "🌍 DÜNYA & DİĞER": {
        'Suudi Arabistan': 'soccer_saudi_arabia_pro_league',
        'BAE Ligi': 'soccer_uae_pro_league',
        'ABD MLS': 'soccer_usa_mls',
        'Brezilya Serie A': 'soccer_brazil_campeonato_serie_a',
        'Japonya J-League': 'soccer_japan_j_league',
        'Meksika Liga MX': 'soccer_mexico_ligamx',
        'Rusya Premier': 'soccer_russia_premier_league',
        'İskoçya Premiership': 'soccer_scotland_premier_league'
    },
    "🌍 MİLLİ TAKIMLAR": {
        'Uluslar Ligi': 'soccer_uefa_nations_league',
        'Dünya Kupası Elemeleri': 'soccer_fifa_world_cup_qualifying_uefa'
    }
}

secili_kodlar = []
st.sidebar.markdown("### 🏟️ Lig Seçimi")
for kategori, ligler in Dunya_Ligleri.items():
    with st.sidebar.expander(kategori):
        for isim, kod in ligler.items():
            if st.sidebar.checkbox(isim, value=(kategori == "🇹🇷 TÜRKİYE"), key=kod):
                secili_kodlar.append(kod)

TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.45, 0.20)

@st.cache_data(ttl=86400)
def ultra_global_veri_yukle():
    lig_sozlugu = {
        'T1': 'Tür1', 'E0': 'İng1', 'E1': 'İng2', 'E2': 'İng3', 'E3': 'İng4',
        'SP1': 'İsp1', 'SP2': 'İsp2', 'D1': 'Alm1', 'I1': 'İta1', 'F1': 'Fra1',
        'N1': 'Hol1', 'P1': 'Por1', 'SC0': 'İsk1', 'BRA': 'Brezilya'
    }
    sezonlar = ['2324', '2425', '2526']
    liste = []
    for kod in lig_sozlugu.keys():
        for sezon in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{sezon}/{kod}.csv"
                df = pd.read_csv(url)
                cols = ['Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HTHG', 'HTAG', 'FTR', 'HTR', 'B365H', 'B365D', 'B365A', 'HC', 'AC', 'HY', 'AY']
                temp = df[cols].dropna().copy()
                temp['MS_GOL'] = temp['FTHG'] + temp['FTAG']
                temp['KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['SURPRIZ'] = ((temp['HTR'] == 'H') & (temp['FTR'] == 'A')) | ((temp['HTR'] == 'A') & (temp['FTR'] == 'H'))
                temp['KORNER'] = temp['HC'] + temp['AC']
                temp['KART'] = temp['HY'] + temp['AY']
                temp['SKOR'] = temp['FTHG'].astype(int).astype(str) + "-" + temp['FTAG'].astype(int).astype(str)
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).sort_values(by='Date', ascending=False) if liste else pd.DataFrame()

def bulten_cek(key, kodlar):
    sonuc = []
    bitis = datetime.now() + timedelta(days=4)
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h').json()
            if isinstance(r, list):
                for m in r:
                    t = datetime.strptime(m['commence_time'], '%Y-%m-%dT%H:%M:%SZ') + timedelta(hours=3)
                    if t <= bitis:
                        o = m['bookmakers'][0]['markets'][0]['outcomes']
                        sonuc.append({'lig': m['sport_title'], 'zaman': t.strftime('%d/%m %H:%M'), 
                                      'ev': m['home_team'], 'dep': m['away_team'], 
                                      'h': next(x['price'] for x in o if x['name']==m['home_team']),
                                      'a': next(x['price'] for x in o if x['name']==m['away_team']),
                                      'b': next(x['price'] for x in o if x['name']=='Draw')})
        except: continue
    return pd.DataFrame(sonuc)

def style_vibe(val):
    if val in ['Over', 'Yes', 'Home']: return 'background-color: #2ecc71; color: white;'
    if val in ['Under', 'No', 'Away']: return 'background-color: #e74c3c; color: white;'
    if val == 'Draw': return 'background-color: #f39c12; color: white;'
    return ''

if API_KEY and secili_kodlar:
    if st.button("🚀 SEÇİLİ TÜM LİGLERİ TARA"):
        gecmis = ultra_global_veri_yukle()
        bulten = bulten_cek(API_KEY, secili_kodlar)
        
        if not bulten.empty:
            final_data, surpriz_list = [], []
            for i, m in bulten.iterrows():
                b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & 
                           (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & 
                           (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                if not b.empty:
                    final_data.append({
                        'ID': i, 'ZAMAN': m['zaman'], 'LİG': m['lig'], 'MAÇ': f"{m['ev']} - {m['dep']}",
                        'MS 2.5': 'Over' if b['MS_GOL'].mean() > 2.5 else 'Under',
                        'KG': 'Yes' if b['KG'].mean() > 0.5 else 'No',
                        'KORNER (ORT)': round(b['KORNER'].mean(), 1),
                        'KART (ORT)': round(b['KART'].mean(), 1),
                        'SKOR': b['SKOR'].mode()[0], 'ÖRNEK': len(b)
                    })
                    if b['SURPRIZ'].any():
                        surpriz_list.append({'m': f"{m['ev']}-{m['dep']}", 's': b['SURPRIZ'].sum(), 't': len(b)})

            if final_data:
                st.subheader(f"📊 {len(final_data)} Maç Analiz Edildi")
                st.dataframe(pd.DataFrame(final_data).style.map(style_vibe, subset=['MS 2.5', 'KG']), use_container_width=True)
                
                st.markdown("### 📚 Maç Detayları")
                for row in final_data:
                    m_orig = bulten.loc[row['ID']]
                    b_det = gecmis[(gecmis['B365H'].between(m_orig['h']-TOLERANS, m_orig['h']+TOLERANS)) & 
                                   (gecmis['B365D'].between(m_orig['b']-TOLERANS, m_orig['b']+TOLERANS)) & 
                                   (gecmis['B365A'].between(m_orig['a']-TOLERANS, m_orig['a']+TOLERANS))]
                    with st.expander(f"👁️ {row['ZAMAN']} | {row['MAÇ']}"):
                        st.table(b_det[['Date', 'HomeTeam', 'AwayTeam', 'MS_SKOR', 'KORNER']].head(10))

                if surpriz_list:
                    st.markdown("---")
                    st.subheader("🔥 HT/FT SÜPRİZ ANALİZİ")
                    for s in surpriz_list:
                        st.warning(f"**{s['m']}**: {s['t']} benzer maçın **{s['s']}** tanesi ters döndü!")
            else: st.warning("Benzer maç bulunamadı.")
else:
    st.info("Sol menüden ligleri seçin ve API Key girin.")
