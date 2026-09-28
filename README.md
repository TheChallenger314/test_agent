# test_agent — piloter son téléphone Android depuis Claude

Ce dépôt contient un petit **serveur MCP** qui tourne sur le téléphone (dans
Termux). Une fois ajouté comme **connecteur personnalisé** dans claude.ai, tu
peux dire à Claude, depuis l'app ou le site :

> « Mets-moi une vidéo de lofi sur mon téléphone »

et YouTube s'ouvre sur le téléphone avec la vidéo.

Les connecteurs personnalisés sont inclus dans les abonnements Pro/Max :
**aucun crédit API n'est nécessaire**.

```
App Claude ──► serveurs Anthropic ──► tunnel Cloudflare ──► Termux (server.py) ──► YouTube
```

## Outils disponibles

| Outil            | Effet                                                                 |
|------------------|-----------------------------------------------------------------------|
| `youtube_play`   | Lance une vidéo (recherche → 1er résultat, ou lien/ID YouTube)        |
| `youtube_play_latest` | Lance la dernière vidéo d'une chaîne (« la dernière vidéo d'Adam Savage ») |
| `youtube_search` | Liste des résultats sans rien lancer, pour que Claude choisisse       |
| `open_url`       | Ouvre une URL `http(s)` ou `geo:` (Maps) avec l'appli adaptée         |
| `set_volume`     | Règle le volume média en % (nécessite Termux:API)                     |

## Installation (une seule fois)

1. Installe **Termux** et **Termux:API** depuis **F-Droid** (la version du Play
   Store est obsolète). Les deux applis doivent venir de la même source.
2. Dans les paramètres Android > Applis > **Termux** :
   - active **« Afficher par-dessus les autres applis »**. C'est indispensable,
     sinon Android bloque l'ouverture de YouTube quand Termux est en arrière-plan ;
   - désactive l'**optimisation de la batterie**.
3. Dans Termux :
   ```bash
   pkg install -y git
   git clone https://github.com/TheChallenger314/test_agent.git
   cd test_agent/phone_mcp
   ./install.sh
   ```

## URL fixe avec ngrok (une seule fois)

1. Crée un compte gratuit sur https://ngrok.com.
2. Dans Termux :
   ```bash
   cd ~/test_agent/phone_mcp && ./setup_ngrok.sh
   ```
   Le script installe ngrok, puis te demande ton **authtoken**
   (https://dashboard.ngrok.com/get-started/your-authtoken) et ton **domaine
   gratuit** (https://dashboard.ngrok.com/domains, du type `xxx.ngrok-free.app`).

Sans ngrok, `start.sh` utilise un tunnel Cloudflare temporaire, dont l'URL change
à chaque démarrage.

## Démarrage automatique avec le téléphone (une seule fois)

1. Installe **Termux:Boot** depuis F-Droid et ouvre-la une fois.
2. Dans Termux :
   ```bash
   cd ~/test_agent/phone_mcp && ./enable_boot.sh
   ```
3. Sur les téléphones Realme, Oppo, Xiaomi, etc. : dans les paramètres Android,
   autorise **Termux** et **Termux:Boot** à démarrer automatiquement et à tourner
   en arrière-plan (réglages de batterie).

Le service démarre alors tout seul à chaque allumage du téléphone. Il reste en
veille sans rien faire jusqu'à ce que Claude l'appelle.

## Utilisation

```bash
./start.sh   # démarre le service (ou affiche l'URL s'il tourne déjà)
./stop.sh    # l'arrête (par exemple avant une mise à jour avec git pull)
```

Sur **claude.ai** (depuis un navigateur) : **Paramètres > Connecteurs > Ajouter
un connecteur personnalisé**, colle l'URL affichée par `start.sh` (laisse OAuth
vide) et valide. Avec ngrok, c'est à faire une seule fois. Le connecteur est
ensuite disponible dans l'app mobile : active-le dans une conversation via le
menu des outils, puis demande par exemple « lance la dernière vidéo de Squeezie ».

## Pour que ce soit fluide

- **Ne plus devoir autoriser à chaque fois** : sur claude.ai, dans Paramètres >
  Connecteurs, ouvre ton connecteur et règle chaque outil sur « Toujours
  autoriser ». Tu peux aussi choisir « Toujours autoriser » directement dans la
  fenêtre de demande pendant une conversation.
- **Parle-lui avec la dictée** (le micro dans la zone de saisie) plutôt qu'avec
  le mode vocal : il n'écoutera pas de nouveau après avoir lancé la vidéo.

## À savoir

- **Le tunnel se relance tout seul** s'il tombe (perte de réseau…). Journal du
  service démarré automatiquement : `~/.config/phone-mcp/service.log`.
- **Sécurité** : l'URL contient un jeton secret aléatoire (stocké dans
  `~/.config/phone-mcp/token`). Ne la partage pas. Si elle fuite, supprime ce
  fichier puis relance le service (`./stop.sh` puis `./start.sh`) pour générer un nouveau jeton.
  Le serveur n'accepte que les liens `http`, `https` et `geo:`, et ne peut ni
  appeler, ni envoyer de SMS, ni lire tes données.
- La recherche YouTube lit la page de résultats publique, sans clé d'API. Si
  YouTube change sa page, `youtube_play` avec un lien direct continue de marcher.

## Tests

```bash
cd phone_mcp && python -m unittest test_server.py -v
```

Les tests tournent en mode simulé (`PHONE_MCP_DRY_RUN=1`) et n'ont besoin ni de
téléphone ni d'Internet.
