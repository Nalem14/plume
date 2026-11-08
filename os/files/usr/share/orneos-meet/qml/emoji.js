// The emojis of Meet: by family, each with its short codes (the first is the one shown, « :fete: »: English
// ones as in Slack and Talk, then French and German words) for « : » in the composer and the picker's search.
// emoticons(): the classic ones (« :D », « <3 ») become their emoji when the message leaves.
.pragma library

var FAMILIES = [
    { key: "smileys", icon: "😀", items: [
        ["😀", "grinning sourire content grinsen"], ["😃", "smiley joyeux"], ["😄", "smile rire heureux lachen"],
        ["😁", "grin dents"], ["😆", "laughing mdr"], ["😅", "sweat_smile ouf gene"], ["🤣", "rofl ptdr lol"],
        ["😂", "joy pleure_de_rire lol mdr"], ["🙂", "slightly_smiling sourire"], ["🙃", "upside_down envers ironie"],
        ["😉", "wink clin_doeil zwinkern"], ["😊", "blush rougir gene"], ["😇", "innocent ange"],
        ["🥰", "smiling_hearts amoureux"], ["😍", "heart_eyes amour coeur"], ["🤩", "star_struck etoiles wow"],
        ["😘", "kissing_heart bisou kuss"], ["😚", "kissing bisous"], ["😋", "yum miam lecker"],
        ["😛", "stuck_out_tongue langue"], ["😜", "winking_tongue blague"], ["🤪", "zany fou"],
        ["🤑", "money_mouth argent"], ["🤗", "hugging calin"], ["🤭", "hand_over_mouth oups"],
        ["🤫", "shushing chut"], ["🤔", "thinking reflechir hmm denken"], ["🤐", "zipper_mouth silence"],
        ["🤨", "raised_eyebrow sourcil doute"], ["😐", "neutral_face neutre"], ["😑", "expressionless blase"],
        ["😶", "no_mouth sans_voix"], ["😏", "smirk narquois"], ["😒", "unamused bof"], ["🙄", "roll_eyes yeux_au_ciel"],
        ["😬", "grimacing grimace aie"], ["😮‍💨", "exhale soupir"], ["🤥", "lying menteur"],
        ["😌", "relieved soulage"], ["😔", "pensive pensif"], ["😪", "sleepy fatigue"], ["🤤", "drooling bave"],
        ["😴", "sleeping dort sommeil schlafen"], ["😷", "mask masque malade"], ["🤒", "thermometer fievre"],
        ["🤕", "bandage blesse"], ["🤢", "nauseated nausee"], ["🤮", "vomiting vomir"], ["🤧", "sneezing rhume"],
        ["🥵", "hot chaud"], ["🥶", "cold froid"], ["🥴", "woozy etourdi"], ["😵", "dizzy vertige"],
        ["🤯", "exploding_head explose choque"], ["🤠", "cowboy"], ["🥳", "partying anniversaire party fete"],
        ["😎", "sunglasses cool lunettes"], ["🤓", "nerd intello"], ["🧐", "monocle examiner"],
        ["😕", "confused perplexe"], ["😟", "worried inquiet"], ["🙁", "slightly_frowning decu"],
        ["😮", "open_mouth surpris"], ["😯", "hushed etonne"], ["😲", "astonished stupefait"],
        ["😳", "flushed rouge gene"], ["🥺", "pleading supplier svp"], ["😦", "frowning"], ["😧", "anguished angoisse"],
        ["😨", "fearful peur"], ["😰", "cold_sweat stress"], ["😥", "disappointed_relieved"], ["😢", "cry triste larme"],
        ["😭", "sob pleurer sanglot"], ["😱", "scream cri horreur"], ["😖", "confounded"], ["😣", "persevere"],
        ["😞", "disappointed decu"], ["😓", "sweat sueur"], ["😩", "weary epuise"], ["😫", "tired_face creve"],
        ["🥱", "yawning baille"], ["😤", "triumph frustre"], ["😡", "rage furieux"], ["😠", "angry colere wut"],
        ["🤬", "cursing jurons"], ["😈", "smiling_imp diable"], ["💀", "skull mort crane"], ["💩", "poop caca"],
        ["🤡", "clown"], ["👻", "ghost fantome"], ["👽", "alien extraterrestre"], ["🤖", "robot"],
        ["😺", "smiley_cat chat"], ["🙈", "see_no_evil singe cache"], ["🙉", "hear_no_evil"], ["🙊", "speak_no_evil"]
    ] },
    { key: "people", icon: "👋", items: [
        ["👍", "+1 thumbsup pouce ok oui daumen"], ["👎", "-1 thumbsdown pouce_bas non"], ["👋", "wave salut coucou bonjour hallo"],
        ["🤚", "raised_back_of_hand"], ["✋", "raised_hand main stop"], ["🖐️", "hand_splayed main"], ["🖖", "vulcan"],
        ["👌", "ok_hand parfait"], ["🤌", "pinched_fingers italien"], ["🤏", "pinching_hand un_peu"],
        ["✌️", "v victoire paix"], ["🤞", "crossed_fingers croise_les_doigts chance"], ["🤟", "love_you"],
        ["🤘", "metal rock"], ["🤙", "call_me appelle"], ["👈", "point_left gauche"], ["👉", "point_right droite"],
        ["👆", "point_up haut"], ["👇", "point_down bas"], ["☝️", "index attention"], ["✊", "fist poing"],
        ["👊", "punch check"], ["🤛", "left_fist"], ["🤜", "right_fist"], ["👏", "clap bravo applaudir"],
        ["🙌", "raised_hands hourra"], ["👐", "open_hands"], ["🤲", "palms_up"], ["🤝", "handshake accord poignee"],
        ["🙏", "pray merci svp danke"], ["✍️", "writing ecrire"], ["💅", "nail_care"], ["💪", "muscle force courage"],
        ["🧠", "brain cerveau"], ["👀", "eyes yeux regarde vu"], ["👁️", "eye oeil"], ["👂", "ear oreille ecoute"],
        ["👄", "lips bouche"], ["🫡", "salute salut_militaire"], ["🤷", "shrug bof sais_pas"], ["🙋", "raising_hand moi"],
        ["🙆", "ok_gesture"], ["🙅", "no_gesture non"], ["💁", "tipping_hand voila"], ["🤦", "facepalm"],
        ["🧑‍💻", "technologist developpeur ordi"], ["👩‍💼", "office_worker bureau"], ["🧑‍🏫", "teacher prof"],
        ["🏃", "running courir"], ["🚶", "walking marcher"], ["💃", "dancer danse"], ["🕺", "man_dancing"],
        ["👨‍👩‍👧", "family famille"], ["👶", "baby bebe"], ["🧑", "person personne"]
    ] },
    { key: "nature", icon: "🌿", items: [
        ["🐶", "dog chien hund"], ["🐱", "cat chat katze"], ["🐭", "mouse souris"], ["🐰", "rabbit lapin"],
        ["🦊", "fox renard"], ["🐻", "bear ours"], ["🐼", "panda"], ["🐨", "koala"], ["🐯", "tiger tigre"],
        ["🦁", "lion"], ["🐮", "cow vache"], ["🐷", "pig cochon"], ["🐸", "frog grenouille"], ["🐵", "monkey singe"],
        ["🐔", "chicken poule"], ["🐧", "penguin pingouin"], ["🐦", "bird oiseau"], ["🦅", "eagle aigle"],
        ["🦉", "owl hibou"], ["🐝", "bee abeille"], ["🦋", "butterfly papillon"], ["🐌", "snail escargot lent"],
        ["🐢", "turtle tortue"], ["🐍", "snake serpent"], ["🐙", "octopus pieuvre"], ["🐟", "fish poisson"],
        ["🐬", "dolphin dauphin"], ["🐳", "whale baleine"], ["🦄", "unicorn licorne"], ["🌸", "cherry_blossom fleur"],
        ["🌹", "rose"], ["🌻", "sunflower tournesol"], ["🌷", "tulip tulipe"], ["🌱", "seedling pousse"],
        ["🌿", "herb plante"], ["🍀", "four_leaf_clover trefle chance"], ["🍁", "maple_leaf feuille automne"],
        ["🌲", "evergreen sapin"], ["🌳", "tree arbre"], ["🌵", "cactus"], ["🌞", "sun_with_face soleil"],
        ["☀️", "sunny soleil beau sonne"], ["⛅", "partly_sunny nuageux"], ["☁️", "cloud nuage"],
        ["🌧️", "rain pluie regen"], ["⛈️", "storm orage"], ["❄️", "snowflake neige flocon schnee"], ["⛄", "snowman"],
        ["🌈", "rainbow arc_en_ciel"], ["⚡", "zap eclair"], ["🔥", "fire feu top"], ["💧", "droplet goutte"],
        ["🌊", "ocean vague mer"], ["🌙", "moon lune nuit"], ["⭐", "star etoile"], ["🌟", "star2 brillant"],
        ["✨", "sparkles paillettes magie"], ["🌍", "earth terre monde europe"]
    ] },
    { key: "food", icon: "🍕", items: [
        ["☕", "coffee cafe pause kaffee"], ["🍵", "tea the"], ["🧃", "juice jus"], ["🥤", "soda"], ["🍺", "beer biere bier"],
        ["🍻", "beers sante cheers"], ["🍷", "wine vin wein"], ["🥂", "champagne trinquer"], ["🍾", "bottle bouteille"],
        ["🍹", "cocktail"], ["🍎", "apple pomme"], ["🍌", "banana banane"], ["🍓", "strawberry fraise"],
        ["🍒", "cherries cerise"], ["🍑", "peach peche"], ["🍍", "pineapple ananas"], ["🥑", "avocado avocat"],
        ["🍅", "tomato tomate"], ["🥕", "carrot carotte"], ["🌽", "corn mais"], ["🥐", "croissant"],
        ["🥖", "baguette pain"], ["🧀", "cheese fromage"], ["🥚", "egg oeuf"], ["🍳", "cooking cuisine"],
        ["🥞", "pancakes crepe"], ["🥓", "bacon"], ["🍔", "hamburger burger"], ["🍟", "fries frites"],
        ["🍕", "pizza"], ["🌭", "hotdog"], ["🥪", "sandwich"], ["🌮", "taco"], ["🍝", "spaghetti pates"],
        ["🍜", "ramen"], ["🍣", "sushi"], ["🥗", "salad salade"], ["🍿", "popcorn"], ["🍩", "doughnut donut"],
        ["🍪", "cookie biscuit"], ["🎂", "birthday gateau anniversaire"], ["🍰", "cake gateau"], ["🧁", "cupcake"],
        ["🍫", "chocolate chocolat"], ["🍬", "candy bonbon"], ["🍦", "icecream glace"], ["🍽️", "plate repas dejeuner"]
    ] },
    { key: "activity", icon: "🎉", items: [
        ["🎉", "tada fete bravo party feier"], ["🎊", "confetti"], ["🎈", "balloon ballon"], ["🎁", "gift cadeau"],
        ["🏆", "trophy trophee victoire"], ["🥇", "first_place medaille premier"], ["🏅", "medal medaille"],
        ["⚽", "soccer foot"], ["🏀", "basketball basket"], ["🏈", "football"], ["🎾", "tennis"], ["🏐", "volleyball"],
        ["🏓", "ping_pong"], ["🏸", "badminton"], ["⛳", "golf"], ["🚴", "bike velo"], ["🏊", "swim nager"],
        ["⛷️", "ski"], ["🏋️", "weight_lifting muscu"], ["🧘", "yoga"], ["🎮", "video_game jeu"], ["🎲", "dice de"],
        ["♟️", "chess echecs"], ["🧩", "puzzle"], ["🎯", "dart cible objectif"], ["🎨", "art peinture"],
        ["🎬", "clapper film"], ["🎤", "microphone micro chanter"], ["🎧", "headphones casque musique"],
        ["🎵", "musical_note note musique"], ["🎸", "guitar guitare"], ["🎹", "piano"], ["📸", "camera_flash photo"]
    ] },
    { key: "travel", icon: "🚀", items: [
        ["🚀", "rocket fusee lancement"], ["✈️", "airplane avion vol"], ["🚗", "car voiture auto"], ["🚕", "taxi"],
        ["🚌", "bus"], ["🚆", "train"], ["🚇", "metro"], ["🚲", "bicycle velo"], ["🛴", "scooter trottinette"],
        ["⛵", "boat bateau"], ["🚢", "ship navire"], ["🗺️", "map carte"], ["🧭", "compass boussole"],
        ["🏠", "house maison home"], ["🏡", "home maison_jardin"], ["🏢", "office bureau entreprise"],
        ["🏥", "hospital hopital"], ["🏫", "school ecole"], ["🏖️", "beach plage vacances"], ["⛰️", "mountain montagne"],
        ["🏕️", "camping"], ["🗼", "tokyo_tower tour"], ["🗽", "statue_of_liberty"], ["🌆", "city ville"],
        ["🌅", "sunrise lever_soleil"], ["🌃", "night nuit"], ["🚧", "construction travaux en_cours"],
        ["🚦", "traffic_light feu"], ["⛽", "fuel essence"], ["🛑", "stop"]
    ] },
    { key: "objects", icon: "💡", items: [
        ["💼", "briefcase travail mallette"], ["📁", "file_folder dossier"], ["📂", "open_folder"], ["📄", "page document"],
        ["📝", "memo note ecrire"], ["📋", "clipboard presse_papiers"], ["📌", "pushpin punaise epingle"],
        ["📎", "paperclip trombone"], ["✂️", "scissors ciseaux"], ["🖊️", "pen stylo"], ["✏️", "pencil crayon"],
        ["📅", "date calendrier agenda"], ["📆", "calendar calendrier"], ["🗓️", "spiral_calendar"],
        ["⏰", "alarm_clock reveil"], ["⏳", "hourglass sablier attente"], ["⌛", "hourglass_done"], ["⏱️", "stopwatch chrono"],
        ["💡", "bulb idee ampoule"], ["🔦", "flashlight lampe"], ["🔋", "battery batterie"], ["🔌", "plug prise"],
        ["💻", "computer ordinateur laptop"], ["🖥️", "desktop ecran"], ["⌨️", "keyboard clavier"], ["🖱️", "mouse_computer souris"],
        ["🖨️", "printer imprimante"], ["📱", "phone telephone mobile"], ["☎️", "telephone"], ["📞", "call appel"],
        ["📧", "email mail courriel"], ["📨", "incoming_envelope"], ["✉️", "envelope enveloppe lettre"], ["📦", "package colis"],
        ["📊", "bar_chart graphique stats"], ["📈", "chart_up hausse croissance"], ["📉", "chart_down baisse"],
        ["🔍", "mag recherche loupe"], ["🔒", "lock cadenas securite"], ["🔓", "unlock"], ["🔑", "key cle"],
        ["🛠️", "tools outils"], ["🔧", "wrench cle_molette"], ["🔨", "hammer marteau"], ["⚙️", "gear reglages"],
        ["🧰", "toolbox boite_outils"], ["🧪", "test_tube test essai"], ["💊", "pill medicament"], ["💰", "moneybag argent"],
        ["💶", "euro"], ["💳", "credit_card carte"], ["🧾", "receipt facture recu"], ["📚", "books livres"],
        ["📖", "book livre"], ["🔖", "bookmark marque_page"], ["🏷️", "label etiquette"], ["🗑️", "wastebasket poubelle"],
        ["🛒", "cart panier courses"], ["🎓", "graduation diplome"], ["☂️", "umbrella parapluie"], ["👓", "glasses lunettes"]
    ] },
    { key: "symbols", icon: "❤️", items: [
        ["❤️", "heart coeur amour love herz"], ["🧡", "orange_heart"], ["💛", "yellow_heart"], ["💚", "green_heart"],
        ["💙", "blue_heart coeur_bleu"], ["💜", "purple_heart"], ["🖤", "black_heart"], ["🤍", "white_heart"],
        ["💔", "broken_heart coeur_brise"], ["💕", "two_hearts"], ["💖", "sparkling_heart"], ["💯", "100 cent parfait"],
        ["✅", "white_check_mark fait valide ok erledigt"], ["☑️", "ballot_box_with_check coche"], ["✔️", "heavy_check_mark"],
        ["❌", "x croix non erreur"], ["❎", "negative_squared_cross"], ["⭕", "o cercle"], ["🚫", "no_entry interdit"],
        ["⛔", "no_entry_sign sens_interdit"], ["⚠️", "warning attention alerte"], ["❗", "exclamation important"],
        ["❓", "question"], ["‼️", "bangbang"], ["⁉️", "interrobang"], ["💬", "speech_balloon bulle message"],
        ["💭", "thought_balloon pensee"], ["🗯️", "anger_bubble"], ["💤", "zzz dodo"], ["🔔", "bell cloche notification"],
        ["🔕", "no_bell silence"], ["📣", "mega annonce"], ["📢", "loudspeaker haut_parleur"], ["🆕", "new nouveau"],
        ["🆗", "ok"], ["🆘", "sos aide"], ["🔴", "red_circle rouge"], ["🟠", "orange_circle"], ["🟡", "yellow_circle jaune"],
        ["🟢", "green_circle vert"], ["🔵", "blue_circle bleu"], ["⚪", "white_circle"], ["⚫", "black_circle"],
        ["➡️", "arrow_right fleche"], ["⬅️", "arrow_left"], ["⬆️", "arrow_up"], ["⬇️", "arrow_down"], ["🔄", "arrows_counterclockwise recharger"],
        ["🔁", "repeat repeter"], ["➕", "plus ajouter"], ["➖", "minus moins"], ["♻️", "recycle recycler"],
        ["🏁", "checkered_flag drapeau arrivee fini"], ["🚩", "triangular_flag drapeau"], ["🇪🇺", "eu europe"],
        ["🇫🇷", "fr france"], ["🇩🇪", "de allemagne deutschland"], ["🇧🇪", "be belgique"], ["🇨🇭", "ch suisse"],
        ["🇬🇧", "gb uk royaume_uni"], ["🇪🇸", "es espagne"], ["🇮🇹", "it italie"]
    ] }
]

// every emoji once, with its words
var ALL = (function () {
    var out = []
    for (var f = 0; f < FAMILIES.length; f++)
        for (var i = 0; i < FAMILIES[f].items.length; i++)
            out.push({ emoji: FAMILIES[f].items[i][0], words: FAMILIES[f].items[i][1].split(" "), family: FAMILIES[f].key })
    return out
})()

function fold(text) {
    return String(text).toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "")
}

// those whose words start with `query` (the earlier the word, the higher: « fete » is 🎉's second word,
// 🥳's fourth), then those holding it, at most `limit`; code: the word found (« :fete: »)
function search(query, limit) {
    var q = fold(query).replace(/^:/, "")
    if (!q) return []
    var found = []
    for (var i = 0; i < ALL.length; i++) {
        var e = ALL[i], score = -1, code = e.words[0]
        for (var w = 0; w < e.words.length; w++) {
            var word = fold(e.words[w])
            if (word.indexOf(q) === 0) { score = word === q ? w - 0.5 : w; code = e.words[w]; break }
            if (score < 0 && q.length >= 3 && word.indexOf(q) > 0) { score = 100 + w; code = e.words[w] }
        }
        if (score >= 0) found.push({ emoji: e.emoji, code: code, score: score, order: i })
    }
    found.sort(function (a, b) { return a.score - b.score || a.order - b.order })
    return found.slice(0, limit || 8).map(function (f) { return { emoji: f.emoji, code: f.code } })
}

// the classic emoticons, written alone between spaces (never in a word, a link or code)
var EMOTICONS = { ":)": "🙂", ":-)": "🙂", ":D": "😄", ":-D": "😄", ";)": "😉", ";-)": "😉", ":(": "🙁", ":-(": "🙁",
                  ":P": "😛", ":p": "😛", ":'(": "😢", ":o": "😮", ":O": "😮", "<3": "❤️", "</3": "💔", "xD": "😆", "XD": "😆",
                  ":|": "😐", ":/": "😕", "^^": "😊", "8)": "😎" }

// the usual ones of work, after the recent ones (« : » alone, the picker with nothing recent)
var POPULAR = ["👍", "❤️", "😂", "🎉", "👀", "🙏", "👏", "🔥", "✅", "💯", "😮", "😢", "🤔", "🚀", "☕", "💡", "⚠️", "📌"]

function codeOf(emoji) {
    for (var i = 0; i < ALL.length; i++) if (ALL[i].emoji === emoji) return ALL[i].words[0]
    return ""
}

// what « token » (the word being typed) may become: « : » alone → the recent then the usual ones; « :D », « :- »,
// « ;) », « <3 »… → their emoji (face: what was typed); « :fe » → search. Entries {emoji, code, face}
function suggest(token, recent, limit) {
    limit = limit || 8
    var out = [], seen = {}
    function add(e, code, face) { if (!seen[e] && out.length < limit) { seen[e] = true; out.push({ emoji: e, code: code, face: face || "" }) } }
    var faces = Object.keys(EMOTICONS)
    if (token.charAt(0) !== ":") {
        if (token.length >= 2 && EMOTICONS[token]) add(EMOTICONS[token], "", token)
        return out
    }
    var q = token.slice(1)
    if (!q) {
        var usual = (recent || []).concat(POPULAR)
        for (var i = 0; i < usual.length; i++) add(usual[i], codeOf(usual[i]))
        return out
    }
    for (var f = 0; f < faces.length; f++) if (faces[f].indexOf(token) === 0) add(EMOTICONS[faces[f]], "", faces[f])
    if (out.length && q.length < 2) return out
    var found = search(q, limit)
    for (var j = 0; j < found.length; j++) add(found[j].emoji, found[j].code)
    return out
}

function emoticons(text) {
    if (text.indexOf("`") >= 0) return text              // code: written as it is
    return text.replace(/(^|\s)(:-?\)|:-?D|;-?\)|:-?\(|:[pP]|:'\(|:[oO]|<\/?3|[xX]D|:\||:\/(?!\/)|\^\^|8\))(?=\s|$)/g,
                        function (all, before, face) { return before + (EMOTICONS[face] || face) })
}
