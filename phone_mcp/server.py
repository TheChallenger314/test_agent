#!/usr/bin/env python3
"""Serveur MCP minimal pour piloter un téléphone Android depuis Claude.

Tourne dans Termux, sans aucune dépendance externe (bibliothèque standard
uniquement), et parle le transport MCP « Streamable HTTP » en mode sans état :
chaque requête JSON-RPC reçoit une réponse JSON directe.

L'URL est protégée par un jeton secret placé dans le chemin :
    http://127.0.0.1:8765/<jeton>/mcp

Variables d'environnement :
    PHONE_MCP_TOKEN   jeton secret (obligatoire)
    PHONE_MCP_HOST    adresse d'écoute (défaut 127.0.0.1)
    PHONE_MCP_PORT    port d'écoute (défaut 8765)
    PHONE_MCP_DRY_RUN si "1", n'exécute aucune commande Android (tests)
"""

import gzip
import html as html_lib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SERVER_NAME = "android-phone"
SERVER_VERSION = "0.1.0"
SUPPORTED_PROTOCOL_VERSIONS = ["2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05"]
ALLOWED_URL_SCHEMES = {"http", "https", "geo"}
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

DRY_RUN = os.environ.get("PHONE_MCP_DRY_RUN") == "1"
# Commandes « exécutées » en mode DRY_RUN, pour les tests.
dry_run_log = []


class ToolError(Exception):
    """Erreur renvoyée à Claude comme résultat d'outil (isError=true)."""


# ---------------------------------------------------------------------------
# Actions Android
# ---------------------------------------------------------------------------

def run(cmd):
    if DRY_RUN:
        dry_run_log.append(cmd)
        return ""
    if shutil.which(cmd[0]) is None:
        raise FileNotFoundError(cmd[0])
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    output = (proc.stdout + proc.stderr).strip()
    if proc.returncode != 0 or output.startswith("Error"):
        raise RuntimeError(output or f"code de sortie {proc.returncode}")
    return output


def open_on_phone(url):
    """Ouvre une URL avec l'application Android qui la gère (YouTube, Maps…)."""
    attempts = [
        ["am", "start", "-a", "android.intent.action.VIEW", "-d", url],
        ["termux-open-url", url],
    ]
    errors = []
    for cmd in attempts:
        try:
            run(cmd)
            return
        except (FileNotFoundError, RuntimeError, subprocess.TimeoutExpired) as e:
            errors.append(f"{cmd[0]}: {e}")
    raise ToolError(
        "Impossible d'ouvrir l'URL sur le téléphone. Vérifie que Termux a la "
        "permission « Afficher par-dessus les autres applis ». Détails : "
        + " | ".join(errors)
    )


# ---------------------------------------------------------------------------
# YouTube
# ---------------------------------------------------------------------------

def extract_youtube_id(text):
    """Renvoie l'identifiant vidéo si `text` est un lien ou un ID YouTube."""
    text = text.strip()
    if YOUTUBE_ID_RE.match(text):
        return text
    try:
        parsed = urllib.parse.urlparse(text)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif host.endswith("youtube.com"):
        query_id = urllib.parse.parse_qs(parsed.query).get("v", [""])[0]
        parts = [p for p in parsed.path.split("/") if p]
        if query_id:
            candidate = query_id
        elif len(parts) >= 2 and parts[0] in ("shorts", "embed", "live", "v"):
            candidate = parts[1]
        else:
            return None
    else:
        return None
    return candidate if YOUTUBE_ID_RE.match(candidate) else None


def fetch_youtube(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
            # Page compressée : ~5 fois moins de données à télécharger.
            "Accept-Encoding": "gzip",
            # Évite la page de consentement cookies servie en Europe.
            "Cookie": "SOCS=CAI; CONSENT=YES+1",
        },
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", errors="replace")


def fetch_search_page(query, filter_param=None):
    params = {"search_query": query}
    if filter_param:
        params["sp"] = filter_param
    return fetch_youtube("https://www.youtube.com/results?" + urllib.parse.urlencode(params))


def _text(node):
    if not isinstance(node, dict):
        return ""
    if "simpleText" in node:
        return node["simpleText"]
    return "".join(run_.get("text", "") for run_ in node.get("runs", []))


def parse_search_results(html, max_results):
    """Extrait les vidéos d'une page de résultats YouTube."""
    results = []
    match = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if match:
        try:
            data = json.loads(match.group(1))
        except json.JSONDecodeError:
            data = None
        stack = [data]
        seen = set()
        while stack and len(results) < max_results:
            node = stack.pop()
            if isinstance(node, dict):
                vr = node.get("videoRenderer")
                if isinstance(vr, dict) and vr.get("videoId") not in seen:
                    seen.add(vr.get("videoId"))
                    results.append({
                        "id": vr.get("videoId"),
                        "title": _text(vr.get("title")),
                        "channel": _text(vr.get("ownerText")),
                        "duration": _text(vr.get("lengthText")),
                    })
                # Parcours dans l'ordre du document (pile LIFO → on inverse).
                stack.extend(reversed(list(node.values())))
            elif isinstance(node, list):
                stack.extend(reversed(node))
    if not results:
        # Repli : simple recherche d'identifiants dans la page.
        for vid in dict.fromkeys(re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)):
            results.append({"id": vid, "title": "", "channel": "", "duration": ""})
            if len(results) >= max_results:
                break
    return results


def find_renderers(html, key):
    """Renvoie, dans l'ordre de la page, les objets `key` de ytInitialData."""
    match = re.search(r"var ytInitialData\s*=\s*(\{.*?\});\s*</script>", html, re.S)
    if not match:
        return []
    try:
        stack = [json.loads(match.group(1))]
    except json.JSONDecodeError:
        return []
    found = []
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            if isinstance(node.get(key), dict):
                found.append(node[key])
            stack.extend(reversed(list(node.values())))
        elif isinstance(node, list):
            stack.extend(reversed(node))
    return found


CHANNEL_FILTER = "EgIQAg=="  # filtre de recherche YouTube « Chaînes »


def parse_latest_from_feed(xml):
    """Première entrée (la plus récente) du flux RSS d'une chaîne."""
    entry = re.search(r"<entry>(.*?)</entry>", xml, re.S)
    if not entry:
        return None
    vid = re.search(r"<yt:videoId>([A-Za-z0-9_-]{11})</yt:videoId>", entry.group(1))
    title = re.search(r"<title>(.*?)</title>", entry.group(1), re.S)
    if not vid:
        return None
    return {"id": vid.group(1),
            "title": html_lib.unescape(title.group(1)) if title else ""}


def latest_video_of_channel(channel):
    try:
        page = fetch_search_page(channel, CHANNEL_FILTER)
    except Exception as e:
        raise ToolError(f"Recherche de la chaîne impossible : {e}")
    channels = [c for c in find_renderers(page, "channelRenderer") if c.get("channelId")]
    if not channels:
        raise ToolError(f"Aucune chaîne trouvée pour « {channel} ».")
    chan = channels[0]
    try:
        feed = fetch_youtube(
            "https://www.youtube.com/feeds/videos.xml?channel_id=" + chan["channelId"]
        )
    except Exception as e:
        raise ToolError(f"Lecture du flux de la chaîne impossible : {e}")
    video = parse_latest_from_feed(feed)
    if not video:
        raise ToolError(f"Aucune vidéo trouvée sur la chaîne « {_text(chan.get('title'))} ».")
    video["channel"] = _text(chan.get("title"))
    return video


def search_youtube(query, max_results):
    try:
        html = fetch_search_page(query)
    except Exception as e:  # réseau, HTTP…
        raise ToolError(f"Recherche YouTube impossible : {e}")
    results = parse_search_results(html, max_results)
    if not results:
        raise ToolError(f"Aucune vidéo trouvée pour « {query} ».")
    return results


def describe(video):
    parts = [video["title"] or video["id"]]
    if video["channel"]:
        parts.append(f"— {video['channel']}")
    if video["duration"]:
        parts.append(f"({video['duration']})")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Outils MCP
# ---------------------------------------------------------------------------

def tool_youtube_play(args):
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("Paramètre « query » manquant.")
    video_id = extract_youtube_id(query)
    if video_id:
        label = video_id
    else:
        video = search_youtube(query, 1)[0]
        video_id, label = video["id"], describe(video)
    open_on_phone(f"https://www.youtube.com/watch?v={video_id}")
    return f"Lecture lancée sur le téléphone : {label}"


def tool_youtube_play_latest(args):
    channel = str(args.get("channel", "")).strip()
    if not channel:
        raise ToolError("Paramètre « channel » manquant.")
    video = latest_video_of_channel(channel)
    open_on_phone(f"https://www.youtube.com/watch?v={video['id']}")
    return f"Lecture lancée : {video['title']} — {video['channel']}"


def tool_youtube_search(args):
    query = str(args.get("query", "")).strip()
    if not query:
        raise ToolError("Paramètre « query » manquant.")
    max_results = max(1, min(int(args.get("max_results", 5)), 20))
    videos = search_youtube(query, max_results)
    lines = [f"{i}. {describe(v)} [id: {v['id']}]" for i, v in enumerate(videos, 1)]
    return "\n".join(lines)


def tool_open_url(args):
    url = str(args.get("url", "")).strip()
    scheme = urllib.parse.urlparse(url).scheme.lower()
    if scheme not in ALLOWED_URL_SCHEMES:
        raise ToolError(
            f"Schéma « {scheme or '?'} » refusé. Autorisés : "
            + ", ".join(sorted(ALLOWED_URL_SCHEMES))
        )
    open_on_phone(url)
    return f"Ouvert sur le téléphone : {url}"


def tool_set_volume(args):
    try:
        percent = int(args.get("percent"))
    except (TypeError, ValueError):
        raise ToolError("Paramètre « percent » (0-100) manquant ou invalide.")
    percent = max(0, min(percent, 100))
    max_volume = 15
    if not DRY_RUN:
        try:
            streams = json.loads(run(["termux-volume"]))
            music = next(s for s in streams if s.get("stream") == "music")
            max_volume = int(music["max_volume"])
        except (FileNotFoundError, RuntimeError, StopIteration, KeyError, ValueError):
            raise ToolError(
                "termux-volume indisponible : installe le paquet « termux-api » "
                "et l'application Termux:API."
            )
    level = round(percent * max_volume / 100)
    try:
        run(["termux-volume", "music", str(level)])
    except (FileNotFoundError, RuntimeError) as e:
        raise ToolError(f"Réglage du volume impossible : {e}")
    return f"Volume média réglé à {percent} % ({level}/{max_volume})."


TOOLS = {
    "youtube_play": {
        "handler": tool_youtube_play,
        "description": (
            "Lance une vidéo YouTube sur le téléphone Android de l'utilisateur, "
            "dans l'application YouTube. Accepte une recherche (le premier "
            "résultat est joué), un lien YouTube ou un identifiant de vidéo."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Recherche, lien YouTube ou ID de vidéo.",
                }
            },
            "required": ["query"],
        },
    },
    "youtube_play_latest": {
        "handler": tool_youtube_play_latest,
        "description": (
            "Lance sur le téléphone la vidéo la plus récente d'une chaîne YouTube "
            "(ex. « la dernière vidéo d'Adam Savage »). Un seul appel suffit."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "channel": {
                    "type": "string",
                    "description": "Nom de la chaîne ou du créateur.",
                }
            },
            "required": ["channel"],
        },
    },
    "youtube_search": {
        "handler": tool_youtube_search,
        "description": (
            "Cherche des vidéos YouTube et renvoie titres, chaînes, durées et "
            "identifiants, sans rien lancer. Utile pour choisir la bonne vidéo "
            "avant d'appeler youtube_play avec son identifiant."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Termes de recherche."},
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
    "open_url": {
        "handler": tool_open_url,
        "description": (
            "Ouvre une URL sur le téléphone avec l'application adaptée "
            "(navigateur, YouTube, Google Maps avec geo:…)."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL http(s) ou geo: à ouvrir.",
                }
            },
            "required": ["url"],
        },
    },
    "set_volume": {
        "handler": tool_set_volume,
        "description": (
            "Règle le volume média (musique/vidéos) du téléphone, en pourcentage. "
            "Nécessite l'application Termux:API."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "percent": {"type": "integer", "minimum": 0, "maximum": 100}
            },
            "required": ["percent"],
        },
    },
}


# ---------------------------------------------------------------------------
# JSON-RPC / MCP
# ---------------------------------------------------------------------------

def rpc_error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def handle_message(msg):
    """Traite un message JSON-RPC ; renvoie None pour une notification."""
    if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
        return rpc_error(None, -32600, "Requête invalide")
    method = msg.get("method")
    msg_id = msg.get("id")
    if "id" not in msg:
        return None  # notification (ex. notifications/initialized)
    params = msg.get("params") or {}

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = (
            requested
            if requested in SUPPORTED_PROTOCOL_VERSIONS
            else SUPPORTED_PROTOCOL_VERSIONS[0]
        )
        result = {
            "protocolVersion": version,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": (
                "Ces outils agissent sur le téléphone Android de l'utilisateur. "
                "Agis immédiatement, en un seul appel, sans demander de "
                "confirmation ni chercher d'abord : « mets/lance une vidéo de X » "
                "→ youtube_play ; « la dernière vidéo de X » → "
                "youtube_play_latest. Réponds ensuite en une phrase très courte."
            ),
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {
            "tools": [
                {"name": name, "description": t["description"], "inputSchema": t["inputSchema"]}
                for name, t in TOOLS.items()
            ]
        }
    elif method == "tools/call":
        name = params.get("name")
        tool = TOOLS.get(name)
        if tool is None:
            return rpc_error(msg_id, -32602, f"Outil inconnu : {name}")
        try:
            text, is_error = tool["handler"](params.get("arguments") or {}), False
        except ToolError as e:
            text, is_error = str(e), True
        except Exception as e:  # ne jamais faire tomber le serveur
            text, is_error = f"Erreur inattendue : {e!r}", True
        print(f"[outil] {name} -> {text}", file=sys.stderr)
        result = {"content": [{"type": "text", "text": text}], "isError": is_error}
    else:
        return rpc_error(msg_id, -32601, f"Méthode inconnue : {method}")
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


class Handler(BaseHTTPRequestHandler):
    token = ""
    protocol_version = "HTTP/1.1"

    def _path_ok(self):
        path = urllib.parse.urlparse(self.path).path.rstrip("/")
        return bool(self.token) and path in (f"/{self.token}", f"/{self.token}/mcp")

    def _send(self, status, body=None, extra_headers=None):
        payload = b"" if body is None else json.dumps(body).encode("utf-8")
        self.send_response(status)
        if body is not None:
            self.send_header("Content-Type", "application/json")
        for key, value in (extra_headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        if not self._path_ok():
            return self._send(404, {"error": "not found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length) or b"null")
        except (ValueError, json.JSONDecodeError):
            return self._send(400, rpc_error(None, -32700, "JSON invalide"))

        if isinstance(body, list):
            responses = [r for r in (handle_message(m) for m in body) if r is not None]
            return self._send(200, responses) if responses else self._send(202)
        response = handle_message(body)
        if response is None:
            return self._send(202)
        return self._send(200, response)

    def do_GET(self):
        # Pas de flux SSE côté serveur : autorisé par la spécification.
        if not self._path_ok():
            return self._send(404, {"error": "not found"})
        self._send(405, extra_headers={"Allow": "POST"})

    do_DELETE = do_GET

    def log_message(self, fmt, *args):
        # Ne jamais écrire le jeton secret dans les journaux.
        line = fmt % args
        if self.token:
            line = line.replace(self.token, "<jeton>")
        print(f"[http] {line}", file=sys.stderr)


def make_server(host, port, token):
    handler = type("PhoneHandler", (Handler,), {"token": token})
    return ThreadingHTTPServer((host, port), handler)


def main():
    token = os.environ.get("PHONE_MCP_TOKEN", "")
    if len(token) < 16:
        sys.exit("PHONE_MCP_TOKEN doit contenir au moins 16 caractères (lance start.sh).")
    host = os.environ.get("PHONE_MCP_HOST", "127.0.0.1")
    port = int(os.environ.get("PHONE_MCP_PORT", "8765"))
    server = make_server(host, port, token)
    print(f"Serveur MCP en écoute sur http://{host}:{port}/<jeton>/mcp", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
