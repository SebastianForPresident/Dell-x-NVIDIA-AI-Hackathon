"""Bounded business operations shared by Streamlit and future OpenClaw tools."""

import hashlib
import json

from persistence import utcnow


def stable_id(*parts):
    return hashlib.sha256(json.dumps(parts, sort_keys=True, separators=(",", ":"),
                                     allow_nan=False).encode()).hexdigest()


class InvestigationService:
    def __init__(self, store):
        self.store = store

    def get_claim(self, claim_id):
        return self.store.get("claims", claim_id)

    def _investigation(self, investigation_id):
        record = self.store.get("investigations", investigation_id)
        if record is None:
            raise ValueError("Unknown investigation.")
        return record

    def start_investigation(self, metadata, input_signature, context=None):
        claim_id = metadata.get("claim_id", "").strip()
        if not claim_id:
            raise ValueError("A claim ID is required.")
        metadata = {**metadata, "claim_id": claim_id}
        investigation_id = stable_id(claim_id, input_signature)
        now = utcnow()
        self.store.insert_once("claims", {"_id": claim_id, "metadata": metadata,
                                           "created_at": now})
        self.store.insert_once("investigations", {
            "_id": investigation_id, "claim_id": claim_id, "metadata": metadata,
            "input_signature": input_signature, "context": context or {},
            "status": "NEW", "persistence_complete": False,
            "created_at": now, "updated_at": now,
            "transitions": [{"from": None, "to": "NEW", "at": now,
                             "actor": "application", "reason": "Investigation created"}],
        })
        return investigation_id

    def record_action(self, investigation_id, action_key, tool, arguments, result,
                      actor="application"):
        self._investigation(investigation_id)
        key = stable_id(investigation_id, "action", action_key)
        self.store.insert_once("agent_actions", {
            "_id": key, "investigation_id": investigation_id, "tool": tool,
            "arguments": arguments, "result": result, "actor": actor,
            "created_at": utcnow(),
        })
        return key

    def record_evidence(self, investigation_id, finding):
        self._investigation(investigation_id)
        if finding.get("status") not in {"supported", "contradicted", "inconclusive", "unavailable"}:
            raise ValueError("Invalid evidence status.")
        if not all(key in finding for key in ("check", "detail", "source", "values")):
            raise ValueError("Incomplete finding.")
        key = stable_id(investigation_id, "evidence", finding)
        self.store.insert_once("evidence", {"_id": key, "investigation_id": investigation_id,
                                            "finding": finding, "created_at": utcnow()})
        return key

    def create_follow_up_task(self, investigation_id, title, reason, actor="human"):
        self._investigation(investigation_id)
        title, reason = title.strip(), reason.strip()
        if not title or not reason:
            raise ValueError("Task title and reason are required.")
        key = stable_id(investigation_id, "task", title, reason)
        self.store.insert_once("follow_up_tasks", {
            "_id": key, "investigation_id": investigation_id, "title": title,
            "reason": reason, "status": "OPEN", "actor": actor, "created_at": utcnow(),
        })
        self.set_case_status(investigation_id, "NEEDS_EVIDENCE", reason, actor)
        return key

    def set_case_status(self, investigation_id, status, reason, actor="human"):
        if status not in {"INVESTIGATING", "NEEDS_EVIDENCE", "READY_FOR_ADJUSTER_REVIEW"}:
            raise ValueError("Unsupported case status; claim decisions are not allowed.")
        record = self._investigation(investigation_id)
        if status == "READY_FOR_ADJUSTER_REVIEW":
            if not record.get("persistence_complete"):
                raise ValueError("Save a complete evidence package before marking ready.")
            if self.store.db.follow_up_tasks.count_documents({"investigation_id": investigation_id,
                                                              "status": "OPEN"}):
                raise ValueError("Resolve open follow-up tasks before marking ready.")
        if record["status"] == status:
            return
        now = utcnow()
        result = self.store.db.investigations.update_one(
            {"_id": investigation_id, "status": record["status"]},
            {"$set": {"status": status, "updated_at": now},
             "$push": {"transitions": {"from": record["status"], "to": status,
                                         "reason": reason, "actor": actor, "at": now}}})
        if not result.matched_count:
            raise ValueError("Case changed concurrently. Refresh and retry.")

    def resolve_follow_up_task(self, investigation_id, task_id, resolution):
        if not resolution.strip():
            raise ValueError("A resolution note is required.")
        result = self.store.db.follow_up_tasks.update_one(
            {"_id": task_id, "investigation_id": investigation_id, "status": "OPEN"},
            {"$set": {"status": "RESOLVED", "resolution": resolution.strip(),
                      "resolved_at": utcnow()}})
        return bool(result.matched_count)

    def save_report(self, investigation_id, report):
        record = self._investigation(investigation_id)
        if report["claim_id"].strip() != record["claim_id"]:
            raise ValueError("Report belongs to a different claim.")
        key = stable_id(investigation_id, "report", report)
        self.store.insert_once("reports", {"_id": key, "investigation_id": investigation_id,
                                           "report": report, "created_at": utcnow()})
        return key

    def save_package(self, report, input_signature, context=None):
        """Import the existing deterministic analysis. No model decisions are implied.

        Content-derived IDs make interrupted saves retryable. Publish the report
        pointer only after all writes succeed; this is not a multi-document transaction.
        """
        metadata = {key: report[key] for key in
                    ("claim_id", "reported_cause", "reported_loss_date", "field", "synthetic_demo")}
        metadata["claimed_crop"] = (context or {}).get("claimed_crop")
        signature = stable_id(input_signature, report, context or {})
        investigation_id = self.start_investigation(metadata, signature, context)
        record = self._investigation(investigation_id)
        if record["persistence_complete"]:
            return investigation_id
        if record["status"] == "NEW":
            self.set_case_status(investigation_id, "INVESTIGATING", "Importing calculated evidence", "application")
        for finding in report["findings"]:
            evidence_id = self.record_evidence(investigation_id, finding)
            self.record_action(investigation_id, evidence_id, "import_existing_finding",
                               {"check": finding["check"]}, {"evidence_id": evidence_id}, "application")
        report_id = self.save_report(investigation_id, report)
        self.record_action(investigation_id, "save_report", "save_report", {},
                           {"report_id": report_id}, "application")
        self.store.db.investigations.update_one({"_id": investigation_id}, {"$set": {
            "report_id": report_id, "persistence_complete": True, "updated_at": utcnow()}})
        return investigation_id

    def load_package(self, investigation_id):
        record = self._investigation(investigation_id)
        report = self.store.get("reports", record.get("report_id")) if record.get("report_id") else None
        return {"investigation": record, "report": report["report"] if report else None,
                "evidence": self.store.related("evidence", investigation_id),
                "actions": self.store.related("agent_actions", investigation_id),
                "tasks": self.store.related("follow_up_tasks", investigation_id)}
