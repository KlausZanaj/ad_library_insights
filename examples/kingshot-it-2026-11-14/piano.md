# Gioco da tavolo di strategia medievale: piano a partire da Kingshot, Italia, 14 novembre 2026

Gli importi sono nella valuta del prezzo scritto nella scheda del progetto. I numeri segnati «dal file
del progetto» sono copiati da `pacchetto/project.md`: li ha calcolati il programma. I numeri di Kingshot
vengono dagli altri file della cartella `pacchetto` e valgono per l'Italia.

## Decisione richiesta

Approvare un primo giro di prova di 5 annunci video per 7 giorni, con una spesa massima di 323,75 in
tutto, che parte solo dopo aver verificato che gli acquisti vengono registrati.

## Tre priorità

1. **Verificare il tracciamento prima di spendere.** Il problema dichiarato è il costo per acquisto
   alto: se gli acquisti non arrivano con il loro valore, quel costo non si può nemmeno misurare.
2. **Un primo giro di 5 video che mostrano una partita, non la scatola.** I tre concetti di Kingshot
   accesi da 121 a 143 giorni mostrano solo il gioco in azione e hanno un testo di una riga
   (id 882123034940286: 143 giorni, 56 creatività, 5.844 persone al giorno in Italia).
3. **Un ritmo fisso di 3 creatività nuove a settimana.** Kingshot ne lancia 42,2 a settimana e tiene
   acceso oltre i 90 giorni solo 3 concetti su 14: per trovare un annuncio che tiene servono molte
   prove. Tre a settimana è quanto una persona sola può reggere (è una nostra ipotesi, da confermare
   con chi le produce).

## I numeri dietro le priorità

| | |
|---|---:|
| Margine per ordine (dal file del progetto) | 25,9 |
| CPA di pareggio (dal file del progetto) | 25,9 |
| Budget del primo giro (5 annunci) | fino a 323,75 |
| Spegnere un annuncio dopo aver speso | da 51,8 a 77,7 senza aggiunte al carrello né vendite |
| Spesa al livello dell'obiettivo (30 ordini al giorno), a pareggio | 777 al giorno, 5.439 a settimana |
| Kingshot: annunci attivi / nuovi a settimana tra quelli ancora accesi | 216 / 42,2, contati su 212 annunci caricati |
| Kingshot: persone raggiunte al giorno in Italia, concetto di mezzo | 3.675 su 12 concetti letti |

## Rischi e cosa non sappiamo

- **Il pareggio vero è più basso di 25,9.** Il calcolo usa solo il costo del prodotto (14). IVA,
  spedizione, commissioni di pagamento e resi non sono compresi: servono quei valori per rifare il
  conto prima del primo giro.
- **Un gioco gratuito per telefono non è un gioco da tavolo da 39,9.** Kingshot chiede di installare
  un'app; noi chiediamo un acquisto. Prendiamo da lui come si mostra un gioco di strategia a un
  pubblico largo, non l'idea che basti una riga di testo: sulla nostra pagina servono prezzo,
  spedizione e una prova. Si verifica nel primo giro, confrontando un annuncio con la prova e uno senza.
- **Di Kingshot non conosciamo spesa né vendite.** Meta non le pubblica. Durata e persone raggiunte
  sono indizi che un annuncio renda, non prove.
- **Non sappiamo quanti annunci Kingshot spegne.** Con una ricerca sola la sopravvivenza non è
  misurabile; lo diventa con la seconda ricerca, tra sette giorni.
- **Le persone raggiunte sono un minimo.** Per i concetti più grandi è stato letto 1 annuncio su 58,
  su 28 o su 15.

## Prossimi sette giorni

| Giorno | Cosa | Chi |
|---|---|---|
| 1 | Acquisto di prova e controllo del tracciamento | Tu (si può affidare a chi gestisce il sito) |
| 1 | Mandare i valori di IVA, spedizione, commissioni e resi per rifare il pareggio | Tu |
| 2-3 | Girare i 5 video delle idee qui sotto | Tu (si può affidare a chi fa i video) |
| 4 | Accendere il primo giro: 5 annunci, fino a 64,75 l'uno | Tu |
| 5-7 | Ogni giorno: spesa per annuncio, aggiunte al carrello, acquisti, costo per acquisto contro 25,9 | Tu |
| 7 | Rifare la ricerca su Kingshot e leggere cosa è cambiato | Tu |

---

## Controllo prima di spendere

- **Pixel e Conversions API:** devono essere attivi tutti e due. Oggi non sappiamo se lo sono: è la
  prima cosa da guardare.
- **Evento di acquisto:** deve arrivare con valore e valuta.
- **Come verificare:** un acquisto di prova dal sito, poi in Gestione eventi controllare che compaia un
  evento di acquisto con l'importo giusto, ricevuto sia dal browser sia dal server.
- **Se non funziona:** si sistema prima l'evento di acquisto, poi il resto. Il piano parte solo dopo
  che questo controllo è passato.

## Idee di annuncio

Nessuna copia frasi, nomi o promesse di Kingshot: ognuna prende un meccanismo e lo applica al gioco da
tavolo. Ogni idea prova una cosa sola.

### Idea 1: una mossa vista dall'alto

- **Tipo:** dimostrazione del prodotto
- **Prende da:** il gioco mostrato dall'alto, senza persone e senza spiegazioni (annuncio 882123034940286: 143 giorni, 56 creatività, 5.844 persone al giorno in Italia)
- **Gancio:** nei primi tre secondi il tabellone ripreso dall'alto e una mano che muove una pedina dentro il territorio dell'avversario
- **Sviluppo:** la mossa / la risposta dell'avversario / il tabellone a fine partita
- **Prova da mostrare:** nessuna in questo annuncio; si vede solo il gioco
- **Formato:** video, 15 secondi
- **Bottone e pagina di arrivo:** «Acquista ora» verso la pagina del gioco
- **Cosa prova:** se il gioco in azione, da solo, porta alla pagina

### Idea 2: la confessione di chi ha giocato

- **Tipo:** UGC o creator
- **Prende da:** il testo in prima persona che racconta quanto a lungo si è giocato, il più longevo dell'elenco (annuncio 882123034940286: 143 giorni, 56 creatività, 5.844 persone al giorno in Italia)
- **Gancio:** una persona al tavolo, a partita finita, dice a che ora dovevano smettere e a che ora hanno smesso davvero
- **Sviluppo:** la frase / due secondi del tavolo a fine serata / la scatola
- **Prova da mostrare:** la serata vera, con l'orologio in vista
- **Formato:** video, 15 secondi
- **Bottone e pagina di arrivo:** «Acquista ora» verso la pagina del gioco
- **Cosa prova:** il gancio in prima persona contro quello dell'idea 1, sullo stesso tipo di immagini

### Idea 3: il testo che dà un compito

- **Tipo:** dimostrazione del prodotto
- **Prende da:** il testo in seconda persona che mette chi legge davanti a un bisogno da risolvere (annuncio 1731950095184534: 15 giorni, 10 creatività, 12.175 persone al giorno in Italia; è recente, quindi è un segnale e non una conferma)
- **Gancio:** una riga che dice a chi guarda cosa manca al suo regno al primo turno
- **Sviluppo:** il problema del primo turno / le due scelte possibili / cosa succede con una delle due
- **Prova da mostrare:** nessuna in questo annuncio
- **Formato:** video, 15 secondi, le stesse immagini dell'idea 1
- **Bottone e pagina di arrivo:** «Acquista ora» verso la pagina del gioco
- **Cosa prova:** il testo in seconda persona, a parità di video con l'idea 1

### Idea 4: prima la scena, poi il tavolo

- **Tipo:** altro: scena realistica, poi prodotto
- **Prende da:** l'apertura con una scena medievale realistica al posto del gioco (annuncio 1998843314137956: 15 giorni, 2 creatività, 7.037 persone al giorno in Italia; anche questo è recente)
- **Gancio:** tre secondi di una scena in costume, senza testo
- **Sviluppo:** la scena / lo stacco sul tabellone nella stessa posizione / la mossa
- **Prova da mostrare:** nessuna in questo annuncio
- **Formato:** video, 20 secondi
- **Bottone e pagina di arrivo:** «Acquista ora» verso la pagina del gioco
- **Cosa prova:** l'apertura: scena realistica contro tabellone subito (idea 1)

### Idea 5: la partita con la prova

- **Tipo:** dimostrazione del prodotto
- **Prende da:** lo stesso meccanismo dell'idea 1; qui si aggiunge ciò che a Kingshot non serve e a noi forse sì. Nei suoi 14 testi la prova è allo 0% (`pacchetto/copy.md`), ma lui chiede un'installazione gratuita
- **Gancio:** la stessa mossa dell'idea 1
- **Sviluppo:** la mossa / una recensione vera di un cliente a schermo / prezzo e tempi di spedizione
- **Prova da mostrare:** una recensione verificata e il numero di copie vendute, se c'è un dato vero da mostrare
- **Formato:** video, 20 secondi
- **Bottone e pagina di arrivo:** «Acquista ora» verso la pagina del gioco
- **Cosa prova:** la prova: lo stesso video con e senza recensione e prezzo

## Struttura delle campagne

- **Pubblico:** largo, solo Italia, testi in italiano. Kingshot punta tutti i generi, età da 20-65 a
  25-65, pubblico largo e nessuna esclusione su 12 annunci letti su 12, e non ha nessun testo in
  italiano (`pacchetto/reach.md`). Che l'italiano dia un vantaggio è un'ipotesi: non c'è un dato che
  lo misuri.
- **Campagne e gruppi di annunci:** due campagne. Una di prova, con un solo gruppo e i 5 annunci
  insieme; una per gli annunci che passano la prova.
- **Dove girano le prove e dove vanno i vincitori:** ogni annuncio nuovo entra nella campagna di prova.
  Passa nell'altra solo quando rispetta la regola «Tenere» qui sotto.

## Piano dei test

- **Giro 1:** 5 annunci accesi insieme, 7 giorni, fino a 64,75 l'uno, 323,75 in tutto.
- **Ogni giorno, guardare:** spesa per annuncio, aggiunte al carrello, acquisti, costo per acquisto contro 25,9.
- **Spegnere:** un annuncio che ha speso da 51,8 a 77,7 senza aggiunte al carrello né vendite.
- **Tenere:** un annuncio con acquisti a 25,9 o meno l'uno dopo aver speso almeno 51,8. La soglia è una
  nostra regola pratica (due volte il CPA di pareggio, cioè il punto in cui gli altri si spengono), non
  un numero del programma.
- **Alzare il budget:** del 20% ogni due giorni finché il costo per acquisto resta sotto 25,9. Anche
  questa è una regola pratica: aumenti piccoli per non far ripartire da capo la consegna.
- **Se nessuno tiene:** si cambia prima la pagina di arrivo (prezzo, spedizione e recensioni in alto),
  poi l'offerta, per ultimo il pubblico. In questo ordine perché il pubblico largo è la cosa che i dati
  di Kingshot sostengono di più, mentre sulla nostra pagina non abbiamo ancora nessun dato.
- **Giro 2:** i vincitori del giro 1 cambiano una cosa sola alla volta, partendo dai primi tre secondi.
- **Creatività nuove a settimana:** 3. Kingshot ne lancia 42,2 a settimana tra quelle ancora accese
  (elenco letto quasi tutto: 212 su 216; quelle già spente non si vedono, quindi il ritmo vero è uguale
  o più alto). La quota per i test al livello dell'obiettivo, cioè il 20% di 5.439, è 1.087,8 a
  settimana e regge fino a 16 annunci nuovi a settimana a 64,75 l'uno: ma vale a regime, non
  all'inizio. Una persona sola ne regge 3 (ipotesi nostra). Il primo giro ne usa 5, preparati prima.

## Appendice

### 1. Diagnosi del progetto

**Cosa dicono i numeri.** Prezzo 39,9, costo del prodotto 14, margine per ordine 25,9. Un acquisto può
costare in pubblicità al massimo 25,9; il ROAS di pareggio è 1,54. A 30 ordini al giorno la spesa
massima a pareggio è 777 al giorno (`pacchetto/project.md`).

**Cosa è ipotesi, e come si controlla.**
- Che il costo per acquisto alto dipenda dalle creatività e non dalla pagina: si controlla nel primo
  giro guardando quante persone arrivano alla pagina e quante aggiungono al carrello.
- Che gli acquisti oggi vengano registrati bene: si controlla con l'acquisto di prova.
- Che il margine sia davvero 25,9: si controlla con i valori di IVA, spedizione, commissioni e resi.

### 2. Lettura del concorrente

Il dettaglio è in `analisi.md`. Per questo prodotto contano quattro cose:

- I video che tengono mostrano il gioco in azione, con un testo di una riga (causa 1 e 2, forza alta).
- Kingshot lancia molto e tiene poco: 6 concetti su 14 hanno meno di 7 giorni, 3 superano i 90
  (causa 3, forza media).
- Pubblico largo, nessun testo in italiano (causa 4, forza media).
- Le scene realistiche e il testo in seconda persona sono un filone di 8-15 giorni: un'ipotesi (causa 5).

### 3. Controllo settimanale

- **Quando:** ogni sette giorni dalla prima ricerca; la prossima il 21 novembre 2026.
- **Cosa guardare:** annunci nuovi, spenti e cambiati rispetto alla ricerca precedente; i concetti
  id 1998843314137956 e 2641423062963167; dove portano gli annunci che superano i 30 giorni.
- **Cosa cambierebbe il piano:** se le scene realistiche vengono spente, l'idea 4 esce dal giro 2. Se
  compare un testo in italiano, l'ipotesi del vantaggio della lingua cade. Se la sopravvivenza misurata
  è molto bassa, il ritmo di 3 creatività a settimana va rivisto verso l'alto.
