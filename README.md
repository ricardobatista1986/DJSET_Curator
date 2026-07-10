# 🎛️ DJ Set Curator

Sistema de curadoria de DJ sets que aprende com sets reais do 1001tracklists
e propõe a melhor ordenação para suas tracks, incluindo sugestões externas.

---

## Como funciona

1. **Coleta** sets reais do 1001tracklists por gênero (1000+ sets/gênero)
2. **Constrói** um grafo de transições: qual track segue qual, quantas vezes
3. **Enriquece** suas tracks com BPM, Camelot key e energia (Spotify + tunebat)
4. **Propõe** a tracklist ideal via Gemini 2.0 Flash, usando o grafo como contexto
5. **Sugere** tracks externas que se encaixam naturalmente nos gaps

---

## Setup passo a passo

### 1. Pré-requisitos

- Python 3.11+
- Conta no [Supabase](https://supabase.com) (gratuito)
- Conta no [Spotify for Developers](https://developer.spotify.com/dashboard) (gratuito)
- Conta no [Google AI Studio](https://aistudio.google.com) para Gemini (gratuito)
- Conta no [GitHub](https://github.com) (gratuito)

---

### 2. Instalar dependências

```bash
pip install -r requirements.txt
playwright install chromium
```

---

### 3. Configurar Supabase

1. Crie um projeto em supabase.com
2. Vá em **SQL Editor** e execute:
   - `config/schema.sql` — cria as tabelas
   - `config/rpc_functions.sql` — cria as funções do grafo
3. Copie a **Project URL** e a **anon key** (Settings → API)

---

### 4. Configurar Spotify

1. Acesse [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard)
2. Clique em **Create app**
3. Preencha qualquer nome e URL de redirect (`http://localhost`)
4. Copie o **Client ID** e **Client Secret**

---

### 5. Configurar Gemini

1. Acesse [aistudio.google.com](https://aistudio.google.com)
2. Clique em **Get API key**
3. Copie a chave gerada

---

### 6. Criar arquivo .env

```bash
cp .env.example .env
# Edite .env com suas credenciais
```

---

### 7. Testar localmente (Jupyter)

```bash
jupyter notebook notebooks/01_coletor.ipynb
```

Execute as células de **TESTE** para validar que o scraping funciona.
Depois rode `notebooks/03_enriquecedor.ipynb` para validar o Spotify.
Depois rode `notebooks/04_curadoria.ipynb` para gerar sua primeira tracklist.

---

### 8. Configurar a coleta em escala (GitHub Actions)

1. Suba este projeto para um repositório **privado** no GitHub
2. Vá em **Settings → Secrets and variables → Actions**
3. Adicione os secrets:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `SPOTIFY_CLIENT_ID`
   - `SPOTIFY_CLIENT_SECRET`
4. Vá em **Actions → DJ Set Curator — Coleta 1001tracklists**
5. Clique em **Run workflow**
6. Para a **coleta inicial**: selecione `mode=full`, `max_sets=1000`
7. Para updates: o job semanal roda automaticamente toda segunda-feira

---

## Uso diário

Abra `notebooks/04_curadoria.ipynb`, edite:
- `GENERO` — gênero do set
- `MINHAS_TRACKS` — suas tracks no formato `Artista - Título`
- `NOME_DO_SET` — nome para salvar no histórico

Execute as células → a tracklist proposta aparece na tela.

---

## Estrutura do projeto

```
djset-curator/
├── config/
│   ├── schema.sql          # Schema do banco de dados
│   └── rpc_functions.sql   # Funções SQL para o grafo
├── src/
│   ├── collector/          # Módulo 1: Coleta 1001tracklists
│   ├── graph/              # Módulo 2: Grafo de transições
│   ├── enricher/           # Módulo 3: Dados acústicos
│   └── curator/            # Módulo 4: Motor de curadoria
├── notebooks/
│   ├── 01_coletor.ipynb    # Testa e roda coleta
│   ├── 02_grafo.ipynb      # Explora o grafo
│   ├── 03_enriquecedor.ipynb # Enriquece tracks
│   └── 04_curadoria.ipynb  # Gera tracklists ← uso diário
├── scripts/
│   └── run_collector.py    # Entrada do GitHub Actions
├── .github/
│   └── workflows/
│       └── collect.yml     # Job semanal + coleta manual
├── requirements.txt
└── .env.example
```

---

## Gêneros disponíveis

| Slug | Nome |
|---|---|
| `goa-psy-trance` | Goa / Psy-Trance |
| `techno` | Techno |
| `tech-house` | Tech House |
| `house` | House |
| `deep-house` | Deep House |
| `progressive-house` | Progressive House |
| `melodic-house-techno` | Melodic House / Techno |
| `minimal-deep-tech` | Minimal / Deep Tech |
| `trance` | Trance |
| `drum-bass` | Drum & Bass |
| `dubstep` | Dubstep |
| `hard-dance` | Hard Dance |
| `bass-house` | Bass House |
| `breaks` | Breaks |
| `afro-house` | Afro House |
| `indie-dance` | Indie Dance |
| `electronica` | Electronica |
| `organic-house-downtempo` | Organic House / Downtempo |
| `mainstage` | Mainstage |

Para **desativar** um gênero (parar de coletar e excluir do contexto):
```sql
UPDATE genres SET active = FALSE WHERE slug = 'dubstep';
```
