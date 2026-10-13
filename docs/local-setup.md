# Local setup (macOS)

Default: Homebrew services. Docker is optional (see the end).

## 1. Toolchain
- [uv](https://docs.astral.sh/uv/) (Python 3.12 is installed by uv from `.python-version`)
- Node 22 (`.nvmrc`) and pnpm 10
- Homebrew

```bash
make sync                      # uv sync --all-packages + pnpm install
uv run pre-commit install
cp .env.example .env           # local dev values work as-is
```

## 2. Postgres 16 and Redis (Homebrew)

```bash
brew install postgresql@16 redis
brew services start postgresql@16
brew services start redis
```

Provision roles and databases (idempotent, safe to re-run):

```bash
/opt/homebrew/opt/postgresql@16/bin/psql -v ON_ERROR_STOP=1 -d postgres -f scripts/db/init.sql
```

| Database | Purpose |
| --- | --- |
| `vp_dev` | local development |
| `vp_test` | automated tests (tenant-isolation tests); never point dev at it |

| Role | Attributes | Used by |
| --- | --- | --- |
| `vp_migrator` | login, owns both databases and all tables, no superuser | Alembic only (`MIGRATION_DATABASE_URL`) |
| `vp_app` | login, **not superuser, not owner, NOBYPASSRLS**, DML only via default privileges | API and workers (`DATABASE_URL`) |
| `vp_resolver` | **no login**, BYPASSRLS; `vp_migrator` may `SET ROLE` to it (no inheritance) | owns the narrow resolver functions only (decision 0005) |

Why two roles: superusers and table owners bypass row-level security. The app must connect as a
role that is neither, or RLS (decision 0002) silently does nothing. Owner-bypass is closed separately
with `FORCE ROW LEVEL SECURITY` on tenant tables.

### Require passwords over TCP (recommended)
Homebrew's `initdb` trusts every local connection, so any password works and a wrong
`DATABASE_URL` would go unnoticed. Switch TCP connections to password auth. Unix-socket access
stays `trust`, so admin `psql` keeps working.

```bash
sed -i '' -E '/^host[[:space:]]/ s/[[:space:]]trust$/ scram-sha-256/' /opt/homebrew/var/postgresql@16/pg_hba.conf
```

```bash
/opt/homebrew/opt/postgresql@16/bin/psql -d postgres -c 'select pg_reload_conf()'
```

### Check
```bash
/opt/homebrew/opt/postgresql@16/bin/psql "postgresql://vp_app:vp_app_local_dev@localhost:5432/vp_dev" -c 'select current_user'
```

```bash
redis-cli ping
```

```bash
cd api && uv run alembic current
```

## 3. Run
See "Commands" in `CLAUDE.md`. The dashboard reads `API_URL` (put it in `dashboard/.env.local`;
defaults to `http://localhost:8000`).

## Optional: Docker
`docker compose up -d` starts Postgres 16 and Redis 7 with the same databases and roles
(`scripts/db/init.sql` runs on first start), so the same `.env` works. Stop the brew services
first: they use the same ports.
