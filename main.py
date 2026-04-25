"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";

type Match = any;

const LEAGUE_MAP: Record<string, string> = {
  "Şampiyonlar Ligi": "🏆",
  "Avrupa Ligi": "🟠",
  "Konferans Ligi": "🟢",
  "Süper Lig": "🇹🇷",
  "Premier League": "🏴",
  "Championship": "🏴",
  "League 1": "🏴",
  "League 2": "🏴",
  "FA Cup": "🏴",
  "EFL Cup": "🏴",
  "La Liga": "🇪🇸",
  "La Liga 2": "🇪🇸",
  "Copa del Rey": "🇪🇸",
  "Bundesliga": "🇩🇪",
  "Bundesliga 2": "🇩🇪",
  "DFB-Pokal": "🇩🇪",
  "Serie A": "🇮🇹",
  "Serie B": "🇮🇹",
  "Coppa Italia": "🇮🇹",
  "Ligue 1": "🇫🇷",
  "Ligue 2": "🇫🇷",
  "Coupe de France": "🇫🇷",
  "Hollanda": "🇳🇱",
  "Belçika": "🇧🇪",
  "Portekiz": "🇵🇹",
  "İskoçya": "🏴",
  "Danimarka": "🇩🇰",
  "Avusturya": "🇦🇹",
  "İsviçre": "🇨🇭",
  "İsveç": "🇸🇪",
  "Norveç": "🇳🇴",
  "Polonya": "🇵🇱",
  "Finlandiya": "🇫🇮",
  "İrlanda": "🇮🇪",
  "Yunanistan": "🇬🇷",
  "MLS": "🇺🇸",
  "Brezilya Serie A": "🇧🇷",
  "Arjantin Primera": "🇦🇷",
  "Japonya J League": "🇯🇵",
  "Meksika Liga MX": "🇲🇽",
  "Güney Kore K League 1": "🇰🇷",
  "Şili Primera": "🇨🇱",
};

const LEAGUES = [
  "🏆 Tüm Ligler",
  ...Object.entries(LEAGUE_MAP).map(([name, icon]) => `${icon} ${name}`),
];

const DATE_OPTIONS = ["Bugün", "Yarın", "2 Gün Sonra", "3 Gün Sonra", "Özel Tarih"];
const SEASONS = ["2122", "2223", "2324", "2425", "2526"];

function todayText() {
  return new Intl.DateTimeFormat("tr-TR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
    weekday: "long",
  }).format(new Date());
}

function safePercent(v: any) {
  const n = Number(v || 0);
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(100, Math.round(n)));
}

function formatTolerance(v: number) {
  return (v / 100).toFixed(2);
}

function cleanLeagueName(value: string) {
  return value
    .replace(/^(\p{Emoji_Presentation}|\p{Extended_Pictographic}|\S)\s/u, "")
    .trim();
}

function getSampleCount(m: Match) {
  return Number(
    m.sample_count ??
      m.ornek ??
      m.examples ??
      m.similar_count ??
      m.benzer_mac_sayisi ??
      m.match_count ??
      m.history_count ??
      m.total_examples ??
      0
  );
}

function calcPlayableScore(m: Match) {
  const confidence = safePercent(m.pro_score);
  const sample = Math.min(100, getSampleCount(m) * 4);
  const toleranceBonus = Array.isArray(m.tolerance_hits) ? m.tolerance_hits.length * 4 : 0;
  const comboBonus = m.combo_pick ? 6 : 0;

  return Math.max(
    1,
    Math.min(100, Math.round(confidence * 0.62 + sample * 0.25 + toleranceBonus + comboBonus))
  );
}

export default function HomePage() {
  const [scanner, setScanner] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [coupon, setCoupon] = useState<Match[]>([]);
  const [error, setError] = useState("");
  const [filterOpen, setFilterOpen] = useState(false);
  const [dateOption, setDateOption] = useState("Bugün");
  const [selectedLeagues, setSelectedLeagues] = useState<string[]>(["🏆 Tüm Ligler"]);
  const [selectedSeasons, setSelectedSeasons] = useState<string[]>([
    "2122",
    "2223",
    "2324",
    "2425",
    "2526",
  ]);
  const [query, setQuery] = useState("");
  const [confidenceFilter, setConfidenceFilter] = useState<"all" | "high" | "mid" | "risk">("all");
  const [tolerance, setTolerance] = useState(8);
  const [apiKey, setApiKey] = useState("");

  const matches: Match[] = scanner?.top_matches || [];

  useEffect(() => {
    const raw = localStorage.getItem("vibe_scanner");
    if (raw) {
      try {
        setScanner(JSON.parse(raw));
      } catch {}
    }

    const savedKey = localStorage.getItem("odds_api_key");
    if (savedKey) setApiKey(savedKey);
  }, []);

  async function loadScanner() {
    setLoading(true);
    setError("");

    if (!apiKey.trim()) {
      setError("Analiz başlatmak için API key girmen gerekiyor.");
      setLoading(false);
      return;
    }

    try {
      const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

      const dateMap: Record<string, string> = {
        Bugün: "today",
        Yarın: "tomorrow",
        "2 Gün Sonra": "2days",
        "3 Gün Sonra": "3days",
        "Özel Tarih": "today",
      };

      const cleanLeagues =
        selectedLeagues.includes("🏆 Tüm Ligler") || selectedLeagues.length === 0
          ? Object.keys(LEAGUE_MAP)
          : selectedLeagues.map((x) => cleanLeagueName(x));

      const params = new URLSearchParams({
        date: dateMap[dateOption] || "today",
        leagues: cleanLeagues.join(","),
        tolerans: formatTolerance(tolerance),
      });

      const res = await fetch(`${API_URL}/scanner/daily?${params.toString()}`, {
        headers: {
          "x-api-key": apiKey,
        },
      });

      const data = await res.json();

      if (data.error) {
        setError(data.message || "API hata verdi");
        return;
      }

      setScanner(data);
      localStorage.setItem("vibe_scanner", JSON.stringify(data));
    } catch (err) {
      setError("API bağlantı hatası");
    } finally {
      setLoading(false);
    }
  }

  function openDetail(m: Match, index: number) {
    localStorage.setItem("vibe_selected_match", JSON.stringify(m));
    localStorage.setItem("vibe_selected_index", String(index));
  }

  function addCoupon(m: Match) {
    setCoupon((prev) => {
      const exists = prev.some((x) => x.home_team === m.home_team && x.away_team === m.away_team);
      if (exists) return prev;
      return [...prev, m];
    });
  }

  function removeCoupon(index: number) {
    setCoupon((prev) => prev.filter((_, i) => i !== index));
  }

  function toggleLeague(league: string) {
    setSelectedLeagues((prev) => {
      const allRealLeagues = LEAGUES.filter((x) => x !== "🏆 Tüm Ligler");

      if (league === "🏆 Tüm Ligler") {
        const allSelected = allRealLeagues.every((x) => prev.includes(x));

        if (allSelected) {
          return [];
        }

        return ["🏆 Tüm Ligler", ...allRealLeagues];
      }

      const withoutAll = prev.filter((x) => x !== "🏆 Tüm Ligler");

      let next: string[];

      if (withoutAll.includes(league)) {
        next = withoutAll.filter((x) => x !== league);
      } else {
        next = [...withoutAll, league];
      }

      const allSelectedNow = allRealLeagues.every((x) => next.includes(x));

      if (allSelectedNow) {
        return ["🏆 Tüm Ligler", ...allRealLeagues];
      }

      return next;
    });
  }

  function toggleSeason(season: string) {
    setSelectedSeasons((prev) => {
      if (prev.includes(season)) {
        const next = prev.filter((x) => x !== season);
        return next.length ? next : prev;
      }
      return [...prev, season];
    });
  }

  const filteredLeagues = LEAGUES.filter((x) => x.toLowerCase().includes(query.toLowerCase()));

  const filteredMatches = useMemo(() => {
    return matches
      .filter((m) => {
        const s = safePercent(m.pro_score);
        if (confidenceFilter === "high") return s >= 70;
        if (confidenceFilter === "mid") return s >= 55 && s < 70;
        if (confidenceFilter === "risk") return s < 55;
        return true;
      })
      .sort((a, b) => {
        const ap = Number(a.playable_score || calcPlayableScore(a));
        const bp = Number(b.playable_score || calcPlayableScore(b));
        return bp - ap || safePercent(b.pro_score) - safePercent(a.pro_score);
      });
  }, [matches, confidenceFilter]);

  const couponOdd = useMemo(() => {
    return coupon.reduce((acc, m) => acc * Number(m.odd || 1), 1).toFixed(2);
  }, [coupon]);

  const averageScore = useMemo(() => {
    if (!matches.length) return 0;
    const total = matches.reduce((acc, m) => acc + safePercent(m.pro_score), 0);
    return Math.round(total / matches.length);
  }, [matches]);

  const leagueSummary =
    selectedLeagues.length === 0
      ? "Lig seçilmedi"
      : selectedLeagues.includes("🏆 Tüm Ligler")
      ? "Tüm Ligler"
      : `${selectedLeagues.length} lig`;

  const seasonSummary = `${selectedSeasons.length} sezon`;

  return (
    <main className="min-h-screen bg-[#f4f7fb] text-slate-100">
      <div className="grid min-h-screen grid-cols-[260px_1fr]">
        <aside className="sticky top-0 flex h-screen flex-col justify-between border-r border-white/10 bg-[#0b111c] text-white shadow-xl">
          <div className="p-4">
            <div className="flex items-center gap-3">
              <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-yellow-400 text-xl font-black text-black shadow-[0_0_25px_rgba(250,204,21,0.25)]">
                O
              </div>
              <div>
                <div className="text-sm font-black tracking-[0.22em] text-yellow-400">
                  ORAN ANALİZ
                </div>
                <div className="text-xs font-bold text-slate-400">
                  AI Match Engine
                </div>
              </div>
            </div>

            <div className="mt-8 space-y-2">
              <SidebarItem icon="🏠" label="Ana Sayfa" active />
              <SidebarItem icon="⭐" label="Favoriler" />
              <SidebarItem icon="🎫" label="Kuponlarım" />
              <SidebarItem icon="📊" label="Analiz Geçmişi" />
            </div>

            <div className="mt-6 rounded-xl border border-yellow-400/20 bg-yellow-400/10 p-3">
              <div className="text-xs font-black text-yellow-300">Bugünkü Özet</div>
              <div className="mt-2 text-xs leading-5 text-slate-300">
                {scanner?.total_matches || 0} maç analiz edildi.
                <br />
                Ortalama güven: %{averageScore}
                <br />
                Hassasiyet: {formatTolerance(tolerance)}
              </div>
            </div>
          </div>

          <div className="border-t border-white/10 p-4">
            <div className="rounded-xl border border-yellow-400/20 bg-yellow-400/10 p-3 text-xs leading-5 text-yellow-100">
              <b className="text-yellow-300">🔑 API Key Sistemi</b>
              <br />
              Üyelik sistemi kaldırıldı. Maçları çekmek için üst bölümden kendi API keyini girmen yeterli.
            </div>

            <div className="mt-3 rounded-xl border border-red-400/20 bg-red-500/10 p-3 text-xs leading-5 text-red-200">
              <b>⚠️ Yasal Uyarı</b>
              <br />
              Bu platform yalnızca istatistiksel analiz sunar. Kesin kazanç garantisi vermez.
            </div>
          </div>
        </aside>

        <section className="min-w-0 p-4">
          <div className="w-full">
            <header className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-[#0b111c] px-4 py-3 shadow-xl">
              <div>
                <div className="text-xs font-black uppercase tracking-[0.25em] text-yellow-400">
                  ORAN ANALİZ
                </div>
                <h1 className="text-2xl font-black text-white">Ana Maç Ekranı</h1>
                <p className="text-xs text-slate-400">{todayText()}</p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <input
                  value={apiKey}
                  onChange={(e) => {
                    setApiKey(e.target.value);
                    localStorage.setItem("odds_api_key", e.target.value);
                  }}
                  placeholder="API Key..."
                  className="rounded-lg border border-white/10 bg-[#111827] px-3 py-2 text-xs text-white outline-none focus:border-yellow-400/60"
                />

                <button
                  onClick={() => setFilterOpen(true)}
                  className="rounded-lg border border-white/10 bg-[#121a2a] px-4 py-2 text-xs font-black text-white hover:border-yellow-400/50"
                >
                  ⚙️ Filtreler
                </button>

                <button
                  onClick={loadScanner}
                  className="rounded-lg bg-yellow-400 px-5 py-2 text-xs font-black text-black hover:bg-yellow-300"
                >
                  {loading ? "Analiz Ediliyor..." : "🚀 Analizi Başlat"}
                </button>
              </div>
            </header>

            {error && (
              <div className="mb-3 rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700">
                {error}
              </div>
            )}

            <div className="mb-3 grid gap-3 lg:grid-cols-3">
              <TopCard title="TOPLAM MAÇ" value={scanner?.total_matches || 0} sub="Analiz edilen maç" color="green" />
              <TopCard title="KUPONDA" value={coupon.length} sub="Seçili maç" color="blue" />
              <TopCard title="ORTALAMA GÜVEN" value={`%${averageScore}`} sub="AI güven ortalaması" color="dark" />
            </div>

            <section className="mb-3 rounded-xl border border-white/10 bg-[#0b111c] p-4 shadow-xl">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-black uppercase tracking-widest text-white">
                    Kontrol Paneli
                  </h2>
                  <p className="text-xs text-slate-400">
                    {dateOption} • {leagueSummary} • {seasonSummary} • Oran hassasiyeti {formatTolerance(tolerance)}
                  </p>
                </div>

                <div className="flex flex-wrap gap-2">
                  <FilterButton active={confidenceFilter === "all"} onClick={() => setConfidenceFilter("all")}>
                    Tümü
                  </FilterButton>
                  <FilterButton active={confidenceFilter === "high"} onClick={() => setConfidenceFilter("high")}>
                    🔥 Yüksek Güven
                  </FilterButton>
                  <FilterButton active={confidenceFilter === "mid"} onClick={() => setConfidenceFilter("mid")}>
                    🟡 Orta Güven
                  </FilterButton>
                  <FilterButton active={confidenceFilter === "risk"} onClick={() => setConfidenceFilter("risk")}>
                    🔴 Riskli
                  </FilterButton>
                </div>
              </div>

              <div className="grid gap-2 md:grid-cols-[1fr_1fr_1fr_1fr_auto]">
                <MiniInfo label="Tarih" value={dateOption} />
                <MiniInfo label="Lig" value={leagueSummary} />
                <MiniInfo label="Sezon" value={seasonSummary} />
                <MiniInfo label="Hassasiyet" value={formatTolerance(tolerance)} />
                <button
                  onClick={() => setFilterOpen(true)}
                  className="rounded-lg bg-yellow-400 px-4 py-3 text-xs font-black text-black hover:bg-yellow-300"
                >
                  Düzenle
                </button>
              </div>
            </section>

            <section className="rounded-xl border border-white/10 bg-[#0b111c] p-4 shadow-xl">
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-sm font-black uppercase tracking-widest text-white">
                    Maç Listesi
                  </h2>
                  <p className="text-xs text-slate-400">
                    Puan + güvene göre sıralı • {filteredMatches.length} maç gösteriliyor
                  </p>
                </div>

                <div className="rounded-lg bg-yellow-400/15 px-3 py-2 text-xs font-black text-yellow-300">
                  Tahmin değil, analiz.
                </div>
              </div>

              {matches.length === 0 && (
                <div className="rounded-xl border border-dashed border-yellow-400/30 bg-[#111827] p-10 text-center">
                  <div className="text-5xl">⚽</div>
                  <div className="mt-3 text-xl font-black text-white">Analiz bekleniyor</div>
                  <div className="mt-1 text-sm text-slate-400">
                    Başlamak için “Analizi Başlat” butonuna bas.
                  </div>
                </div>
              )}

              <div className="grid gap-2">
                {filteredMatches.map((m, i) => {
                  const score = safePercent(m.pro_score);
                  const playableScore = Number(m.playable_score || calcPlayableScore(m));
                  const risky = score < 55;
                  const realIndex = matches.findIndex(
                    (x) => x.home_team === m.home_team && x.away_team === m.away_team
                  );

                  return (
                    <div
                      key={`${m.home_team}-${m.away_team}-${i}`}
                      className="grid grid-cols-[78px_2fr_210px_100px_100px_115px_150px] items-center gap-3 rounded-xl border border-white/10 bg-[#111827] px-4 py-3 text-sm shadow hover:bg-[#151f33]"
                    >
                      <div className="text-center">
                        <div className="font-black text-white">{m.time || "20:00"}</div>
                        <div className="text-[10px] text-slate-500">Saat</div>
                      </div>

                      <div>
                        <div className="font-black text-white">
                          {m.home_team || "-"} - {m.away_team || "-"}
                        </div>
                        <div className="text-[11px] text-slate-400">
                          {m.league || "Lig"} • {m.match_type || "Maç tipi"} • {m.goal_profile || "Gol profili"}
                        </div>

                        <div className="mt-2 flex flex-wrap gap-1">
                          {(m.tolerance_hits || []).map((hit: string) => (
                            <span
                              key={hit}
                              className="rounded-md border border-yellow-400/20 bg-yellow-400/10 px-2 py-1 text-[10px] font-black text-yellow-300"
                            >
                              {hit}
                            </span>
                          ))}
                        </div>
                      </div>

                      <div>
                        <div className="mb-1 flex flex-wrap gap-1">
                          <span className="rounded-lg bg-yellow-400 px-3 py-1 text-xs font-black text-black">
                            {m.main_pick || m.selection || "-"}
                          </span>
                          <span className="rounded-lg border border-white/10 bg-[#0b111c] px-3 py-1 text-xs font-black text-slate-200">
                            Alt: {m.alternative_pick || "-"}
                          </span>
                        </div>

                        {m.combo_pick && (
                          <div
                            className={
                              m.combo_fit
                                ? "w-fit rounded-md bg-emerald-500/15 px-2 py-1 text-[10px] font-black text-emerald-300"
                                : "w-fit rounded-md bg-red-500/15 px-2 py-1 text-[10px] font-black text-red-300"
                            }
                          >
                            {m.combo_fit ? "Uyumlu Kombo: " : "Riskli Kombo: "}
                            {m.combo_pick}
                          </div>
                        )}
                      </div>

                      <div className="text-center">
                        <div className="text-lg font-black text-white">%{playableScore}</div>
                        <div className="text-[10px] text-slate-500">Puan</div>
                      </div>

                      <div className="text-center">
                        <div className={risky ? "text-lg font-black text-red-400" : "text-lg font-black text-yellow-300"}>
                          %{score}
                        </div>
                        <div className="mx-auto mt-1 h-1.5 w-16 rounded bg-[#263247]">
                          <div
                            className={risky ? "h-1.5 rounded bg-red-500" : "h-1.5 rounded bg-yellow-400"}
                            style={{ width: `${score}%` }}
                          />
                        </div>
                      </div>

                      <div className="text-center">
                        <div className="font-black text-white">{getSampleCount(m)}</div>
                        <div className="text-[10px] text-slate-500">Örnek maç</div>
                        <div className="mt-1 font-black text-yellow-300">{m.odd || "-"}</div>
                      </div>

                      <div className="flex justify-end gap-2">
                        <Link
                          href={`/match/${realIndex >= 0 ? realIndex : i}`}
                          onClick={() => openDetail(m, realIndex >= 0 ? realIndex : i)}
                          className="rounded-lg border border-white/10 px-3 py-2 text-xs font-black text-white hover:border-yellow-400/50"
                        >
                          Detay
                        </Link>

                        <button
                          onClick={() => addCoupon(m)}
                          className="rounded-lg bg-yellow-400 px-3 py-2 text-xs font-black text-black hover:bg-yellow-300"
                        >
                          + Kupon
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            <footer className="mt-3 rounded-xl border border-red-400/30 bg-red-500/10 p-4 text-xs leading-6 text-red-700">
              <b>⚠️ Yasal Uyarı:</b> Bu platform yalnızca istatistiksel analizler,
              geçmiş veri karşılaştırmaları ve yapay zekâ destekli tahminler sunar.
              Kesin kazanç garantisi verilmez. Bahis oynamak risk içerir.
            </footer>
          </div>
        </section>
      </div>

      {coupon.length > 0 && (
        <div className="fixed bottom-5 right-5 z-40 w-[380px] rounded-2xl border border-yellow-400/25 bg-[#07111f] p-4 text-white shadow-2xl">
          <div className="mb-3 flex items-center justify-between">
            <div>
              <div className="text-lg font-black">Kuponum</div>
              <div className="text-xs text-slate-500">{coupon.length} maç seçili</div>
            </div>

            <button
              onClick={() => setCoupon([])}
              className="rounded-lg border border-red-400/30 px-3 py-2 text-xs font-black text-red-300 hover:bg-red-500/10"
            >
              Temizle
            </button>
          </div>

          <div className="max-h-72 overflow-y-auto pr-1">
            {coupon.map((m, i) => (
              <div
                key={i}
                className="mb-2 flex items-center justify-between rounded-xl bg-[#0b1628] p-3 text-sm"
              >
                <div>
                  <div className="font-bold">{m.home_team} - {m.away_team}</div>
                  <div className="text-xs text-yellow-400">
                    {m.combo_pick || m.selection || m.main_pick} • {m.odd || "-"}
                  </div>
                </div>

                <button
                  onClick={() => removeCoupon(i)}
                  className="rounded-lg bg-red-500/15 px-3 py-2 text-red-300 hover:bg-red-500/25"
                >
                  🗑
                </button>
              </div>
            ))}
          </div>

          <div className="mt-3 rounded-xl border border-yellow-400/20 bg-yellow-400/10 p-3">
            <div className="text-xs text-yellow-200">Toplam Oran</div>
            <div className="text-3xl font-black text-yellow-300">{couponOdd}</div>
          </div>
        </div>
      )}

      {filterOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
          <div className="w-full max-w-6xl rounded-2xl border border-yellow-400/20 bg-[#0b111c] p-6 text-white shadow-2xl">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <h2 className="text-2xl font-black">Tarih, Lig, Sezon ve Hassasiyet</h2>
                <p className="text-sm text-slate-400">
                  Analiz yapılacak günü, ligleri, sezonları ve oran hassasiyetini seç.
                </p>
              </div>
              <button
                onClick={() => setFilterOpen(false)}
                className="rounded-lg bg-red-500 px-4 py-2 text-sm font-black text-white"
              >
                Kapat
              </button>
            </div>

            <div className="grid gap-5 lg:grid-cols-[0.8fr_0.8fr_1fr_1.4fr]">
              <div className="rounded-xl border border-white/10 bg-[#111827] p-4">
                <div className="mb-3 text-xs font-black uppercase text-yellow-400">
                  Tarih Seçimi
                </div>

                <div className="grid gap-2">
                  {DATE_OPTIONS.map((d) => (
                    <button
                      key={d}
                      onClick={() => setDateOption(d)}
                      className={`rounded-lg px-4 py-3 text-left text-sm font-black ${
                        dateOption === d
                          ? "bg-yellow-400 text-black"
                          : "bg-[#0b111c] text-slate-300 hover:bg-[#172238]"
                      }`}
                    >
                      {d}
                    </button>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-[#111827] p-4">
                <div className="mb-3 text-xs font-black uppercase text-yellow-400">
                  Sezon Seçimi
                </div>

                <div className="grid gap-2">
                  {SEASONS.map((season) => (
                    <label
                      key={season}
                      className="flex cursor-pointer items-center gap-3 rounded-lg bg-[#0b111c] px-4 py-3 text-sm hover:bg-[#172238]"
                    >
                      <input
                        type="checkbox"
                        checked={selectedSeasons.includes(season)}
                        onChange={() => toggleSeason(season)}
                        className="accent-yellow-400"
                      />
                      <span>{season}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-[#111827] p-4">
                <div className="mb-3 text-xs font-black uppercase text-yellow-400">
                  Oran Hassasiyeti
                </div>

                <div className="rounded-xl border border-yellow-400/20 bg-yellow-400/10 p-4 text-center">
                  <div className="text-4xl font-black text-yellow-300">
                    {formatTolerance(tolerance)}
                  </div>
                  <div className="mt-1 text-xs text-slate-400">
                    0.00 - 0.30 arası
                  </div>
                </div>

                <input
                  type="range"
                  min={0}
                  max={30}
                  step={1}
                  value={tolerance}
                  onChange={(e) => setTolerance(Number(e.target.value))}
                  className="mt-5 w-full accent-yellow-400"
                />

                <div className="mt-3 flex justify-between text-xs text-slate-500">
                  <span>0.00</span>
                  <span>0.15</span>
                  <span>0.30</span>
                </div>
              </div>

              <div className="rounded-xl border border-white/10 bg-[#111827] p-4">
                <div className="mb-3 text-xs font-black uppercase text-yellow-400">
                  Lig Seçimi
                </div>

                <input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Lig ara..."
                  className="mb-3 w-full rounded-lg border border-white/10 bg-[#0b111c] px-4 py-3 text-sm outline-none focus:border-yellow-400/60"
                />

                <div className="max-h-96 overflow-y-auto pr-2">
                  {filteredLeagues.map((league) => (
                    <label
                      key={league}
                      className="mb-2 flex cursor-pointer items-center gap-3 rounded-lg bg-[#0b111c] px-4 py-3 text-sm hover:bg-[#172238]"
                    >
                      <input
                        type="checkbox"
                        checked={
                          selectedLeagues.includes("🏆 Tüm Ligler") ||
                          selectedLeagues.includes(league)
                        }
                        onChange={() => toggleLeague(league)}
                        className="accent-yellow-400"
                      />
                      <span>{league}</span>
                    </label>
                  ))}
                </div>
              </div>
            </div>

            <button
              onClick={() => setFilterOpen(false)}
              className="mt-5 w-full rounded-xl bg-yellow-400 px-4 py-3 font-black text-black hover:bg-yellow-300"
            >
              Seçimi Uygula
            </button>
          </div>
        </div>
      )}






    </main>
  );
}

function SidebarItem({ icon, label, active }: any) {
  return (
    <div
      className={`flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm font-bold ${
        active
          ? "bg-yellow-400 text-black"
          : "text-slate-300 hover:bg-[#172238] hover:text-white"
      }`}
    >
      <span>{icon}</span>
      <span>{label}</span>
    </div>
  );
}

function TopCard({ title, value, sub, color }: any) {
  const cls =
    color === "green"
      ? "bg-[#14532d]"
      : color === "blue"
      ? "bg-[#12325f]"
      : "bg-[#1b2136]";

  return (
    <div className={`rounded-xl border border-white/10 ${cls} p-5 text-center shadow-xl`}>
      <div className="text-[10px] font-black uppercase tracking-[0.25em] text-slate-300">
        {title}
      </div>
      <div className="mt-2 text-4xl font-black text-white">{value}</div>
      <div className="mt-2 text-xs font-bold text-slate-300">{sub}</div>
    </div>
  );
}

function MiniInfo({ label, value }: any) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#111827] px-4 py-3">
      <div className="text-[10px] font-black uppercase tracking-widest text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-sm font-black text-white">{value}</div>
    </div>
  );
}

function FilterButton({ active, onClick, children }: any) {
  return (
    <button
      onClick={onClick}
      className={
        active
          ? "rounded-lg bg-yellow-400 px-3 py-2 text-xs font-black text-black"
          : "rounded-lg border border-white/10 bg-[#111827] px-3 py-2 text-xs font-black text-slate-300 hover:border-yellow-400/50"
      }
    >
      {children}
    </button>
  );
}
