"""New passwords, made here with the system's random source (secrets): no round trip, works offline.

Three styles:
- "strong" (default), like the ones Apple suggests: three groups of six letters that can be read aloud,
  one capital and one digit (gwosky-Kiddu7-pyrbem): about 71 bits, and easy to type on a phone or a TV;
- "random": letters, digits and, if wanted, symbols, of the chosen length;
- "words": a passphrase of common words (Wi-Fi keys, what must be typed by hand).
"""
import secrets

CONSONANTS = "bcdfghjkmnpqrstvwxz"
VOWELS = "aeiouy"
LOWER, UPPER, DIGITS = "abcdefghijkmnopqrstuvwxyz", "ABCDEFGHJKLMNPQRSTUVWXYZ", "23456789"
SYMBOLS = "-_.!?@#%+=*$&"

WORDS = """
abri acier agile aigle algue ambre ancre anis arbre argent arome astre atlas aube avril azur balade baleine
bambou banjo barque basilic berge bijou bison blason bleuet bocal bois bonsai bouleau boussole branche
brise bronze cabane cactus cadeau calme camelia canal canoe capitaine caramel carnet cascade castor cedre
cerise chalet chamois chanvre charme chene cheval chocolat cigale citron clairiere clementine comete
compas corail cosmos coton couleur crayon cristal cumulus cygne dauphin delta desert diamant dune ecorce
ecume eclair emeraude encre epice erable escale etoile falaise faucon feuille figue flamme flocon fontaine
foret fougere fraise frene galet gazelle geyser girafe givre glacier gland granit grenade griotte guitare
hamac harpe hermine heron hibou horizon houblon igloo indigo iris ivoire jade jardin jasmin jonquille
kayak kiwi lagon lagune lama lavande levant lierre lilas lime linotte loutre lucarne lumiere lune lynx
magnolia mandarine mangue marbre marais marine melodie menthe meridien merle mesange metal miel mimosa
mistral montagne mousse muguet myrtille narval nectar neige nenuphar noisette nomade nuage oasis ocean
olive ombre onyx orage orange orchidee origan ortie osier otarie ouragan pagaie palmier panda papyrus
paquebot pastel pecheur pelican perle phare piano pigeon pinson pivoine plage planete plume poivre pollen
pomme prairie prisme puits quartz radis rameau rapide recif renard riviere roche romarin roseau rubis
ruche sable safran saphir sapin saule savane sequoia sierra silex sirop soleil source sureau tamaris
tango tilleul tonnerre topaze torrent toucan tournesol trefle tulipe turquoise vague vallon vanille
velours vent verger vigne violette volcan voilier zebre zephyr
""".split()


def _pick(chars):
    return chars[secrets.randbelow(len(chars))]


def _shuffle(items):
    for i in range(len(items) - 1, 0, -1):
        j = secrets.randbelow(i + 1)
        items[i], items[j] = items[j], items[i]
    return items


def strong():
    groups = []
    for _ in range(3):
        groups.append([_pick(CONSONANTS), _pick(VOWELS), _pick(CONSONANTS), _pick(CONSONANTS), _pick(VOWELS),
                       _pick(CONSONANTS)])
    # one capital and one digit, at an edge of a group (where Apple puts them: easy to see when typing)
    g, edge = secrets.randbelow(3), _pick((0, 5))
    groups[g][edge] = groups[g][edge].upper()
    g2 = (g + 1 + secrets.randbelow(2)) % 3
    groups[g2][_pick((0, 5))] = _pick(DIGITS)
    return "-".join("".join(group) for group in groups)


def random_password(length=20, symbols=True, digits=True):
    length = max(8, min(128, int(length)))
    sets = [LOWER, UPPER] + ([DIGITS] if digits else []) + ([SYMBOLS] if symbols else [])
    pool = "".join(sets)
    out = [_pick(s) for s in sets]
    out += [_pick(pool) for _ in range(length - len(out))]
    return "".join(_shuffle(out))


def words(count=5, separator="-"):
    count = max(3, min(10, int(count)))
    chosen = [secrets.choice(WORDS) for _ in range(count)]
    i = secrets.randbelow(count)
    chosen[i] = chosen[i].capitalize()
    return separator.join(chosen) + separator + str(secrets.randbelow(90) + 10)


def make(style="strong", length=20, symbols=True, digits=True, count=5):
    if style == "random":
        return random_password(length, symbols, digits)
    if style == "words":
        return words(count)
    return strong()
