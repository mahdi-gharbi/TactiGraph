"""Verified French templates; the historical English v1 renderer stays unchanged."""

FR_LABELS = {
    "final_third_entries": "Entrées dans le dernier tiers par minute",
    "field_tilt": "Part des passes complétées dans le tiers offensif",
    "passes": "Passes tentées",
    "completed_passes": "Proportion de passes complétées",
    "shots": "Tirs",
    "xg": "xG du modèle",
    "movement_xt": "xT signé des déplacements",
    "network_concentration": "Concentration des passes sortantes (HHI)",
    "network_passes": "Passes complétées incluses dans le réseau",
}
FR_LIMITS = {
    "no_causality": "Ces indicateurs ne prouvent ni une perte de contrôle ni sa cause.",
    "no_tracking": (
        "Les événements ne permettent pas d’établir les déplacements hors ballon "
        "ou la forme défensive."
    ),
    "small_window": (
        "Les réseaux sur de petites fenêtres peuvent être instables ; "
        "les positions sont des observations historiques avec ballon."
    ),
}
FR_UNITS = {
    "shots": "tirs",
    "passes": "passes",
    "expected goals": "buts attendus",
    "fraction": "proportion",
    "entries/minute": "entrées/minute",
    "signed xT": "xT signé",
    "HHI": "HHI",
}


def french_numeric_text(claim, metric):
    direction = (
        "augmente"
        if claim.after > claim.before
        else "diminue"
        if claim.after < claim.before
        else "reste identique"
    )
    unit = FR_UNITS.get(claim.unit, claim.unit)
    if claim.unit in {"shots", "passes"}:
        before, after = f"{claim.before:g}", f"{claim.after:g}"
    else:
        before, after = f"{claim.before:.4f}", f"{claim.after:.4f}"
    return f"{FR_LABELS[metric]} : {direction}, {before} → {after} {unit}."


def translate_report(report, language):
    if language != "fr":
        return report
    translated = report.model_copy(deep=True)
    for claim in translated.claims:
        if claim.kind == "limitation":
            claim.text = FR_LIMITS[claim.predicate]
        else:
            fact = next(
                f
                for f in report.evidence.before
                if f.evidence_id == claim.evidence_ids[0] and f.unit == claim.unit
            )
            claim.text = french_numeric_text(claim, fact.metric)
    translated.qualifications = report.evidence.quality_warnings + [
        "Les fenêtres utilisent des bornes propres à chaque période, début inclus et fin exclue.",
        "Les mesures indisponibles sont omises ; aucune valeur n’est remplacée par zéro.",
        "Les chiffres et les formulations sont calculés et vérifiés. "
        "La revue humaine reste en attente.",
    ]
    translated.publication_label = "Rapport vérifié automatiquement ; revue humaine en attente"
    return translated
