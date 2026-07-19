import json, os, smtplib, ssl, sys
from datetime import datetime, timezone
from email.mime.text import MIMEText
import yfinance as yf

LOOKBACK = 500
BEAR = -50.0
ACCUM = -30.0
PEAK = -15.0

def load_tickers():
    rows = []
    for line in open("tickers.txt", encoding="utf-8"):
        line = line.split("#")[0].strip()
        if not line:
            continue
        p = [x.strip() for x in line.split("|")]
        rows.append((p[0], p[1] if len(p) > 1 else p[0]))
    return rows

def phase_of(dd):
    if dd <= BEAR: return 3
    if dd <= ACCUM: return 0
    if dd >= PEAK: return 2
    return 1

def analyze(symbols):
    raw = yf.download([s for s, _ in symbols], period="5y", interval="1d",
                      auto_adjust=True, progress=False, group_by="ticker")
    out = []
    for sym, name in symbols:
        try:
            close = (raw["Close"] if len(symbols) == 1 else raw[sym]["Close"]).dropna()
            if len(close) < 30:
                raise ValueError("мало данных")
            w = close.tail(LOOKBACK)
            ath = float(w.max()); price = float(w.iloc[-1])
            dd = (price - ath) / ath * 100
            out.append({"sym": sym, "name": name, "price": price,
                        "ath": ath, "dd": dd, "phase": phase_of(dd), "err": None})
        except Exception as e:
            out.append({"sym": sym, "name": name, "err": str(e),
                        "dd": None, "phase": None})
    return out

def main():
    syms = load_tickers()
    res = analyze(syms)

    for r in sorted([x for x in res if x["phase"] is not None], key=lambda x: x["dd"]):
        print(f"{r['sym']:<12} {r['dd']:>7.1f}%  phase {r['phase']}")

    try:
        prev = json.load(open("state.json"))
    except Exception:
        prev = {}

    red = [r for r in res if r["phase"] == 3]
    new_red = [r for r in red if prev.get(r["sym"]) != 3]
    left = [r for r in res if r["phase"] not in (None, 3) and prev.get(r["sym"]) == 3]

    json.dump({r["sym"]: r["phase"] for r in res if r["phase"] is not None},
              open("state.json", "w"), indent=2)

    if not red and not left:
        print("Красной зоны нет.")
        return

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    subj = (f"НОВОЕ в красной зоне ({len(new_red)}) — {today}" if new_red
            else f"В красной зоне: {len(red)} — {today}" if red
            else f"Выход из красной зоны — {today}")

    L = []
    if new_red:
        L.append("ТОЛЬКО ЧТО ВОШЛИ В КРАСНУЮ ЗОНУ:")
        for r in new_red:
            L.append(f"  {r['name']} ({r['sym']}): {r['dd']:.1f}%  цена {r['price']:.2f}  ATH {r['ath']:.2f}")
        L.append("")
    if red:
        L.append(f"ВСЕГО В КРАСНОЙ ЗОНЕ (просадка <= {BEAR:.0f}%):")
        for r in sorted(red, key=lambda x: x["dd"]):
            mark = "  NEW" if prev.get(r["sym"]) != 3 else ""
            L.append(f"  {r['name']} ({r['sym']}): {r['dd']:.1f}%{mark}")
        L.append("")
    if left:
        L.append("ВЫШЛИ ИЗ КРАСНОЙ ЗОНЫ:")
        for r in left:
            L.append(f"  {r['name']} ({r['sym']}): {r['dd']:.1f}%")
        L.append("")
    L.append(f"Окно ATH: {LOOKBACK} дней. Это расчёт просадки, не рекомендация.")
    body = "\n".join(L)

    print(subj); print(body)

    user = os.environ["SMTP_USER"]
    pwd = os.environ["SMTP_PASS"]
    to = os.getenv("MAIL_TO", user)
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subj
    msg["From"] = user
    msg["To"] = to
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context()) as s:
        s.login(user, pwd)
        s.sendmail(user, [x.strip() for x in to.split(",")], msg.as_string())
    print("Письмо отправлено")

main()
