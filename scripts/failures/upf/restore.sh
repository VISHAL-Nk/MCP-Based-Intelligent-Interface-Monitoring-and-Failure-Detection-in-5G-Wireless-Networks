#!/usr/bin/env bash
# WMN 5G Core Chaos Script - Restore UPF Data Plane Failure
set -e
NAMESPACE="open5gs"
echo "Restoring UPF User Plane (removing iptables DROP)..."

UPF1=$(kubectl get pods -n $NAMESPACE -l app=open5gs,name=upf1,nf=upf -o jsonpath='{.items[0].metadata.name}')
UPF2=$(kubectl get pods -n $NAMESPACE -l app=open5gs,name=upf2,nf=upf -o jsonpath='{.items[0].metadata.name}')

if [ -n "$UPF1" ]; then
    kubectl exec -n $NAMESPACE $UPF1 -c upf -- iptables -D FORWARD -m comment --comment "DATAPLANE_DROP" -j DROP || true
fi
if [ -n "$UPF2" ]; then
    kubectl exec -n $NAMESPACE $UPF2 -c upf -- iptables -D FORWARD -m comment --comment "DATAPLANE_DROP" -j DROP || true
fi

# In case they were scaled to 0 previously by the old script
kubectl scale deployment open5gs-upf1 -n $NAMESPACE --replicas=1
kubectl scale deployment open5gs-upf2 -n $NAMESPACE --replicas=1

echo "UPF Data Plane restored."
