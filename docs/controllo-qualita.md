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

## C. Casi difficili

Ognuno è un test sui dati reali in `tests/test_rating.py`, con la ragione per cui la posizione è giusta.

| Caso | Dato reale | Dove finisce | Perché è giusto | Test |
|---|---|---|---|---|
| Annuncio di 1 giorno con molta copertura | Kingshot: 91.509 persone in UE il primo giorno, 476 in Italia | 13° su 14, «In prova» | Un giorno non è un ritmo, e in Italia ha raggiunto 476 persone | `test_one_day_with_a_lot_of_reach_does_not_reach_the_top` |
| Annuncio vecchio con pochi raggiunti | Gabrieli sport: 516 giorni, 47.011 persone, 91 al giorno | 37° su 106, «Da verificare» | La tenuta piena non basta: raggiunge mille volte meno persone del migliore | `test_hard_case_old_ad_with_few_people` |
| Annuncio mostrato quasi solo fuori dal paese cercato | Kingshot: 12.402 persone in UE, 966 in Italia in 53 giorni | 12° su 14, «Nella media» | Per chi studia l'Italia è un annuncio da 18 persone al giorno | `test_hard_case_ad_shown_almost_only_outside_the_searched_country` |
| Ricerca senza copertura | «standing desk», Stati Uniti: 19 annunci con copertura, tutta UE o Regno Unito | Affidabilità media per tutti, nessun «Sta scalando» | La copertura di un altro mercato non dice niente di questo | `test_hard_case_search_without_any_reach_in_the_market` |
| Annuncio catalogo | HOKA: 8 annunci catalogo, 176 giorni, 10.438 al giorno | 3° su 106, «Regge nel tempo» | Vale 1 creatività: è lì per giorni e persone, non per il numero di prodotti | `test_hard_case_catalogue_ad` |
| Stesso annuncio in più lingue | Kingshot: tedesco, inglese, francese, spagnolo | Una riga sola, in cima | Sono lo stesso annuncio: contati a parte riempirebbero la classifica di copie | `test_hard_case_one_ad_in_several_languages` |
| Piccolo negozio contro un marchio grande | Zalando 116.749 al giorno, Cappellettoshop 706, Flexora 4.983 | Zalando 1°, Cappellettoshop 18°, Flexora 2° sopra Decathlon | La scala conta, ma un piccolo che regge da 112 giorni con 5 creatività supera un grande di 15 giorni | `test_hard_case_small_shop_against_a_large_brand` |
