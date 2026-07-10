# DJ Set Curator — Design Document
*Criado: 2026-03-23*

## Objetivo
Sistema de curadoria de DJ sets que aprende como DJs reais montam suas tracklists
(via 1001tracklists.com) e propõe a melhor ordenação para uma lista de tracks fornecida,
incluindo sugestões de tracks externas que se encaixam nos gaps.

---

## Arquitetura — 5 Módulos

### Módulo 1: Coletor 1001tracklists
- API não-oficial via engenharia reversa
- Coleta inicial: 1000+ sets por gênero, 19 gêneros
- Job semanal via GitHub Actions (só delta)
- Controle de duplicatas por URL

### Módulo 2: Grafo de Transições
- track_a → track_b, peso = nº de ocorrências em sets reais
- Segmentado por gênero
- Top 15 vizinhos por track (predecessores e sucessores)
- Atualização incremental a cada coleta

### Módulo 3: Enriquecedor de Tracks
- Cascata: Spotify API → tunebat → fallback grafo
- Dados: BPM, Camelot key, energy, danceability, confidence
- Aceita texto livre para tracks fora do Spotify

### Módulo 4: Motor de Curadoria
- Score de compatibilidade: coocorrências × ΔBpm × compatibilidade Camelot
- Identificação de gaps + sugestões externas
- LLM: Gemini 2.0 Flash (API gratuita)
- Output: tracklist ordenada + scores + notas de transição

### Módulo 5: Interface
- Fase 1: Jupyter Notebooks (4 notebooks, um por módulo)
- Fase 2: Web App React + Vercel + Supabase

---

## Banco de Dados (Supabase)

```sql
genres                  -- gêneros ativos/inativos
sets                    -- sets coletados do 1001tracklists
tracks                  -- tracks com dados acústicos
transitions             -- grafo: track_from → track_to por set
user_lists              -- listas do usuário
user_list_tracks        -- tracks de cada lista
proposed_sets           -- sets propostos pelo motor
proposed_set_tracks     -- tracks de cada set proposto
```

---

## Decisões Técnicas

| Decisão | Escolha | Motivo |
|---|---|---|
| Coleta | API não-oficial 1001tracklists | Mais robusto que scraping HTML |
| Execução coleta | GitHub Actions | Não requer máquina local ligada |
| Grafo | Supabase (tabela transitions) | Centralizado, multi-device |
| Enriquecimento | Spotify API + tunebat | Cascata com fallback gracioso |
| LLM | Gemini 2.0 Flash | API gratuita, 1M tokens contexto |
| Storage | Supabase | Multi-device, já familiar |
| Frontend | React + Vercel | Mesma stack do app de saúde |

---

## Gêneros Ativos (19)
psytrance, progressive psytrance, darkpsy, full-on, techno, minimal techno,
tech house, deep house, progressive house, melodic house & techno, trance,
progressive trance, uplifting trance, drum & bass, dubstep, hardstyle,
ambient, electro, breaks

---

## Fases de Implementação

- [x] Design e arquitetura
- [ ] Fase 1: Investigação API 1001tracklists (endpoint discovery)
- [ ] Fase 2: Coletor + Supabase schema
- [ ] Fase 3: Grafo de transições
- [ ] Fase 4: Enriquecedor (Spotify + tunebat)
- [ ] Fase 5: Motor de curadoria (Gemini)
- [ ] Fase 6: Notebooks Jupyter
- [ ] Fase 7: Web App
- [ ] Fase 8: GitHub Actions (job semanal)
