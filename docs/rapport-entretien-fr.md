# TactiGraph AI — rapport simple pour les entretiens

*État vérifié le 26 septembre 2026. Ce document explique le projet tel qu'il existe aujourd'hui, puis propose des pistes futures. Les chiffres cités viennent des rapports et model cards du dépôt.*

## Le projet en une phrase

**TactiGraph AI est une application d'analyse du football qui transforme des événements de match en visualisations, probabilités et explications vérifiables, avec un lien vers les actions d'origine.**

Elle permet d'explorer quatre saisons de Women's Super League (WSL) et, séparément, la Premier League masculine 2015/16. Ce sont des données historiques d'événements StatsBomb Open Data : tirs, passes, lieux et instants des actions. Ce ne sont ni des données de suivi continu des joueurs ni des scores en direct.

### Une présentation orale de 45 secondes

> J'ai construit TactiGraph AI, une application de data science pour analyser des matchs de football à partir des événements StatsBomb. J'ai préparé et contrôlé les données, puis testé des modèles pour estimer la probabilité qu'un tir devienne un but, la valeur des actions qui font progresser une possession et la probabilité d'un tir après une séquence de passes. L'application montre aussi les réseaux de passes et des profils descriptifs de jeu. J'ai séparé les matchs dans le temps pour évaluer les modèles sur des matchs ultérieurs, comparé des modèles simples et complexes, et conservé les résultats négatifs. Chaque chiffre important peut être rattaché aux événements qui l'ont produit. La version locale fonctionne ; la publication publique et une revue humaine indépendante restent à faire.

## Comment fonctionne l'application ?

1. **Choisir une ligue.** En haut de l'application locale, choisir WSL ou **Premier League · 2015/16**. Les données et les modèles de ces deux ligues restent séparés.
2. **Overview / Audit.** Voir le volume de données et les contrôles de qualité. Pour la Premier League, le corpus comprend 380 matchs, 20 équipes et environ 1,31 million d'événements.
3. **Match Lab.** Choisir un match, une équipe, une période ou un joueur. Explorer la carte des tirs, les courbes temporelles, les entrées dans le dernier tiers, les réseaux de passes, les profils de jeu et les prédictions disponibles. Cliquer sur une preuve pour retrouver les événements concernés.
4. **Evidence Analyst.** Poser une question parmi les intentions guidées. Le système calcule les nombres avec des fonctions déterministes et peut utiliser un modèle de langage pour choisir ou formuler des affirmations contrôlées. Il doit s'abstenir si la preuve manque.
5. **Experiments.** Voir le protocole, les modèles comparés, les mesures sur les matchs de test et les limites de leur interprétation.

Sur Windows, le lancement local prévu est `Start-TactiGraph.cmd`. Si le navigateur affiche **Failed to fetch**, vérifier d'abord que le serveur local a bien démarré : une page ouverte ne maintient pas le serveur actif. Les journaux sont dans `output/local-server.*.log`. L'adresse locale habituelle est `http://127.0.0.1:8003/` ; le guide détaillé est à `/guide`.

## Les notions de data science, expliquées simplement

| Notion | Explication simple | Dans TactiGraph AI |
| --- | --- | --- |
| **Donnée d'événement** | Une ligne décrit une action observée : qui, quoi, où et quand. | Passes, tirs, pertes de balle et autres événements de match. La position continue de tous les joueurs entre deux actions n'est pas disponible. |
| **Pipeline de données** | Les étapes qui transforment des fichiers bruts en tables fiables. | Téléchargement d'une version précise, vérification par empreintes SHA-256, normalisation, audits, base de données et exports Parquet. |
| **Variable explicative** (*feature*) | Une information donnée au modèle avant la prédiction. | Par exemple la position et le contexte d'un tir ; le résultat du tir ne doit pas être une variable d'entrée. |
| **xG** (*expected goals*) | Probabilité estimée qu'un tir donné finisse en but. | Si un tir a xG = 0,20, le modèle lui attribue environ 20 % de chance de finir en but. Additionner les xG des tirs donne une mesure agrégée des occasions, pas le score promis du match. Les penalties sont traités séparément. |
| **Régression logistique** | Modèle simple qui transforme des variables en probabilité entre 0 et 1. | C'est le modèle xG retenu après comparaison ; sa simplicité aide à expliquer et à contrôler les résultats. |
| **xT** (*expected threat*) | Estimation de la valeur d'une action qui change l'endroit et la situation de la possession. | Une action peut créer de la valeur sans produire immédiatement un tir. Ici, la mesure dépend des suites observées historiquement ; elle ne prouve pas qu'une autre décision aurait été meilleure. |
| **Graphe de passes** | Joueurs = points ; passes observées = liens entre eux. | Il sert à voir les connexions et à analyser ce qui reste du réseau quand on retire un joueur du dessin. Cette suppression n'est pas une simulation causale d'un vrai remplacement. |
| **GNN** (*graph neural network*) | Réseau neuronal conçu pour apprendre à partir de relations entre points. | Il a été essayé pour prédire un tir après la troisième passe complétée d'une séquence. Dans ce protocole, il n'a pas apporté le gain exigé face au modèle tabulaire LightGBM : c'est un résultat négatif documenté. |
| **PCA + K-means** | La PCA résume plusieurs mesures corrélées ; K-means regroupe des observations proches. | Ces techniques décrivent quatre profils de séquences de passes sur des fenêtres de 15 minutes. Les groupes sont utiles pour explorer, mais leur séparation reste modeste et leurs noms ne sont pas une vérité tactique. |
| **RAG / recherche documentaire** | Retrouver des passages pertinents avant de rédiger une réponse. | La recherche porte sur la méthodologie du projet ; les nombres de match viennent des calculs sur les données. Un LLM n'est pas autorisé à inventer un chiffre ou une citation. |

### Pourquoi séparer les données dans le temps ?

Un modèle apprend sur les matchs d'**entraînement**, on choisit ses réglages sur les matchs de **validation/tuning**, on réserve une partie à la **calibration** éventuelle, puis on mesure le résultat final sur des matchs de **test plus tardifs**. Le but est d'éviter de « connaître l'avenir » pendant la construction du modèle. Les matchs d'une même date restent ensemble dans le découpage. La Premier League n'a été testée que sur la fin de **la même saison 2015/16** : cela ne démontre pas qu'elle marchera aussi bien la saison suivante.

Une fuite de données (*data leakage*) serait, par exemple, calculer une statistique sur toute la saison avant de couper les données puis la donner au modèle pour prédire un match antérieur. Il faut calculer chaque variable avec ce qui était réellement disponible au moment de la prédiction.

### Comment lire les résultats sans se tromper ?

- **Log loss** : mesure la qualité des probabilités ; une erreur annoncée avec beaucoup de certitude coûte cher. **Plus bas est meilleur.**
- **Score de Brier** : moyenne des carrés entre probabilité prédite et résultat réel (0 ou 1). **Plus bas est meilleur.**
- **Calibration** : parmi les événements annoncés à environ 20 %, près de 20 % devraient réellement se produire, à condition d'avoir assez de cas pour juger.
- **Bootstrap par match** : on refait les comparaisons en rééchantillonnant des matchs entiers afin de montrer l'incertitude, car les actions d'un même match sont liées entre elles.

Ces scores n'ont de sens qu'avec la **question prédite**, le **nombre de cas** et le **jeu de test**. Un score de xG et un score de prédiction après trois passes ne mesurent pas le même problème ; il ne faut pas les comparer comme un classement général. De même, les chiffres WSL et Premier League ne prouvent pas qu'une ligue serait « plus facile » à modéliser.

## Ce qui a été réalisé, concrètement

- **Données et traçabilité.** 457 matchs WSL sur quatre saisons et 380 matchs de Premier League 2015/16, à partir d'une version figée de StatsBomb Open Data. Chaque ligue a sa base, son découpage temporel et ses résultats. Les contrôles conservent la trace des fichiers sources et des anomalies, y compris deux durées négatives dans la source Premier League, signalées sans supprimer les événements.
- **Application.** API FastAPI, interface React, exploration des matchs, cartes et courbes, filtres, preuves paginées, audits et pages de résultats expérimentaux. Une démonstration guidée WSL relie désormais trois questions à leurs mesures, événements source et limites. Le démarrage local Windows a été préparé.
- **xG.** Comparaison d'une régression logistique et de LightGBM ; la régression logistique a été retenue selon la règle de choix établie avant l'accès au test. En Premier League : 1 551 tirs hors penalty sur 57 matchs de test, log loss **0,2842**, Brier **0,08125**. En WSL : 3 506 tirs hors penalty sur 132 matchs de test, log loss **0,3146**, Brier **0,0907**.
- **xT.** Modèle spatial de valeur des séquences de possession, évalué sur des matchs ultérieurs. En Premier League : 15 807 séquences éligibles, log loss **0,05256**, Brier **0,01006**. En WSL : 35 899 séquences, log loss **0,05425**, Brier **0,01068**.
- **Prédiction après trois passes.** Essai d'un GNN et comparaison avec des modèles tabulaires. Le GNN n'a pas satisfait les critères de contribution définis à l'avance ; **LightGBM** est servi dans l'application. En Premier League : 2 541 séquences de test, log loss **0,3019**, Brier **0,08462**. En WSL : 6 607 séquences, log loss **0,2491**, Brier **0,0670**.
- **Analyse et IA.** Quatre profils descriptifs de passes par ligue ; analyse de sensibilité du réseau de passes ; assistant guidé avec chiffres vérifiés. L'évaluation automatique de 60 cas tactiques WSL est réussie, mais la revue sémantique indépendante reste à faire. La recherche méthodologique obtient Recall@5 **96,7 %**, mais MRR@5 **77,4 %**, sous son objectif de 80 %. Les validations de l'assistant WSL ne valent pas validation Premier League.
- **Préparation M8.** Une version candidate pour publication a été préparée localement, avec conteneurs, procédure de restauration et 36 rapports pré-calculés pour 12 matchs WSL. Une grille figée de 12 rapports est prête pour un premier examen humain indépendant ; aucune note humaine n'a encore été attribuée. L'application n'est **pas encore publiée sur Internet**.

## Ce qui reste à faire

**Pour terminer la publication M8 :** obtenir une revue humaine indépendante des 36 rapports, vérifier les droits de publication et l'attribution StatsBomb, puis créer le dépôt distant et l'hébergement si la décision de publier est prise. Mesurer enfin les coûts et vérifier le fonctionnement sur la vraie adresse publique. La base Premier League locale n'est pas incluse automatiquement dans ce mode public.

**Pour renforcer la valeur scientifique :** faire évaluer les réponses de l'analyste par des personnes indépendantes ; améliorer la recherche méthodologique qui manque sa cible ; créer un jeu d'évaluation propre à la Premier League ; et, surtout, tester la généralisation sur une **autre saison** ou une autre compétition disponible légalement. Les résultats actuels restent solides pour leurs protocoles, mais ces tests supplémentaires éviteraient de généraliser au-delà des données observées.

**Pour l'entretien :** préparer une démonstration de trois minutes sur un match, une page de résultats reproductibles et une explication honnête du résultat négatif du GNN. C'est souvent plus convaincant qu'ajouter un modèle complexe sans question claire.

## Trois améliorations simples, par ordre de valeur

1. **Une page « Pourquoi cette prédiction ? »** Afficher sur un tir les variables utilisées, la probabilité xG, le modèle, la date du test et les limites. Cela transforme un chiffre en explication utilisable.
2. **Un mini-banc d'essai humain.** Faire noter à deux ou trois personnes une sélection figée de réponses de l'analyste : exactitude, utilité et preuve. Publier les erreurs et les corrections, pas seulement les réussites.
3. **Une vraie démonstration publique courte.** Après revue et vérification des droits, montrer trois matchs sélectionnés, une question tactique et la preuve correspondante. Ajouter une courte vidéo et un README qui permet de reproduire les résultats sans exposer les données brutes ou des secrets.

Une amélioration de recherche plus ambitieuse serait un **test hors saison**. Elle a davantage de valeur qu'un nouveau modèle spectaculaire si elle permet de vérifier ce qui se généralise réellement.

## Utiliser Claude Opus 5.5 avec GPT-6 Sol

Les deux modèles peuvent travailler sur **le développement et l'audit du projet**, sans être tous deux intégrés dans l'application. C'est une méthode de travail proposée, pas un résultat expérimental montrant qu'un modèle serait supérieur à l'autre. Les deux modèles existent dans les offres documentées par [Anthropic](https://www.anthropic.com/claude-opus-5-5) et [OpenAI](https://developers.openai.com/api/docs/models/gpt-6-sol) ; l'accès et le coût dépendent de vos abonnements ou de l'API utilisée.

**Répartition pratique :** confier à GPT-6 Sol une tâche d'implémentation bornée, avec fichiers visés et critères d'acceptation. Donner ensuite à Claude Opus 5.5 le protocole, le code et les résultats pour une **revue indépendante** : chercher les fuites temporelles, les affirmations trop fortes, les bugs, les trous dans les tests et les faiblesses de la démonstration. Faire corriger les observations vérifiées, relancer les tests, puis demander une seconde revue ciblée. Si les deux travaillent en parallèle, utiliser des branches ou worktrees séparés et fusionner après vérification humaine.

**Prompt à donner à Claude Opus 5.5 :**

> Tu es relecteur indépendant d'un projet data science de football. Lis `README.md`, `docs/premier-league.md`, les quatre model cards et les rapports d'expériences. Cherche 10 problèmes concrets maximum : fuite de données, métrique mal interprétée, affirmation causale injustifiée, preuve manquante, défaut de reproductibilité ou de démonstration. Pour chaque problème, donne le fichier, la ligne ou le résultat concerné, son impact et un test qui permettrait de le vérifier. N'invente pas de résultat et distingue erreur démontrée, risque et préférence.

**Prompt à donner à GPT-6 Sol après la revue :**

> Prends seulement les observations étayées du rapport de revue ci-joint. Corrige-les une par une dans le projet, ajoute les tests nécessaires, exécute les contrôles adaptés et mets à jour la documentation. Ne change pas les résultats publiés sans nouveau protocole et n'annonce aucune métrique que tu n'as pas mesurée. Présente le diff, les commandes exécutées et les limites restantes.

**Prompt pour vous entraîner à l'entretien, dans l'un ou l'autre modèle :**

> Interroge-moi comme un recruteur data science sur TactiGraph AI. Pose une question à la fois, du niveau débutant au niveau avancé : xG, découpage temporel, calibration, GNN négatif, preuves, limites et déploiement. Après ma réponse, indique ce qui est correct, ce qui est imprécis et une réponse orale de 30 secondes. Empêche-moi de revendiquer un résultat absent du rapport.

Le point décisif est de garder **un seul dossier de preuves** : protocole figé, commandes de reproduction, résultats, captures de démonstration et limites. Les assistants peuvent coder, critiquer et reformuler ; les chiffres et les conclusions doivent venir des exécutions réelles et rester explicables par vous.

## Questions probables en entretien

**« Pourquoi ne pas utiliser directement le modèle le plus complexe ? »** — Parce que la complexité doit apporter un gain mesuré. Ici, le GNN n'a pas dépassé le modèle tabulaire selon les critères fixés avant le test. Je montre ce résultat et je conserve LightGBM.

**« Le xG prédit-il le score final ? »** — Non. Il estime la probabilité de but de chaque tir ; leur somme résume la qualité des occasions selon le modèle. Elle ne garantit aucun score.

**« Comment avez-vous évité de tricher avec les données ? »** — Les matchs sont séparés chronologiquement par date et les choix de modèles sont faits avant de regarder le test final. Les variables doivent être disponibles au moment où la prédiction est calculée.

**« L'assistant IA invente-t-il ses chiffres ? »** — L'objectif du système est que les nombres viennent de fonctions analytiques et de sources identifiées. Le modèle de langage, lorsqu'il est utilisé, choisit ou formule des affirmations contrôlées. Une revue indépendante de la qualité sémantique reste à faire.

**« Vos profils de jeu sont-ils de vraies catégories tactiques ? »** — Non. Ce sont des regroupements descriptifs de fenêtres de passes. Ils aident à explorer les matchs, mais la séparation statistique est modeste et une validation par des analystes serait nécessaire pour leur donner des noms tactiques forts.

**« Peut-on conclure qu'en retirant un joueur l'équipe jouerait moins bien ? »** — Non. La fonction supprime ce joueur d'un réseau de passes *observé* et mesure comment la connectivité du dessin change. Elle ne simule pas les décisions des autres joueurs ni un match alternatif.

**« Est-ce déjà en production ? »** — L'application fonctionne localement et une version candidate au déploiement existe. La revue indépendante, les vérifications de publication et l'hébergement public restent à faire.

**« Quelle a été votre contribution personnelle si vous avez utilisé des assistants IA ? »** — Décrivez précisément ce que vous avez décidé, vérifié et compris : question de recherche, règles de séparation temporelle, critères de choix, contrôle des résultats, expérience utilisateur et limites. Soyez transparent sur l'aide au code ; montrez que vous savez reproduire et défendre chaque conclusion.

## Formulation possible sur un CV

> **TactiGraph AI — projet de data science appliquée au football.** Construction d'un pipeline reproductible pour 837 matchs historiques StatsBomb (457 WSL et 380 Premier League), développement et comparaison de modèles xG/xT/prédiction de séquences, et application FastAPI/React avec preuves remontant aux événements. Évaluation temporelle, calibration, intervalles bootstrap et publication explicite d'un résultat GNN négatif. Version locale opérationnelle ; publication publique en préparation.

Adaptez ce texte à votre contribution réelle et à la place disponible. En entretien, **racontez une décision technique que vous pouvez défendre** — par exemple pourquoi la régression logistique a été gardée pour le xG ou pourquoi le GNN n'a pas été retenu — puis montrez le résultat et sa limite.

## Où vérifier les détails

- `README.md` : fonctions disponibles et démarrage local.
- `docs/roadmap.md` : état des jalons M1 à M8.
- `docs/premier-league.md` : données, protocole et résultats Premier League.
- `docs/xg-model-card.md`, `docs/xt-model-card.md`, `docs/graph-model-card.md`, `docs/styles-model-card.md` : méthodes et limites des modèles.
- `docs/analyst-workflow.md` : fonctionnement et évaluation de l'analyste.
- `docs/public-release.md` : ce qui manque avant la publication publique.
