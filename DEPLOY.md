# Deploy — DJ Set Curator (Vercel, URL pública)

Objetivo: ter a app acessível em `https://<teu-projeto>.vercel.app` de qualquer lado.

## 0. Pré-requisitos
- Conta Vercel (já tens acesso).
- O projeto num repositório Git (GitHub) — já está em `ricardobatista1986/DJSET_Curator`.

## 1. Na Vercel (dashboard)
1. **New Project** → Importa o repo `djset-curator`.
2. Framework Preset: **Other** (ou deixa detetar Python).
3. Root Directory: `/` (raiz do repo).
4. Build Command: deixar vazio (o `vercel.json` trata).
5. **Environment Variables** — adiciona TODAS (copiadas do teu `.env` local, gitignored):
   - `SUPABASE_URL` = https://kqyvpnmofrxcacjhnwsm.supabase.co
   - `SUPABASE_KEY` = (anon key do teu .env)
   - `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` = (do teu .env)
   - `SPOTIFY_REDIRECT_URI` = https://djset-curator.vercel.app/api/spotify/callback
   - `OPENROUTER_API_KEY` = (do teu .env, já tens)
   - `GROQ_API_KEY` = (do teu .env)
   - `GEMINI_API_KEY` = (do teu .env, opcional)
   - `LLM_PROVIDER` = groq
   - `LLM_MODEL` = llama-3.3-70b-versatile
   - `APP_USER` = ricardo.rocha.nb@gmail.com
   - `APP_PASSWORD` = (a senha da app — vê mensagem; NÃO uses a do teu email)
6. **Deploy**. A Vercel instala `requirements.txt` e serve via `api/index.py`.

## 2. Configurar a app Spotify (OAuth — obrigatório p/ ler playlists)
O Spotify exige autenticação de utilizador para ler playlists. Fazes na tua conta:
1. Vai a **developer.spotify.com/dashboard** → a tua app (a que deu o `SPOTIFY_CLIENT_ID`).
2. **Settings → Redirect URIs** → adiciona exatamente:
   `https://djset-curator.vercel.app/api/spotify/callback`
   (e, para testar localmente: `http://localhost:5000/api/spotify/callback`)
3. Os scopes usados são `playlist-read-private playlist-read-collaborative` (já pedidos no código).
4. Guarda. Não precisas de mexer em mais nada — a app trata o resto.
5. Na app, aba "Montar Set" → **🔗 Conectar Spotify** → autorizas → colas o link da playlist.

## 3. Aceder
- URL: `https://<teu-projeto>.vercel.app`
- Login com `APP_USER` / `APP_PASSWORD`.
- Montar set: aba "Montar Set" (colas faixas ou link de playlist Spotify ligada).
- Carregar banco: a recolha do 1001tracklists **NÃO funciona na Vercel** (sem browser/IP). Vê secção 5.

## 4. Limites Vercel (free tier)
- Funções: **timeout de 60s** (hobby). A geração de tracklist com LLM pode demorar → mantém sets até ~30 faixas por chamada.
- Cold start: primeira chamada após inatividade pode demorar alguns segundos.

## 5. Recolha do 1001tracklists (CARGA AUTOMÁTICA via worker)
O 1001tracklists é a **fonte de conhecimento** dos DJ sets (lá estão os sets reais
de quem toca o quê e em que ordem). A extração **não pode correr na Vercel**
(sem browser / Cloudflare bloqueia datacenters). Por isso usa-se um **worker**
que corres na tua máquina.

Fluxo:
1. Na app (Vercel) → aba "Carregar Banco" → escolhes género + máx sets → **🚀 Gerar carga**.
   Isto cria um `job` na tabela `jobs` do Supabase.
2. O `worker.py` (a correr na tua máquina) apanha o job, extrai os sets do
   1001tracklists (Chrome + teu IP) e grava sets+transições no Supabase.
3. O grafo enche-se e o motor passa a montar sets com conhecimento real.

Setup (1x):
```bash
# a) criar a tabela jobs (escolhe UMA opção):
#   opção A — via DATABASE_URL:
#      Supabase → Settings → Database → Connection string → copia a linha
#      postgresql://postgres:****@db.<ref>.supabase.co:5432/postgres
#      cola no .env como DATABASE_URL e corre:
python setup_db.py
#   opção B — cola config/create_jobs_table.sql na Supabase SQL Editor

# b) instalar Chrome do Playwright (1x):
playwright install chromium

# c) deixar o worker a correr (num terminal próprio):
python worker.py
```
Depois é só clicar "Gerar carga" quando quiseres abastecer.

## 6. Atualizar a app
```bash
git add -A && git commit -m "update" && git push
```
A Vercel faz redeploy automático.

## 7. Notas de segurança
- O `.env` NÃO vai para o repo (`.gitignore`). As chaves vivem nas Environment Variables da Vercel.
- Login simples (utilizador/senha). Partilha a senha só com quem deva aceder.
- Se suspeitares de comprometimento, roda `APP_PASSWORD` e as API keys.
