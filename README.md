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

## Démarrage

```bash
cd ~/test_agent/phone_mcp
./start.sh
```

Le script affiche une URL de la forme :

```
https://xxxx-xxxx.trycloudflare.com/<jeton-secret>/mcp
```

Sur **claude.ai** (depuis un navigateur) : **Paramètres > Connecteurs > Ajouter
un connecteur personnalisé**, colle l'URL et valide. Le connecteur est ensuite
disponible dans l'app mobile. Active-le dans une conversation via le menu des
outils, puis demande par exemple « lance la dernière vidéo de Squeezie ».

Laisse Termux ouvert en arrière-plan (la notification Termux doit rester visible).

## Pour que ce soit fluide

- **Ne plus devoir autoriser à chaque fois** : sur claude.ai, dans Paramètres >
  Connecteurs, ouvre ton connecteur et règle chaque outil sur « Toujours
  autoriser ». Tu peux aussi choisir « Toujours autoriser » directement dans la
  fenêtre de demande pendant une conversation.
- **Après un redémarrage de `start.sh`** : mets à jour l'URL du connecteur.

## À savoir

- **L'URL change à chaque redémarrage de `start.sh`** : c'est le cas du tunnel
  Cloudflare gratuit « rapide ». Il faut alors modifier l'URL du connecteur dans
  claude.ai. Pour une URL fixe, il faut un tunnel Cloudflare nommé, ce qui demande
  un compte Cloudflare gratuit et un nom de domaine.
- **Sécurité** : l'URL contient un jeton secret aléatoire (stocké dans
  `~/.config/phone-mcp/token`). Ne la partage pas. Si elle fuite, supprime ce
  fichier puis relance `start.sh` pour générer un nouveau jeton.
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
