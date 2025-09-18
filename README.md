# anime-helper (MCP server)

Servidor **Model Context Protocol (MCP)** para **Anime & Manga** que entrega **JSON estructurado** desde **AniList GraphQL** (sin API key) con **Jikan** (MyAnimeList) como *fallback*.
El **LLM del host** usa estos datos para redactar resúmenes, recomendaciones y respuestas al usuario.

* 🔎 `search_media` — búsqueda de ANIME/MANGA (AniList por defecto; Jikan fallback)
* 📄 `media_details` — ficha normalizada (títulos, formato/estado, episodios/capítulos, géneros, sinopsis, enlaces externos, recomendaciones)
* 📈 `trending` — lo que está en tendencia (AniList)
* 🩺 `health` / ℹ️ `about` — diagnóstico y metadatos del servidor
* 🧱 **Contrato estable** con `schemaVersion`, *timeouts*, **reintentos con backoff** y **errores uniformes**

> **No necesitas API key** para AniList ni Jikan.

---

## Requisitos

* Python **3.10+**
* `pip`
* Un **host MCP** (por ejemplo, tu host OpenAI por STDIO)

---

## Instalación

### Opción A — desde **tag** (recomendado para usuarios)

```bash
pip install -U --no-cache-dir git+https://github.com/Ctribsz/AnimeHelper-MCP.git@v0.1.0
```

### Opción B — desde **main** (último código)

```bash
pip install -U --no-cache-dir git+https://github.com/Ctribsz/AnimeHelper-MCP.git@main
```

### Opción C — modo dev (editable)

```bash
git clone https://github.com/Ctribsz/AnimeHelper-MCP
cd AnimeHelper-MCP
python -m venv .venv
# Linux/Mac:
source .venv/bin/activate
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

pip install -U pip
pip install -e .
```

---

## Uso desde un host MCP (STDIO)

En el `mcp.config.json` de tu host añade:

```json
{
  "servers": {
    "anime-helper": {
      "command": "python",
      "args": ["-m", "anime_helper.server"],
      "transport": "stdio"
    }
  }
}
```

Arranca tu host (ejemplo OpenAI):

```bash
python -m src.host_openai
```

Deberías ver algo como:

```
✔️ Conectado a 'anime-helper' con herramientas: ['search_media', 'media_details', 'trending', 'health', 'about']
```

---

## Prompts de prueba (para el chat del host)

1. **Búsqueda**

```
Usa anime-helper__search_media {"query":"one piece","kind":"ANIME","limit":3} y muéstrame los títulos con su id.
```

2. **Detalles (AniList)**

```
Llama anime-helper__media_details {"source":"anilist","id":21,"kind":"ANIME"} y resume en 5 puntos. Cita la URL.
```

3. **Tendencia (Manga)**

```
Usa anime-helper__trending {"kind":"MANGA","limit":5} y ordénalos por score descendente con título y año.
```

4. **Salud / versión**

```
Ejecuta anime-helper__health y luego anime-helper__about para ver versión y endpoints.
```

---

## Tools & contrato JSON

### `search_media(query, kind="ANIME|MANGA", source="anilist|jikan", limit=5)`

**Éxito:**

```json
{
  "schemaVersion": "1.0.0",
  "query": "one piece",
  "kind": "ANIME",
  "source": "anilist",
  "results": [
    {
      "source": "anilist",
      "id": 21,
      "idMal": 21,
      "titles": {"romaji":"One Piece","english":"One Piece","native":"ワンピース"},
      "year": 1999,
      "format": "TV",
      "episodes": 1100,
      "chapters": null,
      "score": 86,
      "url": "https://anilist.co/anime/21"
    }
  ]
}
```

### `media_details(source, id, kind="ANIME|MANGA")`

**Éxito (campos principales):**

```json
{
  "schemaVersion": "1.0.0",
  "source": "anilist",
  "id": 21,
  "idMal": 21,
  "titles": {"romaji":"One Piece","english":"One Piece","native":"ワンピース"},
  "format": "TV",
  "status": "RELEASING",
  "episodes": 1100,
  "chapters": null,
  "genres": ["Action","Adventure"],
  "tags": ["Shounen", "Pirates"],
  "score": {"anilist": 86, "mal": null},
  "synopsis": "…",
  "url": "https://anilist.co/anime/21",
  "external": [{"site":"Official","url":"…"}],
  "recommendations": [ /* MediaHit[] */ ]
}
```

### `trending(kind="ANIME|MANGA", limit=10)`

**Éxito:**

```json
{
  "schemaVersion": "1.0.0",
  "kind": "MANGA",
  "results": [ /* MediaHit[] */ ]
}
```

### `health()` / `about()`

```json
{"schemaVersion":"1.0.0","ok":true,"sources":["anilist","jikan"]}
```

```json
{
  "schemaVersion": "1.0.0",
  "name": "anime-helper",
  "version": "0.1.0",
  "endpoints": {"anilist": "https://graphql.anilist.co", "jikan": "https://api.jikan.moe/v4"},
  "limits": {"maxPerPage": 25, "timeoutSec": 15}
}
```

### Errores (uniforme)

```json
{
  "schemaVersion": "1.0.0",
  "error": {
    "code": "UPSTREAM_429",
    "message": "rate limited by upstream",
    "source": "anilist"
  }
}
```

---

## Smoke test (opcional, desde tu host)

Crea `scripts/smoke_test.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
printf "anime-helper__health\nanime-helper__search_media {\"query\":\"one piece\",\"kind\":\"ANIME\",\"limit\":2}\nsalir\n" | python -m src.host_openai
```

Linux/Mac:

```bash
chmod +x scripts/smoke_test.sh
./scripts/smoke_test.sh
```

Windows (PowerShell):

```powershell
"anime-helper__health`nanime-helper__search_media {""query"":""one piece"",""kind"":""ANIME"",""limit"":2}`nsalir" | python -m src.host_openai
```

---

## Solución de problemas

* **No aparecen las tools** → confirma instalación:

  ```bash
  pip show anime-helper
  ```

  y la entrada en `mcp.config.json`.

* **429/5xx** → reintenta; el server implementa backoff. Baja `limit` si persiste.

* **Sin Internet** → AniList/Jikan requieren red.

---

## Versionado

* El paquete declara versión en `pyproject.toml` y `about()` la expone.
* Publica tags (ej. `v0.1.0`) y recomienda instalar por tag:

  ```bash
  pip install -U --no-cache-dir git+https://github.com/Ctribsz/AnimeHelper-MCP.git@v0.1.0
  ```
* Crear/actualizar tag:

  ```bash
  git add -A
  git commit -m "chore: bump version"
  git tag -a v0.1.1 -m "Release v0.1.1"
  git push origin main --tags
  ```

---

## Licencia

MIT (ver `LICENSE`).