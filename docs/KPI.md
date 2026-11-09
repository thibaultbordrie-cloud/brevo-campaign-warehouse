# Dictionnaire des KPI

Une seule formule par indicateur, partout. Source : API Brevo, statistiques globales de campagne.

| Indicateur | Formule | Colonne dans v_campaign_kpis |
| --- | --- | --- |
| Délivrés | envoyés − rebonds | delivered |
| Taux d'ouverture | ouvreurs uniques ÷ délivrés | open_rate_pct |
| Taux de clic | cliqueurs ÷ délivrés | click_rate_pct |
| CTOR | cliqueurs ÷ ouvreurs uniques | ctor_pct |
| Taux de désinscription | désinscrits ÷ délivrés | unsub_rate_pct |

Les ouvertures automatiques Apple sont stockées à part (`apple_mpp_opens`). Vérifié le 21/10/2026 (analyse 09) : chez Brevo, `uniqueViews` est égal à `trackableViews`, donc **le taux d'ouverture exclut déjà les ouvertures automatiques Apple**. `apple_mpp_opens` compte des ouvertures, pas des personnes : il ne se compare pas aux ouvreurs uniques.

## Périmètre local / national (colonne `scope`)

Une campagne est **LOCAL** si son nom commence par `LOCAL`, contient `_STORE_` ou contient « fermeture » (fermeture de magasin). Sinon elle est **NATIONAL**. La règle est écrite une seule fois, dans `v_campaign_kpis`, et testée dans `tests/test_ingest.py`. Si une nouvelle convention de nommage apparaît, on l'ajoute là, et toutes les analyses en profitent.

## Listes de contacts

| Indicateur | Source | Colonne |
| --- | --- | --- |
| Abonnés | totalSubscribers, ou uniqueSubscribers quand Brevo laisse le total à 0 (cas observé avec l’API Brevo) | subscribers (v_list_size) |
| Contacts en liste noire | totalBlacklisted | total_blacklisted |
| Variation sur un jour | différence avec la photo précédente | change_subscribers, change_blacklisted (v_list_growth) |

Attention : additionner les abonnés de toutes les listes compte plusieurs fois un contact inscrit à plusieurs listes.
