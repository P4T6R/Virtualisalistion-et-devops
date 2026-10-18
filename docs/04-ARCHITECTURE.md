# Décision d'architecture

Le trafic suit le chemin suivant :

127.0.0.1:8080 → lb1 HAProxy → app1..N Flask/Gunicorn → bdd1 PostgreSQL

bdd2 reçoit la réplication de bdd1. Après une promotion explicite, les
applications emploient la sélection multi-hôte en lecture-écriture de libpq pour
utiliser bdd2. Redis se trouve sur lb1 et écoute uniquement sur le réseau privé
avec authentification.

Toutes les VM utilisent l'image fixée bento/ubuntu-24.04. Un inventaire Ruby
unique construit les VM et produit le JSON consommé par le provisionnement. lb1
est traité en dernier et régénère sa configuration à chaque démarrage.

Le socle consomme 3 072 Mio : bdd1 768, bdd2 768, app1 512, app2 512 et lb1 512.
Quatre applications portent le total à 4 096 Mio. Le NAT sert aux téléchargements
de paquets et le réseau privé au trafic des services. Les dossiers partagés sont
désactivés.

Redis évite une VM supplémentaire. Son expiration de trente secondes borne les
lectures anciennes. E4 draine chaque serveur, attend la fin des requêtes, déploie
la version et contrôle sa santé avant son retour. lb1 reste un point unique de
panne connu.
