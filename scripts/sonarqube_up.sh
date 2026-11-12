#!/bin/bash
# Starts the local SonarQube server in WSL's Docker (creating the container on
# first use) and waits until it reports UP.
set -euo pipefail

IMAGE=sonarqube:26.10.0.133078-community

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
    echo "First run: open http://localhost:9000, log in as admin/admin, set a new password,"
    echo "create a project analysis token, and store it in the SONAR_TOKEN environment variable."
fi

for _ in $(seq 1 90); do
    status=$(curl -s -m 2 http://localhost:9000/api/system/status | sed -n 's/.*"status":"\([A-Z_]*\)".*/\1/p')
    if [ "$status" = "UP" ]; then
        echo "SonarQube is up."
        exit 0
    fi
    sleep 2
done
echo "SonarQube did not come up within 3 minutes (last status: ${status:-none})." >&2
exit 1
