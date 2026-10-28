# Programme TV

Le programme télé des chaînes françaises sur les écrans e-paper [TRMNL](https://trmnl.com) : ce qui passe en ce moment et ce qui suit, puis la soirée (première et seconde partie).

## Fonctionnalités

- Jusqu'à 10 chaînes au choix parmi les quelque 400 accessibles en France : TNT, câble, satellite, chaînes locales, outre-mer, plus quelques chaînes belges et suisses.
- Trois modes d'affichage :
  - **En ce moment** : le programme en cours, avec une barre de progression, et le suivant.
  - **Ce soir** : la première partie de soirée (vers 21 h) et la seconde.
  - **Auto** (par défaut) : « En ce moment », puis « Ce soir » de 18 h à 22 h.
- Les quatre formats TRMNL (plein écran, moitiés horizontale et verticale, quart), en paysage comme en portrait, et le mode sombre.

## Données

Les programmes viennent de [XML TV Fr](https://xmltvfr.fr) ([GitHub](https://github.com/racacax/XML-TV-Fr)), qui publie chaque jour un guide XMLTV de 5 jours pour environ 400 chaînes accessibles en France. Ce projet n'est pas affilié à XML TV Fr.

## Fonctionnement

TRMNL refuse les réponses de plus de 100 Ko, et le guide pèse 73 Mo (9 Mo compressé). D'où un relais :

1. Toutes les 3 heures, une GitHub Action ([`.github/workflows/relay.yml`](.github/workflows/relay.yml)) télécharge le guide et le découpe en un petit fichier JSON par chaîne, limité aux 30 heures à venir (3 Ko en moyenne). Elle les publie sur GitHub Pages ([`relay/build.py`](relay/build.py)) :
   - `https://rivallinkil.github.io/trmnl-tv-schedule/channels.json` : la liste des chaînes ;
   - `https://rivallinkil.github.io/trmnl-tv-schedule/c/<id>.json` : les programmes d'une chaîne, par exemple `c/TF1.fr.json`.
2. TRMNL interroge uniquement les fichiers des chaînes choisies (une URL de polling par chaîne, construite en Liquid dans [`src/settings.yml`](src/settings.yml)).
3. Un transform serverless choisit, pour chaque chaîne, le programme en cours et le suivant, ou la soirée ([`src/transform.py`](src/transform.py)). Il regroupe les épisodes consécutifs d'une même série et ignore les programmes courts (météo, tirages du loto, bandes-annonces).
4. Les vues affichent le tout ([`src/shared.liquid`](src/shared.liquid)).

## Développement

Utilise [trmnlp](https://github.com/usetrmnl/trmnlp) via Docker, sans Ruby :

```sh
bin/trmnlp serve   # aperçu sur http://localhost:4567
bin/trmnlp lint
bin/trmnlp test
```

Le relais ne demande que Python 3, sans dépendance :

```sh
python3 relay/build.py public                         # télécharge le guide et écrit public/
python3 relay/update_settings.py public/channels.json # met à jour la liste des chaînes dans src/settings.yml
```

La liste des chaînes proposées dans les réglages est figée dans `src/settings.yml`. Quand le guide ajoute ou retire des chaînes, relancez ces deux commandes et relisez le diff.

Les tests utilisent les fichiers de 32 chaînes du mercredi 28 octobre 2026 ([`tests/fixtures/c`](tests/fixtures/c)), décalés au jour du test.

`bin/trmnlp login` et `bin/trmnlp push` envoient le plugin sur votre compte TRMNL.

## Licence

[MIT](LICENSE)
