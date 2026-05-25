# Coolify Deployment

Production runs from Git, not from the local development checkout.

## Source

- Repository: `https://github.com/hram/running-portal.git`
- Branch: `main`
- Build pack: Dockerfile
- Port: `8000`

## Persistent Data

Current prepared host path on `dev-server`:

```text
/home/hram/services/running-portal/data
```

Mount it inside the container to:

```text
/data/running-portal
```

This directory stores:

- `portal.db`
- `auth.json`
- `fds_cache/`

## Environment Variables

Use `.env.production.example` as the template in Coolify.

Required production paths:

```env
DB_PATH=/data/running-portal/portal.db
MI_FITNESS_STATE_PATH=/data/running-portal/auth.json
MI_FITNESS_CACHE_DIR=/data/running-portal/fds_cache
PORT=8000
```

Optional unattended Mi Fitness re-login:

```env
MI_FITNESS_EMAIL=
MI_FITNESS_PASSWORD=
```

## Initial Data Migration

Current runtime data was copied from the development machine to:

```text
/home/hram/services/running-portal/data
```

Original copy command:

```bash
rsync -a --delete /home/hram/.running_portal/ hram@192.168.1.72:/home/hram/services/running-portal/data/
```

Use the prepared host path as the Coolify persistent storage source.

## Notes

- Do not commit `.env`, `auth.json`, `portal.db`, or cache files.
- AI features currently call `CLAUDE_CLI_PATH`. In Docker production this is not configured yet, so normal portal and sync features can run, but AI actions need a separate production AI decision.
