# Partie données et résilience

Ce document regroupe tout ce qui concerne la couche de données : PostgreSQL 16 en primaire et réplique, le contrôle de la réplication, la panne de bdd1, la promotion de bdd2, la réintégration de l'ancienne base et le cache Redis. Il couvre R5, R6, V4 et E3. Les commandes se lancent depuis l'hôte, à la racine du dépôt.

Les chiffres cités dans la section 9 viennent de la campagne du 18 octobre 2026 et des fichiers listés dans [VALIDATION.md](VALIDATION.md). Aucun chiffre de ce document n'est estimé.

## 1. Rôles des deux bases

| Machine | Adresse | Rôle au démarrage | Accès |
|---|---|---|---|
| bdd1 | `192.168.56.31` | Primaire | Lecture et écriture |
| bdd2 | `192.168.56.32` | Réplique en flux | Lecture seule, promouvable |

Les adresses viennent de `config/topology.rb`, la même source que le Vagrantfile. PostgreSQL écoute sur `127.0.0.1` et sur l'adresse privée du nœud : le port 5432 n'est jamais redirigé vers l'hôte (R8).

**Mise en place, dans `scripts/provision.py`.** bdd1 active `wal_level = replica` et crée l'emplacement de réplication physique `bdd2_slot`. Un rôle `replicator` est autorisé dans `pg_hba.conf` uniquement depuis l'adresse de bdd2. bdd2 s'initialise une seule fois par `pg_basebackup -R -X stream -S bdd2_slot`, puis démarre en mode récupération. Le fichier marqueur `/var/lib/postgresql/resultats-replica-initialized` empêche de recopier la base à chaque `vagrant provision`, ce qui garde R2.

**Pourquoi l'asynchrone.** La réplication est asynchrone : bdd1 n'attend pas bdd2 pour valider une écriture. Une réplique lente ou arrêtée ne ralentit donc pas la base principale. En contrepartie, une panne brutale peut perdre les dernières transactions non encore transmises. Pour des résultats publiés une fois puis lus en masse, ce risque est jugé acceptable.

**Pourquoi un emplacement de réplication.** Sans emplacement, bdd1 pourrait recycler des journaux dont bdd2 a encore besoin après une coupure. `bdd2_slot` les conserve, dans la limite de `max_slot_wal_keep_size = 256MB` pour qu'une réplique arrêtée longtemps ne remplisse pas le disque de bdd1. Au-delà, l'emplacement est invalidé et bdd2 doit être reconstruite.

## 2. Comment l'application trouve la bonne base

Chaque serveur applicatif reçoit `DB_HOSTS=<bdd1>,<bdd2>` dans `/etc/resultats/app.env`. `app/service.py` se connecte avec `target_session_attrs='read-write'` : psycopg2 essaie les hôtes dans l'ordre et ne garde que celui qui accepte les écritures. Tant que bdd1 est primaire, bdd2 est ignorée pour les requêtes. Après promotion, la procédure place bdd2 en tête de la liste pour éviter d'attendre le délai de connexion de bdd1 à chaque requête.

## 3. Vérifier la réplication (R5)

```bash
python3 scripts/ops.py replication
```

Le contrôle se déroule en quatre temps :

1. il vérifie que bdd1 n'est pas en récupération et que bdd2 l'est ; sinon il s'arrête **avant toute écriture**, avec un message qui rappelle qu'après une promotion il faut reconstruire ;
2. il vérifie que `pg_stat_replication` sur bdd1 montre une réplique dans l'état `streaming` ;
3. il écrit une valeur unique dans la ligne `050000` sur bdd1 et attend de la lire sur bdd2, vingt secondes au plus ;
4. il restaure la valeur d'origine et purge le cache Redis, puis enregistre la preuve dans `results/…-R5-replication.json` avec les rôles, l'état du flux et le délai observé.

Le délai enregistré inclut les allers-retours `vagrant ssh` : c'est une borne haute, pas le retard réel de réplication.

Vérification manuelle équivalente :

```bash
vagrant ssh bdd1 -c "sudo -u postgres psql -c 'SELECT client_addr, state, replay_lag FROM pg_stat_replication;'"
vagrant ssh bdd2 -c "sudo -u postgres psql -At -c 'SELECT pg_is_in_recovery();'"   # attendu : t
```

## 4. Diagnostic de connexion aux bases

```bash
python3 scripts/diagnose-db.py            # tous les serveurs applicatifs de l'inventaire
python3 scripts/diagnose-db.py app1       # un seul serveur
```

Le diagnostic est en lecture seule et masque les mots de passe. Il produit trois parties :

- **databases** : pour bdd1 et bdd2, l'état du service, le rôle (`in_recovery`), le flux vu par la primaire ou par la réplique, et l'état de l'emplacement de réplication. Une VM arrêtée est signalée `reachable: false` au lieu de faire échouer tout le diagnostic.
- **applications** : pour chaque serveur applicatif, la valeur de `DB_HOSTS` et, pour chaque hôte de la liste, si une connexion en écriture réussit et vers quelle adresse.
- **verdict** : aucune base en écriture (le service renvoie 503 jusqu'à la promotion), une seule (situation normale), ou deux (cerveau divisé, à arrêter immédiatement).

Avant cette version, le script interrogeait `app3` et `app4` en dur et échouait avec la configuration par défaut `NB_APP=2`. Il lit maintenant la liste des serveurs dans l'inventaire, comme le répartiteur.

## 5. Panne de bdd1 et comportement HTTP 503 (V4)

### 5.1. Ce que renvoie l'application

Vérifié dans `app/service.py` et par les tests unitaires de `tests/test_project.py` :

| Requête | Base indisponible | Corps |
|---|---|---|
| `GET /sante` | 503 | `{"status": "database_unavailable"}` |
| `GET /resultat`, résultat absent du cache | 503 | `{"error": "database_unavailable"}` |
| `GET /resultat`, résultat présent dans Redis | 200 | le résultat en cache |

Le message d'erreur de PostgreSQL n'est jamais renvoyé : il pourrait contenir un nom d'hôte ou un mot de passe. `/sante` n'interroge jamais Redis, pour que le cache ne masque pas une panne de base au répartiteur. Le troisième cas est volontaire et désormais couvert par un test : un serveur peut encore répondre depuis le cache tout en se déclarant malade.

### 5.2. Ce que voit le client derrière HAProxy

HAProxy interroge `/sante` toutes les secondes (`inter 1s fall 2`). Dès que bdd1 tombe, tous les serveurs applicatifs répondent 503 et sont retirés du groupe après deux échecs de sonde, soit quelques secondes (l'éviction d'un serveur a été mesurée à 3,67 s pendant V2). Pendant ce court intervalle, le client reçoit les 503 JSON de l'application. Ensuite, lorsqu'aucun serveur n'est disponible, la règle du frontal public fait répondre **HAProxy lui-même** avec le code 503, le type `application/json` et le corps `{"error":"service_unavailable"}`. Le client reçoit donc toujours une réponse JSON contrôlée, jamais la page HTML par défaut de HAProxy ni une connexion refusée, ce qui répond à V4.

### 5.3. Observer la panne

```bash
python3 scripts/validate-recovery.py
```

Le script arrête bdd1, attend un 503 sur `/sante` pendant vingt secondes au plus, lance la promotion, vérifie le retour à 200 et enregistre `V4-total-failover`. Attention : il enchaîne ensuite V5, donc une reconstruction complète.

Pour observer la panne seule pendant un trafic continu :

```bash
python3 scripts/ops.py probe --seconds 60 --path /sante    # terminal 1
vagrant halt bdd1                                          # terminal 2
python3 scripts/diagnose-db.py                             # verdict attendu : aucune base en écriture
```

## 6. Promotion de bdd2 (R6)

```bash
vagrant halt bdd1
python3 scripts/ops.py promote
```

La commande suit cet ordre, chaque étape conditionnant la suivante :

1. **Isolement.** Elle refuse de continuer si bdd1 n'est pas dans l'état `poweroff`. Une VM `saved` n'est pas isolée : elle peut reprendre en primaire et créer un cerveau divisé.
2. **Promotion.** `pg_promote(true, 30)` sur bdd2, qui attend la fin de la promotion. Si bdd2 est déjà primaire, l'étape ne fait rien.
3. **Redirection.** Sur chaque serveur applicatif, `DB_HOSTS` devient `<bdd2>,<bdd1>` puis le service redémarre.
4. **Contrôle.** Attente d'un 200 public sur `/sante`.
5. **Purge du cache.** Les clés `resultats:v1:*` sont supprimées de Redis (voir 8.2). Si lb1 ne répond pas, la promotion n'échoue pas : un avertissement demande de lancer `python3 scripts/ops.py cache-purge`, et la preuve indique `cache_purged: false`.
6. **Preuve.** Écriture de `V4-promotion` et du marqueur `.runtime/promoted`. La durée enregistrée s'arrête au retour de la santé et n'inclut pas la purge, pour rester comparable aux mesures précédentes.

Après promotion, **bdd1 doit rester arrêtée**. Si on la redémarre telle quelle, elle se croit encore primaire : deux bases accepteraient des écritures divergentes. `python3 scripts/diagnose-db.py` signale cette situation dans son verdict.

## 7. Réintégration de l'ancienne base

### 7.1. Procédure retenue par le projet

Le laboratoire étant reproductible, la procédure validée est la reconstruction :

```bash
python3 scripts/ops.py rebuild --confirm-destroy-project-vms
```

Elle détruit les VM du projet, supprime le marqueur `.runtime/promoted` et refait `vagrant up`. bdd1 redevient primaire, bdd2 redevient réplique, et le jeu de données est régénéré. Cette voie a été mesurée pendant V5 : 1 042,10 s pour sept VM, suivies d'un R5 réussi.

Elle convient au laboratoire car les 50 000 lignes sont synthétiques. Elle ne conviendrait pas en production : les écritures faites sur bdd2 après la promotion seraient perdues.

### 7.2. Réintégration sans perte (non exécutée pendant la campagne)

En production, on ferait revenir bdd1 comme **réplique de bdd2**. Cette procédure n'a pas été testée sur nos VM et deux prérequis manquent dans le provisionnement actuel :

- le `pg_hba.conf` de bdd2 n'autorise la réplication que depuis l'adresse de bdd2 ; il faudrait une règle pour l'adresse de bdd1 ;
- bdd2 n'a pas d'emplacement de réplication pour bdd1.

Une fois ces deux points ajoutés, la démarche serait : démarrer bdd1 sans provisionnement, arrêter PostgreSQL, vider son répertoire de données, refaire une copie depuis bdd2 avec `pg_basebackup -R -X stream`, puis redémarrer. bdd1 serait alors en récupération et `diagnose-db.py` montrerait une seule base en écriture. `pg_rewind` éviterait la copie complète mais exige `wal_log_hints = on` dès l'installation ; avec 50 000 lignes, la copie complète reste plus simple.

## 8. Cache Redis (E3)

### 8.1. Fonctionnement

Redis tourne sur lb1 pour ne pas ajouter de VM au budget de 3 Go. Il écoute sur `127.0.0.1` et l'adresse privée de lb1, exige un mot de passe généré, se limite à 64 Mio avec éviction `allkeys-lru`, et sa persistance est désactivée : PostgreSQL reste la seule source durable.

Pour `GET /resultat`, l'application suit le principe « lecture à travers le cache » :

1. elle lit la clé `resultats:v1:<matricule>` dans Redis ;
2. si la clé existe, elle renvoie la valeur sans toucher PostgreSQL ;
3. sinon, elle lit la base et écrit la réponse avec une durée de vie de 30 s.

Les délais Redis sont de 0,2 s. Si Redis ne répond pas, la lecture passe directement par PostgreSQL : le cache accélère le service mais n'en conditionne jamais la disponibilité. Les serveurs applicatifs restent sans état, car le cache est partagé et extérieur à eux.

### 8.2. Invalidation

- **Durée de vie.** Une donnée modifiée en base peut rester ancienne dans le cache pendant 30 s au plus. C'est le filet de sécurité si une purge est oubliée.
- **Purge explicite.** `python3 scripts/ops.py cache-purge` supprime toutes les clés `resultats:v1:*`. Le contrôle R5 l'appelle automatiquement après avoir restauré la ligne de test.
- **Version dans la clé.** Le préfixe `v1` permet, si le format JSON change, de passer à `v2` sans servir d'anciennes réponses.
- **Après une bascule.** Une écriture validée sur bdd1 mais non répliquée peut se trouver dans le cache et pas dans bdd2. `ops.py promote` purge donc le cache automatiquement, pour ne pas servir une donnée que la nouvelle primaire ne contient pas.

Le compromis est assumé : un résultat d'examen change très rarement après publication, donc 30 s de fraîcheur perdue contre un débit multiplié par dix est un bon échange.

### 8.3. Mesure

```bash
python3 scripts/ops.py cache-off
python3 scripts/ops.py benchmark --label E3-no-cache
python3 scripts/ops.py cache-on
python3 scripts/ops.py cache-purge
curl 'http://127.0.0.1:8080/resultat?matricule=000001'
python3 scripts/ops.py benchmark --label E3-warm-cache
```

## 9. Résultats obtenus

| Critère | Résultat mesuré le 18 octobre 2026 | Preuve |
|---|---|---|
| R5 | Valeur unique écrite sur bdd1 visible sur bdd2 | `20261018T132337157126Z-R5-replication.json` |
| R5 après V5 | Contrôle rejoué avec succès après reconstruction complète | `V5-post-rebuild` puis R5 |
| V4 | 503 contrôlé après l'arrêt de bdd1, bdd2 promue, retour à 200 en 22,66 s d'intervalle repris | `V4-promotion` et `V4-total-failover` |
| E3 | 121,28 req/s sans cache, 1 271,20 req/s avec cache préchauffé, soit 10,48 fois | `V3-N4.txt` et `E3-warm-cache.txt` |
| E3 latence | 412,28 ms sans cache, 39,33 ms avec cache, zéro échec | mêmes fichiers |

**Lecture honnête des chiffres.**

- Le 22,66 s de V4 est un intervalle repris : la première promotion avait réussi avant la correction de l'ordre `DB_HOSTS`, et l'ancienne base est restée arrêtée. Il exclut la durée d'arrêt de bdd1.
- La première tentative de V4 a montré que les applications essayaient trop longtemps l'ancienne base. C'est ce qui a conduit à placer bdd2 en tête de `DB_HOSTS` après promotion.
- Le gain E3 est mesuré sur une seule clé préchauffée, c'est-à-dire le meilleur cas. Le jour des résultats, les consultations portent sur des matricules différents ; le gain réel dépendra de la proportion de requêtes répétées.
- Les preuves R5 antérieures à cette contribution ne contiennent pas encore les rôles ni le délai : ils apparaîtront dans les prochaines exécutions de `ops.py replication`.

## 10. Limites connues

- La bascule est manuelle. Un outil à consensus comme Patroni l'automatiserait, mais il faudrait au moins une machine de plus, hors du budget mémoire.
- Après promotion, bdd2 est seule : il n'y a plus de réplique jusqu'à la reconstruction.
- La réplication asynchrone peut perdre les dernières transactions lors d'une panne brutale de bdd1.
- Une fois tous les serveurs retirés, le 503 JSON est produit par HAProxy avec l'erreur générique `service_unavailable` ; il ne précise pas si l'indisponibilité vient de PostgreSQL ou des serveurs applicatifs.
- Redis n'est pas redondant. Sa panne n'interrompt pas le service mais ramène le débit au niveau sans cache.
- Aucune sauvegarde hors ligne n'est prévue : une réplique protège contre la perte d'une machine, pas contre une suppression accidentelle, qui serait aussitôt répliquée.
