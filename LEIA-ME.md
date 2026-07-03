# 13F Search

Rastreador de carteiras de grandes gestores via SEC EDGAR: baixa os formulários
13F-HR, compara as carteiras trimestre a trimestre e cruza os movimentos entre
gestores (balanço de que papel entrou e saiu).

## Arquivos

| Arquivo | O que é |
|---|---|
| `13f_search.py` | O programa (só Python 3, sem dependências). Comandos: `fetch`, `analyze`, `report`, `all`. |
| `dashboard_template.html` | Template do dashboard (o script injeta os dados nele). |
| `13f_dashboard.html` | Dashboard interativo pronto — abra no navegador. 4 abas: Consenso, Movimentos por gestor, Carteiras, Rastrear papel. |
| `13F_analise.xlsx` | Planilha com 6 abas: Resumo, Consenso, Entradas e Saídas, Aumentos e Reduções, Carteiras, Notas. |
| `make_excel.py` | Gera a planilha a partir de `data/analysis.json` (requer `pip install openpyxl`). |
| `data/csv/` | Carteiras normalizadas (1 CSV por gestor/trimestre). |
| `data/meta/` | Metadados dos filings (accession, datas, nº posições). |
| `data/analysis.json` | Resultado da análise (mudanças + consenso + carteiras). |

## Como rodar (na sua máquina ou no Claude da empresa)

```bash
python 13f_search.py all        # baixa da SEC + analisa + gera dashboard
python make_excel.py            # regenera o Excel (opcional)
```

Basta copiar esta pasta. Em outro Claude (Claude Code, Cowork, etc.), diga:
"rode o 13f_search.py e me explique os resultados" — ou peça alterações.
Edite `USER_AGENT` no topo do script com seu e-mail (exigência da SEC).

## Como adicionar/remover gestores

Edite o dicionário `MANAGERS` no `13f_search.py`. Com o CIK
(busque em https://www.sec.gov/cgi-bin/browse-edgar) ou com `None` + nome em
`SEARCH_NAMES` para resolução automática. Gestores gigantes (Bridgewater,
Coatue, Viking, Soros) já estão no arquivo, comentados — rodando localmente o
script baixa qualquer tamanho de carteira.

## Estado atual dos dados (gerados em 2026-07-02)

- 18 gestores, trimestres 2024-06-30 a 2026-03-31 (8 trimestres).
- Coletados: Berkshire, Duquesne, Pershing Square, Baupost, Third Point,
  Appaloosa, Tiger Global, Lone Pine, Scion, Icahn, ValueAct, Trian, TCI,
  Elliott, Himalaya, Gates Foundation, Pabrai (Dalal Street), Aquamarine.
- Pendentes (limite de sessão durante a coleta): Fairholme, Altimeter, Akre,
  Starboard, Sachem Head, Abrams — já configurados no script; um
  `python 13f_search.py all` completa tudo.
- Duquesne não arquivou o 13F de 2026-03-31 até a geração; Scion (Burry) parou
  de reportar após 2025-09-30; Greenlight (Einhorn) sem 13F desde 2023.

## Limitações do 13F

Somente posições **long** em papéis listados nos EUA (ações, ADRs, opções);
não mostra shorts, bonds nem posições fora dos EUA. Publicado até 45 dias após
o fim do trimestre — as posições podem já ter mudado. Filings com valores em
milhares de USD (alguns filers antigos) são normalizados automaticamente.
Não é recomendação de investimento.
