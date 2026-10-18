# Modélisation

resultats(matricule TEXT PRIMARY KEY, nom TEXT NOT NULL, serie TEXT NOT NULL,
moyenne NUMERIC(4,2) NOT NULL, admis BOOLEAN NOT NULL)

Les clés vont de 000001 à 050000 et toutes les données sont fictives.

Cycle d'une VM :

absente → créée → provisionnée → active → arrêtée → détruite

Cycle de la base :

bdd1 en écriture et bdd2 en récupération → bdd1 arrêtée → bdd2 promue

L'ancienne base principale ne doit pas redémarrer après promotion.

Cycle d'un déploiement :

prêt → drainage → zéro session → maintenance → redémarrage → santé directe → prêt

Une erreur laisse le serveur désactivé et arrête le déploiement.

L'inventaire JSON et le nombre d'applications doivent rester cohérents. Après
l'extension, NB_APP=4 doit être conservé dans .env. Une réduction du nombre
ne détruit pas automatiquement les anciennes VM.
