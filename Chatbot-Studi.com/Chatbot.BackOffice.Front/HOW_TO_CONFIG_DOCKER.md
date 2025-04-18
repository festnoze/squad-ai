### Comment configurer Docker pour le frontend Streamlit du backoffice de l'API RAG du chatbot du site Studi.com

Suivez pas à pas la procédure ci-après : 

1. **Créer le package "common_tools"** : (*préalable : pip install setuptools wheel build*)

2. Incrémenter la version du package en modifiant la valeur de **version** dans le fichier  **setup.py** .
   
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
   
   - copier le fichier "*common_tools-0.x.x-py3-none-any.whl*" du dossier "*dist*"  de common_tools, vers le dossier "*wheels*" du front.
   
   - Vérifier dans `requirements_docker.txt` que la bonne version du package est spécifiée.

4. **Créer l'image docker du frontend backoffice** :
   
   A la racine du projet, créer et configurer le fichier : **Dockerfile** et copier : **docker_create.bat** et **requirements_docker.txt** (avec la version correspondante de common_tools dans 'wheels'). Nota : aussi créer un **requirements_common.txt** et faire que **requirements.txt** appele ce dernier.
   
   Puis, en admin., à la racine du projet, lancer le script:
   
   ```bash
   .\docker_create.bat
   ```
   
   Veillez que la variable 'repo_prefix' ait bien le nom de l'API concernée - Idem pour l'API Slack si besoin.

5. **Créer vos containers à partir des images docker de l'API et du frontend** .
   Attention les 2 containers  doivent être sur le <u>même network</u> (interne à docker) pour pouvoir communiquer entre eux, et les ports à exposer lors de la création des containers doivent être spécifiés explicitement, tel que : 8301 et 8281.
   
   Pour ce faire, ne pas passer par Docker Desktop. Créer vos containers à partir des images en lançant directement les commandes (en <u>mode administrateur</u>) : 
   
   **5.1. Créer un <u>network</u> commun (inutile si le network a déjà été créé au préalable)**
   
   ```bash
   docker network create my_network
   ```
   
   **5.2. Créer les <u>containers pour l'API et le frontend</u>**
    Pour l'API **"studi website chatbot"** :

```bash
docker run -d --name studi-website-rag-api --network my_network -p 8281:8281 rag_studi_public_website_api_0.10
```

   Pour le frontend du backoffice de **"studi website chatbot"** :

```bash
docker run -d --name studi-website-rag-backoffice-frontend --network my_network -p 8280:8280 -e HTTP_SCHEMA="http" -e EXTERNAL_API_HOST="studi-website-rag-api" -e EXTERNAL_API_PORT="8281" rag_studi_public_website_backoffice_frontend_0.10
```

       

- 'studi-website-rag-api' est le nom du container à créer, 

- 'my_network' est le réseau docker partagé, 

- '8281:8281' sont les ports d'entrée/sortie, 

- 'rag_studi_public_website_xxx_0.10' est le nom de l'image docker à partir de laquelle créer le container.
  
  ---
  
  **5.3. Configuer l'URL de l'API RAG à cibler par l'API Slack**
  
  Dans le fichier '*Dockerfile*', définir le nom 'docker' du container de l'API RAG et son port, comme :

```bash
EXTERNAL_API_HOST="studi-website-rag-api"
EXTERNAL_API_PORT="8281"
```

   **5.4. <u>Tester</u> le bon fonctionnement**
      Chaque API expose un endpoint "/ping" qui permet de test son bon fonctionnement, et renvoie "pong" en cas de réussite.
      De plus, l'API Slack expose un endpoint "/ping-api" qui appelle le endpoint "/ping" de l'API RAG, permettant de tester la chaine, et le bon fonctionnement de la communication entre containers des deux containters docker.

6. **Créer un tunnel ngrok pour rendre l'API Slack visible depuis le web :** 
   Dans une nouvelle fenêtre de commande, comme powershell:
   
   - authentification sur ngrok, si nécessaire (remplacer `<ngrok-token>` par votre token ngrok): 
   
   ```bash
   ngrok config add-authtoken <ngrok-token>
   ```
   
   -lancement de ngrok :
   Pour **CodeDoc** :
   
   ```bash
   ngrok http --url=code-doc.slack.studi.ngrok.app 8301
   ```
   
   Pour **StudiPublicWebsite** : 

```bash
ngrok http --url=public-website.slack.studi.ngrok.app 8302
```

   <u>Nota :</u> commandes à executer depuis le dossier où est installé ngrok si besoin (actuellement inutile car ngrok.exe est dans `C:\Windows\System32`, qui est dans le PATH).
