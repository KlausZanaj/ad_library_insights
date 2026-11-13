"""Compose what a user hands to their own assistant for the Analysis and Plan levels.

Nothing here calls a model. The app gathers the data with plain code and writes:

* one self-contained brief (role, method, what to deliver, rules of evidence, and the
  data itself) that works in a single pass in any assistant;
* a data pack with one file per specialist (see ``packs``), for clients that can run
  sub-agents: each specialist reads only its own slice.

The Analysis reads the advertiser through four lenses: copy, creative, reach and
audience, testing and destinations. The Plan adds the user's own project: diagnosis
first, then ad ideas, a test plan built on break-even numbers, and a one-page report.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import breakeven, consumption, packs

LEVELS = ("analysis", "plan")
IDEAS = 5                          # ad ideas in a plan, and ads in the first test round
TEST_MULTIPLIER = 2.5              # spend allowed per test ad, in break-even CPAs (range 2-3)

_T = {
    "en": {
        "language": "Write in English.",
        "role.analysis": (
            "Act as a performance marketing specialist: someone who buys Meta ads every day and reads "
            "an ad as hook, offer, proof, audience and test. Do not reason as a social media manager: "
            "this is about why advertising pays, not about running profiles."),
        "goal.analysis": (
            "Explain why {name} gets the reach shown in the data. Every claim must rest on a number or "
            "a quote from the data below, with the ad id. A generic summary is of no use."),
        "method.title": "How to work",
        "method.intro": (
            "Go through the data in four passes, one at a time. For each pass note at most five "
            "findings as: finding · evidence (number or quote, with ad id) · how solid it is (high, medium, low)."),
        "lens": [
            "Copy (section Copy). Which hooks open the longest-running ads, which offer and which proof "
            "they carry, which structures repeat, and what separates texts reused many times from texts used once.",
            "Creative (section Creative). For videos: what happens in the first seconds, how it develops, "
            "how it closes. Look at the attached stills (start, middle, end) and thumbnails. If there are no "
            "stills, say so in one line and work from thumbnails, formats and copy.",
            "Reach and audience (section Reach and audience). Reach per day, how broad the audience is "
            "(age, gender, locations), the split by country, and what differs between ads that reach many "
            "people and ads that reach few.",
            "Testing and destinations (section Testing and destinations). How many new ads a week, how "
            "many survive, which buttons and landing pages, and what that pace says about how they test.",
        ],
        "deliver.title": "What to deliver",
        "deliver.analysis": [
            "The answer in two lines: why {name} gets this reach.",
            "The causes, heaviest first (three to five). For each: what they do, the evidence, how solid it is.",
            "The findings of the four passes, as four short lists.",
            "What this data cannot tell.",
            "Three things to test or verify, in order of priority.",
        ],
        "rules.title": "Rules of evidence",
        "rules": [
            "Meta publishes no spend and no sales. The longevity score (days running and copy reuse) is a clue, not proof.",
            "Reach exists only for ads delivered in the European Union or the United Kingdom. Where it is "
            "missing, say so and work from copy and dates.",
            "Reach is per ad, and for a group of ads sharing one text it is the reach of one of them. "
            "Summed over ads, the same person can be counted more than once.",
            "Hook, promise and proof labels in the data were assigned by rules: correct them when the text says otherwise.",
            "If the data does not support a conclusion, say what is missing instead of guessing.",
        ],
        "role.plan": (
            "Act as a head of marketing. Diagnose first, then propose. The diagnosis starts from my "
            "project: what I sell, to whom, at what price, with what margin, and where on the way to "
            "purchase I lose customers. The proposal has priorities, a budget and decision rules. Do not "
            "reason as a social media manager: no content calendar is needed."),
        "steps.title": "Steps",
        "steps": [
            "Diagnosis of my project. Use the card \"My project\" and the numbers computed below. In a few "
            "lines: margin per order, how much one purchase may cost, and where I most likely lose "
            "customers given the problem I named. Separate what the data shows from what you assume, and "
            "for each assumption say how to check it.",
            "What {name} does. Read the data in the four passes (copy, creative, reach and audience, "
            "testing and destinations) and keep only what matters for my case.",
            "Five ad ideas for my product, inspired by the patterns that hold in the data. Not copies: no "
            "sentences, brand names or promises of the competitor. For each idea: angle; the pattern it "
            "borrows (with ad id); hook (first line or first three seconds); development in three points; "
            "proof to show; format; button and landing page; what it tests.",
            "Test plan. Use the section \"Numbers for the test\": budget per ad, budget of the first round, "
            "cut rule. Add: how many ads to run together, for how many days, what to look at each day, "
            "when to cut, when to raise the budget, and what to do if nothing holds.",
            "Report for whoever decides: one page. On top the decision asked for and the three priorities; "
            "then the numbers behind them; then risks and what we do not know; at the bottom the next "
            "seven days, with who does what.",
        ],
        "deliver.plan": (
            "Deliver in this order: the report (step 5) first, then the ad ideas (3), the test plan (4), "
            "and the diagnosis (1) and competitor reading (2) as an appendix. Whoever decides reads the first page only."),
        "project.title": "My project",
        "project": ["Product", "Selling price", "Product cost", "Market", "Goal", "Main problem"],
        "numbers.title": "Numbers for the test",
        "numbers": [
            "Margin per order (price minus product cost): {margin}",
            "Break-even CPA, the most one purchase may cost in ads: {cpa}. Break-even ROAS: {roas}",
            "Cut rule: switch an ad off once it has spent {cut_low} to {cut_high} (2 to 3 times break-even "
            "CPA) with no add to cart and no sale",
            "Budget per test ad: up to {per_ad} ({multiplier} times break-even CPA)",
            "First round with {ideas} ads: up to {round_total}",
            "These numbers use product cost only. If shipping, payment fees or returns are not in that "
            "cost, the real break-even is lower: say so in the plan.",
        ],
        "data.title": "Data",
        "attach.title": "Pictures to attach",
        "attach.none": "none: say that the creative reading is based on formats and copy only",
    },
    "it": {
        "language": "Scrivi in italiano.",
        "role.analysis": (
            "Ragiona da specialista di performance marketing: una persona che compra pubblicità su Meta "
            "ogni giorno e legge un annuncio come gancio, offerta, prova, pubblico e test. Non ragionare da "
            "social media manager: qui si capisce perché una pubblicità rende, non si gestiscono profili."),
        "goal.analysis": (
            "Spiega perché {name} ottiene la copertura che vedi nei dati. Ogni affermazione deve poggiare "
            "su un numero o su una citazione presa dai dati qui sotto, con l'id dell'annuncio. Una sintesi "
            "generica non serve."),
        "method.title": "Come lavorare",
        "method.intro": (
            "Leggi i dati in quattro passaggi, uno per volta. Per ogni passaggio annota al massimo cinque "
            "osservazioni così: osservazione · prova (numero o citazione, con id dell'annuncio) · quanto è "
            "solida (alta, media, bassa)."),
        "lens": [
            "Testi (sezione Copy). Quali ganci aprono gli annunci più longevi, quale offerta e quale prova "
            "portano, quali strutture si ripetono, e cosa distingue i testi riusati molte volte da quelli usati una volta.",
            "Creatività (sezione Creative). Per i video: cosa succede nei primi secondi, come si sviluppa, "
            "come chiude. Guarda i fotogrammi allegati (inizio, metà, fine) e le miniature. Se i fotogrammi "
            "non ci sono, dillo in una riga e lavora su miniature, formati e testi.",
            "Copertura e pubblico (sezione Reach and audience). Copertura al giorno, ampiezza del pubblico "
            "(età, genere, luoghi), distribuzione per paese, e cosa cambia tra gli annunci che raggiungono "
            "molte persone e quelli che ne raggiungono poche.",
            "Test e destinazioni (sezione Testing and destinations). Quanti annunci nuovi a settimana, "
            "quanti sopravvivono, quali bottoni e quali pagine di arrivo, e cosa dice quel ritmo su come testano.",
        ],
        "deliver.title": "Cosa consegnare",
        "deliver.analysis": [
            "La risposta in due righe: perché {name} ottiene questa copertura.",
            "Le cause, dalla più pesante alla meno pesante (da tre a cinque). Per ognuna: cosa fanno, la prova, quanto è solida.",
            "Le osservazioni dei quattro passaggi, in quattro elenchi brevi.",
            "Cosa questi dati non possono dire.",
            "Tre cose da provare o verificare, in ordine di priorità.",
        ],
        "rules.title": "Regole sulle prove",
        "rules": [
            "Meta non pubblica spesa né vendite. Il punteggio di longevità (giorni attivi e riuso del testo) è un indizio, non una prova.",
            "La copertura esiste solo per gli annunci mostrati nell'Unione europea o nel Regno Unito. Dove "
            "manca, dillo e lavora su testi e date.",
            "La copertura è per annuncio, e per un gruppo di annunci con lo stesso testo è quella di uno "
            "solo. Sommata su più annunci, la stessa persona può essere contata più volte.",
            "Le etichette hook, promise e proof nei dati sono assegnate da regole: correggile quando il testo dice altro.",
            "Se i dati non reggono una conclusione, indica cosa manca invece di tirare a indovinare.",
        ],
        "role.plan": (
            "Ragiona da responsabile marketing. Prima diagnostica, poi proponi. La diagnosi parte dal mio "
            "progetto: cosa vendo, a chi, a che prezzo, con che margine, e in che punto del percorso "
            "d'acquisto perdo clienti. La proposta ha priorità, budget e criteri di decisione. Non ragionare "
            "da social media manager: non serve un piano editoriale."),
        "steps.title": "Passaggi",
        "steps": [
            "Diagnosi del mio progetto. Usa la scheda «Il mio progetto» e i numeri calcolati sotto. In poche "
            "righe: margine per ordine, quanto può costare un acquisto, e dove è più probabile che io perda "
            "clienti dato il problema che ho indicato. Distingui ciò che i dati mostrano da ciò che ipotizzi, "
            "e per ogni ipotesi di' come verificarla.",
            "Cosa fa {name}. Leggi i dati nei quattro passaggi (testi, creatività, copertura e pubblico, "
            "test e destinazioni) e tieni solo ciò che serve al mio caso.",
            "Cinque idee di annuncio per il mio prodotto, ispirate agli schemi che reggono nei dati. Non "
            "copie: niente frasi, marchi o promesse del concorrente. Per ogni idea: angolo; schema a cui si "
            "ispira (con id dell'annuncio); gancio (prima riga o primi tre secondi); sviluppo in tre punti; "
            "prova da mostrare; formato; bottone e pagina di arrivo; cosa mette alla prova.",
            "Piano di test. Usa la sezione «Numeri per il test»: budget per annuncio, budget del primo giro, "
            "regola di spegnimento. Aggiungi: quanti annunci accendere insieme, per quanti giorni, cosa "
            "guardare ogni giorno, quando spegnere, quando aumentare il budget, e cosa fare se nessuno regge.",
            "Report per chi decide: una pagina. In alto la decisione richiesta e le tre priorità; poi i "
            "numeri che le sostengono; poi i rischi e ciò che non sappiamo; in fondo i prossimi sette giorni, "
            "con chi fa cosa.",
        ],
        "deliver.plan": (
            "Consegna in questo ordine: prima il report (passaggio 5), poi le idee di annuncio (3), il piano "
            "di test (4), e in appendice la diagnosi (1) e la lettura del concorrente (2). Chi decide legge "
            "solo la prima pagina."),
        "project.title": "Il mio progetto",
        "project": ["Prodotto", "Prezzo di vendita", "Costo del prodotto", "Mercato", "Obiettivo", "Problema principale"],
        "numbers.title": "Numeri per il test",
        "numbers": [
            "Margine per ordine (prezzo meno costo del prodotto): {margin}",
            "CPA di pareggio, il massimo che un acquisto può costare in pubblicità: {cpa}. ROAS di pareggio: {roas}",
            "Regola di spegnimento: spegni un annuncio quando ha speso da {cut_low} a {cut_high} (da 2 a 3 "
            "volte il CPA di pareggio) senza aggiunte al carrello né vendite",
            "Budget per annuncio in test: fino a {per_ad} ({multiplier} volte il CPA di pareggio)",
            "Primo giro con {ideas} annunci: fino a {round_total}",
            "Questi numeri usano solo il costo del prodotto. Se spedizione, commissioni di pagamento o resi "
            "non sono in quel costo, il pareggio reale è più basso: scrivilo nel piano.",
        ],
        "data.title": "Dati",
        "attach.title": "Immagini da allegare",
        "attach.none": "nessuna: scrivi che la lettura delle creatività si basa solo su formati e testi",
    },
}


def test_numbers(project: dict, ideas: int = IDEAS, multiplier: float = TEST_MULTIPLIER) -> dict:
    """Break-even and test budget from the project card, by plain arithmetic."""
    cpa = breakeven.breakeven_cpa(project["price"], project["product_cost"])
    if cpa <= 0:
        raise ValueError("the product cost leaves no margin: no test budget can be computed")
    return {
        "margin": round(project["price"] - project["product_cost"], 2),
        "cpa": cpa,
        "roas": round(project["price"] / cpa, 2),
        "cut_low": round(cpa * 2, 2),
        "cut_high": round(cpa * 3, 2),
        "per_ad": round(cpa * multiplier, 2),
        "round_total": round(cpa * multiplier * ideas, 2),
        "multiplier": multiplier,
        "ideas": ideas,
    }


def _demote(text: str, levels: int = 2) -> str:
    """Push the headings of a data slice below the headings of the brief."""
    return "\n".join("#" * levels + line if line.startswith("#") else line for line in text.splitlines()) + "\n"


def _money(value) -> str:
    return f"{value:,.2f}".rstrip("0").rstrip(".") if isinstance(value, float) else str(value)


def project_section(project: dict, lang: str) -> str:
    """The project card and the numbers computed from it, as Markdown."""
    words = _T[lang]
    numbers = {key: _money(value) for key, value in test_numbers(project).items()}
    values = [project["product"], _money(float(project["price"])), _money(float(project["product_cost"])),
              project["market"], project["goal"], project["main_problem"]]
    lines = [f"## {words['project.title']}", *[f"- {label}: {value}" for label, value in zip(words["project"], values)],
             "", f"## {words['numbers.title']}", *[f"- {line.format(**numbers)}" for line in words["numbers"]]]
    return "\n".join(lines) + "\n"


def instructions(level: str, name: str, lang: str = "it") -> str:
    """Role, method, deliverables and rules for a level, without any data."""
    words = _T[lang]
    out = [words[f"role.{level}"], ""]
    if level == "analysis":
        out += [words["goal.analysis"].format(name=name), "", f"## {words['method.title']}", words["method.intro"],
                *[f"{n}. {line}" for n, line in enumerate(words["lens"], start=1)], "",
                f"## {words['deliver.title']}", words["language"],
                *[f"{n}. {line.format(name=name)}" for n, line in enumerate(words["deliver.analysis"], start=1)]]
    else:
        out += [f"## {words['steps.title']}",
                *[f"{n}. {line.format(name=name)}" for n, line in enumerate(words["steps"], start=1)], "",
                f"## {words['method.title']}", words["method.intro"],
                *[f"{n}. {line}" for n, line in enumerate(words["lens"], start=1)], "",
                f"## {words['deliver.title']}", words["language"], words["deliver.plan"]]
    out += ["", f"## {words['rules.title']}", *[f"- {line}" for line in words["rules"]]]
    return "\n".join(out) + "\n"


def compose(level: str, result: dict, ads: int = 10, frames: bool = False,
            project: dict | None = None, lang: str = "it") -> dict:
    """The single-pass brief for ``level``, with the data inside.

    Returns the text, the pictures to attach (local paths: thumbnails always, video
    stills only with ``frames``), the data slices and a size measure. A plan needs
    the project card.
    """
    if level not in LEVELS:
        raise ValueError("level must be analysis or plan")
    if level == "plan" and not project:
        raise ValueError("the plan needs the project card")
    lang = "en" if lang == "en" else "it"
    words = _T[lang]
    name = packs.subject_name(result)
    slices, images = packs.sections(result, ads, frames)
    if not frames:
        images = []                       # thumbnails stay on disk; nothing is sent as a picture

    parts = [f"# {name} · {result.get('country') or ''}".rstrip(" ·"), "", instructions(level, name, lang)]
    if level == "plan":
        parts += [project_section(project, lang)]
    parts += [f"## {words['data.title']}", ""]
    parts += [_demote(slices[key]) for key in packs.SLICES]
    parts += [f"## {words['attach.title']}",
              *([f"- {path}" for path in images] or [f"- {words['attach.none']}"])]
    text = "\n".join(parts).strip() + "\n"
    return {"level": level, "text": text, "images": images, "slices": slices,
            "ads": min(max(1, int(ads)), len(result["ads"])), "frames": bool(frames),
            "size": consumption.measure(text, len(images), level)}


def prepare(level: str, result: dict, ads: int = 10, frames: bool = False, project: dict | None = None,
            lang: str = "it", directory: Path | None = None, today: date | None = None) -> dict:
    """Compose the brief and save the data pack next to it.

    The pack folder holds the brief, one data file per specialist and, for a plan, the
    project card with its numbers. Returns the brief plus the folder and file paths.
    """
    made = compose(level, result, ads, frames, project, lang)
    extra = {"project": project_section(project, "en" if lang == "en" else "it")} if level == "plan" else None
    saved = packs.write(result, level, made.pop("slices"), made["images"], made["text"], extra,
                        directory, today, ads=made["ads"])
    return {**made, **saved}
