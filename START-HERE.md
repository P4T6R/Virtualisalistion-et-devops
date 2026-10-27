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
7. Consulter `docs/journal-de-bord.md` pour les contributions réelles des quatre
   membres et `docs/guide-demonstration.pdf` pour préparer la présentation.
8. Confirmer le réseau provisoire avec l'enseignant, puis répéter la
   reconstruction et trois scénarios.

La suite découvre 42 tests ; sur l'hôte sans binaire HAProxy, 41 réussissent et
le contrôle d'intégration HAProxy est ignoré. Les mesures et limites sont dans
docs/STATUS.md.
La VM Ubuntu créée séparément ne fait pas partie des VM ciblées par ce projet.
