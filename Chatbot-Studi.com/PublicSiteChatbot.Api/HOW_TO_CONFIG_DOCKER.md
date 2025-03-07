### Comment configurer Docker pour l'API RAG du chatbot du site Studi.com

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

4. **Créer l'image docker de l'API** :
   
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
   
   **5.2. Créer les <u>containers pour l'API</u>**
    Pour l'API **"studi website chatbot"** :

```bash
docker run -d --name studi-website-rag-api --network my_network -p 8281:8281 rag_studi_public_website_api_0.10
```

- 'studi-website-rag-api' est le nom du container à créer, 

- 'my_network' est le réseau docker partagé, 

- '8281:8281' sont les ports d'entrée/sortie, 

- 'rag_studi_public_website_xxx_0.10' est le nom de l'image docker à partir de laquelle créer le container.
  
  ---
  

   **5.3. <u>Tester</u> le bon fonctionnement**
      Chaque API expose un endpoint "/ping" qui permet de test son bon fonctionnement, et renvoie "pong" en cas de réussite.
      De plus, l'API Slack expose un endpoint "/ping-api" qui appelle le endpoint "/ping" de l'API RAG, permettant de tester la chaine, et le bon fonctionnement de la communication entre containers des deux containters docker.