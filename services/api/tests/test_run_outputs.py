from vic.contracts import ErrorBody, NodeOutput, RoleResult, Run, RunStatus, SectionContent
from vic.storage import get_repository


def test_failed_run_outputs_are_readable_without_a_final_report(client):
    repo = get_repository()
    case_id = client.post("/cases", json={"indication": "Synthetic X",
        "mechanism": "Synthetic Y", "scope": "approach"}).json()["case_id"]
    run = Run(id="run-partial", case_id=case_id, status=RunStatus.FAILED,
              trace_id="trace-partial", error=ErrorBody(code="agent_error", message="Market failed"))
    repo.create_run(run)
    role = RoleResult(role_id="science", summary="Saved science output", position="insufficient_data",
        section_content=[SectionContent(key="scientific_thesis", summary="Saved science output",
            structured_data={"own_analysis": {"gap": "Human evidence missing"},
                             "upstream_context": {"duplicated": "Ancestor output"}})])
    repo.save_node(run.id, NodeOutput(role_id="science", status="completed", attempt=1, result=role))
    repo.save_node(run.id, NodeOutput(role_id="market", status="failed", attempt=1, error=run.error))
    response = client.get(f"/runs/{run.id}/outputs")
    assert response.status_code == 200
    raw = response.json()
    assert raw["case_id"] == case_id and raw["run_id"] == run.id
    nodes = {node["role_id"]: node for node in raw["nodes"]}
    assert nodes["science"]["result"]["summary"] == "Saved science output"
    data = nodes["science"]["result"]["section_content"][0]["structured_data"]
    assert data == {"own_analysis": {"gap": "Human evidence missing"}}
    assert repo.get_nodes(run.id)[0].result.section_content[0].structured_data["upstream_context"]
    assert nodes["market"]["error"]["message"] == "Market failed"
    assert nodes["chair"]["status"] == "not_started"
    assert client.get(f"/cases/{case_id}/reports/1").status_code == 404
    assert client.get("/runs/run-missing/outputs").status_code == 404


def test_outputs_of_interrupted_run_stop_showing_running_nodes(client):
    repo = get_repository()
    case_id = client.post("/cases", json={"indication": "Synthetic X",
        "mechanism": "Synthetic Y", "scope": "approach"}).json()["case_id"]
    run = Run(id="run-interrupted-output", case_id=case_id, status=RunStatus.RUNNING,
              trace_id="trace-interrupted-output")
    repo.create_run(run)
    repo.save_node(run.id, NodeOutput(role_id="market", status="running", attempt=1))
    repo.recover_interrupted_runs()
    raw = client.get(f"/runs/{run.id}/outputs").json()
    market = next(node for node in raw["nodes"] if node["role_id"] == "market")
    assert market["status"] == "interrupted" and market["error"]["code"] == "run_interrupted"
