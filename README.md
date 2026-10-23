# RESULTATS-BF — Groupe 10

**État : la campagne VirtualBox complète a été exécutée le 18 octobre 2026.**
V1, V2, V4, V5, R2, R5, E3 et E4 sont validés. V3 a été mesuré et montre une
baisse de débit avec quatre applications sur le même hôte physique. Les preuves
figurent dans docs/VALIDATION.md et results.

Ce laboratoire crée une base PostgreSQL principale et une réplique, quatre
serveurs Flask sans état et un répartiteur HAProxy. Les extensions retenues sont
le cache Redis E3 et le déploiement progressif E4.

## 1 Prérequis et adressage

Les commandes doivent être exécutées sur la machine Linux physique, pas dans une
VM Ubuntu déjà ouverte dans VirtualBox. Il faut VirtualBox, Vagrant, Ruby,
Python 3, ApacheBench, un accès Internet et suffisamment de mémoire.

Le sujet attribue des réseaux uniquement aux groupes 1 à 8. Le groupe 10 utilise
provisoirement NETWORK_OCTET=56, soit 192.168.56.0/24. Il faut confirmer ce choix
avec l'enseignant et vérifier que .11, .21 à .28, .31 et .32 sont disponibles.

python3 scripts/ops.py preflight s'arrête si une VM VirtualBox en cours
d'exécution, hors de ce projet, annonce déjà l'une des adresses de l'inventaire.
La détection repose sur les Guest Additions ; une VM qui n'en dispose pas, ou une
machine hors VirtualBox, doit toujours être vérifiée à la main.

## 2 Démarrage

Depuis le dossier du projet :

    python3 scripts/setup.py
    python3 scripts/ops.py preflight
    vagrant validate
    vagrant up --provider=virtualbox
    python3 scripts/ops.py v1

scripts/setup.py crée .env avec des secrets aléatoires et ne remplace jamais un
fichier existant. Il faut conserver ce même fichier pendant les reconstructions.
.env.exemple ne contient aucun mot de passe réel.

L'image utilisée est bento/ubuntu-24.04 version 202502.21.0. Elle a été
téléchargée et utilisée avec succès pour les sept VM.

L'API est accessible à l'adresse :

    http://127.0.0.1:8080/resultat?matricule=000001

/info indique le serveur et la version. /sante contrôle réellement une base
accessible en écriture.

## 3 Architecture

Le trafic suit ce chemin :

    Hôte:8080 → lb1 .11 HAProxy → app1 à app4 .21 à .24
                                         ↓
                                 bdd1 .31 PostgreSQL
                                         ↓ réplication
                                 bdd2 .32 PostgreSQL

Redis se trouve sur lb1 et écoute uniquement sur le réseau privé. Seul lb1
expose un port applicatif. Les redirections SSH automatiques de Vagrant restent
limitées à 127.0.0.1 et servent uniquement à l'administration.

config/topology.rb est la source unique des noms, adresses et mémoires. HAProxy
est généré à partir du même inventaire. Le socle à deux applications consomme
3 072 Mio et la version à quatre applications 4 096 Mio.

## 4 Montée en charge et V3

Pour mesurer deux applications :

    python3 scripts/ops.py cache-off
    python3 scripts/ops.py benchmark --label V3-N2

Pour créer quatre applications :

    NB_APP=4 vagrant up

Il faut ensuite conserver NB_APP=4 dans .env et exécuter :

    python3 scripts/ops.py v1
    python3 scripts/ops.py cache-off
    python3 scripts/ops.py benchmark --label V3-N4

Le test utilise exactement ab -n 2000 -c 50. Le résultat réel est 137,17 req/s
avec deux applications et 121,28 req/s avec quatre. Le partage du même hôte,
de la même base et du même disque explique cette baisse.

ops.py v1 est le scénario V1 officiel : exactement 20 appels successifs à /info,
soit dix réponses par application avec NB_APP=2 et cinq avec NB_APP=4. Ces deux
cas sont ceux qui doivent être validés. Vingt appels ne se répartissent pas
également entre six, sept ou huit applications ; pour vérifier la répartition
avec ces valeurs, une commande distincte, qui ne remplace pas V1, envoie cinq
appels par application et enregistre une preuve V1-generic :

    python3 scripts/ops.py v1-generic

## 5 Réplication et idempotence

    python3 scripts/ops.py replication
    python3 scripts/ops.py idempotence

Le contrôle de réplication écrit une valeur unique sur bdd1, attend cette valeur
sur bdd2 puis restaure la donnée. Le contrôle d'idempotence compare les
empreintes après deux provisionnements successifs. Le deuxième ne doit produire
aucun nouveau changement.

## 6 Pannes

Le scénario V2 arrête app1 pendant un trafic continu :

    python3 scripts/validate-live.py v2

La preuve finale contient 2 939 requêtes, huit pertes, une période dégradée de
4,49 secondes et aucune erreur après cinq secondes.

Le scénario V4 arrête bdd1 puis promeut bdd2 :

    python3 scripts/validate-recovery.py

La promotion refuse de fonctionner si bdd1 est encore active ou sauvegardée.
Après promotion, bdd1 doit rester arrêtée. La procédure place bdd2 en tête sur
chaque application et attend le retour de /sante.

Le même script exécute ensuite V5. Il détruit uniquement les VM de ce projet,
les reconstruit et vérifie les sept états. La reconstruction mesurée a demandé
1 042,10 secondes.

## 7 Cache Redis E3

    python3 scripts/ops.py cache-off
    python3 scripts/ops.py benchmark --label E3-no-cache
    python3 scripts/ops.py cache-on
    python3 scripts/ops.py cache-purge
    curl 'http://127.0.0.1:8080/resultat?matricule=000001'
    python3 scripts/ops.py benchmark --label E3-warm-cache

Les entrées expirent après trente secondes. Après une modification de données,
il faut purger le cache pour une visibilité immédiate. Redis n'est jamais la
source durable et une panne du cache renvoie les lectures vers PostgreSQL.

Le test a mesuré 121,28 req/s sans cache et 1 271,20 req/s avec le cache
préchauffé, sans échec.

## 8 Déploiement progressif E4

    python3 scripts/validate-live.py e4

Chaque application est drainée, placée en maintenance, mise à jour, redémarrée
et contrôlée directement puis par HAProxy avant de passer à la suivante. La
preuve finale couvre tout le déploiement et cinq secondes supplémentaires :
17 155 requêtes, zéro échec, quatre applications en version 2.

## 9 Livrables

- docs/architecture-report.pdf : rapport en français de douze pages.
- docs/team-journal.pdf : journal en français de deux pages à compléter.
- docs/guide-commits-git.pdf : méthode pour les vrais commits des membres.
- docs/VALIDATION.md : matrice reliant chaque critère à sa preuve.
- docs/STATUS.md : état vérifié et travail humain restant.
- results : preuves JSON, CSV et ApacheBench.

L'historique Git doit contenir de vraies contributions. Chaque membre configure
son vrai nom et son courriel, réalise une modification qu'il comprend, la teste
et crée son propre commit. Il ne faut pas inventer les auteurs.

## 10 Démonstration

Prévoir environ deux minutes pour l'architecture, huit minutes pour expliquer la
reconstruction, sept minutes pour les scénarios et trois minutes pour
interpréter les preuves. V6 ne s'applique pas car E1 n'est pas retenue.

Avant la remise, compléter les noms et contributions, confirmer le réseau du
groupe 10 et répéter la présentation.
