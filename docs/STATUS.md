# État de la livraison au 18 octobre 2026

## Travaux terminés

- Topologie de sept VM active après une reconstruction complète : bdd1, bdd2,
  app1 à app4 et lb1.
- Réplication PostgreSQL, contrôles HAProxy, cache Redis et déploiement
  progressif réalisés et mesurés.
- Les secrets restent dans .env et .runtime, tous deux ignorés et exclus de
  l'archive.
- Les documents d'exigences, de contrat, d'architecture et de modélisation
  précèdent l'implémentation.
- Le rapport et la matrice de validation correspondent aux preuves brutes.

## Résultats vérifiés

- V1 : 20 appels successifs à /info avec quatre applications, soit cinq
  réponses par application, écart de 0 %.
- V2 : 2 939 requêtes, huit pertes, période dégradée de 4,49 s, éviction HAProxy
  en 3,67 s et aucune erreur après cinq secondes.
- V3 : 137,17 req/s avec deux applications et 121,28 req/s avec quatre, sans
  échec.
- V4 : HTTP 503 contrôlé après l'arrêt de bdd1, promotion de bdd2 puis retour à
  HTTP 200 en 22,66 s d'intervalle repris.
- V5 : sept VM reconstruites en 1 042,10 s, soit 17 min 22 s, puis V1 et R5
  rejoués avec succès.
- R2 : mêmes empreintes après la première et la seconde application complète.
- R5 : une valeur unique écrite sur bdd1 est devenue visible sur bdd2.
- E3 : le cache Redis préchauffé passe de 121,28 à 1 271,20 req/s.
- E4 : 17 155 requêtes pendant la totalité du déploiement, zéro échec et les
  quatre applications observées en version 2.
- Les 21 tests locaux passent.

## Incidents corrigés

- Deux anciens processus de VM utilisaient encore .31 et .32. Les adresses MAC
  ont permis de prouver le conflit puis de les arrêter proprement.
- Le système de fichiers de app4 était en lecture seule ; cette VM sans état a
  été recréée.
- La première promotion laissait l'ancienne base en tête de la liste de
  connexion. La procédure place maintenant bdd2 en premier après promotion.
- Le contrôle d'idempotence vérifie désormais la condition formelle F(F(x)) =
  F(x).

## Travail humain restant

- Confirmer le réseau provisoire 192.168.56.0/24 avec l'enseignant.
- Ajouter les quatre vrais noms, rôles, contributions croisées et commits.
- Répéter la démonstration de vingt minutes.
- Confirmer l'interprétation de R8 concernant les ports SSH de gestion Vagrant.

La campagne technique est terminée. La remise dépend encore de ces éléments
humains et de la confirmation de l'enseignant.
