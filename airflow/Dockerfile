# Image Airflow 3 + dépendances du projet, installées AVEC le fichier de contraintes officiel
# d'Airflow pour ne casser aucune de ses dépendances internes.
FROM apache/airflow:3.4.0-python3.11

COPY requirements-airflow.txt /tmp/requirements-airflow.txt
RUN pip install --no-cache-dir "apache-airflow==3.4.0" -r /tmp/requirements-airflow.txt \
    --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.4.0/constraints-3.11.txt"
