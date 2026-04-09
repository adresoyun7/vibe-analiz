import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz - AI & Export", layout="wide")

# Excel indirme için gerekli fonksiyon
def to_excel(df):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    df.to_excel(writer, index=False, sheet_name='Analiz_Sonuclari')
    writer.close()
    processed_data = output.getvalue()
    return processed_data

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
spor_turu = st.sidebar.radio("Analiz Türü", ["⚽ Futbol", "🏀 Basketbol"])
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
GEMINI_API_KEY = st.sidebar.text_input("Gemini API Key (Opsiyonel)", type="password")

bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun, min_value=bugun)
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=2)
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.45, 0.15)

# (Lig Havuzları ve Seçim Mantığı Aynı - Session State korunuyor)
FUTBOL_LIGLERI = {
    "🇹🇷 TÜRKİYE": {'Süper Lig': 'soccer_turkey_super_league', '1. Lig': 'soccer_turkey_pTT_1_lig'},
    "🇪🇺 AVRUPA": {'İngiltere': 'soccer_epl', 'İspanya': 'soccer_spain_la_liga', 'Almanya': 'soccer_germany_bundesliga', 'Romanya': 'soccer_romania_liga_1', 'Hollanda': 'soccer_netherlands_ere_divisie'}
}
BASKETBOL_LIGLERI = {
    "🏆 MAJÖR": {'Euroleague': 'basketball_euroleague', 'NBA': 'basketball_nba'},
    "🇪🇺 AVRUPA": {'Türkiye BSL': 'basketball_turkey_bsl', 'İspanya ACB': 'basketball_spain_liga_endesa'}
}

lig_havuzu = FUTBOL_LIGLERI if "Futbol" in spor_turu else BASKETBOL_LIGLERI
secili_kodlar = []

def toggler_all():
    for kat in lig_havuzu.values():
        for kod in kat.values(): st.session_state[f"cb_{kod}"] = st.session_state["genel_secici"]

st.sidebar.checkbox(f"🚀 Bütün {spor_turu} Liglerini Seç", key="genel_secici", on_change=toggler_all)

for kat_isim, ligler in lig_havuzu.items():
    with st.sidebar.expander(kat_isim):
        def toggler_kat(k=kat_isim, l=ligler):
            for kod in l.values(): st.session_state[f"cb_{kod}"] = st.session_state[f"ks_{k}"]
        st.checkbox(f"Hepsini Seç", key=f"ks_{kat_isim}", on_change=toggler_kat)
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"): secili_kodlar.append(kod)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    lig_map = {'T1':'TR','E0':'EN1','SP1':'ES1','D1':'DE1','I1':'IT1','F1':'FR1','ROM':'RO'}
    liste = []
    for k in lig_map.keys():
        try:
            url = f"https://www.football-data.co.uk/mmz4281/2425/{k}.csv"
            df = pd.read_csv(url)
            cols = ['Date','HomeTeam','AwayTeam','FTHG','FTAG','HTHG','HTAG','FTR','HTR','B365H','B365D','B365A','HC','AC','HY','AY']
            temp = df[cols].dropna().copy()
            # Analiz sütunları (Öncekiyle aynı)
            temp['C_MS25'] = (temp['FTHG'] + temp['FTAG']) > 2.5
            temp['C_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
            temp['C_KRN'] = temp['HC'] + temp['AC']
            temp['S1Y'] = temp['HTHG'].astype(int).astype(str)+"-"+temp['HTAG'].astype(int).astype(str)
            temp['SMS'] = temp['FTHG'].astype(int).astype(str)+"-"+temp['FTAG'].astype(int).astype(str)
            temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
            liste.append(temp)
        except: continue
    return pd.concat(liste) if liste else pd.DataFrame()

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

# --- ANA PROGRAM ---
st.title(f"{spor_turu} Analiz İstasyonu")

if API_KEY and secili_kodlar:
    if st.button("🚀 ANALİZİ BAŞLAT"):
        gecmis = futbol_veri_motoru() if "Futbol" in spor_turu else pd.DataFrame()
        bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)
        
        if not bulten.empty:
            final_list = []
            for i, m in bulten.sort_values(by='zaman').iterrows():
                if "Futbol" in spor_turu:
                    b = gecmis[(gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) & (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) & (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))]
                    if not b.empty and len(b) >= min_ornek:
                        final_list.append({
                            'SAAT': m['zaman'].strftime('%H:%M'), 'MAÇ': f"{m['ev']} - {m['dep']}",
                            'MS 2.5': 'Over' if b['C_MS25'].mean() > 0.5 else 'Under',
                            'KG': 'Yes' if b['C_KG'].mean() > 0.5 else 'No',
                            '1Y SKOR': b['S1Y'].mode()[0], 'MS SKOR': b['SMS'].mode()[0],
                            'KRN (ORT)': round(b['C_KRN'].mean(), 1), 'ÖRNEK': len(b)
                        })
                else: # Basketbol Özet
                    final_list.append({'SAAT': m['zaman'].strftime('%H:%M'), 'MAÇ': f"{m['ev']} - {m['dep']}", 'ORANlar': f"E:{m['h']} - D:{m['a']}", 'ÖRNEK': 0})

            if final_list:
                df_res = pd.DataFrame(final_list)
                st.dataframe(df_res, use_container_width=True)
                
                # --- EXCEL ÇIKTISI ---
                st.download_button(label="📥 Analizi Excel Olarak İndir", data=to_excel(df_res), file_name=f"Vibe_Analiz_{secili_tarih}.xlsx", mime="application/vnd.ms-excel")
                
                # --- AI YORUM (YENİ) ---
                if GEMINI_API_KEY:
                    if st.button("🤖 Gemini AI İle Maçları Yorumla"):
                        st.info("AI Analizi Hazırlanıyor... (Ersin, bu kısım veriyi Gemini'ye gönderip özet alır)")
                        # Buraya Gemini API call gelecek
            else: st.warning("Eşleşen örnek bulunamadı.")
else: st.info("Lig seçip API Key girin.")
