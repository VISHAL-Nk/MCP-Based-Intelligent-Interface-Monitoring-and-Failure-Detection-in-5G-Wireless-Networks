#!/usr/bin/env bash
# WMN 5G Core Chaos Script - Inject AMF Failure
set -e
NAMESPACE="open5gs"
echo "Injecting AMF Control Plane isolation (iptables DROP on SCTP)..."

AMF=$(kubectl get pods -n $NAMESPACE -l app=open5gs,nf=amf -o jsonpath='{.items[0].metadata.name}')
if [ -n "$AMF" ]; then
    kubectl exec -n $NAMESPACE $AMF -c amf -- iptables -I INPUT -p sctp -m comment --comment "AMF_SCTP_DROP" -j DROP
    kubectl exec -n $NAMESPACE $AMF -c amf -- iptables -I OUTPUT -p sctp -m comment --comment "AMF_SCTP_DROP" -j DROP
fi

echo "AMF SCTP control plane packets are now being dropped by iptables. The pod remains running."
