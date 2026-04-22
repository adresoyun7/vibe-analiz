import math
from datetime import datetime, timedelta

import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title="VIBE PRO EXPERT", layout="wide", page_icon="⚡")

APP_SCHEMA_VERSION = 6
if st.session_state.get("app_schema_version") != APP_SCHEMA_VERSION:
    st.session_state.clear()
    st.session_state["app_schema_version"] = APP_SCHEMA_VERSION

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@500;600;700&family=DM+Sans:wght@400;500;600&display=swap');

html, body, [class*="css"] {
    font-family: 'DM Sans', sans-serif;
    background: #0d0f14;
    color: #fff;
}
section[data-testid="stSidebar"] {
    background: #111318 !important;
    border-right: 1px solid #1e2130;
}
section[data-testid="stSidebar"] label {
    font-size: 0.82rem !important;
    color: #aaa !important;
}
.main .block-container {
    background: #0d0f14;
    padding-top: 1.2rem;
    max-width: 1500px;
}
.top-header {
    display:flex;
    align-items:flex-start;
    justify-content:space-between;
    margin-bottom:1.1rem;
}
.top-header h2 {
    font-family:'Rajdhani',sans-serif;
    font-size:1.9rem;
    font-weight:700;
    color:#fff;
    margin:0;
    letter-spacing:1px;
}
.top-header .sub {
    font-size:0.88rem;
    color:#7b8291;
    margin-top:3px;
}
.top-filters {
    display:flex;
    gap:10px;
    margin:12px 0 18px 0;
    flex-wrap:wrap;
}
.tf-chip {
    background:#111926;
    border:1px solid #1f2b3f;
    color:#77b4ff;
    padding:8px 14px;
    border-radius:999px;
    font-size:0.8rem;
    font-weight:600;
}
.mac-badge {
    background:#121826;
    border:1px solid #22304a;
    border-radius:12px;
    padding:8px 18px;
    font-family:'Rajdhani',sans-serif;
    font-size:1.5rem;
    font-weight:700;
    color:#27ae60;
    text-align:center;
    min-width:110px;
}
.mac-badge span {
    color:#7b8291;
    font-size:0.75rem;
    display:block;
    letter-spacing:1px;
}
.mac-kart {
    background:#13151e;
    border:1px solid #1e2130;
    border-radius:16px;
    padding:16px 18px;
    margin-bottom:12px;
    display:grid;
    grid-template-columns:90px 1.6fr 190px 180px 180px;
    gap:14px;
    align-items:center;
    transition:.2s ease;
}
.mac-kart:hover {
    border-color:#2a3a52;
    box-shadow:0 0 0 1px rgba(39,174,96,.12);
}
.mk-zaman { text-align:center; }
.mk-star {
    font-size:1rem;
    color:#596073;
    margin-bottom:4px;
    display:block;
}
.mk-saat {
    font-family:'Rajdhani',sans-serif;
    font-size:1.45rem;
    font-weight:700;
    color:#fff;
    line-height:1;
}
.mk-lig {
    font-size:0.68rem;
    color:#8b94a8;
    background:#1a1d26;
    border-radius:5px;
    padding:3px 8px;
    margin-top:8px;
    display:inline-block;
}
.mk-takimlar .mk-ev {
    font-size:1.06rem;
    font-weight:700;
    color:#fff;
    margin-bottom:8px;
}
.mk-takimlar .mk-dep {
    font-size:1.02rem;
    font-weight:600;
    color:#c6cfdd;
}
.mk-mini {
    font-size:0.75rem;
    color:#8f98ab;
    margin-top:8px;
}
.mk-label {
    font-size:0.66rem;
    color:#858ca0;
    letter-spacing:1px;
    text-transform:uppercase;
    margin-bottom:5px;
}
.ana-pill {
    background:#27ae60;
    color:#fff;
    font-family:'Rajdhani',sans-serif;
    font-size:1.08rem;
    font-weight:700;
    padding:5px 15px;
    border-radius:7px;
    display:inline-block;
}
.ana-pill.kirmizi { background:#c0392b; }
.ana-pill.sari { background:#c9a227; color:#111; }
.ana-pill.gri { background:#5d6779; color:#fff; }

.guven-pct {
    font-family:'Rajdhani',sans-serif;
    font-size:1.32rem;
    font-weight:700;
    color:#fff;
}
.guven-bar {
    height:6px;
    border-radius:6px;
    background:#1e2130;
    margin-top:5px;
    overflow:hidden;
}
.guven-fill { height:100%; border-radius:6px; }

.alt-pill {
    background:#17304d;
    color:#6ec1ff;
    font-size:0.82rem;
    font-weight:700;
    padding:4px 10px;
    border-radius:6px;
    display:inline-block;
    margin-bottom:8px;
}
.surp-pill {
    background:#1e2130;
    color:#f39c12;
    font-size:0.8rem;
    font-weight:700;
    padding:4px 10px;
    border-radius:6px;
    display:inline-block;
}
.surp-pill.yok { color:#e74c3c; }

.value-pill {
    display:inline-block;
    border-radius:999px;
    padding:4px 10px;
    font-size:0.74rem;
    font-weight:700;
}
.value-good { background:#183925; color:#3ddb7c; }
.value-neutral { background:#2d3444; color:#c7cfdd; }
.value-bad { background:#391212; color:#ff6b6b; }

.oran-row {
    display:flex;
    gap:12px;
    align-items:center;
}
.oran-box { text-align:center; }
.oran-box .ov {
    font-size:0.65rem;
    color:#687084;
}
.oran-box .val {
    font-size:0.98rem;
    font-weight:700;
    color:#fff;
}

.hero-boxes {
    display:grid;
    grid-template-columns:1fr 1fr 1fr;
    gap:14px;
    margin-bottom:14px;
}
.hbox {
    border-radius:16px;
    padding:20px 24px;
    text-align:center;
}
.hbox.green {
    background:linear-gradient(135deg,#153b25,#1b5636);
    border:1px solid #1f8d53;
}
.hbox.blue {
    background:linear-gradient(135deg,#102340,#173764);
    border:1px solid #2c7be5;
}
.hbox.dark {
    background:linear-gradient(135deg,#1a1d28,#232845);
    border:1px solid #2c3152;
}
.hb-label {
    font-size:0.68rem;
    color:#aeb5c3;
    letter-spacing:2px;
    text-transform:uppercase;
    margin-bottom:10px;
}
.hb-val {
    font-family:'Rajdhani',sans-serif;
    font-size:2.35rem;
    font-weight:700;
    color:#fff;
    line-height:1;
}
.hb-sub {
    font-size:0.82rem;
    color:#c0c7d3;
    margin-top:7px;
}
.hb-badge {
    display:inline-block;
    margin-top:9px;
    padding:4px 12px;
    border-radius:999px;
    font-size:0.74rem;
    font-weight:700;
}
.badge-yuksek { background:#27ae60; color:#fff; }
.badge-orta   { background:#e67e22; color:#fff; }
.badge-dusuk  { background:#c0392b; color:#fff; }

.tahmin-kart, .diger-kart, .neden-kart, .kupon-kart {
    background:#13151e;
    border:1px solid #1e2130;
    border-radius:16px;
    padding:18px 22px;
}
.tk-title {
    font-family:'Rajdhani',sans-serif;
    font-size:1.05rem;
    font-weight:700;
    color:#fff;
    letter-spacing:1px;
    margin-bottom:14px;
    text-transform:uppercase;
}
.tk-row, .diger-row {
    display:flex;
    justify-content:space-between;
    align-items:center;
    padding:10px 0;
    border-bottom:1px solid #1a1d26;
}
.tk-row:last-child, .diger-row:last-child { border-bottom:none; }
.tk-key { font-size:0.84rem; color:#9098aa; }

.risk-row {
    background:#1a1d26;
    border-radius:10px;
    padding:10px 16px;
    display:flex;
    justify-content:space-between;
    align-items:center;
    margin-top:14px;
}
.rk {
    font-size:0.8rem;
    color:#8d95a8;
    font-weight:700;
    letter-spacing:1px;
}
.risk-pill {
    padding:5px 18px;
    border-radius:7px;
    font-family:'Rajdhani',sans-serif;
    font-size:1rem;
    font-weight:700;
}
.risk-dusuk  { background:#27ae60; color:#fff; }
.risk-orta   { background:#e67e22; color:#fff; }
.risk-yuksek { background:#c0392b; color:#fff; }

.diger-left {
    display:flex;
    align-items:center;
    gap:10px;
}
.diger-icon {
    font-size:1.05rem;
    width:20px;
    text-align:center;
}
.diger-name {
    font-size:0.86rem;
    font-weight:700;
    color:#fff;
}
.diger-sub {
    font-size:0.72rem;
    color:#666;
}
.diger-badge {
    padding:4px 12px;
    border-radius:6px;
    font-size:0.84rem;
    font-weight:700;
    font-family:'Rajdhani',sans-serif;
}
.db-green { background:#183925; color:#3ddb7c; }
.db-gold  { background:#37290f; color:#f1c40f; }
.db-red   { background:#391212; color:#ff6b6b; }
.db-blue  { background:#17304d; color:#6ec1ff; }

.surpriz-radar {
    background:#2d0a0a;
    border:1px solid #e74c3c;
    border-radius:10px;
    padding:12px 18px;
    color:#ff6f6f;
    font-weight:700;
    font-size:0.9rem;
    margin-bottom:12px;
}
.neden-item {
    padding:8px 0;
    border-bottom:1px solid #1a1d26;
    color:#c7cfdd;
    font-size:0.88rem;
}
.neden-item:last-child {
    border-bottom:none;
}
</style>
""", unsafe_allow_html=True)


def format_tr_date(d):
    aylar = {
        1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
        7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"
    }
    gunler = {
        0: "Pazartesi", 1: "Salı", 2: "Çarşamba", 3: "Perşembe",
        4: "Cuma", 5: "Cumartesi", 6: "Pazar"
    }
    return f"{d.day} {aylar[d.month]} {d.year} {gunler[d.weekday()]}"


def dinamik_min_mac(tolerans: float) -> int:
    if tolerans <= 0.02:
        return 1
    elif tolerans <= 0.05:
        return 3
    elif tolerans <= 0.08:
        return 5
    elif tolerans <= 0.12:
        return 10
    return 20


def sample_factor_hesapla(sample: int, tolerans: float) -> float:
    if tolerans <= 0.02:
        hedef = 5
    elif tolerans <= 0.05:
        hedef = 10
    elif tolerans <= 0.08:
        hedef = 15
    elif tolerans <= 0.12:
        hedef = 25
    else:
        hedef = 40
    return min(0.75 + 0.25 * (sample / max(hedef, 1)), 1.0)


def tolerans_rehberi(tolerans: float):
    min_mac = dinamik_min_mac(tolerans)
    if tolerans <= 0.02:
        yorum = "Çok dar filtre. Az ama çok yakın oranlı örnekler gelir."
    elif tolerans <= 0.05:
        yorum = "Dar filtre. Örnek az olabilir ama eşleşme kalitesi yüksektir."
    elif tolerans <= 0.08:
        yorum = "Dengeli filtre. Hem kalite hem örnek sayısı dengeli."
    elif tolerans <= 0.12:
        yorum = "Biraz geniş filtre. Veri artar, benzerlik biraz düşer."
    else:
        yorum = "Geniş filtre. Sonuçlar daha genel davranabilir."
    return {
        "onerilen_tolerans": "0.08 - 0.10",
        "onerilen_min_mac": min_mac,
        "yorum": yorum,
    }


def guven_metni(sample: int, tolerans: float):
    min_mac = dinamik_min_mac(tolerans)
    if sample >= max(20, min_mac * 3):
        return "Çok Sağlam", "#27ae60"
    if sample >= max(10, min_mac * 2):
        return "Sağlıklı", "#2ecc71"
    if sample >= min_mac:
        return "Kullanılabilir", "#f39c12"
    return "Riskli", "#e74c3c"


def guven_renk(pct: int):
    if pct >= 70:
        return "#27ae60", "badge-yuksek", "Yüksek Güven"
    if pct >= 55:
        return "#e67e22", "badge-orta", "Orta Güven"
    return "#e74c3c", "badge-dusuk", "Düşük Güven"


def risk_seviyesi(pct: int, flip_p: float):
    if pct >= 70 and flip_p < 0.15:
        return "DÜŞÜK", "risk-dusuk"
    if pct >= 55:
        return "ORTA", "risk-orta"
    return "YÜKSEK", "risk-yuksek"


def tahmini_skor(b: pd.DataFrame, ms_mod: str):
    eg = math.floor(b["FTHG"].mean() + 0.5) if not b.empty else 1
    dg = math.floor(b["FTAG"].mean() + 0.5) if not b.empty else 1
    if ms_mod == "H" and eg <= dg:
        eg = dg + 1
    if ms_mod == "A" and dg <= eg:
        dg = eg + 1
    return eg, dg


def value_hesapla(model_prob: float, odds):
    if odds in (None, "-", 0):
        return None
    try:
        implied = 1 / float(odds)
        return model_prob - implied
    except Exception:
        return None


def value_sinifi(value):
    if value is None:
        return "N/A", "value-neutral"
    if value >= 0.03:
        return f"+EV %{round(value * 100, 1)}", "value-good"
    if value >= -0.02:
        return f"Nötr %{round(value * 100, 1)}", "value-neutral"
    return f"-EV %{round(abs(value) * 100, 1)}", "value-bad"


def mac_tipi(h: float, a: float):
    if abs(h - a) <= 0.50:
        return "Dengeli"
    if h < 2.0 or a < 2.0:
        return "Favori"
    return "Sürpriz Açık"


def gol_profili(avg_goal: float):
    if avg_goal < 2.2:
        return "Düşük Gollü"
    if avg_goal < 3.0:
        return "Dengeli"
    return "Yüksek Gollü"


def fake_confidence_duzelt(conf_prob: float, sample: int, tolerans: float):
    carpan = 1.0
    if tolerans <= 0.05 and sample < 10 and conf_prob > 0.80:
        carpan *= 0.75
    elif tolerans <= 0.08 and sample < 8 and conf_prob > 0.75:
        carpan *= 0.82
    return conf_prob * carpan, carpan < 1.0


@st.cache_data(ttl=86400)
def futbol_veri_motoru(sezonlar):
    if not sezonlar:
        return pd.DataFrame()

    lig_map = ["T1", "E0", "SP1", "D1", "I1", "F1", "N1", "B1", "P1", "SC0"]
    liste = []

    for k in lig_map:
        for s in sezonlar:
            try:
                url = f"https://www.football-data.co.uk/mmz4281/{s}/{k}.csv"
                df = pd.read_csv(url)
                cols = [
                    "Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HTHG", "HTAG",
                    "FTR", "HTR", "B365H", "B365D", "B365A", "HC", "AC", "HY", "AY"
                ]
                df = df[df.columns.intersection(cols)]
                temp = df.dropna(subset=["B365H", "B365D", "B365A"]).copy()
                temp["Date"] = pd.to_datetime(temp["Date"], dayfirst=True, errors="coerce")
                liste.append(temp)
            except Exception:
                continue

    return pd.concat(liste).reset_index(drop=True) if liste else pd.DataFrame()


def bulten_cek(key, kodlar, t):
    res = []

    for k in kodlar:
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{k}/odds/",
                params={
                    "apiKey": key,
                    "regions": "eu",
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                },
                timeout=12,
            )

            if r.status_code != 200:
                continue

            data = r.json()
            if not isinstance(data, list):
                continue

            for m in data:
                try:
                    tm = datetime.strptime(m["commence_time"], "%Y-%m-%dT%H:%M:%SZ") + timedelta(hours=3)
                except Exception:
                    continue

                if tm.date() != t:
                    continue

                bookies = m.get("bookmakers", [])
                if not bookies:
                    continue

                market = None
                for bk in bookies:
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
                    for team in teams:
                        if team != home:
                            away = team
                            break

                h = next((x["price"] for x in outcomes if x["name"] == home), None)
                a = next((x["price"] for x in outcomes if x["name"] == away), None)
                b = next((x["price"] for x in outcomes if str(x["name"]).lower() in ["draw", "tie", "beraberlik"]), None)

                if h is None or a is None or b is None:
                    continue

                res.append({
                    "lig": m.get("sport_title", k),
                    "zaman": tm,
                    "ev": home,
                    "dep": away,
                    "h": float(h),
                    "b": float(b),
                    "a": float(a),
                })
        except Exception:
            continue

    if not res:
        return pd.DataFrame()

    df = pd.DataFrame(res).drop_duplicates(subset=["ev", "dep", "zaman"])
    return df.sort_values("zaman").reset_index(drop=True)


def hesapla(b_df, m_row, tolerans):
    rehber = tolerans_rehberi(float(tolerans))
    onerilen_min_mac = dinamik_min_mac(float(tolerans))

    b = b_df[
        (b_df["B365H"].between(m_row["h"] - tolerans, m_row["h"] + tolerans)) &
        (b_df["B365D"].between(m_row["b"] - tolerans, m_row["b"] + tolerans)) &
        (b_df["B365A"].between(m_row["a"] - tolerans, m_row["a"] + tolerans))
    ].copy()

    if b.empty:
        return None, b

    for c in ["FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A"]:
        b[c] = pd.to_numeric(b[c], errors="coerce")

    b = b.dropna(subset=["FTHG", "FTAG", "HTHG", "HTAG", "B365H", "B365D", "B365A"])
    if b.empty:
        return None, b

    sample = len(b)

    toplam_gol = b["FTHG"] + b["FTAG"]
    ilk_yari_gol = b["HTHG"] + b["HTAG"]

    ms_vc = b["FTR"].value_counts(normalize=True)
    iy_vc = b["HTR"].value_counts(normalize=True)

    ms_mod = ms_vc.idxmax() if not ms_vc.empty else "D"
    ms_raw = float(ms_vc.get(ms_mod, 0))
    ms_side = "MS 1" if ms_mod == "H" else "MS 2" if ms_mod == "A" else "Beraberlik"

    ms1_raw = float(ms_vc.get("H", 0))
    msx_raw = float(ms_vc.get("D", 0))
    ms2_raw = float(ms_vc.get("A", 0))

    ms25_raw = (toplam_gol >= 3).mean()
    ms35_raw = (toplam_gol >= 4).mean()
    ms15_raw = (toplam_gol >= 2).mean()
    kg_raw = ((b["FTHG"] > 0) & (b["FTAG"] > 0)).mean()
    iy05_raw = (ilk_yari_gol >= 1).mean()
    iy15_raw = (ilk_yari_gol >= 2).mean()

    htft_s = b["HTR"].replace({"H": "1", "A": "2", "D": "X"}) + "/" + b["FTR"].replace({"H": "1", "A": "2", "D": "X"})
    htft_mod = htft_s.mode()[0] if not htft_s.empty else "-"
    htft_raw = float(htft_s.value_counts(normalize=True).get(htft_mod, 0)) if not htft_s.empty else 0.0

    oran_ev = float(m_row["h"])
    oran_ber = float(m_row["b"])
    oran_dep = float(m_row["a"])

    sample_factor = sample_factor_hesapla(sample, float(tolerans))
    if oran_ev < 1.40 or oran_dep < 1.40:
        oran_factor = 0.93
    elif oran_ev > 6.50 or oran_dep > 6.50:
        oran_factor = 0.95
    else:
        oran_factor = 1.0

    guven_carpani = sample_factor * oran_factor

    ms_prob = ms_raw * guven_carpani
    ou25_best_raw = max(ms25_raw, 1 - ms25_raw)
    ou25_prob = ou25_best_raw * guven_carpani
    kg_best_raw = max(kg_raw, 1 - kg_raw)
    kg_prob = kg_best_raw * guven_carpani

    ms_label = ms_side
    ou_label = "2.5 Üst" if ms25_raw >= 0.5 else "2.5 Alt"
    kg_label = "KG Var" if kg_raw >= 0.5 else "KG Yok"

    # --- KOMBO / ORTAK EŞLEŞME MOTORU ---
    cond_ms1 = (b["FTR"] == "H")
    cond_msx = (b["FTR"] == "D")
    cond_ms2 = (b["FTR"] == "A")
    cond_ust25 = (toplam_gol >= 3)
    cond_alt25 = (toplam_gol <= 2)
    cond_kg_var = ((b["FTHG"] > 0) & (b["FTAG"] > 0))
    cond_kg_yok = ~cond_kg_var

    combo_defs = [
        ("MS1 + 2.5 Üst", cond_ms1 & cond_ust25),
        ("MS1 + 2.5 Alt", cond_ms1 & cond_alt25),
        ("MS1 + KG Var", cond_ms1 & cond_kg_var),
        ("MS1 + KG Yok", cond_ms1 & cond_kg_yok),

        ("MSX + 2.5 Üst", cond_msx & cond_ust25),
        ("MSX + 2.5 Alt", cond_msx & cond_alt25),
        ("MSX + KG Var", cond_msx & cond_kg_var),
        ("MSX + KG Yok", cond_msx & cond_kg_yok),

        ("MS2 + 2.5 Üst", cond_ms2 & cond_ust25),
        ("MS2 + 2.5 Alt", cond_ms2 & cond_alt25),
        ("MS2 + KG Var", cond_ms2 & cond_kg_var),
        ("MS2 + KG Yok", cond_ms2 & cond_kg_yok),
    ]

    combo_list = []
    min_combo_hits = max(2, min(5, onerilen_min_mac))
    for combo_label, combo_cond in combo_defs:
        combo_hit = int(combo_cond.sum())
        combo_raw = float(combo_cond.mean())
        combo_conf = combo_raw * guven_carpani
        combo_conf, combo_fake_drop = fake_confidence_duzelt(combo_conf, sample, float(tolerans))

        if combo_hit >= min_combo_hits and combo_raw >= 0.18:
            combo_list.append({
                "label": combo_label,
                "raw_prob": combo_raw,
                "conf_prob": combo_conf,
                "hit": combo_hit,
                "fake_drop": combo_fake_drop,
            })

    combo_list = sorted(combo_list, key=lambda x: (x["raw_prob"], x["hit"]), reverse=True)

    if combo_list:
        best_combo = combo_list[0]
        combo_label = best_combo["label"]
        combo_p = int(round(best_combo["conf_prob"] * 100))
        combo_raw_p = int(round(best_combo["raw_prob"] * 100))
        combo_hit = int(best_combo["hit"])
        combo_var = True
    else:
        combo_label = kg_label
        kg_conf, _ = fake_confidence_duzelt(kg_best_raw * guven_carpani, sample, float(tolerans))
        combo_p = int(round(kg_conf * 100))
        combo_raw_p = int(round(kg_best_raw * 100))
        combo_hit = 0
        combo_var = False

    cands = [
        {
            "label": ms_label,
            "raw_prob": ms_raw,
            "conf_prob": ms_prob,
            "oran": oran_ev if ms_mod == "H" else oran_dep if ms_mod == "A" else oran_ber,
            "market": "ms",
        },
        {
            "label": ou_label,
            "raw_prob": ou25_best_raw,
            "conf_prob": ou25_prob,
            "oran": "-",
            "market": "ou25",
        },
        {
            "label": kg_label,
            "raw_prob": kg_best_raw,
            "conf_prob": kg_prob,
            "oran": "-",
            "market": "kg",
        },
    ]

    best = max(cands, key=lambda x: x["raw_prob"])
    best_conf, fake_drop = fake_confidence_duzelt(best["conf_prob"], sample, float(tolerans))

    ana_label = best["label"]
    ana_p = int(round(best_conf * 100))
    ana_raw_p = int(round(best["raw_prob"] * 100))
    ana_oran = best["oran"]

    others = [c for c in cands if c["label"] != ana_label]
    alt = max(others, key=lambda x: x["raw_prob"]) if others else cands[1]
    alt_conf, _ = fake_confidence_duzelt(alt["conf_prob"], sample, float(tolerans))
    alt_label = alt["label"]
    alt_p = int(round(alt_conf * 100))

    if ana_p < 35:
        ana_label = "Tahmin Zayıf"

    if iy05_raw * guven_carpani >= 0.68:
        canli_label = "İY 0.5 Üst" + (
            " · 3.5 Üst" if ms35_raw * guven_carpani >= 0.60 else
            " · 2.5 Üst" if ms25_raw * guven_carpani >= 0.60 else
            ""
        )
        canli_p = int(round(iy05_raw * guven_carpani * 100))
    elif iy15_raw * guven_carpani >= 0.55:
        canli_label = "İY 1.5 Üst"
        canli_p = int(round(iy15_raw * guven_carpani * 100))
    else:
        canli_label, canli_p = "Canlı İzle", 50

    flip_p = (((b["HTR"] == "H") & (b["FTR"] == "A")) | ((b["HTR"] == "A") & (b["FTR"] == "H"))).mean()

    risk_l, risk_cls = risk_seviyesi(ana_p, flip_p)
    eg, dg = tahmini_skor(b, ms_mod)
    gc, gb_cls, gb_lbl = guven_renk(ana_p)
    ornek_durum, ornek_renk = guven_metni(sample, float(tolerans))

    if sample < onerilen_min_mac:
        tavsiye = "Örnek az ama kullanılabilir"
    elif sample < max(10, onerilen_min_mac * 2):
        tavsiye = "Dengeli"
    elif sample > max(25, onerilen_min_mac * 3) and tolerans > 0.10:
        tavsiye = "Biraz düşürülebilir"
    else:
        tavsiye = "Uygun"

    avg_goal = float(toplam_gol.mean())
    goal_profile = gol_profili(avg_goal)
    match_type = mac_tipi(oran_ev, oran_dep)

    ana_value = value_hesapla(best["raw_prob"], best["oran"])
    ana_value_text, ana_value_cls = value_sinifi(ana_value)
    ana_value_text = ana_value_text or "N/A"
    ana_value_cls = ana_value_cls or "value-neutral"

    nedenler = [
        f"Bu oran aralığında {sample} benzer maç bulundu.",
        f"Ham ana olasılık %{ana_raw_p} seviyesinde.",
        f"Ortalama toplam gol {avg_goal:.2f} ({goal_profile}).",
        f"Maç tipi: {match_type}.",
    ]
    if combo_var:
        nedenler.append(f"Ortak eşleşme bulundu: {combo_label} (%{combo_raw_p}, {combo_hit} maç).")
    if fake_drop:
        nedenler.append("Düşük örnek + yüksek güven görüldüğü için fake confidence freni uygulandı.")
    if ana_value is not None:
        nedenler.append(f"Value hesabı: {ana_value_text}.")
    if flip_p >= 0.12:
        nedenler.append(f"HT/FT sürpriz riski %{int(round(flip_p * 100))}.")

    oynanabilir = (ana_p >= 58 and sample >= onerilen_min_mac)

    return {
        "ana_label": ana_label,
        "ana_p": ana_p,
        "ana_raw_p": ana_raw_p,
        "ana_oran": ana_oran,
        "ana_value": ana_value,
        "ana_value_text": ana_value_text,
        "ana_value_cls": ana_value_cls,
        "alt_label": alt_label,
        "alt_p": alt_p,
        "kg_label": kg_label,
        "kg_p": int(round(kg_raw * guven_carpani * 100)),
        "combo_label": combo_label,
        "combo_p": combo_p,
        "combo_raw_p": combo_raw_p,
        "combo_hit": combo_hit,
        "combo_var": combo_var,
        "combo_list": combo_list[:5],
        "canli_label": canli_label,
        "canli_p": canli_p,
        "ms_side": ms_side,
        "ms_p": int(round(ms_raw * guven_carpani * 100)),
        "ms_mod": ms_mod,
        "ms1_p": int(round(ms1_raw * guven_carpani * 100)),
        "msx_p": int(round(msx_raw * guven_carpani * 100)),
        "ms2_p": int(round(ms2_raw * guven_carpani * 100)),
        "ms25_p": int(round(ms25_raw * guven_carpani * 100)),
        "ms25a_p": int(round((1 - ms25_raw) * guven_carpani * 100)),
        "ms15_p": int(round(ms15_raw * guven_carpani * 100)),
        "ms35_p": int(round(ms35_raw * guven_carpani * 100)),
        "kg_var_p": int(round(kg_raw * guven_carpani * 100)),
        "kg_yok_p": int(round((1 - kg_raw) * guven_carpani * 100)),
        "iy05_p": int(round(iy05_raw * guven_carpani * 100)),
        "iy05a_p": int(round((1 - iy05_raw) * guven_carpani * 100)),
        "iy15_p": int(round(iy15_raw * guven_carpani * 100)),
        "iy1_p": int(round(float(iy_vc.get("H", 0)) * guven_carpani * 100)),
        "iyx_p": int(round(float(iy_vc.get("D", 0)) * guven_carpani * 100)),
        "iy2_p": int(round(float(iy_vc.get("A", 0)) * guven_carpani * 100)),
        "htft_mod": htft_mod,
        "htft_p": int(round(htft_raw * guven_carpani * 100)),
        "flip_p": flip_p,
        "risk_label": risk_l,
        "risk_cls": risk_cls,
        "eg": eg,
        "dg": dg,
        "guven_renk": gc,
        "guven_badge_cls": gb_cls,
        "guven_badge_lbl": gb_lbl,
        "ornek": sample,
        "ornek_durum": ornek_durum,
        "ornek_renk": ornek_renk,
        "onerilen_tolerans": rehber["onerilen_tolerans"],
        "onerilen_min_mac": onerilen_min_mac,
        "tolerans_yorumu": rehber["yorum"],
        "tolerans_tavsiyesi": tavsiye,
        "kullanilan_tolerans": round(float(tolerans), 2),
        "guven_carpani": round(guven_carpani, 3),
        "goal_profile": goal_profile,
        "match_type": match_type,
        "nedenler": nedenler,
        "oynanabilir": oynanabilir,
        "fake_drop": fake_drop,
    }, b.sort_values("Date", ascending=False)


for key, default in [
    ("final_list", []),
    ("detay_idx", None),
    ("filtre", "tumu"),
    ("kupona", []),
]:
    if key not in st.session_state:
        st.session_state[key] = default

FUTBOL_LIGLERI = {
    "AVRUPA KUPALARI": {
        "Şampiyonlar Ligi": "soccer_uefa_champs_league",
        "Avrupa Ligi": "soccer_uefa_europa_league",
        "Konferans Ligi": "soccer_uefa_europa_conference_league",
    },
    "TÜRKİYE": {
        "Süper Lig": "soccer_turkey_super_league",
        "1. Lig": "soccer_turkey_pTT_1_lig",
        "Türkiye Kupası": "soccer_turkey_cup",
    },
    "İNGİLTERE": {
        "Premier League": "soccer_epl",
        "FA Cup": "soccer_fa_cup",
        "EFL Cup": "soccer_england_efl_cup",
    },
    "İSPANYA": {
        "La Liga": "soccer_spain_la_liga",
        "Copa del Rey": "soccer_spain_copa_del_rey",
    },
    "ALMANYA": {
        "Bundesliga": "soccer_germany_bundesliga",
        "DFB-Pokal": "soccer_germany_dfb_pokal",
    },
    "İTALYA": {
        "Serie A": "soccer_italy_serie_a",
        "Coppa Italia": "soccer_italy_coppa_italia",
    },
    "AVRUPA DİĞER": {
        "Hollanda": "soccer_netherlands_eredivisie",
        "Belçika": "soccer_belgium_first_division",
        "Portekiz": "soccer_portugal_primeira_liga",
        "İskoçya": "soccer_spl",
    },
}


def init_league_states():
    for kat, ligler in FUTBOL_LIGLERI.items():
        group_key = f"group_{kat}"
        if group_key not in st.session_state:
            st.session_state[group_key] = False
        for _, kod in ligler.items():
            item_key = f"cb_{kod}"
            if item_key not in st.session_state:
                st.session_state[item_key] = False


def toggle_group(kat, ligler):
    group_value = st.session_state[f"group_{kat}"]
    for _, kod in ligler.items():
        st.session_state[f"cb_{kod}"] = group_value


init_league_states()
secili_kodlar = []

with st.sidebar:
    st.markdown("""
    <div style="display:flex;align-items:center;gap:10px;padding:10px 0 18px 0">
      <div style="background:#27ae60;border-radius:8px;padding:6px 10px;font-family:Rajdhani,sans-serif;font-size:1.1rem;font-weight:700;color:#fff">V</div>
      <div>
        <div style="font-family:Rajdhani,sans-serif;font-size:1.12rem;font-weight:700;color:#fff;line-height:1.1">VIBE PRO</div>
        <div style="font-family:Rajdhani,sans-serif;font-size:0.72rem;color:#27ae60;letter-spacing:2px">EXPERT v7.0</div>
      </div>
    </div>
    <div style="font-size:0.72rem;color:#555;letter-spacing:2px;text-transform:uppercase;margin-bottom:8px">KONTROL MERKEZİ</div>
    """, unsafe_allow_html=True)

    API_KEY = st.text_input("The Odds API Key", type="password")
    bugun = datetime.now().date()
    secili_tarih = st.date_input("Analiz Tarihi", value=bugun)

    st.markdown("---")

    yillar = st.multiselect(
        "Sezonlar",
        options=["2122", "2223", "2324", "2425", "2526"],
        default=["2324", "2425", "2526"],
    )
    min_ornek = st.number_input("Min. Örnek Sayısı", min_value=1, value=1)
    TOLERANS = st.slider("Oran Hassasiyeti", 0.00, 0.30, 0.08, step=0.01)
    sadece_oynanabilir = st.checkbox("🔥 Sadece oynanabilir maçlar", value=False)

    rehber = tolerans_rehberi(TOLERANS)
    st.markdown(f"""
    <div style="margin-top:10px;background:#151a23;border:1px solid #253046;border-radius:12px;padding:10px 12px">
      <div style="font-size:0.72rem;color:#8ea2c7;letter-spacing:1px;text-transform:uppercase;margin-bottom:6px">Tolerans Rehberi</div>
      <div style="font-size:0.82rem;color:#fff">Önerilen tolerans: <b>{rehber['onerilen_tolerans']}</b></div>
      <div style="font-size:0.8rem;color:#c7cfdd;margin-top:4px">Dinamik min maç: <b>{rehber['onerilen_min_mac']}</b></div>
      <div style="font-size:0.76rem;color:#7f8a9e;margin-top:6px">{rehber['yorum']}</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    for kat, ligler in FUTBOL_LIGLERI.items():
        with st.expander(kat, expanded=(kat == "TÜRKİYE")):
            st.checkbox("Tümünü Seç", key=f"group_{kat}", on_change=toggle_group, args=(kat, ligler))
            for isim, kod in ligler.items():
                st.checkbox(isim, key=f"cb_{kod}")
                if st.session_state.get(f"cb_{kod}", False):
                    secili_kodlar.append(kod)

    st.markdown("---")
    analiz_btn = st.button("🚀 ANALİZİ BAŞLAT", use_container_width=True, type="primary", key="analiz_baslat_btn")

    if "son_analiz" in st.session_state:
        st.markdown(
            f"""<div style="font-size:0.74rem;color:#666;margin-top:10px">
            Son analiz: {st.session_state.son_analiz}<br>
            Toplam maç: {st.session_state.get('toplam_mac',0)}</div>""",
            unsafe_allow_html=True,
        )

if analiz_btn:
    if not API_KEY or not secili_kodlar:
        st.error("⚠️ API Key ve en az bir lig seçin.")
    else:
        with st.spinner("📊 Veriler çekiliyor ve analiz ediliyor..."):
            gecmis = futbol_veri_motoru(tuple(yillar))
            bulten = bulten_cek(API_KEY, secili_kodlar, secili_tarih)

        final = []
        if not bulten.empty and not gecmis.empty:
            for _, m in bulten.iterrows():
                t, b_det = hesapla(gecmis, m, TOLERANS)
                if t is None:
                    continue
                if len(b_det) < min_ornek:
                    continue
                if sadece_oynanabilir and not t["oynanabilir"]:
                    continue
                final.append({"m": m.to_dict(), "t": t, "b": b_det})

        st.session_state.final_list = final
        st.session_state.detay_idx = None
        st.session_state.son_analiz = datetime.now().strftime("%d/%m/%Y %H:%M")
        st.session_state.toplam_mac = len(final)
        st.rerun()

if st.session_state.detay_idx is not None:
    idx = st.session_state.detay_idx
    item = st.session_state.final_list[idx]
    m, t, b_det = item["m"], item["t"], item["b"]

    c1, c2, c3 = st.columns([1, 6, 1])
    with c1:
        if st.button("← Geri", key="geri_btn"):
            st.session_state.detay_idx = None
            st.rerun()
    with c2:
        st.markdown(f"""
        <div style="padding:6px 0">
          <div style="font-family:Rajdhani,sans-serif;font-size:1.8rem;font-weight:700;color:#fff;letter-spacing:1px">
            {m['ev'].upper()} – {m['dep'].upper()}
          </div>
          <div style="font-size:0.84rem;color:#888;margin-top:4px">
            {m['lig']} &nbsp;·&nbsp; {format_tr_date(m['zaman'].date())} &nbsp;·&nbsp; {m['zaman'].strftime('%H:%M')}
          </div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(
            f"""<div style="text-align:right;padding-top:10px">
            <span style="font-size:0.76rem;color:#666">📊 {int(t['ornek'])} örnek</span></div>""",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    ms_label_long = "Ev Sahibi" if t["ms_mod"] == "H" else "Deplasman" if t["ms_mod"] == "A" else "Beraberlik"

    st.markdown(f"""
    <div class="hero-boxes">
      <div class="hbox green">
        <div class="hb-label">ANA TAHMİN</div>
        <div class="hb-val">{t['ana_label']}</div>
        <div class="hb-sub">Maç Sonucu: {ms_label_long}</div>
      </div>
      <div class="hbox blue">
        <div class="hb-label">GÜVEN SKORU</div>
        <div class="hb-val">{int(t['ana_p'])}%</div>
        <div><span class="hb-badge {t['guven_badge_cls']}">{t['guven_badge_lbl']}</span></div>
      </div>
      <div class="hbox dark">
        <div class="hb-label">TAHMİNİ SKOR</div>
        <div class="hb-val">{t['eg']} – {t['dg']}</div>
        <div class="hb-sub">En Olası Skor</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:#13151e;border:1px solid #1e2130;border-radius:16px;padding:14px 18px;margin-bottom:14px">
      <div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;justify-content:space-between">
        <div style="font-size:0.82rem;color:#c7cfdd">Kullanılan tolerans: <b>{t['kullanilan_tolerans']:.2f}</b> · Önerilen: <b>{t['onerilen_tolerans']}</b></div>
        <div style="font-size:0.82rem;color:#c7cfdd">Örnek: <b>{int(t['ornek'])}</b> · Dinamik min maç: <b>{t['onerilen_min_mac']}</b></div>
      </div>
      <div style="display:flex;flex-wrap:wrap;gap:14px;margin-top:8px;align-items:center">
        <span style="background:{t.get('ornek_renk', '#44506b')};color:#fff;padding:4px 10px;border-radius:999px;font-size:0.75rem;font-weight:700">{t.get('ornek_durum', 'Standart')}</span>
        <span class="value-pill {t.get('ana_value_cls', 'value-neutral')}">{t.get('ana_value_text', 'N/A')}</span>
        <span style="font-size:0.78rem;color:#8f98ab">{t['tolerans_yorumu']}</span>
        <span style="font-size:0.78rem;color:#77b4ff">Tavsiye: {t['tolerans_tavsiyesi']}</span>
        <span style="font-size:0.78rem;color:#8f98ab">Güven çarpanı: {t['guven_carpani']}</span>
        <span style="font-size:0.78rem;color:#8f98ab">Maç tipi: {t['match_type']}</span>
        <span style="font-size:0.78rem;color:#8f98ab">Gol profili: {t['goal_profile']}</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if t["flip_p"] >= 0.12:
        st.markdown(f"""
        <div class="surpriz-radar">
        🔥 SÜRPRİZ RADARI — %{int(t['flip_p']*100)} ihtimalle HT/FT sürprizi (1/2 - 2/1) tespit edildi!
        </div>""", unsafe_allow_html=True)

    left, right = st.columns(2)

    with left:
        st.markdown(f"""
        <div class="tahmin-kart">
          <div class="tk-title">MAÇ TAHMİNLERİ</div>

          <div class="tk-row">
            <span class="tk-key">🏆 Maç Sonucu <small style="color:#555">MS 1/X/2</small></span>
            <div style="display:flex;gap:18px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">1</div><div style="font-weight:700;color:#27ae60">%{int(t['ms1_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">X</div><div style="font-weight:700;color:#f1c40f">%{int(t['msx_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">2</div><div style="font-weight:700;color:#e74c3c">%{int(t['ms2_p'])}</div></div>
            </div>
          </div>

          <div class="tk-row">
            <span class="tk-key">⚽ 2.5 Üst/Alt <small style="color:#555">Toplam Gol</small></span>
            <div style="display:flex;gap:18px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Üst</div><div style="font-weight:700;color:#27ae60">%{int(t['ms25_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Alt</div><div style="font-weight:700;color:#e74c3c">%{int(t['ms25a_p'])}</div></div>
            </div>
          </div>

          <div class="tk-row">
            <span class="tk-key">🤝 Karşılıklı Gol <small style="color:#555">KG Var / Yok</small></span>
            <div style="display:flex;gap:18px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Var</div><div style="font-weight:700;color:#27ae60">%{int(t['kg_var_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Yok</div><div style="font-weight:700;color:#e74c3c">%{int(t['kg_yok_p'])}</div></div>
            </div>
          </div>

          <div class="tk-row">
            <span class="tk-key">⏱ İlk Yarı Sonucu <small style="color:#555">İY 1/X/2</small></span>
            <div style="display:flex;gap:18px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">1</div><div style="font-weight:700;color:#27ae60">%{int(t['iy1_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">X</div><div style="font-weight:700;color:#f1c40f">%{int(t['iyx_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">2</div><div style="font-weight:700;color:#e74c3c">%{int(t['iy2_p'])}</div></div>
            </div>
          </div>

          <div class="tk-row">
            <span class="tk-key">⏱ İlk Yarı 0.5 Üst/Alt</span>
            <div style="display:flex;gap:18px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Üst</div><div style="font-weight:700;color:#27ae60">%{int(t['iy05_p'])}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">Alt</div><div style="font-weight:700;color:#e74c3c">%{int(t['iy05a_p'])}</div></div>
            </div>
          </div>

          <div class="risk-row">
            <span class="rk">RİSK SEVİYESİ</span>
            <span class="risk-pill {t['risk_cls']}">{t['risk_label']}</span>
          </div>
        </div>
        """, unsafe_allow_html=True)

    with right:
        ms35a = 100 - int(t["ms35_p"])
        ms35_cls = "db-green" if t["ms35_p"] >= 50 else "db-gold"
        ms35_lbl = f"Üst %{int(t['ms35_p'])}" if t["ms35_p"] >= 50 else f"Alt %{ms35a}"

        kg_cls = "db-green" if t["kg_var_p"] >= 50 else "db-red"
        kg_lbl = f"Var %{int(t['kg_var_p'])}" if t["kg_var_p"] >= 50 else f"Yok %{int(t['kg_yok_p'])}"

        iy_cls = "db-green" if t["iy05_p"] >= 50 else "db-red"
        iy_lbl = f"Üst %{int(t['iy05_p'])}" if t["iy05_p"] >= 50 else f"Alt %{int(t['iy05a_p'])}"

        htft_cls = "db-green" if t["htft_p"] >= 40 else "db-gold"
        combo_cls = "db-gold" if t.get("combo_var", False) else "db-red"

        st.markdown(f"""
        <div class="diger-kart">
          <div class="tk-title">DİĞER ÖNERİLER</div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">🔁</span><div><div class="diger-name">HT/FT</div><div class="diger-sub">1. Yarı / Maç Sonu</div></div></div>
            <span class="diger-badge {htft_cls}">{t['htft_mod']} %{int(t['htft_p'])}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">⚽</span><div><div class="diger-name">Toplam Gol 3.5</div><div class="diger-sub">Tahmini Gol Sayısı</div></div></div>
            <span class="diger-badge {ms35_cls}">{ms35_lbl}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">⏱</span><div><div class="diger-name">İlk Yarı / 0.5 Üst</div><div class="diger-sub">İlk Yarı Toplam Gol</div></div></div>
            <span class="diger-badge {iy_cls}">{iy_lbl}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">🤝</span><div><div class="diger-name">Karşılıklı Gol</div><div class="diger-sub">KG Var / Yok</div></div></div>
            <span class="diger-badge {kg_cls}">{kg_lbl}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">🎯</span><div><div class="diger-name">Sürpriz / Kombo</div><div class="diger-sub">Ortak eşleşme</div></div></div>
            <span class="diger-badge {combo_cls}">{t.get('combo_label', 'N/A')} %{int(t.get('combo_p', 0))}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">📍</span><div><div class="diger-name">Canlı Tercih</div><div class="diger-sub">{t['canli_label']}</div></div></div>
            <span class="diger-badge db-green">%{int(t['canli_p'])}</span>
          </div>

          <div class="diger-row">
            <div class="diger-left"><span class="diger-icon">💹</span><div><div class="diger-name">Value</div><div class="diger-sub">Model vs oran</div></div></div>
            <span class="diger-badge db-blue">{t.get('ana_value_text', 'N/A')}</span>
          </div>

          <div class="risk-row" style="margin-top:14px">
            <span class="rk">ORANLAR</span>
            <div style="display:flex;gap:16px">
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">1</div><div style="font-weight:700;color:#fff;font-size:0.95rem">{m['h']:.2f}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">X</div><div style="font-weight:700;color:#fff;font-size:0.95rem">{m['b']:.2f}</div></div>
              <div style="text-align:center"><div style="font-size:0.62rem;color:#666">2</div><div style="font-weight:700;color:#fff;font-size:0.95rem">{m['a']:.2f}</div></div>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    neden_html = "".join([f'<div class="neden-item">• {x}</div>' for x in t["nedenler"]])
    st.markdown(f"""
    <div class="neden-kart" style="margin-bottom:14px">
      <div class="tk-title">NEDEN BU TAHMİN?</div>
      {neden_html}
    </div>
    """, unsafe_allow_html=True)

    if t.get("combo_list"):
        combo_rows = "".join([
            f"""
            <div class="diger-row">
              <div class="diger-left">
                <span class="diger-icon">➕</span>
                <div>
                  <div class="diger-name">{c['label']}</div>
                  <div class="diger-sub">{c['hit']} eşleşme</div>
                </div>
              </div>
              <span class="diger-badge db-gold">%{int(round(c['conf_prob'] * 100))}</span>
            </div>
            """
            for c in t["combo_list"]
        ])

        st.markdown(f"""
        <div class="diger-kart" style="margin-bottom:14px">
          <div class="tk-title">ORTAK EŞLEŞEN KOMBOLAR</div>
          {combo_rows}
        </div>
        """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="background:#13151e;border:1px solid #1e2130;border-radius:16px;padding:16px 22px;margin-bottom:0">
      <div class="tk-title" style="margin-bottom:4px">Benzer Oranlı Geçmiş Maçlar (Son {min(len(b_det), 10)})</div>
      <div style="font-size:0.72rem;color:#666">ℹ️ Tablodaki maçlar seçili oran aralığına (±{t['kullanilan_tolerans']:.2f}) en yakın bulunan benzer maçlardır.</div>
    </div>
    """, unsafe_allow_html=True)

    bd = b_det.head(10)
    dt = pd.DataFrame()
    dt["Tarih"] = bd["Date"].dt.strftime("%d.%m.%Y")
    dt["Ev Sahibi"] = bd["HomeTeam"]
    dt["Deplasman"] = bd["AwayTeam"]
    dt["İY Sonuç"] = bd["HTHG"].astype(int).astype(str) + "-" + bd["HTAG"].astype(int).astype(str)
    dt["MS Sonuç"] = bd["FTHG"].astype(int).astype(str) + "-" + bd["FTAG"].astype(int).astype(str)
    dt["2.5 GOL"] = (bd["FTHG"] + bd["FTAG"] >= 3).map({True: "Üst", False: "Alt"})
    dt["KG"] = ((bd["FTHG"] > 0) & (bd["FTAG"] > 0)).map({True: "Var", False: "Yok"})
    dt["HT/FT"] = bd["HTR"].replace({"H": "1", "A": "2", "D": "X"}) + "/" + bd["FTR"].replace({"H": "1", "A": "2", "D": "X"})

    def color_cell(val):
        v = str(val)
        if v in ["Üst", "Var", "1/1", "2/2"]:
            return "background-color:#183925;color:#3ddb7c;font-weight:700"
        if v in ["Alt", "Yok"]:
            return "background-color:#391212;color:#ff6b6b;font-weight:700"
        if "1/2" in v or "2/1" in v:
            return "background-color:#37290f;color:#f1c40f;font-weight:700"
        return ""

    st.dataframe(
        dt.style.map(color_cell, subset=["2.5 GOL", "KG", "HT/FT"]),
        use_container_width=True,
        hide_index=True,
    )

    st.stop()

fl = st.session_state.final_list

hc1, hc2 = st.columns([6, 1])
with hc1:
    st.markdown(f"""
    <div class="top-header">
      <div>
        <h2>ANA MAÇ EKRANI</h2>
        <div class="sub">{format_tr_date(secili_tarih)}</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="top-filters">
      <div class="tf-chip">📅 Kartlı görünüm</div>
      <div class="tf-chip">🎯 Detaylı tahmin ekranı</div>
      <div class="tf-chip">💹 Value odaklı analiz</div>
      <div class="tf-chip">🔥 Smart filter</div>
    </div>
    """, unsafe_allow_html=True)

with hc2:
    if fl:
        st.markdown(f"""<div class="mac-badge" style="margin-top:8px">{len(fl)}<span>MAÇ BULUNDU</span></div>""", unsafe_allow_html=True)

if not fl:
    st.markdown("""
    <div style="background:#13151e;border:1px solid #1e2130;border-radius:16px;padding:42px;text-align:center;margin-top:20px">
      <div style="font-size:2rem;margin-bottom:12px">⚡</div>
      <div style="font-family:Rajdhani,sans-serif;font-size:1.35rem;color:#fff;font-weight:700">Analizi Başlatın</div>
      <div style="font-size:0.9rem;color:#666;margin-top:6px">Sol menüden API Key ve lig seçin, ardından ANALİZİ BAŞLAT butonuna basın.</div>
    </div>
    """, unsafe_allow_html=True)
else:
    yuksek = [x for x in fl if x["t"]["ana_p"] >= 70]
    orta = [x for x in fl if 55 <= x["t"]["ana_p"] < 70]
    value_good = [x for x in fl if x["t"]["ana_value"] is not None and x["t"]["ana_value"] >= 0.03]

    fc1, fc2, fc3, fc4 = st.columns(4)
    with fc1:
        if st.button(f"Tümü {len(fl)}", use_container_width=True, key="f1"):
            st.session_state.filtre = "tumu"
            st.rerun()
    with fc2:
        if st.button(f"🔥 Yüksek Güven {len(yuksek)}", use_container_width=True, key="f2"):
            st.session_state.filtre = "yuksek"
            st.rerun()
    with fc3:
        if st.button(f"🟡 Orta Güven {len(orta)}", use_container_width=True, key="f3"):
            st.session_state.filtre = "orta"
            st.rerun()
    with fc4:
        if st.button(f"💹 +EV {len(value_good)}", use_container_width=True, key="f4"):
            st.session_state.filtre = "value"
            st.rerun()

    filtre = st.session_state.filtre
    if filtre == "yuksek":
        goster = yuksek
    elif filtre == "orta":
        goster = orta
    elif filtre == "value":
        goster = value_good
    else:
        goster = fl

    st.markdown("<br>", unsafe_allow_html=True)

    for i, item in enumerate(goster):
        m, t = item["m"], item["t"]
        real_i = fl.index(item)
        gc, _, _ = guven_renk(t["ana_p"])

        pill_cls = ""
        if "MS 2" in t["ana_label"]:
            pill_cls = "kirmizi"
        elif "Beraberlik" in t["ana_label"] or "2.5" in t["ana_label"]:
            pill_cls = "sari"
        elif "Zayıf" in t["ana_label"]:
            pill_cls = "gri"

        surp_text = t.get("combo_label", t.get("kg_label", "N/A"))
        surp_cls = "" if "Var" in surp_text or "+" in surp_text else "yok"

        kc, bc = st.columns([9, 1.4])
        with kc:
            st.markdown(f"""
            <div class="mac-kart">
              <div class="mk-zaman">
                <span class="mk-star">☆</span>
                <div class="mk-saat">{m['zaman'].strftime('%H:%M')}</div>
                <div class="mk-lig">{m['lig'][:14]}</div>
              </div>

              <div class="mk-takimlar">
                <div class="mk-ev">⬜ {m['ev']}</div>
                <div class="mk-dep">🟦 {m['dep']}</div>
                <div class="mk-mini">Maç tipi: {t['match_type']} · Gol profili: {t['goal_profile']}</div>
              </div>

              <div>
                <div class="mk-label">ANA TAHMİN</div>
                <span class="ana-pill {pill_cls}">{t['ana_label']}</span>
                <div style="margin-top:10px">
                  <div class="mk-label">GÜVEN</div>
                  <div class="guven-pct">{int(t['ana_p'])}%</div>
                  <div class="guven-bar"><div class="guven-fill" style="width:{int(t['ana_p'])}%;background:{gc}"></div></div>
                </div>
              </div>

              <div>
                <div class="mk-label">ALTERNATİF</div>
                <span class="alt-pill">{t['alt_label']}</span>
                <div style="margin-top:8px">
                  <div class="mk-label">SÜRPRİZ / KOMBO</div>
                  <span class="surp-pill {surp_cls}">{surp_text}</span>
                </div>
                <div style="margin-top:8px">
                  <span class="value-pill {t.get('ana_value_cls', 'value-neutral')}">{t.get('ana_value_text', 'N/A')}</span>
                </div>
              </div>

              <div>
                <div class="mk-label">ORANLAR</div>
                <div class="oran-row">
                  <div class="oran-box"><div class="ov">1</div><div class="val">{m['h']:.2f}</div></div>
                  <div style="color:#2a2a2a">/</div>
                  <div class="oran-box"><div class="ov">X</div><div class="val">{m['b']:.2f}</div></div>
                  <div style="color:#2a2a2a">/</div>
                  <div class="oran-box"><div class="ov">2</div><div class="val">{m['a']:.2f}</div></div>
                </div>
                <div style="margin-top:8px;font-size:0.72rem;color:#666">📊 {int(t['ornek'])} örnek · {t.get('ornek_durum', 'Standart')}</div>
              </div>
            </div>
            """, unsafe_allow_html=True)

        with bc:
            st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
            if st.button("Detay →", key=f"d_{real_i}_{i}", use_container_width=True):
                st.session_state.detay_idx = real_i
                st.rerun()
            if st.button("+ Kupona", key=f"k_{real_i}_{i}", use_container_width=True):
                lbl = f"{m['ev']} vs {m['dep']} — {t['ana_label']}"
                if lbl not in st.session_state.kupona:
                    st.session_state.kupona.append(lbl)
                st.rerun()

    if st.session_state.kupona:
        st.markdown("---")
        rows_html = "".join(
            f'<div class="tk-row"><span class="tk-key">✅ {k}</span></div>'
            for k in st.session_state.kupona
        )
        st.markdown(f"""
        <div class="kupon-kart">
          <div class="tk-title">🎫 Kuponum ({len(st.session_state.kupona)} seçim)</div>
          {rows_html}
        </div>
        """, unsafe_allow_html=True)

        if st.button("🗑️ Kuponu Temizle", key="kupon_temizle_btn"):
            st.session_state.kupona = []
            st.rerun()
