# AI Trader — Project Handout

**Date :** 17 mai 2026  
**Repo :** https://github.com/Merlinn-H/autotrader (privé)  
**Stack :** Python 3.12, yfinance, SQLite/SQLModel, Streamlit, APScheduler, DeepSeek API

---

## Ce qui a été fait

### Infrastructure
| Module | Fichier | Statut |
|---|---|---|
| Config loader | `src/config.py` | ✅ Charge `DEEPSEEK_API_KEY` depuis `.env` |
| Base de données | `src/database.py` | ✅ Tables : `portfolio_config`, `positions`, `trade_log`, `decision_log` |
| Rate limiter Yahoo | `src/rate_limiter.py` | ✅ 1.2s entre appels, cap 1900/h, cache TTL 30s-300s |
| Données marché | `src/market_data.py` | ✅ `get_quote()`, `get_historical()`, `get_batch_quotes()` via yfinance |
| Heures de marché | `src/market_status.py` | ✅ Vérifie 9:30-16:00 ET, weekdays only (pytz) |
| Config portefeuille | `src/portfolio.py` | ✅ Watchlist, risk params, `apply_buy/sell`, `get_positions` |
| Broker virtuel | `src/virtual_broker.py` | ✅ Ordres simulés, cash $100k par défaut, positions en SQLite |
| Moteur IA | `src/decision_engine.py` | ✅ Rate limiter, build_prompt, query_deepseek, validate_decision |
| Boucle trading | `src/trader.py` | ✅ Cycle complet : quote → snapshot → IA → validate → execute |
| Scheduler | `scheduler.py` | ✅ APScheduler, jours ouvrés, 9:30-16:00 ET |
| Dashboard | `dashboard.py` | ✅ Streamlit 4 pages |
| Tests | `tests/test_decision_engine.py` | ✅ 5 tests unitaires (mockés, zéro appel API) |
| Smoke tests | `smoke_test.py`, `smoke_market.py` | ✅ Valident le broker virtuel et les données marché |

### Décisions d'architecture

1. **Pas de broker externe** — Tout est simulé en local. `virtual_broker.py` gère les positions et le cash dans SQLite. Pas d'Alpaca, pas d'Interactive Brokers.

2. **DeepSeek au lieu de Claude** — Le projet original visait l'API Anthropic. Remplacé par DeepSeek (`deepseek-chat`) via le SDK OpenAI (`base_url=https://api.deepseek.com`). Voir `CLAUDE.md` pour les règles de traduction.

3. **Pas d'ORM lourd** — SQLModel (mince couche au-dessus de SQLAlchemy). Pas de Django, pas de migrations Alembic. Les tables sont créées par `init_db()` → `SQLModel.metadata.create_all()`.

4. **Rate limiting partout** — Yahoo Finance (1 req/s), DeepSeek (configurable via `max_ai_calls_per_hour`, défaut 50), cache TTL pour éviter les doublons.

5. **Barrière de sécurité** — `validate_decision()` bloque toute décision IA brute avant qu'elle atteigne le portefeuille. Confidence minimum 0.65, vérifie cash/positions/limites quotidiennes.

---

## Ce qui fonctionne

- **Smoke test broker virtuel** : `venv\Scripts\python smoke_test.py` → BUY 10 AAPL, SELL 5 AAPL, equity tracking OK
- **Smoke test marché** : `venv\Scripts\python smoke_market.py` → quotes AAPL/MSFT/GOOGL, cache, rate limiting OK
- **Tests unitaires** : `venv\Scripts\python -m pytest tests/ -v` → 5/5 passent
- **Dashboard** : `venv\Scripts\python -m streamlit run dashboard.py` → 4 pages fonctionnelles
- **Dry cycle** : Boucle complète exécutée sans crash (décision HOLD car pas de clé API DeepSeek valide)
- **Git** : Repo privé sur GitHub, `.env` et `trader.db` dans `.gitignore`

---

## Ce qui ne fonctionne pas encore / À faire

### Bloquant
1. **Clé DeepSeek non testée** — La clé dans `.env` (`sk-1869...`) n'a pas encore été validée avec un vrai appel. Le dry cycle a retourné `Authentication Fails`. Vérifier que la clé est active et que le compte DeepSeek a du crédit.

### Améliorations futures
2. **Pas de backtesting** — Le moteur ne peut pas rejouer des données historiques pour tester les stratégies.
3. **Pas de gestion des splits/dividendes** — yfinance les inclut dans l'historique mais le broker virtuel n'ajuste pas les positions.
4. **Une seule stratégie** — `build_prompt()` a un prompt unique. Pas de mode multi-stratégie (momentum, mean reversion, etc.).
5. **Pas de notifications** — Aucun système d'alerte (email, webhook) quand un trade est exécuté.
6. **Dashboard en local seulement** — Pas de déploiement Streamlit Cloud. Le scheduler et le dashboard tournent sur la même machine.
7. **Pas de log rotate** — Les logs sont en console uniquement, pas de fichier.
8. **Streamlit pas dans requirements.txt** — Oublié. Corrigé depuis.
9. **Les warnings yfinance** — `Pandas4Warning: Timestamp.utcnow is deprecated` à chaque appel. Cosmétique, peut être supprimé avec `warnings.filterwarnings`.

---

## Commandes utiles

```bash
# Installer les dépendances
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# Configurer les clés API
cp .env.template .env
# → éditer .env avec la clé DeepSeek

# Lancer le dashboard
venv\Scripts\python -m streamlit run dashboard.py

# Lancer le scheduler (terminal séparé)
venv\Scripts\python scheduler.py

# Tests
venv\Scripts\python -m pytest tests/ -v

# Smoke tests
venv\Scripts\python smoke_test.py
venv\Scripts\python smoke_market.py

# Dry cycle forcé (ignore les heures de marché)
venv\Scripts\python -c "from src.database import *; from src.trader import *; init_db(); ..."
```

---

## Structure du projet

```
autotrader/
├── .env.template          # Template clé DeepSeek
├── .gitignore             # .env, *.db, venv/
├── CLAUDE.md              # Règles de traduction Claude → DeepSeek
├── README.md              # Setup et vue d'ensemble
├── requirements.txt       # Toutes les dépendances
├── smoke_test.py          # Test broker virtuel
├── smoke_market.py        # Test données marché
├── scheduler.py           # Lanceur APScheduler
├── dashboard.py           # Streamlit 4 pages
├── src/
│   ├── config.py          # Charge .env
│   ├── database.py        # Tables SQLite + CRUD
│   ├── market_data.py     # Wrapper yfinance
│   ├── rate_limiter.py    # Rate limiter Yahoo Finance
│   ├── market_status.py   # Heures de marché US
│   ├── portfolio.py       # Config portefeuille + apply_buy/sell
│   ├── virtual_broker.py  # Exécution simulée
│   ├── decision_engine.py # Rate limiter IA + build_prompt + query + validate
│   └── trader.py          # Boucle de trading principale
└── tests/
    └── test_decision_engine.py  # 5 tests unitaires mockés
```

---

## Valeurs par défaut

| Paramètre | Valeur | Emplacement |
|---|---|---|
| `DEFAULT_CASH` | $100,000 | `virtual_broker.py` |
| `max_position_size_pct` | 20% | `portfolio_config` |
| `max_daily_trades` | 10 | `portfolio_config` |
| `risk_tolerance` | medium | `portfolio_config` |
| `stop_loss_pct` | 5% | `portfolio_config` |
| `max_ai_calls_per_hour` | 50 | `portfolio_config` |
| `loop_interval_minutes` | 15 | `portfolio_config` |
| Watchlist par défaut | AAPL, MSFT, GOOGL | `portfolio_config` |
| Marché ouvert | 9:30-16:00 ET, lundi-vendredi | `market_status.py` |
| Rate limit Yahoo | 1.2s/appel, 1900/h | `rate_limiter.py` |
| Cache Yahoo quote | 30s | `rate_limiter.py` |
| Cache Yahoo historique | 5min | `rate_limiter.py` |
| Modèle DeepSeek | `deepseek-chat` | `decision_engine.py` |
| Seuil confidence minimum | 0.65 | `decision_engine.py` |
