# Gioco da tavolo di strategia medievale: piano a partire da Kingshot, Italia, 14 novembre 2026

Gli importi sono nella valuta del prezzo scritto nella scheda del progetto. I numeri segnati «dal file
del progetto» sono copiati da `pacchetto/project.md`: li ha calcolati il programma. I numeri di Kingshot
vengono dagli altri file della cartella `pacchetto` e valgono per l'Italia. Un «concetto» è un testo con
tutti gli annunci che lo portano.

Due sigle tornano spesso. **CPA di pareggio**: quanto può costare al massimo, in pubblicità, un
acquisto senza andare in perdita. **ROAS**: incasso diviso spesa pubblicitaria.

## Decisione richiesta

Approvare un primo giro di 5 annunci video per 7 giorni, con una spesa massima di 323,75 in tutto, che
parte solo dopo aver verificato che gli acquisti vengono registrati. Serve a scartare le idee peggiori,
non ancora a scegliere un vincitore.

## Tre priorità

1. **Verificare che gli acquisti vengano registrati, prima di spendere.** Il problema dichiarato è il
   costo per acquisto alto: se un acquisto da 39,9 non arriva a Meta con il suo valore, quel costo non
   si può nemmeno misurare.
2. **Un primo giro di 5 video che mostrano una partita, non la scatola.** I tre concetti di Kingshot
   accesi da 121 a 143 giorni mostrano solo il gioco in azione e hanno un testo di una riga
   (concetto 882123034940286: 143 giorni, 56 creatività, 5.844 persone al giorno in Italia).
3. **Un ritmo fisso di 3 video nuovi a settimana.** Kingshot lancia 42,2 annunci nuovi a settimana tra
   quelli ancora accesi, e oggi 3 dei suoi 14 concetti sono accesi da oltre 90 giorni. Quanti ne
   spegne non si può sapere con una ricerca sola; di certo prova molto. Tre a settimana è quanto una
   persona sola può reggere: è una nostra ipotesi, da confermare con chi li produce.

## I numeri dietro le priorità

| | |
|---|---:|
| Margine per ordine (dal file del progetto) | 25,9 |
| CPA di pareggio (dal file del progetto) | 25,9 |
| Budget del primo giro (5 annunci) | fino a 323,75 |
| Spegnere un annuncio dopo aver speso | da 51,8 a 77,7 senza aggiunte al carrello né vendite |
| Spesa al livello dell'obiettivo (30 ordini al giorno), a pareggio | 777 al giorno, 5.439 a settimana |
| Kingshot: annunci attivi / annunci nuovi a settimana tra quelli ancora accesi | 216 / 42,2, contati su 212 annunci caricati |
| Kingshot: persone raggiunte al giorno in Italia, concetto di mezzo | 3.675 su 12 concetti letti |

## Rischi e cosa non sappiamo

- **Il pareggio vero è più basso di 25,9 se** il prezzo di 39,9 comprende l'IVA, o se spedizione,
  commissioni di pagamento e resi non sono già dentro il costo di 14. Servono quei valori per rifare
  il conto prima del primo giro.
- **Un gioco gratuito per telefono non è un gioco da tavolo da 39,9.** Kingshot chiede di installare
  un'app; noi chiediamo un acquisto. Le persone che raggiunge con un'installazione gratuita, in 27-32
  paesi e con testi in inglese, non dicono quante comprerebbero una scatola in Italia. Prendiamo da
  lui come si mostra un gioco di strategia, non l'idea che basti una riga di testo.
- **Alcuni suoi ganci sono tipici dei giochi gratuiti.** Le ore passate a giocare e i lotti da
  comprare con le monete funzionano dentro un'app; su un gioco da tavolo vanno riprovati da zero. Per
  questo l'idea 5 aggiunge una recensione, che nei testi di Kingshot non c'è mai.
- **Il primo giro non può nominare un vincitore.** 64,75 per annuncio è 2,5 volte il CPA di pareggio:
  a pareggio vuol dire due o tre vendite per annuncio. Bastano per spegnere chi non vende, non per
  scegliere il migliore.
- **Di Kingshot non conosciamo spesa né vendite.** Meta non le pubblica. Durata e persone raggiunte
  sono indizi che un annuncio renda, non prove. E non sappiamo quanti annunci spegne: si potrà
  misurare con la seconda ricerca, tra sette giorni.
- **Le persone raggiunte sono un minimo.** Per i suoi concetti più grandi è stato letto 1 annuncio su
  58, su 28 o su 15.

## Prossimi sette giorni

| Giorno | Cosa | Chi |
|---|---|---|
| 1 | Acquisto di prova da 39,9 e controllo che arrivi a Meta (vedi sotto) | Tu (si può affidare a chi gestisce il sito) |
| 1 | Mandare i valori di IVA, spedizione, commissioni e resi per rifare il pareggio | Tu |
| 2-3 | Girare i 5 video delle idee qui sotto | Tu (si può affidare a chi fa i video) |
| 4 | Accendere il primo giro: 5 annunci, fino a 64,75 l'uno | Tu |
| 5-7 | Ogni giorno: spesa per annuncio, aggiunte al carrello, acquisti, costo per acquisto contro 25,9 | Tu |
| 7 | Rifare la ricerca su Kingshot e leggere cosa è cambiato | Tu |

---

## Controllo prima di spendere

Meta riceve gli acquisti per due strade: il pixel, che è un codice nel sito, e la Conversions API, che
li manda dal server. Devono funzionare tutte e due, altrimenti una parte degli acquisti si perde.

- **Cosa fare il giorno 1:** un acquisto di prova da 39,9 dal sito. In Gestione eventi deve comparire
  un evento di acquisto con valore 39,9 e la valuta giusta, ricevuto sia dal browser sia dal server.
- **Se l'evento manca o arriva senza valore:** si sistema quello, e nient'altro, finché non compare.
  Il primo giro non si accende prima.

## Idee di annuncio

Nessuna copia frasi, nomi o promesse di Kingshot: ognuna prende un meccanismo e lo applica al gioco da
tavolo. Le idee 2, 3 e 5 usano le stesse riprese dell'idea 1 e cambiano una cosa sola, così il
confronto è pulito. «Tipo» è uno dei tipi di annuncio elencati in `pacchetto/overview.md`.

### Idea 1: una mossa vista dall'alto

- **Tipo:** dimostrazione del prodotto
- **Prende da:** il gioco mostrato dall'alto, senza persone e senza spiegazioni (concetto 882123034940286: 143 giorni, 56 creatività, 5.844 persone al giorno in Italia)
- **Gancio:** nei primi tre secondi il tabellone ripreso dall'alto e una mano che muove una pedina dentro il territorio dell'avversario
- **Sviluppo:** la mossa / la risposta dell'avversario / il tabellone a fine partita
- **Prova da mostrare:** nessuna in questo annuncio; si vede solo il gioco
- **Formato:** video, 15 secondi
- **Bottone e pagina di arrivo:** «Acquista ora» verso la pagina del gioco
- **Cosa prova:** è il video di confronto per tutte le altre idee

### Idea 2: la confessione di chi ha giocato

- **Tipo:** dimostrazione del prodotto
- **Prende da:** il testo in prima persona che racconta quanto a lungo si è giocato, quello acceso da più tempo (concetto 882123034940286: 143 giorni, 56 creatività, 5.844 persone al giorno in Italia)
- **Gancio:** le riprese dell'idea 1, con una voce fuori campo che dice a che ora dovevano smettere e a che ora hanno smesso davvero
- **Sviluppo:** la frase / la mossa / il tabellone a fine partita
- **Prova da mostrare:** nessuna in questo annuncio
- **Formato:** video, 15 secondi
- **Bottone e pagina di arrivo:** «Acquista ora» verso la pagina del gioco
- **Cosa prova:** il gancio in prima persona, a parità di immagini con l'idea 1

### Idea 3: il testo che dà un compito

- **Tipo:** dimostrazione del prodotto
- **Prende da:** il testo in seconda persona che mette chi legge davanti a un bisogno da risolvere (concetto 1731950095184534: 15 giorni, 10 creatività, 12.175 persone al giorno in Italia; è recente, quindi è un segnale e non una conferma)
- **Gancio:** le riprese dell'idea 1, con una riga scritta che dice a chi guarda cosa manca al suo regno al primo turno
- **Sviluppo:** il problema del primo turno / la mossa / cosa succede dopo
- **Prova da mostrare:** nessuna in questo annuncio
- **Formato:** video, 15 secondi
- **Bottone e pagina di arrivo:** «Acquista ora» verso la pagina del gioco
- **Cosa prova:** il testo in seconda persona, a parità di immagini con l'idea 1

### Idea 4: prima la scena, poi il tavolo

- **Tipo:** altro: scena realistica, poi prodotto
- **Prende da:** una scena medievale realistica al posto del gioco (concetto 1998843314137956: 15 giorni, 2 creatività, 7.037 persone al giorno in Italia; è recente, e di quel video c'è una sola immagine)
- **Gancio:** tre secondi di una scena in costume, senza testo
- **Sviluppo:** la scena / lo stacco sul tabellone / la mossa dell'idea 1
- **Prova da mostrare:** nessuna in questo annuncio
- **Formato:** video, 20 secondi
- **Bottone e pagina di arrivo:** «Acquista ora» verso la pagina del gioco
- **Cosa prova:** l'apertura: scena realistica contro tabellone subito (idea 1)

### Idea 5: la partita con una recensione

- **Tipo:** dimostrazione del prodotto
- **Prende da:** le stesse riprese dell'idea 1; aggiunge ciò che a Kingshot non serve e a noi forse sì. Nei suoi 14 testi la prova è allo 0% (`pacchetto/copy.md`), ma lui chiede un'installazione gratuita e noi 39,9
- **Gancio:** la stessa mossa dell'idea 1
- **Sviluppo:** la mossa / la risposta dell'avversario / una recensione vera di un cliente a schermo
- **Prova da mostrare:** una recensione verificata, con nome e data
- **Formato:** video, 15 secondi
- **Bottone e pagina di arrivo:** «Acquista ora» verso la pagina del gioco
- **Cosa prova:** la prova: lo stesso video con e senza recensione

## Struttura delle campagne

- **Pubblico:** largo, solo Italia, testi in italiano. Kingshot usa lo stesso pubblico in tutti gli
  annunci letti (12 su 12): tutti i generi, età da 20-65 a 25-65, pubblico largo, nessuna esclusione
  (`pacchetto/reach.md`). Non abbiamo un motivo per restringerlo. Tra i testi di Kingshot con una
  lingua riconosciuta l'italiano non c'è (di 39 annunci la lingua non è stata riconosciuta): che
  l'italiano ci dia un vantaggio è un'ipotesi, e la misuriamo solo con i nostri annunci.
- **Campagne e gruppi di annunci:** due campagne. Una di prova, con un solo gruppo e i 5 annunci
  insieme; una per gli annunci che passano la prova.
- **Dove girano le prove e dove vanno i vincitori:** ogni annuncio nuovo entra nella campagna di prova.
  Passa nell'altra solo quando rispetta la regola «Tenere» qui sotto.

## Piano dei test

- **Giro 1:** 5 annunci accesi insieme, fino a 64,75 l'uno, 323,75 in tutto. Durata 7 giorni: è una
  scelta nostra, per avere ogni giorno della settimana almeno una volta.
- **Ogni giorno, guardare:** spesa per annuncio, aggiunte al carrello, acquisti, costo per acquisto contro 25,9.
- **Spegnere:** un annuncio che ha speso da 51,8 a 77,7 senza aggiunte al carrello né vendite.
- **Tenere:** un annuncio con acquisti a 25,9 o meno l'uno dopo aver speso almeno 51,8. La soglia è una
  nostra regola pratica (due volte il CPA di pareggio, il punto in cui gli altri si spengono), non un
  numero del programma.
- **Alzare il budget:** del 20% ogni due giorni finché il costo per acquisto resta sotto 25,9. Anche
  questa è una regola pratica: con aumenti piccoli Meta non deve ricominciare a imparare a chi mostrare
  l'annuncio.
- **Se nessuno tiene:** si cambia prima la pagina di arrivo (prezzo, spedizione e recensioni in alto),
  poi l'offerta, per ultimo il pubblico. In questo ordine perché sulla nostra pagina non abbiamo ancora
  nessun dato, mentre per restringere il pubblico non abbiamo nessun motivo.
- **Giro 2:** gli annunci tenuti si rifanno cambiando solo i primi tre secondi: l'apertura sul
  tabellone dell'idea 1 contro la scena dell'idea 4.
- **Video nuovi a settimana:** 3. Kingshot lancia 42,2 annunci nuovi a settimana tra quelli ancora
  accesi (elenco letto quasi tutto: 212 su 216; quelli già spenti non si vedono, quindi il ritmo vero è
  uguale o più alto). La quota per i test al livello dell'obiettivo, per la regola pratica del 20%
  della spesa, è 1.087,8 a settimana e regge fino a 16 annunci nuovi a settimana a 64,75 l'uno: ma
  vale a regime, non all'inizio. Una persona sola ne regge 3 (ipotesi nostra). Il primo giro ne usa 5,
  preparati prima.

## Appendice

### 1. Diagnosi del progetto

**Cosa dicono i numeri.** Prezzo 39,9, costo del prodotto 14, margine per ordine 25,9. Un acquisto può
costare in pubblicità al massimo 25,9; il ROAS di pareggio è 1,54. A 30 ordini al giorno la spesa
massima a pareggio è 777 al giorno (`pacchetto/project.md`).

**Cosa è ipotesi, e come si controlla.**
- Che il costo per acquisto alto dipenda dai video e non dalla pagina: si controlla nel primo giro
  guardando quante persone arrivano alla pagina e quante aggiungono al carrello.
- Che il margine sia davvero 25,9: si controlla con i valori di IVA, spedizione, commissioni e resi.

### 2. Lettura del concorrente

Il dettaglio è in `analisi.md`. Per questo prodotto contano quattro cose:

- I testi sono una riga sotto molti video diversi (causa 1, forza media: descrive come scrive, non
  perché un annuncio va meglio); i video accesi da più tempo mostrano il gioco in azione (causa 2,
  forza media).
- Kingshot lancia molto: 6 concetti su 14 hanno meno di 7 giorni, 3 superano i 90 (causa 3, forza
  media). Quanti ne spegne non è misurabile.
- Pubblico largo e uguale ovunque, nessun testo in italiano tra quelli con lingua riconosciuta
  (causa 4, forza media).
- Le scene realistiche e il testo in seconda persona sono su concetti di 8 e 15 giorni: un'ipotesi
  (causa 5).

### 3. Controllo settimanale

- **Quando:** ogni sette giorni dalla prima ricerca; la prossima il 21 novembre 2026.
- **Cosa guardare:** annunci nuovi, spenti e cambiati rispetto alla ricerca precedente; i concetti
  1998843314137956 e 2641423062963167; dove portano i concetti che superano i 30 giorni.
- **Cosa cambierebbe il piano:** se le scene realistiche vengono spente, l'idea 4 esce dal giro 2. Se
  compare un testo in italiano, lo seguiamo: vuol dire che Kingshot investe sull'Italia. Se alla
  seconda ricerca risulta che spegne in pochi giorni gran parte di ciò che lancia, 3 video a settimana
  sono pochi e il ritmo va alzato.
