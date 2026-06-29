from pathlib import Path

from app.persistence import RunStore
from app.schemas import ModelProfileAdaptationProposal, RunLease


def test_store_round_trips_run_state(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")

    run = store.create_run("Check memory first", "Test run", str(tmp_path), ["criterion"])
    run.state.completed_steps.append("Consulted memory")
    updated = store.update_run(run.id, status="running", state=run.state)

    assert updated.status == "running"
    assert updated.state.acceptance_criteria == ["criterion"]
    assert updated.state.acceptance_evidence[0].criterion == "criterion"
    assert updated.state.completed_steps == ["Consulted memory"]


def test_approval_lifecycle(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Needs approval", "Approval run", str(tmp_path), [])

    approval = store.create_approval(run.id, "command", {"command": "winget install demo"}, "global install")
    resolved = store.resolve_approval(approval["id"], "rejected")

    assert resolved["status"] == "rejected"
    assert store.list_approvals(run.id)[0]["status"] == "rejected"


def test_update_run_lease_preserves_latest_state(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    run = store.create_run("Lease update", "Lease update", str(tmp_path), [])
    run.state.completed_steps.append("Milestone completed while heartbeat was pending.")
    store.update_run(run.id, status="running", state=run.state)

    updated = store.update_run_lease(
        run.id,
        RunLease(
            id="lease-test",
            owner_id="engine-test",
            status="active",
            heartbeat_at="2026-06-27T08:00:00+00:00",
            expires_at="2026-06-27T08:01:30+00:00",
        ),
    )

    assert updated.state.completed_steps == ["Milestone completed while heartbeat was pending."]
    assert updated.state.run_lease.id == "lease-test"


def test_model_adaptation_review_ledger_round_trips(tmp_path: Path) -> None:
    store = RunStore(tmp_path / "runs.sqlite3")
    proposal = ModelProfileAdaptationProposal(
        id="proposal-test",
        profile_id="ornith",
        generated_at="2026-06-27T08:00:00+00:00",
        status="needs_confirmation",
        summary="Propose one prompt tuning change.",
    )

    review = store.create_model_adaptation_review(proposal, "accepted", "Looks useful.")

    assert review.profile_id == "ornith"
    assert review.decision == "accepted"
    assert review.proposal.id == "proposal-test"
    assert store.list_model_adaptation_reviews()[0].reviewer_note == "Looks useful."
