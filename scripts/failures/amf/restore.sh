#!/usr/bin/env bash
# WMN 5G Core Chaos Script - Restore AMF Failure
set -e
NAMESPACE="open5gs"
echo "Restoring AMF Control Plane (removing iptables DROP)..."

AMF=$(kubectl get pods -n $NAMESPACE -l app=open5gs,nf=amf -o jsonpath='{.items[0].metadata.name}')
if [ -n "$AMF" ]; then
    kubectl exec -n $NAMESPACE $AMF -c amf -- iptables -D INPUT -p sctp -m comment --comment "AMF_SCTP_DROP" -j DROP || true
    kubectl exec -n $NAMESPACE $AMF -c amf -- iptables -D OUTPUT -p sctp -m comment --comment "AMF_SCTP_DROP" -j DROP || true
fi

# Fallback in case it was previously scaled to 0
kubectl scale deployment open5gs-amf -n $NAMESPACE --replicas=1

echo "AMF Control Plane restored."
