# Deploy — DJ Set Curator (Vercel, URL pública)

Objetivo: ter a app acessível em `https://<teu-projeto>.vercel.app` de qualquer lado.

## 0. Pré-requisitos
- Conta Vercel (já tens acesso).
- O projeto num repositório Git (GitHub recomendado). Se ainda não tens repo:
  ```bash
  cd ~/djset-curator-v3/djset-curator
  git init && git add -A && git commit -m "DJ Set Curator v1"
  # cria o repo no GitHub e:
  git remote add origin git@github.com:<teu-user>/djset-curator.git
  git push -u origin main
  ```

## 1. Na Vercel (dashboard)
1. **New Project** → Importa o repo `djset-curator`.
2. Framework Preset: **Other** (ou deixa detetar Python).
3. Root Directory: `/` (raiz do repo).
4. Build Command: deixar vazio (o `vercel.json` trata).
5. **Environment Variables** — adiciona TODAS (copiadas do teu `.env` local, gitignored):
   - `SUPABASE_URL` = https://kqyvpnmofrxcacjhnwsm.supabase.co
   - `SUPABASE_KEY` = (anon key do teu .env)
   - `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` = (do teu .env)
   - `OPENROUTER_API_KEY` = (do teu .env, já tens)
   - `GROQ_API_KEY` = (a key Groq que vais criar em console.groq.com — grátis)
   - `GEMINI_API_KEY` = (do teu .env, opcional)
   - `LLM_PROVIDER` = groq
   - `LLM_MODEL` = llama-3.3-70b-versatile
   - `APP_USER` = ricardo.rocha.nb@gmail.com
   - `APP_PASSWORD` = (a senha da app que o Hermes gerou — vê mensagem; NÃO uses a do teu email)
6. **Deploy**. A Vercel instala `requirements.txt` e serve via `api/index.py`.

## 2. Aceder
- URL: `https://<teu-projeto>.vercel.app`
- Login com `APP_USER` / `APP_PASSWORD`.
- Para adicionar uma tracklist: aba "Montar Set". Para carregar o banco: aba "Carregar Banco" (a coleta corre no servidor da Vercel — demora conforme o número de sets; acompanha o progresso).

## 3. Limites Vercel (free tier)
- Funções têm **timeout de 60s** (hobby). A geração de tracklist com LLM pode demorar mais se houver muitas tracks → mantém sets até ~30 faixas por chamada, ou aumenta o timeout no plano pago.
- A coleta de 1001tracklists em background roda numa função; para grandes volumes, considera correr a coleta localmente e empurrar para o Supabase (que é partilhado).
- Cold start: primeira chamada após inatividade pode demorar alguns segundos.

## 4. Atualizar a app
```bash
git add -A && git commit -m "update" && git push
```
A Vercel faz redeploy automático.

## 5. Notas de segurança
- O `.env` NÃO vai para o repo (está no `.gitignore`). As chaves vivem nas Environment Variables da Vercel.
- A app tem login simples (utilizador/senha). Não é multi-utilizador. Partilha a senha só com quem deva aceder.
- Se suspeitares de comprometimento, roda a `APP_PASSWORD` nas Environment Variables da Vercel e roda as API keys.
