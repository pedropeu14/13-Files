#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
radar.py — rastreia sinais ANTES da defasagem de 45 dias do 13F.

Três camadas, da mais confiável para a mais ruidosa:

1. FILINGS RÁPIDOS (SEC EDGAR, por CIK dos gestores do 13F Search):
   - SC 13D / 13D/A: obrigatório em até 5 DIAS ÚTEIS ao cruzar 5% de uma
     empresa ou mudar materialmente a posição/intenção. É mudança de carteira
     divulgada em dias — o furo legal da defasagem trimestral.
   - SC 13G / 13G/A: participações passivas >5% (prazos mais frouxos).
   - 13F-HR / 13F-HR(A): o trimestral em si, para contexto.
   Para 13D/13G recentes, busca também a EMPRESA-ALVO no header do filing.

2. NOTÍCIAS (Google News RSS, sem chave): últimas manchetes por gestor.
   Ruído jornalístico — sinal fraco, mas às vezes antecipa cartas/posições.

3. CARTAS (letters.json, curadoria manual): links estáveis para as páginas
   de cartas dos gestores que publicam. Sem scraping frágil — quem não tem
   fonte pública estável fica de fora, declaradamente.

Saída: radar.json (lido pela aba Radar do dashboard). Stdlib apenas.
"""

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
SEC_UA = {"User-Agent": os.environ.get("SEC_USER_AGENT",
                                       "Pedro Amorim pedrof.amorim@gmail.com")}
WEB_UA = {"User-Agent": "Mozilla/5.0"}

ATOM_URL = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany"
            "&CIK={cik}&type={ftype}&dateb=&owner=include&count=10&output=atom")
NEWS_URL = ("https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")

# prefix match (covers /A amends). EDGAR renamed schedules in the 2024+
# modernization: old filings are "SC 13D/G", new ones "SCHEDULE 13D/G".
FAST_FORMS = ["SC 13", "SCHEDULE 13", "13F-HR"]
LOOKBACK_DAYS = 400                            # keep the radar recent
MAX_NEWS = 6
NS = {"a": "http://www.w3.org/2005/Atom"}


def fetch(url, headers, timeout=30):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def edgar_filings(cik, name):
    """Recent fast filings for one manager CIK, via the EDGAR Atom feed."""
    out = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    for ftype in FAST_FORMS:
        try:
            xml = fetch(ATOM_URL.format(cik=cik, ftype=urllib.request.quote(ftype)), SEC_UA)
            root = ET.fromstring(xml)
        except Exception as e:
            print(f"  ! EDGAR {name} {ftype}: {e}")
            continue
        for entry in root.findall("a:entry", NS):
            cat = entry.find("a:category", NS)
            form = cat.get("term") if cat is not None else ftype
            date = (entry.findtext("a:updated", "", NS) or "")[:10]
            href = ""
            link = entry.find("a:link", NS)
            if link is not None:
                href = link.get("href", "")
            if not date or date < cutoff:
                continue
            out.append({"form": form, "date": date, "url": href})
        time.sleep(0.25)
    # dedupe (a filing can appear under more than one type query)
    seen, uniq = set(), []
    for f in sorted(out, key=lambda x: x["date"], reverse=True):
        k = (f["form"], f["date"], f["url"])
        if k not in seen:
            seen.add(k)
            uniq.append(f)
    return uniq


def subject_company(filing_url):
    """Target company of a 13D/13G, from the filing header (best effort)."""
    try:
        html = fetch(filing_url, SEC_UA)
        # new-style index pages: companyName">Target Inc. (Subject)
        m = re.search(r'companyName">\s*([^<]+?)\s*\(Subject\)', html)
        if m:
            return m.group(1).strip()
        # legacy header format
        m = re.search(r"SUBJECT COMPANY.*?COMPANY CONFORMED NAME:\s*([^\n<]+)",
                      html, re.S | re.I)
        return m.group(1).strip() if m else None
    except Exception:
        return None


def google_news(query):
    try:
        xml = fetch(NEWS_URL.format(q=urllib.request.quote(query)), WEB_UA)
        root = ET.fromstring(xml)
    except Exception as e:
        print(f"  ! news '{query}': {e}")
        return []
    items = []
    for item in root.iter("item"):
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        pub = item.findtext("pubDate") or ""
        try:
            d = datetime.strptime(pub[:16].strip(), "%a, %d %b %Y").strftime("%Y-%m-%d")
        except ValueError:
            d = ""
        items.append({"title": title.strip(), "url": link.strip(), "date": d})
        if len(items) >= MAX_NEWS:
            break
    return items


def main():
    # managers (slug, name, cik) come from the dashboard's own dataset
    html = open(os.path.join(HERE, "13f_dashboard.html"), encoding="utf-8",
                errors="replace").read()
    start = html.index("{", html.find("const D = "))
    D, _ = json.JSONDecoder().raw_decode(html[start:])
    managers = [(m["slug"], m["manager"], m["cik"]) for m in D["managers"] if m.get("cik")]

    letters = {}
    lpath = os.path.join(HERE, "letters.json")
    if os.path.exists(lpath):
        letters = {k: v for k, v in json.load(open(lpath, encoding="utf-8")).items()
                   if not k.startswith("_")}

    radar = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "lookback_days": LOOKBACK_DAYS, "managers": {}}

    for slug, name, cik in managers:
        short = name.split("(")[0].strip()
        print(f"{short} …")
        filings = edgar_filings(cik, short)
        # target company for the hot ones (13D/G), capped to keep it polite
        for f in [x for x in filings
                  if x["form"].startswith(("SC 13", "SCHEDULE 13"))][:4]:
            tgt = subject_company(f["url"])
            if tgt:
                f["target"] = tgt
            time.sleep(0.25)
        news = google_news(f'"{short}"')
        time.sleep(0.3)
        radar["managers"][slug] = {
            "name": name,
            "filings": filings,
            "news": news,
            "letters": letters.get(slug, []),
        }

    with open(os.path.join(HERE, "radar.json"), "w", encoding="utf-8") as f:
        json.dump(radar, f, ensure_ascii=False)

    nf = sum(len(m["filings"]) for m in radar["managers"].values())
    nn = sum(len(m["news"]) for m in radar["managers"].values())
    nl = sum(len(m["letters"]) for m in radar["managers"].values())
    print(f"\nradar.json: {len(radar['managers'])} gestores · {nf} filings "
          f"(últimos {LOOKBACK_DAYS}d) · {nn} manchetes · {nl} fontes de cartas")
    return 0


if __name__ == "__main__":
    sys.exit(main())
