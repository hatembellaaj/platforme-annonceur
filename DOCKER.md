# Docker — Platform Annonceur

Stack lancée par `docker compose` :

| Service   | Image                | Port hôte | Rôle                                                      |
| --------- | -------------------- | --------- | --------------------------------------------------------- |
| `app`     | build local (Python 3.12) | `8087`    | App Streamlit (`app.py`)                                  |
| `postgres`| `postgres:16-alpine` | `5432`    | Base de données locale (remplace Supabase pour les overrides) |
| `adminer` | `adminer:latest`     | `8080`    | UI web pour explorer la DB                                |

## 1. Prérequis

- Docker Desktop ≥ 4.30 (ou Docker Engine + Compose v2)
- Un service account Google Ad Manager valide
- (Optionnel) Une clé Gemini pour l'assistant IA

## 2. Configurer les variables d'environnement

```bash
cp .env.example .env
```

Édite `.env` :

- `GAM_NETWORK_CODE`, `GAM_API_VERSION` : identifiants GAM.
- `GAM_SERVICE_ACCOUNT_JSON` : **toute** la JSON du service account, sur **une seule ligne**. Astuce :
  ```bash
  jq -c . gam-service-account.json
  ```
  Copie la sortie après le `=` (entourée de guillemets si elle contient des espaces).
- `GAM_GEMINI_API_KEY` : clé Gemini (laisser vide désactive juste l'assistant).
- `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` : credentials Postgres locaux.

⚠️ `.env` ne doit jamais être commité (déjà ignoré).

## 3. Démarrer la stack

```bash
docker compose up -d --build
```

Ouvre ensuite :

- App Streamlit : http://localhost:8087
- Adminer : http://localhost:8080
  - Système : **PostgreSQL**
  - Serveur : `postgres`
  - Utilisateur / mot de passe / base : ceux de `.env`

Logs en direct :

```bash
docker compose logs -f app
```

Arrêt :

```bash
docker compose down            # garde les volumes
docker compose down -v         # supprime aussi les données Postgres
```

## 4. Comment fonctionnent les overrides

Le code essaie d'abord Supabase, puis bascule sur les fichiers JSON locaux si la
DB est indisponible. Dans cette stack Docker :

- `app` reçoit `SUPABASE_DB_HOST=postgres` et `SUPABASE_DB_SSLMODE=disable` via
  `docker-compose.yml` → il écrit dans la table `platform_annonceur_overrides`
  du conteneur Postgres.
- Les fichiers `*_overrides.json` et `platform_settings.json` sont bind-mountés
  dans le conteneur pour garder un fallback fonctionnel et persister entre les
  rebuilds.
- Les données Postgres vivent dans le volume nommé `postgres_data`.

> Note : un patch a été appliqué à `local_supabase.py` pour exposer
> `SUPABASE_DB_SSLMODE` (défaut `require`). Le Postgres local n'a pas de TLS,
> donc on force `disable` côté `app`. Ça n'affecte pas la prod Supabase qui
> reste sur `require`.

## 5. Pointer sur la vraie Supabase au lieu du Postgres local

Dans `docker-compose.yml`, commente le bloc `environment:` du service `app` qui
écrase les variables `SUPABASE_*`, puis renseigne dans `.env` :

```env
SUPABASE_DB_HOST=db.<ref>.supabase.co
SUPABASE_DB_PORT=5432
SUPABASE_DB_USER=postgres
SUPABASE_DB_PASSWORD=...
SUPABASE_DB_NAME=postgres
SUPABASE_DB_SSLMODE=require
```

Tu peux aussi retirer les services `postgres` et `adminer` si tu n'en as plus
besoin.

## 6. Commandes utiles

```bash
# Rebuild après un changement de requirements.txt
docker compose build --no-cache app

# Shell dans le conteneur app
docker compose exec app bash

# Vérifier la santé
docker compose ps

# Lancer un client psql
docker compose exec postgres psql -U postgres -d platform_annonceur
```

## 7. Sécurité — checklist rapide

- [ ] `.env` n'est pas commité.
- [ ] `gam-service-account.json` n'est pas commité (le fichier est généré au runtime depuis `GAM_SERVICE_ACCOUNT_JSON`).
- [ ] Le port `5432` n'est exposé qu'en local dev. En prod, retirer le mapping `ports:` du service `postgres`.
- [ ] Le port `8080` (Adminer) est protégé / désactivé en prod.
