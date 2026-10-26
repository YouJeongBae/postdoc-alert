"""포닥·장학금·산업체 공고를 모아 카카오톡으로 매일 알려주는 스크립트.

사용법:
  python main.py            # 실제 실행 (카톡 전송 + 상태 저장)
  python main.py --dry-run  # 테스트: 수집 결과와 보낼 메시지만 출력
"""
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

from kakao import KakaoClient

ROOT = Path(__file__).parent
STATE_PATH = ROOT / "state" / "state.json"
DIGEST_PATH = ROOT / "docs" / "index.html"
NEW_TOKEN_PATH = ROOT / ".new_refresh_token"
KST = dt.timezone(dt.timedelta(hours=9))
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
CATEGORY_KO = {"academic": "학계", "industry": "산업체", "national_lab": "국립연구소"}
HISTORY_DAYS = 14


# ---------------- 공통 ----------------
def clean(text):
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return " ".join(text.split())


def make_id(url):
    return hashlib.sha1(url.encode()).hexdigest()[:12]


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE_PATH.parent.mkdir(exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------- 수집: 학계 사이트 ----------------
def fetch_html_source(src):
    r = requests.get(src["url"], headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    pattern = re.compile(src["link_pattern"])
    items, seen, raw = [], set(), 0
    for a in soup.find_all("a", href=True):
        href = a["href"]
        path = urlparse(href).path if href.startswith("http") else href
        if not pattern.search(path):
            continue
        url = urljoin(src["url"], href).split("#")[0]
        title = clean(a.get_text(" "))
        if len(title) < 8 or url in seen:
            continue
        raw += 1
        if not matches_any(title, src.get("require_any")):
            continue
        seen.add(url)
        items.append({
            "id": make_id(url), "title": title[:150], "url": url,
            "source": src["name"], "category": src["category"],
            "region": src.get("region", ""), "org": src.get("org", ""), "text": title,
            "tag": src.get("tag", ""),
        })
    return items, raw


def matches_any(text, words):
    """words가 비어 있으면 통과, 있으면 하나라도 포함돼야 통과."""
    if not words:
        return True
    t = text.lower()
    return any(w.lower() in t for w in words)


# ---------------- 수집: SmartRecruiters 공개 API (Bosch 등) ----------------
def fetch_smartrecruiters(src):
    items, seen = [], set()
    countries = {c.lower() for c in src.get("countries", [])}
    for q in src["queries"]:
        r = requests.get(f"https://api.smartrecruiters.com/v1/companies/{src['company_id']}/postings",
                         params={"q": q, "limit": 100}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        for p in r.json().get("content", []):
            loc = p.get("location") or {}
            country = (loc.get("country") or "").lower()
            if countries and country not in countries:
                continue
            pid = str(p.get("id"))
            if pid in seen:
                continue
            seen.add(pid)
            url = f"https://jobs.smartrecruiters.com/{src['company_id']}/{pid}"
            title = clean(p.get("name"))
            items.append({
                "id": f"sr-{pid}", "title": title[:150], "url": url, "source": src["name"],
                "category": src.get("category", "industry"), "region": country.upper(),
                "org": src.get("org", src["name"]), "text": title, "tag": src.get("tag", ""),
            })
    return items


# ---------------- 수집: Adzuna API (산업체·미국) ----------------
def fetch_adzuna(cfg):
    app_id, app_key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not (app_id and app_key):
        return [], ["Adzuna 키 없음"]
    labs = [x.lower() for x in cfg.get("national_labs", [])]
    items, errors = [], []
    for q in cfg["queries"]:
        for country in q.get("countries", cfg["countries"]):
            params = {
                "app_id": app_id, "app_key": app_key, "results_per_page": 50,
                "max_days_old": cfg.get("max_days_old", 3), "content-type": "application/json",
            }
            for k in ("what", "what_phrase", "what_or", "what_and", "what_exclude"):
                if q.get(k):
                    params[k] = q[k]
            try:
                r = requests.get(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1",
                                 params=params, timeout=30)
                r.raise_for_status()
            except Exception as e:
                errors.append(f"Adzuna-{country}: {str(e)[:60]}")
                continue
            for j in r.json().get("results", []):
                company = clean((j.get("company") or {}).get("display_name", ""))
                cat = "national_lab" if any(l in company.lower() for l in labs) else q["category"]
                url = j.get("redirect_url", "")
                items.append({
                    "id": f"adz-{j.get('id')}", "title": clean(j.get("title"))[:150], "url": url,
                    "source": "Adzuna", "category": cat, "region": country.upper(), "org": company,
                    "text": clean(f"{j.get('title', '')} {j.get('description', '')}"),
                    "tag": q.get("tag", ""),
                })
    return items, errors


# ---------------- 필터 ----------------
def is_excluded(item, keywords):
    t = item["title"].lower()
    return any(k.lower() in t for k in keywords)


def visa_note(item, flags):
    t = item["text"].lower()
    for f in flags:
        if f.lower() in t:
            return f"⛔ 비자 제한 문구: '{f}'"
    if item["region"] == "US" or item["category"] == "national_lab":
        return "⚠️ 비자 스폰서 여부 확인 필요"
    return ""


# ---------------- 훔볼트 ----------------
def next_open_date(open_dates, today):
    cands = []
    for md in open_dates:
        m, d = map(int, md.split("-"))
        for y in (today.year, today.year + 1):
            od = dt.date(y, m, d)
            if od >= today:
                cands.append(od)
    return min(cands)


def check_humboldt(cfg, state, today):
    msgs, error = [], None
    prev = state.get("humboldt_status")
    try:
        r = requests.get(cfg["url"], headers=HEADERS, timeout=30)
        r.raise_for_status()
        status = "closed" if cfg["closed_marker"].lower() in r.text.lower() else "open"
    except Exception as e:
        status, error = prev or "unknown", f"Humboldt: {str(e)[:60]}"
    if not error:
        if prev and prev != status:
            msgs.append("🟢 훔볼트 연구 펠로십 지원 창구가 열렸어요! 800건이 차면 바로 마감되니 서두르세요."
                        if status == "open" else
                        "🔴 훔볼트 연구 펠로십 지원 창구가 마감됐어요 (800건 도달).")
        state["humboldt_status"] = status
    nod = next_open_date(cfg["open_dates"], today)
    if status != "open" and (nod - today).days == cfg["remind_days_before"]:
        msgs.append(f"⏰ 훔볼트 펠로십 다음 모집이 {nod:%m/%d}에 열려요 (D-{(nod - today).days}). "
                    "호스트 서류와 추천서 준비 상태를 확인하세요.")
    return msgs, error, status, nod


# ---------------- 날짜형 리마인더 (MSCA 등) ----------------
def check_deadlines(reminders, today):
    msgs, upcoming = [], []
    for r in reminders or []:
        for ev in r["events"]:
            d = dt.date.fromisoformat(ev["date"])
            left = (d - today).days
            if left >= 0:
                upcoming.append((left, f"{r['name']} {ev['label']} D-{left}"))
            if left in ev.get("offsets", []):
                when = "오늘!" if left == 0 else f"{left}일 남음 ({d:%m/%d})"
                text = f"⏰ {r['name']} {ev['label']}: {when}"
                if r.get("note"):
                    text += "\n" + r["note"]
                msgs.append((text[:200], r["url"], "공고 페이지"))
    nearest = min(upcoming)[1] if upcoming else None
    return msgs, nearest


# ---------------- 요약 페이지 ----------------
def render_digest(history, generated_at, errors=()):
    rows = []
    if errors:
        rows.append("<div class='item'><b>⚠️ 오늘 수집에 문제가 있던 소스</b>"
                    + "".join(f"<div class='note'>{html.escape(e)}</div>" for e in errors) + "</div>")
    for day in history:
        rows.append(f"<h2>{day['date']} · {len(day['items'])}건</h2>")
        if not day["items"]:
            rows.append("<p class='muted'>새 공고 없음</p>")
        for it in day["items"]:
            meta = " · ".join(x for x in [it.get("tag") or CATEGORY_KO.get(it["category"], it["category"]),
                                          it.get("org"), it.get("region"), it["source"]] if x)
            note = f"<div class='note'>{html.escape(it['visa'])}</div>" if it.get("visa") else ""
            star = "★ " if it.get("priority") else ""
            rows.append(f"<div class='item' id='{it['id']}'><a href='{html.escape(it['url'])}' "
                        f"target='_blank' rel='noopener'>{star}{html.escape(it['title'])}</a>"
                        f"<div class='meta'>{html.escape(meta)}</div>{note}</div>")
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>공고 알림 요약</title><style>
:root{{--bg:#fafaf8;--fg:#1d1d1b;--muted:#6b6b66;--card:#fff;--line:#e4e2dc;--accent:#1f5fbf;--warn:#a2520b}}
@media (prefers-color-scheme:dark){{:root{{--bg:#161615;--fg:#ecebe6;--muted:#9a9993;--card:#20201e;--line:#33322f;--accent:#7fb0ff;--warn:#f0a35e}}}}
body{{background:var(--bg);color:var(--fg);font-family:system-ui,-apple-system,"Apple SD Gothic Neo",sans-serif;max-width:760px;margin:0 auto;padding:20px 16px 60px}}
h1{{font-size:1.3rem}} h2{{font-size:1rem;margin-top:28px;border-bottom:1px solid var(--line);padding-bottom:6px}}
.item{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:8px 0}}
.item:target{{outline:2px solid var(--accent)}} a{{color:var(--accent);text-decoration:none;font-weight:600}}
.meta,.muted{{color:var(--muted);font-size:.85rem;margin-top:4px}} .note{{color:var(--warn);font-size:.85rem;margin-top:4px}}
</style></head><body><h1>📬 연구·채용 공고 알림</h1>
<p class="muted">최근 {HISTORY_DAYS}일 · 마지막 갱신 {generated_at}</p>{''.join(rows)}</body></html>"""


# ---------------- 메시지 ----------------
def link_for(item, cfg):
    host = urlparse(item["url"]).hostname or ""
    if any(host == d or host.endswith("." + d) for d in cfg["kakao_registered_domains"]):
        return item["url"]
    return f"{cfg['digest_url']}#{item['id']}"


def build_messages(cfg, new_items, h_msgs, h_status, h_next, errors, today, first_run,
                   d_msgs=(), d_nearest=None):
    digest = cfg["digest_url"]
    msgs = []
    counts = {c: sum(1 for i in new_items if i["category"] == c) for c in CATEGORY_KO}
    h_text = {"open": "🟢 열림", "closed": f"닫힘 (다음 {h_next:%m/%d})"}.get(h_status, "확인 불가")
    if first_run:
        head = f"📬 공고 알림 시작!\n현재 공고 {len(new_items)}건을 기록했어요. 내일부터 새 공고만 알려드릴게요."
    else:
        head = (f"📬 {today:%m/%d} 연구·채용 알림\n새 공고 {len(new_items)}건 "
                f"(학계 {counts['academic']} · 산업체 {counts['industry']} · 국립연구소 {counts['national_lab']})")
    summary = f"{head}\n훔볼트: {h_text}"
    if d_nearest:
        summary += f"\n다음 일정: {d_nearest}"
    if errors:
        shown = ", ".join(e.split(":")[0] for e in errors[:2])
        more = f" 외 {len(errors) - 2}곳" if len(errors) > 2 else ""
        summary += f"\n⚠️ 확인 필요: {shown}{more} (요약 페이지 참고)"
    msgs.append((summary[:200], digest, "요약 페이지"))
    for m in h_msgs:
        msgs.append((m, cfg["humboldt"]["url"], "훔볼트 페이지"))
    msgs.extend(d_msgs)
    if first_run:
        return msgs
    for it in new_items[: cfg["max_item_messages"]]:
        star = "★" if it.get("priority") else ""
        label = it.get("tag") or CATEGORY_KO.get(it["category"], "")
        lines = [f"{star}[{label}] {it['title']}"]
        meta = " · ".join(x for x in [it.get("org"), it.get("region"), it["source"]] if x)
        lines.append(meta)
        if it.get("visa"):
            lines.append(it["visa"])
        msgs.append(("\n".join(lines)[:200], link_for(it, cfg), "공고 보기"))
    rest = len(new_items) - cfg["max_item_messages"]
    if rest > 0:
        msgs.append((f"외 {rest}건은 요약 페이지에서 확인하세요.", digest, "요약 페이지"))
    return msgs


# ---------------- 실행 ----------------
def main(dry_run=False):
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    state = load_state()
    first_run = "seen" not in state
    seen = set(state.get("seen", []))
    today = dt.datetime.now(KST).date()

    collected, errors = [], []
    for src in cfg.get("html_sources", []):
        try:
            got, raw = fetch_html_source(src)
            print(f"[{src['name']}] 링크 {raw}개 → 관련 공고 {len(got)}건")
            if raw == 0:  # 링크를 하나도 못 찾음 = 페이지 구조 변경이나 접속 차단 의심
                errors.append(f"{src['name']} 0건")
            collected += got
        except Exception as e:
            print(f"[{src['name']}] 실패: {e}")
            errors.append(f"{src['name']}: {str(e)[:60]}")
    for src in cfg.get("smartrecruiters_sources", []):
        try:
            got = fetch_smartrecruiters(src)
            print(f"[{src['name']}] {len(got)}건")
            collected += got
        except Exception as e:
            print(f"[{src['name']}] 실패: {e}")
            errors.append(f"{src['name']}: {str(e)[:60]}")
    if cfg.get("adzuna", {}).get("enabled"):
        got, errs = fetch_adzuna(cfg["adzuna"])
        print(f"[Adzuna] {len(got)}건, 오류 {len(errs)}")
        collected += got
        errors += errs

    new_items, ids = [], set()
    for it in collected:
        if it["id"] in seen or it["id"] in ids or is_excluded(it, cfg["exclude_title_keywords"]):
            continue
        ids.add(it["id"])
        it["visa"] = visa_note(it, cfg["visa_red_flags"])
        org = it.get("org", "").lower()
        it["priority"] = (any(re.search(rf"\b{re.escape(c)}\b", org)
                              for c in cfg.get("priority_companies", []))
                          or matches_any(it["title"], cfg.get("priority_title_keywords") or [])
                          and bool(cfg.get("priority_title_keywords")))
        new_items.append(it)
    order = {"industry": 0, "national_lab": 1, "academic": 2}
    new_items.sort(key=lambda i: (not i["priority"], order.get(i["category"], 9)))

    h_msgs, h_err, h_status, h_next = check_humboldt(cfg["humboldt"], state, today)
    if h_err:
        errors.append(h_err)

    d_msgs, d_nearest = check_deadlines(cfg.get("deadline_reminders"), today)
    messages = build_messages(cfg, new_items, h_msgs, h_status, h_next, errors, today, first_run,
                              d_msgs, d_nearest)

    if dry_run:
        print("\n===== 보낼 메시지 (dry-run) =====")
        for text, url, btn in messages:
            print(f"---\n{text}\n[{btn}] {url}")
        return

    # 상태·요약 페이지 저장
    history = [h for h in state.get("history", []) if h["date"] != str(today)]
    slim = [{k: v for k, v in i.items() if k != "text"} for i in new_items]
    history.insert(0, {"date": str(today), "items": [] if first_run else slim})
    history = history[:HISTORY_DAYS]
    state["history"] = history
    state["seen"] = (state.get("seen", []) + sorted(ids))[-5000:]
    save_state(state)
    DIGEST_PATH.parent.mkdir(exist_ok=True)
    DIGEST_PATH.write_text(render_digest(history, dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST"),
                                         errors),
                           encoding="utf-8")

    if new_items or h_msgs or d_msgs or cfg.get("send_when_empty", True) or first_run:
        kakao = KakaoClient(os.environ["KAKAO_REST_KEY"], os.environ["KAKAO_REFRESH_TOKEN"],
                            os.environ.get("KAKAO_CLIENT_SECRET"))
        for text, url, btn in messages:
            kakao.send_text(text, url, btn)
        if kakao.new_refresh_token:
            NEW_TOKEN_PATH.write_text(kakao.new_refresh_token)
            print("새 refresh token 발급됨 → 워크플로가 Secret을 갱신합니다.")
    print(f"완료: 새 공고 {len(new_items)}건, 메시지 {len(messages)}개")


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
