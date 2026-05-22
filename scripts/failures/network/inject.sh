#!/usr/bin/env bash
# WMN 5G Core Chaos Script - Inject Network Chaos on gNB
set -e
NAMESPACE="open5gs"

echo "Finding ueransim-gnb pod..."
GNB_POD=$(kubectl get pods -n $NAMESPACE -l app=ueransim,component=gnb -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

if [ -z "$GNB_POD" ]; then
    echo "Error: ueransim-gnb pod not found!"
    exit 1
fi

echo "GNB Pod: $GNB_POD"
echo "Injecting packet delay (200ms) and loss (20%) on N3 interface inside gNB pod..."
kubectl exec -n $NAMESPACE $GNB_POD -c gnb -- tc qdisc add dev n3 root netem delay 200ms loss 20%
echo "Network chaos injected."
