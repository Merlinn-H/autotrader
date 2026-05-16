# AI Trader — Project Handout

**Dernière mise à jour :** 17 mai 2026 (23:30)  
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
| Déploiement | Streamlit Cloud | ✅ Dashboard en ligne, connecté au repo GitHub |

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
- **Dashboard local** : `venv\Scripts\python -m streamlit run dashboard.py` → 4 pages fonctionnelles
- **Dashboard Cloud** : Déployé sur Streamlit Cloud, connecté au repo, mis à jour automatiquement à chaque push
- **Dry cycle** : Boucle complète exécutée sans crash (décision HOLD car clé DeepSeek pas encore active)
- **Git** : Repo privé sur GitHub, `.env` et `trader.db` dans `.gitignore`

---

## Ce qui ne fonctionne pas encore / À faire

### Bloquant
1. **Clé DeepSeek à valider** — La clé dans `.env` (`sk-1869...`) a retourné `Authentication Fails` au dry cycle. Vérifier que la clé est active et que le compte DeepSeek a du crédit. Si la clé marche, le scheduler prendra de vraies décisions.

### Améliorations futures
2. **Dashboard Cloud = read-only** — Le dashboard Streamlit Cloud ne peut pas lancer le scheduler. Il affiche juste les données. Le scheduler doit tourner sur ton PC ou un serveur.
3. **Pas de backtesting** — Le moteur ne peut pas rejouer des données historiques.
4. **Pas de gestion des splits/dividendes** — yfinance les inclut dans l'historique mais le broker virtuel n'ajuste pas les positions.
5. **Une seule stratégie** — `build_prompt()` a un prompt unique.
6. **Pas de notifications** — Aucun système d'alerte quand un trade est exécuté.
7. **Pas de log rotate** — Les logs sont en console uniquement.
8. **Warnings yfinance** — `Pandas4Warning: Timestamp.utcnow is deprecated`. Cosmétique.

---

## Comment faire tourner le projet quand les marchés sont ouverts

### Prérequis (une seule fois)

```bash
# 1. Cloner le repo
git clone https://github.com/Merlinn-H/autotrader.git
cd autotrader

# 2. Créer le venv et installer les dépendances
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# 3. Créer le .env avec ta clé DeepSeek
cp .env.template .env
# → Édite .env et mets ta vraie clé : DEEPSEEK_API_KEY=sk-1869...
```

### Lancer le système (chaque session de trading)

Tu as besoin de **2 terminaux** ouverts dans le dossier `autotrader/` :

**Terminal 1 — Le scheduler (obligatoire)**
```bash
venv\Scripts\python scheduler.py
```
C'est le cerveau. Il tourne en fond et déclenche la boucle de trading automatiquement :
- Du lundi au vendredi
- De 15:30 à 22:00 heure française (9:30–16:00 New York)
- Tous les X minutes (par défaut 15, configurable dans le dashboard)

Tu verras ce genre de logs :
```
[INFO] Starting scheduler — interval=15min, timezone=US/Eastern
[INFO] Scheduler running. Press Ctrl+C to stop.
[INFO] Trigger at 09:30 ET — running trading cycle
[INFO] --- Processing AAPL ---
[INFO] Quote: $213.40
[INFO] Raw AI decision: BUY x5 (confidence=0.78)
[INFO] Validated: BUY x5 (confidence=0.78)
[INFO] EXECUTED BUY 5 AAPL @ $213.40
[INFO] Cycle done: 1 buys, 0 sells, 2 holds, 0 errors
```

**Terminal 2 — Le dashboard (optionnel, pour voir ce qui se passe)**
```bash
venv\Scripts\python -m streamlit run dashboard.py
```
Ouvre `http://localhost:8501` dans ton navigateur. Tu peux aussi utiliser le dashboard Streamlit Cloud (déployé en ligne) mais il ne lance pas le scheduler — il affiche juste l'état du portefeuille.

### Vérifier que tout est prêt avant le lundi

```bash
# Test 1 : le broker virtuel fonctionne
venv\Scripts\python smoke_test.py

# Test 2 : les données Yahoo Finance arrivent
venv\Scripts\python smoke_market.py

# Test 3 : forcer un dry cycle (même si le marché est fermé)
venv\Scripts\python -c "
from src.database import init_db, set_config
from src.portfolio import Portfolio
from src.virtual_broker import get_account
from src.trader import _process_ticker
init_db()
set_config('watchlist', 'AAPL')
portfolio = Portfolio.load()
account = get_account()
result = _process_ticker('AAPL', portfolio, account, {})
print('Action:', result.get('action'), '| Reason:', result.get('reason', ''))
"
```

Si le test 3 affiche autre chose que `HOLD` avec `reason=rate_limit_or_error` ou `Authentication Fails`, ta clé DeepSeek est valide et l'IA prend des décisions.

### Heures de trading (heure française)

| Saison | Ouverture | Fermeture |
|---|---|---|
| Hiver (nov-mars) | 15:30 | 22:00 |
| Été (mars-nov) | 15:30 | 22:00 |

Les États-Unis passent à l'heure d'été aussi, donc 9:30 ET = toujours 15:30 en France. Le décalage est constant.

### Arrêter le système

Ctrl+C dans le terminal du scheduler. Le dashboard se ferme aussi avec Ctrl+C.

---

## Commandes utiles

```bash
# Installer les dépendances
python -m venv venv
venv\Scripts\pip install -r requirements.txt

# Lancer le scheduler (terminal 1)
venv\Scripts\python scheduler.py

# Lancer le dashboard (terminal 2)
venv\Scripts\python -m streamlit run dashboard.py

# Tests
venv\Scripts\python -m pytest tests/ -v

# Smoke tests
venv\Scripts\python smoke_test.py
venv\Scripts\python smoke_market.py
```

---

## Structure du projet

```
autotrader/
├── .env.template          # Template clé DeepSeek
├── .gitignore             # .env, *.db, venv/
├── CLAUDE.md              # Règles de traduction Claude → DeepSeek
├── HANDOUT.md             # Ce fichier
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
