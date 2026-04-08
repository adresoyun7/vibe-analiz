import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz - Sürpriz Avcısı", layout="wide")

st.title("⚽ Ultra Analiz & HT/FT Sürpriz Dedektörü")
st.markdown("---")

# --- YAN MENÜ ---
st.sidebar.header("⚙️ Ayarlar")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
Dunya_Ligleri = {
    'Türkiye Süper Lig': 'soccer_turkey_super_league',
    'İngiltere Premier Lig': 'soccer_epl',
    'İspanya La Liga': 'soccer_spain_la_liga',
    'Almanya Bundesliga': 'soccer_germany_bundesliga',
    'İtalya Serie A': 'soccer_italy_serie_a',
    'Fransa Ligue 1': 'soccer_france_ligue_one'
}
secili_etiketler = st.sidebar.multiselect("Ligleri Seçin", list(Dunya_Ligleri.keys()), default=['Türkiye Süper Lig', 'İngiltere Premier Lig'])
LIG_KODLARI = [Dunya_Ligleri[lig] for lig in secili_etiketler]
TOLERANS = st.sidebar.slider("Oran Toleransı", 0.05, 0.40, 0.20)

# --- 1. VERİ YÜKLEME (HT/FT DAHİL) ---
@st.cache_data(ttl=86400)
def surpriz_veri_yukle():
    lig_dosyalari = {'E0': 'İng1', 'SP1': 'İsp1', 'D1': 'Alm1', 'I1': 'İta1', 'T1': 'Tür1', 'F1': 'Fra1'}
    sezonlar = ['2324', '2425', '2526']
    liste = []
    for kod, ad in lig_dosyalari.items():
        for sezon in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{sezon}/{kod}.csv"
                df = pd.read_csv(url)
                # HTR: İlk Yarı Sonucu, FTR: Maç Sonucu
                cols = ['HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HTHG', 'HTAG', 'FTR', 'HTR', 'B365H', 'B365D', 'B365A', 'HC', 'AC', 'HY', 'AY']
                temp = df[cols].copy()
                
                # HT/FT Sürprizlerini Tanımla (1/2 veya 2/1)
                temp['SURPRIZ'] = ((temp['HTR'] == 'H') & (temp['FTR'] == 'A')) | ((temp['HTR'] == 'A') & (temp['FTR'] == 'H'))
                temp['MS_GOL'] = temp['FTHG'] + temp['FTAG']
                temp['KG_VAR'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['MS_SKOR'] = temp['FTHG'].astype(int).astype(str) + "-" + temp['FTAG'].astype(int).astype(str)
                liste.append(temp)
            except: continue
    return pd.concat(liste) if liste else pd.DataFrame()

# (Bülten çekme fonksiyonu aynı kalıyor...)
def guncel_bulten_cek(key, secili_kodlar):
    sonuc = []
    bugun = datetime.now()
    yarin = bugun + timedelta(days=2)
    for lig_kod in secili_kodlar:
        try:
            url = f'https://api.the-odds-api.com/v4/sports/{lig_kod}/odds/?apiKey={key}&regions=eu&markets=h2h'
            resp = requests.get(url).json()
            if isinstance(resp, list):
                for mac in resp:
                    mac_zamani = datetime.strptime(mac['commence_time'], '%Y-%m-%dT%H:%M:%SZ')
                    if bugun.date() <= mac_zamani.date() <= yarin.date():
                        oranlar = mac['bookmakers'][0]['markets'][0]['outcomes']
                        h = next(o['price'] for o in oranlar if o['name'] == mac['home_team'])
                        a = next(o['price'] for o in oranlar if o['name'] == mac['away_team'])
                        b = next(o['price'] for o in oranlar if o['name'] == 'Draw')
                        sonuc.append({'lig': mac['sport_title'], 'ev': mac['home_team'], 'dep': mac['away_team'], 'h': h, 'b': b, 'a': a})
        except: continue
    return pd.DataFrame(sonuc)

def style_surpriz(val):
    if val == '🔥 SÜRPRIZ RISKI!': return 'background-color: #9b59b6; color: white; font-weight: bold;'
    if val in ['Over', 'Yes']: return 'background-color: #2ecc71; color: white;'
    if val in ['Under', 'No']: return 'background-color: #e74c3c; color: white;'
    return ''

# --- 4. ANA PROGRAM ---
if API_KEY:
    if st.button("🚀 ÇILGIN ANALİZİ BAŞLAT"):
        gecmis = surpriz_veri_yukle()
        bulten = guncel_bulten_cek(API_KEY, LIG_KODLARI)
        
        if not bulten.empty:
            for _, m in bulten.iterrows():
                benzerler = gecmis[
                    (gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) &
                    (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) &
                    (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))
                ]
                
                if len(benzerler) >= 2:
                    surpriz_sayisi = benzerler['SURPRIZ'].sum()
                    surpriz_notu = "Düşük" if surpriz_sayisi == 0 else f"🔥 {surpriz_sayisi} Örnekte Var!"
                    
                    st.subheader(f"🏟️ {m['ev']} - {m['dep']}")
                    
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        df_row = pd.DataFrame([{
                            'MS 2.5': 'Over' if benzerler['MS_GOL'].mean() > 2.5 else 'Under',
                            'KG': 'Yes' if benzerler['KG_VAR'].mean() > 0.5 else 'No',
                            'HT/FT SÜRPRIZ': '🔥 SÜRPRIZ RISKI!' if surpriz_sayisi > 0 else 'Normal',
                            'KORNER (ORT)': round((benzerler['HC'] + benzerler['AC']).mean(), 1),
                            'EN ÇOK SKOR': benzerler['MS_SKOR'].mode()[0],
                            'ÖRNEK': len(benzerler)
                        }])
                        st.dataframe(df_row.style.map(style_surpriz))
                    
                    with col2:
                        if surpriz_sayisi > 0:
                            st.warning(f"Bu oranlarla geçmişte {surpriz_sayisi} maç ters dönmüş (1/2 veya 2/1).")
                        with st.expander("Detaylar"):
                            st.table(benzerler[['HTR', 'FTR', 'MS_SKOR']].head(10))
                    st.markdown("---")
