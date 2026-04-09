import streamlit as st
import pandas as pd
import requests
import io
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
TOLERANS = st.sidebar.slider("Oran Hassasiyeti", 0.05, 0.45, 0.15)

# --- LİG HAVUZLARI ---
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
    "🇪🇺 AVRUPA MAJÖR": {
        'İngiltere': 'soccer_epl',
        'İspanya': 'soccer_spain_la_liga',
        'Almanya': 'soccer_germany_bundesliga',
        'İtalya': 'soccer_italy_serie_a',
        'Fransa': 'soccer_france_ligue_one'
    },
    "🇪🇺 AVRUPA DİĞER": {
        'Romanya': 'soccer_romania_liga_1',
        'Hollanda': 'soccer_netherlands_ere_divisie',
        'Belçika': 'soccer_belgium_first_division',
        'Portekiz': 'soccer_portugal_primeira_liga',
        'Avusturya': 'soccer_austria_bundesliga',
        'İskoçya': 'soccer_scotland_premier_league',
        'Polonya': 'soccer_poland_ekstraklasa'
    }
}

BASKETBOL_LIGLERI = {
    "🏆 ULUSLARARASI": {
        'Euroleague': 'basketball_euroleague',
        'NBA': 'basketball_nba'
    },
    "🇪🇺 AVRUPA LİGLERİ": {
        'Türkiye BSL': 'basketball_turkey_bsl',
        'İspanya ACB': 'basketball_spain_liga_endesa'
    }
}

lig_havuzu = FUTBOL_LIGLERI if "Futbol" in spor_turu else BASKETBOL_LIGLERI
secili_kodlar = []

st.sidebar.markdown("---")
if "genel_secici" not in st.session_state:
    st.session_state["genel_secici"] = False

def toggler_all():
    for kat in lig_havuzu.values():
        for kod in kat.values():
            st.session_state[f"cb_{kod}"] = st.session_state["genel_secici"]

st.sidebar.checkbox(
    f"🚀 Bütün {spor_turu} Liglerini Seç",
    key="genel_secici",
    on_change=toggler_all
)

for kat_isim, ligler in lig_havuzu.items():
    with st.sidebar.expander(kat_isim):
        for isim, kod in ligler.items():
            if st.checkbox(isim, key=f"cb_{kod}"):
                secili_kodlar.append(kod)

# --- VERİ MOTORU ---
@st.cache_data(ttl=86400)
def futbol_veri_motoru():
    lig_map = {
        'T1': 'TR', 'E0': 'EN1', 'SP1': 'ES1', 'D1': 'DE1',
        'I1': 'IT1', 'F1': 'FR1', 'ROM': 'RO', 'N1': 'NL',
        'B1': 'BE', 'P1': 'PT', 'SC0': 'SC1', 'AUT': 'AT'
    }
    sezonlar = ['2425', '2526']
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
                ms_gol = temp['FTHG'] + temp['FTAG']
                iy_gol = temp['HTHG'] + temp['HTAG']
                temp['C_1Y05'] = iy_gol > 0.5
                temp['C_1Y15'] = iy_gol > 1.5
                temp['C_MS15'] = ms_gol > 1.5
                temp['C_MS25'] = ms_gol > 2.5
                temp['C_MS35'] = ms_gol > 3.5
                temp['C_KG'] = (temp['FTHG'] > 0) & (temp['FTAG'] > 0)
                temp['C_KRN'] = temp['HC'] + temp['AC']
                temp['C_KRT'] = temp['HY'] + temp['AY']
                temp['C_FLIP'] = (
                    ((temp['HTR'] == 'H') & (temp['FTR'] == 'A')) |
                    ((temp['HTR'] == 'A') & (temp['FTR'] == 'H'))
                )
                temp['S1Y'] = (
                    temp['HTHG'].astype(int).astype(str) + "-" +
                    temp['HTAG'].astype(int).astype(str)
                )
                temp['SMS'] = (
                    temp['FTHG'].astype(int).astype(str) + "-" +
                    temp['FTAG'].astype(int).astype(str)
                )
                temp['Date'] = pd.to_datetime(temp['Date'], dayfirst=True, errors='coerce')
                liste.append(temp)
            except:
                continue
    return pd.concat(liste).sort_values(by='Date', ascending=False) if liste else pd.DataFrame()

# --- GELİŞTİRİLMİŞ BÜLTEN ÇEKME FONKSİYONU ---
def bulten_cek(key, kodlar, t, spor):
    all_res = []
    hata_listesi = []

    for k in kodlar:
        try:
            url = (
                f'https://api.the-odds-api.com/v4/sports/{k}/odds/'
                f'?apiKey={key}&regions=eu&markets=h2h'
            )
            r = requests.get(url, timeout=10)

            # HTTP hata kodlarını yakala
            if r.status_code == 401:
                hata_listesi.append(f"❌ {k}: API key geçersiz (HTTP 401)")
                continue
            elif r.status_code == 422:
                hata_listesi.append(f"❌ {k}: Geçersiz lig kodu (HTTP 422)")
                continue
            elif r.status_code == 429:
                hata_listesi.append(f"⏸️ {k}: API kota doldu (HTTP 429)")
                continue
            elif r.status_code != 200:
                hata_listesi.append(f"❌ {k}: HTTP {r.status_code} — {r.text[:120]}")
                continue

            data = r.json()

            if not isinstance(data, list):
                hata_listesi.append(f"⚠️ {k}: Beklenmeyen yanıt → {str(data)[:120]}")
                continue

            if len(data) == 0:
                hata_listesi.append(f"ℹ️ {k}: Bülten boş (maç yok veya lig henüz açılmadı)")
                continue

            maclar_bu_tarih = 0
            for m in data:
                try:
                    tm = datetime.strptime(
                        m['commence_time'], "%Y-%m-%dT%H:%M:%SZ"
                    ) + timedelta(hours=3)

                    if tm.date() != t:
                        continue

                    maclar_bu_tarih += 1
                    bookies = m.get('bookmakers', [])
                    if not bookies:
                        hata_listesi.append(
                            f"⚠️ {k} — {m['home_team']} vs {m['away_team']}: "
                            f"Bookmaker verisi yok"
                        )
                        continue

                    # En fazla outcome'u olan bookmaker'ı seç
                    best_bookie = max(
                        bookies,
                        key=lambda b: len(b['markets'][0]['outcomes'])
                        if b.get('markets') else 0
                    )
                    o = best_bookie['markets'][0]['outcomes']

                    h = next((x['price'] for x in o if x['name'] == m['home_team']), 0)
                    a = next((x['price'] for x in o if x['name'] == m['away_team']), 0)
                    b_oran = 0
                    if spor == "⚽ Futbol":
                        b_oran = next(
                            (x['price'] for x in o if x['name'].lower() in ['draw', 'tie']),
                            0
                        )

                    if h == 0 or a == 0:
                        hata_listesi.append(
                            f"⚠️ {k} — {m['home_team']} vs {m['away_team']}: "
                            f"Oran verisi eksik (h={h}, a={a})"
                        )
                        continue

                    all_res.append({
                        'lig': m['sport_title'],
                        'zaman': tm,
                        'ev': m['home_team'],
                        'dep': m['away_team'],
                        'h': h,
                        'b': b_oran,
                        'a': a
                    })
                except Exception as e:
                    hata_listesi.append(f"⚠️ Maç parse hatası ({k}): {e}")
                    continue

            if maclar_bu_tarih == 0 and len(data) > 0:
                # Ligin hangi tarihler için veri döndürdüğünü göster
                ilk_tarihler = []
                for m in data[:3]:
                    try:
                        tm = datetime.strptime(
                            m['commence_time'], "%Y-%m-%dT%H:%M:%SZ"
                        ) + timedelta(hours=3)
                        ilk_tarihler.append(tm.strftime('%d.%m.%Y'))
                    except:
                        pass
                hata_listesi.append(
                    f"📅 {k}: {t} tarihinde maç yok. "
                    f"Mevcut yakın tarihler: {', '.join(ilk_tarihler)}"
                )

        except requests.exceptions.Timeout:
            hata_listesi.append(f"⏱️ {k}: Bağlantı zaman aşımı (10s)")
        except requests.exceptions.ConnectionError:
            hata_listesi.append(f"🔌 {k}: Bağlantı hatası")
        except Exception as e:
            hata_listesi.append(f"💥 {k}: Beklenmeyen hata — {e}")

    # Debug bilgilerini göster
    if hata_listesi:
        with st.expander(
            f"🔍 Debug / Tanı Bilgisi ({len(hata_listesi)} mesaj) — tıkla",
            expanded=len(all_res) == 0
        ):
            for msg in hata_listesi:
                st.text(msg)

    return pd.DataFrame(all_res)


def style_engine(val):
    if val in ['Over', 'Yes', 'Home']:
        return 'background-color: #27ae60; color: white;'
    if val in ['Under', 'No', 'Away']:
        return 'background-color: #c0392b; color: white;'
    if val in ['Draw', 'Tie']:
        return 'background-color: #f39c12; color: white;'
    return ''

# --- ANA PROGRAM ---
if st.button("🚀 ANALİZİ BAŞLAT"):
    if not API_KEY:
        st.error("⚠️ Lütfen The Odds API key girin.")
    elif not secili_kodlar:
        st.error("⚠️ Lütfen en az bir lig seçin.")
    else:
        if "Futbol" in spor_turu:
            with st.spinner("📊 Geçmiş veriler yükleniyor..."):
                gecmis = futbol_veri_motoru()

            if gecmis.empty:
                st.error("❌ Geçmiş futbol verisi çekilemedi.")
            else:
                st.info(f"✅ Geçmiş veri: {len(gecmis):,} maç yüklendi.")

            with st.spinner("📡 Bülten çekiliyor..."):
                bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih, "⚽ Futbol")

            if bulten.empty:
                st.error(
                    f"❌ Seçili liglerde **{secili_tarih}** tarihinde bülten çekilemedi. "
                    f"Yukarıdaki debug bilgisini kontrol edin."
                )
                st.info(
                    f"💡 İpucu: Farklı bir tarih deneyin veya lig kodlarının "
                    f"geçerli olduğundan emin olun."
                )
            else:
                st.success(f"✅ {len(bulten)} maç bulundu.")
                final_list = []
                flips = []

                for i, m in bulten.iterrows():
                    b = gecmis[
                        (gecmis['B365H'].between(m['h'] - TOLERANS, m['h'] + TOLERANS)) &
                        (gecmis['B365D'].between(m['b'] - TOLERANS, m['b'] + TOLERANS)) &
                        (gecmis['B365A'].between(m['a'] - TOLERANS, m['a'] + TOLERANS))
                    ]

                    if len(b) >= min_ornek:
                        final_list.append({
                            'SAAT': m['zaman'].strftime('%H:%M'),
                            'LİG': m['lig'],
                            'EV SAHİBİ': m['ev'],
                            'DEPLASMAN': m['dep'],
                            '1Y 0.5': 'Over' if b['C_1Y05'].mean() > 0.5 else 'Under',
                            '1Y 1.5': 'Over' if b['C_1Y15'].mean() > 0.5 else 'Under',
                            'MS 1.5': 'Over' if b['C_MS15'].mean() > 0.5 else 'Under',
                            'MS 2.5': 'Over' if b['C_MS25'].mean() > 0.5 else 'Under',
                            'MS 3.5': 'Over' if b['C_MS35'].mean() > 0.5 else 'Under',
                            'KG': 'Yes' if b['C_KG'].mean() > 0.5 else 'No',
                            '1Y SKOR': b['S1Y'].mode()[0],
                            'MS SKOR': b['SMS'].mode()[0],
                            'KRN (ORT)': round(b['C_KRN'].mean(), 1),
                            'KRT (ORT)': round(b['C_KRT'].mean(), 1),
                            '1Y': 'Home' if b['HTR'].mode()[0] == 'H' else (
                                'Draw' if b['HTR'].mode()[0] == 'D' else 'Away'
                            ),
                            'MS': 'Home' if b['FTR'].mode()[0] == 'H' else (
                                'Draw' if b['FTR'].mode()[0] == 'D' else 'Away'
                            ),
                            'ÖRNEK': len(b),
                            'idx': i
                        })
                        if b['C_FLIP'].any():
                            flips.append({
                                'm': f"{m['ev']}-{m['dep']}",
                                'p': int(b['C_FLIP'].mean() * 100)
                            })

                if final_list:
                    df = pd.DataFrame(final_list)
                    st.subheader(f"⚽ {secili_tarih} Tarihli Futbol Analizleri")

                    styled_cols = [
                        '1Y 0.5', '1Y 1.5', 'MS 1.5', 'MS 2.5',
                        'MS 3.5', 'KG', '1Y', 'MS'
                    ]
                    st.dataframe(
                        df.drop(columns=['idx']).style.map(
                            style_engine, subset=styled_cols
                        ),
                        use_container_width=True
                    )

                    st.download_button(
                        "📥 Excel İndir",
                        to_excel(df.drop(columns=['idx'])),
                        f"Vibe_Futbol_{secili_tarih}.xlsx"
                    )

                    if flips:
                        st.subheader("🔄 Potansiyel Skor Dönüşü Olan Maçlar")
                        for f in flips:
                            st.warning(f"⚠️ {f['m']} — Geçmişte %{f['p']} dönüş oranı")
                else:
                    st.warning(
                        f"⚠️ Bülten çekildi ({len(bulten)} maç) fakat seçilen oran "
                        f"toleransı ({TOLERANS}) ve min. örnek ({min_ornek}) "
                        f"kriterlerine uyan geçmiş maç bulunamadı.\n\n"
                        f"💡 Toleransı artırmayı veya min. örnek sayısını düşürmeyi deneyin."
                    )

        else:  # 🏀 BASKETBOL
            with st.spinner("📡 Basketbol bülteni çekiliyor..."):
                bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih, "🏀 Basketbol")

            if bulten.empty:
                st.error(
                    f"❌ Seçili liglerde **{secili_tarih}** tarihinde bülten çekilemedi. "
                    f"Yukarıdaki debug bilgisini kontrol edin."
                )
            else:
                st.success(f"✅ {len(bulten)} maç bulundu.")
                basket_list = []
                for i, m in bulten.iterrows():
                    basket_list.append({
                        'SAAT': m['zaman'].strftime('%H:%M'),
                        'LİG': m['lig'],
                        'EV': m['ev'],
                        'DEP': m['dep'],
                        'EV ORANI': m['h'],
                        'DEP ORANI': m['a'],
                        'idx': i
                    })

                st.subheader(f"🏀 {secili_tarih} Tarihli Basketbol Bülteni")
                df_b = pd.DataFrame(basket_list)
                st.dataframe(df_b.drop(columns=['idx']), use_container_width=True)
                st.download_button(
                    "📥 Excel İndir",
                    to_excel(df_b.drop(columns=['idx'])),
                    f"Vibe_Basketbol_{secili_tarih}.xlsx"
                )

else:
    st.info("👈 Soldan lig seçin, API key girin ve analizi başlatın.")
