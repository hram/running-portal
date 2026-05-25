# Coolify Deployment

Production runs from Git, not from the local development checkout.

## Source

- Repository: `https://github.com/hram/running-portal.git`
- Branch: `main`
- Build pack: Dockerfile
- Port: `8000`
- URL: `http://running-portal.192.168.1.72.sslip.io`

## Persistent Data

Current prepared host path on `dev-server`:

```text
/srv/running-portal/data
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
HOME=/data/running-portal
CLAUDE_CLI_PATH=/usr/local/bin/claude
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
/srv/running-portal/data
```

Original copy command:

```bash
rsync -a --delete /home/hram/.running_portal/ hram@192.168.1.72:/tmp/running-portal-data/
ssh hram@192.168.1.72 'sudo rsync -a --delete /tmp/running-portal-data/ /srv/running-portal/data/'
```

Use the prepared host path as the Coolify persistent storage source.

## Current Status

- Coolify application UUID: `i13x51t3ujxxdr8iu02x9ogg`
- Coolify API token name: `running-portal-deploy`
- Coolify API token file on `dev-server`: `/home/hram/secrets/coolify/running-portal-deploy.token`
- Latest verified deployment commit: `fc140ad`
- Container status after deploy: healthy.
- Mi Fitness auth state was present after deploy.
- Claude Code is installed inside the Docker image.
- Claude auth for production is stored in `/srv/running-portal/data/.claude` on `dev-server`.

## Notes

- Do not commit `.env`, `auth.json`, `portal.db`, or cache files.
- Do not commit Claude auth files from `/srv/running-portal/data/.claude`.
