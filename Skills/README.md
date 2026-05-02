# Skills (instructions pour Zedo)

Les fichiers **`.md`** dans ce dossier sont chargés comme **règles système** additionnelles — même idée que les instructions projet dans Cursor.

## Emplacement

- Par défaut : **`Skills/`** à la racine du workspace (à côté de `zedo/` dans le dépôt, ou à la racine du projet sur ta machine).
- Renommage : variable **`ZEDO_SKILLS_DIR`**.

## Format

### Sans en-tête

Tout le fichier peut être injecté selon les règles de filtrage (`keywords` / `always`).

### En-tête YAML (entre `---`)

```markdown
---
title: Sport et fichiers
always: false
keywords: sport, séance, fichier, docs
---

- Toujours enregistrer les séances sous `Docs/Sport/`.
```

| Champ | Rôle |
|--------|------|
| `title` | Titre du bloc injecté (optionnel). |
| `always: true` | Toujours chargée. |
| `keywords` | Chargée si un mot apparaît dans ton message (virgules). |

Sans `keywords` ni `always: true` → traitée comme **toujours active** (comportement simple).

## Limites

- Troncature par fichier (~12k caractères) et au total (`ZEDO_SKILLS_MAX_CHARS`, défaut 16000).
- Désactiver : **`ZEDO_SKILLS_ENABLED=false`** ou **`zedo --no-skills`**.

Les skills **n’entraînent pas** le modèle : elles ajoutent du contexte pour réduire les erreurs sur ce que tu décris.

## Prompts importés (awesome-prompts)

Voir **`Skills/github-awesome-prompts/README.md`** pour les fichiers copiés depuis [ai-boost/awesome-prompts](https://github.com/ai-boost/awesome-prompts).
