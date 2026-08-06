"""
Verification Agent - Verifies the Action Agent's work
"""
from datetime import datetime


class VerificationAgent:
    def __init__(self):
        pass
        
    def verify(self, complaint_id: str, decision_result: dict, action_result: dict, complaint_doc: dict) -> dict:
        """
        Verify the Action Agent's work
        """
        verification_result = {
            "status": "pending",
            "checks": [],
            "timestamp": datetime.now().isoformat()
        }
        
        # Check if status is correct
        expected_status = self._get_expected_status(decision_result["decision"])
        status_ok = complaint_doc.get("status") == expected_status
        verification_result["checks"].append({
            "check": "status_updated",
            "passed": status_ok,
            "expected": expected_status,
            "actual": complaint_doc.get("status")
        })
        
        # Check if decision is stored
        decision_ok = "agent_decision" in complaint_doc
        verification_result["checks"].append({
            "check": "decision_stored",
            "passed": decision_ok
        })
        
        # Check if action plan is stored
        action_ok = "agent_action_plan" in complaint_doc
        verification_result["checks"].append({
            "check": "action_plan_stored",
            "passed": action_ok
        })
        
        # Check if assigned team/partner is present if needed
        if decision_result["decision"] in ["bank_escalation", "partner_escalation"]:
            assigned_ok = "assigned_team" in complaint_doc or "partner" in complaint_doc
            verification_result["checks"].append({
                "check": "team_or_partner_assigned",
                "passed": assigned_ok
            })
        
        # Determine overall status
        all_passed = all(check["passed"] for check in verification_result["checks"])
        verification_result["status"] = "verified" if all_passed else "failed"
        
        return verification_result
    
    def _get_expected_status(self, decision: str) -> str:
        """Get the expected complaint status based on the decision"""
        status_map = {
            "auto_resolve": "Resolved",
            "bank_escalation": "Escalated to Bank",
            "partner_escalation": "Forwarded to Partner"
        }
        return status_map.get(decision, "Open")
