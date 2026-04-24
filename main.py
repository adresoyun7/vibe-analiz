import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import streamlit as st


# =========================================================
# VIBE ANALIZ PRO - MARKET GENISLETILMIS ANA KOD
# =========================================================
# Bu dosya tek basina Streamlit main.py olarak kullanilabilir.
# Gerekli paketler:
# pip install streamlit pandas numpy
#
# Beklenen mac verisi kolonlari:
# home_team, away_team, league, commence_time,
# h, d, a veya B365H, B365D, B365A
# over25, under25, btts_yes, btts_no opsiyonel
#
# Beklenen gecmis veri kolonlari:
# HomeTeam, AwayTeam, FTHG, FTAG, B365H, B365D, B365A
# Opsiyonel: HTHG, HTAG
# =========================================================


st.set_page_config(page_title="Vibe Analiz Pro", layout="wide")


# -----------------------------
# Yardimci fonksiyonlar
# -----------------------------

def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def safe_float(x, default=None):
    try:
        if pd.isna(x):
            return default
        return float(x)
    except Exception:
        return default


def implied_prob(odd: Optional[float]) -> Optional[float]:
    if odd is None or odd <= 1:
        return None
    return 1 / odd


def fair_odd(prob: float, margin: float = 0.00) -> float:
    prob = clamp(prob - margin, 0.01, 0.99)
    return round(1 / prob, 2)


def pct(x: float) -> str:
    if x is None or pd.isna(x):
        return "-"
    return f"%{round(x * 100)}"


def normalize_match_row(row: pd.Series) -> Dict:
    h = safe_float(row.get("h", row.get("B365H")))
    d = safe_float(row.get("d", row.get("B365D")))
    a = safe_float(row.get("a", row.get("B365A")))
    return {
        "home": row.get("home_team", row.get("HomeTeam", "Ev Sahibi")),
        "away": row.get("away_team", row.get("AwayTeam", "Deplasman")),
        "league": row.get("league", row.get("Div", "Lig")),
        "time": row.get("commence_time", row.get("Date", "")),
        "h": h,
        "d": d,
        "a": a,
        "over25_odd": safe_float(row.get("over25")),
        "under25_odd": safe_float(row.get("under25")),
        "btts_yes_odd": safe_float(row.get("btts_yes")),
        "btts_no_odd": safe_float(row.get("btts_no")),
    }


def get_odds_strength(h: float, d: float, a: float) -> Dict:
    probs = [implied_prob(h) or 0, implied_prob(d) or 0, implied_prob(a) or 0]
    total = sum(probs) or 1
    p_home, p_draw, p_away = [p / total for p in probs]
    fav_side = "home" if p_home >= p_away else "away"
    fav_prob = max(p_home, p_away)
    dog_prob = min(p_home, p_away)
    balance = abs(p_home - p_away)
    return {
        "p_home_market": p_home,
        "p_draw_market": p_draw,
        "p_away_market": p_away,
        "fav_side": fav_side,
        "fav_prob_market": fav_prob,
        "dog_prob_market": dog_prob,
        "balance": balance,
    }


def poisson_score_probs(home_lambda: float, away_lambda: float, max_goals: int = 7) -> Dict[Tuple[int, int], float]:
    probs = {}
    for hg in range(max_goals + 1):
        for ag in range(max_goals + 1):
            p = (math.exp(-home_lambda) * home_lambda ** hg / math.factorial(hg)) * (
                math.exp(-away_lambda) * away_lambda ** ag / math.factorial(ag)
            )
            probs[(hg, ag)] = p
    total = sum(probs.values()) or 1
    return {k: v / total for k, v in probs.items()}


def estimate_lambdas_from_odds(h: float, d: float, a: float) -> Tuple[float, float]:
    s = get_odds_strength(h, d, a)
    base_total = 2.55
    diff = clamp((s["p_home_market"] - s["p_away_market"]) * 1.35, -0.95, 0.95)
    home_lambda = clamp(base_total / 2 + diff, 0.55, 3.20)
    away_lambda = clamp(base_total / 2 - diff, 0.45, 3.00)
    return home_lambda, away_lambda


def score_market_probs(score_probs: Dict[Tuple[int, int], float]) -> Dict[str, float]:
    p_home = sum(p for (h, a), p in score_probs.items() if h > a)
    p_draw = sum(p for (h, a), p in score_probs.items() if h == a)
    p_away = sum(p for (h, a), p in score_probs.items() if h < a)
    p_over15 = sum(p for (h, a), p in score_probs.items() if h + a >= 2)
    p_under35 = sum(p for (h, a), p in score_probs.items() if h + a <= 3)
    p_under45 = sum(p for (h, a), p in score_probs.items() if h + a <= 4)
    p_over25 = sum(p for (h, a), p in score_probs.items() if h + a >= 3)
    p_under25 = sum(p for (h, a), p in score_probs.items() if h + a <= 2)
    p_btts_yes = sum(p for (h, a), p in score_probs.items() if h >= 1 and a >= 1)
    p_btts_no = 1 - p_btts_yes
    p_home_goal = sum(p for (h, a), p in score_probs.items() if h >= 1)
    p_away_goal = sum(p for (h, a), p in score_probs.items() if a >= 1)
    p_home_double = p_home + p_draw
    p_away_double = p_away + p_draw
    p_12 = p_home + p_away
    p_home_ah0 = p_home + 0.5 * p_draw
    p_away_ah0 = p_away + 0.5 * p_draw
    p_home_plus1 = p_home + p_draw + sum(p for (h, a), p in score_probs.items() if a - h == 1)
    p_away_plus1 = p_away + p_draw + sum(p for (h, a), p in score_probs.items() if h - a == 1)

    most_likely = sorted(score_probs.items(), key=lambda x: x[1], reverse=True)[:5]
    return {
        "MS 1": p_home,
        "MS X": p_draw,
        "MS 2": p_away,
        "1X": p_home_double,
        "X2": p_away_double,
        "12": p_12,
        "1.5 Üst": p_over15,
        "2.5 Üst": p_over25,
        "2.5 Alt": p_under25,
        "3.5 Alt": p_under35,
        "4.5 Alt": p_under45,
        "KG Var": p_btts_yes,
        "KG Yok": p_btts_no,
        "Ev Sahibi 0.5 Üst": p_home_goal,
        "Deplasman 0.5 Üst": p_away_goal,
        "Ev Sahibi AH 0": p_home_ah0,
        "Deplasman AH 0": p_away_ah0,
        "Ev Sahibi +1 AH": p_home_plus1,
        "Deplasman +1 AH": p_away_plus1,
        "_scores": most_likely,
    }


def historical_similarity(history_df: pd.DataFrame, h: float, d: float, a: float, tolerance: float) -> pd.DataFrame:
    required = {"B365H", "B365D", "B365A", "FTHG", "FTAG"}
    if history_df is None or history_df.empty or not required.issubset(set(history_df.columns)):
        return pd.DataFrame()

    df = history_df.copy()
    for col in ["B365H", "B365D", "B365A", "FTHG", "FTAG"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["B365H", "B365D", "B365A", "FTHG", "FTAG"])

    sim = df[
        df["B365H"].between(h - tolerance, h + tolerance)
        & df["B365D"].between(d - tolerance, d + tolerance)
        & df["B365A"].between(a - tolerance, a + tolerance)
    ].copy()
    return sim


def historical_probs(sim: pd.DataFrame) -> Dict[str, float]:
    if sim is None or sim.empty:
        return {}
    total_goals = sim["FTHG"] + sim["FTAG"]
    home = sim["FTHG"] > sim["FTAG"]
    draw = sim["FTHG"] == sim["FTAG"]
    away = sim["FTHG"] < sim["FTAG"]
    return {
        "MS 1": home.mean(),
        "MS X": draw.mean(),
        "MS 2": away.mean(),
        "1X": (home | draw).mean(),
        "X2": (away | draw).mean(),
        "12": (home | away).mean(),
        "1.5 Üst": (total_goals >= 2).mean(),
        "2.5 Üst": (total_goals >= 3).mean(),
        "2.5 Alt": (total_goals <= 2).mean(),
        "3.5 Alt": (total_goals <= 3).mean(),
        "4.5 Alt": (total_goals <= 4).mean(),
        "KG Var": ((sim["FTHG"] >= 1) & (sim["FTAG"] >= 1)).mean(),
        "KG Yok": ((sim["FTHG"] == 0) | (sim["FTAG"] == 0)).mean(),
        "Ev Sahibi 0.5 Üst": (sim["FTHG"] >= 1).mean(),
        "Deplasman 0.5 Üst": (sim["FTAG"] >= 1).mean(),
        "Ev Sahibi AH 0": home.mean() + draw.mean() * 0.5,
        "Deplasman AH 0": away.mean() + draw.mean() * 0.5,
        "Ev Sahibi +1 AH": ((sim["FTHG"] >= sim["FTAG"] - 1)).mean(),
        "Deplasman +1 AH": ((sim["FTAG"] >= sim["FTHG"] - 1)).mean(),
    }


def merge_probs(model_probs: Dict[str, float], hist_probs: Dict[str, float], sample_size: int) -> Dict[str, float]:
    result = {}
    hist_weight = clamp(sample_size / 40, 0.15, 0.58) if sample_size > 0 else 0.0
    model_weight = 1 - hist_weight
    for k, v in model_probs.items():
        if k.startswith("_"):
            continue
        hp = hist_probs.get(k)
        if hp is None:
            result[k] = v
        else:
            result[k] = model_weight * v + hist_weight * hp
    return result


@dataclass
class Pick:
    match: str
    league: str
    market: str
    prob: float
    odd: float
    risk: str
    value_score: float
    reason: str
    score_hint: str


def risk_label(prob: float) -> str:
    if prob >= 0.78:
        return "Düşük"
    if prob >= 0.68:
        return "Orta-Düşük"
    if prob >= 0.58:
        return "Orta"
    return "Yüksek"


def market_type(market: str) -> str:
    if market in ["1X", "X2", "12"]:
        return "cifte_sans"
    if "0.5 Üst" in market:
        return "takim_golu"
    if "AH" in market:
        return "handikap"
    if "Alt" in market or "Üst" in market:
        return "alt_ust"
    if "KG" in market:
        return "kg"
    if market.startswith("MS"):
        return "ms"
    return "diger"


def market_safety_bonus(market: str) -> float:
    t = market_type(market)
    bonuses = {
        "cifte_sans": 0.09,
        "takim_golu": 0.07,
        "handikap": 0.06,
        "alt_ust": 0.04,
        "kg": 0.01,
        "ms": -0.02,
    }
    if market in ["3.5 Alt", "4.5 Alt", "1.5 Üst"]:
        return 0.08
    return bonuses.get(t, 0)


def estimate_market_odd(market: str, prob: float, m: Dict) -> float:
    # Gercek oran yoksa yaklasik adil oran + bookmaker marji kullanilir.
    direct = {
        "2.5 Üst": m.get("over25_odd"),
        "2.5 Alt": m.get("under25_odd"),
        "KG Var": m.get("btts_yes_odd"),
        "KG Yok": m.get("btts_no_odd"),
        "MS 1": m.get("h"),
        "MS X": m.get("d"),
        "MS 2": m.get("a"),
    }
    if direct.get(market):
        return round(direct[market], 2)

    base = fair_odd(prob)
    if market in ["1X", "X2", "12", "1.5 Üst", "3.5 Alt", "4.5 Alt", "Ev Sahibi 0.5 Üst", "Deplasman 0.5 Üst", "Ev Sahibi +1 AH", "Deplasman +1 AH"]:
        return round(max(1.10, base * 0.91), 2)
    if "AH 0" in market:
        return round(max(1.20, base * 0.97), 2)
    return round(max(1.15, base * 0.95), 2)


def select_picks(m: Dict, probs: Dict[str, float]) -> List[Pick]:
    picks = []
    score_items = probs.get("_scores", [])
    score_hint = ", ".join([f"{s[0][0]}-{s[0][1]}" for s in score_items[:3]]) if score_items else "-"
    match_name = f"{m['home']} - {m['away']}"

    for market, prob in probs.items():
        if market.startswith("_"):
            continue
        if prob < 0.50:
            continue
        odd = estimate_market_odd(market, prob, m)
        imp = implied_prob(odd) or 0
        value = (prob - imp) + market_safety_bonus(market)
        reason = f"Model olasılığı {pct(prob)}, tahmini oran {odd}. Market tipi: {market_type(market)}."
        picks.append(Pick(match_name, m["league"], market, prob, odd, risk_label(prob), value, reason, score_hint))

    return sorted(picks, key=lambda p: (p.prob + p.value_score * 0.45 + market_safety_bonus(p.market)), reverse=True)


def ai_decision(m: Dict, picks: List[Pick], sample_size: int) -> Dict:
    if not picks:
        return {
            "main": None,
            "safe_alt": None,
            "reduced_risk": None,
            "pass_reason": "Yeterli güven üreten market yok. Bu maç pas geçilmeli.",
            "status": "PAS",
        }

    safe_markets = [p for p in picks if p.market in ["1X", "X2", "1.5 Üst", "3.5 Alt", "4.5 Alt", "Ev Sahibi +1 AH", "Deplasman +1 AH", "Ev Sahibi 0.5 Üst", "Deplasman 0.5 Üst"]]
    value_markets = [p for p in picks if p.value_score > 0.02 and p.prob >= 0.56]
    main = value_markets[0] if value_markets else picks[0]
    safe_alt = safe_markets[0] if safe_markets else picks[0]

    reduced = None
    for p in safe_markets:
        if p.prob >= main.prob or market_type(p.market) in ["cifte_sans", "handikap", "takim_golu"]:
            reduced = p
            break
    reduced = reduced or safe_alt

    pass_reasons = []
    if sample_size < 3:
        pass_reasons.append("benzer oranlı geçmiş maç sayısı düşük")
    if main.prob < 0.58:
        pass_reasons.append("ana tahmin güveni düşük")
    if main.value_score < -0.03:
        pass_reasons.append("oran/value avantajı zayıf")
    if main.risk == "Yüksek":
        pass_reasons.append("risk seviyesi yüksek")

    status = "OYNANABİLİR"
    if len(pass_reasons) >= 2:
        status = "PAS / CANLI TAKİP"
    elif pass_reasons:
        status = "DİKKATLİ"

    return {
        "main": main,
        "safe_alt": safe_alt,
        "reduced_risk": reduced,
        "pass_reason": "; ".join(pass_reasons) if pass_reasons else "Net pas sebebi yok.",
        "status": status,
    }


def analyze_match(row: pd.Series, history_df: pd.DataFrame, tolerance: float) -> Dict:
    m = normalize_match_row(row)
    if not all([m["h"], m["d"], m["a"]]):
        return {"match": m, "error": "MS oranları eksik."}

    hl, al = estimate_lambdas_from_odds(m["h"], m["d"], m["a"])
    score_probs = poisson_score_probs(hl, al)
    model_probs = score_market_probs(score_probs)
    sim = historical_similarity(history_df, m["h"], m["d"], m["a"], tolerance)
    hp = historical_probs(sim)
    merged = merge_probs(model_probs, hp, len(sim))
    merged["_scores"] = model_probs["_scores"]
    picks = select_picks(m, merged)
    decision = ai_decision(m, picks, len(sim))
    return {
        "match": m,
        "sample_size": len(sim),
        "similar_matches": sim,
        "probs": merged,
        "picks": picks,
        "decision": decision,
    }


def combo_probability(picks: List[Pick]) -> float:
    # Korelasyon riski icin cezali carpim.
    if not picks:
        return 0
    prob = 1.0
    for p in picks:
        prob *= p.prob
    corr_penalty = 0.97 ** max(0, len(picks) - 1)
    return prob * corr_penalty


def combo_odd(picks: List[Pick]) -> float:
    odd = 1.0
    for p in picks:
        odd *= p.odd
    return round(odd, 2)


def build_coupons(analyses: List[Dict]) -> Dict[str, List[Pick]]:
    all_decisions = [a for a in analyses if not a.get("error") and a.get("decision")]

    safe_candidates = []
    value_candidates = []
    aggressive_candidates = []

    used_matches = set()
    for a in all_decisions:
        d = a["decision"]
        if d["status"].startswith("PAS"):
            continue
        if d["reduced_risk"]:
            safe_candidates.append(d["reduced_risk"])
        if d["main"]:
            value_candidates.append(d["main"])
        for p in a["picks"][:5]:
            if p.prob >= 0.54 and p.odd >= 1.45:
                aggressive_candidates.append(p)

    def unique_by_match(cands: List[Pick], limit: int) -> List[Pick]:
        out = []
        seen = set()
        for p in cands:
            if p.match in seen:
                continue
            out.append(p)
            seen.add(p.match)
            if len(out) >= limit:
                break
        return out

    safe_candidates = sorted(safe_candidates, key=lambda p: (p.prob, -p.odd), reverse=True)
    value_candidates = sorted(value_candidates, key=lambda p: (p.value_score, p.prob), reverse=True)
    aggressive_candidates = sorted(aggressive_candidates, key=lambda p: (p.odd, p.value_score), reverse=True)

    return {
        "Güvenli Yol": unique_by_match(safe_candidates, 3),
        "Value Yol": unique_by_match(value_candidates, 4),
        "Agresif Yol": unique_by_match(aggressive_candidates, 5),
    }


def stake_plan(bankroll: float, target: float, days: int, mode: str) -> pd.DataFrame:
    rows = []
    current = bankroll
    if bankroll <= 0 or target <= bankroll or days <= 0:
        return pd.DataFrame()

    mode_factor = {
        "Güvenli": 0.035,
        "Value": 0.055,
        "Agresif": 0.085,
    }.get(mode, 0.045)

    for day in range(1, days + 1):
        remaining_ratio = target / max(current, 1)
        needed_daily_growth = remaining_ratio ** (1 / max(1, days - day + 1)) - 1
        stake_pct = clamp(needed_daily_growth / 1.2, mode_factor * 0.6, mode_factor * 1.9)
        stake = current * stake_pct
        expected_return = stake * 1.55
        net_gain = expected_return - stake
        rows.append({
            "Gün": day,
            "Kasa": round(current, 2),
            "Stake %": f"%{round(stake_pct * 100, 2)}",
            "Stake": round(stake, 2),
            "Hedeflenen Net Kazanç": round(net_gain, 2),
        })
        current += net_gain
    return pd.DataFrame(rows)


# -----------------------------
# Demo veri / Yukleme
# -----------------------------

def demo_matches() -> pd.DataFrame:
    return pd.DataFrame([
        {"league": "Premier League", "home_team": "Arsenal", "away_team": "Everton", "h": 1.42, "d": 4.60, "a": 7.20, "commence_time": "Bugün 20:00"},
        {"league": "La Liga", "home_team": "Real Valladolid", "away_team": "Girona", "h": 3.10, "d": 3.25, "a": 2.32, "commence_time": "Bugün 21:00"},
        {"league": "Süper Lig", "home_team": "Göztepe", "away_team": "Kasımpaşa", "h": 2.05, "d": 3.35, "a": 3.45, "commence_time": "Bugün 19:00"},
        {"league": "Eredivisie", "home_team": "PSV", "away_team": "Sparta Rotterdam", "h": 1.22, "d": 6.30, "a": 10.50, "commence_time": "Yarın 18:30"},
    ])


def demo_history(n: int = 500) -> pd.DataFrame:
    rows = []
    for _ in range(n):
        h = round(random.uniform(1.20, 4.20), 2)
        a = round(random.uniform(1.60, 7.50), 2)
        d = round(random.uniform(2.80, 5.20), 2)
        hl, al = estimate_lambdas_from_odds(h, d, a)
        hg = np.random.poisson(hl)
        ag = np.random.poisson(al)
        rows.append({"HomeTeam": "A", "AwayTeam": "B", "B365H": h, "B365D": d, "B365A": a, "FTHG": hg, "FTAG": ag})
    return pd.DataFrame(rows)


st.title("⚽ Vibe Analiz Pro Ultra")
st.caption("MS + Alt/Üst + KG + Çifte Şans + Takım Golü + Handikap + Skor Aralığı analiz motoru")

with st.sidebar:
    st.header("Ayarlar")
    tolerance = st.slider("Oran hassasiyeti", 0.00, 0.30, 0.08, 0.01)
    min_sample = st.number_input("Minimum benzer maç", min_value=0, max_value=50, value=3)
    st.divider()
    match_file = st.file_uploader("Güncel maç CSV", type=["csv"])
    hist_file = st.file_uploader("Geçmiş veri CSV", type=["csv"])
    st.divider()
    bankroll = st.number_input("Kasa", min_value=0.0, value=10000.0, step=500.0)
    target = st.number_input("Hedef Kasa", min_value=0.0, value=30000.0, step=1000.0)
    days = st.number_input("Gün", min_value=1, max_value=365, value=30)
    plan_mode = st.selectbox("Kasa Planı Modu", ["Güvenli", "Value", "Agresif"])

if match_file:
    matches_df = pd.read_csv(match_file)
else:
    matches_df = demo_matches()

if hist_file:
    history_df = pd.read_csv(hist_file)
else:
    history_df = demo_history()

analyses = []
for _, row in matches_df.iterrows():
    a = analyze_match(row, history_df, tolerance)
    if a.get("sample_size", 0) < min_sample:
        # Tamamen eleme yapmiyoruz; sadece status icinde risk olarak gosterecegiz.
        pass
    analyses.append(a)

coupons = build_coupons(analyses)

# -----------------------------
# Kupon Builder
# -----------------------------

st.subheader("🎫 AI Kupon Builder")
cols = st.columns(3)
for col, (name, picks) in zip(cols, coupons.items()):
    with col:
        st.markdown(f"### {name}")
        if not picks:
            st.warning("Uygun seçim yok.")
            continue
        for p in picks:
            st.markdown(
                f"""
                <div style='padding:12px;border:1px solid rgba(255,255,255,.12);border-radius:14px;margin-bottom:10px;background:rgba(255,255,255,.035)'>
                <b>{p.match}</b><br>
                <span style='color:#facc15'>{p.market}</span> · Oran: <b>{p.odd}</b><br>
                Güven: <b>{pct(p.prob)}</b> · Risk: <b>{p.risk}</b><br>
                Skor ihtimali: {p.score_hint}
                </div>
                """,
                unsafe_allow_html=True,
            )
        st.metric("Toplam Oran", combo_odd(picks))
        st.metric("Tahmini Tutma", pct(combo_probability(picks)))

st.divider()

# -----------------------------
# Mac Kartlari
# -----------------------------

st.subheader("🧠 AI Maç Analizi")

for idx, a in enumerate(analyses):
    m = a["match"]
    with st.container(border=True):
        left, right = st.columns([2, 1])
        with left:
            st.markdown(f"### {m['home']} - {m['away']}")
            st.caption(f"{m['league']} · {m['time']} · MS oranları: {m['h']} / {m['d']} / {m['a']}")
        with right:
            if a.get("error"):
                st.error(a["error"])
                continue
            st.metric("Benzer Maç", a["sample_size"])
            st.metric("AI Durum", a["decision"]["status"])

        d = a["decision"]
        c1, c2, c3, c4 = st.columns(4)
        cards = [
            ("Ana Tahmin", d["main"]),
            ("Güvenli Alternatif", d["safe_alt"]),
            ("Risk Azaltılmış Market", d["reduced_risk"]),
            ("Pas Sebebi", None),
        ]
        for col, (title, pick) in zip([c1, c2, c3, c4], cards):
            with col:
                st.markdown(f"**{title}**")
                if title == "Pas Sebebi":
                    st.write(d["pass_reason"])
                elif pick:
                    st.write(f"{pick.market}")
                    st.write(f"Güven: {pct(pick.prob)}")
                    st.write(f"Oran: {pick.odd}")
                    st.write(f"Risk: {pick.risk}")
                else:
                    st.write("-")

        with st.expander("Tüm market skorları"):
            rows = []
            for p in a["picks"]:
                rows.append({
                    "Market": p.market,
                    "Güven": pct(p.prob),
                    "Olasılık": round(p.prob, 4),
                    "Oran": p.odd,
                    "Risk": p.risk,
                    "Value Skor": round(p.value_score, 4),
                    "Skor İpucu": p.score_hint,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        with st.expander("Benzer oranlı geçmiş maçlar"):
            sim = a["similar_matches"]
            if sim.empty:
                st.info("Bu hassasiyette benzer maç bulunamadı.")
            else:
                show_cols = [c for c in ["HomeTeam", "AwayTeam", "B365H", "B365D", "B365A", "FTHG", "FTAG"] if c in sim.columns]
                st.dataframe(sim[show_cols].head(20), use_container_width=True, hide_index=True)

st.divider()

# -----------------------------
# Kasa Plani
# -----------------------------

st.subheader("📈 30 Günlük Kasa Planı")
plan_df = stake_plan(bankroll, target, int(days), plan_mode)
if plan_df.empty:
    st.info("Kasa hedefi mevcut kasadan büyük olmalı.")
else:
    st.dataframe(plan_df, use_container_width=True, hide_index=True)

st.warning(
    "Bu uygulama tahmin ve risk analizi üretir; kesin kazanç garanti etmez. Kuponları küçük stake, stop-loss ve pas filtresiyle kullanmak daha sağlıklıdır."
)
