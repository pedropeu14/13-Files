# 13F Search

Rastreador de carteiras de grandes gestores via SEC EDGAR: baixa os formulários
13F-HR, compara as carteiras trimestre a trimestre e cruza os movimentos entre
gestores (quem entrou, saiu, aumentou e reduziu cada papel).

Site: https://pedropeu14.github.io/13-Files/13f_dashboard.html

## Arquivos

| Arquivo | O que é |
|---|---|
| `13f_search.py` | O programa (só Python 3, sem dependências). Comandos: `fetch`, `analyze`, `report`, `all`. |
| `radar.py` | Radar de 13D/G, notícias e cartas — movimentos que aparecem ANTES dos 45 dias do 13F. Gera `radar.json`. |
| `dashboard_template.html` | Template do dashboard (o script injeta os dados no lugar de `__DATA__`). |
| `13f_dashboard.html` | Dashboard pronto — **arquivo gerado, não edite à mão**. 7 abas. |
| `13F_analise.xlsx` | Planilha com 6 abas: Resumo, Consenso, Entradas e Saídas, Aumentos e Reduções, Carteiras, Notas. |
| `make_excel.py` | Gera a planilha a partir de `data/analysis.json` (requer `pip install openpyxl`). |
| `data/csv/` | Carteiras normalizadas (1 CSV por gestor/trimestre). Serve de cache: o `fetch` pula o que já existe. |
| `data/meta/` | Metadados dos filings (accession, datas, nº posições) + `_run.json` com a cobertura da última rodada. |
| `data/ciks.json` | Cache dos CIKs resolvidos por busca, para não depender do full-text search do EDGAR toda vez. |
| `data/analysis.json` | Resultado da análise (mudanças + consenso + carteiras + cobertura). |

## Atualização automática

Dois workflows do GitHub Actions, ambos com `workflow_dispatch` (dá para rodar
na mão pela aba Actions):

| Workflow | Quando roda | O que atualiza |
|---|---|---|
| `.github/workflows/13f.yml` | **dia 14 às 21:00 UTC** e **dia 15 às 13:00 UTC** de fev/mai/ago/nov | carteiras, `13f_dashboard.html`, `13F_analise.xlsx` e o cache em `data/` |
| `.github/workflows/radar.yml` | 2× por dia útil | `radar.json` (13D/G, notícias, cartas) |

Os dois horários existem porque o prazo legal do 13F é de **45 dias corridos**
após o fim do trimestre (14/fev, 15/mai, 14/ago, 14/nov) e a maioria dos grandes
gestores arquiva no próprio dia, ao longo do dia útil de Nova York. A rodada do
dia 14 é às 17h em NY, depois do fechamento; a do dia 15 é às 9h em NY, para
pegar quem entregou tarde da noite. Fora desses dois dias o workflow não roda —
use **Run workflow** na aba Actions quando precisar (por exemplo, para pegar
emendas `13F-HR/A` semanas depois).

Defina o secret `SEC_USER_AGENT` (formato `Nome Sobrenome email@dominio.com`) em
Settings → Secrets → Actions. A SEC exige User-Agent identificável.

Cada rodada escreve um resumo na aba Actions com quantos gestores arquivaram o
trimestre e quais falharam.

## Como rodar na mão

```bash
python 13f_search.py all        # baixa da SEC + analisa + gera o dashboard
python make_excel.py            # regenera o Excel (opcional)
```

O `fetch` usa `data/csv/` como cache — apagar um CSV força o redownload daquele
gestor/trimestre. `SEC_USER_AGENT` no ambiente sobrescreve o `USER_AGENT` do
script.

## Como adicionar/remover gestores

Edite o dicionário `MANAGERS` no `13f_search.py`. Com o CIK (busque em
https://www.sec.gov/cgi-bin/browse-edgar) ou com `None` + o nome em
`SEARCH_NAMES` para resolução automática — nesse caso o CIK resolvido é gravado
em `data/ciks.json` e reaproveitado nas rodadas seguintes.

Todos os 42 gestores configurados hoje têm CIK fixo. Se for adicionar por nome,
use a **razão social exata** do EDGAR: nome genérico resolve para a entidade
errada silenciosamente. Confira também se a casa arquiva **13F-HR** e não
**13F-NT** — o segundo é apenas um aviso de que as posições são reportadas por
outro gestor, e não tem tabela de carteira para extrair.

Bridgewater segue comentado no arquivo (milhares de posições por filing).

## Estado atual dos dados (coleta de 2026-08-07)

- **41 gestores** com dados, 8 trimestres de 2024-06-30 a **2026-03-31**.
- Cobertura do 1T26: 40/41. Só Scion (Burry) falta — parou de reportar após
  2025-09-30.
- **43 gestores configurados** no `MANAGERS`.
- **Peconic Partners (Bill Harnisch)**, CIK `0001050464`, entra na próxima
  rodada — arquiva 13F-HR todo trimestre, então cobre a janela inteira.
- **Greenlight (David Einhorn)** aponta para a **DME Capital Management, LP**
  (CIK `0001489933`), que é quem arquiva o 13F-HR do grupo desde 2023. A
  Greenlight Capital Inc (CIK `0001079114`) parou de reportar posições naquele
  ano e hoje só arquiva notices; a DME Advisors, LP (CIK `0001300763`) arquiva
  apenas 13F-NT. Usar o CIK da Greenlight Capital Inc devolve zero posições —
  foi o que aconteceu até 23/08/2026.
- `giverny` = **Giverny Capital Inc. (François Rochon, Montreal)**, a única
  Giverny que arquiva 13F-HR. A Giverny Capital Asset Management de David Poppe
  arquiva 13F-NT e não tem carteira para extrair.
- `N_QUARTERS = 9`: a partir da próxima coleta a janela guarda 9 trimestres, para
  o trimestre novo não empurrar o mais antigo para fora.

## Entendendo a aba Consenso

As colunas medem coisas diferentes e são fáceis de confundir:

- **Detentores** — quantos gestores tinham o papel ao **fim** do trimestre,
  incluindo quem não mexeu em nada.
- **Abriram** — quem não tinha e passou a ter. **São os novos entrantes.**
- **Interesse líq.** — `(abriram + aumentaram) − (fecharam + reduziram)`.
  Um número alto aqui pode ser apenas reforço de quem já era detentor, **sem
  nenhum entrante novo**. Para ver entrantes, olhe a coluna Abriram.

Exemplo real (1T26, Uber): Detentores 6, Abriram nenhum, Aumentaram 4,
Interesse líquido +4 — quatro gestores ampliaram posição, zero entraram.

## Limitações do 13F

Somente posições **long** em papéis listados nos EUA (ações, ADRs, opções); não
mostra shorts, bonds nem posições fora dos EUA. Publicado até 45 dias após o fim
do trimestre — as posições podem já ter mudado. Pedidos de tratamento
confidencial podem atrasar a divulgação de posições específicas por meses.
Filings com valores em milhares de USD são normalizados automaticamente.
Opções (puts/calls) estão **excluídas** da análise (`INCLUDE_OPTIONS = False`).

Não é recomendação de investimento.
