# Raccordement Linux, jalon vertical et admission finale

État : IN_PROGRESS, pas de qualification globale du produit.

- `junit.xml` : 87 PASS, 2 SKIP, 8,97 s. Les skips sont les sondes réelles explicitement opt-in (CLI Claude et Docker), pas des contrats produit admis.
- `full-regression-initial.xml` : 1 998 PASS, 59 FAIL, 41 SKIP, 5 127,78 s. Échecs conservés pour contrôle de migration, aucun résultat vert global revendiqué.
- Les canaris sans preuve native, les tests seulement planifiés et les rapports de couverture absents ne donnent plus de GREEN.
- Le socle est vérifié avant le développement ; les checkers natifs sont lisibles mais non modifiables par le broker.
- Le jalon vertical exige des preuves navigateur/API/DB liées au contrat et au snapshot. Un simple healthcheck, une preuve V manquante ou un graphe réadmis incomplet bloque les descendants.
- La livraison finale appelle le vérificateur indépendant ; le code source changé, une preuve externe altérée, un critère mandatory non vérifié ou un pack indisponible bloque `delivery_ready`.
- Lancement/arrêt preview : ressources isolées possédées, disponibilité HTTP exigée, retrait du flag running à la sortie, autorité de nettoyage conservée en cas d'erreur.
- Contre-revue Windows : refus des alias NTFS 8.3, en complément des liens/jonctions/hardlinks et de la validation de l'ensemble d'un batch avant écriture.

Limites : les preuves ci-dessus qualifient des raccordements de la fabrique et leurs contre-exemples, pas les 57 critères du nouveau projet. Les ports du coordinateur et les scénarios navigateur complets restent en intégration. Les tests historiques de shell hôte sont migrés vers les interfaces isolées ; la régression finale doit être rejouée après cette migration.
