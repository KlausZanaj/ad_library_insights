# Valutazione degli annunci: prima e dopo

Questa pagina documenta il cambio dell'algoritmo di valutazione, con tre ricerche reali fatte sulla Ad Library pubblica. I dati (elenco degli annunci e copertura letta dalle schede) sono gli stessi per il «prima» e per il «dopo»: cambia solo il calcolo. Le tre ricerche sono salvate in `tests/fixtures/rating_*.json` e fanno da prova nei test (`tests/test_rating.py`).

## La formula in breve

Prima c'era un solo numero: 60 punti dai giorni di attività (pieno a 90) più 40 dal riuso del testo (pieno a 10 copie). Premiava chi teneva acceso a lungo un annuncio copiato molte volte, anche se lo vedevano in pochi.

Ora la valutazione guarda tre cose distinte:

| Parte | Cosa misura | Punti |
|---|---|---:|
| Scala | Persone raggiunte al giorno nel paese cercato. Senza quel dato: posizione nell'elenco di Meta, ordinato per impressioni totali | 60 |
| Tenuta | Giorni di attività, piena a 90 giorni | 25 |
| Investimento creativo | Creatività diverse che portano lo stesso concetto, piene a 10 | 15 |

- **Il paese cercato, non tutta l'UE.** Meta pubblica la copertura paese per paese. La scala usa le persone raggiunte nel paese della ricerca; il totale UE resta nel dettaglio come informazione. Se il paese cercato non è tra quelli coperti (Stati Uniti, per esempio), la copertura UE o del Regno Unito è mostrata ma non valuta.
- **Mai meno di 7 giorni.** La copertura al giorno è il totale diviso i giorni di attività dell'annuncio, e mai per meno di 7. Un annuncio acceso da meno di 7 giorni resta «In prova» e nel dettaglio dice «troppo recente per giudicare».
- **Scala relativa al migliore.** 100 all'annuncio che raggiunge più persone al giorno nella ricerca, 0 a chi ne raggiunge mille volte meno, su scala logaritmica. Togliere o aggiungere annunci deboli non sposta gli altri. La tenuta e le creatività hanno soglie fisse (90 giorni, 10 creatività).
- **Gli stessi punti, con o senza copertura.** Un annuncio di cui non si è letta la copertura non prende mai più punti di uno letto solo perché mancano i dati. Senza copertura la scala viene dalla posizione nell'elenco di Meta, misurata sull'intero elenco e non sulla parte caricata.
- **Un annuncio per concetto.** Le copie identiche, le versioni di un annuncio dinamico, gli annunci catalogo e le traduzioni dello stesso annuncio vengono riuniti. Contano come creatività solo i video o le immagini davvero diversi. Se un concetto gira come più annunci, se ne leggono fino a tre, i più mostrati, e la loro copertura si somma: accanto è scritto quanti ne sono stati letti.
- **Affidabilità.** Alta: copertura nel paese cercato letta dalla scheda. Media: scala dalla posizione per impressioni (calibrata sugli annunci letti, quando ce ne sono). Bassa: solo giorni e creatività.
- **Etichette.** Sta scalando: tra 14 e 89 giorni, scala di almeno 70 e nel terzo più alto della ricerca. Regge nel tempo: almeno 90 giorni e scala di almeno 40. In prova: meno di 30 giorni. Da verificare: almeno 90 giorni, nessun annuncio nuovo nel concetto, scala fino a 25 e poche persone raggiunte in tutto (sotto la mediana). Spento: non più attivo. Nella media: il resto. «Sta scalando» e «Da verificare» si danno solo su copertura letta, per almeno cinque annunci.
- **Longevità.** Il vecchio calcolo resta visibile nel dettaglio di ogni annuncio, ma non decide più l'ordine.

## «scarpe da corsa», Italia (parola chiave)

181 annunci caricati, 106 dopo averli riuniti per concetto. Dati del 14 novembre 2026.

### Prima (punteggio di longevità)

| # | Inserzionista | Annuncio | Punteggio | Giudizio | Giorni | Riuso del testo | Dove è ora |
|---:|---|---|---:|---|---:|---:|---:|
| 1 | Cappellettoshop Treviso… | Scopri AUTRY: marchio storico di Sneake… | 100 | Forte | 134 | 80 | 18° |
| 2 | HOKA | Scopri le nostre scarpe da corsa più am… | 96 | Forte | 176 | 8 | 3° |
| 3 | Flexora | ⚡ Corri DI PIÙ, soffri di MENO! 🏃‍♂️💨Le… | 84 | Forte | 112 | 4 | 2° |
| 4 | Top4Running | Addocchiato qualche nuovo capo da corsa… | 79 | Forte | 249 | 3 | 42° |
| 5 | Medical Market | 🏃‍♂️ SEI UN RUNNER? | 79 | Forte | 241 | 3 | 10° |
| 6 | Gabrieli sport | 🔴 Non corri per paura del dolore? | 72 | Forte | 516 | 2 | 32° |
| 7 | PUMA | Dalla corsa alla linea del traguardo, i… | 72 | Forte | 149 | 2 | 23° |
| 8 | Zalando | Vento, stanchezza, traffico: quando hai… | 69 | Buono | 44 | 16 | 1° |
| 9 | Feellgood | 🦶 DOPO UNA GIORNATA INTERA IN PIEDI, LE… | 65 | Buono | 69 | 3 | 15° |
| 10 | Correre Naturale | Continui a farti male ogni volta che pr… | 65 | Buono | 46 | 7 | 16° |

### Dopo (valutazione attuale)

| # | Inserzionista | Annuncio | Valutazione | Etichetta | Affidabilità | Raggiunte in Italia | Al giorno | Totale UE | Giorni | Creatività | Annunci riuniti | Tipo |
|---:|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | Zalando | Vento, stanchezza, traffico: quando hai… | 87 | Sta scalando | alta | 5.136.974 | 116.749 | 5.136.974 | 44 | 9 | 9 | più versioni |
| 2 | Flexora | ⚡ Corri DI PIÙ, soffri di MENO! 🏃‍♂️💨Le… | 68 | Regge nel tempo | alta | 385.964 | 4.983 | 201.059 | 112 | 5 | 5 |  |
| 3 | HOKA | Scopri le nostre scarpe da corsa più am… | 64 | Regge nel tempo | alta | 114.820 | 10.438 | 114.820 | 176 | 1 | 8 | catalogo |
| 4 | Decathlon Italia | Vivi la Maratona di Palermo con noi! Da… | 63 | Sta scalando | alta | 1.536.314 | 102.421 | 1.536.314 | 15 | 1 | 1 | più versioni |
| 5 | SHEIN | 1000+ ribassi brand! | 59 | In prova | alta | 870.868 | 66.990 | 870.868 | 13 | 1 | 1 | catalogo |
| 6 | Subito | Cerchi bici 🚲 usate o accessori 🚴🏻‍♀️🚵🏽… | 53 | Regge nel tempo | alta | 2.692.918 | 2.995 | 2.692.918 | 899 | 1 | 1 | catalogo |
| 7 | Craft Running ITA | Non fermare i tuoi allenamenti! 🏃‍♂️ Sc… | 53 | In prova | alta | 124.938 | 4.998 | 124.938 | 25 | 8 | 8 | più versioni |
| 8 | Private Sport Shop | Corsa o trail running, scarpe o abbigli… | 50 | Regge nel tempo | alta | 204.035 | 2.000 | 204.035 | 102 | 1 | 1 | più versioni |
| 9 | 365 Performance Club | Scarpe da 150 € e calzini presi a caso.… | 48 | Nella media | alta | 323.838 | 7.531 | 323.838 | 43 | 1 | 1 |  |
| 10 | Medical Market | 🏃‍♂️ SEI UN RUNNER? | 47 | Nella media | alta | 105.504 | 676 | 105.504 | 241 | 3 | 3 | più versioni |

Cosa è cambiato:

- **Zalando**, 5.136.974 persone in Italia in 44 giorni (116.749 al giorno): da 8° (Buono, 69 punti) a 1° (Sta scalando, 87).
- **Cappellettoshop**, 94.660 persone in 134 giorni (706 al giorno): da 1° con 100 punti a 18° con 41 (Nella media). Non è un annuncio catalogo: sono 8 annunci con lo stesso video, ciascuno in più copie identiche. Il vecchio calcolo li contava come 80 riusi del testo; ora valgono 1 creatività.
- **Gabrieli sport**, acceso da 516 giorni, 47.011 persone in tutto (91 al giorno): da 6° (Forte) a 32°, con l'etichetta Da verificare.
- In questa ricerca tutti gli annunci letti sono stati mostrati solo in Italia: il totale UE coincide con le persone raggiunte in Italia.
- Distribuzione delle etichette: Sta scalando 2, Regge nel tempo 4, In prova 53, Da verificare 4, Nella media 41, Spento 2.

## Kingshot, Italia (azienda)

212 annunci caricati, 14 dopo averli riuniti per concetto. Dati del 14 novembre 2026.

### Prima (punteggio di longevità)

| # | Inserzionista | Annuncio | Punteggio | Giudizio | Giorni | Riuso del testo | Dove è ora |
|---:|---|---|---:|---|---:|---:|---:|
| 1 | Kingshot | I can't believe I've played Kingshot fo… | 100 | Forte | 143 | 39 | 1° |
| 2 | Kingshot | New game released! 🎮🚀 | 100 | Forte | 122 | 23 | 3° |
| 3 | Kingshot | Face the danger and build your own King… | 100 | Forte | 121 | 15 | 2° |
| 4 | Kingshot | 🛡️ 생존을 위한 영웅이 필요하다! 🛡️ | 63 | Buono | 53 | 5 | 12° |
| 5 | Kingshot | Novo jogo lançado! 🎮🚀 | 63 | Buono | 52 | 5 | 3° |
| 6 | Kingshot | 🛡️ Heroes Needed for Survival! 🛡️ | 54 | Buono | 21 | 25 | 12° |
| 7 | Kingshot | Your people need food, resources, and a… | 50 | Buono | 15 | 10 | 4° |
| 8 | Kingshot | 🔥Why is this game so fun??!?! 😂😂 🎮Play … | 42 | Buono | 3 | 12 | 9° |
| 9 | Kingshot | 🔥Warum ist dieses Spiel so spaßig??!?! … | 41 | Buono | 1 | 13 | 9° |
| 10 | Kingshot | What will your first move be in Kingsho… | 41 | Buono | 1 | 21 | 11° |

### Dopo (valutazione attuale)

| # | Inserzionista | Annuncio | Valutazione | Etichetta | Affidabilità | Raggiunte in Italia | Al giorno | Totale UE | Giorni | Creatività | Annunci riuniti | Tipo |
|---:|---|---|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | Kingshot | I can't believe I've played Kingshot fo… | 97 | Regge nel tempo | alta | 835.709 | 5.844 | 7.398.228 | 143 | 56 | 58 |  |
| 2 | Kingshot | Face the danger and build your own King… | 94 | Regge nel tempo | alta | 506.326 | 4.185 | 3.914.051 | 121 | 15 | 15 |  |
| 3 | Kingshot | New game released! 🎮🚀 | 90 | Regge nel tempo | alta | 327.188 | 2.704 | 2.843.429 | 122 | 24 | 28 |  |
| 4 | Kingshot | Your people need food, resources, and a… | 79 | Sta scalando | alta | 124.591 | 8.306 | 713.728 | 15 | 10 | 10 |  |
| 5 | Kingshot | Your Break Just Got Medieval 🏰 | 67 | Sta scalando | alta | 105.553 | 7.037 | 682.503 | 15 | 2 | 2 |  |
| 6 | Kingshot | Defend and Fight, now you're invincible! | 65 | In prova | alta | 41.357 | 5.170 | 328.654 | 8 | 3 | 3 |  |
| 7 | Kingshot | Explore in Kingshot for resources and v… | 64 | In prova | alta | 32.875 | 3.288 | 219.607 | 10 | 4 | 4 |  |
| 8 | Kingshot | Bring Your Alliance to the Fight 🛡️ | 59 | In prova | alta | 10.585 | 1.512 | 103.880 | 4 | 7 | 7 |  |
| 9 | Kingshot | 🔥Why is this game so fun??!?! 😂😂 🎮Play … | 59 | In prova | alta | 7.984 | 1.141 | 64.566 | 3 | 24 | 24 |  |
| 10 | Kingshot | Your Medieval Chapter Begins 🏰 | 47 | In prova | alta | 7.024 | 1.003 | 77.808 | 3 | 2 | 2 |  |

Cosa è cambiato:

- Prima i primi tre erano a pari merito con 100 punti. Ora sono a 97, 94 e 90.
- Le traduzioni sono riunite: da 21 testi a 14 concetti. Il primo riunisce 58 annunci, con 56 video diversi.
- **La scala è quella dell'Italia.** Il primo annuncio ha raggiunto 7.398.228 persone in tutta l'UE, ma 835.709 in Italia: la valutazione usa le seconde (5.844 al giorno).
- **L'annuncio di 1 giorno non scala più.** Nel suo primo giorno ha raggiunto 91.509 persone in UE, di cui 476 in Italia. Con il totale UE diviso per un giorno era 5° con «Sta scalando»; ora è 13°, «In prova», con 68 persone al giorno (476 divise per 7 giorni).
- Le traduzioni si riconoscono in due modi: lo stesso file video sotto testi in lingue diverse, oppure le stesse emoji e cifre nello stesso ordine in testi di lingue diverse e di lunghezza simile. Un testo tradotto senza emoji né cifre e con un video diverso resta separato.
- Distribuzione delle etichette: Sta scalando 2, Regge nel tempo 3, In prova 8, Nella media 1.

## «standing desk», Stati Uniti (parola chiave, fuori da UE e Regno Unito)

148 annunci caricati, 114 dopo averli riuniti per concetto. Dati del 14 novembre 2026.

### Prima (punteggio di longevità)

| # | Inserzionista | Annuncio | Punteggio | Giudizio | Giorni | Riuso del testo | Dove è ora |
|---:|---|---|---:|---|---:|---:|---:|
| 1 | Willis Judd | I quit my Saturday round of golf becaus… | 100 | Forte | 170 | 16 | 1° |
| 2 | Brain.fm | Spotify isn't built for focus. Brain.fm… | 96 | Forte | 180 | 8 | 11° |
| 3 | Sociallysabrina | Back pain shouldn’t run your life. | 91 | Forte | 96 | 6 | 44° |
| 4 | Vanture Customs | 🚐 Get $4,000 Off MSRP - Turn your cargo… | 79 | Forte | 184 | 3 | 32° |
| 5 | Eureka Ergonomic | The Aero Pro Wing-Shaped Desk is design… | 79 | Forte | 110 | 3 | 52° |
| 6 | Sedeta | 😵 Too many things on your desk? | 72 | Forte | 254 | 2 | 37° |
| 7 | Bloon | 😲 A chair that actually takes care of y… | 72 | Forte | 184 | 2 | 6° |
| 8 | Pocket FM Stories | She lived in hell … now she’s ready to … | 72 | Forte | 178 | 2 | 59° |
| 9 | at_home_with_britt | Proof that the right setup really does … | 72 | Forte | 173 | 2 | 31° |
| 10 | Cholesterol Relief Comm… | I found a wallet in a shopping cart at … | 72 | Forte | 172 | 2 | 2° |

### Dopo (valutazione attuale)

| # | Inserzionista | Annuncio | Valutazione | Etichetta | Affidabilità | Posizione per impressioni | Copertura UE o Regno Unito (non valuta) | Giorni | Creatività | Annunci riuniti | Tipo |
|---:|---|---|---:|---|---|---:|---:|---:|---:|---:|---|
| 1 | Willis Judd | I quit my Saturday round of golf becaus… | 91 | Regge nel tempo | media | 5 | 279.262 | 170 | 11 | 11 | più versioni |
| 2 | Cholesterol Relief Comm… | I found a wallet in a shopping cart at … | 90 | Regge nel tempo | media | 1 | 239.279 | 172 | 2 | 2 |  |
| 3 | Cholesterol Relief Comm… | I refused Metformin for 3 years. Here's… | 81 | Regge nel tempo | media | 2 | 99.544 | 158 | 1 | 1 |  |
| 4 | Margaret Whittaker | My husband said I was "getting a little… | 76 | Regge nel tempo | media | 11 | – | 105 | 2 | 2 |  |
| 5 | Cholesterol Relief Comm… | My husband slid a jar of pickles across… | 74 | Regge nel tempo | media | 8 | 8.801 | 109 | 1 | 1 |  |
| 6 | Bloon | 😲 A chair that actually takes care of y… | 73 | Regge nel tempo | media | 9 | – | 184 | 1 | 1 |  |
| 7 | Hulala Home Furniture | Extra 20% off code: IDA20 | 70 | Regge nel tempo | media | 15 | – | 173 | 1 | 1 |  |
| 8 | Pocket FM Stories | - The Alpha who never chose anyone…foun… | 70 | Regge nel tempo | media | 16 | – | 158 | 1 | 1 | più versioni |
| 9 | Pocket FM Stories | Will Duke Edgar save Alesandra’s life o… | 69 | Regge nel tempo | media | 18 | – | 144 | 1 | 1 | più versioni |
| 10 | National Business Furni… | A better standing desk does not need to… | 69 | Regge nel tempo | media | 19 | – | 123 | 1 | 1 |  |

Cosa succede senza copertura nel paese cercato:

- Per 19 annunci la scheda riporta una copertura, ma riguarda UE e Regno Unito, non gli Stati Uniti. È mostrata come informazione e non entra nella valutazione.
- Tutti gli annunci hanno affidabilità media: la scala viene dalla posizione per impressioni.
- Verifica dell'ordine: negli Stati Uniti l'ordine predefinito dell'elenco coincide, sui primi 30 risultati, con l'ordinamento esplicito per impressioni totali (`sort_data[mode]=total_impressions`), e non ha nessun annuncio in comune con l'altro ordinamento disponibile. Quindi la posizione si può usare anche fuori da UE e Regno Unito.
- Limite: le impressioni totali crescono con il tempo, quindi senza copertura la classifica favorisce gli annunci accesi da più tempo. È il motivo per cui l'affidabilità è media e non alta.
- Dalla sola posizione non si dice mai «Sta scalando» né «Da verificare»: qui le etichette sono solo «Regge nel tempo» (almeno 90 giorni, nella parte alta dell'elenco), «In prova» e «Nella media».
- La posizione è misurata sull'intero elenco di Meta (oltre 50.000 annunci per questa ricerca), non sui 148 caricati: caricarne di più o di meno non cambia la valutazione degli altri.
- Distribuzione delle etichette: Regge nel tempo 48, In prova 11, Nella media 55.

## Le correzioni, annuncio per annuncio (Kingshot, Italia)

La prima versione della nuova valutazione divideva la copertura di tutta l'UE per i giorni di attività, anche se erano uno o due. Qui sotto la stessa classifica prima e dopo le correzioni (paese cercato, minimo 7 giorni, e quelle chieste dal revisore indipendente).

| Annuncio | Giorni | Totale UE | Raggiunte in Italia | Prima: al giorno (UE) | Prima: posto ed etichetta | Ora: al giorno (Italia) | Ora: posto ed etichetta |
|---|---:|---:|---:|---:|---|---:|---|
| I can't believe I've played Kingsho… | 143 | 7.398.228 | 835.709 | 51.736 | 1°, Sta scalando | 5.844 | 1°, Regge nel tempo |
| Face the danger and build your own … | 121 | 3.914.051 | 506.326 | 32.348 | 2°, Regge nel tempo | 4.185 | 2°, Regge nel tempo |
| New game released! 🎮🚀 | 122 | 2.843.429 | 327.188 | 23.499 | 3°, Regge nel tempo | 2.704 | 3°, Regge nel tempo |
| Your people need food, resources, a… | 15 | 713.728 | 124.591 | 47.582 | 4°, Sta scalando | 8.306 | 4°, Sta scalando |
| 🔥Prouve que tu mérites de régner su… | 1 | 91.509 | 476 | 91.509 | 5°, Sta scalando | 68 | 13°, In prova |
| Your Break Just Got Medieval 🏰 | 15 | 682.503 | 105.553 | 45.500 | 6°, Sta scalando | 7.037 | 5°, Sta scalando |
| Defend and Fight, now you're invinc… | 8 | 328.654 | 41.357 | 41.082 | 7°, Sta scalando | 5.170 | 6°, In prova |
| 🔥Why is this game so fun??!?! 😂😂 🎮P… | 3 | 64.566 | 7.984 | 21.522 | 8°, In prova | 1.141 | 9°, In prova |
| Bring Your Alliance to the Fight 🛡️ | 4 | 103.880 | 10.585 | 25.970 | 9°, In prova | 1.512 | 8°, In prova |
| Explore in Kingshot for resources a… | 10 | 219.607 | 32.875 | 21.961 | 10°, In prova | 3.288 | 7°, In prova |
| What will your first move be in Kin… | 1 | 20.122 | 2.649 | 20.122 | 11°, In prova | 378 | 11°, In prova |
| Your Medieval Chapter Begins 🏰 | 3 | 77.808 | 7.024 | 25.936 | 12°, In prova | 1.003 | 10°, In prova |
| 🛡️ 생존을 위한 영웅이 필요하다! 🛡️ | 53 | 12.402 | 966 | 234 | 13°, Nella media | 18 | 12°, Nella media |
| 🛡️生存のために英雄が必要だ！🛡️ | 1 | 247 | 44 | 247 | 14°, In prova | 6 | 14°, In prova |

## Limiti noti

- **La copertura conta persone uniche.** Chi vede l'annuncio dieci volte conta una volta. Le persone nuove crescono meno dei giorni: un annuncio acceso da mesi appare con meno persone al giorno di quante ne aveva davvero. Per questo accanto al dato al giorno c'è sempre il totale delle persone raggiunte, in tabella e nel dettaglio.
- **«Da verificare» non è un giudizio negativo.** Vuol dire pochi raggiunti ma acceso da molto: può essere un piccolo budget che funziona o un annuncio dimenticato. Va controllato.
- **Sotto i 7 giorni non si giudica.** La copertura al giorno di un annuncio appena acceso è calcolata su 7 giorni, quindi è prudente: un annuncio che parte forte sale in classifica solo dopo la prima settimana.
- Di un concetto che gira come più annunci si leggono al massimo tre annunci: la sua copertura è la loro somma, non quella di tutto il gruppo, e la stessa persona può comparire in più di un annuncio.
- La tenuta è l'età del concetto, cioè del suo annuncio più vecchio; la copertura è degli annunci letti, che possono essere più recenti. Nel dettaglio è scritto quando le due età sono diverse.
- Senza copertura nel paese cercato la classifica segue l'ordine di Meta corretto con giorni e creatività: dice chi è stato mostrato di più, non quante persone ha raggiunto.
- Una ricerca per parola chiave restituisce anche annunci che non contengono la parola nel testo: Meta la cerca in più campi. Lo strumento li segnala, non li toglie.
- La copertura di un paese è la somma delle fasce di età e genere di quel paese nella scheda di Meta; quando la scheda ha un solo paese si usa il totale della sezione. Le due cifre possono differire di qualche punto percentuale.
- La scala è relativa al migliore annuncio letto: se compare un annuncio molto più grande, gli altri scendono.
- Le traduzioni senza emoji né cifre e con video diversi restano annunci separati.
- Meta non pubblica spesa né vendite: la valutazione resta un indizio, non una prova.
