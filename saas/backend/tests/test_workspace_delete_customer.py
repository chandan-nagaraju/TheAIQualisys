from pathlib import Path


def test_workspace_exposes_delete_customer_when_no_parts() -> None:
    backend = Path(__file__).resolve().parents[1] / "app" / "routers" / "workspace.py"
    page = Path(__file__).resolve().parents[2] / "frontend" / "src" / "pages" / "workspace" / "CustomersPage.tsx"
    src = backend.read_text(encoding="utf-8")
    ui = page.read_text(encoding="utf-8")
    assert '@router.delete("/customers/{customer_id}")' in src
    assert "part(s) are still linked" in src
    assert 'method: "DELETE"' in ui
    assert "Delete" in ui
