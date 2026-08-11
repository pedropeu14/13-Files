# Pacote de atualização — 13F Search

Preparado em 2026-08-11, antes do prazo do 2T26 (**sexta, 14/08/2026**).

**Base:** commit `c60c14f` (radar refresh 2026-08-10) — ou seja, já inclui a sua
coleta de 07/08 que versionou o `data/` e trouxe Coatue, Viking e Soros. O
`13f_dashboard.html` do pacote foi **regerado a partir desse cache**, então
mantém os **41 gestores** e não volta atrás em nada. `13f_search.py` e
`dashboard_template.html` não tinham mudado no remoto, então as edições entraram
limpas.

## Como aplicar

Copie os arquivos por cima dos atuais no repositório e faça commit. `data/` não
vem no pacote de propósito — o cache é construído na primeira rodada real.

```bash
git add -A && git commit -m "13f: prontidao para o ciclo 2T26 + colunas mais claras"
git push
```

Depois, em **Settings → Secrets and variables → Actions**, crie o secret
`SEC_USER_AGENT` com `Nome Sobrenome email@dominio.com`. Sem isso o workflow
cai no e-mail que já estava no script.

Para testar antes do dia 14, rode o workflow **Atualizar 13F** na mão pela aba
Actions (`workflow_dispatch`). Ele vai coletar até o 1T26 e reconstruir o
dashboard — deve terminar com cobertura 36/38.

## O que mudou

### 1. A rodada do dia 14 agora enxerga o trimestre novo

`13f_search.py` exigia **46 dias** desde o fim do trimestre para incluí-lo. O
prazo legal é 45. Rodar em 14/08 devolvia silenciosamente a janela terminando no
1T26, sem erro nenhum.

| Rodando em | Antes | Depois |
|---|---|---|
| 13/08/2026 | 2026-03-31 | 2026-03-31 |
| **14/08/2026** | **2026-03-31** | **2026-06-30** |
| 15/08/2026 | 2026-06-30 | 2026-06-30 |

Agora é `DEADLINE_DAYS = 45`, constante nomeada e comentada.

### 2. Histórico não encolhe mais

`N_QUARTERS` de 8 para 9. Com 8, a entrada do 2T26 empurraria o 2T24 para fora
da análise. Com 9 a janela vai de 2024-06-30 a 2026-06-30.

### 3. Automação do 13F (não existia)

Novo `.github/workflows/13f.yml`. O único workflow do repo era o `radar.yml`,
que só atualiza `radar.json` — as carteiras nunca se atualizariam sozinhas.

- diariamente do dia 14 ao 28 de fev/mai/ago/nov (janela pós-prazo);
- toda segunda-feira fora da janela, para emendas `13F-HR/A` e atrasados;
- commita `13f_dashboard.html` e o cache `data/`, o que republica o Pages;
- escreve na aba Actions um resumo com a cobertura e as falhas da rodada.

### 4. Falhas deixaram de ser silenciosas

O `cmd_fetch` engolia exceção por gestor e seguia em frente — dava para publicar
um dashboard faltando metade dos gestores sem nenhum aviso. Agora ele acumula os
erros, grava `data/meta/_run.json` e imprime no fim:

```
==============================================================
COBERTURA de 2026-06-30: 31/42 gestores arquivaram
  sem filing do trimestre (11): scion, duquesne, ...
==============================================================
```

Essa informação vai para o `analysis.json` e vira uma **faixa no topo do
dashboard**, que fica vermelha quando a cobertura passa de 80% para baixo ou
quando algum gestor falhou. É a proteção contra republicar um dia 14 pela metade.

### 5. Colunas renomeadas (a confusão da Uber)

`Gestores` → **Detentores** e `Balanço` → **Interesse líq.**, com tooltip em cada
cabeçalho e uma legenda acima da tabela. A aba passou de "Consenso (balanço)"
para "Consenso"; o mesmo nome foi ajustado na aba Consenso × preço.

O caso concreto: no 1T26 a Uber aparecia com Detentores **6** e Balanço **+4**
lado a lado, e nenhum novo entrante — os +4 eram Altimeter, Appaloosa, Egerton e
Glenview *aumentando* posição. Os dois números vagos, colados, davam a leitura de
"6 gestores entraram".

### 6. CIKs fixados — todos os 42

19 gestores tinham CIK `None` e eram resolvidos a cada rodada pela busca
full-text do EDGAR — lento e frágil. Agora **nenhum** depende disso.

14 vieram dos dados já publicados: Fairholme, Altimeter, Akre, Abrams, Glenview,
Corvex, Egerton, AKO, Semper Augustus, Atreides, Jericho, Perceptive, Soroban,
Whale Rock.

Os 5 que faltavam foram confirmados um a um no EDGAR:

| Gestor | CIK | Razão social conferida | Sede |
|---|---|---|---|
| Starboard Value | `0001517137` | Starboard Value LP | New York, NY |
| Sachem Head | `0001582090` | Sachem Head Capital Management LP | New York, NY |
| Fundsmith | `0001569205` | Fundsmith LLP | Londres, Reino Unido |
| Punch Card | `0001631664` | Punch Card Management L.P. | Winter Park, FL |
| Giverny | `0001641864` | Giverny Capital Inc. | Montreal, Canadá |

O `data/ciks.json` continua existindo como cache para gestores novos.

### 6b. Giverny estava com o gestor errado no rótulo

Ao confirmar o CIK apareceu um problema que não tinha a ver com prontidão. O
`MANAGERS` rotulava `giverny` como **"Giverny Capital (David Poppe)"**, mas os
dados coletados são de outra casa:

- **Giverny Capital Inc.** — Montreal, **François Rochon**, CIK `0001641864`.
  É a única Giverny que arquiva **13F-HR** (com tabela de posições). São esses
  os 51 papéis / US$ 2,73 bi que estão no site.
- **Giverny Capital Asset Management, LLC** — New York, **David Poppe**, CIK
  `0002035712`. Arquiva **13F-NT** (notice, sem tabela de posições), então não
  tem carteira para extrair. Não é rastreável por 13F.

A resolução automática buscava só `"Giverny Capital"`, que traz a entidade do
Rochon. O rótulo foi corrigido para **"Giverny Capital Inc. (François Rochon)"** —
os números sempre foram dele. Se você queria acompanhar o Poppe, não dá por 13F;
confirme se quer manter o Rochon ou remover o gestor.

Os nomes em `SEARCH_NAMES` também foram trocados pelas razões sociais exatas, para
que uma resolução futura não caia na entidade errada.

### 7. `SEC_USER_AGENT` por variável de ambiente

O `USER_AGENT` era fixo no código. Agora lê de `SEC_USER_AGENT` e usa o valor
antigo como padrão.

### 8. README e LEIA-ME corrigidos

Diziam "4 abas" (são 7) e "18 gestores" (são 38), e listavam como pendentes seis
gestores que já estavam no site com histórico completo. Reescritos com o estado
real, a documentação da automação e a explicação das colunas do Consenso.

## O que foi testado

- `target_periods` com datas simuladas em torno de 14/08, 14/11 e 14/02.
- Pipeline `analyze` + `report` rodado de ponta a ponta com os dados reais
  reconstruídos: 38 gestores, 8 trimestres, 263 transições, cobertura 36/38.
- Dashboard gerado aberto no Chromium: **zero erro de JavaScript**, as 7 abas
  renderizam, e a faixa de cobertura muda para vermelho no cenário degradado.
- Ambos os workflows validados como YAML, e o passo de resumo do `13f.yml`
  executado de verdade.

Não deu para testar a coleta na SEC — o ambiente onde isso foi preparado não tem
acesso a `sec.gov`. As partes que falam com a rede (`fetch`, `resolve_cik`) não
tiveram sua lógica de requisição alterada; o que mudou em volta delas foi cache,
contagem de cobertura e tratamento de erro.

## Observação sobre o `13f_dashboard.html` do pacote

Foi regerado só para você já ver as colunas novas. Os dados continuam sendo a
coleta de **2026-07-03** (até o 1T26) — a data no rodapé reflete isso. A primeira
rodada real sobrescreve o arquivo.
