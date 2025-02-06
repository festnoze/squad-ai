# Comment Configurer une Application Slack avec Bot et abonnements aux événements

Ce guide explique, étape par étape, comment créer une application Slack, ajouter un bot utilisateur et configurer les abonnements aux événements (généré par IA). 

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

- Dans les paramètres de votre application, faites défiler jusqu'à la section **Bot Users**.
- Ajoutez un bot utilisateur et attribuez-lui un nom d'affichage.
- Optionnellement, définissez un avatar et une couleur pour votre bot.
- Enregistrez les modifications.

### 1.4 Configurer OAuth & Permissions

- Accédez à **OAuth & Permissions** dans les paramètres de votre application.
- Dans la section **Scopes**, ajoutez les scopes de Bot Token suivants :
  - `app_mentions:read`
  - `chat:write`
  - `channels:history`
- Cliquez sur **Install App to Workspace** et approuvez les autorisations.
- Copiez le **Bot User OAuth Token** pour une utilisation ultérieure.

---

## 2. Exigence de l'Endpoint Backend

Votre backend doit exposer un endpoint `/slack/events` pour recevoir et traiter les événements envoyés par Slack. Cet endpoint est nécessaire pour que Slack puisse transmettre les événements (par exemple, les mentions d'application) à votre application.

---

## 3. Exposer Votre Serveur Local

Si vous développez en local, utilisez un outil comme [ngrok](https://ngrok.com/) pour exposer votre serveur local sur Internet :

1. Démarrez votre serveur backend sur le port 8301.

2. Dans une nouvelle fenêtre de commande, exécutez :
   
   ```bash
   ngrok http --url=slack1-studi.ngrok.io 8301
   ```

---

## 4. Renseigner Slack de l'URL abonnée aux évenements

Renseigner l'URL externe ngrok affichée lors du lancement de ngrok sur la page: https://api.slack.com/apps/A08AYTSF9QF/event-subscriptions (où : A08AYTSF9QF l'id de l'app. slack).
Cette URL ressemble à : "https://c07236f31f9e.ngrok.app/slack/events" (où "c07236f31f9e" est le sous-host généré par ngrok).
