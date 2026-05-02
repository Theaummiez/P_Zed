# Zedo — assistant local (terminal)

**Zedo** tourne sur ta machine : discussion dans le terminal, **sans API cloud**, pas de quota. Il utilise **[Ollama](https://ollama.com)** pour l’inférence, **SQLite** pour la mémoire, des **Skills** Markdown (comme des instructions projet), et un mode **multi-agent** optionnel.

> **Ancien nom : Jarvis.** La commande `jarvis` reste un alias de `zedo` après installation ; le paquet Python est désormais **`zedo`** (`pip install` → `zedo-local`).

## Pourquoi cette stack

| Élément | Rôle |
|---------|------|
| **Ollama** | Runtime local standard ; modèles quantifiés ; GPU si dispo. |
| **Petits modèles instruct** | `qwen2.5:7b` (défaut), etc. — compromis qualité / RAM. |
| **Résumé glissant** | Mémoire long terme sans renvoyer tout l’historique à chaque tour. |

## Installation

1. **Ollama** : https://ollama.com — `ollama pull qwen2.5:7b` (ou autre modèle).

2. **Projet** :

   ```bash
   cd /path/to/P_Zed
   python -m venv .venv
   source .venv/bin/activate
   pip install -e .
   ```

3. **Lancer** :

   ```bash
   zedo
   # ou (alias)
   jarvis
   # ou
   python -m zedo.cli
   ```

### Skills (instructions perso, style Cursor)

Ajoute des **`Skills/*.md`** sous la **racine workspace** (comme `Docs/`). Contenu injecté dans le contexte système.

- Frontmatter optionnel : `title`, `always: true|false`, `keywords: mot1, mot2`.
- Désactiver : `--no-skills` ou `ZEDO_SKILLS_ENABLED=false`.
- Dossier : `ZEDO_SKILLS_DIR` (défaut `Skills`), taille max `ZEDO_SKILLS_MAX_CHARS`.

Des prompts issus de **[awesome-prompts](https://github.com/ai-boost/awesome-prompts)** sont fournis sous **`Skills/github-awesome-prompts/`** (voir le `README.md` dans ce dossier pour les sources et la licence upstream).

### Options CLI

- `--model` — Modèle Ollama (`ZEDO_MODEL` ou ancien `JARVIS_MODEL`).
- `--multi-agent` — Routeur analyste / rédacteur.
- `--memory` — Chemin SQLite perso (défaut `~/.zedo/memory.db`).
- `--workspace` — Racine du bac à sable fichiers (`ZEDO_WORKSPACE_ROOT`).
- `--no-skills` / `--no-file-tools`

### Fichiers workspace (bac à sable)

Liste / lecture / écriture uniquement **sous** le workspace. Extensions d’écriture typiques : `.md` `.txt` `.html` `.csv` `.json` `.xml` `.css` `.docx` `.pdf` (voir code pour la liste exacte).

### Variables d’environnement (préfixe `ZEDO_`)

Les anciennes variables **`JARVIS_*`** peuvent encore fonctionner pour le modèle (`JARVIS_MODEL`) lors du passage à Zedo ; préfère **`ZEDO_*`** :

```bash
export ZEDO_OLLAMA_HOST=http://127.0.0.1:11434
export ZEDO_MODEL=qwen2.5:7b
export ZEDO_WORKSPACE_ROOT=/chemin/vers/P_Zed
export ZEDO_SKILLS_ENABLED=true
```

### Commandes REPL

`/quit` · `/memory` · `/clear-memory` · `/model <nom>`

### Migration depuis Jarvis

```bash
pip uninstall jarvis-local -y
pip install -e .
```

Si tu avais une mémoire dans `~/.jarvis/memory.db`, copie-la si besoin :

```bash
mkdir -p ~/.zedo && cp ~/.jarvis/memory.db ~/.zedo/memory.db
```

### Prérequis

- Python **3.11+**
- **Ollama** avec au moins un modèle téléchargé
