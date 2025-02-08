### Comment configurer Docker pour le bot slack motorisé par une API RAG ?

Suivez pas à pas la procédure ci-après : 

1. **Créer une nouvelle app. Slack :**
   Regarder le fichier joint "*HOW_TO_CONFIG_SLACK_APP.md*". Sinon, suivre toutes les étapes directement depuis la vidéo : https://youtu.be/3jFXRNn2Bu8?si=UP6R-TT-btbHUbh-

2. **Créer le package "common_tools"** : (*préalable : pip install setuptools wheel build*)
   
   ```bash
   python -m build CommonTools
   ```
   
   ou :
   
   ```bash
   python setup.py bdist_wheel
   ```

3. **Copier le package "common_tools"** :
   
   - copier le fichier "*common_tools-0.x.x-py3-none-any.whl*" du dossier "*dist*" de l'API Slack, vers le dossier "*wheels*" de l'API RAG.
   
   - Vérifier dans `requirements_docker.txt` que la bonne version du package est spécifiée.

4. **Créer l'image docker de l'API RAG** :
   En admin., à la racine du projet, lancer le script:
   
   ```bash
   .\create_docker.bat
   ```
   
   Veillez que la variable 'repo_prefix' ait bien le nom de l'API concernée - Idem pour l'API Slack si besoin.

5. **Lancer les images docker "slack_api" et de votre "API RAG"** .
   Attention les 2 containers  doivent être sur le même network (interne à docker) pour pouvoir communiquer entre eux, et les ports à exposer lors de la création des containers doivent être spécifiés explicitement, tel que : 8301 et 8281.
   
   5.1. Créer un <u>network </u>commun
   
   ```bash
   docker network create my_network
   ```
   
   5.2. Créer le <u>container pour l'API Slack</u>
   
   ```bash
   docker run -d --name slack-api --network my_network -p 8301:8301 slack_api_0.14
   ```
   
      Où : 
   
   - 'slack-api' est le nom du container à créer, 
   
   - 'my_network' est le réseau docker partagé, 
   
   - '8301:8301' sont les ports d'entrée/sortie, 
   
   - 'slack_api_0.14' est le nom de l'image docker à partir de laquelle créer le container.
   
   5.3. Créer le <u>container pour l'API RAG</u>

```bash
docker run -d --name studi-website-rag-api --network my_network -p 8281:8281 rag_studi_public_website_api_0.10
```

      Où : 

- 'studi-website-rag-api' est le nom du container à créer, 

- 'my_network' est le réseau docker partagé, 

- '8281:8281' sont les ports d'entrée/sortie, 

- 'rag_studi_public_website_api_0.10' est le nom de l'image docker à partir de laquelle créer le container.
  
   5.4. Configuer l'URL à cibler dans l'API Slack
  
      Dans le fichier '.env', définir le nom 'docker' du container de l'API RAG et son port, comme :

```bash
EXTERNAL_API_HOST="studi-website-rag-api"
EXTERNAL_API_PORT="8281"
```

   5.5. <u>Tester</u> le bon fonctionnement
      Chaque API expose un endpoint "/ping" qui permet de test son bon fonctionnement, et renvoie "pong" en cas de réussite.
      De plus, l'API Slack expose un endpoint "/ping-api" qui appelle le endpoint "/ping" de l'API RAG, permettant de tester la chaine, et le bon fonctionnement de la communication entre containers des deux containters docker.

6. **Créer un tunnel ngrok** pour rendre l'API Slack visible depuis le web : 
   Dans une nouvelle fenêtre de commande, comme powershell:
   
   - authentification sur ngrok, si nécessaire (remplacer `<ngrok-token>` par votre token ngrok): 
   
   ```bash
   ngrok config add-authtoken <ngrok-token>
   ```
   
   -lancement de ngrok (par défaut l'API Slack est sur le port 8301) :
   
   ```bash
   ngrok http --url=slack1-studi.ngrok.io 8301
   ```
   
   <u>Nota :</u> commandes à executer depuis le dossier où est installé ngrok si besoin (actuellement inutile car ngrok.exe est dans `C:\Windows\System32`, qui est dans le PATH).

7. **Prévenir Slack de l'URL à informer** en cas d'évenements (si changement de URL ngrok)
   Renseigner l'URL externe ngrok affichée lors du lancement de ngrok sur la page: https://api.slack.com/apps/A08AYTSF9QF/event-subscriptions (où : A08AYTSF9QF l'id de l'app. slack).
   Cette URL ressemble à : "https://c07236f31f9e.ngrok.app/slack/events" (où "c07236f31f9e" est le sous-host généré par ngrok).
