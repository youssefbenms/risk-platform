# Risk Platform — projet fil rouge Data Engineer (gestion des risques financiers)

Plateforme qui collecte des données financières (cours Stooq, taux BCE, transactions carte,
communiqués BCE), les stocke (PostgreSQL + MongoDB), contrôle leur qualité, calcule des
indicateurs de risque (VaR, volatilité, anomalies) et expose un modèle de détection de fraude
via une API sécurisée, le tout orchestré par Airflow et supervisé par Prometheus/Grafana.

## Démarrage rapide (Windows, PowerShell)

```powershell
py -3.11 -m venv .venv ; .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
Copy-Item .env.example .env        # puis remplir .env
pytest                              # 22 tests verts attendus
docker compose up -d --build        # bases + API + Airflow + monitoring
docker compose run --rm jobs python -m src.etl.pipeline
docker compose run --rm jobs python -m src.ml.fraud_train --source db
docker compose restart api
.\scripts\smoke_test.ps1
```

| Service | URL |
| --- | --- |
| API (Swagger) | http://localhost:8000/docs |
| Airflow | http://localhost:8080 |
| Grafana | http://localhost:3000 |
| Prometheus | http://localhost:9090 |

## Arborescence

```
src/collect     extraction (Stooq, BCE, Kaggle, RSS + scraping)
src/transform   nettoyage, normalisation, contrôles qualité
src/db          schéma SQL, accès PostgreSQL et MongoDB
src/etl         orchestration des étapes, journal d'exécution
src/ml          modèle de fraude (supervisé), risque de marché (VaR + Isolation Forest)
src/api         API FastAPI sécurisée par clé
airflow/        image et DAGs Airflow 3
monitoring/     Prometheus + Grafana (datasources et tableau de bord provisionnés)
k8s/            déploiement Kubernetes (Deployment, Service, HPA)
infra/          init PostgreSQL, Terraform (bonus)
tests/          tests unitaires et d'intégration (SQLite + mongomock)
```
