# Production Readiness

Notes for turning Running Portal from a local personal app into a production-level product.

## Security

- Do not store Mi Fitness passwords in plain `.env` files for production use.
- Encrypt persisted Mi Fitness auth state and service tokens.
- Add portal-level authentication and session management.
- Protect API endpoints if the app is exposed beyond localhost.
- Avoid logging credentials, tokens, cookies, or raw auth payloads.
- Separate development and production configuration.

## Multi-user Support

- Add user accounts.
- Store separate Mi Fitness auth state per user.
- Add user ownership to activities, details, sync logs, AI analysis, recommendations, settings, and goals.
- Isolate Telegram chat IDs per user.
- Add access control for every API endpoint.
- Add database migrations for user-scoped data.

## Reliable Sync

- Move sync work out of the HTTP request path.
- Use background jobs with retry and backoff.
- Prevent concurrent sync jobs for the same user.
- Keep sync idempotent so repeated runs do not corrupt data.
- Store clear sync status: queued, running, success, failed, auth required.
- Track the last successful sync per user.
- Surface auth and Mi Fitness API failures in the UI.

## Background Workers

- Replace in-process APScheduler with a persistent worker setup for production.
- Consider Redis plus RQ, Celery, Arq, or Dramatiq.
- Store scheduled jobs persistently.
- Support per-user schedules such as morning sync and evening readiness checks.
- Add job duration, retry count, and failure reason tracking.

## Database

- Move from SQLite to PostgreSQL for production.
- Add Alembic migrations.
- Add indexes for user ID, activity date, sync ID, and activity ID.
- Add backups and restore procedures.
- Decide data retention policy for raw Mi Fitness payloads and AI output.

## AI Layer

- Replace direct Claude CLI subprocess calls with a provider abstraction.
- Use async API clients for AI providers.
- Add retries, timeouts, and clear error handling.
- Cache generated recommendations and activity analyses.
- Track token/cost usage if using paid AI APIs.
- Validate and constrain AI JSON outputs.
- Allow AI features to be disabled per deployment or per user.

## UI/UX

- Add onboarding: connect Mi Fitness, verify auth, run first sync, show first data.
- Add integration status page for Mi Fitness and Telegram.
- Add visible scheduler status and next planned sync time.
- Add settings for schedules, monthly goals, Telegram, and alert thresholds.
- Add history pages for recommendations and sync failures.
- Improve mobile ergonomics.

## Observability

- Add structured logs.
- Add healthcheck endpoint.
- Add metrics for sync success/failure, auth failures, AI failures, job duration, and scheduler runs.
- Add error tracking.
- Add correlation IDs for sync jobs and AI jobs.
- Add an admin/debug view for recent jobs and failures.

## Deployment

- Add Dockerfile.
- Add Docker Compose for app, worker, database, and Redis if needed.
- Add production `.env.example` without secrets.
- Run behind a reverse proxy with HTTPS.
- Define persistent volumes for database, cache, and exports.
- Add backup strategy for database and auth state.

## Privacy And Compliance

- Treat running and health data as sensitive.
- Add privacy policy before sharing beyond trusted private use.
- Clearly explain what data is stored and where.
- Add data export and data deletion.
- Avoid collecting unnecessary raw data.
- Require explicit consent before sending activity data to AI providers.
- Prefer a self-hosted production version before considering hosted SaaS.

## Suggested Path

Start with a self-hosted production version:

- Docker Compose deployment.
- Single-user or small multi-user mode.
- PostgreSQL.
- Background worker.
- Encrypted auth state.
- Telegram integration.
- Basic observability.

This keeps privacy and operational complexity manageable while making the project shareable.
