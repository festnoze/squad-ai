# Comment Configurer une Application Slack avec Bot et abonnements aux événements

Ce guide (généré par IA) explique, étape par étape, comment créer une application Slack, ajouter un bot utilisateur et configurer les abonnements aux événements. 

Vous pouvez aussi directement suivre toutes les étapes depuis la vidéo : https://youtu.be/3jFXRNn2Bu8?si=UP6R-TT-btbHUbh-

---

## 1. Configuration de l'Application Slack

### 1.1 Créer un Compte Slack et un Espace de Travail

- Inscrivez-vous sur [Slack](https://slack.com/) si vous n'avez pas encore de compte.
- Créez un nouvel espace de travail (par exemple, "Expériences IA").

### 1.2 Créer une Nouvelle Application Slack

- Rendez-vous sur [Slack API Apps](https://api.slack.com/apps).
- Cliquez sur **Create New App** et choisissez **From scratch**.
- Donnez un nom à votre application (par exemple, "SlackBot") et sélectionnez votre espace de travail.

### 1.3 Configurer le Bot Utilisateur

- Dans les paramètres de votre application, faites défiler jusqu'à la section **Display Information**.
- Attribuez lui un nom d'utilisateur,.
- Optionnellement, définissez un avatar et une couleur pour votre bot.
- <u>Enregistrez</u> les modifications.

### 1.4 Configurer OAuth & Permissions

- Accédez à **OAuth & Permissions** dans les paramètres de votre application.
- Dans la section **Scopes**, ajoutez les scopes de Bot Token suivants :
  - `app_mentions:read`
  - `chat:write`
  - `channels:history`
  - `commands`
- Cliquez sur **Install App to Workspace** et approuvez les autorisations.
- Copiez le **Bot User OAuth Token** pour une utilisation ultérieure.

---

## 2. Exigence de l'Endpoint Backend

Votre backend doit exposer un endpoint `/slack/events` pour recevoir et traiter les événements envoyés par Slack. Cet endpoint est nécessaire pour que Slack puisse transmettre les événements (par exemple, les mentions d'application) à votre application.

---

## 3. Exposer Votre Serveur Local

Si vous développez en local, utilisez un outil comme [ngrok](https://ngrok.com/) pour exposer votre serveur local sur Internet :

1. Démarrez votre serveur backend sur le port XXX.

2. Dans une nouvelle fenêtre de commande, exécutez :
   
   Pour le projet **CodeDoc** :
   
   ```bash
   ngrok http --url=code-doc.slack.studi.ngrok.app 8301
   ```

        Ou pour le projet **StudiPublicWebsite** : 

```bash
ngrok http --url=public-website.slack.studi.ngrok.app 8302
```

---

## 4. Renseigner les infos de l'app Slack dans l'API Slack

Dans le fichier .env de l'API Slack (ou dans la commande pour la création du container à partir de l'image docker), définir les valeurs suivantes : 

- **SLACK_BOT_USER_ID** : Accessible directement depuis l'URL, après le : api.slack.com/apps/ ou en appelant le endpoint : *"/bot_user_id"* depuis l'API Slack.

- **SLACK_BOT_TOKEN** : depuis *api.slack.com/apps*, dans "OAuth & Permissions" et "### OAuth Tokens", cliquer sur le bouton pour générer, commence par "*xoxb-*". 

- **SLACK_SIGNING_SECRET** : depuis *api.slack.com/apps*, dans "Basic Information" et "App Credentials", copier la valeur de : "Client Secret".

## 5. Abonnement de l'API aux évenements Slack

Dans *api.slack.com/apps*, dans "Event Subscriptions, renseigner l'URL externe ngrok affichée lors du lancement de ngrok sur la page: https://api.slack.com/apps/YYY/event-subscriptions (où : YYY est l'id de l'app. slack).
Cette URL ressemble à : "https://xxx.ngrok.io/slack/events" (où "xxx" est le sous-host généré par ngrok). 
<u>Troubleshooting :</u> L'URL fournie est validée à la volée. En cas de problème, vérifier l'URL avec postman et les 3 variables user_id, signing secret, et token slack.

- Pour le projet **CodeDoc**, l'URL ngrok :

```bash
https://code-doc.slack.studi.ngrok.app/slack/events
```

- Pour le projet **StudiWebsite** :

```bash
https://public-website.slack.studi.ngrok.app/slack/events
```

## 6. Donner les droits d'accès aux évenements Slack ciblés

Toujours dans *api.slack.com/apps*, et "*Event Subscriptions*", dans la partie "*Subscribe to bot events*", ajouter l'évenement : "message.im" (permet l'appel d'URL en cas de message direct au bot).

Finir par sauvegarder, puis réinstaller l'app.

<u>Troubleshooting :</u> Si il n'est pas possible d'envoyer de message au bot depuis Slack : 

- Aller dans "App Home", puis activer "**Always Show My Bot as Online**" ou dans "App manifest" changer la valeur pour always_online: true (dans la section : features/bot_user). 

- Aller dans "App Home", puis dans "Show Tabs", activer "**Messages Tab**", et cocher en dessous : "Allow users to send Slash commands and messages from the messages tab". 

- Supprimer et remettre les droits OAuth + du bot.

- Réinstaller l'app.