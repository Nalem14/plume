# Plume (bureau)

Plume pour Windows, macOS et Linux : courrier, agenda, contacts, notes, tâches, mots de passe, Ornis et Meet (discussions et
appels) du compte Orneos dans une seule app native, avec la Photothèque (ouverte depuis la grille des apps, pas depuis le rail)
et la grille des autres apps du cloud, marquées d'un petit nuage : elles s'ouvrent dans le navigateur. Elle remplace l'ancien
lanceur Electron.

La carte des lieux de la Photothèque demande QtLocation et son extension `geoservices` (tuiles OpenStreetMap) : `plume.spec`
les garde. Ses vidéos s'ouvrent dans le lecteur de l'ordinateur (QtMultimedia en QML n'est pas embarqué).

Meet démarre avec Plume (les appels sonnent fenêtre fermée) ; sa page d'appel (QtWebEngine) n'est chargée que pendant un appel.
QtWebSockets (signaling : sonnerie immédiate, « … écrit ») et QtMultimedia (messages vocaux) restent donc dans le paquet.
Sur macOS, la caméra et le micro sont demandés une fois (`NSCameraUsageDescription`, `NSMicrophoneUsageDescription` de `plume.spec`).

**Ce dossier ne contient que l'empaquetage.** Le code est celui des apps d'Orneos OS
(`os/files/usr/share/orneos*`). Toute amélioration d'un module profite donc aux deux. Ce qui dépend du système
(trousseau, notifications, liens, démarrage) passe par `orneos/system.py`.

Ouverture avec la session (hors Orneos OS) : Réglages › Démarrage, ou la même case dans le menu de l'icône de la zone
de notification (les deux restent d'accord, `plume.autostart`). `system.set_autostart` écrit la clé `Run` du registre
(Windows, retirée par la désinstallation), un LaunchAgent (macOS) ou un `.desktop` dans `~/.config/autostart` (Linux),
toujours avec `--background` (zone de notification seule). Au lancement, une entrée existante est réécrite : elle suit
Plume s'il a changé de place (nouvelle AppImage).

Sélecteurs de fichiers (Joindre, Importer, Enregistrer sous…) : ceux du système partout (`system.native_dialogs()`, appelé avant l'app par chaque programme). Windows et macOS les ont toujours ; sous Linux, Qt passe par le thème de son bureau (KDE, GTK), que l'AppImage et le `.deb` n'embarquent pas : il dessinait alors son propre sélecteur, à la racine du disque. Plume y choisit le portail (`QT_QPA_PLATFORMTHEME=xdgdesktopportal`, plugin embarqué : le sélecteur de KDE, GNOME…) quand le thème du bureau manque ; sans portail, Qt reprend le sien. Chaque sélecteur part d'un dossier (`QtCore.StandardPaths`, importé `as Std` : son `Settings` masquerait celui d'Ornis) : Téléchargements pour enregistrer, avec le nom du fichier ; le dossier personnel (Images pour une photo) pour joindre. Ne préremplis jamais `"file:///" + nom` : c'est la racine du disque.

Mots de passe hors d'Orneos OS : la clé de la copie chiffrée va dans le trousseau du système (Gestionnaire
d'identifiants, Trousseau macOS, Secret Service), et le verrou demande le mot de passe du compte Windows
(`LogonUser`, pas le code PIN) ou Mac (`dscl -authonly`), ou Windows Hello (PowerShell, `UserConsentVerifier`) ou Touch ID (`plume-touchid`, `plume/macos/touchid.swift`, compilé par la CI dans `Plume.app/Contents/MacOS`). Le Wi-Fi (NetworkManager) et la lecture d'un QR code
à l'écran (Spectacle) n'existent que sous Linux ; un lien `otpauth://` collé ou ouvert marche partout.

Sur Orneos OS, le même code donne trois apps : Courrier, Agenda et Contacts (`plume --edition=mail|calendar|contacts`,
commandes `orneos-mail`…). Le `.rpm` de Plume reste installable à côté : il vit dans `/usr/lib/orneos-plume` et apporte
seul `/usr/bin/plume`, `eu.orneos.plume.desktop` et son icône, que l'image n'a plus.

## Fichiers

| Fichier | Rôle |
|---|---|
| `stage.py` | Copie les apps comme dans `/usr/share` et génère `apps.json` et les icônes (`os/tools/apps.py`). Télécharge les polices d'`os/Containerfile` (mêmes sommes de contrôle) et crée l'icône `.png`/`.ico`/`.icns`. |
| `plume.spec` | PyInstaller : Python, Qt et les bibliothèques. Les apps restent des fichiers (`launch.py`), comme sur l'OS. Les modules Qt inutiles (3D, multimédia…) sont retirés. |
| `requirements*.txt` | Versions figées, alignées sur Orneos OS : Qt 6.11, icalendar 6, dateutil 2.9. |
| `windows/plume.iss` | Installeur Inno Setup par utilisateur (`%LOCALAPPDATA%\Programs\Plume`), sans demande d'administrateur. Déclare `mailto:`, `webcal:`, `.ics` et `orneos://`. ⚠️ Ne change jamais son `AppId`. |
| `linux/build.sh` | AppImage (qui s'ajoute elle-même au menu) et `.deb` (`/opt/plume`). |
| `linux/rpm.sh` | `.rpm` noarch : les sources sur le Qt de Fedora, dans `/usr/lib/orneos-plume`. |

macOS : `Plume.app` vient de `plume.spec` (`Info.plist` : `mailto`, `webcal`, `orneos`, `.ics`). La CI le signe
« ad hoc » et le met dans un DMG.

## Construire

La CI (`plume/ci/plume.yml`) construit sur Ubuntu 22.04, Windows, macOS arm64 (Apple Silicon) et macOS x86_64 (Mac Intel, runner `macos-15-intel`). Elle ne tourne pas dans ce dépôt
privé, dont les minutes GitHub gratuites sont épuisées (macOS compte 10 fois), mais sur **github.com/Nalem14/plume**,
un dépôt **public** où les runners sont gratuits, macOS compris. Il ne contient que les fichiers lus par le build
(liste `PATHS` de `tools/plume-ci.sh`) et il est remplacé à chaque build. ⚠️ Tout ce qui y va devient public : jamais
de secret dans ces fichiers.
```sh
sh tools/plume-ci.sh plume-v1.0.1        # la version de plume_core/__init__.py ; prend l'étiquette locale, sinon HEAD
sh tools/plume-ci.sh plume-test-essai    # un essai de HEAD (fichiers commités seulement)
```

Chaque paquet passe `--self-test` : les vues des modules, Chromium (QtWebEngine), le trousseau et les polices.
Les fichiers vont ensuite dans une *release* brouillon.

En local, sous Linux, depuis la racine du dépôt :
```sh
python plume/stage.py build/stage
PLUME_STAGE=build/stage pyinstaller --distpath build/dist --workpath build/work plume/plume.spec
sh plume/linux/build.sh build/dist/Plume dist "$(cat build/stage/version)"
sh plume/linux/rpm.sh build/stage dist
build/dist/Plume/Plume --self-test=report.txt && cat report.txt
```

## Publier

Sur le serveur, la signature se fait là où vit la clé :
```sh
sh tools/plume-publish.sh plume-v1.0.1 --channel=unstable   # essai
sh tools/plume-publish.sh plume-v1.0.1                      # tout le monde
```
Le script télécharge la release brouillon, puis appelle `tools/client-release.php plume`. Chaque fichier va dans
`public_html/downloads/plume/` et est signé en Ed25519 avec `private/clients/plume-ed25519.key` (à garder dans les
sauvegardes). Le manifeste `private/clients/plume.json` est servi par `/updates/plume`.

## Mises à jour

`orneos/updater.py` vérifie au démarrage, toutes les 6 h, au retour au premier plan après 2 h sans vérification
(`checkIfStale`) et sur « Rechercher les mises à jour » (Réglages › Compte, `checkNow` : « Recherche en cours… », « Plume
est à jour », le téléchargement en %, ou l'échec). Il n'accepte qu'un fichier dont le SHA-256 et la signature
correspondent : les binaires ne sont pas signés par Apple ni par Microsoft, cette signature est la seule garantie.
Une version prête s'annonce par une barre fine en haut de la fenêtre avec, à droite, la pastille verte « Mettre à
jour » qui pulse (`Main.qml`, `updatePill`). Au clic, les fenêtres de Plume disparaissent et `UpdateSplash.qml` (fenêtre
`updateSplash`, ciel « Nuit », logo dans un anneau qui tourne) dit « Mise à jour de Plume » puis « Plume redémarre… »
jusqu'à la fermeture ; un échec rouvre les fenêtres et la pastille. Selon le paquet :
- Windows, macOS et AppImage : Plume se remplace lui-même (pastille, sinon à la fermeture) ; sous Windows, l'installeur
  montre sa fenêtre de progression (`/SILENT`) quand on l'a demandé, rien à la fermeture (`/VERYSILENT`) ;
- `.deb` et `.rpm` : le fichier est confié à l'installeur du système.

Une version n'est jamais remplacée par une plus ancienne. Pour revenir en arrière, il faut publier une version plus
récente.

Pour une nouvelle version, augmente `VERSION` dans `os/files/usr/share/orneos-plume/plume_core/__init__.py`, commite,
pose l'étiquette `plume-v<version>`, puis lance `sh tools/plume-ci.sh plume-v<version>`.

## « Quoi de neuf » au premier plan

La récupération (`GET …/news?confirm=1`) ne prend pas la fenêtre quotidienne commune au navigateur et à Plume : `claim()` la réserve (`PUT …/news/shown`) juste avant d’ouvrir la fenêtre, et seul le premier appareil qui l’ouvre vraiment la montre (avant le 09/11, la demander suffisait à la consommer : Plume ne la montrait jamais). Elle ne démarre que lorsque la fenêtre est visible, active et connectée. Le retour au premier plan retente la récupération (au plus une fois par minute), en plus du contrôle toutes les six heures. Un changement de compte efface les annonces en attente et invalide les réponses précédentes ; fermer l’ancienne fenêtre ne marque rien lu sur le nouveau compte. Les éditions Agenda et Contacts restent silencieuses.

Tests sans réseau : `os/tests/plume/newstest.py` et `newsuitest.py`, inclus dans `os/tests/plume/run.sh`. Ce correctif de sources nécessite une nouvelle distribution pour les Plume déjà installés.
