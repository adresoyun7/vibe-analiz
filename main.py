import streamlit as st
import pandas as pd
import requests
import io
from datetime import datetime, timedelta

# --- SAYFA AYARLARI ---
st.set_page_config(page_title="Vibe Analiz Pro Ultra", layout="wide")

def style_engine(val):
    if val in ['Over', 'Yes', 'Home']: return 'background-color: #27ae60; color: white;'
    if val in ['Under', 'No', 'Away']: return 'background-color: #c0392b; color: white;'
    if val in ['Draw', 'Tie', 'Draw']: return 'background-color: #f39c12; color: white;'
    return ''

# --- YAN MENÜ ---
st.sidebar.title("🎮 Vibe Kontrol Merkezi")
API_KEY = st.sidebar.text_input("The Odds API Key", type="password")
bugun = datetime.now().date()
secili_tarih = st.sidebar.date_input("Analiz Tarihi", value=bugun)
min_ornek = st.sidebar.number_input("Min. Örnek Sayısı", min_value=1, value=2)
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.30, 0.10)

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
for kat_isim, ligler in FUTBOL_LIGLERI.items():
    with st.sidebar.expander(kat_isim):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"):
                secili_kodlar.append(kod)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    sezonlar = ['2324', '2425', '2526']
    lig_map = {
        'T1': 'TR', 'E0': 'EN1', 'SP1': 'ES1', 'D1': 'DE1',
        'I1': 'IT1', 'F1': 'FR1', 'ROM': 'RO', 'N1': 'NL',
        'B1': 'BE', 'P1': 'PT', 'SC0': 'SC1', 'AUT': 'AT'
    }
    liste = []
    for k in lig_map.keys():
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = ['Date', 'HomeTeam', 'AwayTeam', 'FTHG', 'FTAG',
                        'HTHG', 'HTAG', 'FTR', 'HTR', 'B365H', 'B365D',
                        'B365A', 'HC', 'AC', 'HY', 'AY']
                temp = df[cols].dropna().copy()
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except:
                continue
    return pd.concat(liste) if liste else pd.DataFrame()

def bulten_cek(key, kodlar, t):
    res = []
    hata = []
    for k in kodlar:
        try:
            r = requests.get(
                f'https://api.the-odds-api.com/v4/sports/{k}/odds/?apiKey={key}&regions=eu&markets=h2h',
                timeout=10
            )
            if r.status_code == 401:
                hata.append(f"❌ {k}: API key geçersiz (401)")
                continue
            if r.status_code == 422:
                hata.append(f"❌ {k}: Geçersiz lig kodu (422)")
                continue
            if r.status_code == 429:
                hata.append(f"⏸️ {k}: Kota doldu (429)")
                continue
            if r.status_code != 200:
                hata.append(f"❌ {k}: HTTP {r.status_code}")
                continue
            data = r.json()
            if not isinstance(data, list) or not data:
                hata.append(f"ℹ️ {k}: Bülten boş")
                continue
            mac_say = 0
            for m in data:
                tm = datetime.strptime(m['commence_time'], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                if tm.date() == t:
                    mac_say += 1
                    bookies = m.get('bookmakers', [])
                    if not bookies:
                        continue
                    o = bookies[0]['markets'][0]['outcomes']
                    h = next((x['price'] for x in o if x['name'] == m['home_team']), 0)
                    a = next((x['price'] for x in o if x['name'] == m['away_team']), 0)
                    b = next((x['price'] for x in o if x['name'].lower() in ['draw', 'tie']), 0)
                    if h > 0 and a > 0:
                        res.append({
                            'lig': m['sport_title'], 'zaman': tm,
                            'ev': m['home_team'], 'dep': m['away_team'],
                            'h': h, 'b': b, 'a': a
                        })
            if mac_say == 0 and data:
                yakin = (datetime.strptime(data[0]['commence_time'], "%Y-%m-%dT%H:%M:%SZ")
                         + timedelta(hours=3)).strftime('%d.%m.%Y')
                hata.append(f"📅 {k}: {t} tarihinde maç yok. Yakın tarih: {yakin}")
        except Exception as e:
            hata.append(f"💥 {k}: {e}")

    if hata:
        with st.expander(f"🔍 Bülten Günlüğü ({len(hata)} mesaj)", expanded=len(res) == 0):
            for msg in hata:
                st.text(msg)
    return pd.DataFrame(res)

# --- ANA PROGRAM ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ Key girin ve lig seçin.")
    else:
        with st.spinner("📊 Veriler yükleniyor..."):
            gecmis = futbol_veri_motoru()
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)

        if bulten.empty:
            st.error("❌ Bülten çekilemedi.")
        elif gecmis.empty:
            st.error("❌ Geçmiş veri çekilemedi.")
        else:
            st.success(f"✅ {len(bulten)} maç bulundu.")
            final_list, flips = [], []

            for i, m in bulten.iterrows():
                b = gecmis[
                    (gecmis['B365H'].between(m['h'] - TOLERANS, m['h'] + TOLERANS)) &
                    (gecmis['B365D'].between(m['b'] - TOLERANS, m['b'] + TOLERANS)) &
                    (gecmis['B365A'].between(m['a'] - TOLERANS, m['a'] + TOLERANS))
                ]
                if len(b) < min_ornek:
                    continue

                # ── Doğru hesaplama: tüm geçmiş maçların ORTALAMASI ──────────
                # İlk yarı gol = HTHG (ev iy gol) + HTAG (dep iy gol)
                iy_gol_ser = b['HTHG'] + b['HTAG']
                ms_gol_ser = b['FTHG'] + b['FTAG']

                iy_05_oran = (iy_gol_ser > 0.5).mean()   # 0.5 üzeri iy gol yüzdesi
                ms_15_oran = (ms_gol_ser > 1.5).mean()   # 1.5 üzeri ms gol yüzdesi
                ms_25_oran = (ms_gol_ser > 2.5).mean()   # 2.5 üzeri ms gol yüzdesi
                kg_oran    = ((b['FTHG'] > 0) & (b['FTAG'] > 0)).mean()  # KG yüzdesi

                # Mod sonuç (en sık çıkan)
                iy_skor_mod = (b['HTHG'].astype(int).astype(str) + "-" +
                               b['HTAG'].astype(int).astype(str)).mode()[0]
                ms_skor_mod = (b['FTHG'].astype(int).astype(str) + "-" +
                               b['FTAG'].astype(int).astype(str)).mode()[0]

                # Flip
                c_flip = ((b['HTR'] == 'H') & (b['FTR'] == 'A')) | \
                         ((b['HTR'] == 'A') & (b['FTR'] == 'H'))
                if c_flip.any():
                    flips.append({'m': f"{m['ev']} - {m['dep']}", 'p': int(c_flip.mean() * 100)})

                final_list.append({
                    'SAAT':      m['zaman'].strftime('%H:%M'),
                    'LİG':       m['lig'],
                    'EV SAHİBİ': m['ev'],
                    'DEPLASMAN': m['dep'],
                    # Over/Under: ortalamaya göre — %50+ ise Over
                    '1Y_05':  'Over' if iy_05_oran > 0.5 else 'Under',
                    'MS_15':  'Over' if ms_15_oran > 0.5 else 'Under',
                    'MS_25':  'Over' if ms_25_oran > 0.5 else 'Under',
                    'KG_V':   'Yes'  if kg_oran    > 0.5 else 'No',
                    # Yüzdeleri de göster
                    '1Y_05_%': f"%{iy_05_oran*100:.0f}",
                    'MS_15_%': f"%{ms_15_oran*100:.0f}",
                    'MS_25_%': f"%{ms_25_oran*100:.0f}",
                    'KG_%':    f"%{kg_oran*100:.0f}",
                    '1Y_SKOR': iy_skor_mod,
                    'MS_SKOR': ms_skor_mod,
                    # Mod sonuca göre 1Y/MS tahmini
                    '1Y_V': ('Home' if b['HTR'].mode()[0] == 'H' else
                             ('Draw' if b['HTR'].mode()[0] == 'D' else 'Away')),
                    'MS_V': ('Home' if b['FTR'].mode()[0] == 'H' else
                             ('Draw' if b['FTR'].mode()[0] == 'D' else 'Away')),
                    'ÖRNEK': len(b),
                    'idx': i
                })

            if final_list:
                df_ana = pd.DataFrame(final_list)
                st.subheader(f"⚽ {secili_tarih} Vibe Analizleri")
                st.dataframe(
                    df_ana.drop(columns=['idx']).style.map(
                        style_engine,
                        subset=['1Y_05', 'MS_15', 'MS_25', 'KG_V', '1Y_V', 'MS_V']
                    ),
                    use_container_width=True
                )

                st.markdown("---")
                st.subheader("📚 Maç Detayları (Geçmiş Örnekler)")

                for row in final_list:
                    with st.expander(f"🔍 {row['SAAT']} | {row['EV SAHİBİ']} vs {row['DEPLASMAN']} "
                                     f"| {row['LİG']} | Örnek: {row['ÖRNEK']}"):
                        m_o = bulten.loc[row['idx']]
                        b_det = gecmis[
                            (gecmis['B365H'].between(m_o['h'] - TOLERANS, m_o['h'] + TOLERANS)) &
                            (gecmis['B365D'].between(m_o['b'] - TOLERANS, m_o['b'] + TOLERANS)) &
                            (gecmis['B365A'].between(m_o['a'] - TOLERANS, m_o['a'] + TOLERANS))
                        ].copy().sort_values('Date', ascending=False)

                        # Detay tablosu — her satır bir geçmiş maç
                        dt = pd.DataFrame()
                        dt['Tarih']   = b_det['Date'].dt.strftime('%d.%m.%Y')
                        dt['Ev']      = b_det['HomeTeam']
                        dt['Dep']     = b_det['AwayTeam']
                        # Doğru: HTHG + HTAG (ilk yarı toplam gol)
                        dt['1Y_05']   = (b_det['HTHG'] + b_det['HTAG'] > 0.5).map({True: 'Over', False: 'Under'})
                        dt['MS_15']   = (b_det['FTHG'] + b_det['FTAG'] > 1.5).map({True: 'Over', False: 'Under'})
                        dt['MS_25']   = (b_det['FTHG'] + b_det['FTAG'] > 2.5).map({True: 'Over', False: 'Under'})
                        dt['KG_V']    = ((b_det['FTHG'] > 0) & (b_det['FTAG'] > 0)).map({True: 'Yes', False: 'No'})
                        dt['1Y_SKOR'] = (b_det['HTHG'].astype(int).astype(str) + "-" +
                                         b_det['HTAG'].astype(int).astype(str))
                        dt['MS_SKOR'] = (b_det['FTHG'].astype(int).astype(str) + "-" +
                                         b_det['FTAG'].astype(int).astype(str))
                        dt['Krn']     = (b_det['HC'] + b_det['AC']).astype(int)
                        dt['Krt']     = (b_det['HY'] + b_det['AY']).astype(int)
                        dt['1Y_V']    = b_det['HTR'].replace({'H': 'Home', 'A': 'Away', 'D': 'Draw'})
                        dt['MS_V']    = b_det['FTR'].replace({'H': 'Home', 'A': 'Away', 'D': 'Draw'})
                        dt['H_Oran']  = b_det['B365H'].round(2)
                        dt['B_Oran']  = b_det['B365D'].round(2)
                        dt['A_Oran']  = b_det['B365A'].round(2)

                        st.dataframe(
                            dt.style.map(
                                style_engine,
                                subset=['1Y_05', 'MS_15', 'MS_25', 'KG_V', '1Y_V', 'MS_V']
                            ),
                            use_container_width=True,
                            hide_index=True
                        )

                if flips:
                    st.markdown("---")
                    st.subheader("🔥 HT/FT Sürpriz Radarı (1/2 - 2/1)")
                    for f in flips:
                        st.warning(f"⚠️ **{f['m']}**: Geçmişte bu oranlarla %{f['p']} sürpriz HT/FT dönüşü olmuş!")
            else:
                st.warning(
                    f"Bülten çekildi ({len(bulten)} maç) ama tolerans ({TOLERANS}) / "
                    f"min. örnek ({min_ornek}) kriterine uyan geçmiş maç bulunamadı. "
                    f"Toleransı artırın veya min. örneği düşürün."
                )
