import os
import json
from typing import Dict, Any, List

# Define the standard diagnostic template for healthy status
HEALTHY_DIAGNOSIS = {
    "probable_cause": "The 5G core network is fully functional. All control plane (AMF, NRF) and user plane (UPF) deployments have 100% ready replicas, and there are no network path delays, packet drops, or PFCP association blockages active.",
    "affected_interfaces": [],
    "severity": "INFO",
    "impact": "All UEs are successfully registered and transmitting user-plane traffic without degradation. Latency and packet delivery are within optimal baseline parameters.",
    "recommended_actions": [
        {
            "description": "Maintain active monitoring of SBI service notifications and N3 data plane traffic.",
            "command": "echo 'System healthy'"
        }
    ]
}

# Define rule-based fallback expert diagnoses for 5G failure modes
MOCK_DIAGNOSES = {
    "AMF": {
        "probable_cause": "AMF Control Plane Pod Failure. The AMF pod was deleted or crashed, causing the SCTP association to the gNB (on N2 interface) to terminate. While existing user-plane GTP-U sessions may persist temporarily, no new UE registrations or session modification requests can be processed.",
        "affected_interfaces": ["N1 (NAS)", "N2 (NGAP/SCTP)", "SBI (HTTP/2)"],
        "severity": "CRITICAL",
        "impact": "Control plane communication lost. UEs cannot register, authenticate, or establish new sessions. Existing GTP-U sessions are orphaned and will fail upon re-negotiation.",
        "recommended_actions": [
            {
                "description": "Rollout restart the AMF deployment to ensure healthy pod recreation.",
                "command": "./scripts/failures/amf/restore.sh"
            },
            {
                "description": "Restart UERANSIM pods to force fresh SCTP and NAS registration with the new AMF instance.",
                "command": "kubectl delete pod -n open5gs -l app=ueransim"
            }
        ]
    },
    "UPF": {
        "probable_cause": "UPF User Plane Deployment Scale Down. Both UPF1 and UPF2 deployments have been scaled to 0 replicas. The user-plane GTP-U data tunnel is completely severed. The control plane (SMF) is unable to route user data packets.",
        "affected_interfaces": ["N3 (GTP-U)", "N4 (PFCP)", "N6 (Data Out)"],
        "severity": "CRITICAL",
        "impact": "Complete user plane outage. Registered UEs lose all internet and external network connectivity. Pings and user data packets are dropped immediately.",
        "recommended_actions": [
            {
                "description": "Scale UPF deployments back up to 1 replica and wait for rollout completion.",
                "command": "./scripts/failures/upf/restore.sh"
            }
        ]
    },
    "gNB": {
        "probable_cause": "GNB-to-UPF User Plane Path Degradation. High latency (200ms) and packet loss (20%) have been injected into the gNB's N3 interface namespace via netem. This severely degrades user plane throughput and quality of service.",
        "affected_interfaces": ["N3 (GTP-U)"],
        "severity": "WARNING",
        "impact": "Data plane transmission suffers severe lag, jitter, and packet drop. Applications requiring low latency or high reliability (e.g. voice/video streams) will fail or experience degradation.",
        "recommended_actions": [
            {
                "description": "Clear the netem qdisc delay and packet loss rules from the gNB network interface.",
                "command": "./scripts/failures/network/restore.sh"
            }
        ]
    },
    "UPF1 / SMF1": {
        "probable_cause": "N4 Interface PFCP Association Failure. An iptables rule has been applied inside the UPF1 container to DROP incoming UDP port 8805 (PFCP) traffic. This blocks session establishment and heartbeat exchanges between the SMF and UPF.",
        "affected_interfaces": ["N4 (PFCP)"],
        "severity": "CRITICAL",
        "impact": "The SMF cannot associate with the UPF or install session rules. New user sessions fail to activate, and existing sessions cannot be modified or released.",
        "recommended_actions": [
            {
                "description": "Remove the iptables DROP rule on UDP port 8805 inside the UPF1 container to restore PFCP traffic.",
                "command": "./scripts/failures/n4/restore.sh"
            }
        ]
    },
    "NRF": {
        "probable_cause": "NRF Repository Service Failure. The NRF pod is offline (ready replicas = 0). Network functions (AMF, SMF, PCF, UDM) cannot discover each other via the Service Based Architecture (SBI) endpoints.",
        "affected_interfaces": ["SBI (Service Based Interface)"],
        "severity": "CRITICAL",
        "impact": "Complete service discovery failure. New network function registrations fail, preventing any control plane routing or session establishment procedures.",
        "recommended_actions": [
            {
                "description": "Rollout restart the NRF deployment and verify SBI availability.",
                "command": "./scripts/failures/nrf/restore.sh"
            }
        ]
    }
}

class AIClient:
    def __init__(self):
        self.api_key = os.environ.get("OPENAI_API_KEY")
        self.client = None
        if self.api_key:
            try:
                from openai import OpenAI
                self.client = OpenAI(api_key=self.api_key)
            except ImportError:
                self.client = None

    def _generate_prompt(self, mcp_context: Dict[str, Any]) -> str:
        return f"""
        Analyze the following 5G Core Network telemetry context from our Model Context Protocol (MCP) engine:
        
        {json.dumps(mcp_context, indent=2)}
        
        Please perform a Root Cause Analysis (RCA) and return a structured JSON response.
        Ensure the response contains EXACTLY the following keys:
        - "probable_cause": detailed explanation of the network degradation or failure.
        - "affected_interfaces": list of 5G interfaces impacted (e.g., N1/N2, N3, N4, SBI).
        - "severity": severity level ("CRITICAL", "WARNING", "INFO").
        - "impact": real-world impact on UEs and services.
        - "recommended_actions": list of actions, where each action is a dictionary with keys:
            - "description": clear explanation of the recovery step.
            - "command": the exact restoration script/command to execute (e.g., './scripts/failures/amf/restore.sh').
        """

    def diagnose(self, mcp_context: Dict[str, Any]) -> Dict[str, Any]:
        """Diagnoses network health using OpenAI if API key is present, otherwise falls back to expert rules."""
        if not mcp_context.get("detected_anomalies"):
            return HEALTHY_DIAGNOSIS

        # If OpenAI API Key is available, use real AI
        if self.client:
            try:
                system_prompt = (
                    "You are a Senior 5G Core Network Reliability Engineer and automated Root Cause Analysis (RCA) specialist. "
                    "You diagnose failures in Open5GS networks running on Kubernetes and recommend precise mitigation steps. "
                    "You must output valid JSON matching the requested schema."
                )
                
                response = self.client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": self._generate_prompt(mcp_context)}
                    ],
                    response_format={"type": "json_object"},
                    temperature=0.1,
                    max_tokens=800
                )
                
                content = response.choices[0].message.content
                return json.loads(content)
            except Exception as e:
                # Fallback to expert system on API failure
                pass

        # Expert System Fallback
        # Match against the first detected anomaly component
        for anomaly in mcp_context["detected_anomalies"]:
            comp = anomaly.get("component")
            if comp in MOCK_DIAGNOSES:
                return MOCK_DIAGNOSES[comp]
                
        # Default fallback if anomaly component is unrecognized
        return {
            "probable_cause": "An unrecognized network anomaly was detected in telemetry.",
            "affected_interfaces": ["Unknown"],
            "severity": "WARNING",
            "impact": "Potential control or user-plane network degradation.",
            "recommended_actions": [
                {
                    "description": "Heal the entire network components back to healthy baseline.",
                    "command": "./scripts/failures/chaos_menu.sh"
                }
            ]
        }
