#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
13F Search — rastreador de carteiras de grandes gestores via SEC EDGAR.

Baixa os 13F-HR dos gestores configurados, calcula as mudanças de carteira
trimestre a trimestre (entradas, saídas, aumentos, reduções) e o consenso
entre gestores (balanço de quantos abriram/fecharam cada papel).

Uso:
  python 13f_search.py fetch     # baixa filings da SEC (precisa de internet)
  python 13f_search.py analyze   # gera analysis.json a partir de data/csv
  python 13f_search.py report    # injeta os dados no dashboard HTML
  python 13f_search.py all       # tudo

Requisitos: Python 3.8+ (somente stdlib). Ajuste USER_AGENT com seu e-mail
(exigência da SEC: https://www.sec.gov/os/accessing-edgar-data).
"""
import json, re, csv, html, os, sys, time, urllib.request, urllib.parse
from collections import defaultdict
from datetime import date

USER_AGENT = os.environ.get(
    "SEC_USER_AGENT", "Pedro Amorim pedrof.amorim@gmail.com (13F research)")
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
N_QUARTERS = 9
RATE_SLEEP = 0.15
INCLUDE_OPTIONS = False  # True para voltar a incluir puts/calls na análise
# Prazo legal do 13F: 45 dias corridos após o fim do trimestre (Q2 -> 14/ago).
# Um trimestre entra na janela alvo no PRÓPRIO dia do prazo. Antes esse valor
# era 46, o que fazia a rodada do dia 14 ignorar o trimestre novo em silêncio.
DEADLINE_DAYS = 45
CIK_CACHE = os.path.join(DATA_DIR, "ciks.json")
RUN_META = os.path.join(DATA_DIR, "meta", "_run.json")

MANAGERS = {
    "berkshire":  ("Berkshire Hathaway (Warren Buffett)",        "0001067983"),
    "duquesne":   ("Duquesne Family Office (Druckenmiller)",     "0001536411"),
    "pershing":   ("Pershing Square (Bill Ackman)",              "0001336528"),
    "baupost":    ("Baupost Group (Seth Klarman)",               "0001061768"),
    "thirdpoint": ("Third Point (Daniel Loeb)",                  "0001040273"),
    "appaloosa":  ("Appaloosa (David Tepper)",                   "0001656456"),
    "tigerglobal":("Tiger Global (Chase Coleman)",               "0001167483"),
    "lonepine":   ("Lone Pine Capital (Stephen Mandel)",         "0001061165"),
    "scion":      ("Scion Asset Management (Michael Burry)",     "0001649339"),
    "icahn":      ("Icahn Capital (Carl Icahn)",                 "0000921669"),
    "valueact":   ("ValueAct Capital (Mason Morfit)",            "0001418814"),
    "trian":      ("Trian Fund Management (Nelson Peltz)",       "0001345471"),
    "tci":        ("TCI Fund Management (Chris Hohn)",           "0001647251"),
    "elliott":    ("Elliott Investment Mgmt (Paul Singer)",      "0001791786"),
    "himalaya":   ("Himalaya Capital (Li Lu)",                   "0001709323"),
    "gates":      ("Gates Foundation Trust",                     "0001166559"),
    "pabrai":     ("Dalal Street (Mohnish Pabrai)",              "0001549575"),
    "aquamarine": ("Aquamarine Zurich (Guy Spier)",              "0001953324"),
    "fairholme":  ("Fairholme Capital (Bruce Berkowitz)",        "0001056831"),
    "altimeter":  ("Altimeter Capital (Brad Gerstner)",          "0001541617"),
    "akre":       ("Akre Capital (Chuck Akre)",                  "0001112520"),
    "starboard":  ("Starboard Value (Jeff Smith)",               "0001517137"),
    "sachem":     ("Sachem Head (Scott Ferguson)",               "0001582090"),
    "abrams":     ("Abrams Capital (David Abrams)",              "0001358706"),
    "peconic":    ("Peconic Partners (Bill Harnisch)",           "0001050464"),
    # Greenlight arquivou 13F-HR até o 3T/4T de 2023 e parou. Como a janela de
    # análise começa depois disso, ela nunca traz posições — fica configurada
    # para o caso de Einhorn voltar a reportar.
    "greenlight": ("Greenlight Capital (David Einhorn)",         "0001079114"),
    "fundsmith":  ("Fundsmith (Terry Smith)",                     "0001569205"),
    "glenview":   ("Glenview Capital (Larry Robbins)",            "0001138995"),
    "corvex":     ("Corvex Management (Keith Meister)",           "0001535472"),
    "egerton":    ("Egerton Capital",                             "0001581811"),
    "ako":        ("AKO Capital",                                 "0001376879"),
    "semper":     ("Semper Augustus (Chris Bloomstran)",          "0001115373"),
    # ATENÇÃO: os dados coletados sob "giverny" são da Giverny Capital Inc.
    # (Montreal, François Rochon) — a única Giverny que arquiva 13F-HR. A
    # Giverny Capital Asset Management LLC de David Poppe (CIK 0002035712)
    # arquiva 13F-NT (notice, sem tabela de posições) e não é rastreável aqui.
    "giverny":    ("Giverny Capital Inc. (François Rochon)",     "0001641864"),
    "punchcard":  ("Punch Card Management (Norbert Lou)",         "0001631664"),
    "atreides":   ("Atreides Management (Gavin Baker)",           "0001777813"),
    "jericho":    ("Jericho Capital (Josh Resnick)",              "0001525234"),
    "longpond":   ("Long Pond Capital (John Khoury)",             "0001499066"),
    "perceptive": ("Perceptive Advisors (Joseph Edelman)",        "0001224962"),
    "soroban":    ("Soroban Capital (Eric Mandelblatt)",          "0001517857"),
    "whalerock":  ("Whale Rock Capital (Alex Sacerdote)",         "0001387322"),
    # Gestores gigantes (centenas de posições): rode localmente para coletar
    "coatue":     ("Coatue Management (Philippe Laffont)",        "0001135730"),
    "viking":     ("Viking Global (Andreas Halvorsen)",           "0001103804"),
    "soros":      ("Soros Fund Management",                       "0001029160"),
    # "bridgewater": ("Bridgewater Associates (Ray Dalio)",      "0001350694"),  # milhares de posições
}
# Fallback: usado só se o CIK acima for None. Todos os 42 gestores já têm CIK
# fixo, então isto hoje não é exercitado — mantido para gestores novos.
# Razões sociais conferidas no EDGAR; nomes genéricos resolvem para a entidade
# errada (ex.: "Giverny Capital" traz a Giverny Capital Inc., não a de Poppe).
SEARCH_NAMES = {
    "fairholme": "Fairholme Capital Management",
    "altimeter": "Altimeter Capital Management",
    "akre": "Akre Capital Management",
    "starboard": "Starboard Value LP",
    "sachem": "Sachem Head Capital Management LP",
    "abrams": "Abrams Capital Management",
    "fundsmith": "Fundsmith LLP",
    "glenview": "Glenview Capital Management",
    "corvex": "Corvex Management",
    "egerton": "Egerton Capital",
    "ako": "AKO Capital",
    "semper": "Semper Augustus",
    "giverny": "Giverny Capital Inc.",
    "punchcard": "Punch Card Management L.P.",
    "atreides": "Atreides Management",
    "jericho": "Jericho Capital Asset Management",
    "perceptive": "Perceptive Advisors",
    "soroban": "Soroban Capital Partners",
    "whalerock": "Whale Rock Capital Management",
}
CSV_FIELDS = ["cusip", "issuer", "class", "put_call", "value_usd", "shares", "sh_type"]

def get(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for i in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                time.sleep(RATE_SLEEP)
                return r.read().decode("utf-8", "replace")
        except Exception:
            if i == retries - 1:
                raise
            time.sleep(2 * (i + 1))

def target_periods(n=N_QUARTERS, today=None):
    today = today or date.today()
    q_end = {3: 31, 6: 30, 9: 30, 12: 31}
    cands = sorted(date(yy, mm, dd) for yy in (today.year, today.year - 1)
                   for mm, dd in q_end.items()
                   if (today - date(yy, mm, dd)).days >= DEADLINE_DAYS)
    out, cur = [], cands[-1]
    for _ in range(n):
        out.append(cur.isoformat())
        y2, m2 = (cur.year - 1, 12) if cur.month == 3 else (cur.year, cur.month - 3)
        cur = date(y2, m2, q_end[m2])
    return sorted(out)

def resolve_cik(name):
    q = urllib.parse.quote(f'"{name}"')
    js = json.loads(get(f"https://efts.sec.gov/LATEST/search-index?q={q}&forms=13F-HR"))
    for h in js.get("hits", {}).get("hits", []):
        return h["_source"]["ciks"][0]
    raise LookupError(f"CIK não encontrado para {name}")

def load_cik_cache():
    """CIKs resolvidos em rodadas anteriores. Evita depender da busca
    full-text do EDGAR a cada execução (lenta e sujeita a mudança)."""
    try:
        return json.load(open(CIK_CACHE, encoding="utf-8"))
    except Exception:
        return {}

def save_cik_cache(cache):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(CIK_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=1, sort_keys=True)

def list_filings(cik, periods):
    best = {}
    try:
        js = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json"))
        r = js["filings"]["recent"]
        rows = zip(r["form"], r["accessionNumber"], r["filingDate"], r["reportDate"])
    except Exception:
        start = periods[0]
        url = (f"https://efts.sec.gov/LATEST/search-index?q=%22a%22&forms=13F-HR"
               f"&ciks={cik}&startdt={start}&enddt={date.today().isoformat()}")
        js = json.loads(get(url))
        rows = [(h["_source"]["file_type"], h["_source"]["adsh"],
                 h["_source"]["file_date"], h["_source"]["period_ending"])
                for h in js["hits"]["hits"] if cik in h["_source"]["ciks"]]
    for form, adsh, fdate, rdate in rows:
        if not str(form).startswith("13F-HR") or rdate not in periods:
            continue
        cur = best.get(rdate)
        if cur is None or fdate > cur[2]:
            best[rdate] = (form, adsh, fdate)
    return best

TAGP = lambda t: re.compile(r"<(?:\w+:)?%s[^>]*>(.*?)</(?:\w+:)?%s>" % (t, t), re.S | re.I)
T_INFO = re.compile(r"<(?:\w+:)?infoTable[^>]*>(.*?)</(?:\w+:)?infoTable>", re.S | re.I)

def fetch_infotable(cik, adsh):
    cik_i, acc = str(int(cik)), adsh.replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_i}/{acc}"
    idx = json.loads(get(f"{base}/index.json"))
    xmls = [i["name"] for i in idx["directory"]["item"]
            if i["name"].lower().endswith(".xml") and "primary_doc" not in i["name"].lower()]
    name = xmls[0] if xmls else "primary_doc.xml"
    return get(f"{base}/{name}")

def parse_infotable(body):
    ps = {k: TAGP(k) for k in ["nameOfIssuer", "titleOfClass", "cusip", "value",
                               "sshPrnamt", "sshPrnamtType", "putCall"]}
    def txt(p, b):
        m = p.search(b)
        return html.unescape(m.group(1).strip()) if m else ""
    rows = []
    for b in T_INFO.findall(body):
        def num(k):
            v = txt(ps[k], b)
            try:
                return int(float(v))
            except ValueError:
                return 0
        rows.append({"cusip": txt(ps["cusip"], b).upper(),
                     "issuer": txt(ps["nameOfIssuer"], b).upper(),
                     "class": txt(ps["titleOfClass"], b).upper(),
                     "put_call": txt(ps["putCall"], b).title(),
                     "value_usd": num("value"), "shares": num("sshPrnamt"),
                     "sh_type": txt(ps["sshPrnamtType"], b).upper()})
    return rows

def cmd_fetch():
    periods = target_periods()
    latest = periods[-1]
    print("Trimestres alvo:", ", ".join(periods))
    print(f"Trimestre mais recente na janela: {latest}")
    os.makedirs(f"{DATA_DIR}/csv", exist_ok=True)
    os.makedirs(f"{DATA_DIR}/meta", exist_ok=True)
    cik_cache = load_cik_cache()
    errors, got_latest, no_latest = [], [], []
    for slug, (label, cik) in MANAGERS.items():
        try:
            if not cik:
                cik = cik_cache.get(slug) or resolve_cik(SEARCH_NAMES[slug])
                if cik_cache.get(slug) != cik:
                    cik_cache[slug] = cik
                    save_cik_cache(cik_cache)
                    print(f"[{slug}] CIK resolvido e cacheado: {cik}")
            filings = list_filings(cik, periods)
            (got_latest if latest in filings else no_latest).append(slug)
            meta = {"slug": slug, "manager": label, "cik": cik, "filings": [],
                    "missing_periods": [p for p in periods if p not in filings]}
            for p in sorted(filings):
                form, adsh, fdate = filings[p]
                out = f"{DATA_DIR}/csv/{slug}__{p}.csv"
                if os.path.exists(out):
                    n = sum(1 for _ in open(out)) - 1
                    meta["filings"].append({"period": p, "form": form, "adsh": adsh,
                                            "file_date": fdate, "n_positions": n,
                                            "status": "CACHED"})
                    continue
                rows = parse_infotable(fetch_infotable(cik, adsh))
                with open(out, "w", newline="", encoding="utf-8") as f:
                    w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
                    w.writeheader(); w.writerows(rows)
                meta["filings"].append({"period": p, "form": form, "adsh": adsh,
                                        "file_date": fdate, "n_positions": len(rows),
                                        "total_value_usd": sum(r["value_usd"] for r in rows),
                                        "status": "OK"})
                print(f"[{slug}] {p}: {len(rows)} posições ({form} {adsh})")
            json.dump(meta, open(f"{DATA_DIR}/meta/{slug}.json", "w"), indent=1)
        except Exception as e:
            errors.append({"slug": slug, "manager": label,
                           "error": f"{type(e).__name__}: {e}"})
            print(f"[{slug}] ERRO: {e}", file=sys.stderr)

    total = len(MANAGERS)
    run = {"fetched_at": date.today().isoformat(), "target_periods": periods,
           "latest_period": latest, "n_managers": total,
           "reported_latest": sorted(got_latest),
           "missing_latest": sorted(no_latest),
           "errors": errors}
    json.dump(run, open(RUN_META, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    print("\n" + "=" * 62)
    print(f"COBERTURA de {latest}: {len(got_latest)}/{total} gestores arquivaram")
    if no_latest:
        print(f"  sem filing do trimestre ({len(no_latest)}): "
              + ", ".join(no_latest))
    if errors:
        print(f"  FALHAS ({len(errors)}):", file=sys.stderr)
        for e in errors:
            print(f"    {e['slug']}: {e['error']}", file=sys.stderr)
    print("=" * 62)
    # Sinaliza para o CI: nada novo do trimestre = não vale republicar.
    if not got_latest:
        print(f"AVISO: nenhum gestor arquivou {latest} ainda.", file=sys.stderr)
    return len(got_latest), errors

def load_holdings():
    hold = defaultdict(dict)
    import glob
    for f in sorted(glob.glob(f"{DATA_DIR}/csv/*__*.csv")):
        slug, period = os.path.basename(f)[:-4].split("__")
        agg = {}
        for r in csv.DictReader(open(f, encoding="utf-8")):
            if r["put_call"] and not INCLUDE_OPTIONS:
                continue  # exclui opções (puts/calls)
            key = (r["cusip"], r["put_call"])
            a = agg.setdefault(key, {"cusip": r["cusip"], "issuer": r["issuer"],
                                     "class": r["class"], "put_call": r["put_call"],
                                     "sh_type": r.get("sh_type", "SH"),
                                     "value": 0, "shares": 0})
            a["value"] += int(r["value_usd"] or 0)
            a["shares"] += int(r["shares"] or 0)
        total = sum(a["value"] for a in agg.values())
        if 0 < total < 50_000_000:
            for a in agg.values():
                a["value"] *= 1000
        hold[slug][period] = agg
    return hold

def diff_quarters(prev, cur):
    out = {"new": [], "exited": [], "increased": [], "decreased": [], "unchanged": []}
    for k, p in cur.items():
        if k not in prev:
            out["new"].append({**p, "shares_delta": p["shares"], "pct": None})
        else:
            d = p["shares"] - prev[k]["shares"]
            pct = (d / prev[k]["shares"] * 100) if prev[k]["shares"] else None
            rec = {**p, "shares_delta": d,
                   "pct": round(pct, 1) if pct is not None else None,
                   "value_prev": prev[k]["value"]}
            if pct is not None and pct > 1:
                out["increased"].append(rec)
            elif pct is not None and pct < -1:
                out["decreased"].append(rec)
            else:
                out["unchanged"].append(rec)
    for k, p in prev.items():
        if k not in cur:
            out["exited"].append({**p, "shares_delta": -p["shares"], "pct": -100.0})
    return out

def est_performance(hold):
    """Retorno trimestral estimado: variação de preço (valor/ações) das posições
    LONG em ações mantidas entre trimestres, ponderada pelo valor no início do
    trimestre. Ajusta splits óbvios. NÃO é a cota oficial do fundo."""
    perf = {}
    for slug in sorted(hold):
        per, series = sorted(hold[slug]), []
        for a, b in zip(per, per[1:]):
            A, B = hold[slug][a], hold[slug][b]
            tot, acc = 0, 0.0
            for k, pa in A.items():
                if k[1] or pa.get("sh_type", "SH") != "SH":
                    continue
                pb = B.get(k)
                if not pb or pa["shares"] <= 0 or pb["shares"] <= 0 or pa["value"] <= 0:
                    continue
                p0, p1 = pa["value"] / pa["shares"], pb["value"] / pb["shares"]
                r = p1 / p0 - 1
                sr = pb["shares"] / pa["shares"]
                for kk in (2, 3, 4, 5, 10, 20):
                    if abs(sr - kk) < .05 * kk and r < -0.3:
                        r = p1 * kk / p0 - 1
                    elif abs(sr - 1 / kk) < .05 / kk and r > 0.5:
                        r = p1 / kk / p0 - 1
                if abs(r) > 3:
                    continue
                acc += pa["value"] * r; tot += pa["value"]
            totA = sum(p["value"] for p in A.values())
            series.append({"from": a, "to": b,
                           "ret": round(acc / tot, 4) if tot else None,
                           "coverage": round(tot / totA, 3) if totA else 0})
        perf[slug] = series
    return perf


def stock_returns_calc(hold):
    """Retorno trimestral por papel (mediana entre gestores da variação de
    preço = valor/ações), com ajuste de splits. Retorna (rets, nomes)."""
    from statistics import median
    per_all = sorted({p for m in hold.values() for p in m})
    rets, names = defaultdict(dict), {}
    for a, b in zip(per_all, per_all[1:]):
        tr = f"{a}__{b}"
        samples = defaultdict(list)
        for slug in hold:
            A, B = hold[slug].get(a, {}), hold[slug].get(b, {})
            for k, pa in A.items():
                if k[1] or pa.get("sh_type", "SH") != "SH":
                    continue
                pb = B.get(k)
                if not pb or pa["shares"] <= 0 or pb["shares"] <= 0 or pa["value"] <= 0:
                    continue
                p0, p1 = pa["value"] / pa["shares"], pb["value"] / pb["shares"]
                r = p1 / p0 - 1
                sr = pb["shares"] / pa["shares"]
                for kk in (2, 3, 4, 5, 10, 20):
                    if abs(sr - kk) < .05 * kk and r < -0.3:
                        r = p1 * kk / p0 - 1
                    elif abs(sr - 1 / kk) < .05 / kk and r > 0.5:
                        r = p1 / kk / p0 - 1
                if abs(r) > 3:
                    continue
                samples[k[0]].append(r)
                names[k[0]] = pa["issuer"]
        for c, rs in samples.items():
            rets[c][tr] = round(median(rs), 4)
    return rets, names

def signal_stats_calc(consensus, stock_rets):
    """Relação entre balanço de gestores (net_interest) num trimestre e o
    retorno do papel no mesmo trimestre e no seguinte."""
    trs = sorted(consensus)
    nxt = {t: trs[i + 1] for i, t in enumerate(trs[:-1])}
    obs = []
    for tr in trs:
        for row in consensus[tr]:
            if row["put_call"]:
                continue
            same = stock_rets.get(row["cusip"], {}).get(tr)
            fwd = stock_rets.get(row["cusip"], {}).get(nxt.get(tr, ""))
            obs.append((row["net_interest"], same, fwd))
    def bucket(n):
        return "-2 ou menos" if n <= -2 else ("-1" if n == -1 else
               ("+1" if n == 1 else ("+2 ou mais" if n >= 2 else "0")))
    buckets = {}
    for n, same, fwd in obs:
        d = buckets.setdefault(bucket(n), {"n": 0, "same": [], "fwd": []})
        d["n"] += 1
        if same is not None: d["same"].append(same)
        if fwd is not None: d["fwd"].append(fwd)
    order = ["-2 ou menos", "-1", "0", "+1", "+2 ou mais"]
    blist = [{"label": k, "n": buckets[k]["n"],
              "same": round(sum(buckets[k]["same"]) / len(buckets[k]["same"]), 4) if buckets[k]["same"] else None,
              "fwd": round(sum(buckets[k]["fwd"]) / len(buckets[k]["fwd"]), 4) if buckets[k]["fwd"] else None,
              "n_fwd": len(buckets[k]["fwd"])}
             for k in order if k in buckets]
    def pearson(pairs):
        pairs = [(x, y) for x, y in pairs if y is not None]
        n = len(pairs)
        if n < 3: return None
        mx = sum(x for x, _ in pairs) / n; my = sum(y for _, y in pairs) / n
        sx = sum((x - mx) ** 2 for x, _ in pairs) ** .5
        sy = sum((y - my) ** 2 for _, y in pairs) ** .5
        if not sx or not sy: return None
        return round(sum((x - mx) * (y - my) for x, y in pairs) / (sx * sy), 3)
    return {"buckets": blist, "n_obs": len(obs),
            "corr_same": pearson([(n, s) for n, s, _ in obs]),
            "corr_fwd": pearson([(n, f) for n, _, f in obs])}

def cmd_analyze():
    hold = load_holdings()
    periods = sorted({p for m in hold.values() for p in m})
    names = {}
    import glob
    for f in glob.glob(f"{DATA_DIR}/meta/*.json"):
        if os.path.basename(f).startswith("_"):
            continue
        try:
            m = json.load(open(f, encoding="utf-8"))
            if "slug" in m:
                names[m["slug"]] = m
        except Exception:
            pass

    managers, changes = [], {}
    cons = defaultdict(lambda: defaultdict(
        lambda: {"opened": [], "closed": [], "increased": [], "decreased": [],
                 "value_open": 0, "value_close": 0}))
    issuer_name = {}
    for slug in sorted(hold):
        per = sorted(hold[slug])
        label = MANAGERS.get(slug, (names.get(slug, {}).get("manager", slug), None))[0]
        latest = per[-1]
        managers.append({"slug": slug, "manager": label,
                         "cik": names.get(slug, {}).get("cik", MANAGERS.get(slug, ("", ""))[1]),
                         "periods": per,
                         "latest": {"period": latest, "n": len(hold[slug][latest]),
                                    "total": sum(p["value"] for p in hold[slug][latest].values())}})
        changes[slug] = []
        for a, b in zip(per, per[1:]):
            d = diff_quarters(hold[slug][a], hold[slug][b])
            changes[slug].append({"from": a, "to": b,
                                  **{k: sorted(v, key=lambda x: -abs(x["value"]))
                                     for k, v in d.items() if k != "unchanged"},
                                  "n_unchanged": len(d["unchanged"])})
            tr = f"{a}__{b}"
            for p in d["new"]:
                k = (p["cusip"], p["put_call"]); issuer_name[k] = p["issuer"]
                cons[tr][k]["opened"].append(slug); cons[tr][k]["value_open"] += p["value"]
            for p in d["exited"]:
                k = (p["cusip"], p["put_call"]); issuer_name[k] = p["issuer"]
                cons[tr][k]["closed"].append(slug); cons[tr][k]["value_close"] += p["value"]
            for p in d["increased"]:
                k = (p["cusip"], p["put_call"]); issuer_name[k] = p["issuer"]
                cons[tr][k]["increased"].append(slug)
            for p in d["decreased"]:
                k = (p["cusip"], p["put_call"]); issuer_name[k] = p["issuer"]
                cons[tr][k]["decreased"].append(slug)

    consensus = {}
    for tr, m in cons.items():
        rows = []
        for k, v in m.items():
            rows.append({"cusip": k[0], "put_call": k[1], "issuer": issuer_name[k],
                         "opened": v["opened"], "closed": v["closed"],
                         "increased": v["increased"], "decreased": v["decreased"],
                         "net_open": len(v["opened"]) - len(v["closed"]),
                         "net_interest": len(v["opened"]) + len(v["increased"])
                                       - len(v["closed"]) - len(v["decreased"]),
                         "value_open": v["value_open"], "value_close": v["value_close"]})
        rows.sort(key=lambda r: (-r["net_interest"], -r["value_open"]))
        consensus[tr] = rows

    holdings_out = {s: {p: [[v["cusip"], v["issuer"], v["class"], v["put_call"],
                             v["value"], v["shares"]]
                            for v in sorted(hold[s][p].values(), key=lambda x: -x["value"])]
                        for p in hold[s]} for s in hold}

    try:
        run = json.load(open(RUN_META, encoding="utf-8"))
    except Exception:
        run = {}
    # Cobertura recalculada a partir do que realmente entrou na análise —
    # é isso que o dashboard mostra, não a intenção da coleta.
    if periods:
        holders_latest = sorted(s for s in hold if periods[-1] in hold[s])
        run["coverage"] = {"period": periods[-1],
                           "with_data": len(holders_latest),
                           "n_managers": len(hold),
                           "missing": sorted(set(hold) - set(holders_latest))}

    out = {"generated": date.today().isoformat(), "periods": periods,
           "run": run,
           "managers": managers, "changes": changes, "consensus": consensus,
           "holdings": holdings_out, "performance": est_performance(hold),
           "stock_returns": {c: t for c, t in stock_returns_calc(hold)[0].items()},
           "signal_stats": signal_stats_calc(consensus, stock_returns_calc(hold)[0]),
           "notes": ["Valores em USD conforme reportado; filings com soma < US$50 mi "
                     "foram tratados como 'milhares' e multiplicados por 1000.",
                     "Opções (puts/calls) EXCLUÍDAS da análise (INCLUDE_OPTIONS=False no script).",
                     "Fonte: SEC EDGAR, formulários 13F-HR/13F-HR(A)."]}
    with open(f"{DATA_DIR}/analysis.json", "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    print(f"analysis.json gerado: {len(managers)} gestores, {len(periods)} trimestres, "
          f"{sum(len(c) for c in changes.values())} transições")
    cov = run.get("coverage")
    if cov:
        print(f"  cobertura de {cov['period']}: "
              f"{cov['with_data']}/{cov['n_managers']} gestores com dados")

def cmd_report():
    here = os.path.dirname(os.path.abspath(__file__))
    tpl = open(f"{here}/dashboard_template.html", encoding="utf-8").read()
    data = open(f"{DATA_DIR}/analysis.json", encoding="utf-8").read()
    out = tpl.replace("__DATA__", data)
    with open(f"{here}/13f_dashboard.html", "w", encoding="utf-8") as f:
        f.write(out)
    print(f"13f_dashboard.html gerado ({len(out)//1024} KB)")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd in ("fetch", "all"):
        cmd_fetch()
    if cmd in ("analyze", "all"):
        cmd_analyze()
    if cmd in ("report", "all"):
        cmd_report()
