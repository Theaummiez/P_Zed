# Skills (instructions pour Jarvis)

Les fichiers **`.md`** dans ce dossier sont chargés comme **règles système** additionnelles — même idée que les instructions projet dans Cursor ou les « skills » dans d’autres assistants.

## Emplacement

- Dossier par défaut : **`Skills/`** à la racine du workspace (à côté de `jarvis/`, `Docs/`).
- Tu peux renommer via la variable d’environnement **`JARVIS_SKILLS_DIR`**.

## Format d’un fichier

### Sans en-tête

Tout le fichier est injecté **à chaque message** (utile pour des règles globales).

### Avec en-tête YAML simple (entre `---`)

```markdown
---
title: Sport et fichiers
always: false
keywords: sport, séance, fichier, docs
---

- Toujours enregistrer les séances sous `Docs/Sport/`.
- Utiliser `workspace_write_file` avec un chemin explicite en `.md`.
```

| Champ | Rôle |
|--------|------|
| `title` | Titre affiché dans le bloc injecté (optionnel). |
| `always: true` | Skill **toujours** chargée (ignore `keywords`). |
| `keywords` | Liste séparée par virgules ; la skill s’applique si **au moins** un mot apparaît dans le message utilisateur (insensible à la casse). |

Sans `keywords` ni `always: true`, le fichier est traité comme **toujours actif** (comportement simple pour une seule grosse règle).

## Limites

- Texte tronqué par fichier (~12k caractères) et au total par message (`JARVIS_SKILLS_MAX_CHARS`, défaut 16000).
- Désactiver : **`JARVIS_SKILLS_ENABLED=false`** ou l’option CLI **`--no-skills`**.

Les skills **ne réentraînent pas** le modèle : elles ajoutent du contexte pour réduire les erreurs sur les sujets que tu décris explicitement.
