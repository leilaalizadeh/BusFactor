"""Interface language (English / Italiano).

`t("English text")` returns the Italian text when Italian is selected and the English text otherwise
(or when a string has no translation yet), so a missing entry never breaks a page. Only the interface
is translated: decision cards, questions and feedback stay in the language of the project documents,
the demo data or the model, and answers can be written in any language (grammar never lowers a score).
"""
from __future__ import annotations

LANGS = {"en": "English", "it": "Italiano"}
_lang = "en"


def set_lang(code: str) -> None:
    global _lang
    _lang = code if code in LANGS else "en"


def get_lang() -> str:
    return _lang


def t(text: str) -> str:
    return IT.get(text, text) if _lang == "it" else text


IT = {
    # sidebar
    "Your grade is shared. Your understanding shouldn't be isolated.":
        "Il voto è condiviso. La comprensione non dovrebbe essere isolata.",
    "Project": "Progetto",
    " · synthetic demo": " · demo sintetica",
    "DEMO DATA — synthetic": "DATI DEMO — sintetici",
    "Fictional project, members, answers and consent.": "Progetto, membri, risposte e consensi fittizi.",
    "Who are you? (demo identity switch, not a login)": "Chi sei? (cambio identità demo, non un login)",
    "Who are you?": "Chi sei?",
    "Showing only this member's answers · no login yet": "Mostra solo le risposte di questo membro · nessun login",
    "Signed in with an access code": "Accesso con codice personale",
    "Your access code": "Il tuo codice di accesso",
    "Unlock": "Sblocca",
    "That code does not match.": "Il codice non corrisponde.",
    "Too many attempts. Wait 30 seconds.": "Troppi tentativi. Attendi 30 secondi.",
    "Ask the project creator for your personal code.": "Chiedi il tuo codice personale a chi ha creato il progetto.",
    "Enter your access code in the sidebar to continue.":
        "Inserisci il tuo codice di accesso nella barra laterale per continuare.",
    "Go to": "Vai a",
    "Overview": "Panoramica",
    "1. Project Setup": "1. Impostazione progetto",
    "2. Private Check": "2. Verifica privata",
    "3. Team Coverage": "3. Copertura del team",
    "4. Teach Each Other": "4. Insegnatevi a vicenda",
    "5. Defense Retest": "5. Nuovo test",
    "6. Evidence & Limits": "6. Evidenze e limiti",
    "The demo at a glance": "La demo in sintesi",
    "Key decisions and sources": "Decisioni chiave e fonti",
    "Your own questions": "Le tue domande",
    "Who can explain what": "Chi sa spiegare cosa",
    "Peer-teaching missions": "Missioni di insegnamento tra pari",
    "New question, no hints": "Nuova domanda, senza aiuti",
    "Sources, log, limits": "Fonti, registro, limiti",
    "Reset demo data": "Ripristina dati demo",
    "Restores the synthetic demo to its starting point (coverage 1/5). Everything done in the demo is lost. "
    "Your own projects are not touched.":
        "Riporta la demo sintetica al punto di partenza (copertura 1/5). Tutto ciò che hai fatto nella demo va "
        "perso. I tuoi progetti non vengono toccati.",
    "Reset the demo now": "Ripristina la demo ora",
    # grading mode line
    "Live model grading: formative feedback that can be wrong, never an official grade.":
        "Valutazione con modello reale: feedback formativo che può essere sbagliato, mai un voto ufficiale.",
    "Offline demo keyword rubric on synthetic data: a stand-in, not a validated grader.":
        "Rubrica offline a parole chiave su dati sintetici: un sostituto, non un valutatore validato.",
    "Offline: questions come from templates and answers wait for human review, with no automatic scores.":
        "Offline: le domande vengono da modelli e le risposte aspettano la revisione umana, senza punteggi automatici.",
    # stepper / generic
    "Setup": "Impostazione", "Check": "Verifica", "Coverage": "Copertura", "Teach": "Insegna", "Retest": "Nuovo test",
    "Evidence": "Evidenze",
    "not measurable": "non misurabile", "covered": "coperto",
    "{a} of {b} confirmed decisions have been assessed": "{a} decisioni confermate su {b} sono state valutate",
    " · {n} not confirmed yet, so not counted": " · {n} non ancora confermate, quindi non contate",
    # status pills
    "Covered": "Coperta", "Single point of failure": "Punto singolo di fallimento",
    "No explainer yet": "Nessuno sa spiegarla", "Not assessed": "Non valutata", "Verified": "Verificata",
    "Needs review": "Da rivedere", "No source": "Senza fonte", "Waiting for consent": "In attesa di consenso",
    "Accepted": "Accettata", "Retest not passed yet": "Nuovo test non ancora superato",
    "Transfer verified": "Trasferimento verificato", "Ask the TA": "Chiedi al tutor",
    "Demonstrated": "Dimostrata", "Needs practice": "Da esercitare",
    "Not scored: needs human review": "Non valutata: serve revisione umana", "Not confirmed": "Non confermata",
    "Owner check · no hints": "Verifica del responsabile · senza aiuti",
    # overview
    "Synthetic demo": "Demo sintetica", "Your project": "Il tuo progetto",
    "You split the work.<br><em>Don't split the understanding.</em>":
        "Avete diviso il lavoro.<br><em>Non dividete la comprensione.</em>",
    "BusFactor finds the project decisions only one teammate can explain, sets up peer teaching between teammates, "
    "and checks with a new question that the knowledge really moved.":
        "BusFactor trova le decisioni di progetto che sa spiegare un solo compagno, organizza l'insegnamento tra "
        "compagni e verifica con una nuova domanda che la conoscenza sia davvero passata.",
    "Decision coverage": "Copertura delle decisioni", "Single points of failure": "Punti singoli di fallimento",
    "Teaching missions": "Missioni di insegnamento", "Decisions verified": "Decisioni verificate",
    "quotes checked on their page": "citazioni controllate nella loro pagina",
    "<b>+{n}</b> since start": "<b>+{n}</b> dall'inizio", "started at {a}/{b}": "partita da {a}/{b}",
    "<b>−{n}</b> since start": "<b>−{n}</b> dall'inizio",
    "<b class=\"bad\">need a second explainer</b>": "<b class=\"bad\">serve un secondo che sappia spiegare</b>",
    "{n} proposed · {v} verified": "{n} proposte · {v} verificate",
    "Find the decisions": "Trova le decisioni", "Ask privately": "Chiedi in privato",
    "Spot the risk": "Individua il rischio", "Teach each other": "Insegnatevi a vicenda",
    "Check again": "Verifica di nuovo", "Done": "Fatto", "Up next": "Prossimo", "Waiting": "In attesa",
    "{n} of {m} cards verified against the report": "{n} schede su {m} verificate rispetto al report",
    "{n} decisions have private answers": "{n} decisioni hanno risposte private",
    "{n} decisions depended on one person": "{n} decisioni dipendevano da una persona",
    "{n} mission(s) accepted by both people": "{n} missione/i accettata/e da entrambe le persone",
    "{n} transfer(s) verified · coverage {a} → {b}": "{n} trasferimento/i verificato/i · copertura {a} → {b}",
    "Demo story": "Storia della demo",
    "All numbers come from the synthetic demo data and update live as you use the app.":
        "Tutti i numeri vengono dai dati demo sintetici e si aggiornano mentre usi l'app.",
    "All numbers come from this project's stored, consented evidence.":
        "Tutti i numeri vengono dalle evidenze salvate e consentite di questo progetto.",
    # setup page
    "Project Setup": "Impostazione del progetto",
    "The key decisions of the project. Each one is linked to the exact page it comes from.":
        "Le decisioni chiave del progetto. Ognuna è collegata alla pagina esatta da cui proviene.",
    "Start a new project": "Avvia un nuovo progetto",
    "Create project": "Crea progetto", "Project title": "Titolo del progetto", "Course": "Corso",
    "Team members, one name per line": "Membri del team, un nome per riga",
    "Project report (PDF, Markdown or text)": "Report del progetto (PDF, Markdown o testo)",
    "Team members ({n})": "Membri del team ({n})", "Add member": "Aggiungi membro",
    "Add a member (name)": "Aggiungi un membro (nome)", "Add decisions": "Aggiungi decisioni",
    "Add decision": "Aggiungi decisione", "Decision (what the team chose)": "Decisione (cosa ha scelto il team)",
    "Decisions": "Decisioni", "Confirmed": "Confermate", "Confirm card": "Conferma scheda",
    "Owner (who made this decision)": "Responsabile (chi ha preso la decisione)",
    "not declared": "non dichiarato", "Delete this project": "Elimina questo progetto",
    "Delete project": "Elimina progetto",
    "Type the project title to confirm": "Scrivi il titolo del progetto per confermare",
    "Access codes": "Codici di accesso", "Turn on access codes": "Attiva i codici di accesso",
    "Issue new codes": "Emetti nuovi codici",
    "Access codes are off: anyone using this app can switch to any member and read that member's answers. Turn them "
    "on before real students use it.":
        "I codici di accesso sono disattivati: chiunque usi l'app può passare a qualsiasi membro e leggerne le "
        "risposte. Attivali prima che lo usino studenti reali.",
    "This project uses access codes. Each member unlocks their own answers with a personal code; the review queue "
    "needs the reviewer code.":
        "Questo progetto usa i codici di accesso. Ogni membro sblocca le proprie risposte con un codice personale; "
        "la coda di revisione richiede il codice del revisore.",
    "New codes replace the old ones: everyone must unlock again. Type the project title to confirm.":
        "I nuovi codici sostituiscono i vecchi: tutti dovranno sbloccare di nuovo. Scrivi il titolo del progetto per "
        "confermare.",
    "Save these access codes now. They are shown only once and cannot be recovered.":
        "Salva ora questi codici di accesso. Vengono mostrati una sola volta e non si possono recuperare.",
    "Member": "Membro", "Access code": "Codice di accesso", "Reviewer code": "Codice del revisore",
    "I have saved the codes": "Ho salvato i codici",
    # private check
    "Private Check": "Verifica privata",
    "Questions about decisions you didn't make. Your answers and feedback are shown only to you as the selected "
    "member; there is no login yet, so anyone using this app can switch identity.":
        "Domande su decisioni che non hai preso tu. Risposte e feedback sono mostrati solo a te come membro "
        "selezionato; non c'è ancora un login, quindi chiunque usi l'app può cambiare identità.",
    "Questions about decisions you didn't make. Your answers and feedback are shown only to you after you unlock "
    "your account with your access code.":
        "Domande su decisioni che non hai preso tu. Risposte e feedback sono mostrati solo a te dopo aver sbloccato "
        "il tuo account con il codice di accesso.",
    "Scores are practice feedback, not grades. You can answer in English or Italian; grammar and language never "
    "lower the score.":
        "I punteggi sono feedback di allenamento, non voti. Puoi rispondere in inglese o in italiano; grammatica e "
        "lingua non abbassano mai il punteggio.",
    "My consent": "Il mio consenso", "Save my consent": "Salva il mio consenso",
    "I agree to be assessed (private questions and retests)":
        "Accetto di essere valutato (domande private e nuovi test)",
    "I am willing to mentor a teammate": "Sono disponibile a fare da mentore a un compagno",
    "I am willing to learn from a teammate": "Sono disponibile a imparare da un compagno",
    "Allow a human reviewer to read my answers that the model could not score (without my name)":
        "Permetto a un revisore umano di leggere le mie risposte che il modello non ha potuto valutare (senza il "
        "mio nome)",
    "Get my questions": "Ottieni le mie domande", "Start owner check": "Avvia la verifica del responsabile",
    "Verify a decision you own": "Verifica una decisione di cui sei responsabile",
    "To answer ({n})": "Da rispondere ({n})", "Answered ({n})": "Risposte ({n})",
    "Nothing open. Get new questions above.": "Niente da fare. Ottieni nuove domande qui sopra.",
    "Your answer": "La tua risposta", "Submit": "Invia",
    "You have not agreed to be assessed, so BusFactor will not ask or score you.":
        "Non hai accettato di essere valutato, quindi BusFactor non ti farà domande né ti assegnerà punteggi.",
    # coverage
    "Team Coverage": "Copertura del team",
    "How many decisions at least two of you can explain. Only counts are shown, never names or scores.":
        "Quante decisioni almeno due di voi sanno spiegare. Si mostrano solo conteggi, mai nomi o punteggi.",
    "Before": "Prima", "Now": "Ora", "when the project started": "all'avvio del progetto",
    "no change yet": "nessun cambiamento", "decisions only one person can explain": "decisioni che sa spiegare "
    "una sola persona",
    "{n} can explain it": "{n} sanno spiegarla", "Next:": "Prossimo passo:",
    "The ring fills as more decisions get a second person who can explain them.":
        "L'anello si riempie man mano che più decisioni hanno una seconda persona che sa spiegarle.",
    "Export": "Esporta",
    "Download team report (Markdown)": "Scarica il report del team (Markdown)",
    "Download decisions (CSV)": "Scarica le decisioni (CSV)",
    "The exports contain counts only: no names, answers or scores.":
        "Le esportazioni contengono solo conteggi: niente nomi, risposte o punteggi.",
    # missions
    "Teach Each Other": "Insegnatevi a vicenda",
    "For each decision only one person can explain, a teammate who understands it teaches one who doesn't.":
        "Per ogni decisione che sa spiegare una sola persona, un compagno che la capisce la insegna a uno che non la "
        "capisce.",
    "Find knowledge silos and propose missions": "Trova i silos di conoscenza e proponi missioni",
    "No missions yet. Press the button above.": "Ancora nessuna missione. Premi il pulsante qui sopra.",
    "Mentor": "Mentore", "Learner": "Studente",
    "You accepted. Waiting for the other person.": "Hai accettato. In attesa dell'altra persona.",
    "I agree to take part as {role}": "Accetto di partecipare come {role}",
    "Reminder: the teaching session for {d} was agreed {n} days ago. Do it, then take the retest (page 5).":
        "Promemoria: la sessione di insegnamento per {d} è stata concordata {n} giorni fa. Fatela, poi fai il nuovo "
        "test (pagina 5).",
    "Follow-up check due: you passed the retest for {d} {n} days ago. One new question shows whether it stuck.":
        "Verifica di richiamo in scadenza: hai superato il nuovo test per {d} {n} giorni fa. Una nuova domanda "
        "mostra se è rimasto.",
    # retest
    "Defense Retest": "Nuovo test",
    "After the teaching session, answer a new question on your own. No hints are available here.":
        "Dopo la sessione di insegnamento, rispondi da solo a una nuova domanda. Qui non ci sono aiuti.",
    "You have no teaching mission as a learner.": "Non hai nessuna missione come studente.",
    "Start a new independent question": "Avvia una nuova domanda indipendente",
    "Start the follow-up check": "Avvia la verifica di richiamo",
    # evidence
    "Evidence & Limits": "Evidenze e limiti",
    "Where every decision comes from, what the agent did, and what it can't do.":
        "Da dove viene ogni decisione, cosa ha fatto l'agente e cosa non può fare.",
    "Sources": "Fonti", "Action log": "Registro azioni", "Abstentions & blocked": "Astensioni e blocchi",
    "Limits": "Limiti", "Review queue": "Coda di revisione", "None yet.": "Nessuno per ora.",
    "Answers the model could not score wait here for a human. A reviewer sees only answers from members who agreed "
    "to human review, and never their names.":
        "Le risposte che il modello non ha potuto valutare aspettano qui una persona. Il revisore vede solo le "
        "risposte dei membri che hanno accettato la revisione umana, mai i loro nomi.",
    "Enter the reviewer code to open the queue.": "Inserisci il codice del revisore per aprire la coda.",
    "Nothing is waiting for review.": "Niente in attesa di revisione.",
    "Score": "Punteggio", "Feedback for the member (optional)": "Feedback per il membro (facoltativo)",
    "Save review": "Salva revisione", "Answer": "Risposta", "A good answer covers:": "Una buona risposta copre:",
    "Review saved.": "Revisione salvata.",
}
