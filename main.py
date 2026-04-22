import streamlit as st
import pandas as pd
import requests
import numpy as np
from datetime import datetime, timedelta

# =========================================================
# SAYFA
# =========================================================
st.set_page_config(page_title="Rega Tahmin", layout="wide")

# =========================================================
# CSS
# =========================================================
st.markdown("""
<style>
html, body, [class*="css"] {
    background-color: #0b1220;
    color: white;
    font-family: "Segoe UI", sans-serif;
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #08101d 0%, #0d1728 100%);
    border-right: 1px solid rgba(255,255,255,0.08);
}

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
    max-width: 1500px;
}

.rega-title {
    font-size: 34px;
    font-weight: 800;
    color: white;
    margin-bottom: 6px;
}

.rega-subtitle {
    color: #94a3b8;
    font-size: 14px;
    margin-bottom: 18px;
}

.top-badge {
    display: inline-block;
    padding: 8px 14px;
    border-radius: 999px;
    background: #111c30;
    color: #7dd3fc;
    font-size: 13px;
    border: 1px solid rgba(255,255,255,0.08);
    margin-right: 8px;
    margin-bottom: 8px;
}

.card {
    background: linear-gradient(180deg, #0e1728 0%, #111c30 100%);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    padding: 18px;
    margin-bottom: 16px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.22);
}

.match-card {
    background: linear-gradient(180deg, #0e1728 0%, #111c30 100%);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 18px;
    padding: 18px;
    margin-bottom: 14px;
    box-shadow: 0 8px 24px rgba(0,0,0,0.22);
}

.small-label {
    color: #94a3b8;
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: .6px;
}

.big-value {
    color: white;
    font-size: 26px;
    font-weight: 800;
}

.green-pill {
    display: inline-block;
    background: rgba(34,197,94,0.16);
    color: #4ade80;
    border: 1px solid rgba(34,197,94,0.28);
    border-radius: 999px;
    padding: 6px 12px;
    font-size: 13px;
    font-weight: 700;
}

.yellow-pill {
    display: inline-block;
    background: rgba(245,158,11,0.16);
    color: #fbbf24;
    border: 1px solid rgba(245,158,11,0.28);
    border-radius: 999px;
    padding: 6px 12px;
    font-size: 13px;
    font-weight: 700;
}

.red-pill {
    display: inline-block;
    background: rgba(239,68,68,0.16);
    color: #f87171;
    border: 1px solid rgba(239,68,68,0.28);
    border-radius: 999px;
    padding: 6px 12px;
    font-size: 13px;
    font-weight: 700;
}

.blue-pill {
    display: inline-block;
    background: rgba(59,130,246,0.16);
    color: #60a5fa;
    border: 1px solid rgba(59,130,246,0.28);
    border-radius: 999px;
    padding: 6px 12px;
    font-size: 13px;
    font-weight: 700;
}

.odds-box {
    text-align: center;
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 12px;
    padding: 8px;
}

hr.soft {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.08);
    margin: 14px 0;
}
</style>
""", unsafe_allow_html=True)

# =========================================================
# SESSION STATE
# =========================================================
if "coupon" not in st.session_state:
    st.session_state.coupon = []

# =========================================================
# YARDIMCI FONKSİYONLAR
# =========================================================
def safe_pct(x):
    try:
        return int(round(float(x) * 100))
    except:
        return 0

def format_team(s):
    if not isinstance(s, str):
        return ""
    return s.replace("_", " ").strip()

def pill_html(text, mode="green"):
    cls = {
        "green": "green-pill",
        "yellow": "yellow-pill",
        "red": "red-pill",
        "blue": "blue-pill"
    }.get(mode, "blue-pill")
    return f'<span class="{cls}">{text}</span>'

def progress_html(label, left_name, left_val, right_name=None, right_val=None):
    left_pct = safe_pct(left_val)
    html = f"""
    <div style="margin-bottom:14px;">
        <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
            <div style="color:white; font-weight:600;">{label}</div>
            <div style="color:#94a3b8;">%{left_pct}</div>
        </div>
        <div style="height:10px; background:#1e293b; border-radius:999px; overflow:hidden;">
            <div style="width:{left_pct}%; height:10px; background:linear-gradient(90deg,#22c55e,#84cc16);"></div>
        </div>
    </div>
    """
    if right_name is not None and right_val is not None:
        right_pct = safe_pct(right_val)
        html += f"""
        <div style="display:flex; justify-content:space-between; margin-top:2px;">
            <small style="color:#94a3b8;">{left_name}: %{left_pct}</small>
            <small style="color:#94a3b8;">{right_name}: %{right_pct}</small>
        </div>
        """
    return html

def result_label_from_code(code):
    if code == "H":
        return "MS 1"
    if code == "A":
        return "MS 2"
    return "MS X"

def iy_label_from_code(code):
    if code == "H":
        return "İY 1"
    if code == "A":
        return "İY 2"
    return "İY X"

def yes_no_label(prob, yes_text="Var", no_text="Yok"):
    return yes_text if prob >= 0.5 else no_text

def over_under_label(prob, line_name="2.5"):
    return f"{line_name} Üst" if prob >= 0.5 else f"{line_name} Alt"

def confidence_bucket(prob):
    p = safe_pct(prob)
    if p >= 75:
        return "Yüksek Güven", "green"
    if p >= 60:
        return "Orta Güven", "yellow"
    return "Riskli", "red"

def risk_bucket(prob):
    p = safe_pct(prob)
    if p >= 72:
        return "Düşük"
    if p >= 58:
        return "Orta"
    return "Yüksek"

def calc_score_prediction(df):
    if df.empty:
        return "1-0"
    home_goals = df["FTHG"].fillna(0).round().astype(int)
    away_goals = df["FTAG"].fillna(0).round().astype(int)
    score_mode = (home_goals.astype(str) + "-" + away_goals.astype(str)).mode()
    if len(score_mode) > 0:
        return score_mode.iloc[0]
    return f"{int(home_goals.mean())}-{int(away_goals.mean())}"

def style_table_cell(val):
    if pd.isna(val):
        return ''
    s = str(val)
    if any(x in s for x in ["Üst", "Var", "MS 1", "İY 1", "1/1", "2/2"]):
        return "background-color: rgba(34,197,94,0.22); color: white;"
    if any(x in s for x in ["Alt", "Yok", "MS 2", "İY 2", "2/1", "1/2"]):
        return "background-color: rgba(239,68,68,0.22); color: white;"
    if any(x in s for x in ["MS X", "İY X", "X/X"]):
        return "background-color: rgba(245,158,11,0.22); color: white;"
    return ""

def add_to_coupon(match_name, pick_name, odd_value):
    item = {"match": match_name, "pick": pick_name, "odd": float(odd_value)}
    if item not in st.session_state.coupon:
        st.session_state.coupon.append(item)

def remove_from_coupon(index):
    if 0 <= index < len(st.session_state.coupon):
        st.session_state.coupon.pop(index)

# =========================================================
# API / DATA
# =========================================================
FUTBOL_LIGLERI = {
    "🏆 AVRUPA KUPALARI": {
        "Şampiyonlar Ligi": "soccer_uefa_champs_league",
        "Avrupa Ligi": "soccer_uefa_europa_league",
        "Konferans Ligi": "soccer_uefa_europa_conference_league"
    },
    "🇹🇷 TÜRKİYE": {
        "Süper Lig": "soccer_turkey_super_league",
        "1. Lig": "soccer_turkey_1_lig"
    },
    "🇪🇺 AVRUPA MAJÖR": {
        "Premier League": "soccer_epl",
        "La Liga": "soccer_spain_la_liga",
        "Bundesliga": "soccer_germany_bundesliga",
        "Serie A": "soccer_italy_serie_a",
        "Ligue 1": "soccer_france_ligue_one"
    },
    "⚽ AVRUPA DİĞER": {
        "Hollanda": "soccer_netherlands_eredivisie",
        "Belçika": "soccer_belgium_first_division_a",
        "Portekiz": "soccer_portugal_primeira_liga",
        "İskoçya": "soccer_scotland_premiership"
    }
}

@st.cache_data(ttl=43200)
def futbol_veri_motoru(sezonlar):
    if not sezonlar:
        return pd.DataFrame()

    lig_map = {
        "T1": "TR",
        "E0": "EN1",
        "SP1": "ES1",
        "D1": "DE1",
        "I1": "IT1",
        "F1": "FR1",
        "N1": "NL",
        "B1": "BE",
        "P1": "PT",
        "SC0": "SC1"
    }

    all_frames = []

    for code in lig_map.keys():
        for season in sezonlar:
            url = f"https://www.football-data.co.uk/mmz4281/{season}/{code}.csv"
            try:
                df = pd.read_csv(url)
                need_cols = [
                    "Date", "HomeTeam", "AwayTeam",
                    "FTHG", "FTAG", "HTHG", "HTAG",
                    "FTR", "HTR", "B365H", "B365D", "B365A",
                    "HC", "AC", "HY", "AY"
                ]
                df = df[df.columns.intersection(need_cols)].copy()
                if {"B365H", "B365D", "B365A"}.issubset(df.columns):
                    df = df.dropna(subset=["B365H", "B365D", "B365A"])
                else:
                    continue

                df["Date"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
                df["LeagueKey"] = code
                all_frames.append(df)
            except:
                continue

    if not all_frames:
        return pd.DataFrame()

    out = pd.concat(all_frames, ignore_index=True)
    return out

def bulten_cek(api_key, kodlar, target_date):
    rows = []
    for sport_key in kodlar:
        try:
            url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds/"
            params = {
                "apiKey": api_key,
                "regions": "eu",
                "markets": "h2h",
                "oddsFormat": "decimal"
            }
           r = requests.get(url, params=params, timeout=15)

if r.status_code != 200:
    st.error(f"{sport_key} için API hata kodu: {r.status_code}")
    try:
        st.write(r.json())
    except:
        st.write(r.text)
    continue

            data = r.json()
            if not isinstance(data, list):
                continue

            for m in data:
                try:
                    tm = datetime.strptime(m["commence_time"], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                except:
                    continue

              if abs((tm.date() - target_date).days) > 1:
    continue

                bookmakers = m.get("bookmakers", [])
                if not bookmakers:
                    continue

                market = None
                for bk in bookmakers:
                    for mk in bk.get("markets", []):
                        if mk.get("key") == "h2h":
                            market = mk
                            break
                    if market:
                        break

                if not market:
                    continue

                outcomes = market.get("outcomes", [])
          home = m.get("home_team", "")
away = m.get("away_team", "")

if not away:
    teams = m.get("teams", [])
    for t in teams:
        if t != home:
            away = t
            break

                h_odd = next((x["price"] for x in outcomes if x["name"] == home), None)
                a_odd = next((x["price"] for x in outcomes if x["name"] == away), None)
                d_odd = next((x["price"] for x in outcomes if str(x["name"]).lower() in ["draw", "tie"]), None)

                if h_odd is None or a_odd is None or d_odd is None:
                    continue

                rows.append({
                    "lig": m.get("sport_title", sport_key),
                    "zaman": tm,
                    "ev": format_team(home),
                    "dep": format_team(away),
                    "h": float(h_odd),
                    "b": float(d_odd),
                    "a": float(a_odd)
                })
        except:
            continue

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).sort_values("zaman").reset_index(drop=True)

def analyze_match(similar_df, row):
    if similar_df.empty:
        return None

    b = similar_df.copy()
    for c in ["FTHG", "FTAG", "HTHG", "HTAG", "HC", "AC", "HY", "AY"]:
        if c in b.columns:
            b[c] = pd.to_numeric(b[c], errors="coerce").fillna(0)
        else:
            b[c] = 0

    ms1_prob = (b["FTR"] == "H").mean()
    msx_prob = (b["FTR"] == "D").mean()
    ms2_prob = (b["FTR"] == "A").mean()

    iy1_prob = (b["HTR"] == "H").mean()
    iyx_prob = (b["HTR"] == "D").mean()
    iy2_prob = (b["HTR"] == "A").mean()

    iy05_prob = ((b["HTHG"] + b["HTAG"]) >= 1).mean()
    iy15_prob = ((b["HTHG"] + b["HTAG"]) >= 2).mean()

    ms15_prob = ((b["FTHG"] + b["FTAG"]) >= 2).mean()
    ms25_prob = ((b["FTHG"] + b["FTAG"]) >= 3).mean()
    ms35_prob = ((b["FTHG"] + b["FTAG"]) >= 4).mean()

    kg_var_prob = ((b["FTHG"] > 0) & (b["FTAG"] > 0)).mean()
    kg_yok_prob = 1 - kg_var_prob

    corners_over_95 = ((b["HC"] + b["AC"]) >= 10).mean()
    cards_over_45 = ((b["HY"] + b["AY"]) >= 5).mean()

    htft_series = (
        b["HTR"].fillna("D").replace({"H": "1", "D": "X", "A": "2"})
        + "/" +
        b["FTR"].fillna("D").replace({"H": "1", "D": "X", "A": "2"})
    )
    htft_mode = htft_series.mode().iloc[0] if not htft_series.mode().empty else "1/1"
    htft_prob = htft_series.value_counts(normalize=True).get(htft_mode, 0)

    options = {
        "MS 1": ms1_prob,
        "MS X": msx_prob,
        "MS 2": ms2_prob,
        "2.5 Üst": ms25_prob,
        "2.5 Alt": 1 - ms25_prob,
        "KG Var": kg_var_prob,
        "KG Yok": kg_yok_prob,
        "İY 1": iy1_prob,
        "İY X": iyx_prob,
        "İY 2": iy2_prob
    }

    main_pick = max(options, key=options.get)
    main_prob = options[main_pick]

    alt_options = options.copy()
    alt_options.pop(main_pick, None)
    alt_pick = max(alt_options, key=alt_options.get)
    alt_prob = alt_options[alt_pick]

    risk_options = {
        "HT/FT " + htft_mode: htft_prob,
        "İY 0.5 " + ("Üst" if iy05_prob >= 0.5 else "Alt"): max(iy05_prob, 1 - iy05_prob),
        "İY 1.5 " + ("Üst" if iy15_prob >= 0.5 else "Alt"): max(iy15_prob, 1 - iy15_prob),
        "3.5 " + ("Üst" if ms35_prob >= 0.5 else "Alt"): max(ms35_prob, 1 - ms35_prob),
        "Korner 9.5 Üst": corners_over_95,
        "Kartlar 4.5 Üst": cards_over_45,
    }
    risk_pick = max(risk_options, key=risk_options.get)
    risk_prob = risk_options[risk_pick]

    score_pred = calc_score_prediction(b)
    risk_level = risk_bucket(main_prob)
    conf_label, conf_mode = confidence_bucket(main_prob)

    return {
        "main_pick": main_pick,
        "main_prob": main_prob,
        "alt_pick": alt_pick,
        "alt_prob": alt_prob,
        "risk_pick": risk_pick,
        "risk_prob": risk_prob,
        "score_pred": score_pred,
        "risk_level": risk_level,
        "conf_label": conf_label,
        "conf_mode": conf_mode,

        "ms1_prob": ms1_prob,
        "msx_prob": msx_prob,
        "ms2_prob": ms2_prob,
        "iy1_prob": iy1_prob,
        "iyx_prob": iyx_prob,
        "iy2_prob": iy2_prob,
        "iy05_prob": iy05_prob,
        "iy15_prob": iy15_prob,
        "ms15_prob": ms15_prob,
        "ms25_prob": ms25_prob,
        "ms35_prob": ms35_prob,
        "kg_var_prob": kg_var_prob,
        "kg_yok_prob": kg_yok_prob,
        "corners_over_95": corners_over_95,
        "cards_over_45": cards_over_45,
        "htft_mode": htft_mode,
        "htft_prob": htft_prob
    }

# =========================================================
# SIDEBAR
# =========================================================
with st.sidebar:
    st.markdown('<div class="rega-title">Rega Tahmin</div>', unsafe_allow_html=True)
    st.markdown('<div class="rega-subtitle">Profesyonel maç analiz paneli</div>', unsafe_allow_html=True)

    api_key = st.text_input("The Odds API Key", type="password")
    secili_tarih = st.date_input("Analiz Tarihi", value=datetime.now().date())

    st.markdown("---")
    yillar = st.multiselect(
        "Sezonlar",
        options=["2122", "2223", "2324", "2425", "2526"],
        default=["2324", "2425", "2526"]
    )

    min_ornek = st.number_input("Min. Örnek Sayısı", min_value=1, value=4, step=1)
    tolerans = st.slider("Oran Hassasiyeti", 0.02, 0.30, 0.08, 0.01)

    st.markdown("---")
    st.markdown("### Ligler")

    secili_kodlar = []
    for kategori, ligler in FUTBOL_LIGLERI.items():
        with st.expander(kategori, expanded=("TÜRKİYE" in kategori)):
            tumunu = st.checkbox(f"{kategori} - Tümünü Seç", key=f"all_{kategori}")
            for isim, kod in ligler.items():
                sec = st.checkbox(isim, value=tumunu, key=f"cb_{kod}")
                if sec:
                    secili_kodlar.append(kod)

    baslat = st.button("🚀 Analizi Başlat", use_container_width=True)

    st.markdown("---")
    st.markdown("### Kupon")
    if st.session_state.coupon:
        total_odd = 1.0
        for i, item in enumerate(st.session_state.coupon):
            total_odd *= item["odd"]
            c1, c2 = st.columns([5, 1])
            with c1:
                st.caption(f"{item['match']}")
                st.write(f"{item['pick']} @ {item['odd']:.2f}")
            with c2:
                if st.button("❌", key=f"del_coupon_{i}"):
                    remove_from_coupon(i)
                    st.rerun()
        st.markdown(f"**Toplam Oran:** {total_odd:.2f}")
    else:
        st.caption("Kupon boş.")

# =========================================================
# ANA BAŞLIK
# =========================================================
st.markdown('<div class="rega-title">Ana Maç Ekranı</div>', unsafe_allow_html=True)
st.markdown(
    f"""
    <span class="top-badge">📅 {secili_tarih.strftime('%d.%m.%Y')}</span>
    <span class="top-badge">🎯 Kartlı görünüm</span>
    <span class="top-badge">📊 Detaylı tahmin ekranı</span>
    """,
    unsafe_allow_html=True
)

# =========================================================
# ANALİZ
# =========================================================
if baslat:
    if not api_key:
        st.error("API key girmen gerekiyor.")
        st.stop()

    if not secili_kodlar:
        st.error("En az 1 lig seçmen gerekiyor.")
        st.stop()

    with st.spinner("Veriler çekiliyor ve analiz yapılıyor..."):
        gecmis = futbol_veri_motoru(yillar)
        bulten = bulten_cek(api_key, secili_kodlar, secili_tarih)

    if gecmis.empty:
        st.error("Geçmiş veri alınamadı.")
        st.stop()

    if bulten.empty:
        st.warning("Bu tarih için maç bulunamadı ya da API veri dönmedi.")
        st.stop()

    st.success(f"{len(bulten)} maç bulundu.")

    analyzed_rows = []

    for idx, m in bulten.iterrows():
        sim = gecmis[
            (gecmis["B365H"].between(m["h"] - tolerans, m["h"] + tolerans)) &
            (gecmis["B365D"].between(m["b"] - tolerans, m["b"] + tolerans)) &
            (gecmis["B365A"].between(m["a"] - tolerans, m["a"] + tolerans))
        ].copy()

        if len(sim) < min_ornek:
            continue

        analysis = analyze_match(sim, m)
        if analysis is None:
            continue

        analyzed_rows.append({
            "idx": idx,
            "lig": m["lig"],
            "saat": m["zaman"].strftime("%H:%M"),
            "ev": m["ev"],
            "dep": m["dep"],
            "h": m["h"],
            "b": m["b"],
            "a": m["a"],
            "ornek": len(sim),
            "similar_df": sim,
            "analysis": analysis
        })

    if not analyzed_rows:
        st.warning("Filtrelere göre yeterli benzer maç bulunamadı. Toleransı artır veya min. örnek sayısını düşür.")
        st.stop()

    # =====================================================
    # ANA KARTLAR
    # =====================================================
    for i, row in enumerate(analyzed_rows):
        a = row["analysis"]
        conf_html = pill_html(a["conf_label"], a["conf_mode"])
        risk_html = pill_html(a["risk_level"], "blue" if a["risk_level"] == "Orta" else ("green" if a["risk_level"] == "Düşük" else "red"))

        st.markdown(f"""
        <div class="match-card">
            <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:20px; flex-wrap:wrap;">
                
                <div style="min-width:220px;">
                    <div class="small-label">{row["lig"]} • {row["saat"]}</div>
                    <div style="font-size:28px; font-weight:800; color:white; margin-top:6px;">
                        {row["ev"]} <span style="color:#64748b;">-</span> {row["dep"]}
                    </div>
                    <div style="margin-top:12px;">{conf_html}</div>
                </div>

                <div style="min-width:150px;">
                    <div class="small-label">Ana Tahmin</div>
                    <div style="margin-top:8px;">{pill_html(a["main_pick"], "green")}</div>
                    <div style="margin-top:8px; color:#cbd5e1;">Güven: %{safe_pct(a["main_prob"])}</div>
                </div>

                <div style="min-width:150px;">
                    <div class="small-label">Alternatif</div>
                    <div style="margin-top:8px;">{pill_html(a["alt_pick"], "yellow")}</div>
                    <div style="margin-top:8px; color:#cbd5e1;">Başarı: %{safe_pct(a["alt_prob"])}</div>
                </div>

                <div style="min-width:150px;">
                    <div class="small-label">Sürpriz / Risk</div>
                    <div style="margin-top:8px;">{pill_html(a["risk_pick"], "blue")}</div>
                    <div style="margin-top:8px; color:#cbd5e1;">Risk: {risk_html}</div>
                </div>

                <div style="min-width:200px;">
                    <div class="small-label">Oranlar</div>
                    <div style="display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; margin-top:8px;">
                        <div class="odds-box"><div class="small-label">1</div><div style="font-weight:800;">{row["h"]:.2f}</div></div>
                        <div class="odds-box"><div class="small-label">X</div><div style="font-weight:800;">{row["b"]:.2f}</div></div>
                        <div class="odds-box"><div class="small-label">2</div><div style="font-weight:800;">{row["a"]:.2f}</div></div>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        btn1, btn2 = st.columns([1, 1])
        with btn1:
            if st.button(f"🧾 Kupona Ana Tahmini Ekle ({row['ev']} - {row['dep']})", key=f"coupon_main_{i}", use_container_width=True):
                odd_map = {
                    "MS 1": row["h"],
                    "MS X": row["b"],
                    "MS 2": row["a"]
                }
                add_to_coupon(f"{row['ev']} - {row['dep']}", a["main_pick"], odd_map.get(a["main_pick"], 1.50))
                st.success("Kupona eklendi.")
        with btn2:
            if st.button(f"🧾 Kupona Alternatif Ekle ({row['ev']} - {row['dep']})", key=f"coupon_alt_{i}", use_container_width=True):
                odd_map = {
                    "MS 1": row["h"],
                    "MS X": row["b"],
                    "MS 2": row["a"],
                    "2.5 Üst": 1.70,
                    "2.5 Alt": 1.70,
                    "KG Var": 1.75,
                    "KG Yok": 1.75,
                    "İY 1": 2.00,
                    "İY X": 2.00,
                    "İY 2": 2.00
                }
                add_to_coupon(f"{row['ev']} - {row['dep']}", a["alt_pick"], odd_map.get(a["alt_pick"], 1.80))
                st.success("Kupona eklendi.")

        with st.expander(f"Detaylı analiz: {row['ev']} - {row['dep']}", expanded=False):
            c1, c2, c3 = st.columns(3)
            with c1:
                st.markdown(f"""
                <div class="card">
                    <div class="small-label">Ana Tahmin</div>
                    <div class="big-value">{a["main_pick"]}</div>
                    <div style="margin-top:8px; color:#cbd5e1;">Maç için en güçlü ana seçim</div>
                </div>
                """, unsafe_allow_html=True)
            with c2:
                st.markdown(f"""
                <div class="card">
                    <div class="small-label">Güven Skoru</div>
                    <div class="big-value">%{safe_pct(a["main_prob"])}</div>
                    <div style="margin-top:8px;">{pill_html(a["conf_label"], a["conf_mode"])}</div>
                </div>
                """, unsafe_allow_html=True)
            with c3:
                st.markdown(f"""
                <div class="card">
                    <div class="small-label">Tahmini Skor</div>
                    <div class="big-value">{a["score_pred"]}</div>
                    <div style="margin-top:8px; color:#cbd5e1;">Benzer oranlı geçmiş maçlara göre</div>
                </div>
                """, unsafe_allow_html=True)

            left, right = st.columns([1.7, 1])

            with left:
                st.markdown('<div class="card">', unsafe_allow_html=True)
                st.markdown("### Maç Tahminleri")

                st.markdown(progress_html("Maç Sonucu - 1", "1", a["ms1_prob"], "Diğer", 1 - a["ms1_prob"]), unsafe_allow_html=True)
                st.markdown(progress_html("Maç Sonucu - X", "X", a["msx_prob"], "Diğer", 1 - a["msx_prob"]), unsafe_allow_html=True)
                st.markdown(progress_html("Maç Sonucu - 2", "2", a["ms2_prob"], "Diğer", 1 - a["ms2_prob"]), unsafe_allow_html=True)

                st.markdown("<hr class='soft'>", unsafe_allow_html=True)
                st.markdown(progress_html("2.5 Gol", "Üst", a["ms25_prob"], "Alt", 1 - a["ms25_prob"]), unsafe_allow_html=True)
                st.markdown(progress_html("Karşılıklı Gol", "Var", a["kg_var_prob"], "Yok", a["kg_yok_prob"]), unsafe_allow_html=True)
                st.markdown(progress_html("İlk Yarı 0.5", "Üst", a["iy05_prob"], "Alt", 1 - a["iy05_prob"]), unsafe_allow_html=True)
                st.markdown(progress_html("İlk Yarı 1.5", "Üst", a["iy15_prob"], "Alt", 1 - a["iy15_prob"]), unsafe_allow_html=True)

                st.markdown("<hr class='soft'>", unsafe_allow_html=True)
                st.markdown(progress_html("İlk Yarı Sonucu - 1", "1", a["iy1_prob"], "Diğer", 1 - a["iy1_prob"]), unsafe_allow_html=True)
                st.markdown(progress_html("İlk Yarı Sonucu - X", "X", a["iyx_prob"], "Diğer", 1 - a["iyx_prob"]), unsafe_allow_html=True)
                st.markdown(progress_html("İlk Yarı Sonucu - 2", "2", a["iy2_prob"], "Diğer", 1 - a["iy2_prob"]), unsafe_allow_html=True)

                st.markdown('</div>', unsafe_allow_html=True)

            with right:
                st.markdown(f"""
                <div class="card">
                    <div class="small-label">Diğer Öneriler</div>
                    <div style="margin-top:14px;">{pill_html(a["alt_pick"] + "  •  %" + str(safe_pct(a["alt_prob"])), "yellow")}</div>
                    <div style="margin-top:10px;">{pill_html("HT/FT " + a["htft_mode"] + "  •  %" + str(safe_pct(a["htft_prob"])), "blue")}</div>
                    <div style="margin-top:10px;">{pill_html(("Korner 9.5 Üst" if a["corners_over_95"] >= 0.5 else "Korner 9.5 Alt") + "  •  %" + str(safe_pct(max(a["corners_over_95"], 1-a["corners_over_95"]))), "green")}</div>
                    <div style="margin-top:10px;">{pill_html(("Kartlar 4.5 Üst" if a["cards_over_45"] >= 0.5 else "Kartlar 4.5 Alt") + "  •  %" + str(safe_pct(max(a["cards_over_45"], 1-a["cards_over_45"]))), "green")}</div>

                    <hr class="soft">
                    <div class="small-label">Risk Seviyesi</div>
                    <div style="margin-top:10px;">{pill_html(a["risk_level"], "green" if a["risk_level"] == "Düşük" else ("yellow" if a["risk_level"] == "Orta" else "red"))}</div>

                    <hr class="soft">
                    <div class="small-label">Oran Eşleşmesi</div>
                    <div style="margin-top:6px; color:#cbd5e1;">1: {row["h"]:.2f}</div>
                    <div style="color:#cbd5e1;">X: {row["b"]:.2f}</div>
                    <div style="color:#cbd5e1;">2: {row["a"]:.2f}</div>

                    <hr class="soft">
                    <div class="small-label">Benzer Maç Sayısı</div>
                    <div class="big-value">{row["ornek"]}</div>
                </div>
                """, unsafe_allow_html=True)

            # Benzer maçlar tablosu
            b_det = row["similar_df"].copy().sort_values("Date", ascending=False).head(10)
            htft_series = (
                b_det["HTR"].fillna("D").replace({"H": "1", "D": "X", "A": "2"})
                + "/" +
                b_det["FTR"].fillna("D").replace({"H": "1", "D": "X", "A": "2"})
            )

            dt = pd.DataFrame({
                "Tarih": b_det["Date"].dt.strftime("%d.%m.%Y"),
                "Ev Sahibi": b_det["HomeTeam"],
                "Deplasman": b_det["AwayTeam"],
                "İY Sonuç": b_det["HTHG"].fillna(0).astype(int).astype(str) + "-" + b_det["HTAG"].fillna(0).astype(int).astype(str),
                "MS Sonuç": b_det["FTHG"].fillna(0).astype(int).astype(str) + "-" + b_det["FTAG"].fillna(0).astype(int).astype(str),
                "2.5 Gol": np.where((b_det["FTHG"] + b_det["FTAG"]) >= 3, "Üst", "Alt"),
                "KG": np.where((b_det["FTHG"] > 0) & (b_det["FTAG"] > 0), "Var", "Yok"),
                "HT/FT": htft_series.values
            })

            st.markdown("### Benzer Oranlı Geçmiş Maçlar")
            st.dataframe(
                dt.style.map(style_table_cell, subset=["2.5 Gol", "KG", "HT/FT"]),
                use_container_width=True,
                hide_index=True
            )

            st.caption(f"Tablodaki maçlar seçili oran aralığına (±{tolerans:.2f}) göre bulunan benzer maçlardır.")

else:
    st.info("Soldan ayarları yapıp **Analizi Başlat** butonuna bas.")
