"""Provedor de LLM abstrato para o DJ Set Curator.

Suporta Groq (default, free tier generoso, sem cartao), OpenRouter e Google Gemini.
Configurado via .env:
  LLM_PROVIDER = groq | openrouter | gemini
  GROQ_API_KEY / OPENROUTER_API_KEY / GEMINI_API_KEY
  LLM_MODEL    = slug do modelo (tem default por provider)

Se a chave do provider nao estiver presente, o provedor nao quebra o servidor:
o metodo complete() devolve __LLM_FAIL__ e o Curator usa o fallback determinístico.
"""
import logging
import os

logger = logging.getLogger(__name__)

_DEFAULT_MODELS = {
    "groq": "llama-3.3-70b-versatile",
    "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
    "gemini": "gemini-2.0-flash",
}


class LLMProvider:
    def __init__(self):
        self.provider = os.environ.get("LLM_PROVIDER", "groq").lower()
        self.model = os.environ.get("LLM_MODEL") or _DEFAULT_MODELS.get(self.provider)
        self._client = None
        self._gemini = None
        self._kind = self.provider
        # valida se a chave existe (nao cria cliente ainda, para nao quebrar)
        self._key = (
            os.environ.get("GROQ_API_KEY") if self.provider == "groq" else
            os.environ.get("OPENROUTER_API_KEY") if self.provider == "openrouter" else
            os.environ.get("GEMINI_API_KEY")
        )
        if not self._key:
            logger.warning(f"LLM provider '{self.provider}' sem chave -> fallback determinístico.")

    def _ensure(self):
        if self._client is not None or self._gemini is not None:
            return
        if not self._key:
            raise RuntimeError("sem chave de LLM")
        if self._kind == "gemini":
            import google.genai as genai
            self._gemini = genai.Client(api_key=self._key)
        else:
            from openai import OpenAI
            base = ("https://api.groq.com/openai/v1" if self._kind == "groq"
                    else "https://openrouter.ai/api/v1")
            self._client = OpenAI(base_url=base, api_key=self._key)

    def complete(self, prompt: str, max_tokens: int = 1500) -> str:
        try:
            self._ensure()
        except Exception as e:
            return f"__LLM_FAIL__sem LLM configurado: {e}"
        try:
            if self._kind == "gemini":
                r = self._gemini.models.generate_content(
                    model=self.model, contents=prompt,
                    config={"max_output_tokens": max_tokens})
                return r.text
            r = self._client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens, temperature=0.7)
            return r.choices[0].message.content
        except Exception as e:
            logger.error(f"{self.provider} erro: {e}")
            return f"__LLM_FAIL__{e}"
