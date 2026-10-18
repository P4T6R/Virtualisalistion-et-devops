# Exigences du système

- R1 : une reconstruction destroy/up fonctionne sans commande dans les VM.
- R2 : deux provisionnements successifs produisent les mêmes empreintes.
- R3 : NB_APP modifie ensemble l'inventaire et les serveurs HAProxy.
- R4 : /sante est contrôlé chaque seconde et un serveur défaillant est retiré
  en moins de cinq secondes.
- R5 : PostgreSQL 16 utilise une réplication en continu.
- R6 : la promotion exige l'arrêt vérifié de la base principale et mesure la
  reprise.
- R7 : les secrets d'environnement sont ignorés et absents du code et de
  l'historique.
- R8 : le trafic des services reste privé ; seul lb1 expose un port applicatif.
  Les ports SSH Vagrant sont limités à la boucle locale et documentés comme
  exception de gestion à confirmer avec l'enseignant.

L'application comporte moins de cent lignes et fournit /resultat, /sante et
/info. Elle emploie des requêtes SQL paramétrées, crée exactement 50 000
résultats déterministes et ne conserve aucun état métier local. Le cache est
externe et facultatif. Les erreurs ne doivent pas révéler les exceptions de la
base.

L'acceptation exige des preuves issues des VM. V1 à V5, E3 et E4 doivent être
exécutés. V6 ne s'applique pas puisque E1 n'est pas retenue.
