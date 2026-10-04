"""Small bilingual, deterministic methodology retrieval; never a source of match facts."""

import hashlib
import json
import math
import re
import unicodedata
from collections import Counter

from tactigraph.retrieval.bm25 import DocumentChunk

VERSION = "methodology-v2"
METHOD = "BM25 bilingual v2"

# Translations are paired at the topic level; this is an authored methodology corpus,
# not an independently reviewed retrieval benchmark or a general football knowledge base.
TEXTS = {
    "movement_xt": (
        (
            "Expected threat and turnovers",
            "Signed movement xT is the destination value minus "
            "the origin value for completed passes and carries. Failed passes, failed dribbles, "
            "dispossessions and miscontrols lose the origin value. Shots receive no movement "
            "credit. Actions with invalid coordinates are excluded and counted in warnings. "
            "This describes observed movements, not off-ball options or causal effects.",
        ),
        (
            "Menace attendue et pertes de balle",
            "Le xT signé des déplacements est la valeur "
            "d'arrivée moins la valeur de départ pour les passes réussies et les conduites. "
            "Les passes ratées, dribbles ratés, dépossessions et mauvais contrôles perdent la "
            "valeur de départ. Les tirs ne reçoivent aucun crédit de déplacement. Les actions "
            "aux coordonnées invalides sont exclues et signalées. Ce sont des déplacements "
            "observés, pas des options sans ballon ni des effets causaux.",
        ),
    ),
    "passes": (
        (
            "Attempted passes",
            "Pass attempts count all passes by the selected team, including "
            "unsuccessful passes. A count depends on the selected period and time bounds. "
            "Comparing unequal durations requires a stated denominator, not an invented rate.",
        ),
        (
            "Passes tentées",
            "Les tentatives de passe comptent toutes les passes de l'équipe "
            "sélectionnée, y compris les passes ratées. Le compte dépend de la période et des "
            "bornes temporelles choisies. Comparer des durées différentes exige un dénominateur "
            "explicite, pas un taux inventé.",
        ),
    ),
    "completed_passes": (
        (
            "Pass completion",
            "Pass completion is completed passes divided by attempted "
            "passes. It is reported as a fraction, not a percentage. With no pass attempts "
            "the denominator is zero and the fraction is unavailable, not zero.",
        ),
        (
            "Réussite des passes",
            "La réussite des passes est le nombre de passes réussies "
            "divisé par les passes tentées. Elle est exprimée comme une fraction, pas un "
            "pourcentage. Sans tentative, le dénominateur est nul et la fraction est "
            "indisponible ; elle ne vaut pas zéro.",
        ),
    ),
    "shots": (
        (
            "Shot counts",
            "Shots are counted in the selected period-local half-open time "
            "window. Penalty shootouts are excluded. A count of zero shots is distinct from "
            "an unavailable model prediction. Missing shot locations do not remove the shot "
            "from a count, but prevent its spatial display.",
        ),
        (
            "Nombre de tirs",
            "Les tirs sont comptés dans une fenêtre temporelle semi-ouverte "
            "de la période sélectionnée. Les séances de tirs au but sont exclues. Zéro tir "
            "est différent d'une prédiction indisponible. Un tir sans position reste compté, "
            "mais ne peut pas être affiché sur le terrain.",
        ),
    ),
    "xg": (
        (
            "Expected goals probability",
            "Expected goals, xG, estimates shot scoring "
            "probability. Window xG sums stored predictions for every shot, including "
            "separately modeled penalties. It is unavailable if any shot lacks a prediction "
            "or no evaluated model exists. Higher xG does not guarantee winning. StatsBomb "
            "xG is an external reference, not part of the controlled model comparison.",
        ),
        (
            "Buts attendus et probabilité",
            "Les buts attendus, xG, estiment la probabilité "
            "qu'un tir soit marqué. Le xG d'une fenêtre additionne les prédictions stockées "
            "de tous les tirs, penalties modélisés séparément inclus. Il est indisponible "
            "si une prédiction manque ou sans modèle évalué. Un xG supérieur ne garantit "
            "pas la victoire. Le xG StatsBomb est une référence externe à la comparaison "
            "contrôlée des modèles.",
        ),
    ),
    "final_third_entries": (
        (
            "Final-third progression",
            "Final-third entries are completed passes or carries "
            "crossing from x below 80 to x at least 80 on the 120 by 80 pitch, with both "
            "locations inside the pitch. The rate divides by selected elapsed minutes, "
            "including stoppages, not ball-in-play time.",
        ),
        (
            "Progression dans le dernier tiers",
            "Les entrées dans le dernier tiers sont les "
            "passes réussies ou conduites allant de x inférieur à 80 vers x au moins égal à "
            "80 sur un terrain de 120 par 80, avec les deux positions valides. Le taux divise "
            "par les minutes écoulées sélectionnées, arrêts de jeu inclus, pas le temps "
            "effectif avec le ballon en jeu.",
        ),
    ),
    "field_tilt": (
        (
            "Field tilt territorial share",
            "Field tilt divides the selected team's completed "
            "passes ending in the attacking third by both teams' such passes. Each event "
            "uses its team's attacking direction. Invalid endpoints are excluded. A zero "
            "denominator makes the share unavailable. Evidence includes both teams. "
            "Territorial share does not by itself establish control or explain a result.",
        ),
        (
            "Field tilt et domination territoriale",
            "Le field tilt divise les passes réussies "
            "de l'équipe finissant dans le tiers offensif par celles des deux équipes. Chaque "
            "événement utilise le sens d'attaque de son équipe. Les positions d'arrivée "
            "invalides sont exclues. Un dénominateur nul rend la part indisponible. Les "
            "preuves incluent les deux équipes. Cette part territoriale ne prouve pas à "
            "elle seule le contrôle ni la cause du résultat.",
        ),
    ),
    "network": (
        (
            "Passing network and concentration",
            "The directed passing network uses completed "
            "passes; self-passes and unknown recipients are excluded. Edges are weighted "
            "by pass count. Outgoing concentration, HHI, sums squared outgoing pass shares. "
            "Density is edges divided by n(n-1); betweenness uses inverse-count distances. "
            "Average on-ball origins and receptions are not tracking or a tactical formation. "
            "Small-window networks can be unstable.",
        ),
        (
            "Réseau de passes et concentration",
            "Le réseau orienté utilise les passes "
            "réussies ; les auto-passes et destinataires inconnus sont exclus. Le poids "
            "d'un lien est le nombre de passes. La concentration sortante HHI additionne "
            "les carrés des parts de passes sortantes. La densité divise les liens par "
            "n(n-1) ; l'intermédiarité utilise l'inverse du nombre de passes comme distance. "
            "Les positions moyennes avec ballon ne sont ni du suivi ni une formation "
            "tactique. Les réseaux de courtes fenêtres peuvent être instables.",
        ),
    ),
    "limitations": (
        (
            "Coverage and interpretation limits",
            "This application uses event data, not "
            "continuous player tracking. Event data cannot establish off-ball runs, "
            "defensive shape, unseen passing alternatives or player fatigue. Associations "
            "do not prove substitution effects or causes of winning. WSL and Premier League "
            "releases use separate datasets and model versions; results do not transfer "
            "automatically between competitions.",
        ),
        (
            "Couverture et limites d'interprétation",
            "L'application utilise des événements, "
            "pas le suivi continu des joueurs. Ils ne permettent pas d'établir les appels "
            "sans ballon, la forme défensive, les passes possibles non jouées ou la fatigue. "
            "Une association ne prouve ni l'effet d'un remplacement ni la cause d'une "
            "victoire. Les versions WSL et Premier League ont des données et modèles "
            "séparés ; leurs résultats ne se transfèrent pas automatiquement.",
        ),
    ),
    "graph": (
        (
            "Third-pass forecast cutoff",
            "Third-pass predictions estimate a later shot "
            "within the same eligible control episode. Features use only the observed "
            "prefix through the third completed pass. Future events and the final outcome "
            "are not model inputs. Historical on-ball locations are not current tracking "
            "positions. The selected serving model can be a tabular baseline.",
        ),
        (
            "Prévision après la troisième passe",
            "La prévision estime un tir ultérieur "
            "dans le même épisode de contrôle admissible. Les variables utilisent seulement "
            "le préfixe observé jusqu'à la troisième passe réussie. Les événements futurs "
            "et le résultat final ne sont pas des entrées du modèle. Les positions "
            "historiques avec ballon ne sont pas un suivi actuel. Le modèle servi peut "
            "être une référence tabulaire.",
        ),
    ),
    "windows": (
        (
            "Periods and time-window boundaries",
            "Comparison windows are chronological, "
            "non-overlapping and within one period. They are half-open: the start is "
            "included and the end excluded. Match minutes 45–60 and 60–75 correspond "
            "to period two 0–15 and 15–30. A comparison must not silently cross halftime "
            "or exceed recorded coverage. Ambiguous time bounds require clarification.",
        ),
        (
            "Périodes et bornes des fenêtres",
            "Les fenêtres comparées sont chronologiques, "
            "sans chevauchement et dans une même période. Elles sont semi-ouvertes : début "
            "inclus, fin exclue. Les minutes 45–60 et 60–75 du match correspondent à "
            "0–15 et 15–30 en deuxième période. Une comparaison ne doit pas franchir "
            "la mi-temps ni dépasser la couverture enregistrée. Des bornes ambiguës "
            "nécessitent une clarification.",
        ),
    ),
}
TOPICS = tuple(TEXTS)
STOPWORDS = set(
    "a an and are as at be by can do does for from how in is it of on or the this to "
    "what which why with un une et au aux ce ces de des du en est il la le les ou "
    "par pour que quel quelle quels quelles qui sont sur comment pourquoi dans "
    "peut sont tous tout avec se ne pas".split()
)


def normalize(value: str) -> str:
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(char)
    )


def tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", normalize(value)) if token not in STOPWORDS]


def corpus() -> list[DocumentChunk]:
    return [
        DocumentChunk(
            document_id=f"{VERSION}:{language}",
            version=VERSION,
            section=section,
            chunk_id=f"{VERSION}:{topic}:{language}",
            topic=topic,
            language=language,
            text=content,
            score=0,
        )
        for topic, translations in TEXTS.items()
        for language, (section, content) in zip(("en", "fr"), translations, strict=True)
    ]


def fingerprint() -> str:
    payload = [chunk.model_dump() for chunk in corpus()]
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    ).hexdigest()


def search(
    query: str, *, language: str = "en", topics: list[str] | None = None
) -> list[DocumentChunk]:
    """BM25 k1=1.2/b=.75; language-specific ranking, no model loading or fallback."""
    if not isinstance(query, str) or not query.strip() or len(query) > 500:
        raise ValueError("Query must contain 1–500 characters")
    if language not in {"en", "fr"}:
        raise ValueError("Language must be en or fr")
    if topics is not None and (
        not isinstance(topics, list)
        or len(topics) > 2
        or not all(isinstance(topic, str) and topic in TOPICS for topic in topics)
        or len(set(topics)) != len(topics)
    ):
        raise ValueError("Choose at most two unique supported methodology topics")
    documents = [
        chunk
        for chunk in corpus()
        if chunk.language == language and (not topics or chunk.topic in topics)
    ]
    counts = [Counter(tokens(chunk.section + " " + chunk.text)) for chunk in documents]
    lengths = [sum(count.values()) for count in counts]
    average = sum(lengths) / len(lengths)
    ranked = []
    for chunk, count, length in zip(documents, counts, lengths, strict=True):
        score = 0.0
        for token in set(tokens(query)):
            frequency = sum(token in other for other in counts)
            idf = math.log(1 + (len(documents) - frequency + 0.5) / (frequency + 0.5))
            occurrence = count[token]
            score += idf * occurrence * 2.2 / (occurrence + 1.2 * (0.25 + 0.75 * length / average))
        if score > 0:
            ranked.append(chunk.model_copy(update={"score": score}))
    return sorted(ranked, key=lambda chunk: (-chunk.score, chunk.chunk_id))[:5]
