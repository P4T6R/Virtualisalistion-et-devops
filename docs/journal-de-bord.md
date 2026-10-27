# Journal du groupe 10

Journal factuel des contributions et des essais du groupe.

## Journal de préparation

### 18 octobre 2026 périmètre

Le sujet a été étudié et les exigences obligatoires ont été séparées des extensions. Le groupe 10 a été confirmé. Comme le tableau d'adressage s'arrête au groupe 8, le réseau configurable 192.168.56.0/24 a été retenu provisoirement. Redis et le déploiement progressif ont été choisis.

### Conception et réalisation

Le PRD, le SRS, le contrat, l'architecture et le modèle ont été écrits avant le code. L'implémentation utilise une source d'inventaire, des serveurs HAProxy générés, PostgreSQL répliqué, une API sans état, des secrets locaux et des procédures d'exploitation.

### Vérification et difficultés

La suite découvre 42 tests : 41 réussissent sur l'hôte et un test nécessitant le binaire HAProxy y est ignoré. La campagne VirtualBox a validé V1, V2, V4, V5, R2, R5, E3 et E4. Deux processus anciens causaient des doublons d'adresses. app4 a dû être recréée après un système de fichiers en lecture seule. La première promotion a révélé un mauvais ordre de connexion, désormais corrigé.

### 26 octobre 2026 — préparation de la remise

Les contributions fusionnées ont été recensées et les documents actualisés avec les quatre auteurs. Le rapport inclut le schéma, le tableau des scénarios et le dépôt GitHub. Le journal est complété à partir des preuves existantes ; la préparation documentaire ne constitue pas une nouvelle campagne sur les VM.

## Contributions des membres et expériences

### Responsabilités

Céphas CONGO : architecture, intégration, preuves et fusion des Pull Requests. Lompo Ephraim : validation continue, réseau et détection des conflits VirtualBox. Leïla BOUGOUMA : comportement de l'application, erreurs JSON et test du délai HAProxy. Eva Benjamine Kazienga : PostgreSQL, réplication, résilience, Redis et réponse 503 de HAProxy.

### Contribution croisée

Céphas : l'intégration initiale 56e79f3 couvre l'infrastructure, l'application, les données, les tests et la documentation. Lompo : bd482e4 ajoute la CI au-delà du travail réseau 0e1ff83. Leïla : cd63415 ajoute un test HAProxy en dehors des correctifs applicatifs 00ff746 et 118c64e. Eva : 452b7bf améliore le répartiteur en dehors de sa contribution données 2492ee1.

### Expérience tracée — reconstruction V5 du 18 octobre

La preuve 20261018T132322639742Z-V5-reconstruction.json a été enregistrée à 13:23:22 UTC : reconstruction en 1 042,10 s, santé HTTP 200. La topologie compte quatre applications, deux bases et lb1, avec 4 096 Mio de RAM allouée et un vCPU par VM. Le contrôle V5-post-rebuild confirme les sept VM actives ; V1 puis R5 réussissent à 13:23:31 et 13:23:37 UTC. Le mode du cache n’est pas consigné dans cette preuve V5 et n’est donc pas déduit.

### Limites et vérifications avant remise

Les conflits IP ont été identifiés par comparaison des adresses MAC ; app4 a été recréée après une erreur de système de fichiers. La reprise V4 a nécessité de placer bdd2 en tête des connexions. Les 22,66 s concernent une reprise de test, pas une bascule initiale complète. Restent la confirmation du réseau et des ports SSH avec l’enseignant, puis la répétition sur la version courante.
