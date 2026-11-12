# AGENTS.md

Guidance for AI agents working in this repository.

## What this repo is

格雨's personal operating system: versioned templates, scripts, and workflows that glue together Obsidian (long-term knowledge), Notion (projects/tasks), and GitHub (process definitions).

## Conventions

- **No copyrighted material**: `books/` holds metadata and reading protocols only. Never commit EPUB/PDF book files (`.gitignore` already blocks them).
- **Scripts are local tools**: everything in `scripts/` is a small, single-purpose CLI. Keep them dependency-light (stdlib first).
- **Templates are plain markdown**: `templates/` files follow YAML frontmatter + markdown body.
- **Language**: docs and templates in Chinese (owner is a native speaker); code and commit messages in English.

## Commands

```bash
# EPUB metadata
python scripts/epub_metadata.py <book.epub>

# Import EPUB full-text into an Obsidian vault
python scripts/import_epub_fulltext_to_obsidian.py <book.epub> <vault_dir> <slug>
```

## Safety rules

- Do not commit anything under `books/` that isn't metadata or a reading protocol.
- Do not hardcode owner-specific paths (e.g. vault directories); use placeholders.
- Before pushing, verify staged files contain no EPUB/PDF content or key material.
