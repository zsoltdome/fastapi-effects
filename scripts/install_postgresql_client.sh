#!/usr/bin/env bash
set -euo pipefail

readonly POSTGRES_VERSION="${1:-}"
readonly PGDG_KEY_FINGERPRINT="B97B0AFCAA1A47F044F244A07FCC7D46ACCC4CF8"
readonly PGDG_KEY_URL="https://www.postgresql.org/media/keys/ACCC4CF8.asc"
readonly PGDG_REPOSITORY="https://apt.postgresql.org/pub/repos/apt"

case "${POSTGRES_VERSION}" in
  16|18) ;;
  *)
    echo "Expected a supported PostgreSQL major version (16 or 18)." >&2
    exit 2
    ;;
esac

readonly CLIENT_DIR="/usr/lib/postgresql/${POSTGRES_VERSION}/bin"
readonly CLIENT_PACKAGE="postgresql-client-${POSTGRES_VERSION}"

if [[ ! -x "${CLIENT_DIR}/pg_dump" || ! -x "${CLIENT_DIR}/psql" ]]; then
  sudo apt-get update
  if ! apt-cache show "${CLIENT_PACKAGE}" >/dev/null 2>&1; then
    source /etc/os-release
    if [[ "${ID:-}" != "ubuntu" || ! "${VERSION_CODENAME:-}" =~ ^[a-z]+$ ]]; then
      echo "The PostgreSQL Apt repository requires a supported Ubuntu runner." >&2
      exit 1
    fi

    key_file="$(mktemp)"
    trap 'rm -f "${key_file}"' EXIT
    curl --fail --location --silent --show-error "${PGDG_KEY_URL}" --output "${key_file}"
    key_fingerprint="$(
      gpg --batch --show-keys --with-colons "${key_file}" 2>/dev/null \
        | awk -F: '$1 == "fpr" { print $10; exit }'
    )"
    if [[ "${key_fingerprint}" != "${PGDG_KEY_FINGERPRINT}" ]]; then
      echo "The PostgreSQL Apt repository signing key fingerprint is invalid." >&2
      exit 1
    fi

    readonly KEYRING_DIR="/usr/share/postgresql-common/pgdg"
    readonly KEYRING_PATH="${KEYRING_DIR}/apt.postgresql.org.asc"
    readonly ARCHITECTURE="$(dpkg --print-architecture)"
    sudo install -d -m 0755 "${KEYRING_DIR}"
    sudo install -m 0644 "${key_file}" "${KEYRING_PATH}"
    printf '%s\n' \
      "Types: deb" \
      "URIs: ${PGDG_REPOSITORY}" \
      "Suites: ${VERSION_CODENAME}-pgdg" \
      "Architectures: ${ARCHITECTURE}" \
      "Components: main" \
      "Signed-By: ${KEYRING_PATH}" \
      | sudo tee /etc/apt/sources.list.d/pgdg.sources >/dev/null
    sudo apt-get update
  fi
  sudo apt-get install --yes --no-install-recommends "${CLIENT_PACKAGE}"
fi

test -x "${CLIENT_DIR}/pg_dump"
test -x "${CLIENT_DIR}/psql"
client_version="$("${CLIENT_DIR}/pg_dump" --version)"
if [[ "${client_version}" != "pg_dump (PostgreSQL) ${POSTGRES_VERSION}"* ]]; then
  echo "Unexpected PostgreSQL client version: ${client_version}" >&2
  exit 1
fi
echo "Using ${client_version} from ${CLIENT_DIR}."
printf '%s\n' "${CLIENT_DIR}" >> "${GITHUB_PATH:?GITHUB_PATH is required}"
