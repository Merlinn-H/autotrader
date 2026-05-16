# AI Rules — Autotrade

## API AI : DeepSeek, pas Claude

Toute mention de l'API Claude / Anthropic dans les prompts, la config ou le code doit être remplacée par l'API DeepSeek.

| Si le prompt dit... | Utiliser... |
|---|---|
| `ANTHROPIC_API_KEY` | `DEEPSEEK_API_KEY` |
| `anthropic` (package Python) | `openai` (package Python, compatible DeepSeek) |
| `claude-3-opus` / `claude-3-sonnet` / etc. | `deepseek-chat` |
| `https://api.anthropic.com` | `https://api.deepseek.com` |
| Anthropic SDK | OpenAI SDK (base_url=https://api.deepseek.com) |

## Principe

Le projet utilise DeepSeek comme fournisseur IA. Tout exemple, snippet ou configuration mentionnant Claude/Anthropic doit être automatiquement traduit vers DeepSeek.
