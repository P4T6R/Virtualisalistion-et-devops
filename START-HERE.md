# Commencer ici — Groupe 10

La plateforme a été déployée, mesurée et validée. Les étapes suivantes servent à
la reproduire sur la machine Linux physique.

1. Ouvrir un terminal sur l'hôte, en dehors de la VM Ubuntu.
2. Entrer dans le dossier :

       cd /home/aiobi5/Documents/Codex/2026-10-18/dis/outputs/resultats-bf

3. Contrôler les prérequis et le réseau :

       python3 scripts/ops.py preflight

4. Vérifier que les adresses .11, .21 à .28, .31 et .32 du réseau provisoire
   192.168.56.0/24 ne sont pas déjà utilisées.
5. Démarrer :

       bash scripts/start.sh

6. Consulter README.md pour la réplication, les pannes, le cache et le
   déploiement progressif.
7. Utiliser docs/guide-commits-git.pdf pour produire les vrais commits des quatre
   membres.
8. Compléter le journal avec les vrais noms, contributions et identifiants.

Les 21 tests locaux passent. Les mesures et limites sont dans docs/STATUS.md.
La VM Ubuntu créée séparément ne fait pas partie des VM ciblées par ce projet.
