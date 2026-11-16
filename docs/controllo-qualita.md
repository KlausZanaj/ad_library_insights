# Controllo di qualità

Questo documento serve a una cosa: evitare che un numero dica una cosa e ne misuri un'altra.
Ha tre parti. La prima elenca ogni numero che entra nella valutazione, nell'analisi o nel piano,
e dice cosa misura davvero. La seconda riporta cosa ha trovato un revisore indipendente che ha
provato a rompere i risultati. La terza elenca i casi difficili, ognuno con un test sui dati reali.

Il controllo va rifatto ogni volta che cambia un calcolo. I test dei casi difficili sono in
`tests/test_rating.py` e girano senza rete, sui dati salvati in `tests/fixtures/`.

## A. Cosa misura ogni numero

«Coincide» risponde a una domanda sola: il numero riguarda quello che l'utente ha cercato
(quel paese, quell'azienda o quella parola chiave)? Dove la risposta era «no», è scritto cosa è
stato corretto.

### Numeri che entrano nella valutazione

| Numero | Cosa misura davvero | Su chi | Coincide con la ricerca? | Dove viene letto |
|---|---|---|---|---|
| Persone raggiunte nel paese (`reach_total`) | Persone uniche che hanno visto l'annuncio almeno una volta, da quando è acceso. Per un concetto con più annunci: somma degli annunci letti, al massimo tre (`reach_cards_read`) | Il paese cercato | Sì. **Corretto**: prima la scala usava il totale UE, e di un concetto contava un solo annuncio | `details.parse_reach`: riga del paese in `age_country_gender_reach_breakdown`, somma delle fasce di età e genere; con un solo paese, il totale della sezione. Poi `signals.annotate` |
| Totale UE (`reach.eu_total`) | Persone uniche in tutta l'Unione europea | UE | No. Per questo è solo informazione, nel dettaglio dell'annuncio | `details._total`, campo `eu_total_reach` |
| Totale Regno Unito (`reach.uk_total`) | Persone uniche nel Regno Unito | Regno Unito | Solo se si cerca il Regno Unito | `details._total`, sezione `uk_transparency` |
| Copertura al giorno (`reach_per_day`) | Persone raggiunte nel paese, diviso i giorni di attività di ogni annuncio letto, mai meno di 7; gli annunci dello stesso concetto si sommano. È una media su tutta la vita dell'annuncio, non il ritmo di oggi | Il paese cercato | Sì. **Corretto**: prima divideva anche per 1 giorno | `signals.annotate`, `rating.rate_days` |
| Copertura fuori dal paese (`reach_elsewhere_per_day`) | Totale UE o Regno Unito al giorno, quando il paese cercato non è coperto | UE o Regno Unito | No. Non entra nella valutazione | `signals.annotate` |
| Giorni dell'annuncio letto (`ad_days`) | Giorni dalla data di inizio della scheda più mostrata del concetto | L'annuncio, ovunque sia stato mostrato | In parte: la data di inizio è una sola per tutti i paesi. Se l'annuncio è partito altrove e in Italia è arrivato dopo, qui non si vede | `records` (`start_date`), `scoring.days_running`, `rating.group_concepts` |
| Giorni del concetto (`days_running`) | Giorni dalla data di inizio più vecchia tra gli annunci riuniti | Gli annunci ancora attivi caricati | Sì, con un limite: gli annunci già spenti non ci sono, quindi il concetto può essere più vecchio di così | `rating.group_concepts` |
| Posizione per impressioni (`impression_rank`) | Posto della scheda nell'elenco della Ad Library, chiesto in ordine di impressioni totali | L'elenco filtrato per il paese cercato | Non dimostrabile: Meta non dice se le impressioni sono solo quelle del paese (un annuncio Kingshot è 27° con 966 persone in Italia e 12.402 in UE). Per questo l'affidabilità è media, la posizione è misurata sull'intero elenco e non dà mai «Sta scalando» né «Da verificare» | `client.SORT_BY_IMPRESSIONS`, `records`, `rating._scale_from_position` |
| Stima di copertura al giorno (`reach_per_day_estimate`) | Per gli annunci non letti: copertura nel paese stimata dalla posizione per impressioni, calibrata sugli annunci letti | Il paese cercato | Sì, ma è una stima: affidabilità media, e non basta a dare «Da verificare» | `rating._reach_by_position`, `rating.evaluate` |
| Creatività (`creatives`) | File video o immagine diversi tra gli annunci riuniti nel concetto; punti pieni a 10 | Gli annunci caricati | Sì. Un catalogo vale 1. Lo stesso video sotto due testi diversi conta per tutti e due i concetti | `rating.media_key`, `rating.group_concepts` |
| Annunci riuniti (`cards`) e copie identiche (`copies_total`) | Schede riunite nel concetto; copie = somma di `collation_count`, cioè gli annunci che Meta stessa raggruppa perché identici | Gli annunci caricati | Sì. Sono informazioni, non danno punti | `records` (`collation_count`), `rating.group_concepts` |
| Scala, da 0 a 100 | Distanza dal migliore annuncio della ricerca, su scala logaritmica: 100 al migliore, 0 a chi raggiunge mille volte meno persone al giorno | Gli annunci di questa ricerca di cui la copertura è nota | Sì | `rating.evaluate`, `rating._scale_from_rate` |
| Tenuta, da 0 a 100 | Giorni del concetto diviso 90, al massimo 100 | Come i giorni del concetto | Sì | `rating.evaluate` |
| Longevità precedente | Il vecchio punteggio: giorni e copie del testo | Come sopra | Mostrata nel dettaglio, non decide l'ordine | `scoring.longevity_score` |

### Numeri dell'analisi (riepilogo di una ricerca)

| Numero | Cosa misura davvero | Su chi | Coincide con la ricerca? | Dove viene letto |
|---|---|---|---|---|
| Annunci attivi | Il conteggio che Meta dà per la ricerca. Meta stessa lo indica come approssimato | Tutti gli annunci attivi che corrispondono, nel paese cercato | Sì | `records` (`count` della risposta), `signals.summarize` |
| Annunci caricati | Quanti annunci lo strumento ha letto davvero | I più mostrati dell'elenco | È un campione quando sono meno degli attivi: è scritto accanto al titolo | `service.assemble` |
| Annunci nuovi a settimana, partiti in 30 giorni | Annunci **ancora attivi** partiti nelle ultime quattro settimane (diviso quattro) o negli ultimi 30 giorni | Gli annunci caricati | In parte. Quelli lanciati e già spenti non si vedono: il ritmo vero è uguale o più alto. **Corretto**: l'etichetta diceva «nuove creatività», ma conta annunci | `signals._launches` |
| Quota video, formati, bottoni, destinazioni, piattaforme | Quota degli annunci caricati | Gli annunci caricati | Sì | `signals.summarize` |
| Lingue | Lingua riconosciuta dal testo con un elenco di parole frequenti | Gli annunci caricati che hanno un testo | Sì. I testi molto brevi possono restare senza lingua, e sono contati a parte | `signals.detect_language` |
| Copertura al giorno, mediana e migliore | Valore mediano e valore più alto tra gli annunci letti | Il paese cercato | Sì | `signals._reach_summary` |
| Persone raggiunte, mediana e migliore | Come sopra, sul totale delle persone | Il paese cercato | Sì | `signals._reach_summary` |
| Somme di copertura (UE, paese, Regno Unito) | Somma delle coperture dei singoli annunci | Persone contate più volte | No: non sono persone uniche. **Corretto**: l'interfaccia mostra mediana e migliore, non la somma | `signals._reach_summary` |
| Età, genere, luoghi | Le impostazioni di pubblico scelte dall'inserzionista | La consegna in UE dell'annuncio letto | Dicono a chi è stato aperto l'annuncio, non chi lo ha visto | `details.parse_audience` |
| Ampiezza del pubblico | Un'etichetta (ampio, medio, stretto) calcolata da età, genere e luoghi | Come sopra | È un giudizio di sintesi, non un dato di Meta | `signals.audience_breadth` |
| Paesi per copertura | Somma per paese delle coperture degli annunci letti | UE e Regno Unito | Serve a capire dove va la consegna, non quante persone uniche | `signals._reach_summary` |
| Seguaci della pagina | I «mi piace» della pagina Facebook | Tutto il mondo | No. È solo contesto e non entra in nessun calcolo | `records.parse_pages` |
| Novità: nuovi, spenti, cambiati | Differenza tra le ultime due ricerche salvate | Gli annunci caricati nelle due ricerche | Per un'azienda sì. Per una parola chiave è un campione: «spento» può voler dire solo «uscito dai più mostrati», ed è scritto | `history.compare` |

### Numeri del piano

| Numero | Cosa misura davvero | Su chi | Coincide con la ricerca? | Dove viene letto |
|---|---|---|---|---|
| Margine per ordine | Prezzo di vendita meno costo del prodotto, come li ha scritti l'utente | Il progetto dell'utente | Sì, ma non comprende IVA, spedizione, commissioni di pagamento e resi: il piano lo dice e chiede di toglierli | `briefs.test_numbers`, `breakeven.breakeven_cpa` |
| CPA di pareggio | Quanto può costare un acquisto in pubblicità senza perdere soldi: è uguale al margine | Come sopra | Come sopra | `breakeven.breakeven_cpa` |
| ROAS di pareggio | Prezzo diviso CPA di pareggio | Come sopra | Come sopra | `briefs.test_numbers` |
| Budget per annuncio in test | 2,5 volte il CPA di pareggio | Come sopra | È una regola pratica (da 2 a 3 volte), non un dato | `briefs.test_numbers` |
| Budget del primo giro | Budget per annuncio per cinque annunci | Come sopra | Come sopra | `briefs.test_numbers` |
| Stima di utilizzo | Dimensione del testo e numero di immagini da passare all'assistente | Il testo preparato | È una stima: i limiti dipendono dal piano e dal modello dell'utente | `consumption.estimate`, `consumption.measure` |

## B. Revisore indipendente

Un revisore che non aveva visto il lavoro ha ricevuto solo il codice e i dati reali salvati
(`tests/fixtures/`). Compito: rompere i risultati. Ha rieseguito la valutazione sulle tre ricerche
(106, 14 e 114 concetti), ha seguito ogni numero fino al dato grezzo e ha provato le funzioni con dati
anomali. Ogni problema è riportato con la prova numerica e con la correzione fatta.

### Problemi gravi

| Cosa ha trovato | La prova | Cosa è stato corretto | Test |
|---|---|---|---|
| Un annuncio non letto prendeva più punti di uno letto identico | I pesi cambiavano con l'affidabilità (50/30/20 contro 60/25/15): Padel Pro Italia, stimato a 29 persone al giorno, stava sopra Gabrieli sport, letto a 91 | Pesi unici 60/25/15. Senza dati la scala vale zero punti | `test_an_ad_that_was_not_read_never_gains_from_it` |
| La scala di un concetto era la copertura di un solo annuncio | Zalando: 9 annunci, letto 1. Flexora: il secondo annuncio letto (184.905 persone) non contava | Si leggono fino a tre annunci per concetto, i più mostrati, e si sommano. Accanto è scritto quanti | `test_reach_of_a_concept_adds_up_the_ads_that_were_read` |
| Gli annunci da leggere erano scelti da un punteggio che favorisce l'età | 14 concetti tra i primi 100 per impressioni non letti, tutti recenti; letto invece un annuncio al 123° posto | Si leggono nell'ordine dell'elenco di Meta | `test_cards_are_read_in_the_order_of_the_library_three_per_concept_at_most` |
| «Da verificare» dato dalla sola posizione, su un elenco parziale | Stati Uniti: 148 annunci caricati su oltre 50.000; quello al 148° posto era «Da verificare». Caricandone 120 cambiavano 18 etichette | La posizione si misura sull'intero elenco. «Sta scalando» e «Da verificare» solo su copertura letta | `test_position_scale_does_not_depend_on_how_much_of_the_list_was_loaded` |
| Un dato in più ribaltava la classifica | Con 2 o 3 coperture lette cambiavano 24 posizioni; tre annunci a 1.000, 1.010 e 1.020 persone al giorno prendevano scala 0, 50 e 100 | Scala ancorata al migliore, non al più debole. Etichette relative solo con almeno cinque annunci letti | `test_close_rates_get_close_scales_and_the_lowest_is_not_zero`, `test_scale_is_anchored_to_the_best_ad_not_to_the_weakest` |
| «Da verificare» a chi ha raggiunto molte persone | SPORT LIFE: 629 giorni, 161.736 persone (dodicesimo totale su 47), 257 al giorno | «Da verificare» richiede anche un totale sotto la mediana e nessun annuncio nuovo nel concetto | `test_a_large_total_reach_is_never_called_forgotten`, `test_a_concept_with_a_fresh_ad_is_not_called_forgotten` |
| Età del concetto e copertura prese da annunci diversi | HOKA: 176 giorni dal più vecchio, 10.438 al giorno dal più recente (11 giorni) | Resta così, perché l'unità è il concetto, ma è scritto nel dettaglio; la copertura somma gli annunci letti | `test_hard_case_catalogue_ad` |

### Problemi medi

| Cosa ha trovato | Cosa è stato corretto | Test |
|---|---|---|
| Lingua sbagliata che riunisce testi diversi («Alibaba.com» letto come portoghese) | Gli indirizzi web non contano per la lingua; due testi che condividono le parole non sono mai traduzioni; una sola cifra in comune non basta | `test_texts_are_not_merged_on_a_guessed_language` |
| Catalogo dedotto dai parametri di tracciamento dei link | I link si confrontano senza la parte dopo «?», e servono titoli diversi | `test_catalogue_ads_are_one_creative_with_products` |
| Le creatività si misuravano sul massimo della ricerca | Soglia fissa: piene a 10 | `test_different_creatives_for_one_text_are_counted` |
| Ricerca su tutti i paesi mai valutata sulla copertura | «ALL» vale come nessun paese: conta tutto ciò che Meta pubblica | `test_reach_figures_that_are_not_numbers_do_not_break_the_rating` |
| «Sta scalando» a 7 giorni, «In prova» a 6 | «Sta scalando» da 14 giorni e fino a 89; oltre è «Regge nel tempo» | `test_scaling_is_for_ads_between_two_weeks_and_three_months` |
| Annunci spenti trattati come attivi | Etichetta «Spento»; un concetto è spento solo se lo sono tutti i suoi annunci | `test_ended_ads_are_labelled_as_such` |
| Punteggio degli inserzionisti non aggiornato dopo la lettura | La tabella degli inserzionisti si ricalcola | `service.deepen` |
| Risultati di parola chiave fuori tema (Stati Uniti: 18 annunci su 148 contengono «standing desk») | Ogni annuncio dice se contiene le parole cercate (`query_match`); il riepilogo dice quanti no. Non vengono tolti: Meta cerca in più campi | `test_keyword_match_is_a_hint` |
| Ordine dell'elenco dato per scontato | L'ordine per impressioni è chiesto in modo esplicito | `client.SORT_BY_IMPRESSIONS` |

### Lasciato com'è, con il motivo

- **La copertura al giorno è una media su tutta la vita dell'annuncio.** Il revisore mostra che chi è
  acceso da molto ne esce più basso (Subito: primo per impressioni, 2,7 milioni di persone in 899 giorni,
  2.995 al giorno). È una scelta fatta: il dato resta semplice da spiegare, il totale è sempre accanto, e
  «Da verificare» non si dà più a chi ha un totale alto. Mettere un tetto ai giorni alzava di cinque volte
  gli annunci piccoli e vecchi (Gabrieli sport dal 37° al 19° posto), che è l'errore da cui si era partiti.
- **La copertura di un paese è una somma di fasce** quando l'annuncio gira in più paesi: differisce dal
  totale unico di qualche punto percentuale (Italia 835.585 come somma, UE 7.538.995 contro 7.398.228 unici).
- **Lo stesso video può contare in due concetti**, se sta sotto due testi diversi.
- **Testi quasi identici** (un hashtag o una virgola di differenza) restano due concetti.

### Verificato senza trovare errori

Somma dei punti uguale alla valutazione e sempre tra 0 e 100 su 234 concetti; nessun uso di copertura
UE nella ricerca negli Stati Uniti; righe giuste lette da `parse_reach` (Italia 835.585, Francia 1.126.613,
Germania 1.461.753, Regno Unito dal totale 1.679.270, Stati Uniti assenti); aritmetica di Zalando
(5.136.974 / 44 = 116.749); posizioni continue da 1 a n; le quattro traduzioni Kingshot riunite sono giuste.

## B2. Secondo passaggio del revisore: valutazione, pacchetti dati, specialisti

Un secondo revisore indipendente ha ricontrollato la valutazione e, per la prima volta, i pacchetti dati,
i brief, i quattro specialisti e le due skill. Poi ha fatto un solo ripasso sulle correzioni.

### Problemi gravi, corretti

- **Un annuncio non letto poteva stare sopra lo stesso annuncio letto.** Togliendo la copertura a un
  annuncio alla volta, il punteggio saliva in 22 casi su 47 (scarpe da corsa) e in 6 su 14 (Kingshot).
  Ora la stima di un annuncio non letto non supera mai l'annuncio letto più debole. Dopo: 0 su 47 e
  1 su 14 (è l'annuncio più debole stesso, da 14,6 a 21,3). Nella ricerca delle scarpe 77 concetti su 106
  hanno cambiato posizione, tutti non letti; nessun concetto letto ha cambiato punteggio o giudizio e i
  primi 10 sono identici.
- **L'obiettivo del piano veniva letto male.** «1.500 ordini al mese» diventava 0,05 ordini al giorno.
  Ora dà 50. Al ripasso il revisore ha provato 63 frasi e 11 davano ancora un numero sbagliato
  (intervalli come «tra 20 e 30», periodi come «300 ordini in 30 giorni» o «ogni 2 giorni», parole come
  «weekend»). Corretto: il periodo si legge solo se viene subito dopo, come parola intera e senza cifre
  in mezzo; in tutti gli altri casi il programma chiede invece di indovinare. 26 frasi sono ora nei test.
  Un terzo revisore ha poi provato 124 frasi nuove: 51 giuste, 41 con domanda all'utente, 31 ancora
  sbagliate («1 500 ordini al mese» letto 16,67 al giorno, «da 10 ordini al giorno a 30» letto 10,
  «+20 ordini al giorno» letto come totale, «20 ordini al giorno lavorativo» letto 20). La regola è
  stata riscritta: l'obiettivo si legge solo se contiene un solo numero di ordini, nessuna parola di
  aumento o di multiplo, e dopo il periodo finisce o prosegue con una virgola o un semplice «con»,
  «entro». Altri numeri passano solo se sono chiaramente altro (euro, percentuale, ROAS, anno,
  scadenza). Le 29 frasi sbagliate e 11 frasi comuni che devono restare lette sono nei test. Resta
  ambiguo «2,500 ordini al giorno», letto 2.500: un italiano potrebbe voler dire 2,5.

### Problemi medi e piccoli, corretti

- Copertura infinita, giorni negativi e più di tre annunci letti per concetto non falsano più il calcolo.
- Un annuncio letto senza giorni non dà un ritmo; un annuncio di un giorno non sposta più la scala.
- Nel pacchetto il «migliore» è scritto con il suo concetto (Kingshot: più persone al giorno 8.306,
  più persone in tutto 835.709, due concetti diversi); la tabella per età conta concetti e non annunci.
- Oltre 50.000 annunci attivi si scrive «più di 50.000», perché la libreria smette di contare.
- In una ricerca per parola chiave il ritmo di lancio è la somma di tutti gli inserzionisti: il brief lo
  dice e chiede di non dimensionare la produzione su quel numero.
- Dove la copertura nel paese non è pubblicata, il brief non chiede più «perché raggiunge tante persone».
- I numeri del brief in italiano sono scritti all'italiana (2.862,5).
- Specialisti e skill citano solo etichette che il codice scrive davvero: lo controlla un test.

### Lasciato com'è, con il motivo

- **«Da verificare» anche su un concetto letto in parte** (Gabrieli sport, 1 annuncio letto su 2). Toglierlo
  faceva sparire l'etichetta dal caso per cui è nata; accanto è scritto quanti annunci sono stati letti.
- **«Regge nel tempo» dove la copertura non è pubblicata** (ricerca negli Stati Uniti): vale tra i primi
  148 annunci di oltre 50.000, accesi da 90 giorni o più, ed è scritto che la scala viene dalla posizione.
- **HOKA regge nel tempo con un solo annuncio letto di 11 giorni**: il pacchetto scrive le due età.
- **Giorni scritti come testo o creatività mancanti**: il lettore delle schede dà sempre numeri.
- **Annunci aperti e concetti non erano la stessa cosa**: chiedendo 20 annunci i concetti letti
  potevano essere meno (nell'esempio pubblicato, 30 annunci chiesti e 12 concetti letti). Poi deciso e
  corretto: il numero scelto è ora il numero di concetti da leggere. Il programma apre l'annuncio più
  mostrato di ogni concetto, poi il secondo e il terzo degli stessi concetti, fino a un tetto di due
  annunci aperti per ogni concetto chiesto. Se un annuncio non si apre e il tetto lo consente, legge
  il concetto successivo dell'elenco. Quando il tetto ferma la lettura il risultato lo dice, con quanti
  concetti sono stati letti e quanti annunci sono rimasti chiusi (la loro copertura è un minimo).
- **Nelle scarpe i 59 concetti non letti hanno tutti scala 0** e si ordinano solo per giorni e
  creatività: è prudente, non falso.

### Casi piccoli emersi al ripasso, poi corretti

Nessuno toccava i dati reali salvati; la valutazione delle tre ricerche è rimasta identica.

- Un annuncio letto con 0 persone stava sotto il suo gemello non letto (16,7 contro 30,7). Ora lo zero
  letto conta come l'annuncio più debole: chi viene dopo nell'elenco e non è stato letto ha scala 0.
- Un annuncio letto senza data scriveva «copertura non nota»: ora scrive le persone lette e che il ritmo
  al giorno non si conosce. Con un annuncio datato e uno no, la riga dice su quanti è contato il ritmo.
- Se il primo annuncio non si apriva e ne venivano letti altri tre, ne contavano due: ora tre.
- Nel brief senza copertura la terza lente non parla più di persone raggiunte.

### Verificato senza trovare errori

Somma dei punti, ricalcolo della copertura, ordine delle schede, stabilità della scala per posizione,
scala logaritmica, condizioni dei giudizi, nessuna copertura UE nella ricerca negli Stati Uniti, numeri
dei pacchetti e numeri del piano.

## C. Casi difficili

I primi sette sono test sui dati reali in `tests/test_rating.py`; gli ultimi quattro sono in
`tests/test_levels.py` e `tests/test_rating.py`. Per ognuno c'è la ragione per cui la posizione è giusta.

| Caso | Dato reale | Dove finisce | Perché è giusto | Test |
|---|---|---|---|---|
| Annuncio di 1 giorno con molta copertura | Kingshot: 91.509 persone in UE il primo giorno, 476 in Italia | 13° su 14, «In prova» | Un giorno non è un ritmo, e in Italia ha raggiunto 476 persone | `test_one_day_with_a_lot_of_reach_does_not_reach_the_top` |
| Annuncio vecchio con pochi raggiunti | Gabrieli sport: 516 giorni, 47.011 persone, 91 al giorno | 32° su 106, «Da verificare» | La tenuta piena non basta: raggiunge mille volte meno persone del migliore | `test_hard_case_old_ad_with_few_people` |
| Annuncio mostrato quasi solo fuori dal paese cercato | Kingshot: 12.402 persone in UE, 966 in Italia in 53 giorni | 12° su 14, «Nella media» | Per chi studia l'Italia è un annuncio da 18 persone al giorno | `test_hard_case_ad_shown_almost_only_outside_the_searched_country` |
| Ricerca senza copertura | «standing desk», Stati Uniti: 19 annunci con copertura, tutta UE o Regno Unito | Affidabilità media per tutti, nessun «Sta scalando» | La copertura di un altro mercato non dice niente di questo | `test_hard_case_search_without_any_reach_in_the_market` |
| Annuncio catalogo | HOKA: 8 annunci catalogo, 176 giorni, 10.438 al giorno | 3° su 106, «Regge nel tempo» | Vale 1 creatività: è lì per giorni e persone, non per il numero di prodotti | `test_hard_case_catalogue_ad` |
| Stesso annuncio in più lingue | Kingshot: tedesco, inglese, francese, spagnolo | Una riga sola, in cima | Sono lo stesso annuncio: contati a parte riempirebbero la classifica di copie | `test_hard_case_one_ad_in_several_languages` |
| Piccolo negozio contro un marchio grande | Zalando 116.749 al giorno, Cappellettoshop 706, Flexora 4.983 | Zalando 1°, Cappellettoshop 18°, Flexora 2° sopra Decathlon | La scala conta, ma un piccolo che regge da 112 giorni con 5 creatività supera un grande di 15 giorni | `test_hard_case_small_shop_against_a_large_brand` |
| Concetto vecchio con un annuncio nuovo | HOKA: concetto acceso da 176 giorni, annuncio più mostrato di 11 giorni con 114.820 persone (10.438 al giorno), letto 1 annuncio su 8 | 3° su 106, «Regge nel tempo», non «Da verificare» | La tenuta è del concetto, la copertura è dell'annuncio letto: nel dettaglio e nel pacchetto dati sono scritte le due età | `test_hard_case_catalogue_ad`, `test_a_concept_with_a_fresh_ad_is_not_called_forgotten`, `test_a_concept_shows_its_age_and_the_age_of_its_most_shown_ad` |
| Molti annunci per un concetto | Flexora: 5 annunci, 2 letti (201.059 persone in 112 giorni e 184.905 in 58) | 2° su 106, 385.964 persone, 4.983 al giorno, scritto «2 di 5» | Ogni annuncio è diviso per i suoi giorni e poi si somma; leggerne uno solo dava meno della metà | `test_reach_of_a_concept_adds_up_the_ads_that_were_read` |
| Annuncio spento | Dato costruito: acceso il 17 marzo, spento il 19 | Etichetta «Spento», 2 giorni; un concetto con un annuncio ancora acceso non è spento | Un annuncio finito non si giudica come uno attivo; nel pacchetto è fuori dalla tabella «accesi oggi» | `test_ended_ads_are_labelled_as_such`, `test_ended_and_off_topic_ads_are_marked_in_the_pack` |
| Pochi annunci letti (meno di 5) | Dato costruito: sei inserzionisti, copertura letta per quattro | Nessuno «Sta scalando» né «Da verificare»; con tutti e sei letti le stesse due etichette compaiono | Quattro letture non bastano a dire dove sta un annuncio rispetto agli altri | `test_hard_case_fewer_than_five_ads_read_get_no_label_that_compares_them` |

## D. Esempi di Analisi e Piano

Gli esempi in `examples/kingshot-it-2026-11-14/` sono scritti dal pacchetto dati di una ricerca reale
già salvata (nessuna nuova richiesta a Meta), con i quattro specialisti e i modelli delle due skill.

- **Numeri ricondotti al pacchetto:** tutte le cifre dei due testi sono scritte in un file del
  pacchetto; lo controlla `tests/test_examples.py`, insieme agli id degli annunci, agli importi del
  piano e all'assenza di percorsi del computer.
- **Uno specialista corretto e rifatto.** Alla prima lettura lo specialista della copertura aveva
  scritto che «quasi tutta la copertura viene da un solo annuncio», perché «letto 1 annuncio su 58» era
  ambiguo. Il suo file ora dice che quel numero è un minimo; rifatto, ha letto giusto.
- **Revisore indipendente sui testi:** 44 affermazioni ricondotte al pacchetto, 34 giuste, 10 sbagliate
  o fuorvianti. Tre gravi, tutte corrette: «sei dei sette più recenti portano a Google Play» (erano
  cinque; sei sono i sette in fondo alla valutazione); «molti lanci, pochi che restano» e «tiene poco»,
  cioè una sopravvivenza dedotta da una ricerca sola, che il pacchetto dice non misurabile. Corretti
  anche: il ritmo di 42,2 scritto come creatività invece che annunci; «aprono con» detto di video con
  una sola immagine; «i concetti nuovi» senza la fascia di età; il pareggio «più basso» senza la sua
  condizione; due idee del piano che cambiavano più di una cosa; i limiti del passaggio da un gioco
  gratuito a un prodotto da 39,9, ora scritti tra i rischi.
- **Regole aggiunte alle skill** perché gli stessi errori non tornino: la tabella per età non prova
  la sopravvivenza; il ritmo conta annunci; una sola immagine non dice come apre un video; un primo
  giro piccolo scarta, non sceglie un vincitore.
- **Non ricontrollato:** le correzioni ai due testi non sono passate da un secondo revisore.

## E. Schermata dei livelli 2 e 3, dettagli grafici e nuova regola di lettura

Un revisore indipendente ha provato la regola di lettura sulle tre ricerche salvate (9 combinazioni
più 7 casi costruiti), ha confrontato la stima con 18 corse reali senza rete e 24 combinazioni
dell'indirizzo della stima, ha letto 399 testi in italiano e inglese e ha aperto 6 schermate in due
lingue e due temi. Poi un solo ripasso sulle correzioni.

### Problemi trovati (13, nessuno grave) e corretti

- **Il tetto risultava raggiunto anche quando non aveva fermato niente.** Con 14 concetti in elenco
  e 20 chiesti, se un annuncio non si apriva lo schermo diceva «Letti 13 concetti su 20: raggiunto il
  tetto». Ora il tetto si nomina solo se ha lasciato chiusi degli annunci o dei concetti ancora da
  provare. Dopo: stesso caso, nessun messaggio, 14 concetti letti.
- **Un concetto il cui primo annuncio non si apriva non veniva recuperato** se il tetto era già
  pieno di secondi e terzi annunci (10 chiesti, 9 letti). Ora l'ordine è: prima l'annuncio più
  mostrato di ogni concetto; poi, per chi non si è aperto, il suo secondo annuncio, oppure il concetto
  successivo dell'elenco se ne ha uno solo; solo alla fine i secondi e terzi annunci. Dopo: 10 su 10,
  20 annunci aperti con tetto 20, nessuno aperto due volte.
- **Un concetto letto solo dal suo secondo annuncio aveva la copertura ma non veniva contato** e
  nella tabella mostrava un trattino. Ora conta come letto e la tabella mostra i suoi numeri.
- **I fotogrammi si salvavano per tutti i video**, mentre testo e stima dicevano «dei primi dieci
  concetti»: 29 video invece di 10, e il tempo promesso veniva superato (147 secondi contro 141).
  Ora al massimo 10; dopo: 252 secondi contro i 321 promessi.
- **Il pacchetto prendeva i primi N della classifica rifatta dopo la lettura, non gli N concetti
  letti.** Nella ricerca negli Stati Uniti solo 6 dei 10 concetti nel testo erano stati aperti (12 su
  20, 31 su 50). Ora il pacchetto mette prima i concetti letti. Dopo: 10 su 10, 20 su 20, 50 su 50.
- **La stima in token era bassa**: 26.100 («Basso») contro 34.400 reali («Medio»). Il valore per
  concetto è passato da 260 a 400, misurato sui testi veri. Dopo, senza fotogrammi: scarti da −13% a
  +18% e la fascia giusta in 6 casi su 6.
- **L'apertura della cartella dei fotogrammi** dava errore 500 su un corpo non valido e accettava
  una richiesta da un'altra origine. Ora 400 e 403. Su 12 richieste malevole nessuna cartella aperta.
- Piccoli: messaggio dedicato se la copia del comando fallisce; con 0 concetti letti la finestra non
  dice più 10; un concetto ripetuto in elenco non si apre due volte; «1 concetto» al singolare; due
  testi dicevano «annunci» dove erano concetti; l'età «65-65+» è diventata «65+».

### Emerso al ripasso, poi corretto

- **Si leggevano più concetti di quelli chiesti**: con una sostituzione più i secondi annunci del
  concetto fallito, 10 chiesti davano 11 letti (13 con tre annunci falliti). Corretto con la regola
  scritta sopra; un test fissa che i concetti letti non superano mai quelli chiesti.
- La stima del tempo contava ancora i fotogrammi di tutti i video (29 invece di 10): corretta.
- Il messaggio per la copia fallita del comando rimandava a un comando incompleto: riscritto.

### Lasciato com'è, con il motivo

- **Con i fotogrammi la stima in token resta più bassa del testo** (Analisi a 10 concetti: 35.100
  contro 52.600; Piano a 10: «Medio» contro «Alto»). Il confronto è solo indicativo, perché nelle prove
  senza rete i fotogrammi non sono file veri: va rimisurato su una ricerca vera prima di cambiare il
  valore per immagine.
- **Il comando copiato per l'assistente contiene il percorso completo della cartella**, mentre a
  schermo si vede solo il nome: all'assistente il percorso serve, sullo schermo no.
- **Le correzioni emerse al ripasso non sono passate da un secondo ripasso**: sono fissate da test.
- **Lo screenshot `05c-DIMOSTRAZIONE-non-per-il-post-…`** mostra la frase del tetto con numeri messi
  a mano: senza rete il tetto non scatta sui dati salvati. Non va usato come immagine di dati veri.

### Controllo grafico di ogni schermata

Fatto a 1440 px, senza rete, con i dati salvati: 13 schermate, ognuna in chiaro, in scuro e in
inglese. Per ogni schermata uno script ha cercato testi tagliati, scorrimento orizzontale, testi
interni («undefined», nomi di chiavi), percorsi del computer nel testo e negli attributi, separatori
delle migliaia, singolari, errori in console e risposte di errore. Circa 25 screenshot sono stati
anche guardati uno per uno; gli altri sono coperti solo dai controlli dello script.

Cinque difetti trovati, tutti corretti con un test:

- salvare una scheda del progetto non valida lasciava un errore nella console del browser;
- il testo di esempio del campo «Obiettivo» era tagliato;
- in inglese compariva «1 creatives»;
- nelle novità compariva «1 ore tra le due ricerche»;
- il messaggio per la copia fallita del comando (già citato sopra).

Limiti di questo controllo:

- gli stati di errore sono provocati facendo fallire il lettore finto o la chiamata locale: un errore
  di rete vero non si può riprodurre con i dati salvati;
- tre gruppi di screenshot sono dimostrazioni e portano «DIMOSTRAZIONE-non-per-il-post» nel nome: la
  frase del tetto (`05c`) e il confronto con numeri diversi (`10e`, `10f`), dove il secondo lato è una
  ricerca per parola chiave presentata come azienda;
- nei dati di prova le miniature degli annunci non ci sono e i loghi sono finti: negli screenshot si
  vedono le iniziali (e se un logo vero non si carica l'app mostra le iniziali al suo posto);
- nella prima esecuzione il browser di prova potrebbe aver chiesto a Meta le immagini dei loghi; dalla
  seconda ogni richiesta fuori dal computer era bloccata e non ne risultano;
- gli screenshot di sessioni precedenti con i numeri 12, 15, 17, 20, 21, 22 e 24 non sono stati
  rifatti né ricontrollati.
