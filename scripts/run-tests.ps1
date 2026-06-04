<#
.SYNOPSIS
  Run the full backend quality gate locally - the same checks CI runs:
  ruff (lint gate), pytest (against a REAL PostgreSQL 16), and the alembic
  migration round-trip. Mypy is run informationally (not a gate yet).

.DESCRIPTION
  Runs everything in a DISPOSABLE container ("ats-test-runner") built from the
  same backend image, attached to the compose network so it can reach the
  running "ats-postgres". It NEVER touches the live "ats-backend" container,
  so running tests can't disturb your dev stack.

  We copy the current source into the disposable runner (the OneDrive project
  path isn't reliably shared with Docker Desktop for bind mounts), point it at
  a throwaway "ats_test" database, run the gates, then remove the runner.

  Prerequisite: the stack is up so "ats-postgres" exists, e.g.
    docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

.EXAMPLE
  ./backend/scripts/run-tests.ps1
  ./backend/scripts/run-tests.ps1 -PytestArgs "tests/test_jobs.py -k publish -vv"
#>
param(
  [string]$PytestArgs = "-q",
  [switch]$SkipMigrationRoundtrip
)

# We gate on $LASTEXITCODE explicitly; do NOT set ErrorActionPreference=Stop,
# because native tools write progress to stderr which PS 5.1 would treat as
# terminating errors.

$BackendDir = Split-Path -Parent $PSScriptRoot
$Postgres = "ats-postgres"
$Runner   = "ats-test-runner"
$TestUrl  = "postgresql+asyncpg://postgres:password@postgres:5432/ats_test"
$failed = $false

# Resolve the backend image id and the docker network from the live stack
# (works even if ats-backend is restarting).
$Img = (docker inspect -f '{{.Image}}' ats-backend).Trim()
$Net = (docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}{{end}}' $Postgres).Trim()
if (-not $Img -or -not $Net) {
  Write-Host "Could not resolve backend image / network. Is the stack up?" -ForegroundColor Red
  exit 1
}

try {
  Write-Host "==> Ensuring test database 'ats_test' exists" -ForegroundColor Cyan
  docker exec $Postgres sh -c "psql -U postgres -tc \`"SELECT 1 FROM pg_database WHERE datname='ats_test'\`" | grep -q 1 || psql -U postgres -c 'CREATE DATABASE ats_test'" 2>&1 | Out-Null

  Write-Host "==> Starting disposable runner ($Runner) from image $Img" -ForegroundColor Cyan
  docker rm -f $Runner 2>$null | Out-Null
  docker run -d --name $Runner --network $Net --entrypoint sleep $Img infinity | Out-Null

  Write-Host "==> Copying current source into runner" -ForegroundColor Cyan
  # Trailing-slash dest (an existing dir) => each item lands at /app/<name>; no nesting.
  docker cp "$BackendDir\app"            "${Runner}:/app/"
  docker cp "$BackendDir\alembic"        "${Runner}:/app/"
  docker cp "$BackendDir\alembic.ini"    "${Runner}:/app/"
  docker cp "$BackendDir\tests"          "${Runner}:/app/"
  docker cp "$BackendDir\pytest.ini"     "${Runner}:/app/"
  docker cp "$BackendDir\pyproject.toml" "${Runner}:/app/"

  Write-Host "==> Installing test/lint deps in runner" -ForegroundColor Cyan
  docker exec $Runner sh -c "pip install -q pytest==8.3.5 pytest-asyncio==0.26.0 'ruff>=0.6,<1.0' 'mypy>=1.11,<2' >/dev/null 2>&1"

  Write-Host "==> RUFF (lint gate)" -ForegroundColor Cyan
  docker exec $Runner sh -c "cd /app; ruff check ."
  if ($LASTEXITCODE -ne 0) { Write-Host "RUFF FAILED" -ForegroundColor Red; $failed = $true }

  Write-Host "==> MYPY (informational, not a gate)" -ForegroundColor Cyan
  docker exec $Runner sh -c "cd /app; mypy app"

  if (-not $failed -and -not $SkipMigrationRoundtrip) {
    Write-Host "==> Migration round-trip (upgrade, downgrade -1, upgrade)" -ForegroundColor Cyan
    docker exec -e DATABASE_URL=$TestUrl -e SECRET_KEY=test -e JWT_SECRET=test $Runner sh -c "cd /app; alembic upgrade head; alembic downgrade -1; alembic upgrade head"
    if ($LASTEXITCODE -ne 0) { Write-Host "MIGRATION ROUND-TRIP FAILED" -ForegroundColor Red; $failed = $true }
  }

  if (-not $failed) {
    Write-Host "==> PYTEST (real PostgreSQL 16)" -ForegroundColor Cyan
    docker exec -e TEST_DATABASE_URL=$TestUrl -e SECRET_KEY=test -e JWT_SECRET=test $Runner sh -c "cd /app; python -m pytest $PytestArgs"
    if ($LASTEXITCODE -ne 0) { Write-Host "PYTEST FAILED" -ForegroundColor Red; $failed = $true }
  }
}
finally {
  Write-Host "==> Removing disposable runner" -ForegroundColor Cyan
  docker rm -f $Runner 2>$null | Out-Null
}

if ($failed) { Write-Host "`nGates FAILED." -ForegroundColor Red; exit 1 }
Write-Host "`nAll gates passed." -ForegroundColor Green
