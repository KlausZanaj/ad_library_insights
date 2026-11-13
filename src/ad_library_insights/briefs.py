"""Compose the text a user hands to their own assistant for the Analysis and Plan levels.

Nothing here calls a model. The app gathers the data with plain code and writes one
self-contained brief: the role to take, what to deliver, the rules of evidence, and
the data itself. The user pastes it into the assistant they already use, which is
also where the usage is counted.
"""
from __future__ import annotations

from . import breakeven, consumption, report

_ROLE = {
    "analysis": {
        "en": "Act as a performance marketing specialist who buys Meta ads every day. Read each ad "
              "as hook, offer, proof, audience and test.",
        "it": "Ragiona da specialista di performance marketing che compra pubblicità su Meta ogni "
              "giorno. Leggi ogni annuncio come gancio, offerta, prova, pubblico e test.",
    },
    "plan": {
        "en": "Act as a head of marketing. First diagnose the business problem (what is sold, to "
              "whom, at what price and margin, where customers are lost), then propose the fix "
              "with priorities, budget and decision rules. Do not reason as a social media manager.",
        "it": "Ragiona da responsabile marketing. Prima diagnostica il problema dell'azienda (cosa "
              "vende, a chi, a che prezzo e margine, dove perde clienti), poi proponi la soluzione "
              "con priorità, budget e criteri di decisione. Non ragionare da social media manager.",
    },
}

_TASK = {
    "analysis": {
        "en": ["Explain why this advertiser gets the reach shown below, citing the data for every claim.",
               "Copy: hooks, offers, structures and proof that repeat in the best ads.",
               "Creative: opening seconds, development and close of the videos (use the stills if attached; say so if there are none).",
               "Reach and audience: reach per day, how broad the targeting is, how reach splits by country.",
               "Testing and destinations: how fast new ads are launched, which buttons and landing pages are used."],
        "it": ["Spiega perché questo inserzionista ottiene la copertura indicata sotto, citando i dati per ogni affermazione.",
               "Testi: ganci, offerte, strutture e prove che si ripetono negli annunci migliori.",
               "Creatività: primi secondi, sviluppo e chiusura dei video (usa i fotogrammi se allegati; se mancano, dillo).",
               "Copertura e pubblico: copertura al giorno, ampiezza del pubblico, distribuzione per paese.",
               "Test e destinazioni: velocità di lancio dei nuovi annunci, bottoni e pagine di arrivo usati."],
    },
    "plan": {
        "en": ["Start with the diagnosis of my project, using the card and the competitor data below.",
               "Five ad ideas for my product, inspired by the patterns that work here. No copies.",
               "A test plan with budget and cut rules based on the break-even CPA given below.",
               "A one-page report for a manager: priorities first, then evidence, then next steps."],
        "it": ["Parti dalla diagnosi del mio progetto, usando la scheda e i dati del concorrente qui sotto.",
               "Cinque idee di annuncio per il mio prodotto, ispirate agli schemi che funzionano qui. Non copie.",
               "Un piano di test con budget e regole di spegnimento basate sul CPA di pareggio indicato sotto.",
               "Un report di una pagina per un responsabile: prima le priorità, poi le prove, poi i prossimi passi."],
    },
}

_RULES = {
    "en": ["Meta publishes no spend or sales. The longevity score (days running and copy reuse) is a clue, not proof.",
           "Reach exists only for ads delivered in the European Union or the United Kingdom. Where it is missing, say so and work from copy and dates.",
           "Reach is per ad; the same person can be counted in several ads.",
           "If the data does not support a conclusion, say what is missing instead of guessing."],
    "it": ["Meta non pubblica spesa né vendite. Il punteggio di longevità (giorni attivi e riuso del testo) è un indizio, non una prova.",
           "La copertura esiste solo per gli annunci mostrati nell'Unione europea o nel Regno Unito. Dove manca, dillo e lavora su testi e date.",
           "La copertura è per annuncio; la stessa persona può essere contata in più annunci.",
           "Se i dati non reggono una conclusione, indica cosa manca invece di tirare a indovinare."],
}

_HEAD = {"en": ("What to deliver", "Rules of evidence", "Data", "Ads", "My project", "Stills to attach"),
         "it": ("Cosa consegnare", "Regole sulle prove", "Dati", "Annunci", "Il mio progetto", "Fotogrammi da allegare")}


def _ad_lines(rank: int, ad: dict) -> list[str]:
    reach, audience = ad.get("reach") or {}, ad.get("audience") or {}
    facts = [f"score {ad['longevity_score']}", f"{ad.get('days_running')} days",
             f"copy used {ad['repetitions']}x", ad.get("media_type") or "?",
             f"button: {ad.get('cta') or 'none'}", f"destination: {ad.get('landing_domain') or 'none'}"]
    if ad.get("platforms"):
        facts.append("platforms: " + ", ".join(ad["platforms"]))
    lines = [f"{rank}. {ad.get('advertiser') or '?'} - " + "; ".join(facts)]
    if reach.get("available"):
        parts = [f"EU {reach['eu_total']:,}" if reach.get("eu_total") is not None else "",
                 f"{reach['country']} {reach['country_reach']:,}" if reach.get("country_reach") is not None else "",
                 f"UK {reach['uk_total']:,}" if reach.get("uk_total") is not None else "",
                 f"{ad['reach_per_day']:,} per day" if ad.get("reach_per_day") is not None else ""]
        lines.append("   reach: " + ", ".join(p for p in parts if p))
    elif "reach" in ad:
        lines.append("   reach: not published for this ad")
    if audience:
        places = ", ".join(p["name"] for p in audience.get("locations_included", [])[:12])
        excluded = ", ".join(p["name"] for p in audience.get("locations_excluded", [])[:8])
        lines.append(f"   audience: {audience.get('age_min')}-{audience.get('age_max')}, "
                     f"{audience.get('gender')}; locations: {places or 'n/a'}"
                     + (f"; excluded: {excluded}" if excluded else ""))
    if ad.get("needs_review"):
        lines.append("   flagged for review: long-running, single use of the copy")
    if ad.get("headline"):
        lines.append(f"   headline: {ad['headline']}")
    body = " ".join((ad.get("body") or "").split())
    lines.append(f"   copy: {body[:900] or '(no text)'}")
    return lines


def compose(level: str, result: dict, ads: int = 10, frames: bool = False,
            project: dict | None = None, lang: str = "it") -> dict:
    """The brief for ``level`` ("analysis" or "plan") built from a research result.

    Returns the text, the still frames to attach (local paths, only with ``frames``)
    and a size measure. A plan needs the project card.
    """
    if level not in ("analysis", "plan"):
        raise ValueError("level must be analysis or plan")
    if level == "plan" and not project:
        raise ValueError("the plan needs the project card")
    lang = "en" if lang == "en" else "it"
    deliver, rules, data, ads_title, project_title, stills_title = _HEAD[lang]
    chosen = result["ads"][:max(1, int(ads))]
    name = (result.get("page") or {}).get("name") or result.get("query") or ""

    out = [f"# {name} - {result.get('country') or ''}".strip(" -"), "", _ROLE[level][lang], "",
           f"## {deliver}", *[f"- {line}" for line in _TASK[level][lang]], "",
           f"## {rules}", *[f"- {line}" for line in _RULES[lang]], ""]
    if level == "plan":
        cpa = breakeven.breakeven_cpa(project["price"], project["product_cost"])
        out += [f"## {project_title}",
                f"- Product: {project['product']}",
                f"- Price: {project['price']:g}; product cost: {project['product_cost']:g}; market: {project['market']}",
                f"- Goal: {project['goal']}",
                f"- Main problem: {project['main_problem']}",
                f"- Break-even CPA: {cpa:g}. Cut an ad once it has spent {round(cpa * 2, 2):g}-{round(cpa * 3, 2):g} "
                "(2-3x break-even) with no add to cart and no sale.", ""]
    out += [f"## {data}", *report._signal_lines(result)[3:], "", f"## {ads_title} (top {len(chosen)})"]
    for rank, ad in enumerate(chosen, start=1):
        out += _ad_lines(rank, ad)
    images = [path for ad in chosen[:consumption.ADS_WITH_FRAMES] for path in ad.get("frames") or []] if frames else []
    if frames:
        out += ["", f"## {stills_title}"]
        out += [f"- {path}" for path in images] or ["- none available: work from copy and data"]
    text = "\n".join(out).strip() + "\n"
    return {"level": level, "text": text, "images": images,
            "size": consumption.measure(text, len(images), level)}
