### Comment configurer Docker pour le bot slack motorisé par une API RAG ?

Suivez pas à pas la procédure ci-après : 

1. **Créer une nouvelle app. Slack :**
   Regarder le fichier joint "*HOW_TO_CONFIG_SLACK_APP.md*". Sinon, suivre toutes les étapes directement depuis la vidéo : https://youtu.be/3jFXRNn2Bu8?si=UP6R-TT-btbHUbh-

2. **Créer le package "common_tools"** : (*préalable : pip install setuptools wheel build*)
   
   Incrémenter la version du package en modifiant la valeur de **version** dans le fichier  **setup.py** .
   
   Puis lancer la commande :

```bash
.\libs_build.bat
```

   ou (plus directement) :

```bash
rmdir /s /q common_tools.egg-info
python -m build CommonTools
```

3. **Copier le package "common_tools"** :
   
   - copier le fichier "*common_tools-0.x.x-py3-none-any.whl*" du dossier "*dist*" de l'API Slack, vers le dossier "*wheels*" de l'API RAG.
   
   - Vérifier dans `requirements_docker.txt` que la bonne version du package est spécifiée.

4. **Créer l'image docker de l'API RAG** :
   
   A la racine du projet, créer et configurer le fichier : **Dockerfile** et copier : **docker_create.bat** et **requirements_docker.txt** (avec la version correspondante de common_tools dans 'wheels'). Nota : aussi créer un **requirements_common.txt** et faire que **requirements.txt** appele ce dernier.
   
   Puis, en admin., à la racine du projet, lancer le script:
   
   ```bash
   .\docker_create.bat
   ```
   
   Veillez que la variable 'repo_prefix' ait bien le nom de l'API concernée - Idem pour l'API Slack si besoin.

5. **Créer vos containers à partir des images docker des APIs Slack et RAG** .
   Attention les 2 containers  doivent être sur le <u>même network</u> (interne à docker) pour pouvoir communiquer entre eux, et les ports à exposer lors de la création des containers doivent être spécifiés explicitement, tel que : 8301 et 8281.
   
   Pour ce faire, ne pas passer par Docker Desktop. Créer vos containers à partir des images en lançant directement les commandes (en <u>mode administrateur</u>) : 
   
   **5.1. Créer un <u>network</u> commun (inutile si le network a déjà été créé au préalable)**
   
   ```bash
   docker network create my_network
   ```
   
   **5.2. Créer le <u>container pour le connecteur Slack spécifique pour l'API cible</u>**
   
   Via un fichier de configuration des variables variables d'environnement, spécifique au projet cible :
   
   - Pour cibler **"studi-website-rag-api"** :   
     
     ```bash
     docker run -d --name slack-api-studi-website --network my_network -p 8302:8301 --env-file C:/Dev/squad-ai/SlackAPI/.env.studi-website twillio_proxy_api_0.10
     ```
   
   - Pour cibler **"code-doc-api"** :   
     
     ```bash
     docker run -d --name slack-api-code-doc --network my_network -p 8301:8301 --env-file C:/Dev/squad-ai/SlackAPI/.env.code-doc twillio_proxy_api_0.10
     ```
     
     Avec les paramètres suivants :
   
   - 'slack-api-code-doc' est le nom du container à créer,
   
   - 'my_network' est le réseau docker partagé, 
   
   - '8301:8301' sont les ports d'entrée/sortie, 
   
   - 'C:/Dev/squad-ai/SlackAPI/.env.code-doc' est le chemin d'accès au fichier de configuration des variables variables d'environnement, spécifique au projet cible.
   
   - 'twillio_proxy_api_0.10' est le nom de l'image docker à partir de laquelle créer le container.
     
     ---
   
   <u>Nota</u> : Alternativement, il est possible de specifier chaque valeur de variable d'environnement directement dans la commande de création du container, plutôt que spécifier un fichier contenant la configuration spécifique pour l'API cible.
   ATTENTION : les valeurs pour SLACK_BOT_TOKEN et SLACK_SIGNING_SECRET sont ici absentes, et doivent être renseignées avant de lancer la commande.
- Pour cibler **"code-doc-api"** :
  
  ```bash
  docker run -d --name slack-api-code-doc --network my_network -p 8301:8301 -e EXTERNAL_API_HOST="code-doc-api" -e EXTERNAL_API_PORT="8282" -e QUERY_EXTERNAL_ENDPOINT_URL_STREAMING="/rag/query/stream" -e STREAMING_RESPONSE=true -e SLACK_BOT_USER_ID="A08AYTSF9QF" -e SLACK_BOT_TOKEN="" -e SLACK_SIGNING_SECRET="" twillio_proxy_api_0.10
  ```

- Pour cibler **"studi-website-rag-api"** :
  
  ```bash
  docker run -d --name slack-api-studi-website --network my_network -p 8302:8301 -e EXTERNAL_API_HOST="studi-website-rag-api" -e EXTERNAL_API_PORT="8281" -e QUERY_EXTERNAL_ENDPOINT_URL_STREAMING="/rag/inference/no-conversation/ask-question/stream" -e STREAMING_RESPONSE=true -e SLACK_BOT_USER_ID="A08D1DE3GN5" -e SLACK_BOT_TOKEN="" -e SLACK_SIGNING_SECRET="" twillio_proxy_api_0.10
  ```

- Pour cibler **"studi-website-rag-backoffice-frontend"** :
  
  ```bash
  docker run -d --name slack-api-studi-website --network my_network -p 8302:8301 -e EXTERNAL_API_HOST="studi-website-rag-backoffice-frontend" -e EXTERNAL_API_PORT="8280" -e QUERY_EXTERNAL_ENDPOINT_URL_STREAMING="/rag/inference/no-conversation/ask-question/stream" -e STREAMING_RESPONSE=true -e SLACK_BOT_USER_ID="A08D1DE3GN5" -e SLACK_BOT_TOKEN="" -e SLACK_SIGNING_SECRET="" twillio_proxy_api_0.10
  ```
  
  Avec les paramètres suivants :   

- 'slack-api' est le nom du container à créer, 

- 'my_network' est le réseau docker partagé, 

- '8301:8301' sont les ports d'entrée/sortie, 

- Les variables d'environemment :
  
  - *EXTERNAL_API_HOST* :  le nom du container docker de l'API a ciblé pour sous-traiter les évenements reçus. Définit la variable d'environnement correspondante (override la valeur specifiée dans *Dockerfile* et *.env*).
  
  - *EXTERNAL_API_PORT* : le port du container docker de l'API a ciblé pour sous-traiter les évenements reçus (override la valeur specifiée *Dockerfile* et *.env*).
  
  - *QUERY_EXTERNAL_ENDPOINT_URL* : définit le endpoint de l'API RAG à appeller pour répondre à une demande provenant de slack, sans streaming de la réponse.
  
  - *QUERY_EXTERNAL_ENDPOINT_URL_STREAMING* : définit le endpoint de l'API RAG à appeller pour répondre à une demande provenant de slack, en streamant la réponse.
  
  - *STREAMING_RESPONSE* : définit si la réponse doit être ou non en streaming (vrai par défaut).
  
  - *SLACK_BOT_USER_ID* : définit l'identifiant de l'app Slack.
  
  - *SLACK_BOT_TOKEN* : le token pour s'identifier auprès de slack.
  
  - *SLACK_SIGNING_SECRET* : le secret pour signer les messages.

- 'twillio_proxy_api_0.10' est le nom de l'image docker à partir de laquelle créer le container.
  
  ---
  
   **5.3. Créer les <u>containers pour des API cibles</u>**
   Pour l'API **"studi website chatbot"** :

```bash
docker run -d --name studi-website-rag-api --network my_network -p 8281:8281 rag_studi_public_website_api_0.10
```

   Pour le frontend du backoffice de **"studi website chatbot"** :

```bash
docker run -d --name studi-website-rag-backoffice-frontend --network my_network -p 8280:8280 rag_studi_public_website_backoffice_frontend_0.10
```

        Pour l'API **"code doc"** :

```bash
docker run -d --name code-doc-api --network my_network -p 8282:8282 code_doc_api_0.10
```

Où :

- 'studi-website-rag-api' est le nom du container à créer, 

- 'my_network' est le réseau docker partagé, 

- '8281:8281' sont les ports d'entrée/sortie, 

- 'rag_studi_public_website_api_0.10' est le nom de l'image docker à partir de laquelle créer le container.
  
  ---
  
  **5.4. Configuer l'URL de l'API RAG à cibler par l'API Slack**
  
  Dans le fichier '*Dockerfile*', définir le nom 'docker' du container de l'API RAG et son port, comme :

```bash
EXTERNAL_API_HOST="studi-website-rag-api"
EXTERNAL_API_PORT="8281"
```

   **5.5. <u>Tester</u> le bon fonctionnement**
      Chaque API expose un endpoint "/ping" qui permet de test son bon fonctionnement, et renvoie "pong" en cas de réussite.
      De plus, l'API Slack expose un endpoint "/ping-api" qui appelle le endpoint "/ping" de l'API RAG, permettant de tester la chaine, et le bon fonctionnement de la communication entre containers des deux containters docker.



6. **Créer un tunnel ngrok pour rendre l'API Slack visible depuis le web :** 
   
   
   => Soit <u>automatiquement</u>, si le fichier **ngrok.yml** dans "`C:\Users\aze\AppData\Local\ngrok`" definit déjà l'authentification, ainsi que les tunnels à ouvrir. Il vous suffit alors de lancer la commande :
   
   ```bash
   ngrok start --all
   ```
   
   => Soit <u>manuellement</u>, vous pouvez procéder à l'authentification, puis à l'ouverture des tunnels ngrok souhaités:
   
   Dans une nouvelle fenêtre de commande (comme powershell) :
   
   - Authentification à ngrok (si nécessaire) : 
   
   ```bash
   ngrok config add-authtoken <ngrok-token>
   ```
   
           *remplacer `<ngrok-token>` par votre token ngrok*
   
   
   
   - Ouverture d'un tunnel ngrok pour **CodeDoc** :
   
   ```bash
   ngrok http --url=code-doc.slack.studi.ngrok.app 8301
   ```
   
   - Ouverture d'un tunnel ngrok pour**StudiPublicWebsite** : 

```bash
ngrok http --url=public-website.slack.studi.ngrok.app 8302
```

   <u>Nota</u> : Commandes à executer depuis un dossier où ngrok est accessible (actuellement ok car *ngrok.exe* est dans `C:\Windows\System32`, qui est dans le PATH).

7. **Prévenir Slack de l'URL à informer en cas d'évenements** (si changement de URL ngrok)
   Renseigner l'URL externe ngrok affichée lors du lancement de ngrok sur la page: https://api.slack.com/apps/A08AYTSF9QF/event-subscriptions (où : A08AYTSF9QF l'id de l'app. slack).
   Cette URL ressemble à : "https://c07236f31f9e.ngrok.app/slack/events" (où "c07236f31f9e" est le sous-host généré par ngrok).
