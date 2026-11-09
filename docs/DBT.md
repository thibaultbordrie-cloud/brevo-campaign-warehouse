# Guide du bloc 3 : dbt

## À quoi sert dbt, en une phrase
dbt range tes requêtes SQL en **modèles** qui s'appuient les uns sur les autres, les **teste** à chaque lancement et en fait une **documentation** automatique.

## Les trois couches
| Couche | Rôle | Exemple |
| --- | --- | --- |
| staging (`stg_`) | Une table source = un modèle. On renomme, on nettoie, rien de plus. | `stg_campaigns` ajoute la règle LOCAL / NATIONAL |
| intermediate (`int_`) | Étapes de calcul réutilisables. | `int_campaign_latest_snapshot` garde la photo la plus récente |
| marts (`mart_`) | Les tables finales, prêtes à lire ou à brancher sur un tableau de bord. | `mart_scope_monthly` |

Un modèle en appelle un autre avec `{{ ref('nom_du_modele') }}`, et une table chargée par Python avec `{{ source('brevo', 'nom_de_table') }}`. C'est ce qui permet à dbt de dessiner le graphe (lineage).

## Les tests
- **Standards** (dans `models/schema.yml`) : `unique`, `not_null`, `relationships` (chaque campagne d'une photo existe bien dans la table des campagnes), `accepted_values` (scope vaut LOCAL ou NATIONAL).
- **Personnalisés génériques** (dans `macros/tests/`) : `percentage_between_0_and_100`, `unique_combination`.
- **Personnalisés spécifiques** (dans `tests/`) : délivrés jamais supérieurs aux envoyés ; cliqueurs jamais supérieurs aux ouvreurs (en avertissement).

Un test dbt est une requête qui cherche les lignes **fautives**. Zéro ligne = test réussi.

## Les commandes
```
dbt.bat build                    construit tout et lance tous les tests
dbt.bat test                     lance seulement les tests
dbt.bat docs generate --static   crée transform\target\static_index.html (à ouvrir dans le navigateur)
```

## Exercices
1. Ouvre la documentation, clique sur `mart_scope_monthly`, puis sur l'icône du graphe en bas à droite : suis le chemin jusqu'aux sources.
2. Dans `stg_campaigns.sql`, ajoute une règle LOCAL de ton choix, relance `dbt.bat build` et regarde `mart_scope_monthly` changer.
3. Ajoute le test `not_null` sur la colonne `send_date` de `stg_campaigns` dans `schema.yml` et regarde s'il passe.
