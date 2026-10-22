# Tests locaux

```sh
python3 -m venv .test-env
.test-env/bin/pip install -r tests/requirements.txt
.test-env/bin/python -m unittest discover -s tests -v
ruby -c Vagrantfile
ruby -c config/topology.rb
```

Les tests de l'API utilisent le véritable client de test Flask et remplacent les
connexions PostgreSQL et Redis afin de couvrir les chemins d'erreur. Les tests
d'infrastructure exécutent le générateur Ruby de l'inventaire et la production
de la configuration HAProxy. Ils ne démarrent pas de VM et ne remplacent pas les
preuves de réplication, de performances et de disponibilité dans results.

Le workflow .github/workflows/tests.yml exécute ces mêmes commandes sur GitHub
Actions à chaque push sur main et à chaque pull request.
