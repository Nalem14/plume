.pragma library
const words = {
    fr: {agenda: "Agenda", tasks: "Tâches", day: "Journée", week: "Semaine", month: "Mois", today: "Aujourd’hui",
        all: "Toutes", view: "Vue", list: "Liste", allLists: "Toutes les listes", open: "Ouvrir", add: "Ajouter une tâche",
        previous: "Précédent", next: "Suivant", allDay: "Toute la journée", join: "Rejoindre", done: "Terminer la tâche",
        emptyAgenda: "Aucun événement sur cette période", emptyTasks: "Aucune tâche dans cette vue",
        loading: "Chargement…", signed_out: "Connectez votre compte avec Orneos Connect.",
        setup: "Ouvrez Tâches pour charger vos listes.", offline: "Hors ligne · dernière copie disponible",
        error: "Données indisponibles. Réessayez.", retry: "Réessayer", actionError: "Cette action n’a pas pu être effectuée. Réessayez.",
        missingList: "Liste indisponible · choisissez une autre liste", settings: "Affichage", overdue: "En retard"},
    en: {agenda: "Calendar", tasks: "Tasks", day: "Day", week: "Week", month: "Month", today: "Today",
        all: "All", view: "View", list: "List", allLists: "All lists", open: "Open", add: "Add a task",
        previous: "Previous", next: "Next", allDay: "All day", join: "Join", done: "Complete task",
        emptyAgenda: "No events in this period", emptyTasks: "No tasks in this view",
        loading: "Loading…", signed_out: "Connect your account with Orneos Connect.",
        setup: "Open Tasks to load your lists.", offline: "Offline · last available copy",
        error: "Data unavailable. Try again.", retry: "Retry", actionError: "This action could not be completed. Try again.",
        missingList: "List unavailable · choose another list", settings: "Display", overdue: "Overdue"},
    de: {agenda: "Kalender", tasks: "Aufgaben", day: "Tag", week: "Woche", month: "Monat", today: "Heute",
        all: "Alle", view: "Ansicht", list: "Liste", allLists: "Alle Listen", open: "Öffnen", add: "Aufgabe hinzufügen",
        previous: "Zurück", next: "Weiter", allDay: "Ganztägig", join: "Teilnehmen", done: "Aufgabe erledigen",
        emptyAgenda: "Keine Termine in diesem Zeitraum", emptyTasks: "Keine Aufgaben in dieser Ansicht",
        loading: "Laden…", signed_out: "Verbinden Sie Ihr Konto mit Orneos Connect.",
        setup: "Öffnen Sie Aufgaben, um Ihre Listen zu laden.", offline: "Offline · letzte verfügbare Kopie",
        error: "Daten nicht verfügbar. Versuchen Sie es erneut.", retry: "Erneut versuchen", actionError: "Die Aktion konnte nicht ausgeführt werden. Versuchen Sie es erneut.",
        missingList: "Liste nicht verfügbar · wählen Sie eine andere Liste", settings: "Anzeige", overdue: "Überfällig"}
};
Object.assign(words.fr, {
    "mail": "Courrier",
    "recentMail": "Récents",
    "notes": "Notes",
    "recent": "Récentes",
    "unread": "Non lus",
    "pinned": "Épinglées",
    "allBoxes": "Toutes les boîtes",
    "allFolders": "Tous les dossiers",
    "mailbox": "Boîte mail",
    "folder": "Dossier",
    "search": "Rechercher",
    "itemCount": "Nombre à afficher",
    "compose": "Écrire un message",
    "quickNote": "Note rapide",
    "setupMail": "Ouvrez Plume pour charger vos messages.",
    "setupNotes": "Ouvrez Notes pour charger vos notes.",
    "emptyMail": "Aucun message dans cette vue",
    "emptyNotes": "Aucune note dans cette vue",
    "missingGroup": "Boîte ou dossier indisponible : choisissez-en un autre.",
    "noSubject": "Sans objet",
    "untitled": "Sans titre",
    "moreInApp": "Ouvrez l’application pour voir la suite."
});
Object.assign(words.en, {
    "mail": "Mail",
    "recentMail": "Recent",
    "notes": "Notes",
    "recent": "Recent",
    "unread": "Unread",
    "pinned": "Pinned",
    "allBoxes": "All mailboxes",
    "allFolders": "All folders",
    "mailbox": "Mailbox",
    "folder": "Folder",
    "search": "Search",
    "itemCount": "Items to display",
    "compose": "Write a message",
    "quickNote": "Quick note",
    "setupMail": "Open Plume to load your messages.",
    "setupNotes": "Open Notes to load your notes.",
    "emptyMail": "No messages in this view",
    "emptyNotes": "No notes in this view",
    "missingGroup": "Mailbox or folder unavailable: choose another.",
    "noSubject": "No subject",
    "untitled": "Untitled",
    "moreInApp": "Open the app to see more."
});
Object.assign(words.de, {
    "mail": "Mail",
    "recentMail": "Zuletzt",
    "notes": "Notizen",
    "recent": "Zuletzt",
    "unread": "Ungelesen",
    "pinned": "Angeheftet",
    "allBoxes": "Alle Postfächer",
    "allFolders": "Alle Ordner",
    "mailbox": "Postfach",
    "folder": "Ordner",
    "search": "Suchen",
    "itemCount": "Anzahl der Einträge",
    "compose": "Nachricht schreiben",
    "quickNote": "Schnellnotiz",
    "setupMail": "Öffnen Sie Plume, um Nachrichten zu laden.",
    "setupNotes": "Öffnen Sie Notizen, um Ihre Notizen zu laden.",
    "emptyMail": "Keine Nachrichten in dieser Ansicht",
    "emptyNotes": "Keine Notizen in dieser Ansicht",
    "missingGroup": "Postfach oder Ordner nicht verfügbar: wählen Sie einen anderen.",
    "noSubject": "Kein Betreff",
    "untitled": "Ohne Titel",
    "moreInApp": "Öffnen Sie die App, um mehr zu sehen."
});
Object.assign(words.fr, {"assistant": "Ornis", "favorites": "Favoris Orneos", "team": "Activité de l’équipe", "modifiedFiles": "Documents récemment modifiés", "askOrnis": "Demander à Ornis…", "newConversation": "Nouvelle conversation", "emptyFeed": "Aucun élément à afficher", "chooseTeamFolder": "Choisissez le dossier de votre équipe dans les réglages du widget.", "teamFolder": "Dossier de l’équipe", "folderExample": "Équipe / Projets", "folderHelp": "Chemin exact du dossier partagé dans vos fichiers Orneos, sans adresse web."});
Object.assign(words.en, {"assistant": "Ornis", "favorites": "Orneos Bookmarks", "team": "Team activity", "modifiedFiles": "Recently modified documents", "askOrnis": "Ask Ornis…", "newConversation": "New conversation", "emptyFeed": "No items to display", "chooseTeamFolder": "Choose your team folder in the widget settings.", "teamFolder": "Team folder", "folderExample": "Team/Projects", "folderHelp": "Exact shared folder path in your Orneos files, without a web address."});
Object.assign(words.de, {"assistant": "Ornis", "favorites": "Orneos-Lesezeichen", "team": "Teamaktivität", "modifiedFiles": "Zuletzt geänderte Dokumente", "askOrnis": "Ornis fragen…", "newConversation": "Neues Gespräch", "emptyFeed": "Keine Einträge", "chooseTeamFolder": "Wählen Sie den Teamordner in den Widget-Einstellungen.", "teamFolder": "Teamordner", "folderExample": "Team/Projekte", "folderHelp": "Genauer Pfad des geteilten Ordners in Ihren Orneos-Dateien, ohne Webadresse."});
Object.assign(words.fr, {"inProgress": "En cours", "untilTime": "jusqu’à %1", "beforeTime": "avant %1", "minutes": "%1 min", "nextUp": "prochain", "free": "Libre", "freeRest": "jusqu’à demain", "inMinutes": "dans %1 min", "tomorrow": "Demain", "nothingToday": "Rien d’autre aujourd’hui", "todoToday": "%1 à faire aujourd’hui", "todoAll": "%1 à faire", "lateCount": "dont %1 en retard", "allDone": "Tout est fait", "moreTomorrow": "+ %1 demain", "late": "en retard", "yesterday": "Hier", "doneRatio": "%1 sur %2 faites"});
Object.assign(words.en, {"inProgress": "Now", "untilTime": "until %1", "beforeTime": "before %1", "minutes": "%1 min", "nextUp": "next", "free": "Free", "freeRest": "until tomorrow", "inMinutes": "in %1 min", "tomorrow": "Tomorrow", "nothingToday": "Nothing else today", "todoToday": "%1 to do today", "todoAll": "%1 to do", "lateCount": "%1 overdue", "allDone": "All done", "moreTomorrow": "+ %1 tomorrow", "late": "overdue", "yesterday": "Yesterday", "doneRatio": "%1 of %2 done"});
Object.assign(words.de, {"inProgress": "Läuft", "untilTime": "bis %1", "beforeTime": "vor %1", "minutes": "%1 Min.", "nextUp": "als Nächstes", "free": "Frei", "freeRest": "bis morgen", "inMinutes": "in %1 Min.", "tomorrow": "Morgen", "nothingToday": "Heute nichts mehr", "todoToday": "%1 heute zu erledigen", "todoAll": "%1 zu erledigen", "lateCount": "davon %1 überfällig", "allDone": "Alles erledigt", "moreTomorrow": "+ %1 morgen", "late": "überfällig", "yesterday": "Gestern", "doneRatio": "%1 von %2 erledigt"});
Object.assign(words.fr, {"dayStart": "Début de la journée", "dayEnd": "Fin de la journée", "hourSuffix": "h", "join": "Rejoindre"});
Object.assign(words.en, {"dayStart": "Day starts at", "dayEnd": "Day ends at", "hourSuffix": ":00", "join": "Join"});
Object.assign(words.de, {"dayStart": "Tagesbeginn", "dayEnd": "Tagesende", "hourSuffix": " Uhr", "join": "Teilnehmen"});
Object.assign(words.fr, {"unreadCount": "non lus", "newMessage": "Nouveau message", "allRead": "Tout est lu", "recentNote": "Récente", "pinnedNote": "Épinglée", "noNotes": "Aucune note", "suggestPrepare": "Préparer « %1 » à %2 ?", "askPlaceholder": "Demander à Ornis…", "recentConversations": "Conversations récentes", "send": "Envoyer"});
Object.assign(words.en, {"unreadCount": "unread", "newMessage": "New message", "allRead": "All read", "recentNote": "Recent", "pinnedNote": "Pinned", "noNotes": "No notes", "suggestPrepare": "Prepare “%1” at %2?", "askPlaceholder": "Ask Ornis…", "recentConversations": "Recent conversations", "send": "Send"});
Object.assign(words.de, {"unreadCount": "ungelesen", "newMessage": "Neue Nachricht", "allRead": "Alles gelesen", "recentNote": "Zuletzt", "pinnedNote": "Angeheftet", "noNotes": "Keine Notizen", "suggestPrepare": "„%1“ um %2 vorbereiten?", "askPlaceholder": "Ornis fragen…", "recentConversations": "Letzte Gespräche", "send": "Senden"});
Object.assign(words.fr, {"unreadOne": "non lu"});
Object.assign(words.en, {"unreadOne": "unread"});
Object.assign(words.de, {"unreadOne": "ungelesen"});
Object.assign(words.fr, {"news": "Actualités", "allSources": "Toutes les sources", "starred": "Épinglés", "unreadOnly": "Seulement les non lus", "source": "Source", "sources": "Sources", "noSources": "Choisissez vos premières sources", "noSourcesHint": "Elles s’ajoutent à vos News du cloud, sur tous vos appareils.", "follow": "Suivre", "followed": "Suivie", "moreSources": "Plus de sources…", "missingSource": "Source indisponible · choisissez-en une autre dans les réglages.", "emptyNews": "Rien de nouveau pour l’instant", "explore": "Explorer", "exploreHint": "Les sources proposées par Orneos. Une source suivie s’ajoute à vos News du cloud.", "feedAddress": "Adresse d’un flux (RSS ou Atom)", "add": "Ajouter", "openNews": "Ouvrir News", "folderPrefix": "Dossier · %1", "account": "Mon Orneos", "storage": "Stockage", "storageOf": "%1 sur %2", "storageFree": "%1 libres", "ornisUsage": "Sur 24 h glissantes", "available": "%1 % disponible", "moreSpace": "Plus d’espace", "weather": "Météo", "place": "Lieu", "placeHint": "Une ville ou une adresse. Le même lieu que la météo du tableau de bord de votre cloud.", "usePlace": "Utiliser ce lieu", "placeSaved": "Lieu enregistré.", "noPlace": "Choisissez un lieu dans les réglages du widget.", "wind": "Vent %1 km/h", "rainMm": "%1 mm", "now": "Maintenant"});
Object.assign(words.en, {"news": "News", "allSources": "All sources", "starred": "Starred", "unreadOnly": "Unread only", "source": "Source", "sources": "Sources", "noSources": "Choose your first sources", "noSourcesHint": "They are added to your cloud News, on all your devices.", "follow": "Follow", "followed": "Following", "moreSources": "More sources…", "missingSource": "Source unavailable · choose another in the settings.", "emptyNews": "Nothing new for now", "explore": "Explore", "exploreHint": "Sources suggested by Orneos. A followed source is added to your cloud News.", "feedAddress": "Feed address (RSS or Atom)", "add": "Add", "openNews": "Open News", "folderPrefix": "Folder · %1", "account": "My Orneos", "storage": "Storage", "storageOf": "%1 of %2", "storageFree": "%1 free", "ornisUsage": "Over a rolling 24 h", "available": "%1% available", "moreSpace": "More space", "weather": "Weather", "place": "Place", "placeHint": "A city or an address. The same place as the weather on your cloud's dashboard.", "usePlace": "Use this place", "placeSaved": "Place saved.", "noPlace": "Choose a place in the widget settings.", "wind": "Wind %1 km/h", "rainMm": "%1 mm", "now": "Now"});
Object.assign(words.de, {"news": "Nachrichten", "allSources": "Alle Quellen", "starred": "Markiert", "unreadOnly": "Nur ungelesene", "source": "Quelle", "sources": "Quellen", "noSources": "Wählen Sie Ihre ersten Quellen", "noSourcesHint": "Sie werden Ihren News in der Cloud hinzugefügt, auf all Ihren Geräten.", "follow": "Folgen", "followed": "Abonniert", "moreSources": "Weitere Quellen…", "missingSource": "Quelle nicht verfügbar · wählen Sie in den Einstellungen eine andere.", "emptyNews": "Im Moment nichts Neues", "explore": "Entdecken", "exploreHint": "Von Orneos vorgeschlagene Quellen. Eine abonnierte Quelle wird Ihren News in der Cloud hinzugefügt.", "feedAddress": "Adresse eines Feeds (RSS oder Atom)", "add": "Hinzufügen", "openNews": "News öffnen", "folderPrefix": "Ordner · %1", "account": "Mein Orneos", "storage": "Speicher", "storageOf": "%1 von %2", "storageFree": "%1 frei", "ornisUsage": "In den letzten 24 Std.", "available": "%1 % verfügbar", "moreSpace": "Mehr Speicher", "weather": "Wetter", "place": "Ort", "placeHint": "Eine Stadt oder Adresse. Derselbe Ort wie das Wetter im Dashboard Ihrer Cloud.", "usePlace": "Diesen Ort verwenden", "placeSaved": "Ort gespeichert.", "noPlace": "Wählen Sie einen Ort in den Widget-Einstellungen.", "wind": "Wind %1 km/h", "rainMm": "%1 mm", "now": "Jetzt"});
Object.assign(words.fr, {"photos": "Photos", "recentPhotos": "Récentes", "favoritePhotos": "Favorites", "onThisDay": "Ce jour-là", "album": "Album", "oneYearAgo": "Il y a un an", "yearsAgo": "Il y a %1 ans", "emptyPhotos": "Aucune photo ici pour l’instant.", "missingAlbum": "Album indisponible · choisissez-en un autre dans les réglages.", "noMemoryToday": "Pas de souvenir ce jour-là : vos dernières photos.", "changeEvery": "Changer de photo", "everySeconds": "Toutes les %1 s", "everyMinutes": "Toutes les %1 min", "show": "Afficher"});
Object.assign(words.en, {"photos": "Photos", "recentPhotos": "Recent", "favoritePhotos": "Favourites", "onThisDay": "On this day", "album": "Album", "oneYearAgo": "One year ago", "yearsAgo": "%1 years ago", "emptyPhotos": "No photos here yet.", "missingAlbum": "Album unavailable · choose another in the settings.", "noMemoryToday": "No memories on this day: your latest photos.", "changeEvery": "Change photo", "everySeconds": "Every %1 s", "everyMinutes": "Every %1 min", "show": "Show"});
Object.assign(words.de, {"photos": "Fotos", "recentPhotos": "Neueste", "favoritePhotos": "Favoriten", "onThisDay": "An diesem Tag", "album": "Album", "oneYearAgo": "Vor einem Jahr", "yearsAgo": "Vor %1 Jahren", "emptyPhotos": "Hier gibt es noch keine Fotos.", "missingAlbum": "Album nicht verfügbar · wählen Sie in den Einstellungen ein anderes.", "noMemoryToday": "Keine Erinnerungen an diesem Tag: Ihre neuesten Fotos.", "changeEvery": "Foto wechseln", "everySeconds": "Alle %1 s", "everyMinutes": "Alle %1 Min.", "show": "Anzeigen"});
Object.assign(words.fr, {"meet": "Meet", "waitingCount": "%1 en attente", "noneWaiting": "Rien en attente", "callNow": "Appel en cours", "joinCall": "Rejoindre", "newMeeting": "Nouvelle réunion", "setupMeet": "Ouvrez Meet pour charger vos conversations.", "emptyMeet": "Aucune conversation", "meetingAt": "Réunion à %1", "files": "Fichiers récents", "dropHere": "Déposez pour copier dans Orneos", "copied": "Copié dans votre dossier Orneos", "openDrive": "Ouvrir Drive", "emptyFiles": "Aucun document récent", "deck": "Deck", "overdueCards": "En retard", "dueToday": "Aujourd’hui", "dueTomorrow": "Demain", "dueWeek": "Cette semaine", "dueLater": "Plus tard", "emptyDeck": "Aucune carte à échéance", "noDeck": "Deck n’est pas disponible sur votre cloud.", "openDeck": "Ouvrir Deck", "cardsCount": "%1 cartes à échéance", "cardsOne": "1 carte à échéance", "searchTitle": "Recherche", "searchPlaceholder": "Rechercher sur le web…", "aiMode": "Mode IA", "searchHint": "Résultats sans pistage, sur Orneos Recherche.", "brief": "Ornis du jour", "hello": "Bonjour", "helloEvening": "Bonsoir", "eventsLeft": "%1 événements encore aujourd’hui", "eventsLeftOne": "1 événement encore aujourd’hui", "noEvents": "Plus rien à l’agenda aujourd’hui", "tasksLine": "%1 tâches pour aujourd’hui", "tasksOne": "1 tâche pour aujourd’hui", "mailLine": "%1 messages non lus", "mailOne": "1 message non lu", "waitingLine": "%1 conversations en attente", "waitingOne": "1 conversation en attente", "prepareDay": "Préparer ma journée", "preparePrompt": "Prépare ma journée : mes rendez-vous d’aujourd’hui, mes tâches à faire et les messages importants à traiter.", "nextAt": "Ensuite : %1 à %2", "allClear": "Rien d’urgent pour l’instant.", "lateShort": "dont %1 en retard"});
Object.assign(words.en, {"meet": "Meet", "waitingCount": "%1 waiting", "noneWaiting": "Nothing waiting", "callNow": "Call in progress", "joinCall": "Join", "newMeeting": "New meeting", "setupMeet": "Open Meet to load your conversations.", "emptyMeet": "No conversations", "meetingAt": "Meeting at %1", "files": "Recent files", "dropHere": "Drop to copy into Orneos", "copied": "Copied to your Orneos folder", "openDrive": "Open Drive", "emptyFiles": "No recent documents", "deck": "Deck", "overdueCards": "Overdue", "dueToday": "Today", "dueTomorrow": "Tomorrow", "dueWeek": "This week", "dueLater": "Later", "emptyDeck": "No cards due", "noDeck": "Deck is not available on your cloud.", "openDeck": "Open Deck", "cardsCount": "%1 cards due", "cardsOne": "1 card due", "searchTitle": "Search", "searchPlaceholder": "Search the web…", "aiMode": "AI mode", "searchHint": "Results without tracking, on Orneos Search.", "brief": "Ornis today", "hello": "Good morning", "helloEvening": "Good evening", "eventsLeft": "%1 more events today", "eventsLeftOne": "1 more event today", "noEvents": "Nothing left in your calendar today", "tasksLine": "%1 tasks for today", "tasksOne": "1 task for today", "mailLine": "%1 unread messages", "mailOne": "1 unread message", "waitingLine": "%1 conversations waiting", "waitingOne": "1 conversation waiting", "prepareDay": "Prepare my day", "preparePrompt": "Prepare my day: today's appointments, my tasks to do and the important messages to handle.", "nextAt": "Next: %1 at %2", "allClear": "Nothing urgent for now.", "lateShort": "%1 overdue"});
Object.assign(words.de, {"meet": "Meet", "waitingCount": "%1 warten", "noneWaiting": "Nichts wartet", "callNow": "Anruf läuft", "joinCall": "Teilnehmen", "newMeeting": "Neue Besprechung", "setupMeet": "Öffnen Sie Meet, um Ihre Unterhaltungen zu laden.", "emptyMeet": "Keine Unterhaltungen", "meetingAt": "Besprechung um %1", "files": "Zuletzt geänderte Dateien", "dropHere": "Ablegen, um in Orneos zu kopieren", "copied": "In Ihren Orneos-Ordner kopiert", "openDrive": "Drive öffnen", "emptyFiles": "Keine aktuellen Dokumente", "deck": "Deck", "overdueCards": "Überfällig", "dueToday": "Heute", "dueTomorrow": "Morgen", "dueWeek": "Diese Woche", "dueLater": "Später", "emptyDeck": "Keine fälligen Karten", "noDeck": "Deck ist in Ihrer Cloud nicht verfügbar.", "openDeck": "Deck öffnen", "cardsCount": "%1 fällige Karten", "cardsOne": "1 fällige Karte", "searchTitle": "Suche", "searchPlaceholder": "Im Web suchen…", "aiMode": "KI-Modus", "searchHint": "Ergebnisse ohne Tracking, mit Orneos-Suche.", "brief": "Ornis heute", "hello": "Guten Morgen", "helloEvening": "Guten Abend", "eventsLeft": "Heute noch %1 Termine", "eventsLeftOne": "Heute noch 1 Termin", "noEvents": "Heute keine Termine mehr", "tasksLine": "%1 Aufgaben für heute", "tasksOne": "1 Aufgabe für heute", "mailLine": "%1 ungelesene Nachrichten", "mailOne": "1 ungelesene Nachricht", "waitingLine": "%1 Unterhaltungen warten", "waitingOne": "1 Unterhaltung wartet", "prepareDay": "Meinen Tag vorbereiten", "preparePrompt": "Bereite meinen Tag vor: meine heutigen Termine, meine Aufgaben und die wichtigen Nachrichten.", "nextAt": "Danach: %1 um %2", "allClear": "Im Moment nichts Dringendes.", "lateShort": "davon %1 überfällig"});
Object.assign(words.fr, {"writeNote": "Écrire une note…", "saveNote": "Enregistrer la note", "noteAdded": "Ajoutée à vos Notes", "noteFailed": "Pas enregistrée : réessayez (réseau ?)"});
Object.assign(words.en, {"writeNote": "Write a note…", "saveNote": "Save the note", "noteAdded": "Added to your Notes", "noteFailed": "Not saved: try again (network?)"});
Object.assign(words.de, {"writeNote": "Notiz schreiben…", "saveNote": "Notiz speichern", "noteAdded": "Zu Ihren Notizen hinzugefügt", "noteFailed": "Nicht gespeichert: erneut versuchen (Netzwerk?)"});
function tr(key) { const lang = Qt.locale().name.slice(0, 2); return (words[lang] || words.en)[key] || key; }
// tr() with %1, %2… replaced by the arguments.
function fmt(key) { let text = tr(key); for (let i = 1; i < arguments.length; i++) text = text.replace("%" + i, arguments[i]); return text; }
// A short time for a list: 13:28 today, "Yesterday", else 27 Oct.
function stamp(ts) {
    if (!ts) return "";
    const d = new Date(ts * 1000), now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
    if (d.getTime() >= today) return Qt.locale().toString(d, Qt.locale().timeFormat(1)); // 1 = Locale.ShortFormat (no Locale in a .pragma library)
    if (d.getTime() >= today - 86400000) return tr("yesterday");
    return Qt.locale().toString(d, "d MMM");
}
