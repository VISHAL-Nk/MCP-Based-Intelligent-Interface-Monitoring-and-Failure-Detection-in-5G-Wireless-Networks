#!/usr/bin/env bash
# WMN 5G Core Chaos Script - Restore N4 PFCP Failure
set -e
NAMESPACE="open5gs"

echo "Finding open5gs-upf1 pod..."
UPF_POD=$(kubectl get pods -n $NAMESPACE -l app=open5gs,name=upf1,nf=upf -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

if [ -z "$UPF_POD" ]; then
    echo "Error: open5gs-upf1 pod not found!"
    exit 1
fi

echo "UPF Pod: $UPF_POD"
echo "Restoring N4 (PFCP) by removing iptables drop rule inside UPF pod..."
kubectl exec -n $NAMESPACE $UPF_POD -c upf -- iptables -D INPUT -p udp --dport 8805 -j DROP 2>/dev/null || echo "No drop rule found on INPUT, interface already clean."
kubectl exec -n $NAMESPACE $UPF_POD -c upf -- iptables -D OUTPUT -p udp --sport 8805 -j DROP 2>/dev/null || echo "No drop rule found on OUTPUT, interface already clean."
echo "N4 port 8805 traffic is restored."
