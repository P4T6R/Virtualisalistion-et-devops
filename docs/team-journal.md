# Journal du groupe 10

Journal factuel à compléter avec les véritables noms, contributions et commits.

## Journal de préparation

### 18 octobre 2026 périmètre

Le sujet a été étudié et les exigences obligatoires ont été séparées des extensions. Le groupe 10 a été confirmé. Comme le tableau d'adressage s'arrête au groupe 8, le réseau configurable 192.168.56.0/24 a été retenu provisoirement. Redis et le déploiement progressif ont été choisis.

### Conception et réalisation

Le PRD, le SRS, le contrat, l'architecture et le modèle ont été écrits avant le code. L'implémentation utilise une source d'inventaire, des serveurs HAProxy générés, PostgreSQL répliqué, une API sans état, des secrets locaux et des procédures d'exploitation.

### Vérification et difficultés

Les 21 tests locaux passent. La campagne VirtualBox a validé V1, V2, V4, V5, R2, R5, E3 et E4. Deux processus anciens causaient des doublons d'adresses. app4 a dû être recréée après un système de fichiers en lecture seule. La première promotion a révélé un mauvais ordre de connexion, désormais corrigé.

### Travail restant

Les mesures techniques et la reconstruction sont terminées. Il reste à confirmer le sous-réseau, inscrire les vrais noms, produire des commits issus de contributions réelles et répéter la démonstration. Aucun historique étudiant n'a été inventé.

## Contributions des membres et expériences

### Responsabilités

Membre 1 : __________________. Réseau, inventaire et répartition : __________________. Membre 2 : __________________. Application et E4 : __________________. Membre 3 : __________________. PostgreSQL, réplication et E3 : __________________. Membre 4 : __________________. Validation, preuves et rapport : __________________.

### Contribution croisée

Pour chaque membre, indiquer une modification réelle hors du rôle principal, son identifiant de commit et ce qui a été appris. Membre 1 : __________________. Membre 2 : __________________. Membre 3 : __________________. Membre 4 : __________________. Ne pas fabriquer de commits ni modifier les auteurs.

### Fiche d'expérience

Date et heure : __________________. Scénario et commande : __________________. Mémoire, processeur, nombre d'applications et cache : __________________. Fichier brut : __________________. Résultat : __________________. Cause vérifiée d'une difficulté : __________________. Correction et nouvel essai : __________________.

### Contrôle avant remise

Confirmer le réseau et l'interprétation des ports SSH avec l'enseignant. V5 a demandé 1 042,10 secondes ; V2 reste sous cinq secondes ; V4 a repris en 22,66 secondes ; E4 n'a perdu aucune des 17 155 requêtes. Compléter cette page uniquement à partir du travail réel des membres.

