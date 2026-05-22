#!/usr/bin/env bash
# WMN 55 Core Chaos Script - Inject N4 PFCP Failure
set -e
NAMESPACE="open5gs"

echo "Finding open5gs-upf1 pod..."
UPF_POD=$(kubectl get pods -n $NAMESPACE -l app=open5gs,name=upf1,nf=upf -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)

if [ -z "$UPF_POD" ]; then
    echo "Error: open5gs-upf1 pod not found!"
    exit 1
fi

echo "UPF Pod: $UPF_POD"
echo "Injecting N4 (PFCP) drop rule using iptables on UDP port 8805 inside UPF pod..."
kubectl exec -n $NAMESPACE $UPF_POD -c upf -- iptables -A INPUT -p udp --dport 8805 -j DROP
kubectl exec -n $NAMESPACE $UPF_POD -c upf -- iptables -A OUTPUT -p udp --sport 8805 -j DROP
echo "N4 port 8805 traffic is now blocked."
