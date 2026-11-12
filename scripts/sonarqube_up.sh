#!/bin/bash
# Starts the local SonarQube server in WSL's Docker (creating the container on
# first use), waits until it reports UP, and makes sure the SnapSolve project
# uses the SnapSolve quality gate (needs SONAR_TOKEN).
set -euo pipefail

IMAGE=sonarqube:26.10.0.133078-community
URL=http://localhost:9000
PROJECT=SnapSolve
GATE=SnapSolve

if docker container inspect sonarqube >/dev/null 2>&1; then
    docker start sonarqube >/dev/null
else
    # allow_mmap=false: WSL's default vm.max_map_count is too low for the
    # embedded Elasticsearch, which otherwise refuses to start.
    docker run -d --name sonarqube -p 9000:9000 \
        -e SONAR_SEARCH_JAVAADDITIONALOPTS="-Dnode.store.allow_mmap=false" \
        -v sonarqube_data:/opt/sonarqube/data \
        -v sonarqube_extensions:/opt/sonarqube/extensions \
        -v sonarqube_logs:/opt/sonarqube/logs \
        "$IMAGE" >/dev/null
    echo "Created the SonarQube container ($IMAGE)."
    echo "First run: open $URL, log in as admin/admin, set a new password,"
    echo "create a user token, and store it in the SONAR_TOKEN environment variable."
fi

status=""
for _ in $(seq 1 90); do
    # curl fails (connection refused) until the web server listens; under
    # `set -e -o pipefail` that must not end the script.
    status=$(curl -s -m 2 "$URL/api/system/status" | sed -n 's/.*"status":"\([A-Z_]*\)".*/\1/p' || true)
    [ "$status" = "UP" ] && break
    sleep 2
done
if [ "$status" != "UP" ]; then
    echo "SonarQube did not come up within 3 minutes (last status: ${status:-none})." >&2
    exit 1
fi
echo "SonarQube is up."

# Quality gate: SonarQube's "Sonar way" without its 80% coverage-on-new-code
# condition. No coverage report is sent (the unit tests cover the core logic,
# not the Qt UI), so that condition could never pass.
if [ -z "${SONAR_TOKEN:-}" ]; then
    echo "SONAR_TOKEN is not set; skipping the quality gate setup." >&2
    exit 0
fi
api() { curl -sf -u "$SONAR_TOKEN:" "$@"; }
if ! api "$URL/api/qualitygates/show?name=$GATE" >/dev/null; then
    api -X POST "$URL/api/qualitygates/create" -d "name=$GATE" >/dev/null
    echo "Created the $GATE quality gate."
fi
# A new gate starts with SonarQube's default conditions, coverage included.
gate=$(api "$URL/api/qualitygates/show?name=$GATE")
conditions() {  # prints "<metric> <id>" per condition
    python3 -c 'import json, sys
for c in json.load(sys.stdin)["conditions"]: print(c["metric"], c["id"])' <<<"$gate"
}
for id in $(conditions | awk '$1 == "new_coverage" {print $2}'); do
    api -X POST "$URL/api/qualitygates/delete_condition" -d "id=$id" >/dev/null
done
for condition in "new_violations GT 0" "new_duplicated_lines_density GT 3" \
    "new_security_hotspots_reviewed LT 100"; do
    read -r metric op error <<<"$condition"
    conditions | awk -v m="$metric" '$1 == m {found=1} END {exit !found}' && continue
    api -X POST "$URL/api/qualitygates/create_condition" -d "gateName=$GATE" \
        -d "metric=$metric" -d "op=$op" -d "error=$error" >/dev/null
done
# The project exists after its first scan; create it so the gate applies to that scan too.
api "$URL/api/projects/search?projects=$PROJECT" | grep -q "\"key\":\"$PROJECT\"" \
    || api -X POST "$URL/api/projects/create" -d "project=$PROJECT" -d "name=$PROJECT" >/dev/null
api -X POST "$URL/api/qualitygates/select" -d "gateName=$GATE" -d "projectKey=$PROJECT" >/dev/null
