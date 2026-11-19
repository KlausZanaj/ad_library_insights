"""Compose what a user hands to their own assistant for the Analysis and Plan levels.

Nothing here calls a model. The app gathers the data with plain code and writes:

* one self-contained brief (role, method, what to deliver, rules of evidence, and the
  data itself) that works in a single pass in any assistant;
* a data pack with one file per specialist (see ``packs``), for clients that can run
  sub-agents: each specialist reads only its own slice.

The Analysis reads the advertiser through four lenses: copy, creative, reach and
audience, testing and destinations. The Plan adds the user's own project: diagnosis
first, then a tracking check, ad ideas, a campaign structure, a test plan built on
break-even numbers, and a one-page report. Every number of the plan that can be
computed is computed here, by arithmetic, and handed over ready.
"""
from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path

from . import breakeven, consumption, packs
from .lab import precheck

LEVELS = ("analysis", "plan")
IDEAS = 5                          # ad ideas in a plan, and ads in the first test round
TEST_MULTIPLIER = 2.5              # spend allowed per test ad, in break-even CPAs (range 2-3)
TEST_SHARE = 0.2                   # rule of thumb: the part of ad spend kept for testing new ads

_ORDERS = re.compile(r"(?<![\d.,])(\d+(?:[.,]\d+)*)\s*(?:ordini|ordine|orders?|vendite|vendita|sales?|acquisti|acquisto|"
                     r"purchases?)\b(?=(.{0,24}))", re.I)
# the period is read only when it comes right after the noun, as a whole word and with no figure in
# between: "a day", "al mese", "/week", "per month". "in 30 giorni", "ogni 2 giorni", "by Friday" are not read.
_PERIOD = re.compile(r"^\s*(?:/|al|alla|allo|a|an|per|ogni|each|every|il|la)?\s*(?:"
                     r"(?P<day>giorno|giornalier[ie]|dì|gg|day|daily)|"
                     r"(?P<week>settimana|settimanal[ie]|week|weekly)|"
                     r"(?P<month>mese|mensil[ie]|month|monthly))(?![\w-])", re.I)
_SPANS = {"day": 1, "week": 7, "month": 30}
# the goal is read only when the figure of orders is the one figure in it. Others are let through only when
# they are plainly something else: money, a percentage, a ROAS, a year, a deadline ("entro 3 mesi").
_FIGURE = re.compile(r"\d+(?:[.,]\d+)*")
_OTHER_AFTER = re.compile(r"^\s*(?:%|€|\$|euro\b|eur\b|usd\b)", re.I)
_SPAN_AFTER = re.compile(r"^\s*(?:giorni|settimane|mesi|anni|days|weeks|months|years)\b", re.I)
_OTHER_BEFORE = re.compile(r"(?:€|\$|\b(?:roas|roi|cpa|aov)\s*(?:di|of|a|at|=|:)?)\s*$", re.I)
_DEADLINE = re.compile(r"\b(?:in|entro|within|tra|fra)\s+$", re.I)
# an increase or a multiple is not a total: "+20 orders a day", "altri 20", "raddoppiare i 20 ordini"
_CHANGE = re.compile(r"\+\s*\d|\b(?:aument\w*|increas\w*|più|piu|more|altri|other|additional|ulteriori|extra|"
                     r"raddoppi\w*|doubl\w*|tripl\w*|quadrupl\w*|volte|times|ridu\w*|reduc\w*|meno|less|fewer)\b", re.I)
# after the period the goal ends, or goes on with a comma or a plain connector; "lavorativo", "nel weekend",
# "per 4 negozi" change what the figure means
_TAIL = re.compile(r"^\s*(?:$|[.!,;:)]|(?:entro|by|within|con|with|e|ed|and|senza|without|mantenendo|while|"
                   r"(?:in|tra|fra)\s+\d)\b)", re.I)

_T = {
    "en": {
        "language": "Write in English.",
        "role.analysis": (
            "You work as a performance marketing specialist on Meta: you read an ad as hook, offer, proof, "
            "audience and test, and you look for the reasons an ad keeps being paid for."),
        "goal.analysis": (
            "Explain why {name} gets the reach shown in the data. Every claim must rest on a number or "
            "a quote from the data below, with the ad id. A summary that would fit any advertiser is of no use."),
        "goal.analysis.noreach": (
            "Explain what {name} runs, what it keeps on air and how it tests. Reach in the country searched is "
            "not published: how many people these ads reach is not known. Say so in your first lines and build on "
            "the order of Meta's list, the dates and the creatives. Every claim must rest on a number or a quote "
            "from the data below, with the ad id. A summary that would fit any advertiser is of no use."),
        "method.title": "How to work",
        "method.intro": (
            "Go through the data in four passes, one at a time. For each pass note at most five "
            "findings as: finding · evidence (number or quote, with ad id) · how solid it is (high, medium, low). "
            "Then cross the passes: a fact confirmed by two passes or more weighs more, and you write next to it "
            "which passes confirm it. A fact seen in one pass only stays, marked \"one pass only\"."),
        "lens": [
            "Copy (section Copy). Which hooks open the ads that scale or hold, which offer and which proof "
            "they carry, which structures repeat, and what separates texts carried by many creatives from texts "
            "on a single one. Give every ad a type from the list in \"Ad types\", judging from the text.",
            "Creative (section Creative). For videos: what happens in the first seconds, how it develops, "
            "how it closes. Look at the attached stills (start, middle, end) and pictures. Give every ad a type "
            "from the list in \"Ad types\", judging from what you see. If there are no pictures, say so in one "
            "line and work from formats and copy.",
            "Reach and audience (section Reach and audience). People reached and reach per day, how broad the "
            "audience is (age, gender, locations), and what differs between ads that reach many people and ads "
            "that reach few. Then localisation (section Languages and countries): languages of the texts against "
            "countries reached. One ad translated or different ads per country, and where delivery really goes.",
            "Testing and destinations (section Testing and destinations). How many new ads a week, which buttons "
            "and landing pages. Survival: compare only ads of the same age. Use the table under Survival when it "
            "is there; when it says NOT MEASURABLE, write that it cannot be measured yet and why. The ads on air "
            "today never show how many were stopped.",
        ],
        "deliver.title": "What to deliver",
        "deliver.analysis": [
            "The answer in two lines: why {name} gets this reach.",
            "The causes, heaviest first (three to five). For each: what they do, the evidence, how solid it is, "
            "and which passes confirm it (for example: copy + creative). Causes confirmed by two passes come first.",
            "A table of the ads read: ad id, type, people reached, per day, days, what it shows in one line.",
            "The findings of the four passes, as four short lists.",
            "What this data cannot tell.",
            "Three things to test or verify, in order of priority.",
        ],
        "lens.noreach": (
            "Audience and localisation (sections Reach and audience, Languages and countries). Reach in the country "
            "searched is not published, so no ad is compared by people reached. How broad the audience is (age, "
            "gender, locations), then languages of the texts against the countries targeted: one ad translated or "
            "different ads per country."),
        "deliver.analysis.noreach": {
            0: "The answer in two lines: what {name} keeps running and what that suggests, with the limit that "
               "reach is not published.",
            2: "A table of the ads read: ad id, type, position by impressions, days, creatives, what it shows in one line.",
        },
        "rules.title": "Rules of evidence",
        "rules": [
            "Meta publishes no spend and no sales. The rating (scale, staying power, creative investment) is a clue, not proof.",
            "Every number you write is in the data below. If you compute one, show the calculation.",
            "Reach is the people reached in the country searched. It exists only for ads delivered in the "
            "European Union or the United Kingdom. Where it is not published, never write about people reached, "
            "impressions or spend as if they were known: work from the order of the list, dates and creatives, and say so.",
            "An estimate is not a figure. If something is your inference, call it a hypothesis and say how to check it.",
            "An ad on air for less than 7 days is too recent to judge: do not build a conclusion on it.",
            "Reach counts unique people, who grow slower than days: read the total next to the daily figure.",
            "The reach of a concept is the sum of its ads that were read, up to three; the data says how many "
            "of how many. Do not add reach across concepts: the same person can be counted more than once.",
            "When a concept shows two ages (the concept and its most shown ad), the reach belongs to the ads "
            "that were read: do not divide a reach by the age of the concept.",
            "Hook, promise and proof labels in the data were assigned by rules: correct them when the text says otherwise.",
            "If the data does not support a conclusion, say what is missing instead of guessing.",
        ],
        "role.plan": (
            "You work as head of marketing for a business that sells online. Diagnosis first, then the proposal. "
            "The diagnosis starts from my project: what I sell, to whom, at what price, with what margin, and "
            "where on the way to purchase I lose customers. The proposal has priorities, a budget and rules for "
            "deciding, and it fits the means of the person who has to carry it out."),
        "steps.title": "Steps",
        "steps": [
            "Diagnosis of my project. Use the card \"My project\" and the numbers computed below, as they are: "
            "do not recompute them. In a few lines: margin per order, how much one purchase may cost, and where "
            "I most likely lose customers given the problem I named. Separate what the numbers show from what "
            "you assume, and for each assumption say how to check it.",
            "Check before spending. Before any budget goes out, tracking must work: the pixel and the Conversions "
            "API are both active, and the purchase event arrives with value and currency. Say how to verify it "
            "with a test purchase in Events Manager, and what to fix if it does not. Without this check the plan "
            "does not start.",
            "What {name} does. Read the data in the four passes (copy, creative, reach and audience, testing and "
            "destinations), give every ad a type, and keep only what matters for my case. Mark what two passes confirm.",
            "Five ad ideas for my product, inspired by the patterns that hold in the data. Not copies: no "
            "sentences, brand names or promises of the competitor. For each idea: angle; type of ad; the pattern "
            "it borrows (with ad id and its numbers); hook (first line or first three seconds); development in "
            "three points; proof to show; format; button and landing page; what it tests. Then run a skeptical jury "
            "of four buyer profiles against those ideas alongside {name}'s top ads: (1) price skeptic, (2) 2-second "
            "fast scroller, (3) trust skeptic, (4) comparison shopper. Give zero compliments and zero invented purchase "
            "odds; for each profile state one concrete objection citing a competitor ad id and one fix to make before spending.",
            "Campaign structure. Broad or narrow audience, in line with what the data shows {name} does (age "
            "range, gender, locations and breadth in the section Reach and audience). How many campaigns and ad "
            "sets, where tests run and where winners go. Give the reason from the data; if the audience data is "
            "missing, say so and propose the simplest structure.",
            "Test plan and creative pace. Use the section \"Numbers for the test\": budget per ad, budget of the "
            "first round, cut rule. Add: how many ads to run together, for how many days, what to look at each "
            "day, when to cut, when to raise the budget, and what to do if nothing holds. Then say how many new "
            "creatives a week I have to produce: start from the pace of {name} and from what the test budget can "
            "carry (both are in the numbers), show the calculation, and give a number one person can keep up.",
            "Report for whoever decides: one page. On top the decision asked for and the three priorities; "
            "then the numbers behind them; then risks and what we do not know; at the bottom the next "
            "seven days as a table with the columns Day, What, Who. If I have not told you who works with me, "
            "write \"You\" in the Who column and, where handing over makes sense, add to whom in brackets "
            "(for example video editing to a freelancer).",
        ],
        "deliver.plan": (
            "Deliver in this order: the report (step 7) first, then the check before spending (2), the ad ideas "
            "(4), the campaign structure (5), the test plan with the creative pace (6), and the diagnosis (1) and "
            "competitor reading (3) as an appendix. Whoever decides reads the first page only."),
        "project.title": "My project",
        "project": ["Product", "Selling price", "Product cost", "Market", "Goal", "Main problem"],
        "numbers.title": "Numbers for the test",
        "precheck.title": "Test before spending",
        "numbers.intro": "Computed by the app from the card, by arithmetic. Use them as they are. Amounts are "
                         "in the currency of the price on the card.",
        "numbers.more": "more than {n}",
        "numbers.pace.keyword": "This was a keyword search: {pace} new ads a week is the sum over all the "
                                "advertisers found, not the pace of one competitor. Do not size my production on it.",
        "numbers": [
            "Margin per order (price minus product cost): {margin}",
            "Break-even CPA, the most one purchase may cost in ads: {cpa}. Break-even ROAS: {roas}",
            "Cut rule: switch an ad off once it has spent {cut_low} to {cut_high} (2 to 3 times break-even "
            "CPA) with no add to cart and no sale",
            "Budget per test ad: up to {per_ad} ({multiplier} times break-even CPA)",
            "First round with {ideas} ads: up to {round_total}",
        ],
        "numbers.goal": [
            "Goal of {orders} orders a day: at break-even the most to spend is {daily_max} a day "
            "({orders} × {cpa}), {weekly_max} a week",
            "Share for tests, rule of thumb of {share}% of spend: {weekly_test} a week, enough for {capacity} "
            "new ads a week at {per_ad} each. This holds once spend is at the level of the goal, not at the start",
        ],
        "numbers.nogoal": "No number of orders per day can be read from the goal as written: ask me for it "
                          "before computing spend at the level of the goal.",
        "numbers.pace": "Pace of {name}: {pace} new ads a week among those still on air (ads already stopped "
                        "are not visible, so the real pace is the same or higher)",
        "numbers.pace.part": "The list of {name} was read in part ({loaded} ads of {active} active): the real "
                             "pace is higher than this figure. Do not size my production on it without saying so.",
        "numbers.costs": "These numbers use product cost only. VAT, shipping, payment fees and returns are not "
                         "included: if the price includes VAT or those costs are not in the product cost, the "
                         "real break-even is lower. Say so in the plan and ask me for the values.",
        "data.title": "Data",
        "attach.title": "Pictures to attach",
        "attach.some": "Attach the {n} pictures of the folder \"{folder}\" of this analysis. File names start "
                       "with the number of the ad in the section Creative:",
        "attach.none": "none: say that the creative reading is based on formats and copy only",
    },
    "it": {
        "language": "Scrivi in italiano.",
        "role.analysis": (
            "Lavori come specialista di performance marketing su Meta: leggi un annuncio come gancio, offerta, "
            "prova, pubblico e test, e cerchi le ragioni per cui un annuncio continua a essere pagato."),
        "goal.analysis": (
            "Spiega perché {name} ottiene la copertura che vedi nei dati. Ogni affermazione deve poggiare "
            "su un numero o su una citazione presa dai dati qui sotto, con l'id dell'annuncio. Una sintesi "
            "che andrebbe bene per qualunque inserzionista non serve."),
        "goal.analysis.noreach": (
            "Spiega cosa fa girare {name}, cosa tiene acceso e come fa i test. La copertura nel paese cercato non "
            "è pubblicata: quante persone raggiungono questi annunci non si sa. Scrivilo nelle prime righe e "
            "lavora sull'ordine dell'elenco di Meta, sulle date e sulle creatività. Ogni affermazione deve "
            "poggiare su un numero o su una citazione presa dai dati qui sotto, con l'id dell'annuncio. Una "
            "sintesi che andrebbe bene per qualunque inserzionista non serve."),
        "method.title": "Come lavorare",
        "method.intro": (
            "Leggi i dati in quattro passaggi, uno per volta. Per ogni passaggio annota al massimo cinque "
            "osservazioni così: osservazione · prova (numero o citazione, con id dell'annuncio) · quanto è "
            "solida (alta, media, bassa). Poi incrocia i passaggi: un fatto confermato da due passaggi o più "
            "pesa di più, e accanto scrivi quali passaggi lo confermano. Un fatto visto in un solo passaggio "
            "resta, segnato «un solo passaggio»."),
        "lens": [
            "Testi (sezione Copy). Quali ganci aprono gli annunci che scalano o reggono, quale offerta e quale "
            "prova portano, quali strutture si ripetono, e cosa distingue i testi portati da molte creatività da "
            "quelli su una sola. Dai a ogni annuncio un tipo dell'elenco «Ad types», giudicando dal testo.",
            "Creatività (sezione Creative). Per i video: cosa succede nei primi secondi, come si sviluppa, "
            "come chiude. Guarda i fotogrammi allegati (inizio, metà, fine) e le immagini. Dai a ogni annuncio "
            "un tipo dell'elenco «Ad types», giudicando da ciò che vedi. Se le immagini non ci sono, dillo in "
            "una riga e lavora su formati e testi.",
            "Copertura e pubblico (sezione Reach and audience). Persone raggiunte e copertura al giorno, ampiezza "
            "del pubblico (età, genere, luoghi), e cosa cambia tra gli annunci che raggiungono molte persone e "
            "quelli che ne raggiungono poche. Poi la localizzazione (sezione Languages and countries): lingue dei "
            "testi contro paesi raggiunti. Un annuncio tradotto o annunci diversi per paese, e dove va davvero la consegna.",
            "Test e destinazioni (sezione Testing and destinations). Quanti annunci nuovi a settimana, quali "
            "bottoni e quali pagine di arrivo. Sopravvivenza: confronta solo annunci della stessa età. Usa la "
            "tabella sotto Survival quando c'è; quando dice NOT MEASURABLE scrivi che non è ancora misurabile e "
            "perché. Gli annunci accesi oggi non dicono mai quanti ne sono stati spenti.",
        ],
        "deliver.title": "Cosa consegnare",
        "deliver.analysis": [
            "La risposta in due righe: perché {name} ottiene questa copertura.",
            "Le cause, dalla più pesante alla meno pesante (da tre a cinque). Per ognuna: cosa fanno, la prova, "
            "quanto è solida, e quali passaggi la confermano (per esempio: testi + creatività). Le cause "
            "confermate da due passaggi vengono prima.",
            "Una tabella degli annunci letti: id, tipo, persone raggiunte, al giorno, giorni, cosa mostra in una riga.",
            "Le osservazioni dei quattro passaggi, in quattro elenchi brevi.",
            "Cosa questi dati non possono dire.",
            "Tre cose da provare o verificare, in ordine di priorità.",
        ],
        "lens.noreach": (
            "Pubblico e localizzazione (sezioni Reach and audience, Languages and countries). La copertura nel paese "
            "cercato non è pubblicata, quindi nessun annuncio si confronta per persone raggiunte. Ampiezza del "
            "pubblico (età, genere, luoghi), poi lingue dei testi contro i paesi scelti: un annuncio tradotto o "
            "annunci diversi per paese."),
        "deliver.analysis.noreach": {
            0: "La risposta in due righe: cosa {name} tiene acceso e cosa suggerisce, con il limite che la "
               "copertura non è pubblicata.",
            2: "Una tabella degli annunci letti: id, tipo, posizione per impressioni, giorni, creatività, cosa "
               "mostra in una riga.",
        },
        "rules.title": "Regole sulle prove",
        "rules": [
            "Meta non pubblica spesa né vendite. La valutazione (scala, tenuta, investimento creativo) è un indizio, non una prova.",
            "Ogni numero che scrivi è nei dati qui sotto. Se ne calcoli uno, mostra il calcolo.",
            "La copertura è il numero di persone raggiunte nel paese cercato. Esiste solo per gli annunci mostrati "
            "nell'Unione europea o nel Regno Unito. Dove non è pubblicata non scrivere mai di persone raggiunte, "
            "impressioni o spesa come se fossero note: lavora su ordine dell'elenco, date e creatività, e dillo.",
            "Una stima non è un dato. Se una cosa è una tua deduzione, chiamala ipotesi e scrivi come verificarla.",
            "Un annuncio acceso da meno di 7 giorni è troppo recente per giudicare: non costruirci sopra una conclusione.",
            "La copertura conta persone uniche, che crescono meno dei giorni: leggi il totale accanto al dato al giorno.",
            "La copertura di un concetto è la somma dei suoi annunci letti, fino a tre; nei dati è scritto "
            "quanti su quanti. Non sommare la copertura di concetti diversi: la stessa persona può essere "
            "contata più volte.",
            "Quando un concetto mostra due età (quella del concetto e quella del suo annuncio più mostrato), "
            "la copertura è degli annunci letti: non dividere una copertura per l'età del concetto.",
            "Le etichette hook, promise e proof nei dati sono assegnate da regole: correggile quando il testo dice altro.",
            "Se i dati non reggono una conclusione, indica cosa manca invece di tirare a indovinare.",
        ],
        "role.plan": (
            "Lavori come responsabile marketing di un'azienda che vende online. Prima la diagnosi, poi la proposta. "
            "La diagnosi parte dal mio progetto: cosa vendo, a chi, a che prezzo, con che margine, e in che punto "
            "del percorso d'acquisto perdo clienti. La proposta ha priorità, budget e criteri di decisione, ed è "
            "alla portata di chi la deve eseguire."),
        "steps.title": "Passaggi",
        "steps": [
            "Diagnosi del mio progetto. Usa la scheda «Il mio progetto» e i numeri calcolati sotto così come sono: "
            "non ricalcolarli. In poche righe: margine per ordine, quanto può costare un acquisto, e dove è più "
            "probabile che io perda clienti dato il problema che ho indicato. Distingui ciò che i numeri mostrano "
            "da ciò che ipotizzi, e per ogni ipotesi scrivi come verificarla.",
            "Controllo prima di spendere. Prima che esca un euro il tracciamento deve funzionare: pixel e "
            "Conversions API entrambi attivi, e l'evento di acquisto che arriva con valore e valuta. Scrivi come "
            "verificarlo con un acquisto di prova in Gestione eventi, e cosa sistemare se non arriva. Senza questo "
            "controllo il piano non parte.",
            "Cosa fa {name}. Leggi i dati nei quattro passaggi (testi, creatività, copertura e pubblico, test e "
            "destinazioni), dai a ogni annuncio un tipo, e tieni solo ciò che serve al mio caso. Segna ciò che è "
            "confermato da due passaggi.",
            "Cinque idee di annuncio per il mio prodotto, ispirate agli schemi che reggono nei dati. Non "
            "copie: niente frasi, marchi o promesse del concorrente. Per ogni idea: angolo; tipo di annuncio; "
            "schema a cui si ispira (con id dell'annuncio e i suoi numeri); gancio (prima riga o primi tre "
            "secondi); sviluppo in tre punti; prova da mostrare; formato; bottone e pagina di arrivo; cosa mette alla prova. "
            "Poi sottoponi queste idee, fianco a fianco con i migliori annunci di {name}, a una giuria scettica di "
            "quattro profili: (1) chi guarda subito il prezzo, (2) chi scorre in 2 secondi, (3) chi diffida delle "
            "promesse, (4) chi confronta con alternative note. Nessun complimento e nessuna probabilità di acquisto "
            "inventata: per ogni profilo scrivi un'obiezione concreta citando l'id dell'annuncio concorrente e una "
            "correzione pratica da fare prima di spendere.",
            "Struttura della campagna. Pubblico ampio o ristretto, in linea con ciò che i dati mostrano di {name} "
            "(età, genere, luoghi e ampiezza nella sezione Reach and audience). Quante campagne e quanti gruppi di "
            "inserzioni, dove girano i test e dove vanno i vincitori. Dai la ragione presa dai dati; se i dati sul "
            "pubblico mancano, dillo e proponi la struttura più semplice.",
            "Piano di test e ritmo creativo. Usa la sezione «Numeri per il test»: budget per annuncio, budget del "
            "primo giro, regola di spegnimento. Aggiungi: quanti annunci accendere insieme, per quanti giorni, cosa "
            "guardare ogni giorno, quando spegnere, quando aumentare il budget, e cosa fare se nessuno regge. Poi "
            "scrivi quante creatività nuove a settimana devo produrre: parti dal ritmo di {name} e da quanto il "
            "budget di test può reggere (sono entrambi nei numeri), mostra il calcolo, e dai un numero che una "
            "persona sola riesce a sostenere.",
            "Report per chi decide: una pagina. In alto la decisione richiesta e le tre priorità; poi i "
            "numeri che le sostengono; poi i rischi e ciò che non sappiamo; in fondo i prossimi sette giorni "
            "in una tabella con le colonne Giorno, Cosa, Chi. Se non ti ho detto chi lavora con me, nella colonna "
            "Chi scrivi «Tu» e, dove ha senso delegare, aggiungi tra parentesi a chi (per esempio il montaggio "
            "video a un freelance).",
        ],
        "deliver.plan": (
            "Consegna in questo ordine: prima il report (passaggio 7), poi il controllo prima di spendere (2), le "
            "idee di annuncio (4), la struttura della campagna (5), il piano di test con il ritmo creativo (6), e in "
            "appendice la diagnosi (1) e la lettura del concorrente (3). Chi decide legge solo la prima pagina."),
        "project.title": "Il mio progetto",
        "project": ["Prodotto", "Prezzo di vendita", "Costo del prodotto", "Mercato", "Obiettivo", "Problema principale"],
        "numbers.title": "Numeri per il test",
        "precheck.title": "Prova prima di spendere",
        "numbers.intro": "Calcolati dall'app a partire dalla scheda, con semplice aritmetica. Usali così come "
                         "sono. Gli importi sono nella valuta del prezzo scritto nella scheda.",
        "numbers.more": "più di {n}",
        "numbers.pace.keyword": "Questa era una ricerca per parola chiave: {pace} annunci nuovi a settimana è la "
                                "somma di tutti gli inserzionisti trovati, non il ritmo di un concorrente. Non "
                                "dimensionare la mia produzione su questo dato.",
        "numbers": [
            "Margine per ordine (prezzo meno costo del prodotto): {margin}",
            "CPA di pareggio, il massimo che un acquisto può costare in pubblicità: {cpa}. ROAS di pareggio: {roas}",
            "Regola di spegnimento: spegni un annuncio quando ha speso da {cut_low} a {cut_high} (da 2 a 3 "
            "volte il CPA di pareggio) senza aggiunte al carrello né vendite",
            "Budget per annuncio in test: fino a {per_ad} ({multiplier} volte il CPA di pareggio)",
            "Primo giro con {ideas} annunci: fino a {round_total}",
        ],
        "numbers.goal": [
            "Obiettivo di {orders} ordini al giorno: a pareggio la spesa massima è {daily_max} al giorno "
            "({orders} × {cpa}), {weekly_max} a settimana",
            "Quota per i test, regola pratica del {share}% della spesa: {weekly_test} a settimana, cioè fino a "
            "{capacity} annunci nuovi a settimana a {per_ad} l'uno. Vale a regime, quando la spesa è quella "
            "dell'obiettivo, non all'inizio",
        ],
        "numbers.nogoal": "Dall'obiettivo così come è scritto non si ricava un numero di ordini al giorno: "
                          "chiedimelo prima di calcolare la spesa a regime.",
        "numbers.pace": "Ritmo di {name}: {pace} annunci nuovi a settimana tra quelli ancora attivi (quelli già "
                        "spenti non si vedono, quindi il ritmo vero è uguale o più alto)",
        "numbers.pace.part": "L'elenco di {name} è stato letto in parte ({loaded} annunci su {active} attivi): "
                             "il ritmo vero è più alto di questo numero. Non dimensionare la mia produzione su "
                             "questo dato senza dirlo.",
        "numbers.costs": "Questi numeri usano solo il costo del prodotto. IVA, spedizione, commissioni di pagamento "
                         "e resi non sono compresi: se il prezzo è IVA inclusa o quei costi non sono nel costo del "
                         "prodotto, il pareggio reale è più basso. Scrivilo nel piano e chiedimi i valori.",
        "data.title": "Dati",
        "attach.title": "Immagini da allegare",
        "attach.some": "Allega le {n} immagini della cartella «{folder}» di questa analisi. I nomi dei file "
                       "iniziano con il numero dell'annuncio nella sezione Creative:",
        "attach.none": "nessuna: scrivi che la lettura delle creatività si basa solo su formati e testi",
    },
}


def _number(text: str) -> float | None:
    """A figure as people write it: "12,5", "1.500", "1,500", "2.5". A separator before three digits is thousands."""
    parts = re.split(r"[.,]", text)
    if len(parts) == 1:
        return float(text)
    if all(len(part) == 3 for part in parts[1:]):
        if parts[0].startswith("0"):
            return None                               # "0,500": half an order or five hundred? not guessed
        return float("".join(parts))
    if len(parts) == 2:
        return float(".".join(parts))
    return None


def orders_per_day(goal: str) -> float | None:
    """The number of orders a day named in a goal such as "20 ordini al giorno", or None.

    None means "ask": the goal names no orders, no period right after them (a day, a week,
    a month), a range or a second figure, an increase or a multiple, or words after the
    period that change its meaning. A wrong guess here would size the whole budget of the
    plan, so anything unclear is not guessed.
    """
    goal = goal or ""
    found = list(_ORDERS.finditer(goal))
    if len(found) != 1 or _CHANGE.search(goal):
        return None
    figure, period = found[0].group(1), _PERIOD.match(found[0].group(2))
    for other in _FIGURE.finditer(goal):
        if other.start() == found[0].start(1):
            continue
        before, after = goal[:other.start()], goal[other.end():]
        year = re.fullmatch(r"20\d\d", other.group()) and not re.match(r"\s*[\d/.,-]", after)
        deadline = _DEADLINE.search(before) and _SPAN_AFTER.match(after)
        if not (year or deadline or _OTHER_AFTER.match(after) or _OTHER_BEFORE.search(before)):
            return None                               # "20-30", "da 10 a 30", "1 500": which figure?
    if period is None or not _TAIL.match(found[0].group(2)[period.end():]):
        return None
    orders = _number(figure)
    if not orders or orders <= 0 or period is None:
        return None
    return round(orders / _SPANS[period.lastgroup], 2)


def test_numbers(project: dict, ideas: int = IDEAS, multiplier: float = TEST_MULTIPLIER,
                 pace: float | None = None) -> dict:
    """Break-even, test budget and spend at the level of the goal, by plain arithmetic.

    ``pace`` is the competitor's new ads per week, when a search result is at hand.
    The goal figures are there only when the goal names a number of orders.
    """
    if project["product_cost"] < 0 or project["price"] <= 0:
        raise ValueError("price must be above zero and product cost cannot be negative")
    cpa = breakeven.breakeven_cpa(project["price"], project["product_cost"])
    if cpa <= 0:
        raise ValueError("the product cost leaves no margin: no test budget can be computed")
    per_ad = round(cpa * multiplier, 2)
    numbers = {
        "margin": round(project["price"] - project["product_cost"], 2),
        "cpa": cpa,
        "roas": round(project["price"] / cpa, 2),
        "cut_low": round(cpa * 2, 2),
        "cut_high": round(cpa * 3, 2),
        "per_ad": per_ad,
        "round_total": round(per_ad * ideas, 2),
        "multiplier": multiplier,
        "ideas": ideas,
    }
    orders = orders_per_day(project.get("goal") or "")
    if orders:
        weekly_max = round(orders * cpa * 7, 2)
        weekly_test = round(weekly_max * TEST_SHARE, 2)
        numbers.update(orders=orders, daily_max=round(orders * cpa, 2), weekly_max=weekly_max,
                       share=round(TEST_SHARE * 100), weekly_test=weekly_test,
                       capacity=math.floor(weekly_test / per_ad))
    if pace is not None:
        numbers["pace"] = pace
    return numbers


def precheck_numbers(project: dict, ideas: int = IDEAS, multiplier: float = TEST_MULTIPLIER) -> dict:
    """Reverse-breakeven CPC scenarios, max loss and settled Poisson stop odds from ``project``."""
    return precheck.analyze(
        price=project["price"],
        product_cost=project["product_cost"],
        market=project.get("market") or "",
        vat_pct=project.get("vat_pct", 0.0),
        shipping_cost=project.get("shipping_cost", 0.0),
        payment_fee_pct=project.get("payment_fee_pct", 0.0),
        payment_fee_fixed=project.get("payment_fee_fixed", 0.0),
        return_rate_pct=project.get("return_rate_pct", 0.0),
        other_costs=project.get("other_costs", 0.0),
        ad_fee_pct=project.get("ad_fee_pct"),
        ideas=ideas,
        multiplier=multiplier,
    )


def _demote(text: str, levels: int = 2) -> str:
    """Push the headings of a data slice below the headings of the brief."""
    return "\n".join("#" * levels + line if line.startswith("#") else line for line in text.splitlines()) + "\n"


def _money(value, lang: str = "en") -> str:
    """A figure as the language of the brief writes it: 2,862.5 in English, 2.862,5 in Italian."""
    if isinstance(value, float):
        text = f"{value:,.2f}".rstrip("0").rstrip(".")
    elif isinstance(value, int) and not isinstance(value, bool):
        text = f"{value:,}"
    else:
        return str(value)
    return text.translate(str.maketrans(",.", ".,")) if lang == "it" else text


def project_section(project: dict, lang: str, result: dict | None = None) -> str:
    """The project card and the numbers computed from it, as Markdown."""
    words = _T[lang]
    found = (result or {}).get("signals") or {}
    pace = found.get("new_per_week")
    raw = test_numbers(project, pace=pace)
    numbers = {key: _money(value, lang) for key, value in raw.items()}
    values = [project["product"], _money(float(project["price"]), lang), _money(float(project["product_cost"]), lang),
              project["market"], project["goal"], project["main_problem"]]
    lines = [f"## {words['project.title']}", *[f"- {label}: {value}" for label, value in zip(words["project"], values)],
             "", f"## {words['numbers.title']}", words["numbers.intro"],
             *[f"- {line.format(**numbers)}" for line in words["numbers"]]]
    if "orders" in raw:
        lines += [f"- {line.format(**numbers)}" for line in words["numbers.goal"]]
    else:
        lines.append(f"- {words['numbers.nogoal']}")
    if pace is not None and (result or {}).get("mode") != "company":
        lines.append("- " + words["numbers.pace.keyword"].format(pace=numbers["pace"]))
    elif pace is not None:
        lines.append("- " + words["numbers.pace"].format(name=packs.subject_name(result), pace=numbers["pace"]))
        if packs.partly_loaded(found):
            active = _money(found["active_ads"], lang)
            if found.get("active_ads_at_least"):
                active = words["numbers.more"].format(n=_money(found["active_ads"] - 1, lang))
            lines.append("- " + words["numbers.pace.part"].format(
                name=packs.subject_name(result), loaded=_money(found["ads_loaded"], lang), active=active))
    lines.append(f"- {words['numbers.costs']}")
    lines += ["", f"## {words['precheck.title']}", *precheck.format_markdown(precheck_numbers(project), lang)]
    return "\n".join(lines) + "\n"


def instructions(level: str, name: str, lang: str = "it", reach: bool = True) -> str:
    """Role, method, deliverables and rules for a level, without any data.

    ``reach`` says whether the pack holds reach in the country searched. Without it the
    analysis is asked what the advertiser runs and keeps running, not why it reaches
    what it reaches, and the table of ads has no column for people.
    """
    words = _T[lang]
    out = [words[f"role.{level}"], ""]
    if level == "analysis":
        deliver, lens = list(words["deliver.analysis"]), list(words["lens"])
        if not reach:
            lens[2] = words["lens.noreach"]
            for index, line in words["deliver.analysis.noreach"].items():
                deliver[index] = line
        out += [words["goal.analysis" if reach else "goal.analysis.noreach"].format(name=name), "",
                f"## {words['method.title']}", words["method.intro"],
                *[f"{n}. {line}" for n, line in enumerate(lens, start=1)], "",
                f"## {words['deliver.title']}", words["language"],
                *[f"{n}. {line.format(name=name)}" for n, line in enumerate(deliver, start=1)]]
    else:
        lens = list(words["lens"])
        if not reach:
            lens[2] = words["lens.noreach"]
        out += [f"## {words['steps.title']}",
                *[f"{n}. {line.format(name=name)}" for n, line in enumerate(words["steps"], start=1)], "",
                f"## {words['method.title']}", words["method.intro"],
                *[f"{n}. {line}" for n, line in enumerate(lens, start=1)], "",
                f"## {words['deliver.title']}", words["language"], words["deliver.plan"]]
    out += ["", f"## {words['rules.title']}", *[f"- {line}" for line in words["rules"]]]
    return "\n".join(out) + "\n"


def compose(level: str, result: dict, ads: int = 10, frames: bool = False,
            project: dict | None = None, lang: str = "it") -> dict:
    """The single-pass brief for ``level``, with the data inside.

    Returns the text, the pictures it asks to attach (as names inside the pack's
    ``frames`` folder, never as paths), the data slices and a size measure. Pictures are
    there only with ``frames``. A plan needs the project card.
    """
    if level not in LEVELS:
        raise ValueError("level must be analysis or plan")
    if level == "plan" and not project:
        raise ValueError("the plan needs the project card")
    lang = "en" if lang == "en" else "it"
    words = _T[lang]
    name = packs.subject_name(result)
    slices, pictures = packs.sections(result, ads, frames)

    reach = any(ad.get("reach_per_day") is not None for ad in packs.chosen(result, ads))
    parts = [f"# {name} · {result.get('country') or ''}".rstrip(" ·"), "", instructions(level, name, lang, reach)]
    if level == "plan":
        parts += [project_section(project, lang, result)]
    parts += [f"## {words['data.title']}", ""]
    parts += [_demote(slices[key]) for key in packs.SLICES]
    parts += [f"## {words['attach.title']}"]
    if pictures:
        parts += [words["attach.some"].format(n=len(pictures), folder=packs.FRAMES_FOLDER),
                  *[f"- {Path(picture['name']).name}" for picture in pictures]]
    else:
        parts += [f"- {words['attach.none']}"]
    text = "\n".join(parts).strip() + "\n"
    return {"level": level, "text": text, "images": [picture["name"] for picture in pictures],
            "pictures": pictures, "slices": slices,
            "ads": min(max(1, int(ads)), len(result["ads"])), "frames": bool(frames),
            "size": consumption.measure(text, len(pictures), level)}


def prepare(level: str, result: dict, ads: int = 10, frames: bool = False, project: dict | None = None,
            lang: str = "it", directory: Path | None = None, today: date | None = None) -> dict:
    """Compose the brief and save the data pack next to it.

    The pack folder holds the brief, one data file per specialist, the pictures in
    ``frames`` and, for a plan, the project card with its numbers. Returns the brief
    plus the folder and file paths; ``images`` are the picture files inside the pack.
    """
    made = compose(level, result, ads, frames, project, lang)
    extra = ({"project": project_section(project, "en" if lang == "en" else "it", result)}
             if level == "plan" else None)
    saved = packs.write(result, level, made.pop("slices"), made.pop("pictures"), made["text"], extra,
                        directory, today, ads=made["ads"])
    return {**made, **saved}
