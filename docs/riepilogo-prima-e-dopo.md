# Valutazione degli annunci: riepilogo del prima e del dopo

Una pagina sola. Il dettaglio, annuncio per annuncio, è in [valutazione.md](valutazione.md); cosa
misura ogni numero, le revisioni indipendenti e i casi difficili sono in
[controllo-qualita.md](controllo-qualita.md). I numeri qui sotto vengono da tre ricerche reali
salvate nei test (`tests/fixtures/rating_*.json`): gli stessi dati per il prima e per il dopo.

## La formula

| | Prima | Dopo |
|---|---|---|
| Cosa conta | Un solo numero: 60 punti dai giorni di attività, 40 dal riuso del testo | Tre parti sempre visibili: scala 60, tenuta 25, investimento creativo 15 |
| Scala | Non c'era: chi veniva visto da pochi poteva essere primo | Persone raggiunte al giorno nel paese cercato, rispetto al migliore della ricerca |
| Su chi si misura | — | Il paese cercato, non tutta l'UE; dove Meta non pubblica la copertura, la posizione nel suo elenco, e lo si dice |
| Annunci giovani | Un giorno di attività valeva come un ritmo | Mai meno di 7 giorni nel calcolo; sotto i 7 giorni «troppo recente per giudicare» |
| Copie | 80 copie dello stesso video contavano come 80 riusi | Un annuncio per concetto: copie, versioni automatiche, cataloghi e traduzioni riuniti |
| Annunci non letti | — | Una stima prudente dalla posizione, mai sopra l'annuncio letto più debole |
| Affidabilità | Non dichiarata | Alta, media o bassa, scritta accanto a ogni valutazione |

## Cosa è cambiato sui dati reali

**«scarpe da corsa», Italia** (181 annunci, 106 concetti)

- Zalando, 5.136.974 persone in Italia in 44 giorni (116.749 al giorno): da 8° a 1°.
- Cappellettoshop, 94.660 persone in 134 giorni (706 al giorno): da 1° con 100 punti a 18° con 41.
  Erano 8 annunci con lo stesso video, in più copie identiche.
- Gabrieli sport, acceso da 516 giorni con 47.011 persone in tutto (91 al giorno): da 6° a 32°, con
  l'etichetta «Da verificare».

**Kingshot, Italia** (212 annunci, 14 concetti)

- Prima i primi tre erano a pari merito con 100 punti; ora sono a 97, 94 e 90.
- Il primo annuncio ha raggiunto 7.398.228 persone in tutta l'UE ma 835.709 in Italia: la valutazione
  usa le seconde (5.844 al giorno).
- L'annuncio di un giorno, con 91.509 persone in UE e 476 in Italia, era 5° con «Sta scalando»; ora è
  13°, «In prova», con 68 persone al giorno.
- Le traduzioni sono riunite: da 21 testi a 14 concetti.

**«standing desk», Stati Uniti** (148 annunci caricati su oltre 50.000, 114 concetti)

- Meta non pubblica la copertura negli Stati Uniti: la scala viene dalla posizione nel suo elenco,
  l'affidabilità è media per tutti, e nessun annuncio è chiamato «Sta scalando» o «Da verificare».
- Per 19 annunci esiste una copertura in UE o nel Regno Unito: è mostrata come informazione e non
  entra nella valutazione.

## Cosa hanno corretto i revisori indipendenti

| Problema trovato | Prima | Dopo |
|---|---|---|
| Un annuncio non letto poteva stare sopra lo stesso annuncio letto | Succedeva in 22 casi su 47 (scarpe) e in 6 su 14 (Kingshot) | 0 su 47 e 1 su 14 (l'annuncio più debole stesso) |
| L'obiettivo del piano letto male | «1.500 ordini al mese» diventava 0,05 al giorno; su 124 frasi nuove, 31 sbagliate | Letto solo se è un totale chiaro; altrimenti il programma chiede. Le frasi sbagliate sono nei test |
| Chiedendo 20 annunci si leggevano meno concetti | 30 annunci chiesti, 12 concetti letti | Il numero scelto è il numero di concetti; tetto di due annunci aperti per concetto, e mai più concetti letti di quelli chiesti |
| Il pacchetto conteneva concetti mai aperti | 6 su 10 letti nella ricerca negli Stati Uniti | 10 su 10, 20 su 20, 50 su 50 |
| La stima di consumo era bassa | 26.100 token stimati contro 34.400 reali | Fascia giusta in 6 casi su 6 senza fotogrammi |

## Cosa resta vero anche dopo

- Meta non pubblica né spesa né vendite: la valutazione è un indizio di ciò che un inserzionista
  continua a pagare, non una prova che renda.
- La copertura esiste solo per gli annunci mostrati nell'UE o nel Regno Unito.
- La copertura conta persone uniche, che crescono più piano dei giorni: un annuncio acceso da mesi
  mostra meno persone al giorno di quante ne aveva all'inizio. Accanto al dato al giorno c'è sempre
  il totale.
- Di un concetto si leggono al massimo tre annunci: la sua copertura è un minimo.
- Una ricerca sola mostra ciò che è acceso oggi. Quanti annunci vengono spenti si misura solo dalla
  seconda ricerca salvata della stessa azienda.
- Con i fotogrammi la stima di consumo resta più bassa del testo preparato.
