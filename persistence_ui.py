"""Small Streamlit wrapper; session state remains a working preview only."""

import json

import streamlit as st

from investigations import InvestigationService
from persistence import MongoStore


@st.cache_resource
def get_service():
    return InvestigationService(MongoStore.from_env())


def persistence_panel(report=None, signature=None, context=None):
    with st.expander("Saved investigations · MongoDB", expanded=report is None):
        st.caption("Save an evidence snapshot, reopen it after a restart, and track human follow-up. "
                   "Saving does not run an AI agent or make an insurance decision.")
        try:
            service = get_service()
        except Exception:
            st.warning("Persistence unavailable. Set MONGODB_URI and MONGODB_DATABASE and check MongoDB connectivity. "
                       "The current preview is not saved. Credentials are never displayed here.")
            return

        try:
            if report is not None and st.button("Save evidence package to MongoDB", disabled=not report["claim_id"].strip()):
                saved_id = service.save_package(report, signature, context)
                st.session_state["saved_investigation_id"] = saved_id
                st.success("Evidence package persisted. Repeated saves of the same inputs reuse this investigation.")
            rows = service.store.list_investigations()
            if not rows:
                st.info("No saved investigations yet.")
                return
            labels = {row["_id"]: f"{row['claim_id']} · {row['status']} · {row['_id'][:8]}" for row in rows}
            keys = list(labels)
            previous = st.session_state.get("saved_investigation_id")
            selected = st.selectbox("Saved investigation", keys,
                                    index=keys.index(previous) if previous in keys else 0,
                                    format_func=labels.get)
            package = service.load_package(selected)
            record = package["investigation"]
            st.write(f"Status: **{record['status']}**")
            st.caption("This saved snapshot is independent of the current claim form. "
                       "Original uploaded files must be supplied again to rerun GIS calculations.")
            if not record["persistence_complete"]:
                st.warning("Save is incomplete. Re-save the same evidence package to resume safely.")
            if package["report"]:
                st.download_button("Download saved report JSON", json.dumps(package["report"], indent=2),
                                   file_name=f"{record['claim_id']}-saved.json", mime="application/json")
                st.json(package["report"], expanded=False)
            st.write(f"{len(package['evidence'])} evidence records · {len(package['actions'])} recorded actions")
            st.json(package["actions"], expanded=False)
            st.json(record["transitions"], expanded=False)
            for task in package["tasks"]:
                st.write(f"**{task['status']} — {task['title']}**")
                st.caption(task["reason"])
                if task["status"] == "RESOLVED":
                    st.caption(f"Resolution: {task['resolution']}")
                if task["status"] == "OPEN":
                    resolution = st.text_input("Resolution note", key=f"resolution-{task['_id']}")
                    if st.button("Resolve task", key=f"resolve-{task['_id']}"):
                        service.resolve_follow_up_task(selected, task["_id"], resolution)
                        st.rerun()
            with st.form("new-follow-up"):
                title = st.text_input("Follow-up task")
                reason = st.text_input("Evidence needed / reason")
                if st.form_submit_button("Create follow-up task"):
                    service.create_follow_up_task(selected, title, reason)
                    st.session_state["saved_investigation_id"] = selected
                    st.rerun()
            if st.button("Mark Ready for Adjuster Review"):
                service.set_case_status(selected, "READY_FOR_ADJUSTER_REVIEW",
                                        "Human marked evidence package ready for review")
                st.session_state["saved_investigation_id"] = selected
                st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception:
            st.error("MongoDB operation failed. The save may be incomplete; retry the same package when connectivity returns.")
