# Valutazione degli annunci: prima e dopo

Questa pagina documenta il cambio dell'algoritmo di valutazione, con tre ricerche reali fatte sulla Ad Library pubblica. I dati (elenco degli annunci e copertura letta dalle schede) sono gli stessi per il «prima» e per il «dopo»: cambia solo il calcolo. Le tre ricerche sono salvate in `tests/fixtures/rating_*.json` e fanno da prova nei test.

## La formula in breve

Prima c'era un solo numero: 60 punti dai giorni di attività (pieno a 90) più 40 dal riuso del testo (pieno a 10 copie). Premiava chi teneva acceso a lungo un annuncio copiato molte volte, anche se lo vedevano in pochi.

Ora la valutazione guarda tre cose distinte:

| Parte | Cosa misura | Punti con copertura letta | Punti senza copertura |
|---|---|---:|---:|
| Scala | Persone raggiunte al giorno. Senza copertura: posizione nell'elenco di Meta, ordinato per impressioni totali | 60 | 50 |
| Tenuta | Giorni di attività, piena a 90 giorni | 25 | 30 |
| Investimento creativo | Creatività diverse che portano lo stesso concetto | 15 | 20 |

- **Relativa alla ricerca.** Scala e creatività si misurano rispetto agli altri annunci della stessa ricerca, su scala logaritmica: la scala va da 0 (il valore più basso, al 5° percentile) a 100 (il più alto). La tenuta resta su una soglia fissa, perché tre mesi di spesa sono tre mesi per chiunque.
- **Un annuncio per concetto.** Le copie identiche, le versioni di un annuncio dinamico, gli annunci catalogo e le traduzioni dello stesso annuncio vengono riuniti. Contano come creatività solo i video o le immagini davvero diversi; il numero di annunci riuniti è un'informazione, non dà punti.
- **Affidabilità.** Alta: copertura letta dalla scheda, nel mercato cercato. Media: scala stimata dalla posizione per impressioni (calibrata sugli annunci di cui la copertura è nota, quando ce ne sono). Bassa: solo giorni e creatività.
- **Etichette.** Sta scalando: è nel terzo più alto della ricerca per scala, con scala di almeno 70 su 100. Regge nel tempo: almeno 90 giorni e scala di almeno 40. In prova: meno di 30 giorni. Da verificare: almeno 90 giorni e scala fino a 25, qualunque sia il riuso. Nella media: il resto.
- **Longevità.** Il vecchio calcolo resta visibile nel dettaglio di ogni annuncio, ma non decide più l'ordine.

## «scarpe da corsa», Italia (parola chiave)

181 annunci caricati, 106 dopo averli riuniti per concetto. Dati del 2026-11-14.

### Prima

| # | Inserzionista | Annuncio | Punteggio | Giudizio | Giorni | Riuso del testo | Persone al giorno |
|---:|---|---|---:|---|---:|---:|---:|
| 1 | Cappellettoshop Treviso-M… | Scopri AUTRY: marchio storico di Sneakers f… | 100 | Forte | 134 | 80 | 706 |
| 2 | HOKA | Scopri le nostre scarpe da corsa più amate … | 96 | Forte | 176 | 8 | 274 |
| 3 | Flexora | ⚡ Corri DI PIÙ, soffri di MENO! 🏃‍♂️💨Le sol… | 84 | Forte | 112 | 4 | 1.795 |
| 4 | Top4Running | Addocchiato qualche nuovo capo da corsa? Fa… | 79 | Forte | 249 | 3 | 39 |
| 5 | Medical Market | 🏃‍♂️ SEI UN RUNNER? | 79 | Forte | 241 | 3 | 247 |
| 6 | Gabrieli sport | 🔴 Non corri per paura del dolore? | 72 | Forte | 516 | 2 | 91 |
| 7 | PUMA | Dalla corsa alla linea del traguardo, i pro… | 72 | Forte | 149 | 2 | 282 |
| 8 | Zalando | Vento, stanchezza, traffico: quando hai l’a… | 69 | Buono | 44 | 16 | 114.530 |
| 9 | Feellgood | 🦶 DOPO UNA GIORNATA INTERA IN PIEDI, LE TUE… | 65 | Buono | 69 | 3 | 14 |
| 10 | Correre Naturale | Continui a farti male ogni volta che provi … | 64 | Buono | 46 | 7 | 198 |

### Dopo

| # | Inserzionista | Annuncio | Valutazione | Etichetta | Affidabilità | Persone al giorno | Giorni | Creatività | Annunci riuniti | Tipo |
|---:|---|---|---:|---|---|---:|---:|---:|---:|---|
| 1 | Zalando | Vento, stanchezza, traffico: quando hai l’a… | 87 | Sta scalando | alta | 116.749 | 44 | 9 | 9 | più versioni |
| 2 | HOKA | Scopri le nostre scarpe da corsa più amate … | 65 | Regge nel tempo | alta | 10.438 | 176 | 1 | 8 | catalogo |
| 3 | Decathlon Italia | Vivi la Maratona di Palermo con noi! Dal 13… | 63 | Sta scalando | alta | 102.421 | 15 | 1 | 1 | più versioni |
| 4 | Flexora | ⚡ Corri DI PIÙ, soffri di MENO! 🏃‍♂️💨Le sol… | 61 | Regge nel tempo | alta | 1.795 | 112 | 5 | 5 |  |
| 5 | SHEIN | 1000+ ribassi brand! | 59 | Sta scalando | alta | 66.990 | 13 | 1 | 1 | catalogo |
| 6 | Craft Running ITA | Non fermare i tuoi allenamenti! 🏃‍♂️ Scarpe… | 55 | In prova | alta | 4.998 | 25 | 8 | 8 | più versioni |
| 7 | Subito | Cerchi bici 🚲 usate o accessori 🚴🏻‍♀️🚵🏽‍♂️?… | 54 | Regge nel tempo | alta | 2.995 | 899 | 1 | 1 | catalogo |
| 8 | Private Sport Shop | Corsa o trail running, scarpe o abbigliamen… | 51 | Regge nel tempo | alta | 2.000 | 102 | 1 | 1 | più versioni |
| 9 | Medical Market | 🏃‍♂️ SEI UN RUNNER? | 49 | Nella media | alta | 676 | 241 | 3 | 3 | più versioni |
| 10 | 365 Performance Club | Scarpe da 150 € e calzini presi a caso. È l… | 49 | Nella media | alta | 7.531 | 43 | 1 | 1 |  |

Cosa è cambiato:

- **Zalando**, 116.749 persone al giorno: da 8° (Buono, 69 punti) a 1° (Sta scalando, 87).
- **Cappellettoshop**, 706 persone al giorno: da 1° con 100 punti a 18° con 42 (Nella media). Non è un annuncio catalogo: sono 8 annunci con lo stesso video, ciascuno in più copie identiche (80 in tutto). Il vecchio calcolo li contava come 80 riusi del testo; ora valgono 1 creatività.
- **Gabrieli sport**, attivo da 516 giorni con 91 persone al giorno: da 6° (Forte) a 41°, con l'etichetta Da verificare.
- Distribuzione delle etichette: Sta scalando 3, Regge nel tempo 4, In prova 53, Nella media 41, Da verificare 5.

## Kingshot, Italia (azienda)

212 annunci caricati, 14 dopo averli riuniti per concetto. Dati del 2026-11-14.

### Prima

| # | Inserzionista | Annuncio | Punteggio | Giudizio | Giorni | Riuso del testo | Persone al giorno |
|---:|---|---|---:|---|---:|---:|---:|
| 1 | Kingshot | I can't believe I've played Kingshot for 8 … | 100 | Forte | 143 | 39 | 51.736 |
| 2 | Kingshot | New game released! 🎮🚀 | 100 | Forte | 122 | 23 | 14.965 |
| 3 | Kingshot | Face the danger and build your own Kingdom | 100 | Forte | 121 | 15 | 32.348 |
| 4 | Kingshot | 🛡️ 생존을 위한 영웅이 필요하다! 🛡️ | 63 | Buono | 53 | 5 | 234 |
| 5 | Kingshot | Novo jogo lançado! 🎮🚀 | 63 | Buono | 52 | 5 | 539 |
| 6 | Kingshot | 🛡️ Heroes Needed for Survival! 🛡️ | 54 | Buono | 21 | 25 | 31.890 |
| 7 | Kingshot | Your people need food, resources, and a pla… | 50 | Buono | 15 | 10 | 20.980 |
| 8 | Kingshot | 🔥Why is this game so fun??!?! 😂😂 🎮Play Now👏👏 | 42 | Buono | 3 | 12 | 213 |
| 9 | Kingshot | 🔥Warum ist dieses Spiel so spaßig??!?! 😂😂 🎮… | 41 | Buono | 1 | 13 | 40.458 |
| 10 | Kingshot | What will your first move be in Kingshot? 🤔… | 41 | Buono | 1 | 21 | 484 |

### Dopo

| # | Inserzionista | Annuncio | Valutazione | Etichetta | Affidabilità | Persone al giorno | Giorni | Creatività | Annunci riuniti | Tipo |
|---:|---|---|---:|---|---|---:|---:|---:|---:|---|
| 1 | Kingshot | I can't believe I've played Kingshot for 8 … | 94 | Sta scalando | alta | 51.736 | 143 | 56 | 58 |  |
| 2 | Kingshot | Face the danger and build your own Kingdom | 85 | Regge nel tempo | alta | 32.348 | 121 | 15 | 15 |  |
| 3 | Kingshot | New game released! 🎮🚀 | 83 | Regge nel tempo | alta | 23.499 | 122 | 24 | 28 |  |
| 4 | Kingshot | Your people need food, resources, and a pla… | 66 | Sta scalando | alta | 47.582 | 15 | 10 | 10 |  |
| 5 | Kingshot | 🔥Prouve que tu mérites de régner sur ton Ro… | 64 | Sta scalando | alta | 91.509 | 1 | 3 | 3 |  |
| 6 | Kingshot | Your Break Just Got Medieval 🏰 | 60 | Sta scalando | alta | 45.500 | 15 | 2 | 2 |  |
| 7 | Kingshot | Defend and Fight, now you're invincible! | 58 | Sta scalando | alta | 41.082 | 8 | 3 | 3 |  |
| 8 | Kingshot | 🔥Why is this game so fun??!?! 😂😂 🎮Play Now👏👏 | 58 | In prova | alta | 21.522 | 3 | 24 | 24 |  |
| 9 | Kingshot | Bring Your Alliance to the Fight 🛡️ | 56 | In prova | alta | 25.970 | 4 | 7 | 7 |  |
| 10 | Kingshot | Explore in Kingshot for resources and villa… | 54 | In prova | alta | 21.961 | 10 | 4 | 4 |  |

Cosa è cambiato:

- Prima i primi tre erano a pari merito con 100 punti. Ora sono a 94, 85 e 83.
- Le traduzioni sono riunite: da 21 testi a 14 concetti. Il primo riunisce 58 annunci in 3 lingue riconosciute (de, en, fr), con 56 video diversi.
- Le traduzioni si riconoscono in due modi: lo stesso file video sotto testi in lingue diverse, oppure le stesse emoji e cifre nello stesso ordine in testi di lingue diverse e di lunghezza simile. Un testo tradotto senza emoji né cifre e con un video diverso resta separato.
- Distribuzione delle etichette: Sta scalando 5, Regge nel tempo 2, In prova 6, Nella media 1.

## «standing desk», Stati Uniti (parola chiave, fuori da UE e Regno Unito)

148 annunci caricati, 114 dopo averli riuniti per concetto. Dati del 2026-11-14.

### Prima

| # | Inserzionista | Annuncio | Punteggio | Giudizio | Giorni | Riuso del testo | Persone al giorno |
|---:|---|---|---:|---|---:|---:|---:|
| 1 | Willis Judd | I quit my Saturday round of golf because my… | 100 | Forte | 170 | 16 | 812 |
| 2 | Brain.fm | Spotify isn't built for focus. Brain.fm is 🎯 | 96 | Forte | 180 | 8 | 1.097 |
| 3 | Sociallysabrina | Back pain shouldn’t run your life. | 91 | Forte | 96 | 6 | – |
| 4 | Vanture Customs | 🚐 Get $4,000 Off MSRP - Turn your cargo van… | 79 | Forte | 184 | 3 | – |
| 5 | Eureka Ergonomic | The Aero Pro Wing-Shaped Desk is designed t… | 79 | Forte | 110 | 3 | – |
| 6 | Sedeta | 😵 Too many things on your desk? | 72 | Forte | 254 | 2 | – |
| 7 | Bloon | 😲 A chair that actually takes care of you? … | 72 | Forte | 184 | 2 | – |
| 8 | Pocket FM Stories | She lived in hell … now she’s ready to watc… | 72 | Forte | 178 | 2 | – |
| 9 | at_home_with_britt | Proof that the right setup really does chan… | 72 | Forte | 173 | 2 | – |
| 10 | Cholesterol Relief Commun… | I found a wallet in a shopping cart at Walm… | 72 | Forte | 172 | 2 | 254 |

### Dopo

| # | Inserzionista | Annuncio | Valutazione | Etichetta | Affidabilità | Persone al giorno | Giorni | Creatività | Annunci riuniti | Tipo |
|---:|---|---|---:|---|---|---:|---:|---:|---:|---|
| 1 | Willis Judd | I quit my Saturday round of golf because my… | 99 | Regge nel tempo | media | – | 170 | 11 | 11 | più versioni |
| 2 | Cholesterol Relief Commun… | I found a wallet in a shopping cart at Walm… | 86 | Regge nel tempo | media | – | 172 | 2 | 2 |  |
| 3 | Margaret Whittaker | My husband said I was "getting a little sta… | 83 | Regge nel tempo | media | – | 105 | 2 | 2 |  |
| 4 | Cholesterol Relief Commun… | I refused Metformin for 3 years. Here's wha… | 80 | Regge nel tempo | media | – | 158 | 1 | 1 |  |
| 5 | Cholesterol Relief Commun… | My husband slid a jar of pickles across the… | 78 | Regge nel tempo | media | – | 109 | 1 | 1 |  |
| 6 | Bloon | 😲 A chair that actually takes care of you? … | 77 | Regge nel tempo | media | – | 184 | 1 | 1 |  |
| 7 | Hulala Home Furniture | Extra 20% off code: IDA20 | 76 | Regge nel tempo | media | – | 173 | 1 | 1 |  |
| 8 | Pocket FM Stories | - The Alpha who never chose anyone…found hi… | 75 | Regge nel tempo | media | – | 158 | 1 | 1 | più versioni |
| 9 | Pocket FM Stories | Will Duke Edgar save Alesandra’s life or co… | 74 | Regge nel tempo | media | – | 144 | 1 | 1 | più versioni |
| 10 | National Business Furnitu… | A better standing desk does not need to bre… | 74 | Regge nel tempo | media | – | 123 | 1 | 1 |  |

Cosa succede senza copertura:

- Per 19 annunci la scheda riporta una copertura, ma riguarda UE e Regno Unito, non gli Stati Uniti. È mostrata come informazione e non entra nella valutazione: per questo la colonna «Persone al giorno» è vuota.
- Tutti gli annunci hanno affidabilità media: la scala viene dalla posizione per impressioni.
- Verifica dell'ordine: negli Stati Uniti l'ordine predefinito dell'elenco coincide, sui primi 30 risultati, con l'ordinamento esplicito per impressioni totali (`sort_data[mode]=total_impressions`), e non ha nessun annuncio in comune con l'altro ordinamento disponibile. Quindi la posizione si può usare anche fuori da UE e Regno Unito.
- Limite: le impressioni totali crescono con il tempo, quindi senza copertura la classifica favorisce gli annunci accesi da più tempo. È il motivo per cui l'affidabilità è media e non alta.
- Distribuzione delle etichette: Regge nel tempo 30, Sta scalando 18, Nella media 49, Da verificare 10, In prova 7.

## Limiti noti

- La copertura al giorno di un annuncio acceso da uno o due giorni è alta per costruzione (tutta la copertura divisa per pochi giorni).
- La copertura è quella dell'annuncio più mostrato del gruppo, non la somma del gruppo.
- La scala è relativa agli annunci di cui la copertura è stata letta: leggendone di più cambia il riferimento.
- Meta non pubblica spesa né vendite: la valutazione resta un indizio, non una prova.
