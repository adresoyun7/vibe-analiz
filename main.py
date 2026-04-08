import pandas as pd
import requests
from datetime import datetime, timedelta

# --- 1. AYARLAR ---
API_KEY = 'BURAYA_API_KEY_YAPIŞTIR' # <--- API Key'ini buraya koymayı unutma!
LIGLER = [
    'soccer_turkey_super_league', 'soccer_epl', 'soccer_spain_la_liga', 
    'soccer_germany_bundesliga', 'soccer_italy_serie_a', 'soccer_france_ligue_one'
]
TOLERANS = 0.12 # Oran benzerlik aralığı

# --- 2. DETAYLI GEÇMİŞ VERİ HAVUZU ---
@st.cache_data
def detayli_gecmis_hazirla():
    lig_dosyalari = {'İngiltere': 'E0', 'İspanya': 'SP1', 'Almanya': 'D1', 'İtalya': 'I1', 'Türkiye': 'T1', 'Fransa':'F1'}
    sezonlar = ['2324', '2425', '2526']
    liste = []
    print("⏳ Detaylı geçmiş veri havuzu oluşturuluyor (Son 3 sezon)...")
    for lig, kod in lig_dosyalari.items():
        for sezon in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{sezon}/{kod}.csv"
                df = pd.read_csv(url)
                cols = ['HomeTeam', 'AwayTeam', 'FTHG', 'FTAG', 'HTHG', 'HTAG', 'FTR', 'HTR', 'B365H', 'B365D', 'B365A']
                temp = df[cols].copy()
                
                # Detaylı Alt/Üst ve KG Hesaplamaları
                temp['MS_GOL'] = temp['FTHG'] + temp['FTAG']
                temp['1Y_GOL'] = temp['HTHG'] + temp['HTAG']
                
                temp['1Y_0.5_UST'] = temp['1Y_GOL'] > 0.5
                temp['1Y_1.5_UST'] = temp['1Y_GOL'] > 1.5
                temp['MS_1.5_UST'] = temp['MS_GOL'] > 1.5
                temp['MS_2.5_UST'] = temp['MS_GOL'] > 2.5
                temp['MS_3.5_UST'] = temp['MS_GOL'] > 3.5
                temp['KG_VAR'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                
                temp['MS_SKOR'] = temp['FTHG'].astype(int).astype(str) + "-" + temp['FTAG'].astype(int).astype(str)
                temp['1Y_SKOR'] = temp['HTHG'].astype(int).astype(str) + "-" + temp['HTAG'].astype(int).astype(str)
                
                temp['LİG_ADI'] = lig
                liste.append(temp)
            except: continue
    return pd.concat(liste)

# --- 3. SADECE BUGÜN/YARIN BÜLTENİNİ ÇEKME ---
def guncel_bulten_cek(key):
    print("📡 Bugün ve yarın oynanacak maçlar çekiliyor...")
    sonuc = []
    bugun = datetime.now()
    yarin = bugun + timedelta(days=1)
    
    for lig in LIGLER:
        url = f'https://api.the-odds-api.com/v4/sports/{lig}/odds/?apiKey={key}&regions=eu&markets=h2h'
        resp = requests.get(url).json()
        if isinstance(resp, list):
            for mac in resp:
                try:
                    # Sadece Bugün ve Yarın'ın maçlarını filtrele
                    mac_zamani = datetime.strptime(mac['commence_time'], '%Y-%m-%dT%H:%M:%SZ')
                    if not (bugun.date() <= mac_zamani.date() <= yarin.date()):
                        continue
                        
                    oranlar = mac['bookmakers'][0]['markets'][0]['outcomes']
                    h = next(o['price'] for o in oranlar if o['name'] == mac['home_team'])
                    a = next(o['price'] for o in oranlar if o['name'] == mac['away_team'])
                    b = next(o['price'] for o in oranlar if o['name'] == 'Draw')
                    
                    sonuc.append({'lig': mac['sport_title'], 'ev': mac['home_team'], 'dep': mac['away_team'], 'h': h, 'b': b, 'a': a})
                except: continue
    return pd.DataFrame(sonuc)

# --- 4. RENKLENDİRME FONKSİYONU ---
def style_cells(val):
    if val == 'Over' or val == 'Yes' or val == 'Home' or val == 'Draw' or val == 'Away':
        color = '#2ecc71' # Yeşil
    elif val == 'Under' or val == 'No':
        color = '#e74c3c' # Kırmızı
    else:
        color = '#34495e' # Gri/Siyah
    return f'background-color: {color}; color: white; font-weight: bold; text-align: center;'

# --- 5. ANA ANALİZ VE GÖRSEL TABLO ---
def detayli_vibe_paneli(api_key):
    gecmis = detayli_gecmis_hazirla()
    yarin = guncel_bulten_cek(api_key)
    
    if yarin.empty:
        print("⚠️ Bugün veya yarın için analiz edilecek maç bulunamadı.")
        return None
        
    final_list = []
    print(f"🧠 {len(yarin)} maç detaylı analiz ediliyor...")
    
    for _, m in yarin.iterrows():
        # Benzer oranlı geçmiş maçları bul
        benzerler = gecmis[
            (gecmis['B365H'].between(m['h']-TOLERANS, m['h']+TOLERANS)) &
            (gecmis['B365D'].between(m['b']-TOLERANS, m['b']+TOLERANS)) &
            (gecmis['B365A'].between(m['a']-TOLERANS, m['a']+TOLERANS))
        ]
        
        if len(benzerler) >= 3: # En az 3 örnek varsa
            # İstatistikleri hesapla (En çok biten durum)
            total = len(benzerler)
            iy_05_vibe = 'Over' if (benzerler['1Y_0.5_UST'].mean() > 0.5) else 'Under'
            iy_15_vibe = 'Over' if (benzerler['1Y_1.5_UST'].mean() > 0.5) else 'Under'
            ms_15_vibe = 'Over' if (benzerler['MS_1.5_UST'].mean() > 0.5) else 'Under'
            ms_25_vibe = 'Over' if (benzerler['MS_2.5_UST'].mean() > 0.5) else 'Under'
            ms_3.5_vibe = 'Over' if (benzerler['MS_3.5_UST'].mean() > 0.5) else 'Under'
            kg_vibe = 'Yes' if (benzerler['KG_VAR'].mean() > 0.5) else 'No'
            
            iy_skor = benzerler['1Y_SKOR'].mode()[0]
            ms_skor = benzerler['MS_SKOR'].mode()[0]
            iy_vibe = 'Home' if (benzerler['HTR'].mode()[0] == 'H') else ('Draw' if benzerler['HTR'].mode()[0] == 'D' else 'Away')
            ms_vibe = 'Home' if (benzerler['FTR'].mode()[0] == 'H') else ('Draw' if benzerler['FTR'].mode()[0] == 'D' else 'Away')
            
            final_list.append({
                'LİG': m['lig'], 'EV SAHİBİ': m['ev'], 'DEPLASMAN': m['dep'],
                'İY 0.5': iy_05_vibe, 'İY 1.5': iy_15_vibe, 
                'MS 1.5': ms_15_vibe, 'MS 2.5': ms_25_vibe, 'MS 3.5': ms_3.5_vibe,
                'KG': kg_vibe, '1Y SKOR': iy_skor, 'SKOR': ms_skor, '1Y': iy_vibe, 'MS': ms_vibe,
                'ÖRNEK': total
            })
            
    if not final_list:
        print("⚠️ Yeterli benzer geçmiş maça sahip fırsat bulunamadı.")
        return None
        
    df_final = pd.DataFrame(final_list)
    
    # Tabloyu Renklendir (İstediğin Vibe)
    styled_df = df_final.style.applymap(style_cells, subset=['İY 0.5', 'İY 1.5', 'MS 1.5', 'MS 2.5', 'MS 3.5', 'KG', '1Y', 'MS'])
    
    return styled_df

# --- ÇALIŞTIR ---
print("\n🔥 DETAYLI ANALİZ PANELİ BAŞLATILIYOR... 🔥\n")
styled_panel = detayli_vibe_paneli(API_KEY)

if styled_panel is not None:
    print("\n✅ Analiz Tamamlandı! İşte Hedeflediğin Detaylı Tablo: ✅\n")
    display(styled_panel)
else:
    print("\n⚠️ Analiz yapılamadı.")
