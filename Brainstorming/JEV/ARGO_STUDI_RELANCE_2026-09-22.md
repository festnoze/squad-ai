# Relance manuelle Studi via Argo CD

Le 22 septembre 2026, via l'onglet Brave existant de dev-argocd.studi.network.

- Application : skillforge-cron-job.
- Namespace : skillforge-application-studi.
- CronJob : backend-cronjob-ingestion-opale-studi.
- Manifestes souhaité et live vérifiés : image skillforge-backend:2555, imagePullPolicy: Always.
- CronJob synchronisé et suspendu. Suspension conservée ; action manuelle Create Job uniquement.
- Nouveau job : backend-cronjob-ingestion-opale-studi-2609221954.
- Nouveau pod : backend-cronjob-ingestion-opale-studi-2609221954-hssp9.
- Création : 2026-09-22 21:54:49 Europe/Paris.
- Image du nouveau pod confirmée : 2555.
- Ingestion : 7622d088-68b9-481b-819d-06e6f152f992.

## Résultat observé

Le pod est passé de Running à Error. Les logs finaux indiquent une ingestion `partial` : Opale `completed`, PDF `completed`, Parcours `failed`.

```text
Parcours pipeline failed: Configured reporting parcours are absent from the LMS hierarchy snapshot: [2926]
```

Deux contenus PDF/fallback ont également échoué, signalés comme avertissement. Le rapport mentionne une mise à jour de contenu.

Le cron déclenche et suit l'ingestion via le service backend-service-studi, dans le même namespace. Le tag de l'image du cron ne prouve pas celui des pods derrière ce service. La version de ce backend n'a pas été vérifiée lors de cette relance.

Aucune modification du template, aucune reprise des exécutions planifiées, aucune action sur les autres écoles. Aucune suppression manuelle effectuée à ce stade. Le job ancien suffixé 2609221616 a disparu de l'arbre après la nouvelle exécution, sans action de suppression de notre part ; la cause exacte de ce retrait n'a pas été vérifiée.

## Diagnostic complémentaire : backend épinglé par digest

Inspection ultérieure en lecture seule, dans la même session Brave/Argo CD :

- L'application backend réelle est `argocd/skillforge-backend`, chemin chart `apps/backend` (et non `skillforge-applications` proposé dans l'analyse tierce).
- Le manifeste souhaité de `backend-deploy-studi` spécifie `prazgcontreg1ai-h6aghneweuc7d4gf.azurecr.io/skillforge-backend@sha256:d056aa74682320e7ce59abebb4afd8a8fc862b50d40f4e498e926a3730984a2c`.
- Les deux pods Studi `backend-deploy-studi-575f7ffbff-cvw88` et `backend-deploy-studi-575f7ffbff-qd2rx` apparaissent sous ce ReplicaSet et sous le Deployment géré par Argo CD. Ils affichent tous deux cette image par digest et sont Running/Ready.
- Le statut `containerStatuses.imageID` du pod `cvw88` confirme le digest `d056aa74682320e7ce59abebb4afd8a8fc862b50d40f4e498e926a3730984a2c`. Ce conteneur a démarré le 22 septembre à 17:00:36 UTC.
- Le pod Academee `backend-deploy-academee-8668f846b6-2k47s` spécifie le tag `2555`, et son `containerStatuses.imageID` est `sha256:c53071cfc90cf0dad1aba518bfa07e733aff059da27e249dd55e1ad5b54ff66c`.
- Argo CD affiche l'application Synced/Healthy, avec auto-sync et self-heal activés.

Sources de l'application vérifiées dans son UI :

1. `git@ssh.dev.azure.com:v3/studi-ai/DevOps/DevOps`, branche `feature/ADEV-2279-add-lti-app-and-change-argocd-workflow-with-app-to-apps`, chemin `apps/backend`.
2. `git@ssh.dev.azure.com:v3/studi-ai/Skillforge/skillforge-env`, branche `main`, référence `values`.

Ordre des fichiers de valeurs affiché : `$values/dev/values-dev.yaml`, `$values/dev/values-dev-backend.yaml`, `values.yaml`, `values-dev.yaml`.

Conclusion : un épinglage spécifique est effectivement présent dans le rendu souhaité pour Studi, et l'image exécutée diffère de celle du pod de référence en 2555. Une relance des seuls jobs ou pods ne corrige pas cet état souhaité. Le fichier et la clé exacts à l'origine de l'épinglage restent à localiser : rechercher le digest complet dans les deux dépôts, puis examiner les valeurs et le template d'image. Ne pas inventer une clé `schools.studi.image.tag` sans vérifier le chart.

L'absence de champs dans les runs et le message historique confortent le diagnostic, mais ne prouvent pas à eux seuls une date précise du code ni le tag historique 2063. L'historique Git et l'origine de l'ancien digest n'ont pas été vérifiés ici. Les EndpointSlices n'ont pas été inspectées ; l'absence de tout pod orphelin dans le namespace n'est donc pas établie.

## Relance correcte proposée

1. Corriger dans Git l'image spécifique du backend Studi vers 2555, de préférence son digest vérifié dans le registre. Le digest observé sur Academee fournit une référence de comparaison, à confirmer avec le build/registre.
2. Vérifier que le manifeste souhaité de `backend-deploy-studi` change bien et que les autres écoles restent inchangées, puis synchroniser ce Deployment de façon ciblée.
3. Attendre les deux réplicas Ready sur la nouvelle image ; vérifier leurs imageID et les EndpointSlices de `backend-service-studi` pour exclure d'anciens backends encore sélectionnés.
4. Vérifier qu'aucune ingestion Studi n'est en cours, puis effectuer Create Job sur `backend-cronjob-ingestion-opale-studi`, toujours en 2555 et sans lever la suspension du CronJob.
5. Contrôler les nouvelles métadonnées et les statuts de chaque phase. L'alignement d'image corrige la divergence identifiée, mais ne garantit pas l'absence d'autres erreurs de données.

Aucune modification ni nouvelle exécution effectuée lors de cette analyse complémentaire.

## Identification du digest Studi — preuve Azure Pipelines

Le digest `sha256:d056aa74682320e7ce59abebb4afd8a8fc862b50d40f4e498e926a3730984a2c` correspond au tag **2057**.

Preuve lue dans le build 2057 du 9 septembre 2026, étape « Push immutable and branch Docker tags to ACR » :

```text
2057: digest: sha256:d056aa74682320e7ce59abebb4afd8a8fc862b50d40f4e498e926a3730984a2c size: 4099
```

Journal : https://dev.azure.com/studi-ai/Skillforge/_build/results?buildId=2057&view=logs&j=5adddc6d-2f0c-545e-ee30-b70acd48d6dc&t=f6dedfcd-f613-52d8-35d1-8118dfae3dc2

Origine exacte de l'épinglage : dépôt DevOps, `apps/backend/templates/backend-deployment.yml`, ligne 40, commit `ae31dd72235a0d1cb81ae98bc602ebe46b434edc` du 9 septembre 2026, intitulé « chore(dev): run Studi backend 2057 with explicit migration control ».

Le modèle définit `$recetteStudi` lorsque environment=dev, cluster=de-azg-kubcluster1-ai et school=studi. Dans ce cas, l'image utilise le digest ci-dessus, sinon le tag global backend.image.tag. Ce mécanisme explique pourquoi Studi reste sur 2057 malgré la valeur globale 2555.

Commit : https://dev.azure.com/studi-ai/DevOps/_git/DevOps/commit/ae31dd72235a0d1cb81ae98bc602ebe46b434edc?path=/apps/backend/templates/backend-deployment.yml

Aucune configuration modifiée pendant cette identification.
