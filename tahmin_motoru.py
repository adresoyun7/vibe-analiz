"""YapAiKupon · Tahmin Motoru 2.0

Piyasa olasılığını başlangıç noktası alıp yalnızca sapmayı öğrenen tahmin motoru.

Bileşenler
----------
1. Marjsız piyasa olasılığı (power yöntemi) · Pinnacle > ortalama > B365 önceliği.
2. Dinamik gol modeli: lig bazlı, zamanla güncellenen hücum/savunma güçleri.
   Hedef değişken gol ile "isabetli şut × lig dönüşüm oranı" karışımıdır
   (xG yerine geçen, golden daha az gürültülü sinyal). Skor matrisi
   Dixon-Coles düşük skor düzeltmesiyle üretilir; bütün marketler tek
   matristen tutarlı biçimde çıkar.
3. Artık model (koşullu lojit, piyasa ofseti): log p = log p_piyasa + β·x.
   Özellikler: gol modeli ile piyasa farkı, açılış→kapanış oran hareketi,
   dinlenme günü farkı, beraberlik/ev sahibi düzeltmesi.
   Bir özellik testte işe yaramıyorsa β≈0 olur ve model piyasaya döner.
4. Belirsizlik: β kovaryansından parametrik örnekleme ile olasılığın alt
   sınırı (%10 yüzdelik). Value seçimi bu alt sınırla yapılır.
5. Walk-forward değerlendirme: her test sezonu yalnızca önceki sezonlarla
   eğitilir. Log-loss / Brier piyasaya karşı, ROI ve (açılış modunda) CLV.

Bu modül Streamlit'e bağlı değildir; numpy + pandas dışında bağımlılığı yoktur.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

MOTOR_VERSION = "m2-2026.11.26"
SONUCLAR = ("H", "D", "A")

# ---------------------------------------------------------------------------
# 1) Olasılık araçları
# ---------------------------------------------------------------------------


def marjsiz_power(oranlar: np.ndarray, iterasyon: int = 30) -> np.ndarray:
    """Oranları power yöntemiyle marjdan arındırır: Σ (1/o)^k = 1.

    Orantılı normalizasyona göre favori/sürpriz (longshot) eğilimini daha iyi
    düzeltir. Girdi (n, K) dizisi; geçersiz satırlar NaN döner.
    """
    o = np.asarray(oranlar, dtype=float)
    tek = o.ndim == 1
    if tek:
        o = o[None, :]
    gecerli = np.isfinite(o).all(axis=1) & (o > 1.0).all(axis=1)
    q = np.where(gecerli[:, None], 1.0 / np.where(o > 1.0, o, 2.0), np.nan)
    k = np.ones(len(o))
    lq = np.log(np.where(gecerli[:, None], q, 0.5))
    for _ in range(iterasyon):
        qk = np.exp(k[:, None] * lq)
        f = qk.sum(axis=1) - 1.0
        df = (qk * lq).sum(axis=1)
        adim = np.where(np.abs(df) > 1e-12, f / df, 0.0)
        k = np.clip(k - adim, 0.2, 5.0)
        if np.nanmax(np.abs(f[gecerli]) if gecerli.any() else [0.0]) < 1e-10:
            break
    p = np.exp(k[:, None] * lq)
    p = p / p.sum(axis=1, keepdims=True)
    p[~gecerli] = np.nan
    return p[0] if tek else p


def marjsiz_oransal(oranlar: np.ndarray) -> np.ndarray:
    o = np.asarray(oranlar, dtype=float)
    q = 1.0 / o
    return q / q.sum(axis=-1, keepdims=True)


def _sayisal(df: pd.DataFrame, kolon: str) -> pd.Series:
    if kolon not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[kolon], errors="coerce")


# Geçmiş veri: (etiket, H, D, A) — önce kapanış, sonra açılış kaynakları.
KAPANIS_1X2 = [("Pinnacle kapanış", "PSCH", "PSCD", "PSCA"),
               ("Ortalama kapanış", "AvgCH", "AvgCD", "AvgCA"),
               ("B365 kapanış", "B365CH", "B365CD", "B365CA"),
               ("WH kapanış", "WHCH", "WHCD", "WHCA")]
ACILIS_1X2 = [("Pinnacle", "PSH", "PSD", "PSA"),
              ("Ortalama", "AvgH", "AvgD", "AvgA"),
              ("Ortalama (Bb)", "BbAvH", "BbAvD", "BbAvA"),
              ("B365", "B365H", "B365D", "B365A"),
              ("WH", "WHH", "WHD", "WHA"),
              ("BW", "BWH", "BWD", "BWA"),
              ("VC", "VCH", "VCD", "VCA")]
KAPANIS_OU = [("Pinnacle kapanış", "PC>2.5", "PC<2.5"),
              ("Ortalama kapanış", "AvgC>2.5", "AvgC<2.5"),
              ("B365 kapanış", "B365C>2.5", "B365C<2.5")]
ACILIS_OU = [("Pinnacle", "P>2.5", "P<2.5"),
             ("Ortalama", "Avg>2.5", "Avg<2.5"),
             ("Ortalama (Bb)", "BbAv>2.5", "BbAv<2.5"),
             ("B365", "B365>2.5", "B365<2.5")]


def kaynak_sirali_olasilik(df: pd.DataFrame, kaynaklar) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Her satır için listedeki ilk geçerli kaynağın (olasılık, oran, kaynak) değerleri."""
    k = len(kaynaklar[0]) - 1
    p = np.full((len(df), k), np.nan)
    fiyat = np.full((len(df), k), np.nan)
    etiket = np.array([""] * len(df), dtype=object)
    for kaynak in kaynaklar:
        ad, kolonlar = kaynak[0], kaynak[1:]
        if not all(c in df.columns for c in kolonlar):
            continue
        o = np.column_stack([_sayisal(df, c).to_numpy() for c in kolonlar])
        bos = np.isnan(p).any(axis=1)
        if not bos.any():
            break
        pp = marjsiz_power(o)
        yeni = bos & np.isfinite(pp).all(axis=1)
        p[yeni] = pp[yeni]
        fiyat[yeni] = o[yeni]
        etiket[yeni] = ad
    return p, fiyat, etiket


# ---------------------------------------------------------------------------
# 2) Dinamik gol modeli (online Poisson + Dixon-Coles skor matrisi)
# ---------------------------------------------------------------------------


@dataclass
class GolModeliAyar:
    ogrenme: float = 0.045          # takım gücü güncelleme hızı
    lig_ogrenme: float = 0.002      # lig ortalaması / ev avantajı güncelleme hızı
    gol_agirligi: float = 0.40      # hedef = w·gol + (1-w)·isabetli şut×dönüşüm
    rho: float = -0.06              # Dixon-Coles düşük skor düzeltmesi
    ara_gun: int = 50               # bu kadar gün maç yoksa (sezon arası) güçleri küçült
    ara_kucultme: float = 0.80
    kademe_kaymasi: float = 0.22    # lig atlayan takım için güç kaydırma (kademe başına)
    max_gol: int = 10
    dinlenme_tavan: int = 14

    def anahtar(self):
        return tuple(sorted(asdict(self).items()))


def _lig_kademesi(kod: str) -> Tuple[str, int]:
    kod = str(kod or "")
    rakam = "".join(ch for ch in kod if ch.isdigit())
    harf = "".join(ch for ch in kod if not ch.isdigit())
    return harf, int(rakam) if rakam else 0


def skor_matrisi(lh: np.ndarray, la: np.ndarray, rho: float, max_gol: int = 10) -> np.ndarray:
    """(n, G, G) skor olasılık matrisi; Dixon-Coles tau ile düzeltilmiş."""
    lh = np.atleast_1d(np.asarray(lh, dtype=float))
    la = np.atleast_1d(np.asarray(la, dtype=float))
    g = np.arange(max_gol + 1)
    lg = np.array([math.lgamma(x + 1) for x in g])
    ph = np.exp(g[None, :] * np.log(lh[:, None]) - lh[:, None] - lg[None, :])
    pa = np.exp(g[None, :] * np.log(la[:, None]) - la[:, None] - lg[None, :])
    m = ph[:, :, None] * pa[:, None, :]
    m[:, 0, 0] *= np.maximum(1 - lh * la * rho, 1e-6)
    m[:, 0, 1] *= np.maximum(1 + lh * rho, 1e-6)
    m[:, 1, 0] *= np.maximum(1 + la * rho, 1e-6)
    m[:, 1, 1] *= np.maximum(1 - rho, 1e-6)
    return m / m.sum(axis=(1, 2), keepdims=True)


def matristen_marketler(m: np.ndarray) -> Dict[str, np.ndarray]:
    G = m.shape[1]
    i = np.arange(G)[:, None]
    j = np.arange(G)[None, :]
    toplam = i + j
    sonuc = {
        "H": (m * (i > j)).sum(axis=(1, 2)),
        "D": (m * (i == j)).sum(axis=(1, 2)),
        "A": (m * (i < j)).sum(axis=(1, 2)),
        "O15": (m * (toplam >= 2)).sum(axis=(1, 2)),
        "O25": (m * (toplam >= 3)).sum(axis=(1, 2)),
        "O35": (m * (toplam >= 4)).sum(axis=(1, 2)),
        "BTTS": (m * ((i > 0) & (j > 0))).sum(axis=(1, 2)),
        "EV15": (m * (i >= 2)).sum(axis=(1, 2)),
        "DEP15": (m * (j >= 2)).sum(axis=(1, 2)),
    }
    duz = m.reshape(len(m), -1).argmax(axis=1)
    sonuc["skor_ev"] = duz // G
    sonuc["skor_dep"] = duz % G
    return sonuc


class DinamikGolModeli:
    """Maçları tarih sırasıyla işler; her maç için MAÇ ÖNCESİ λ değerlerini üretir.

    Aynı gündeki maçların hepsi güncellemeden önce tahmin edilir (gün içi sızıntı yok).
    """

    def __init__(self, ayar: Optional[GolModeliAyar] = None):
        self.ayar = ayar or GolModeliAyar()
        self.takim: Dict[str, List] = {}     # ad -> [hücum, savunma, lig, son_tarih, maç_sayısı]
        self.lig: Dict[str, List] = {}       # kod -> [mu, ev_avantajı, gol/isabetli_şut]
        self.son_tarih = None

    # -- yardımcılar ---------------------------------------------------------
    def _lig(self, kod):
        if kod not in self.lig:
            self.lig[kod] = [math.log(1.30), 0.26, 0.30]
        return self.lig[kod]

    def _takim(self, ad, kod, tarih):
        a = self.ayar
        t = self.takim.get(ad)
        if t is None:
            # Yeni takım (genelde alt ligden çıkan): ligin biraz altında başlat.
            t = [-0.10, -0.10, kod, tarih, 0]
            self.takim[ad] = t
            return t
        if t[2] != kod:
            eski_harf, eski_k = _lig_kademesi(t[2])
            yeni_harf, yeni_k = _lig_kademesi(kod)
            if eski_harf == yeni_harf:
                fark = eski_k - yeni_k          # >0: üst lige çıktı
                t[0] -= a.kademe_kaymasi * fark
                t[1] -= a.kademe_kaymasi * fark
            else:
                t[0], t[1] = t[0] * 0.5, t[1] * 0.5
            t[2] = kod
        if t[3] is not None and tarih is not None:
            gun = (tarih - t[3]).days
            if gun > a.ara_gun:
                t[0] *= a.ara_kucultme
                t[1] *= a.ara_kucultme
        return t

    def lambdalar(self, ev, dep, kod, tarih=None, kalici=False):
        """Mevcut durumdan λ_ev, λ_dep. kalici=False ise durum değişmez."""
        if kalici:
            te, td = self._takim(ev, kod, tarih), self._takim(dep, kod, tarih)
            le = self._lig(kod)
        else:
            te = list(self.takim.get(ev, [-0.10, -0.10, kod, None, 0]))
            td = list(self.takim.get(dep, [-0.10, -0.10, kod, None, 0]))
            le = list(self.lig.get(kod, [math.log(1.30), 0.26, 0.30]))
            # kalıcı olmayan çağrıda lig değişimi / ara düzeltmesini kopya üzerinde uygula
            for t in (te, td):
                if t[2] != kod:
                    eh, ek = _lig_kademesi(t[2])
                    yh, yk = _lig_kademesi(kod)
                    if eh == yh:
                        t[0] -= self.ayar.kademe_kaymasi * (ek - yk)
                        t[1] -= self.ayar.kademe_kaymasi * (ek - yk)
                    else:
                        t[0], t[1] = t[0] * 0.5, t[1] * 0.5
                if t[3] is not None and tarih is not None and (tarih - t[3]).days > self.ayar.ara_gun:
                    t[0] *= self.ayar.ara_kucultme
                    t[1] *= self.ayar.ara_kucultme
        mu, h = le[0], le[1]
        lh = math.exp(mu + h / 2 + te[0] - td[1])
        la = math.exp(mu - h / 2 + td[0] - te[1])
        return min(max(lh, 0.05), 6.0), min(max(la, 0.05), 6.0)

    def dinlenme(self, ad, tarih):
        t = self.takim.get(ad)
        if t is None or t[3] is None or tarih is None:
            return float(self.ayar.dinlenme_tavan)
        return float(min(max((tarih - t[3]).days, 0), self.ayar.dinlenme_tavan))

    def mac_sayisi(self, ad):
        t = self.takim.get(ad)
        return int(t[4]) if t else 0

    def _guncelle(self, ev, dep, kod, tarih, fthg, ftag, hst, ast_):
        a = self.ayar
        te, td = self._takim(ev, kod, tarih), self._takim(dep, kod, tarih)
        le = self._lig(kod)
        lh, la = self.lambdalar(ev, dep, kod, tarih, kalici=False)
        donusum = le[2]
        if np.isfinite(hst) and np.isfinite(ast_) and hst >= 0 and ast_ >= 0:
            yh = a.gol_agirligi * fthg + (1 - a.gol_agirligi) * donusum * hst
            ya = a.gol_agirligi * ftag + (1 - a.gol_agirligi) * donusum * ast_
            if hst + ast_ > 0:
                le[2] = 0.995 * le[2] + 0.005 * ((fthg + ftag) / (hst + ast_))
        else:
            yh, ya = fthg, ftag
        eh, ea = yh - lh, ya - la
        te[0] += a.ogrenme * eh
        td[1] -= a.ogrenme * eh
        td[0] += a.ogrenme * ea
        te[1] -= a.ogrenme * ea
        le[0] += a.lig_ogrenme * (eh + ea) / 2
        le[1] += a.lig_ogrenme * (eh - ea) / 2
        for t in (te, td):
            t[0] *= 0.9995
            t[1] *= 0.9995
            t[3] = tarih
            t[4] += 1

    # -- toplu işleme ---------------------------------------------------------
    def isle(self, df: pd.DataFrame) -> pd.DataFrame:
        """df'yi tarih sırasıyla işler, her satır için maç öncesi özellikleri döndürür."""
        kolonlar = ["lam_h", "lam_a", "dinlenme_h", "dinlenme_a", "n_h", "n_a"]
        if df is None or df.empty:
            return pd.DataFrame(columns=kolonlar)
        d = df[["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "league_code"]].copy()
        d["HST"] = _sayisal(df, "HST")
        d["AST"] = _sayisal(df, "AST")
        d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
        d["FTHG"] = pd.to_numeric(d["FTHG"], errors="coerce")
        d["FTAG"] = pd.to_numeric(d["FTAG"], errors="coerce")
        d = d.dropna(subset=["Date", "FTHG", "FTAG"])
        d = d.sort_values("Date", kind="stable")
        cikti = np.full((len(d), 6), np.nan)
        konum = {idx: i for i, idx in enumerate(d.index)}
        tarih_dizi = d["Date"].dt.normalize().to_numpy()
        satirlar = list(d.itertuples(index=True))
        bas = 0
        while bas < len(satirlar):
            son = bas
            while son < len(satirlar) and tarih_dizi[son] == tarih_dizi[bas]:
                son += 1
            gun = satirlar[bas:son]
            for r in gun:
                tarih = r.Date.to_pydatetime()
                lh, la = self.lambdalar(str(r.HomeTeam), str(r.AwayTeam), str(r.league_code), tarih)
                cikti[konum[r.Index]] = (lh, la,
                                         self.dinlenme(str(r.HomeTeam), tarih), self.dinlenme(str(r.AwayTeam), tarih),
                                         self.mac_sayisi(str(r.HomeTeam)), self.mac_sayisi(str(r.AwayTeam)))
            for r in gun:
                self._guncelle(str(r.HomeTeam), str(r.AwayTeam), str(r.league_code), r.Date.to_pydatetime(),
                               float(r.FTHG), float(r.FTAG), float(r.HST), float(r.AST))
            bas = son
        if len(d):
            self.son_tarih = d["Date"].max().to_pydatetime()
        return pd.DataFrame(cikti, index=d.index, columns=kolonlar)


# ---------------------------------------------------------------------------
# 3) Ofsetli koşullu lojit (artık model)
# ---------------------------------------------------------------------------


class OfsetliLojit:
    """p_k ∝ exp(ofset_k + β·x_k). Newton-Raphson + L2 ceza."""

    def __init__(self, ceza: float = 2.0, ozellik_adlari: Sequence[str] = ()):
        self.ceza = float(ceza)
        self.ozellik_adlari = list(ozellik_adlari)
        self.beta: Optional[np.ndarray] = None
        self.kov: Optional[np.ndarray] = None
        self.n = 0

    @staticmethod
    def _olasilik(X, ofset, beta):
        u = ofset + X @ beta
        u = u - u.max(axis=1, keepdims=True)
        e = np.exp(u)
        return e / e.sum(axis=1, keepdims=True)

    def fit(self, X: np.ndarray, ofset: np.ndarray, y: np.ndarray, iterasyon: int = 50):
        n, K, F = X.shape
        beta = np.zeros(F)
        for _ in range(iterasyon):
            p = self._olasilik(X, ofset, beta)
            xbar = np.einsum("nk,nkf->nf", p, X)
            xobs = X[np.arange(n), y]
            grad = (xobs - xbar).sum(axis=0) - self.ceza * beta
            exx = np.einsum("nk,nkf,nkg->fg", p, X, X)
            hess = -(exx - xbar.T @ xbar) - self.ceza * np.eye(F)
            try:
                adim = np.linalg.solve(hess, grad)
            except np.linalg.LinAlgError:
                break
            beta = beta - adim
            if np.max(np.abs(adim)) < 1e-8:
                break
        p = self._olasilik(X, ofset, beta)
        xbar = np.einsum("nk,nkf->nf", p, X)
        exx = np.einsum("nk,nkf,nkg->fg", p, X, X)
        H = (exx - xbar.T @ xbar) + self.ceza * np.eye(F)
        self.beta = beta
        try:
            self.kov = np.linalg.inv(H)
        except np.linalg.LinAlgError:
            self.kov = np.eye(F) * 1e-4
        self.n = int(n)
        return self

    def predict(self, X, ofset):
        if self.beta is None:
            return self._olasilik(X, ofset, np.zeros(X.shape[2]))
        return self._olasilik(X, ofset, self.beta)

    def alt_sinir(self, X, ofset, q: float = 0.10, cekilis: int = 400, tohum: int = 7):
        """β belirsizliğinden olasılığın q yüzdeliği (parametrik örnekleme)."""
        if self.beta is None:
            p = self.predict(X, ofset)
            return p, p
        rng = np.random.default_rng(tohum)
        B = rng.multivariate_normal(self.beta, self.kov, size=cekilis)
        u = ofset[None] + np.einsum("nkf,bf->bnk", X, B)
        u = u - u.max(axis=2, keepdims=True)
        e = np.exp(u)
        P = e / e.sum(axis=2, keepdims=True)
        return np.quantile(P, q, axis=0), np.quantile(P, 1 - q, axis=0)

    def ozet(self):
        if self.beta is None:
            return {}
        se = np.sqrt(np.clip(np.diag(self.kov), 0, None))
        return {ad: {"beta": round(float(b), 4), "se": round(float(s), 4)}
                for ad, b, s in zip(self.ozellik_adlari, self.beta, se)}


# ---------------------------------------------------------------------------
# 4) Özellik matrisi
# ---------------------------------------------------------------------------

OZELLIK_1X2 = ["model_farki", "oran_hareketi", "dinlenme", "beraberlik", "ev_sahibi"]
OZELLIK_OU = ["model_farki", "oran_hareketi", "ust"]
OZELLIK_KG = ["model_log", "var"]


def _guvenli_log(p):
    return np.log(np.clip(p, 1e-6, 1.0))


def ozellik_1x2(p_mkt, p_dc, hareket, dinlenme_h, dinlenme_a):
    n = len(p_mkt)
    X = np.zeros((n, 3, len(OZELLIK_1X2)))
    X[:, :, 0] = _guvenli_log(p_dc) - _guvenli_log(p_mkt)
    X[:, :, 1] = np.nan_to_num(hareket, nan=0.0) * 10.0
    dd = np.clip(np.nan_to_num(dinlenme_h - dinlenme_a, nan=0.0), -7, 7) / 7.0
    X[:, 0, 2] = dd
    X[:, 2, 2] = -dd
    X[:, 1, 3] = 1.0
    X[:, 0, 4] = 1.0
    return X, _guvenli_log(p_mkt)


def ozellik_ou(p_mkt_over, p_dc_over, hareket_over):
    n = len(p_mkt_over)
    pm = np.column_stack([p_mkt_over, 1 - p_mkt_over])
    pd_ = np.column_stack([p_dc_over, 1 - p_dc_over])
    hv = np.nan_to_num(hareket_over, nan=0.0) * 10.0
    X = np.zeros((n, 2, len(OZELLIK_OU)))
    X[:, :, 0] = _guvenli_log(pd_) - _guvenli_log(pm)
    X[:, 0, 1] = hv
    X[:, 1, 1] = -hv
    X[:, 0, 2] = 1.0
    return X, _guvenli_log(pm)


def ozellik_kg(p_dc_btts):
    n = len(p_dc_btts)
    pd_ = np.column_stack([p_dc_btts, 1 - p_dc_btts])
    X = np.zeros((n, 2, len(OZELLIK_KG)))
    X[:, :, 0] = _guvenli_log(pd_)
    X[:, 0, 1] = 1.0
    return X, np.zeros((n, 2))


@dataclass
class EgitimVerisi:
    tablo: pd.DataFrame
    referans: str


def egitim_tablosu(gecmis: pd.DataFrame, ayar: Optional[GolModeliAyar] = None,
                   referans: str = "kapanis") -> Tuple[pd.DataFrame, DinamikGolModeli]:
    """Geçmişten walk-forward özellik tablosu üretir.

    referans="kapanis": çapa = kapanış oranı, oran hareketi = kapanış - açılış.
    referans="acilis":  çapa = açılış oranı, hareket kullanılmaz (CLV ölçülebilir).
    """
    df = gecmis.copy()
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date"])
    for c in ("FTHG", "FTAG"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["FTHG", "FTAG", "HomeTeam", "AwayTeam"])
    if "league_code" not in df.columns:
        df["league_code"] = "?"
    df = df.sort_values("Date", kind="stable").reset_index(drop=True)

    model = DinamikGolModeli(ayar)
    oz = model.isle(df)
    df = df.join(oz)

    p_kap, f_kap, k_kap = kaynak_sirali_olasilik(df, KAPANIS_1X2)
    p_ac, f_ac, k_ac = kaynak_sirali_olasilik(df, ACILIS_1X2)
    # Hareket yalnızca aynı şirketin açılış→kapanış farkı (Pinnacle tercihli).
    pin_ac = marjsiz_power(np.column_stack([_sayisal(df, c) for c in ("PSH", "PSD", "PSA")]))
    pin_kap = marjsiz_power(np.column_stack([_sayisal(df, c) for c in ("PSCH", "PSCD", "PSCA")]))
    b_ac = marjsiz_power(np.column_stack([_sayisal(df, c) for c in ("B365H", "B365D", "B365A")]))
    b_kap = marjsiz_power(np.column_stack([_sayisal(df, c) for c in ("B365CH", "B365CD", "B365CA")]))
    hareket = np.where(np.isfinite(pin_kap - pin_ac).all(axis=1)[:, None], pin_kap - pin_ac,
                       np.where(np.isfinite(b_kap - b_ac).all(axis=1)[:, None], b_kap - b_ac, np.nan))

    if referans == "kapanis":
        cap = np.where(np.isfinite(p_kap).all(axis=1)[:, None], p_kap, p_ac)
        fiyat = np.where(np.isfinite(p_kap).all(axis=1)[:, None], f_kap, f_ac)
        cap_kaynak = np.where(np.isfinite(p_kap).all(axis=1), k_kap, k_ac)
        hareket_kullan = hareket
    else:
        cap, fiyat, cap_kaynak = p_ac, f_ac, k_ac
        hareket_kullan = np.full_like(hareket, np.nan)

    # Piyasadaki en yüksek fiyat (aynı zaman dilimi): value bu fiyata karşı aranır.
    if referans == "kapanis":
        eniyi_kaynak = [("Max kapanış", "MaxCH", "MaxCD", "MaxCA")]
    else:
        eniyi_kaynak = [("Max", "MaxH", "MaxD", "MaxA"), ("Max (Bb)", "BbMxH", "BbMxD", "BbMxA")]
    eniyi = np.full((len(df), 3), np.nan)
    for _, *kol in eniyi_kaynak:
        if all(c in df.columns for c in kol):
            o = np.column_stack([_sayisal(df, c).to_numpy() for c in kol])
            bos = ~np.isfinite(eniyi).all(axis=1)
            eniyi[bos] = o[bos]
    eniyi = np.where(np.isfinite(eniyi) & (eniyi >= fiyat), eniyi, fiyat)

    ou_kap, fou_kap, _ = kaynak_sirali_olasilik(df, KAPANIS_OU)
    ou_ac, fou_ac, _ = kaynak_sirali_olasilik(df, ACILIS_OU)
    if referans == "kapanis":
        ou = np.where(np.isfinite(ou_kap).all(axis=1)[:, None], ou_kap, ou_ac)
        fou = np.where(np.isfinite(ou_kap).all(axis=1)[:, None], fou_kap, fou_ac)
        ou_hareket = np.where(np.isfinite(ou_kap[:, 0] - ou_ac[:, 0]), ou_kap[:, 0] - ou_ac[:, 0], np.nan)
    else:
        ou, fou = ou_ac, fou_ac
        ou_hareket = np.full(len(df), np.nan)

    m = matristen_marketler(skor_matrisi(df["lam_h"].to_numpy(), df["lam_a"].to_numpy(),
                                         model.ayar.rho, model.ayar.max_gol))
    tablo = pd.DataFrame({
        "Date": df["Date"], "league_code": df["league_code"].astype(str),
        "season_code": df["season_code"].astype(str) if "season_code" in df else "",
        "HomeTeam": df["HomeTeam"], "AwayTeam": df["AwayTeam"],
        "FTHG": df["FTHG"], "FTAG": df["FTAG"],
        "lam_h": df["lam_h"], "lam_a": df["lam_a"],
        "dinlenme_h": df["dinlenme_h"], "dinlenme_a": df["dinlenme_a"],
        "n_h": df["n_h"], "n_a": df["n_a"],
        "mkt_H": cap[:, 0], "mkt_D": cap[:, 1], "mkt_A": cap[:, 2], "mkt_kaynak": cap_kaynak,
        "fiyat_H": fiyat[:, 0], "fiyat_D": fiyat[:, 1], "fiyat_A": fiyat[:, 2],
        "eniyi_H": eniyi[:, 0], "eniyi_D": eniyi[:, 1], "eniyi_A": eniyi[:, 2],
        "hrk_H": hareket_kullan[:, 0], "hrk_D": hareket_kullan[:, 1], "hrk_A": hareket_kullan[:, 2],
        "kap_H": p_kap[:, 0], "kap_D": p_kap[:, 1], "kap_A": p_kap[:, 2],
        "dc_H": m["H"], "dc_D": m["D"], "dc_A": m["A"],
        "dc_O25": m["O25"], "dc_BTTS": m["BTTS"],
        "mkt_O25": ou[:, 0], "fiyat_O25": fou[:, 0], "fiyat_U25": fou[:, 1], "hrk_O25": ou_hareket,
    })
    tablo["y_1x2"] = np.select([tablo.FTHG > tablo.FTAG, tablo.FTHG == tablo.FTAG], [0, 1], 2)
    tablo["y_o25"] = np.where(tablo.FTHG + tablo.FTAG >= 3, 0, 1)
    tablo["y_kg"] = np.where((tablo.FTHG > 0) & (tablo.FTAG > 0), 0, 1)
    tablo.attrs["referans"] = referans
    return tablo, model


def _isinmis(tablo, min_mac=8):
    return (tablo["n_h"] >= min_mac) & (tablo["n_a"] >= min_mac)


# ---------------------------------------------------------------------------
# 5) Model eğitimi
# ---------------------------------------------------------------------------


@dataclass
class EgitilmisModeller:
    m1x2: OfsetliLojit
    mou: OfsetliLojit
    mkg: OfsetliLojit
    n_1x2: int = 0
    n_ou: int = 0
    n_kg: int = 0


def modelleri_egit(tablo: pd.DataFrame, ceza: float = 50.0, min_mac: int = 8) -> EgitilmisModeller:
    t = tablo[_isinmis(tablo, min_mac)]
    r1 = t.dropna(subset=["mkt_H", "mkt_D", "mkt_A", "dc_H"])
    X, ofs = ozellik_1x2(r1[["mkt_H", "mkt_D", "mkt_A"]].to_numpy(), r1[["dc_H", "dc_D", "dc_A"]].to_numpy(),
                         r1[["hrk_H", "hrk_D", "hrk_A"]].to_numpy(), r1["dinlenme_h"].to_numpy(),
                         r1["dinlenme_a"].to_numpy())
    m1 = OfsetliLojit(ceza, OZELLIK_1X2)
    if len(r1) >= 200:
        m1.fit(X, ofs, r1["y_1x2"].to_numpy().astype(int))

    r2 = t.dropna(subset=["mkt_O25", "dc_O25"])
    X2, ofs2 = ozellik_ou(r2["mkt_O25"].to_numpy(), r2["dc_O25"].to_numpy(), r2["hrk_O25"].to_numpy())
    m2 = OfsetliLojit(ceza, OZELLIK_OU)
    if len(r2) >= 200:
        m2.fit(X2, ofs2, r2["y_o25"].to_numpy().astype(int))

    r3 = t.dropna(subset=["dc_BTTS"])
    X3, ofs3 = ozellik_kg(r3["dc_BTTS"].to_numpy())
    m3 = OfsetliLojit(ceza, OZELLIK_KG)
    if len(r3) >= 200:
        m3.fit(X3, ofs3, r3["y_kg"].to_numpy().astype(int))
    return EgitilmisModeller(m1, m2, m3, len(r1), len(r2), len(r3))


# ---------------------------------------------------------------------------
# 6) Walk-forward değerlendirme
# ---------------------------------------------------------------------------


def _logloss(p, y):
    return float(-np.mean(np.log(np.clip(p[np.arange(len(y)), y], 1e-9, 1))))


def _brier(p, y):
    o = np.zeros_like(p)
    o[np.arange(len(y)), y] = 1
    return float(np.mean(((p - o) ** 2).sum(axis=1)))


def _sezon_baslangiclari(tablo):
    if "season_code" in tablo and tablo["season_code"].astype(str).str.len().gt(0).all():
        g = tablo.groupby("season_code")["Date"].min().sort_values()
        return list(g.items())
    # sezon kodu yoksa Temmuz başlangıçlı yıllar
    yillar = sorted({(d.year if d.month >= 7 else d.year - 1) for d in tablo["Date"]})
    return [(str(y), pd.Timestamp(year=y, month=7, day=1)) for y in yillar]


def walk_forward(tablo: pd.DataFrame, min_egitim_sezon: int = 2, ceza: float = 50.0,
                 min_ev: float = 0.02, min_mac: int = 8, q: float = 0.10,
                 max_oran: float = 5.0) -> Dict:
    """Her sezon önceki sezonlarla eğitilir. Piyasa, gol modeli ve final modeli kıyaslanır."""
    sezonlar = _sezon_baslangiclari(tablo)
    satirlar, secimler = [], []
    for i, (sezon, bas) in enumerate(sezonlar):
        if i < min_egitim_sezon:
            continue
        bit = sezonlar[i + 1][1] if i + 1 < len(sezonlar) else tablo["Date"].max() + pd.Timedelta(days=1)
        egit = tablo[tablo["Date"] < bas]
        test = tablo[(tablo["Date"] >= bas) & (tablo["Date"] < bit)]
        test = test[_isinmis(test, min_mac)].dropna(subset=["mkt_H", "mkt_D", "mkt_A", "dc_H"])
        if test.empty:
            continue
        modeller = modelleri_egit(egit, ceza, min_mac)
        pm = test[["mkt_H", "mkt_D", "mkt_A"]].to_numpy()
        pdc = test[["dc_H", "dc_D", "dc_A"]].to_numpy()
        X, ofs = ozellik_1x2(pm, pdc, test[["hrk_H", "hrk_D", "hrk_A"]].to_numpy(),
                             test["dinlenme_h"].to_numpy(), test["dinlenme_a"].to_numpy())
        pf = modeller.m1x2.predict(X, ofs)
        plo, _ = modeller.m1x2.alt_sinir(X, ofs, q=q)
        y = test["y_1x2"].to_numpy().astype(int)
        satir = {"Sezon": sezon, "Maç": len(test), "Eğitim maçı": modeller.n_1x2,
                 "Piyasa log-loss": _logloss(pm, y), "Gol modeli log-loss": _logloss(pdc, y),
                 "Model 2.0 log-loss": _logloss(pf, y),
                 "Piyasa Brier": _brier(pm, y), "Model 2.0 Brier": _brier(pf, y)}
        # O/U
        t2 = test.dropna(subset=["mkt_O25"])
        if len(t2) and modeller.mou.beta is not None:
            X2, o2 = ozellik_ou(t2["mkt_O25"].to_numpy(), t2["dc_O25"].to_numpy(), t2["hrk_O25"].to_numpy())
            p2 = modeller.mou.predict(X2, o2)
            y2 = t2["y_o25"].to_numpy().astype(int)
            pm2 = np.column_stack([t2["mkt_O25"], 1 - t2["mkt_O25"]])
            satir.update({"2.5 Piyasa log-loss": _logloss(pm2, y2), "2.5 Model log-loss": _logloss(p2, y2)})
        satirlar.append(satir)

        # Value seçimleri (1X2): olasılık alt sınırı × piyasadaki en iyi fiyat
        fiyat = test[["eniyi_H", "eniyi_D", "eniyi_A"]].to_numpy()
        fiyat = np.where(fiyat <= max_oran, fiyat, np.nan)
        ev_alt = plo * fiyat - 1
        kap_tum = test[["kap_H", "kap_D", "kap_A"]].to_numpy(dtype=float)
        acilis = tablo.attrs.get("referans") == "acilis"
        for j, (idx, r) in enumerate(test.iterrows()):
            if not np.isfinite(ev_alt[j]).any():
                continue
            k = int(np.nanargmax(ev_alt[j]))
            if ev_alt[j, k] < min_ev:
                continue
            tuttu = int(y[j] == k)
            kayit = {"Sezon": sezon, "Tarih": r["Date"], "Lig": r["league_code"],
                     "Maç": f'{r["HomeTeam"]} - {r["AwayTeam"]}', "Seçim": ("MS 1", "Beraberlik", "MS 2")[k],
                     "Oran": float(fiyat[j, k]), "Model %": float(pf[j, k] * 100),
                     "Alt sınır %": float(plo[j, k] * 100), "Piyasa %": float(pm[j, k] * 100),
                     "EV alt %": float(ev_alt[j, k] * 100),
                     "Güç": "Güçlü" if pdc[j, k] > pm[j, k] else "Normal",
                     "Tuttu": bool(tuttu), "Kâr": float(fiyat[j, k] - 1) if tuttu else -1.0}
            if acilis and np.isfinite(kap_tum[j, k]):
                kayit["CLV %"] = float((fiyat[j, k] * kap_tum[j, k] - 1) * 100)
            secimler.append(kayit)

    ozet = pd.DataFrame(satirlar)
    sec = pd.DataFrame(secimler)
    genel = {}
    if not ozet.empty:
        w = ozet["Maç"]
        for c in [c for c in ozet.columns if "log-loss" in c or "Brier" in c]:
            genel[c] = float(np.average(ozet[c].dropna(), weights=w[ozet[c].notna()]))
        genel["Log-loss iyileşme %"] = (genel["Piyasa log-loss"] - genel["Model 2.0 log-loss"]) / genel["Piyasa log-loss"] * 100
    if not sec.empty:
        genel["Value seçimi"] = int(len(sec))
        genel["İsabet %"] = float(sec["Tuttu"].mean() * 100)
        genel["ROI %"] = float(sec["Kâr"].mean() * 100)
        genel["Ort. oran"] = float(sec["Oran"].mean())
        if "CLV %" in sec:
            genel["Ort. CLV %"] = float(sec["CLV %"].mean())
            genel["Pozitif CLV oranı %"] = float((sec["CLV %"] > 0).mean() * 100)
        guclu = sec[sec["Güç"] == "Güçlü"]
        if len(guclu):
            genel["Güçlü seçim"] = int(len(guclu))
            genel["Güçlü ROI %"] = float(guclu["Kâr"].mean() * 100)
    return {"sezonlar": ozet, "secimler": sec, "genel": genel, "lig_karnesi": lig_karnesi(sec)}


def lig_karnesi(secimler: pd.DataFrame) -> pd.DataFrame:
    """Value seçimlerinin lig bazlı geçmiş performansı (walk-forward)."""
    if secimler is None or secimler.empty:
        return pd.DataFrame(columns=["Lig", "Seçim", "İsabet %", "ROI %", "ROI SE %"])
    g = secimler.groupby("Lig")
    k = pd.DataFrame({
        "Seçim": g.size(),
        "İsabet %": g["Tuttu"].mean() * 100,
        "ROI %": g["Kâr"].mean() * 100,
        "ROI SE %": g["Kâr"].std(ddof=1).fillna(0) / np.sqrt(g.size()) * 100,
    }).reset_index()
    if "CLV %" in secimler:
        k = k.merge(secimler.groupby("Lig")["CLV %"].mean().rename("CLV %").reset_index(), on="Lig", how="left")
    return k.sort_values("Seçim", ascending=False).reset_index(drop=True)


def gol_modeli_ayarla(tablo_kaynagi: pd.DataFrame, izgara: Optional[Dict[str, Iterable]] = None,
                      son_tarih=None) -> Tuple[GolModeliAyar, pd.DataFrame]:
    """Gol modeli parametrelerini yalnızca son_tarih ÖNCESİ maçların log-loss'una göre seçer."""
    izgara = izgara or {"ogrenme": (0.03, 0.045, 0.06), "gol_agirligi": (0.35, 0.5, 0.7, 1.0)}
    sonuc = []
    en_iyi, en_iyi_ll = GolModeliAyar(), float("inf")
    anahtarlar = list(izgara.keys())
    from itertools import product
    for degerler in product(*[izgara[k] for k in anahtarlar]):
        ayar = GolModeliAyar(**dict(zip(anahtarlar, degerler)))
        t, _ = egitim_tablosu(tablo_kaynagi, ayar)
        t = t[_isinmis(t)]
        if son_tarih is not None:
            t = t[t["Date"] < pd.Timestamp(son_tarih)]
        if t.empty:
            continue
        ll = _logloss(t[["dc_H", "dc_D", "dc_A"]].to_numpy(), t["y_1x2"].to_numpy().astype(int))
        sonuc.append({**dict(zip(anahtarlar, degerler)), "log-loss": ll})
        if ll < en_iyi_ll:
            en_iyi, en_iyi_ll = ayar, ll
    return en_iyi, pd.DataFrame(sonuc).sort_values("log-loss") if sonuc else pd.DataFrame()


# ---------------------------------------------------------------------------
# 7) Canlı kullanım
# ---------------------------------------------------------------------------


@dataclass
class MotorDurumu:
    gol_modeli: DinamikGolModeli
    modeller: EgitilmisModeller
    egitim_mac: int
    son_veri_tarihi: Optional[pd.Timestamp]
    takimlar_lige_gore: Dict[str, List[str]] = field(default_factory=dict)
    lig_karnesi: pd.DataFrame = field(default_factory=pd.DataFrame)
    version: str = MOTOR_VERSION


def motoru_hazirla(gecmis: pd.DataFrame, ayar: Optional[GolModeliAyar] = None,
                   ceza: float = 50.0, karne: bool = True) -> Optional[MotorDurumu]:
    if gecmis is None or gecmis.empty:
        return None
    tablo, gol = egitim_tablosu(gecmis, ayar, referans="kapanis")
    modeller = modelleri_egit(tablo, ceza)
    karne_df = pd.DataFrame()
    if karne:
        try:
            t_ac, _ = egitim_tablosu(gecmis, ayar, referans="acilis")
            karne_df = walk_forward(t_ac, ceza=ceza)["lig_karnesi"]
        except Exception:  # karne isteğe bağlıdır; motoru durdurmaz
            karne_df = pd.DataFrame()
    lig_takim: Dict[str, set] = {}
    for kod, ad in zip(tablo["league_code"], tablo["HomeTeam"]):
        lig_takim.setdefault(str(kod), set()).add(str(ad))
    for kod, ad in zip(tablo["league_code"], tablo["AwayTeam"]):
        lig_takim.setdefault(str(kod), set()).add(str(ad))
    return MotorDurumu(gol, modeller, int(len(tablo)), tablo["Date"].max() if len(tablo) else None,
                       {k: sorted(v) for k, v in lig_takim.items()}, karne_df)


def _f(x):
    try:
        v = float(x)
        return v if math.isfinite(v) and v > 0 else None
    except (TypeError, ValueError):
        return None


def _uclu(m, anahtarlar):
    v = [_f(m.get(k)) for k in anahtarlar]
    return np.array(v, dtype=float) if all(x is not None and x > 1 for x in v) else None


def canli_piyasa(m: dict) -> Dict:
    """Bülten satırından çapa olasılığı, en iyi fiyat ve hareket."""
    pin = _uclu(m, ("pin_h", "pin_d", "pin_a"))
    kons = [_f(m.get(k)) for k in ("kons_h", "kons_d", "kons_a")]
    ana = _uclu(m, ("h", "b", "a"))
    if pin is not None:
        cap, kaynak = marjsiz_power(pin), "Pinnacle"
    elif all(x is not None for x in kons):
        cap, kaynak = np.array(kons) / sum(kons), f"Konsensüs ({int(m.get('kitap_sayisi') or 0)} şirket)"
    elif ana is not None:
        cap, kaynak = marjsiz_power(ana), str(m.get("bookmaker_key") or "Bülten")
    else:
        return {}
    en_iyi = _uclu(m, ("max_h", "max_d", "max_a"))
    if en_iyi is None:
        en_iyi = ana if ana is not None else 1 / cap
    ilk = [_f(m.get(k)) for k in ("ilk_ph", "ilk_pd", "ilk_pa")]
    hareket = cap - np.array(ilk) if all(x is not None for x in ilk) else np.full(3, np.nan)
    return {"cap": cap, "kaynak": kaynak, "en_iyi": en_iyi, "hareket": hareket,
            "en_iyi_kitap": [m.get("max_h_kitap"), m.get("max_d_kitap"), m.get("max_a_kitap")]}


def mac_tahmini(durum: MotorDurumu, m: dict, ev_hist: Optional[str], dep_hist: Optional[str],
                lig_kodu: Optional[str], q: float = 0.10, min_ev: float = 0.02,
                benzerlik: Optional[Dict[str, float]] = None, max_oran: float = 5.0) -> Dict:
    """Tek maç için Model 2.0 çıktısı.

    ev_hist / dep_hist: geçmiş verideki takım adları (eşleştirme dışarıda yapılır).
    benzerlik: mevcut oran-benzerlik modelinin olasılıkları (0-1) — uyum kontrolü için.
    """
    piyasa = canli_piyasa(m)
    if not piyasa:
        return {"durum": "Oran yok"}
    tarih = pd.to_datetime(m.get("zaman"), errors="coerce")
    tarih = tarih.to_pydatetime().replace(tzinfo=None) if pd.notna(tarih) else None
    gm = durum.gol_modeli
    uyarilar = []
    if not (ev_hist and dep_hist and lig_kodu):
        uyarilar.append("Takım/lig geçmişte eşleşmedi; yalnızca piyasa olasılığı kullanıldı.")
        lh = la = None
    else:
        lh, la = gm.lambdalar(ev_hist, dep_hist, lig_kodu, tarih)
        if min(gm.mac_sayisi(ev_hist), gm.mac_sayisi(dep_hist)) < 8:
            uyarilar.append("Takımlardan birinin geçmişi kısa (<8 maç); gol modeli zayıf.")

    cap = piyasa["cap"]
    sonuc = {"durum": "OK", "piyasa_kaynagi": piyasa["kaynak"], "uyarilar": uyarilar,
             "piyasa": {"MS 1": cap[0], "Beraberlik": cap[1], "MS 2": cap[2]}}

    if lh is not None:
        mat = skor_matrisi(np.array([lh]), np.array([la]), gm.ayar.rho, gm.ayar.max_gol)
        mk = matristen_marketler(mat)
        pdc = np.array([mk["H"][0], mk["D"][0], mk["A"][0]])
        dn_h, dn_a = gm.dinlenme(ev_hist, tarih), gm.dinlenme(dep_hist, tarih)
        sonuc["gol_modeli"] = {
            "lam_ev": lh, "lam_dep": la, "MS 1": pdc[0], "Beraberlik": pdc[1], "MS 2": pdc[2],
            "1.5 Üst": float(mk["O15"][0]), "2.5 Üst": float(mk["O25"][0]), "3.5 Üst": float(mk["O35"][0]),
            "KG Var": float(mk["BTTS"][0]), "Ev 1.5 Üst": float(mk["EV15"][0]), "Dep 1.5 Üst": float(mk["DEP15"][0]),
            "skor": f'{int(mk["skor_ev"][0])}-{int(mk["skor_dep"][0])}',
            "dinlenme_ev": dn_h, "dinlenme_dep": dn_a,
        }
        # En olası 5 skor
        flat = mat[0].ravel()
        en = np.argsort(flat)[::-1][:5]
        G = mat.shape[1]
        sonuc["gol_modeli"]["skorlar"] = [(f"{i // G}-{i % G}", float(flat[i])) for i in en]
    else:
        pdc = cap.copy()
        dn_h = dn_a = float(gm.ayar.dinlenme_tavan)

    X, ofs = ozellik_1x2(cap[None], pdc[None], piyasa["hareket"][None], np.array([dn_h]), np.array([dn_a]))
    pf = durum.modeller.m1x2.predict(X, ofs)[0]
    plo, phi = durum.modeller.m1x2.alt_sinir(X, ofs, q=q)
    plo, phi = plo[0], phi[0]
    sonuc["model"] = {"MS 1": pf[0], "Beraberlik": pf[1], "MS 2": pf[2]}
    sonuc["alt"] = {"MS 1": plo[0], "Beraberlik": plo[1], "MS 2": plo[2]}
    sonuc["ust"] = {"MS 1": phi[0], "Beraberlik": phi[1], "MS 2": phi[2]}
    sonuc["hareket"] = {"MS 1": piyasa["hareket"][0], "Beraberlik": piyasa["hareket"][1], "MS 2": piyasa["hareket"][2]}

    adaylar = []
    for k, ad in enumerate(("MS 1", "Beraberlik", "MS 2")):
        adaylar.append(_aday(ad, pf[k], plo[k], cap[k], piyasa["en_iyi"][k], piyasa["en_iyi_kitap"][k],
                             pdc[k], benzerlik.get(ad) if benzerlik else None, min_ev, max_oran))

    # 2.5 Alt/Üst
    ou = _uclu(m, ("o25_over", "o25_under"))[:2] if _uclu(m, ("o25_over", "o25_under")) is not None else None
    if lh is not None:
        p_dc_o = sonuc["gol_modeli"]["2.5 Üst"]
        if ou is not None:
            p_mo = marjsiz_power(ou)[0]
            X2, o2 = ozellik_ou(np.array([p_mo]), np.array([p_dc_o]), np.array([np.nan]))
            p2 = durum.modeller.mou.predict(X2, o2)[0]
            lo2, _ = durum.modeller.mou.alt_sinir(X2, o2, q=q)
            fiyat_o = [_f(m.get("max_o25_over")) or ou[0], _f(m.get("max_o25_under")) or ou[1]]
            for k, ad in enumerate(("2.5 Üst", "2.5 Alt")):
                adaylar.append(_aday(ad, p2[k], lo2[0][k], (p_mo, 1 - p_mo)[k], fiyat_o[k], None,
                                     (p_dc_o, 1 - p_dc_o)[k], benzerlik.get(ad) if benzerlik else None, min_ev, max_oran))
            sonuc["model"].update({"2.5 Üst": p2[0], "2.5 Alt": p2[1]})
            sonuc["piyasa"].update({"2.5 Üst": p_mo, "2.5 Alt": 1 - p_mo})
        # KG: geçmişte piyasa oranı yok → yalnızca gol modeli kalibrasyonu, daha az güvenilir
        X3, o3 = ozellik_kg(np.array([sonuc["gol_modeli"]["KG Var"]]))
        p3 = durum.modeller.mkg.predict(X3, o3)[0]
        lo3, _ = durum.modeller.mkg.alt_sinir(X3, o3, q=q)
        sonuc["model"].update({"KG Var": p3[0], "KG Yok": p3[1]})
        kg = _uclu(m, ("btts_yes", "btts_no"))
        if kg is not None:
            p_mk = marjsiz_power(kg)
            sonuc["piyasa"].update({"KG Var": p_mk[0], "KG Yok": p_mk[1]})
            for k, ad in enumerate(("KG Var", "KG Yok")):
                a = _aday(ad, p3[k], lo3[0][k], p_mk[k], kg[k], None, p3[k],
                          benzerlik.get(ad) if benzerlik else None, min_ev, max_oran)
                a["not"] = "KG modeli geçmiş KG oranı olmadan eğitildi; temkinli yorumla."
                adaylar.append(a)

    sonuc["adaylar"] = sorted(adaylar, key=lambda a: a["ev_alt"], reverse=True)
    sonuc["value"] = [a for a in sonuc["adaylar"] if a["value"]]
    return sonuc


def _aday(ad, p, p_alt, p_piyasa, fiyat, kitap, p_gol, p_benzer, min_ev, max_oran=5.0):
    fiyat = float(fiyat) if fiyat and fiyat > 1 else float("nan")
    ev = p * fiyat - 1
    ev_alt = p_alt * fiyat - 1
    gol_yonu = (p_gol - p_piyasa) if p_gol is not None else None
    benzer_yonu = (p_benzer - p_piyasa) if p_benzer is not None else None
    yonler = [x > 0 for x in (gol_yonu, benzer_yonu) if x is not None]
    uyum = bool(yonler) and all(yonler)
    oran_uygun = bool(np.isfinite(fiyat) and fiyat <= max_oran)
    value = bool(np.isfinite(ev_alt) and ev_alt >= min_ev and oran_uygun)
    guc = ("Güçlü" if uyum else "Normal") if value else ("Yüksek oran" if np.isfinite(ev_alt) and ev_alt >= min_ev else "—")
    return {"secim": ad, "p": float(p), "p_alt": float(p_alt), "p_piyasa": float(p_piyasa),
            "kenar": float(p - p_piyasa), "kenar_alt": float(p_alt - p_piyasa),
            "fiyat": fiyat, "kitap": kitap, "ev": float(ev), "ev_alt": float(ev_alt),
            "gol_modeli_yonu": gol_yonu, "benzerlik_yonu": benzer_yonu,
            "uyum": uyum, "value": value, "guc": guc}


def wilson_alt_sinir(basari: float, n: float, z: float = 1.2816) -> float:
    """Oran-benzerlik modelinin frekansı için Wilson alt sınırı (%10 tek yönlü)."""
    if n <= 0:
        return 0.0
    p = basari / n
    pay = p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0.0, pay / (1 + z * z / n))
