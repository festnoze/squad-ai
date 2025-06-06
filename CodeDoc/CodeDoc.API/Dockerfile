# Utilise l'image Python 3.12.1-slim comme base
FROM python:3.12.1-slim

# Définit le répertoire de travail à la racine du container
WORKDIR /

# Définit le chemin par défaut pour Python dans le container
ENV PYTHONPATH=/src

# Définit le port d'écoute de l'application
ENV PORT=8282

# Définit l'adresse d'écoute de l'application
ENV HOST_URI=0.0.0.0

# Copie les packages wheel précompilés dans le container
COPY wheels/ /wheels/

# Copie le fichier des dépendances communes (non utilisé pour l'installation ici)
COPY requirements_common.txt .

# Options d'installation alternatives (non activées)
# RUN pip install /wheels/*.whl
# RUN pip install --no-cache-dir -r requirements_common.txt

# Copie et installe les fichiers de dépendances spécifiques pour Docker
COPY requirements.txt .
COPY requirements_docker.txt .
RUN pip install --no-cache-dir -r requirements_docker.txt

# Copie l'intégralité du projet dans le container
COPY . .

# Nettoie le répertoire outputs des données existantes
RUN rm -rf /outputs/logs/{*,.*}

# Expose le port défini pour permettre l'accès externe à l'application
EXPOSE $PORT

# Démarre l'application via Uvicorn avec les paramètres spécifiés
CMD ["sh", "-c", "python -m uvicorn src.api.startup:app --host $HOST_URI --port $PORT --log-level error"]
