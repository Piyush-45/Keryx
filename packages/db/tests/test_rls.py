import pytest

from vp_db.rls import create_policy, enable_tenant_rls


def test_enable_tenant_rls_statements() -> None:
    assert enable_tenant_rls("agents") == [
        "ALTER TABLE agents ENABLE ROW LEVEL SECURITY",
        "ALTER TABLE agents FORCE ROW LEVEL SECURITY",
        "CREATE POLICY tenant_isolation ON agents FOR ALL"
        " USING (org_id = app_current_org()) WITH CHECK (org_id = app_current_org())",
    ]


@pytest.mark.parametrize("bad", ["agents; DROP TABLE users", "Agents", "a-b", "", "1abc"])
def test_rejects_unsafe_identifiers(bad: str) -> None:
    with pytest.raises(ValueError, match="unsafe SQL identifier"):
        enable_tenant_rls(bad)
    with pytest.raises(ValueError, match="unsafe SQL identifier"):
        create_policy("agents", bad, using="true")
