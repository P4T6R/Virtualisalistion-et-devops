# Preuves d'acceptation

| Critère | Opération | Résultat mesuré | Preuve principale |
|---|---|---|---|
| R1 / V5 | validate-recovery.py | Réussi — sept VM en 1 042,10 s, santé 200 | 20261018T132322639742Z-V5-reconstruction.json et V5-post-rebuild.json |
| R2 | ops.py idempotence | Réussi — mêmes empreintes après les deux applications | R2-idempotence et R2-idempotence-evaluation |
| R3 / V1 | NB_APP=4 puis ops.py v1 | Réussi — 20 appels à /info, cinq réponses par application, écart nul | 20261018T132331048575Z-V1.json |
| R4 / V2 | validate-live.py v2 | Réussi — huit pertes, 4,49 s dégradées, aucune erreur après cinq secondes | V2-app-failure, évaluation et CSV |
| R5 | ops.py replication | Réussi — valeur unique visible sur bdd2 | 20261018T132337157126Z-R5-replication.json |
| R6 / V4 | validate-recovery.py | Réussi — 503 contrôlé, bdd2 principale, santé 200 en 22,66 s reprises | V4-promotion et V4-total-failover |
| R7 | contrôle Git | Sources correctes ; vrais commits encore nécessaires | .gitignore et .env.exemple |
| R8 | contrôle réseau | Services privés, seul lb1 expose l'application | Vagrantfile ; interprétation SSH déclarée |
| V3 | ab -n 2000 -c 50 sans cache | 137,17 req/s à deux applications ; 121,28 à quatre ; zéro échec | V3-N2.txt et V3-N4.txt |
| V6 | E1 non retenue | Sans objet | E3 et E4 sont les extensions choisies |
| E3 | mêmes tests sans et avec cache | 121,28 à 1 271,20 req/s, gain 10,48 fois | V3-N4.txt et E3-warm-cache.txt |
| E4 | validate-live.py e4 | Réussi — 17 155 requêtes, zéro échec, quatre applications en version 2 | E4-zero-downtime.json et CSV |

## Notes d'interprétation

- V3 ne montre pas de gain avec quatre applications. Toutes les VM partagent le
  même processeur, le même disque virtuel et la même base. La baisse de 11,58 %
  est le résultat réel.
- Le délai V2 commence au premier échec observé. La dernière réponse en échec se
  termine 4,49 secondes après ce point.
- V4 est indiqué comme intervalle repris parce que la première promotion avait
  déjà réussi avant la correction de l'ordre des bases. L'ancienne base est
  restée arrêtée.
- Le premier essai E4 de quatre-vingt-dix secondes est exclu, car il s'est
  terminé avant le déploiement. La preuve finale couvre tout le déploiement et
  cinq secondes supplémentaires.
- Les essais infructueux sont conservés pour expliquer les corrections, mais
  seules les preuves finales indiquées ci-dessus servent à l'acceptation.
