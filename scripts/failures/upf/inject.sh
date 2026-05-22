#!/usr/bin/env bash
# WMN 5G Core Chaos Script - Inject UPF Data Plane Failure
set -e
NAMESPACE="open5gs"
echo "Injecting UPF User Plane data drop (iptables FORWARD DROP)..."

UPF1=$(kubectl get pods -n $NAMESPACE -l app=open5gs,name=upf1,nf=upf -o jsonpath='{.items[0].metadata.name}')
UPF2=$(kubectl get pods -n $NAMESPACE -l app=open5gs,name=upf2,nf=upf -o jsonpath='{.items[0].metadata.name}')

if [ -n "$UPF1" ]; then
    kubectl exec -n $NAMESPACE $UPF1 -c upf -- iptables -I FORWARD 1 -m comment --comment "DATAPLANE_DROP" -j DROP
fi
if [ -n "$UPF2" ]; then
    kubectl exec -n $NAMESPACE $UPF2 -c upf -- iptables -I FORWARD 1 -m comment --comment "DATAPLANE_DROP" -j DROP
fi

echo "UPF Data Plane packets are now being dropped by iptables. The pods remain running."
