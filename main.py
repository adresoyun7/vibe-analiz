import streamlit as st
import pandas as pd
import requests
import io
import numpy as np
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

def style_engine(val):
    if val is None: return ''
    val_str = str(val)
    if 'Over' in val_str or 'Yes' in val_str or 'Home' in val_str: return 'background-color: #27ae60; color: white;'
    if 'Under' in val_str or 'No' in val_str or 'Away' in val_str: return 'background-color: #c0392b; color: white;'
    if 'Draw' in val_str or 'Tie' in val_str: return 'background-color: #f39c12; color: white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=1)
TOLERANS = st.sidebar.slider("Oran Hassasiyeti (0.00 = Birebir)", 0.00, 0.30, 0.10, step=0.01)

FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {'Şampiyonlar Ligi': 'soccer_uefa_champs_league', 'Avrupa Ligi': 'soccer_uefa_europa_league', 'Konferans Ligi': 'soccer_uefa_europa_conference_league'},
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇸🇦 ARAP LİGLERİ": {'Suudi Arabistan': 'soccer_saudi_arabia_pro_league', 'BAE': 'soccer_uae_pro_league'},
    "🇪🇺 AVRUPA MAJÖR": {'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'İtalya': 'soccer_italy_serie_a', 'Fransa': 'soccer_france_ligue_one'}
}

secili_kodlar = []
for kat_isim, ligler in FUTBOL_LIGLERI.items():
    with st.sidebar.expander(kat_isim):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"): secili_kodlar.append(kod)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    sezonlar = ['2122', '2223', '2324', '2425', '2526']
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO','N1':'NL','B1':'BE','P1':'PT','SC0':'SC1','AUT':'AT'}
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
                df = df[df.columns.intersection(cols)]
                temp = df.dropna(subset=['B365H','B365D','B365A','FTHG','FTAG']).copy()
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except: continue
    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()

def form_analizi_yap(gecmis, ev_takim, dep_takim):
    def get_avg(takim):
        son_5 = gecmis[(gecmis['HomeTeam'] == takim) | (gecmis['AwayTeam'] == takim)].sort_values('Date', ascending=False).head(5)
        if len(son_5) < 3: return 0
        return (son_5['FTHG'] + son_5['FTAG']).mean()
    ev_avg = get_avg(ev_takim)
    dep_avg = get_avg(dep_takim)
    if ev_avg < 1.8 and dep_avg < 1.8: return "⚠️ Form Düşük!"
    return "✅ Form Uygun"

def bulten_cek(key, kodlar, t):
    res = []
    for k in kodlar:
        try:
            r = requests.get(f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h', timeout=10)
            if r.status_code != 200: continue
            data = r.json()
            for m in data:
                tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                if tm.date() == t:
                    bookies = m.get('bookmakers', [])
                    if not bookies: continue
                    o = bookies[0]['markets'][0]['outcomes']
                    h = next((x['price'] for x in o if x['name'] == m['home_team']), 0)
                    a = next((x['price'] for x in o if x['name'] == m['away_team']), 0)
                    b = next((x['price'] for x in o if x['name'].lower() in ['draw', 'tie']), 0)
                    res.append({'lig': m['sport_title'], 'zaman': tm, 'ev': m['home_team'], 'dep': m['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(res)

# --- ANA PROGRAM ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ Lütfen API Key girin ve lig seçin.")
    else:
        with st.spinner("📊 Analizler ve 1Y/MS Tahminleri Yapılıyor..."):
            gecmis = futbol_veri_motoru()
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)

        if bulten.empty:
            st.warning(f"ℹ️ Seçilen liglerde {secili_tarih} tarihinde maç bulunamadı.")
        else:
            final_list, flips = [], []
            for i, m in bulten.iterrows():
                b = gecmis[
                    (gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) &
                    (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) &
                    (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))
                ].copy()
                
                if len(b) >= min_ornek:
                    iy05_p = (b['HTHG'] + b['HTAG'] >= 1).mean()
                    iy15_p = (b['HTHG'] + b['HTAG'] >= 2).mean()
                    ms15_p = (b['FTHG'] + b['FTAG'] >= 2).mean()
                    ms25_p = (b['FTHG'] + b['FTAG'] >= 3).mean()
                    ms35_p = (b['FTHG'] + b['FTAG'] >= 4).mean()
                    kg_p = ((b['FTHG'] > 0) & (b['FTAG'] > 0)).mean()
                    
                    iy_skor = (b['HTHG'].fillna(0).astype(int).astype(str) + "-" + b['HTAG'].fillna(0).astype(int).astype(str)).mode()[0]
                    ms_skor = (b['FTHG'].fillna(0).astype(int).astype(str) + "-" + b['FTAG'].fillna(0).astype(int).astype(str)).mode()[0]
                    
                    c_flip = ((b['HTR'] == 'H') & (b['FTR'] == 'A')) | ((b['HTR'] == 'A') & (b['FTR'] == 'H'))
                    if c_flip.any():
                        flips.append({'m': f"{m['ev']} - {m['dep']}", 'p': int(c_flip.mean()*100)})

                    final_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'), 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                        '1Y_05': f"{'Over' if iy05_p >= 0.5 else 'Under'} ({int(iy05_p*100)}%) {'🔥' if iy05_p >= 0.8 else ''}",
                        'İY_15': f"{'Over' if iy15_p >= 0.5 else 'Under'} ({int(iy15_p*100)}%) {'🔥' if iy15_p >= 0.8 else ''}",
                        'MS_15': f"{'Over' if ms15_p >= 0.5 else 'Under'} ({int(ms15_p*100)}%) {'🔥' if ms15_p >= 0.8 else ''}",
                        'MS_25': f"{'Over' if ms25_p >= 0.5 else 'Under'} ({int(ms25_p*100)}%) {'🔥' if ms25_p >= 0.8 else ''}",
                        'MS_35': f"{'Over' if ms35_p >= 0.5 else 'Under'} ({int(ms35_p*100)}%) {'🔥' if ms35_p >= 0.8 else ''}",
                        'KG_V': f"{'Yes' if kg_p >= 0.5 else 'No'} ({int(kg_p*100)}%) {'🔥' if kg_p >= 0.8 else ''}",
                        '1Y_SKOR': iy_skor, 'MS_SKOR': ms_skor,
                        '1Y_V': b['HTR'].mode()[0].replace('H','Home').replace('A','Away').replace('D','Draw') if not b['HTR'].mode().empty else 'Draw',
                        'MS_V': b['FTR'].mode()[0].replace('H','Home').replace('A','Away').replace('D','Draw') if not b['FTR'].mode().empty else 'Draw',
                        'FORM DURUMU': form_analizi_yap(gecmis, m['ev'], m['dep']),
                        'ÖRNEK': len(b), 'idx': i
                    })

            if final_list:
                # 1. TABLO
                st.subheader(f"⚽ {secili_tarih} Vibe Analizleri & Mod Skorlar")
                style_cols = ['1Y_05', 'İY_15', 'MS_15', 'MS_25', 'MS_35', 'KG_V', '1Y_V', 'MS_V']
                df_ana = pd.DataFrame(final_list)
                st.dataframe(df_ana.drop(columns=['idx']).style.map(style_engine, subset=style_cols), use_container_width=True)
                
                st.markdown("---")
                # 2. TABLO VE DETAYLAR
                st.subheader("📚 Detaylı Geçmiş Örnekler")
                for row in final_list:
                    with st.expander(f"🔍 {row['SAAT']} | {row['EV SAHİBİ']} vs {row['DEPLASMAN']}"):
                        m_o = bulten.loc[row['idx']]
                        b_det = gecmis[(gecmis['B365H'].between(m_o['h']-TOLERANS, m_o['h']+TOLERANS)) & (gecmis['B365D'].between(m_o['b']-TOLERANS, m_o['b']+TOLERANS)) & (gecmis['B365A'].between(m_o['a']-TOLERANS, m_o['a']+TOLERANS))].copy().sort_values('Date', ascending=False)
                        dt = pd.DataFrame()
                        dt['Tarih'] = b_det['Date'].dt.strftime('%d.%m.%Y')
                        dt['Ev'] = b_det['HomeTeam']; dt['Dep'] = b_det['AwayTeam']
                        dt['1Y_05'] = (b_det['HTHG'] + b_det['HTAG'] >= 1).map({True:'Over', False:'Under'})
                        dt['İY_15'] = (b_det['HTHG'] + b_det['HTAG'] >= 2).map({True:'Over', False:'Under'})
                        dt['MS_15'] = (b_det['FTHG'] + b_det['FTAG'] >= 2).map({True:'Over', False:'Under'})
                        dt['MS_25'] = (b_det['FTHG'] + b_det['FTAG'] >= 3).map({True:'Over', False:'Under'})
                        dt['MS_35'] = (b_det['FTHG'] + b_det['FTAG'] >= 4).map({True:'Over', False:'Under'})
                        dt['KG_V'] = ((b_det['FTHG']>0) & (b_det['FTAG']>0)).map({True:'Yes', False:'No'})
                        dt['1Y_SKOR'] = b_det['HTHG'].fillna(0).astype(int).astype(str) + "-" + b_det['HTAG'].fillna(0).astype(int).astype(str)
                        dt['MS_SKOR'] = b_det['FTHG'].fillna(0).astype(int).astype(str) + "-" + b_det['FTAG'].fillna(0).astype(int).astype(str)
                        dt['Krn'] = (b_det.get('HC', 0).fillna(0) + b_det.get('AC', 0).fillna(0)).astype(int)
                        dt['Krt'] = (b_det.get('HY', 0).fillna(0) + b_det.get('AY', 0).fillna(0)).astype(int)
                        dt['1Y_V'] = b_det['HTR'].replace({'H':'Home','A':'Away','D':'Draw'})
                        dt['MS_V'] = b_det['FTR'].replace({'H':'Home','A':'Away','D':'Draw'})
                        dt['H_Oran'] = b_det['B365H']; dt['B_Oran'] = b_det['B365D']; dt['A_Oran'] = b_det['B365A']
                        st.dataframe(dt.style.map(style_engine, subset=style_cols), use_container_width=True, hide_index=True)

                # 3. SÜRPRİZ RADARI (EN ALTA)
                if flips:
                    st.markdown("---")
                    st.subheader("🔥 HT/FT Sürpriz Radarı (1/2 - 2/1)")
                    for f in flips:
                        st.warning(f"⚠️ **{f['m']}**: %{f['p']} sürpriz geri dönüş ihtimali!")
            else: st.warning("Eşleşen örnek bulunamadı.")
