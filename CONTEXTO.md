# DJ Set Curator — Arquivo de Contexto
*Atualizado: 2026-03-25*

---

## O que é este projeto

Sistema de curadoria de DJ sets que:
1. Coleta sets reais do 1001tracklists.com (1000+ por gênero)
2. Constrói um grafo de transições: qual track segue qual, quantas vezes
3. Enriquece tracks com BPM, Camelot key e energia (Spotify + tunebat)
4. Usa Gemini 2.0 Flash para propor a tracklist ideal
5. Sugere tracks externas que se encaixam nos gaps da sua lista

---

## Status atual

- [x] Design e arquitetura definidos
- [x] Código de todos os módulos escrito e validado
- [x] Notebooks Jupyter criados e testados (JSON válido)
- [x] Schema do banco de dados (Supabase) criado
- [x] GitHub Actions workflow criado
- [ ] Coleta inicial ainda não rodou (base vazia)
- [ ] Primeira tracklist gerada ainda não

---

## Decisões arquiteturais tomadas

| Decisão | Escolha | Motivo |
|---|---|---|
| Coleta | Playwright async + BeautifulSoup | API JSON interna não existe; scraping HTML é a única opção |
| Modelo de curadoria | Grafo (B) + LLM com contexto (C) combinados | Grafo pontua suas tracks E sugere externas; LLM ordena com raciocínio |
| LLM | Gemini 2.0 Flash (google-genai SDK) | Grátis, 1M tokens contexto, nova SDK estável |
| Storage | Supabase | Multi-device, gratuito, já familiar |
| Execução da coleta | GitHub Actions | Não exige máquina local ligada |
| Atualização | Semanal, automática, só delta | Sem retrabalho, acompanha ritmo de publicação do site |
| Gêneros | 19 gêneros, configuráveis via tabela genres | Filtro global: coleta, grafo e curadoria usam só os ativos |
| Feedback | Aprovação com 1 clique + histórico de sets propostos | Sem fricção, retroalimentação passiva |
| Tracks manuais | Texto livre "Artista - Titulo" | Busca automática; se não achar, usa só nome no grafo |
| Interface fase 1 | Jupyter Notebooks | Validação e uso diário antes do web app |
| Interface fase 2 | React + Vercel | Mesma stack do app de saúde (já familiar) |

---

## Arquitetura dos módulos

```
src/collector/collector.py   — Coleta sets do 1001tracklists (async)
src/graph/graph.py           — Queries no grafo de transições (sync)
src/enricher/enricher.py     — BPM/key/energia via Spotify+tunebat (sync)
src/curator/curator.py       — Motor de curadoria via Gemini (sync)

notebooks/01_coletor.ipynb      — Testa e roda coleta (usa await)
notebooks/02_grafo.ipynb        — Explora grafo (sem await)
notebooks/03_enriquecedor.ipynb — Enriquece tracks (sem await)
notebooks/04_curadoria.ipynb    — USO DIÁRIO — gera tracklists (sem await)

scripts/run_collector.py     — Entrada do GitHub Actions (asyncio.run)
config/schema.sql            — Schema do Supabase (tabelas)
config/rpc_functions.sql     — Funções SQL para queries do grafo
.github/workflows/collect.yml — Job semanal + coleta manual
```

---

## Banco de dados (Supabase)

```
genres              — gêneros ativos/inativos (19 pré-carregados)
sets                — sets coletados do 1001tracklists
tracks              — tracks com dados acústicos
transitions         — grafo: track_from → track_to (coração do sistema)
user_lists          — listas do usuário
user_list_tracks    — tracks de cada lista
proposed_sets       — sets propostos pelo motor (com approved bool)
proposed_set_tracks — tracks de cada set proposto
```

---

## Gêneros configurados (19)

| Slug | Nome |
|---|---|
| goa-psy-trance | Goa / Psy-Trance |
| techno | Techno |
| tech-house | Tech House |
| house | House |
| deep-house | Deep House |
| progressive-house | Progressive House |
| melodic-house-techno | Melodic House / Techno |
| minimal-deep-tech | Minimal / Deep Tech |
| trance | Trance |
| drum-bass | Drum & Bass |
| dubstep | Dubstep |
| hard-dance | Hard Dance |
| bass-house | Bass House |
| breaks | Breaks |
| afro-house | Afro House |
| indie-dance | Indie Dance |
| electronica | Electronica |
| organic-house-downtempo | Organic House / Downtempo |
| mainstage | Mainstage |

Para desativar um gênero:
```sql
UPDATE genres SET active = FALSE WHERE slug = 'dubstep';
```

---

## Credenciais necessárias (.env)

```
SUPABASE_URL          — https://xxxx.supabase.co
SUPABASE_KEY          — anon key (eyJ...)
SPOTIFY_CLIENT_ID     — do Spotify Developer Dashboard
SPOTIFY_CLIENT_SECRET — do Spotify Developer Dashboard
GEMINI_API_KEY        — do Google AI Studio (AIza...)
```

---

## Comportamento importante por módulo

### collector.py
- Todos os métodos públicos são `async` — use `await` no Jupyter
- `scrape_set(url)` → scraping de um set individual
- `get_set_urls(genre, max)` → lista de URLs de um gênero
- `collect_genre(genre, max)` → coleta completa com persistência
- Delay de 3–6s entre requisições (respeito ao servidor)
- Deduplicação por `external_id` (nunca reprocessa o mesmo set)

### graph.py
- Totalmente síncrono — sem `await`
- `get_successors(track_id, genre_id, top_n=15)` → top N tracks que seguem
- `get_predecessors(track_id, genre_id, top_n=15)` → top N tracks que precedem
- `get_typical_position(track_id, genre_id=None)` → zona típica no set
- `genre_id=None` = todos os gêneros (sem filtro)
- Usa RPC functions do Supabase; fallback manual se RPC falhar

### enricher.py
- Totalmente síncrono — sem `await`
- Cascata: Spotify → tunebat → fallback gracioso
- `enrich_track(artist, title)` → retorna dict com todos os dados
- `enrich_all_unenriched(batch_size)` → lote de tracks sem dados
- `_upsert_track_db()` → cria a track se não existir, atualiza se existir
- confidence: "high" (Spotify), "medium" (tunebat), "low" (não encontrou)

### curator.py
- Totalmente síncrono — sem `await`
- Usa `google.genai` SDK (nova, não depreciada)
- `build_set(tracks, genre_slug, list_name, save_to_db)` → retorna dict
- 4 etapas impressas no console durante execução
- Sugere tracks externas com count >= 3 ocorrências no grafo
- Salva no histórico automaticamente (proposed_sets)

---

## Erros já corrigidos

| Erro | Causa | Solução |
|---|---|---|
| `sync API inside asyncio loop` | Playwright sync em Jupyter | Reescrito com async_playwright |
| `FutureWarning google.generativeai` | SDK depreciada | Trocado para google.genai |
| `_update_db` falha silenciosa | Track não existia no DB | Reescrito como upsert (cria ou atualiza) |
| `genre_id=-1` inválido | Chamada com -1 em vez de None | Suporta None como "todos os gêneros" |
| JSON inválido nos notebooks | Geração com heredoc problemático | Gerados via script Python com json.dump |

---

## Próximos passos

### Imediato (Fase 1 — Jupyter)
1. Instalar dependências: `pip install -r requirements.txt`
2. Instalar browser: `playwright install chromium`
3. Instalar novo SDK Gemini: `pip install google-genai`
4. Executar schema no Supabase: `config/schema.sql` + `config/rpc_functions.sql`
5. Configurar `.env` com as 5 credenciais
6. Testar notebook 01 (TESTE 1 e TESTE 2)
7. Coletar 10 sets de validação
8. Testar notebook 03 (enriquecimento)
9. Testar notebook 04 (primeira tracklist)
10. Configurar GitHub Actions para coleta em escala

### Futuro (Fase 2 — Web App)
- Interface React + Vercel (mesma stack do app de saúde)
- 4 telas: Configuração, Nova Tracklist, Resultado, Histórico
- Input: URL de playlist Spotify + campo de texto para tracks manuais
- Output: tracklist com botão "Copiar" e aprovação com 1 clique

---

## Roadmap futuro (pós web app)

- Importar playlist do Spotify diretamente via OAuth
- Aprendizado de preferências: padrões dos sets que você aprovou vs rejeitou
- Filtro por BPM range e energia mínima
- Exportação para formato compatível com Rekordbox/Serato
- App iOS via Capacitor (mesmo código React)

---

## Notas técnicas importantes

**Por que `await` só no notebook 01?**
O collector usa `async_playwright` que requer contexto async. Os outros módulos
(graph, enricher, curator) são síncronos — sem await necessário.

**Jupyter moderno suporta await direto?**
Sim. Anaconda com ipykernel >= 6.0 suporta `await` diretamente nas células,
sem `nest_asyncio` ou `asyncio.run()`. É o comportamento padrão desde 2021.

**Por que google-genai e não google.generativeai?**
O pacote `google.generativeai` foi depreciado em 2025. O novo é `google-genai`
(import: `import google.genai as genai`). Sintaxe mudou:
- Antigo: `genai.configure(api_key=...) + GenerativeModel(...).generate_content(...)`
- Novo: `genai.Client(api_key=...).models.generate_content(model=..., contents=...)`
