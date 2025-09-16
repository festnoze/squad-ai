# Déploiement GCP (Google Cloud Platform)

Ce document décrit la procédure de déploiement de l'application **PIC Prospect Incoming Callbot** sur Google Cloud Platform.

## Prérequis

- Docker installé et configuré
- Google Cloud SDK (gcloud) installé
- Fichier de credentials de service account : `secrets/google-credentials-for-GCP-deploiement.json`
- Droits administrateur sur le projet GCP

## Déploiement Automatique

Pour déployer l'application, utilisez le script de déploiement :

```bash
.\docker_gcp_deploy.bat
```

### Déploiement Partiel

Il est possible de commencer le processus à partir d'une étape spécifique en passant le numéro d'étape en paramètre :

```bash
# Commencer à partir de l'étape 5 (build de l'image)
.\docker_gcp_deploy.bat 5

# Commencer à partir de l'étape 7 (déploiement sur Cloud Run)
.\docker_gcp_deploy.bat 7
```

## Étapes du Processus de Déploiement

Le script `docker_gcp_deploy.bat` exécute les étapes suivantes :

### 1. Activation du Service Account
```bash
gcloud auth activate-service-account --key-file=secrets/google-credentials-for-GCP-deploiement.json
```
- Active l'authentification avec le service account configuré
- Utilise les credentials stockés dans le fichier `secrets/google-credentials-for-GCP-deploiement.json`

### 2. Activation de l'API Cloud Resource Manager
```bash
gcloud services enable cloudresourcemanager.googleapis.com --project=studi-com-rag-api --quiet
```
- Active l'API Cloud Resource Manager nécessaire pour la gestion des ressources
- Silencieuse avec l'option `--quiet`

### 3. Configuration du Projet
```bash
gcloud config set project studi-com-rag-api --quiet
```
- Définit le projet GCP actuel : `studi-com-rag-api`
- Configure le contexte gcloud pour ce projet

### 4. Configuration de Docker pour Artifact Registry
```bash
gcloud auth configure-docker europe-west1-docker.pkg.dev --quiet
```
- Configure Docker pour s'authentifier auprès d'Artifact Registry
- Région utilisée : `europe-west1`

### 5. Construction de l'Image Docker
```bash
docker build -f Dockerfile -t europe-west1-docker.pkg.dev/studi-com-rag-api/depot-docker/prospect-incoming-callbot .
```
- Construit l'image Docker à partir du Dockerfile
- Taggue l'image avec l'URL complète d'Artifact Registry
- Image finale : `prospect-incoming-callbot`

### 6. Push vers Artifact Registry
```bash
docker push europe-west1-docker.pkg.dev/studi-com-rag-api/depot-docker/prospect-incoming-callbot
```
- Pousse l'image construite vers le registry Docker de GCP
- Stockage dans le repository `depot-docker`

### 7. Déploiement sur Cloud Run
```bash
gcloud run deploy prospect-incoming-callbot --image europe-west1-docker.pkg.dev/studi-com-rag-api/depot-docker/prospect-incoming-callbot --platform managed --region europe-west1 --allow-unauthenticated --port 8080
```
- Déploie le service sur Cloud Run
- Configuration :
  - **Nom du service** : `prospect-incoming-callbot`
  - **Plateforme** : `managed` (entièrement géré par Google)
  - **Région** : `europe-west1`
  - **Accès** : `--allow-unauthenticated` (accès public)
  - **Port** : `8080`

## Configuration du Projet

Le script utilise les variables suivantes :

| Variable | Valeur | Description |
|----------|---------|-------------|
| `PROJECT_ID` | `studi-com-rag-api` | Identifiant du projet GCP |
| `REGION` | `europe-west1` | Région de déploiement |
| `REPO` | `depot-docker` | Nom du repository Artifact Registry |
| `IMAGE_NAME` | `prospect-incoming-callbot` | Nom de l'image et du service |

## Étapes Optionnelles

Le script inclut également des étapes optionnelles pour la gestion post-déploiement :

- **Étape 8** : Affiche les détails du service déployé
- **Étape 9** : Récupère l'URL publique du service
- **Étape 10** : Affiche les logs du service
- **Étape 11** : Supprime l'image locale pour libérer l'espace disque

## Gestion des Erreurs

Le script s'arrête automatiquement en cas d'erreur (`if errorlevel 1 pause`) permettant de :
- Identifier l'étape qui a échoué
- Corriger le problème
- Reprendre le déploiement à partir de cette étape

## Accès au Service Déployé

Une fois le déploiement terminé, le service est accessible via l'URL fournie par Cloud Run, généralement sous la forme :
```
https://prospect-incoming-callbot-[hash]-ew.a.run.app
```

## Sécurité

- Les credentials de service account sont stockés dans `secrets/` (non commités)
- Le service est configuré en accès public (`--allow-unauthenticated`)
- La région `europe-west1` assure la conformité RGPD