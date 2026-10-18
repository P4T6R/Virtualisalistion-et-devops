# Contrat HTTP et d'exploitation

GET /info renvoie en JSON le nom du serveur et la version.

GET /sante renvoie 200 uniquement si une base accessible en écriture accepte
SELECT 1, sinon 503.

GET /resultat?matricule=000001 renvoie le matricule, le nom, la série, la
moyenne et l'admission. Un identifiant mal formé renvoie 400, un candidat absent
404 et une base indisponible 503 lors d'une absence en cache.

Une entrée Redis peut être ancienne de trente secondes. /sante contourne
toujours Redis. Une panne Redis renvoie automatiquement les lectures vers
PostgreSQL.

Seules les connexions privées authentifiées atteignent PostgreSQL et Redis. La
promotion exige que bdd1 soit réellement arrêtée. bdd1 doit rester arrêtée après
la promotion ; la reconstruction complète du laboratoire est la procédure de
retour. La réplication asynchrone peut perdre une écriture récente qui n'a pas
encore atteint bdd2.
