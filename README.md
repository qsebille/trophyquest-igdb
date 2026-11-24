# IGDB Enricher

Ce module est une application Python conçue pour être exécutée sous forme de fonction **AWS Lambda**. Elle a pour rôle
d'enrichir les jeux PSN de la base de données avec des informations provenant de **IGDB** via l'API **Twitch**.

Le statut de chaque jeu est géré dans une base de données **PostgreSQL**.

## Fonctionnalités

- Récupération des jeux PSN en attente d'enrichissement.
- Recherche de correspondances sur IGDB.
- Calcul de score de similarité pour trouver le meilleur candidat.
- Mise à jour de la base de données avec les IDs IGDB et les métadonnées (images, compagnies, etc.).

## Prérequis

- Python 3.12+
- Accès à une base de données PostgreSQL.
- Un Client ID et un Client Secret Twitch (pour l'API IGDB).

## Installation

```bash
pip install -r requirements.txt
```

## Configuration (Variables d'environnement)

Le module utilise les variables d'environnement suivantes :

- `POSTGRES_HOST` : Hôte de la base de données PostgreSQL.
- `POSTGRES_PORT` : Port de la base de données.
- `POSTGRES_DATABASE` : Nom de la base de données.
- `POSTGRES_USER` : Utilisateur PostgreSQL.
- `POSTGRES_PASSWORD` : Mot de passe PostgreSQL.
- `TWITCH_CLIENT_ID` : Client ID Twitch.
- `TWITCH_CLIENT_SECRET` : Client Secret Twitch.

## Utilisation

### En tant que AWS Lambda

Le handler principal est situé dans `handler.py` (`igdb_enricher_handler`).

L'événement (`event`) passé à la Lambda peut contenir une limite optionnelle :

```json
{
  "limit": 50
}
```

Par défaut, la limite est fixée à `20` si non spécifiée.

### Exécution locale

Vous pouvez appeler `run_enricher` directement depuis `src/run.py`.

### IGDB backfill

Use the local PostgreSQL and Twitch settings to preview missing backgrounds for
matched games. The local runner requires a loopback PostgreSQL host.

```bash
PYTHONPATH=src python -m igdb_enricher.local_backfill backgrounds --game-ids 1001 1002
PYTHONPATH=src python -m igdb_enricher.local_backfill backgrounds --scan --limit 50
```

Add `--apply` to write the proposed backgrounds. Use `--after-game-id` to
resume a scan from the last reported cursor. Each batch reports recoverable
games, actual updates, games without a suitable image and IDs missing from IGDB.
Preview results include the proposed URLs.

Before deploying the regular enricher with a restricted PostgreSQL role, grant
it `SELECT (id, igdb_background_url, aws_background_url)` and
`UPDATE (igdb_background_url, aws_background_url)` on `igdb.game` if needed
for the guarded upsert. Keep its existing insert privileges.

## Structure du projet

- `handler.py` : Point d'entrée pour AWS Lambda.
- `src/igdb_enricher/run.py` : Logique principale de coordination.
- `src/igdb_enricher/candidate/` : Logique de recherche et de scoring des candidats IGDB.
- `src/igdb_enricher/igdb/` : Client API IGDB.
- `src/igdb_enricher/postgres/` : Gestion de la base de données.
