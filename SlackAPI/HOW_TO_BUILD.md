### Comment configurer un bot slack motorisé par une API RAG ?

Suivez pas à pas la procédure ci-après : 

1. **Créer une nouvelle app. Slack :**
   Regarder le fichier "*HOW_TO_CONFIG.md*". Sinon, suivre toutes les étapes directement depuis la vidéo : https://youtu.be/3jFXRNn2Bu8?si=UP6R-TT-btbHUbh-

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

5. **Lancer les images docker "slack_api" et de votre "API RAG"** . Attention à spécifier explicitement les ports à exposer lors du run, tel que : 8301 et 8281.

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

7. **Prévenir Slack de l'URL à informer** en cas d'évenements
   Renseigner l'URL externe ngrok affichée lors du lancement de ngrok sur la page: https://api.slack.com/apps/A08AYTSF9QF/event-subscriptions (où : A08AYTSF9QF l'id de l'app. slack).
   Cette URL ressemble à : "https://c07236f31f9e.ngrok.app/slack/events" (où "c07236f31f9e" est le sous-host généré par ngrok).
