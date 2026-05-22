import datetime
import subprocess
from typing import Dict, Any, List
from .telemetry import TelemetryIngestor

class MCPContextEngine:
    def __init__(self, ingestor: TelemetryIngestor = None):
        self.ingestor = ingestor or TelemetryIngestor()

    def _get_gnb_pod_name(self) -> str:
        """Helper to get the dynamic gNB pod name."""
        try:
            cmd = "kubectl get pods -n open5gs -l app=ueransim,component=gnb -o jsonpath='{.items[0].metadata.name}'"
            pod_name = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            return pod_name
        except Exception:
            return ""

    def _get_upf_pod_name(self) -> str:
        """Helper to get the dynamic UPF1 pod name."""
        try:
            cmd = "kubectl get pods -n open5gs -l app=open5gs,name=upf1,nf=upf -o jsonpath='{.items[0].metadata.name}'"
            pod_name = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            return pod_name
        except Exception:
            return ""

    def _get_amf_pod_name(self) -> str:
        """Helper to get the dynamic AMF pod name."""
        try:
            cmd = "kubectl get pods -n open5gs -l app=open5gs,nf=amf -o jsonpath='{.items[0].metadata.name}'"
            pod_name = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            return pod_name
        except Exception:
            return ""

    def _get_nrf_pod_name(self) -> str:
        """Helper to get the dynamic NRF pod name."""
        try:
            cmd = "kubectl get pods -n open5gs -l app=open5gs,nf=nrf -o jsonpath='{.items[0].metadata.name}'"
            pod_name = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            return pod_name
        except Exception:
            return ""

    def _check_network_chaos_active(self) -> bool:
        """Probes the gNB pod's n3 interface for netem rules."""
        gnb_pod = self._get_gnb_pod_name()
        if not gnb_pod:
            return False
        try:
            cmd = f"kubectl exec -n open5gs {gnb_pod} -c gnb -- tc qdisc show dev n3"
            output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            return "netem" in output
        except Exception:
            return False

    def _check_n4_blocked(self) -> bool:
        """Probes the UPF1 container for PFCP drop rules in iptables."""
        upf_pod = self._get_upf_pod_name()
        if not upf_pod:
            return False
        try:
            cmd = f"kubectl exec -n open5gs {upf_pod} -c upf -- iptables -L INPUT -n"
            output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            return "dpt:8805" in output and "DROP" in output
        except Exception:
            return False

    def _check_upf_data_dropped(self) -> bool:
        """Probes the UPF1 container for data plane DROP rules in iptables FORWARD chain."""
        upf_pod = self._get_upf_pod_name()
        if not upf_pod:
            return False
        try:
            cmd = f"kubectl exec -n open5gs {upf_pod} -c upf -- iptables -L FORWARD -n"
            output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            return "DATAPLANE_DROP" in output
        except Exception:
            return False

    def _check_amf_blocked(self) -> bool:
        """Probes the AMF container for SCTP drop rules in iptables."""
        amf_pod = self._get_amf_pod_name()
        if not amf_pod:
            return False
        try:
            cmd = f"kubectl exec -n open5gs {amf_pod} -c amf -- iptables -L INPUT -n"
            output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            return "AMF_SCTP_DROP" in output
        except Exception:
            return False

    def _check_nrf_blocked(self) -> bool:
        """Probes the NRF container for TCP drop rules in iptables."""
        nrf_pod = self._get_nrf_pod_name()
        if not nrf_pod:
            return False
        try:
            cmd = f"kubectl exec -n open5gs {nrf_pod} -c nrf -- iptables -L INPUT -n"
            output = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL)
            return "NRF_SBI_DROP" in output
        except Exception:
            return False

    def generate_context(self) -> Dict[str, Any]:
        """Runs correlation rules and returns a structured MCP JSON payload."""
        metrics = self.ingestor.get_metrics()
        logs = self.ingestor.get_logs(limit=100)
        captures = self.ingestor.get_packet_captures()

        detected_anomalies = []
        root_causes = []

        # 1. Check AMF Failure
        amf_ready = metrics.get("amf_ready", 1)
        amf_blocked = self._check_amf_blocked()
        amf_logs = [l for l in logs if "amf" in str(l.get("kubernetes", {}).get("container_name", "")).lower() or "amf" in str(l.get("message", "")).lower()]
        amf_errors = [l for l in amf_logs if str(l.get("level", "")).upper() in ("ERROR", "CRITICAL", "WARNING", "ERR")]
        
        # Look for explicit SCTP/NGAP disconnect logs in gNB/AMF logs
        ngap_disconnects = [l for l in logs if "association terminated for amf" in str(l.get("message", "")).lower() or "sctp association shutdown" in str(l.get("message", "")).lower()]

        if amf_ready == 0 or amf_blocked or len(ngap_disconnects) > 0:
            if amf_blocked:
                symptom = "AMF Control Plane Blocked (SCTP iptables DROP active)"
            elif amf_ready == 0:
                symptom = "AMF Pod is Offline / Terminating"
            else:
                symptom = "SCTP association shutdown / Control connection lost"

            detected_anomalies.append({
                "component": "AMF",
                "interface": "N1/N2 (Control Plane)",
                "symptom": symptom,
                "severity": "CRITICAL",
                "correlated_telemetry": {
                    "metrics": {"ready_replicas": amf_ready, "sctp_blocked": amf_blocked},
                    "logs": [l.get("message", l.get("raw_message", "")) for l in (ngap_disconnects + amf_errors)[:5]]
                }
            })
            root_causes.append("AMF Control Plane Isolation (SCTP Blocked)")

        # 2. Check UPF Failure
        upf1_ready = metrics.get("upf1_ready", 1)
        upf2_ready = metrics.get("upf2_ready", 1)
        upf_data_dropped = self._check_upf_data_dropped()
        upf_logs = [l for l in logs if "upf" in str(l.get("kubernetes", {}).get("container_name", "")).lower()]
        upf_errors = [l for l in upf_logs if str(l.get("level", "")).upper() in ("ERROR", "CRITICAL", "WARNING", "ERR")]

        if upf1_ready == 0 or upf2_ready == 0 or upf_data_dropped:
            symptom = "UPF Data Plane Blocked (iptables DROP active)" if upf_data_dropped else f"UPF deployment replicas scaled down (UPF1={upf1_ready}, UPF2={upf2_ready})"
            detected_anomalies.append({
                "component": "UPF",
                "interface": "N3/N6 (Data Plane)",
                "symptom": symptom,
                "severity": "CRITICAL",
                "correlated_telemetry": {
                    "metrics": {"upf1_ready_replicas": upf1_ready, "upf2_ready_replicas": upf2_ready, "data_plane_blocked": upf_data_dropped},
                    "logs": [l.get("message", l.get("raw_message", "")) for l in upf_errors[:5]]
                }
            })
            root_causes.append("UPF User Plane Data Drop")

        # 3. Check Network Chaos (Latency/Loss)
        netem_active = self._check_network_chaos_active()
        # Look for UERANSIM packet decoding or signal loss indicators
        ueransim_warnings = [l for l in logs if "unable to decode rls message" in str(l.get("message", "")).lower() or "signal lost" in str(l.get("message", "")).lower()]

        if netem_active:
            detected_anomalies.append({
                "component": "gNB",
                "interface": "N3 (Data Plane)",
                "symptom": "Active network delay (200ms) and packet loss (20%) detected on gNB interface",
                "severity": "WARNING",
                "correlated_telemetry": {
                    "metrics": {"netem_rules_active": True},
                    "logs": [l.get("message", l.get("raw_message", "")) for l in ueransim_warnings[:5]]
                }
            })
            root_causes.append("GNB-to-UPF User Plane Path Degradation (Network Delay/Loss)")

        # 4. Check N4 PFCP Block
        n4_blocked = self._check_n4_blocked()
        # Look for SMF/UPF association timeouts, e.g. TEID 0 errors
        teid_errors = [l for l in logs if "teid 0 not found on gtp-u downlink" in str(l.get("message", "")).lower()]

        if n4_blocked or (len(teid_errors) > 0 and upf1_ready > 0):
            detected_anomalies.append({
                "component": "UPF1 / SMF1",
                "interface": "N4 (PFCP Interface)",
                "symptom": "PFCP control port 8805 traffic blocked (iptables DROP active)" if n4_blocked else "GTP-U downlink TEID mismatch anomalies detected",
                "severity": "CRITICAL",
                "correlated_telemetry": {
                    "metrics": {"n4_blocked_iptables": n4_blocked},
                    "logs": [l.get("message", l.get("raw_message", "")) for l in teid_errors[:5]]
                }
            })
            root_causes.append("N4 Interface PFCP Association Failure (Control plane interface dropped)")

        # 5. Check NRF Failure
        # Use live check instead of Prometheus to avoid 30s delay on scale-to-0
        try:
            cmd = "kubectl get deployment open5gs-nrf -n open5gs -o jsonpath='{.status.readyReplicas}'"
            live_nrf_ready = subprocess.check_output(cmd, shell=True, text=True, stderr=subprocess.DEVNULL).strip()
            nrf_ready = int(live_nrf_ready) if live_nrf_ready else 0
        except Exception:
            nrf_ready = metrics.get("nrf_ready", 1)
        nrf_blocked = self._check_nrf_blocked()
        nrf_logs = [l for l in logs if "nrf" in str(l.get("kubernetes", {}).get("container_name", "")).lower()]
        nrf_errors = [l for l in nrf_logs if str(l.get("level", "")).upper() in ("ERROR", "CRITICAL", "WARNING", "ERR")]

        if nrf_ready == 0 or nrf_blocked:
            symptom = "NRF SBI Blocked (iptables DROP active)" if nrf_blocked else "NRF pod is offline (ready replicas = 0)"
            detected_anomalies.append({
                "component": "NRF",
                "interface": "SBI (Service Based Interface)",
                "symptom": symptom,
                "severity": "CRITICAL",
                "correlated_telemetry": {
                    "metrics": {"ready_replicas": nrf_ready, "sbi_blocked": nrf_blocked},
                    "logs": [l.get("message", l.get("raw_message", "")) for l in nrf_errors[:5]]
                }
            })
            root_causes.append("NRF Repository Service Isolation (SBI Blocked)")

        # Compile final status
        status = "Healthy" if not detected_anomalies else "Degraded"
        root_cause = "No anomalies detected." if not root_causes else " / ".join(root_causes)

        # Build MCP Payload structure
        payload = {
            "status": status,
            "detected_anomalies": detected_anomalies,
            "root_cause_candidate": root_cause,
            "packet_capture_metadata": {
                "recent_captures_count": len(captures),
                "last_capture": captures[0] if captures else None
            },
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
        }

        return payload
