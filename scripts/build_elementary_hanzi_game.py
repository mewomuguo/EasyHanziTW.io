#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build 小學全字庫 game HTML: entries from 小學全字庫.md, levels from 字頻總表 ranks."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FREQ_PATH = ROOT / "108課鋼-字頻總表.md"
LIB_PATH = ROOT / "108課鋼-小學全字庫.md"
IDS_PATH = ROOT / "scripts" / "cjkvi-ids.txt"
OUT_PATH = ROOT / "小學字遊戲.html"

# 無字頻表時的排序權重（排在最後，仍分級）
MISSING_RANK = 99999

# IDS 運算符（含嵌套）；僅採用扁平 ⿰⿱ 且兩側皆單一字元者作為組字題
IDS_OPS = set("⿰⿱⿲⿳⿴⿵⿶⿷⿸⿹⿺⿻")


def load_freq_ranks() -> dict[str, int]:
    ranks: dict[str, int] = {}
    line_re = re.compile(r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|")
    with FREQ_PATH.open(encoding="utf-8") as f:
        for line in f:
            m = line_re.match(line.strip())
            if not m:
                continue
            rank = int(m.group(1))
            ch = m.group(2).strip()
            if len(ch) != 1:
                continue
            # 保留第一次（最高頻）
            if ch not in ranks:
                ranks[ch] = rank
    return ranks


def split_flat_binary_ids(ids: str) -> tuple[str, str, str] | None:
    """若 IDS 為扁平 ⿰／⿱，且兩側皆單一字元（無嵌套），回傳 (運算, 左或上, 右或下)。"""
    ids = ids.strip()
    if len(ids) < 3:
        return None
    op = ids[0]
    if op not in "⿰⿱":
        return None

    def grab_leaf(s: str, i: int) -> tuple[str | None, int]:
        if i >= len(s):
            return None, i
        if s[i] in IDS_OPS:
            return None, i
        return s[i], i + 1

    a, i2 = grab_leaf(ids, 1)
    if a is None:
        return None
    b, i3 = grab_leaf(ids, i2)
    if b is None:
        return None
    if i3 != len(ids):
        return None
    return op, a, b


def load_ids_compositions(path: Path) -> dict[str, tuple[str, str, str]]:
    """字 → (⿰|⿱, 部件甲, 部件乙)。同一字多行取首次。"""
    out: dict[str, tuple[str, str, str]] = {}
    if not path.is_file():
        return out
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 2)
            if len(parts) < 3:
                continue
            ch, ids = parts[1], parts[2]
            if len(ch) != 1:
                continue
            triple = split_flat_binary_ids(ids)
            if triple is None:
                continue
            if ch not in out:
                out[ch] = triple
    return out


def build_compose_entries(
    entries: list[dict], char_to_comp: dict[str, tuple[str, str, str]]
) -> list[dict]:
    out: list[dict] = []
    for e in entries:
        ch = e["c"]
        if ch not in char_to_comp:
            continue
        op, a, b = char_to_comp[ch]
        ne = {k: e[k] for k in ("c", "z", "b", "s", "e", "r")}
        ne["parts"] = [a, b]
        ne["cmp"] = op
        out.append(ne)
    return out


def polyphone_chars(entries: list[dict]) -> set[str]:
    zmap: dict[str, set[str]] = defaultdict(set)
    for e in entries:
        zmap[e["c"]].add(e["z"])
    return {c for c, zs in zmap.items() if len(zs) > 1}


def cumulative_by_level(leveled_entries: list[dict]) -> dict[str, list[dict]]:
    tiers: dict[str, list[dict]] = {"1": [], "2": [], "3": [], "4": [], "5": []}
    for e in leveled_entries:
        tiers[str(e["lv"])].append(e)
    by_level: dict[str, list[dict]] = {}
    acc: list[dict] = []
    for lv in range(1, 6):
        acc.extend(tiers[str(lv)])
        by_level[str(lv)] = acc[:]
    return by_level


def parse_dictionary_entries(text: str) -> list[dict]:
    """Split 小學全字庫 into entries; each ## 字 (注音) block."""
    blocks = re.split(r"(?=^## .+ \(.+\)\s*$)", text, flags=re.MULTILINE)
    entries: list[dict] = []
    header_re = re.compile(r"^## (.+?) \((.+?)\)\s*$")
    bushou_re = re.compile(r"- \*\*部首\*\*:\s*(.+)")
    strokes_re = re.compile(r"- \*\*總筆畫數\*\*:\s*(\d+)")
    explain_re = re.compile(r"### 解釋\s*\n(.*?)(?=\n---\s*$|\Z)", re.DOTALL)

    for block in blocks:
        block = block.strip()
        if not block.startswith("## "):
            continue
        hm = header_re.match(block.split("\n", 1)[0])
        if not hm:
            continue
        char = hm.group(1).strip()
        zhuyin = hm.group(2).strip()
        if len(char) != 1:
            continue

        bushou = ""
        sm = bushou_re.search(block)
        if sm:
            bushou = sm.group(1).strip()

        strokes = ""
        tm = strokes_re.search(block)
        if tm:
            strokes = tm.group(1)

        expl = ""
        em = explain_re.search(block)
        if em:
            expl = em.group(1).strip()
            expl = re.sub(r"\s+", " ", expl)
            if len(expl) > 320:
                expl = expl[:320] + "…"

        entries.append(
            {
                "c": char,
                "z": zhuyin,
                "b": bushou,
                "s": strokes,
                "e": expl,
            }
        )
    return entries


def assign_levels(entries: list[dict], ranks: dict[str, int]) -> None:
    for e in entries:
        e["r"] = ranks.get(e["c"], MISSING_RANK)

    entries.sort(key=lambda x: (x["r"], x["c"], x["z"]))

    n = len(entries)
    if n == 0:
        return
    # 五等分（字頻序愈小愈前 → LV1 最易）
    for i, e in enumerate(entries):
        bucket = min(4, (i * 5) // n)
        e["lv"] = bucket + 1


def build_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>小學全字庫 · 認字遊戲</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+TC:wght@400;600;700&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --bg: #f4f0e8;
      --card: #fffef9;
      --ink: #1a1a1a;
      --muted: #5c5346;
      --accent: #2d6a4f;
      --accent2: #bc6c25;
      --wrong: #9b2335;
      --ok: #1b7f5a;
      --border: #d4cbb8;
      --shadow: rgba(45, 42, 38, 0.08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", sans-serif;
      background: linear-gradient(165deg, #ebe4d6 0%, var(--bg) 45%, #e8e2d4 100%);
      color: var(--ink);
      line-height: 1.5;
    }}
    .wrap {{
      max-width: 42rem;
      margin: 0 auto;
      padding: 1.25rem 1rem 3rem;
    }}
    header {{
      text-align: center;
      margin-bottom: 1.5rem;
    }}
    header h1 {{
      font-size: 1.35rem;
      font-weight: 700;
      margin: 0 0 0.35rem;
      letter-spacing: 0.06em;
    }}
    header p {{
      margin: 0;
      font-size: 0.85rem;
      color: var(--muted);
    }}
    .panel {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 1.1rem 1rem;
      box-shadow: 0 8px 28px var(--shadow);
      margin-bottom: 1rem;
    }}
    .row {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      align-items: center;
      justify-content: center;
      margin-bottom: 0.75rem;
    }}
    label {{
      font-size: 0.8rem;
      color: var(--muted);
      margin-right: 0.25rem;
    }}
    select, button {{
      font: inherit;
      border-radius: 8px;
      border: 1px solid var(--border);
      padding: 0.45rem 0.75rem;
      background: #fff;
      cursor: pointer;
    }}
    select:focus, button:focus {{
      outline: 2px solid var(--accent);
      outline-offset: 2px;
    }}
    button.primary {{
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
      font-weight: 600;
    }}
    button.ghost {{
      background: transparent;
    }}
    .quiz-area {{
      text-align: center;
      min-height: 12rem;
    }}
    .char-display {{
      font-size: 5rem;
      font-weight: 700;
      line-height: 1.1;
      margin: 0.5rem 0 0.25rem;
      font-family: "Noto Sans TC", serif;
    }}
    .meta {{
      font-size: 0.8rem;
      color: var(--muted);
      margin-bottom: 1rem;
    }}
    .choices {{
      display: grid;
      gap: 0.5rem;
      margin-top: 0.75rem;
    }}
    .choices button {{
      width: 100%;
      text-align: left;
      padding: 0.65rem 0.85rem;
      transition: background 0.15s, border-color 0.15s;
    }}
    .choices button:hover:not(:disabled) {{
      background: #f0ebe0;
    }}
    .choices button:disabled {{
      cursor: default;
      opacity: 0.95;
    }}
    .choices button.correct {{
      border-color: var(--ok);
      background: #e8f5ef;
    }}
    .choices button.incorrect {{
      border-color: var(--wrong);
      background: #fce8ec;
    }}
    .score {{
      font-size: 0.9rem;
      color: var(--muted);
    }}
    .flash {{
      margin-top: 1rem;
      padding: 0.75rem;
      border-radius: 10px;
      background: #f5f1e8;
      border: 1px dashed var(--border);
      font-size: 0.85rem;
      text-align: left;
      max-height: 8rem;
      overflow-y: auto;
    }}
    .flash .zhuyin {{ color: var(--accent2); font-weight: 600; }}
    footer {{
      text-align: center;
      font-size: 0.75rem;
      color: var(--muted);
      margin-top: 1.5rem;
    }}
    .timer-row {{
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: center;
      gap: 0.75rem;
      margin-top: 0.5rem;
      padding-top: 0.75rem;
      border-top: 1px dashed var(--border);
    }}
    #timerDisplay {{
      font-variant-numeric: tabular-nums;
      font-weight: 700;
      font-size: 1.1rem;
      min-width: 5rem;
      text-align: center;
      color: var(--accent);
    }}
    #timerDisplay.warn {{ color: var(--accent2); }}
    #timerDisplay.danger {{ color: var(--wrong); }}
    #btnPause:disabled {{
      opacity: 0.45;
      cursor: not-allowed;
    }}
    .overlay {{
      position: fixed;
      inset: 0;
      z-index: 1000;
      background: rgba(36, 32, 28, 0.55);
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 1rem;
    }}
    .overlay[hidden] {{ display: none !important; }}
    .overlay-box {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 1.5rem 1.35rem;
      max-width: 22rem;
      width: 100%;
      text-align: center;
      box-shadow: 0 16px 48px rgba(0,0,0,0.18);
    }}
    .overlay-box h2 {{
      margin: 0 0 0.35rem;
      font-size: 1.2rem;
    }}
    .overlay-box p {{
      margin: 0 0 1rem;
      font-size: 0.9rem;
      color: var(--muted);
    }}
    .overlay-actions {{
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }}
    .overlay-actions button {{
      width: 100%;
    }}
    @media (max-width: 480px) {{
      .char-display {{ font-size: 4rem; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1>小學全字庫 · 認字遊戲</h1>
      <p>題庫來自《小學全字庫》條目；依《字頻總表》字頻序將條目分為五層難度後，<strong>高級包含所有較易級</strong>。<strong>多音字</strong>模式僅出現一字多音之字；<strong>組合字</strong>模式依 CJKVI IDS 資料，採左右（⿰）或上下（⿱）兩部件可扁平拆解之字（例：木＋古＝枯）。每題仍標示該條所屬層級（lv）。</p>
    </header>

    <div class="panel">
      <div class="row">
        <div>
          <label for="lv">難度</label>
          <select id="lv" aria-label="難度等級">
            <option value="1">LV1（最易約 20%）</option>
            <option value="2">LV2（含 LV1）</option>
            <option value="3">LV3（含 LV1–2）</option>
            <option value="4">LV4（含 LV1–3）</option>
            <option value="5">LV5（全部用字）</option>
            <option value="0">全部級別</option>
          </select>
        </div>
        <div>
          <label for="mode">模式</label>
          <select id="mode" aria-label="遊戲模式">
            <option value="zhuyin">選注音</option>
            <option value="char">選漢字（聽注音）</option>
            <option value="poly_zhuyin">多音字：選注音</option>
            <option value="poly_char">多音字：選漢字</option>
            <option value="compose">組合字（部件組字）</option>
          </select>
        </div>
        <div>
          <label for="timeMode">計時</label>
          <select id="timeMode" aria-label="計時模式">
            <option value="inf">無限時</option>
            <option value="60">1 分鐘</option>
            <option value="180">3 分鐘</option>
            <option value="300">5 分鐘</option>
            <option value="420">7 分鐘</option>
          </select>
        </div>
      </div>
      <div class="timer-row">
        <span id="timerDisplay" aria-live="polite">無限時</span>
        <button type="button" class="ghost" id="btnPause" disabled>暫停</button>
      </div>
      <div class="row">
        <button type="button" class="primary" id="btnNext">下一題</button>
        <button type="button" class="ghost" id="btnReveal">看解答／釋義</button>
      </div>
      <p class="score" id="scoreLine">答對 0 / 0</p>
    </div>

    <div class="panel quiz-area" id="quiz">
      <div class="char-display" id="bigChar">—</div>
      <p class="meta" id="promptLine"></p>
      <div class="choices" id="choices"></div>
      <div class="flash" id="explainBox" hidden>
        <div><span class="zhuyin" id="exZy"></span> · 部首 <span id="exB"></span> · <span id="exS"></span> 畫</div>
        <p id="exE" style="margin:0.5rem 0 0;"></p>
      </div>
    </div>

    <footer>
      資料：教育部相關字表與字典迷你版結構之學習用整理 · 離線可開啟本 HTML
    </footer>
  </div>

  <div class="overlay" id="overlayPause" hidden role="dialog" aria-modal="true" aria-labelledby="pauseTitle">
    <div class="overlay-box">
      <h2 id="pauseTitle">作答已暫停</h2>
      <p>計時已停止，選擇下一步。</p>
      <div class="overlay-actions">
        <button type="button" class="primary" id="btnResume">繼續作答</button>
        <button type="button" class="ghost" id="btnHomeFromPause">回首頁</button>
      </div>
    </div>
  </div>

  <div class="overlay" id="overlayTimeup" hidden role="dialog" aria-modal="true" aria-labelledby="timeupTitle">
    <div class="overlay-box">
      <h2 id="timeupTitle">時間到</h2>
      <p id="timeupScore">本局答對 0 / 0</p>
      <div class="overlay-actions">
        <button type="button" class="primary" id="btnPlayAgain">再玩一局</button>
        <button type="button" class="ghost" id="btnHomeFromTimeup">回首頁</button>
      </div>
    </div>
  </div>

  <script id="game-data" type="application/json">{payload}</script>
  <script>
(function () {{
  const DATA = JSON.parse(document.getElementById("game-data").textContent);
  const entries = DATA.entries;
  const byLevel = DATA.byLevel;
  const polyByLevel = DATA.polyByLevel || {{}};
  const composeByLevel = DATA.composeByLevel || {{}};

  let correct = 0, total = 0;
  let current = null;
  let answered = false;

  let atHome = true;
  let timeUp = false;
  let paused = false;
  let timerId = null;
  let timeLeftSec = 0;
  let sessionClockStarted = false;

  const el = (id) => document.getElementById(id);
  const lvSel = el("lv"), modeSel = el("mode"), timeSel = el("timeMode");
  const bigChar = el("bigChar"), promptLine = el("promptLine");
  const choicesEl = el("choices"), explainBox = el("explainBox");
  const scoreLine = el("scoreLine");
  const timerDisplay = el("timerDisplay");
  const btnPause = el("btnPause");
  const overlayPause = el("overlayPause");
  const overlayTimeup = el("overlayTimeup");

  function pool() {{
    const mode = modeSel.value;
    const v = lvSel.value;
    const key = v === "0" ? "5" : String(parseInt(v, 10));
    if (mode === "compose") {{
      if (v === "0") return composeByLevel["5"] || [];
      return composeByLevel[key] || [];
    }}
    if (mode === "poly_zhuyin" || mode === "poly_char") {{
      if (v === "0") return polyByLevel["5"] || [];
      return polyByLevel[key] || [];
    }}
    if (v === "0") return entries;
    return byLevel[key] || [];
  }}

  function getTimeLimitSec() {{
    const v = timeSel.value;
    if (v === "inf") return null;
    return parseInt(v, 10);
  }}

  function formatTime(sec) {{
    const n = Math.max(0, sec | 0);
    const m = Math.floor(n / 60);
    const s = n % 60;
    return m + ":" + (s < 10 ? "0" : "") + s;
  }}

  function updateTimerStyle() {{
    timerDisplay.classList.remove("warn", "danger");
    const lim = getTimeLimitSec();
    if (lim == null || atHome || timeUp) return;
    if (timeLeftSec <= 10) timerDisplay.classList.add("danger");
    else if (timeLeftSec <= 30) timerDisplay.classList.add("warn");
  }}

  function refreshTimerDisplay() {{
    const lim = getTimeLimitSec();
    if (lim == null) {{
      timerDisplay.textContent = "無限時";
      timerDisplay.classList.remove("warn", "danger");
      return;
    }}
    if (atHome) {{
      timerDisplay.textContent = formatTime(lim);
      timerDisplay.classList.remove("warn", "danger");
      return;
    }}
    timerDisplay.textContent = formatTime(timeLeftSec);
    updateTimerStyle();
  }}

  function stopTimerTick() {{
    if (timerId != null) {{
      clearInterval(timerId);
      timerId = null;
    }}
  }}

  function tickTimer() {{
    if (paused || timeUp || atHome) return;
    timeLeftSec -= 1;
    refreshTimerDisplay();
    if (timeLeftSec <= 0) {{
      stopTimerTick();
      timeUp = true;
      btnPause.disabled = true;
      el("timeupScore").textContent =
        "本局答對 " + correct + " / " + total;
      overlayTimeup.hidden = false;
    }}
  }}

  function startTimerFromLimit() {{
    const lim = getTimeLimitSec();
    stopTimerTick();
    if (lim == null) {{
      refreshTimerDisplay();
      return;
    }}
    timeLeftSec = lim;
    timerId = setInterval(tickTimer, 1000);
    refreshTimerDisplay();
  }}

  function showHomePlaceholder() {{
    atHome = true;
    timeUp = false;
    paused = false;
    sessionClockStarted = false;
    stopTimerTick();
    overlayPause.hidden = true;
    overlayTimeup.hidden = true;
    correct = 0;
    total = 0;
    current = null;
    answered = false;
    explainBox.hidden = true;
    choicesEl.innerHTML = "";
    bigChar.textContent = "—";
    promptLine.textContent =
      "請選擇難度、模式與計時，按「下一題」開始作答。";
    scoreLine.textContent = "答對 0 / 0";
    refreshTimerDisplay();
    btnPause.disabled = true;
  }}

  function goHome() {{
    showHomePlaceholder();
  }}

  function keyOf(x) {{ return x.c + "\\t" + x.z; }}

  function pickDistractors(pool, current, need) {{
    const excludeKey = keyOf(current);
    const candidates = pool.filter((x) => keyOf(x) !== excludeKey);
    const out = [];
    const used = new Set();
    const tryAdd = (arr) => {{
      for (const x of arr) {{
        if (out.length >= need) return;
        const k = keyOf(x);
        if (used.has(k)) continue;
        used.add(k);
        out.push(x);
      }}
    }};
    const otherChar = shuffle(candidates.filter((x) => x.c !== current.c));
    tryAdd(otherChar);
    if (out.length < need) {{
      const rest = shuffle(candidates.filter((x) => !used.has(keyOf(x))));
      tryAdd(rest);
    }}
    return out.slice(0, need);
  }}

  function shuffle(a) {{
    for (let i = a.length - 1; i > 0; i--) {{
      const j = Math.floor(Math.random() * (i + 1));
      [a[i], a[j]] = [a[j], a[i]];
    }}
    return a;
  }}

  function showExplain(e) {{
    el("exZy").textContent = e.z;
    el("exB").textContent = e.b || "—";
    el("exS").textContent = e.s || "—";
    el("exE").textContent = e.e || "（無釋義摘要）";
    explainBox.hidden = false;
  }}

  function nextQuestion() {{
    if (timeUp) return;
    if (paused) return;
    answered = false;
    explainBox.hidden = true;
    const p = pool();
    if (!p.length) {{
      atHome = true;
      sessionClockStarted = false;
      stopTimerTick();
      bigChar.textContent = "—";
      const md = modeSel.value;
      let emptyMsg = "此級別無題目，請換級別。";
      if (md === "compose")
        emptyMsg = "此級別沒有組合字題目，請換難度或改選其他模式。";
      else if (md === "poly_zhuyin" || md === "poly_char")
        emptyMsg = "此級別沒有多音字題目，請換難度。";
      promptLine.textContent = emptyMsg;
      choicesEl.innerHTML = "";
      btnPause.disabled = true;
      return;
    }}
    atHome = false;
    current = p[Math.floor(Math.random() * p.length)];
    const mode = modeSel.value;
    const distractors = pickDistractors(p, current, 3);
    const opts = shuffle([current, ...distractors].slice(0, 4));
    const dupChar = opts.some((a, i) => opts.some((b, j) => j !== i && a.c === b.c));
    const isPoly = mode === "poly_zhuyin" || mode === "poly_char";
    const polyTag = isPoly ? "【多音字】" : "";

    if (mode === "compose") {{
      bigChar.textContent = "？";
      const cmpLabel = current.cmp === "⿱" ? "上下" : "左右";
      promptLine.textContent =
        "【組合字（" + cmpLabel + "）】" +
        current.parts[0] +
        " ＋ " +
        current.parts[1] +
        " ＝ ？　請選正確的漢字（字頻序 " +
        current.r +
        " · LV" +
        current.lv +
        "）";
      choicesEl.innerHTML = "";
      opts.forEach((o) => {{
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = dupChar ? o.c + "（" + o.z + "）" : o.c;
        b.style.fontSize = dupChar ? "1.1rem" : "1.75rem";
        b.addEventListener("click", () => chooseChar(o, b, opts));
        choicesEl.appendChild(b);
      }});
    }} else if (mode === "zhuyin" || mode === "poly_zhuyin") {{
      bigChar.textContent = current.c;
      promptLine.textContent =
        polyTag +
        "請選正確注音（字頻序 " +
        current.r +
        " · LV" +
        current.lv +
        "）";
      choicesEl.innerHTML = "";
      opts.forEach((o) => {{
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = o.z;
        b.addEventListener("click", () => chooseZhuyin(o, b, opts));
        choicesEl.appendChild(b);
      }});
    }} else {{
      bigChar.textContent = "？";
      promptLine.textContent =
        polyTag +
        "注音：「" +
        current.z +
        "」— 請選正確的漢字（LV" +
        current.lv +
        "）";
      choicesEl.innerHTML = "";
      opts.forEach((o) => {{
        const b = document.createElement("button");
        b.type = "button";
        b.textContent = dupChar ? o.c + "（" + o.z + "）" : o.c;
        b.style.fontSize = dupChar ? "1.1rem" : "1.75rem";
        b.addEventListener("click", () => chooseChar(o, b, opts));
        choicesEl.appendChild(b);
      }});
    }}
    if (!sessionClockStarted) {{
      sessionClockStarted = true;
      const lim = getTimeLimitSec();
      if (lim != null) startTimerFromLimit();
      else refreshTimerDisplay();
    }}
    btnPause.disabled = false;
  }}

  function chooseZhuyin(o, btn, all) {{
    if (paused || timeUp) return;
    if (answered) return;
    answered = true;
    total++;
    const ok = keyOf(o) === keyOf(current);
    if (ok) correct++;
    all.forEach((x, i) => {{
      const button = choicesEl.children[i];
      if (keyOf(x) === keyOf(current)) button.classList.add("correct");
      else if (x === o && !ok) button.classList.add("incorrect");
      button.disabled = true;
    }});
    scoreLine.textContent = "答對 " + correct + " / " + total;
    showExplain(current);
  }}

  function chooseChar(o, btn, all) {{
    if (paused || timeUp) return;
    if (answered) return;
    answered = true;
    total++;
    const ok = keyOf(o) === keyOf(current);
    if (ok) correct++;
    all.forEach((x, i) => {{
      const button = choicesEl.children[i];
      if (keyOf(x) === keyOf(current)) button.classList.add("correct");
      else if (x === o && !ok) button.classList.add("incorrect");
      button.disabled = true;
    }});
    scoreLine.textContent = "答對 " + correct + " / " + total;
    showExplain(current);
  }}

  el("btnNext").addEventListener("click", nextQuestion);
  el("btnReveal").addEventListener("click", () => {{
    if (paused || timeUp) return;
    if (current) showExplain(current);
  }});
  lvSel.addEventListener("change", () => {{
    if (!paused && !timeUp) nextQuestion();
  }});
  modeSel.addEventListener("change", () => {{
    if (!paused && !timeUp) nextQuestion();
  }});
  timeSel.addEventListener("change", () => {{
    goHome();
  }});

  btnPause.addEventListener("click", () => {{
    if (atHome || timeUp) return;
    paused = true;
    stopTimerTick();
    overlayPause.hidden = false;
  }});

  el("btnResume").addEventListener("click", () => {{
    paused = false;
    overlayPause.hidden = true;
    const lim = getTimeLimitSec();
    if (lim != null && timeLeftSec > 0 && !timeUp) {{
      if (timerId == null) timerId = setInterval(tickTimer, 1000);
    }}
    refreshTimerDisplay();
  }});

  el("btnHomeFromPause").addEventListener("click", () => {{
    overlayPause.hidden = true;
    paused = false;
    goHome();
  }});

  el("btnPlayAgain").addEventListener("click", () => {{
    overlayTimeup.hidden = true;
    timeUp = false;
    paused = false;
    correct = 0;
    total = 0;
    scoreLine.textContent = "答對 0 / 0";
    sessionClockStarted = false;
    stopTimerTick();
    nextQuestion();
  }});

  el("btnHomeFromTimeup").addEventListener("click", () => {{
    overlayTimeup.hidden = true;
    timeUp = false;
    paused = false;
    goHome();
  }});

  showHomePlaceholder();
}})();
  </script>
</body>
</html>
"""


def main() -> None:
    ranks = load_freq_ranks()
    text = LIB_PATH.read_text(encoding="utf-8")
    entries = parse_dictionary_entries(text)
    assign_levels(entries, ranks)

    # 內層 lv 仍為「本條所屬 quintile」（1～5）；題庫池 byLevel 為累積：高級含所有較易級
    by_level = cumulative_by_level(entries)

    multi = polyphone_chars(entries)
    poly_entries = [
        {k: e[k] for k in ("c", "z", "b", "s", "e", "r")}
        for e in entries
        if e["c"] in multi
    ]
    assign_levels(poly_entries, ranks)
    poly_by_level = cumulative_by_level(poly_entries)

    char_to_comp = load_ids_compositions(IDS_PATH)
    compose_entries = build_compose_entries(entries, char_to_comp)
    assign_levels(compose_entries, ranks)
    compose_by_level = cumulative_by_level(compose_entries)

    def serialize_standard(e: dict) -> dict:
        return {k: e[k] for k in ("c", "z", "b", "s", "e", "r", "lv")}

    def serialize_compose(e: dict) -> dict:
        d = serialize_standard(e)
        d["parts"] = e["parts"]
        d["cmp"] = e["cmp"]
        return d

    out_entries = [serialize_standard(e) for e in entries]
    data = {
        "entries": out_entries,
        "byLevel": {k: [serialize_standard(x) for x in v] for k, v in by_level.items()},
        "polyByLevel": {k: [serialize_standard(x) for x in v] for k, v in poly_by_level.items()},
        "composeByLevel": {k: [serialize_compose(x) for x in v] for k, v in compose_by_level.items()},
    }
    html = build_html(data)
    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {len(entries)} entries -> {OUT_PATH}")
    for i in range(1, 6):
        print(f"  LV{i}: {len(by_level[str(i)])}")
    print(f"  poly total: {len(poly_entries)}")
    print(f"  compose total: {len(compose_entries)} (IDS: {IDS_PATH.name})")


if __name__ == "__main__":
    main()
