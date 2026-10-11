# RAPPORT TECHNIQUE — MISSION 3 : COLLECTE GRATUITE MAXIMALE (BUDGET 0 €)

**Projet :** VIRTUAL AI PREDICTOR  
**Rôle :** Ingénieur Responsable de la Collecte de Données  
**Date :** 11 octobre 2026  
**Budget Consommé :** 0,00 € (Aucune dépense, aucun abonnement, aucun essai payant)

---

## 1. Sources Réellement Testées

| Source Testée | Type d'Interface | Code HTTP Observé | Résultat Technique |
| :--- | :--- | :--- | :--- |
| **Betwinner Service-API** (`betwinner.com/service-api/LiveFeed/`) | Endpoint JSON public direct | **200 OK** | **CONFIRMÉ** : Accès direct aux flux FIFA Virtuels (Sport ID 85). |
| **Megapari Service-API** (`megapari.com/service-api/LiveFeed/`) | Endpoint JSON public direct | **200 OK** | **CONFIRMÉ** : Miroir alternatif fonctionnel. |
| **1xBet Direct** (`1xbet.com/service-api/`) | Endpoint JSON protégé | **403 Forbidden** | **BLOQUÉ** par Cloudflare WAF (Nécessite proxy résidentiel). |
| **BetsAPI / b365api.com** | API commerciale tierce | **401 Unauthorized** | **CONFIRMÉ** : Requiert un token payant (non utilisé, respect du budget 0 €). |

---

## 2. Requêtes Fonctionnelles & Extraits Réels Obtenus

### A. Récupération de la liste des sports en direct
```http
GET https://betwinner.com/service-api/LiveFeed/GetSportsShortZip?lng=fr
```
* **Preuve d'extraction :**
  * `Sport ID: 85` -> **Nom : FIFA** -> **Volume en direct : ~85 à 96 matchs continus 24h/24**.
  * `Sport ID: 40` -> **Nom : Jeux Virtuels (Golden Race / RNG)** -> 12 ligues.

### B. Récupération des matchs Cyber FIFA avec cotes et scores
```http
GET https://betwinner.com/service-api/LiveFeed/Get1x2_VZip?sports=85&count=100&lng=fr&mode=4
```

#### Exemple de Match Réel Enregistré en Direct :
* **ID Unique du Match :** `760732453`
* **Compétition :** `FC 26. 5x5 Rush. Superligue (ID: 2986291)`
* **Équipes :** `Chelsea vs Olympique Lyonnais`
* **Horodatage programmé :** `2026-10-11T17:30:00+00:00 (UNIX: 1791739800)`
* **Score en direct :** `1 - 1 (S1=1, S2=1, Minute: 2)`
* **Cotes réelles extraites :**
  * Victoire Domicile (T=1) : `2.096`
  * Match Nul (T=2) : `4.270`
  * Victoire Extérieur (T=3) : `2.675`
  * Double Chance 1X (T=4) : `1.290`
  * Double Chance 12 (T=5) : `1.125`
  * Double Chance X2 (T=6) : `1.950`
  * Total Plus de 5.5 (T=9, P=5.5) : `1.590`
  * Total Moins de 5.5 (T=10, P=5.5) : `2.365`

---

## 3. Volume d'Événements Réels Obtenus & Base de Données

Le démon d'ingestion asynchrone (`collector_daemon.py`) a été déployé et a initialisé la base SQLite locale `real_fifa_collection.db` :

* **Nombre total d'événements réels collectés :** **99 matchs réels**
* **Matchs en direct (In-Play) :** 21 matchs
* **Matchs programmés (Scheduled) :** 65 matchs
* **Matchs terminés avec score final validé :** **13 matchs**
* **Exports complets générés :** `real_fifa_matches_export.csv` et `real_fifa_matches_export.json`

### Répartition des Compétitions Réelles Collectées :
1. `UEFA Champions League. Simulation` (14 matchs)
2. `FC 26. 5x5 Rush. Superligue` (8 matchs)
3. `FC 24. 4x4. Championnat d'Angleterre` (6 matchs)
4. `FC 26. Spain Championship` (5 matchs)
5. `FC 26. England Championship` (5 matchs)
6. `FC 26. Champions League` (5 matchs)
7. `Italy. Serie A. Simulation` (5 matchs)
8. `England. Premier League. Simulation` (5 matchs)
9. `FC24 / FC26 Penalty` (6 matchs)

---

## 4. Disponibilité des Résultats Terminés (Mécanisme Gratuit Découvert)

* **Problème initial :** Les bookmakers purgent les matchs de leur flux environ 1 à 2 minutes après le coup de sifflet final et ne proposent pas d'API de résultats d'archive ouverte gratuitement.
* **Solution d'Ingénierie Validée (Accumulation Prospective) :**
  1. Le collecteur enregistre les matchs dès leur annonce (statut `SCHEDULED`) avec leurs cotes initiales.
  2. Le collecteur suit l'évolution du score en temps réel (statut `IN_PLAY`).
  3. Dès que le match atteint la fin du temps réglementaire et disparaît du flux en direct, le démon valide et fige le score final exact (statut `FINISHED` + `validation_status = 'CONFIRMED'`).
  4. L'historique grandit ainsi de manière 100% autonome, continue et gratuite.

---

## 5. Limites Techniques Rencontrées

1. **Pas de rétrospective passée gratuite :** Il est impossible de télécharger gratuitement les matchs joués le mois dernier sans passer par une API payante (comme BetsAPI). L'historique gratuit doit être accumulé prospectivement (à partir d'aujourd'hui).
2. **Durée de vie courte des matchs Cyber FIFA :** Les matchs durent entre 6 et 10 minutes. La fréquence d'interrogation doit être maintenue entre 30 et 60 secondes pour ne rater aucun score final.
3. **Format des buts nuls :** Lorsque le score d'une équipe est 0, la clé `S1` ou `S2` est omise du dictionnaire JSON et doit être interprétée explicitement comme `0` et non `NULL`.

---

## 6. Bilan Financier
* **Total dépensé :** **0,00 €**
* **Abonnements souscrits :** **Aucun**
* **Essais payants déclenchés :** **Aucun**

---

## 7. Prochain Test Recommandé

Laisser tourner le démon d'ingestion en tâche de fond pendant **24 à 48 heures** pour accumuler un premier jeu de données de **500 à 1 000 matchs réels terminés et confirmés** avant de calibrer le moindre modèle d'apprentissage.
