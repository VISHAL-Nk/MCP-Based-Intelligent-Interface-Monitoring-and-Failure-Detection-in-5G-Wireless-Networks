#!/usr/bin/env bash
# WMN 5G Core Chaos Script - Inject NRF Failure
set -e
NAMESPACE="open5gs"
echo "Injecting NRF Service Registry isolation (iptables DROP on TCP)..."

kubectl scale deployment open5gs-nrf -n $NAMESPACE --replicas=0
echo "NRF Service Registry is now isolated (scaled to 0). Network functions will lose discovery."
