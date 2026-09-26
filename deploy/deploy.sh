#!/usr/bin/env bash
set -euo pipefail

revision=${1:?Usage: deploy.sh REVISION}
[[ $revision =~ ^[0-9a-f]{40}$ ]] || { echo "Invalid revision" >&2; exit 2; }

base=/opt/littora
archive="$base/incoming/$revision.tar.gz"
release="$base/releases/$revision"
[[ -f $archive ]] || { echo "Missing archive: $archive" >&2; exit 1; }

exec 9>"$base/deploy.lock"
flock -x 9

mkdir -p "$release"
tar -xzf "$archive" -C "$release" --no-same-owner
ln -sfn "$base/shared/.env" "$release/.env"
cd "$release"

docker compose config --quiet
docker compose build --pull
docker compose up -d --wait --remove-orphans

curl --fail --silent --show-error --max-time 20 http://127.0.0.1/ -o /dev/null
curl --fail --silent --show-error --max-time 20 http://127.0.0.1/api/v1/health \
  | python3 -c 'import json,sys; assert json.load(sys.stdin)["status"] == "ok"'

printf '%s\n' "$revision" > "$base/deployed-revision"
ln -sfn "$release" "$base/current"
rm -f "$archive"

# Keep the current and previous release for inspection or rollback.
find "$base/releases" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
  | sort -nr | tail -n +3 | cut -d' ' -f2- | xargs -r rm -rf --
docker image prune -f >/dev/null
echo "Deployed $revision"
