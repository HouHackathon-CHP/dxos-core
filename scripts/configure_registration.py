# SPDX-License-Identifier: Apache-2.0
"""Enable local citizen self-registration in an existing DX-OS realm.

The realm import is skipped when Keycloak already has a database. Run this
idempotent setup after `docker compose up` to update that existing realm too.
"""

from smoke import IDENTITY, admin_token, read_env, request, require


def main() -> None:
    admin = admin_token(read_env()["KEYCLOAK_ADMIN_PASSWORD"])
    base = f"{IDENTITY}/admin/realms/dxos"

    status, profile = request("GET", f"{base}/users/profile", token=admin)
    require(status, 200, profile)
    tenant = next((item for item in profile["attributes"] if item["name"] == "tenant_id"), None)
    if tenant is None:
        tenant = {"name": "tenant_id", "displayName": "Tenant ID"}
        profile["attributes"].append(tenant)
    desired_permissions = {"view": ["admin"], "edit": ["admin"]}
    if tenant.get("defaultValue") is not None or tenant.get("permissions") != desired_permissions:
        tenant.pop("defaultValue", None)
        tenant["permissions"] = desired_permissions
        status, result = request("PUT", f"{base}/users/profile", token=admin, data=profile)
        require(status, 200, result)

    status, groups = request("GET", f"{base}/groups?search=citizens-demo", token=admin)
    require(status, 200, groups)
    group = next((item for item in groups if item["name"] == "citizens-demo"), None)
    if group is None:
        status, result = request("POST", f"{base}/groups", token=admin, data={
            "name": "citizens-demo", "attributes": {"tenant_id": ["demo"]},
        })
        require(status, 201, result)
        status, groups = request("GET", f"{base}/groups?search=citizens-demo", token=admin)
        require(status, 200, groups)
        group = next(item for item in groups if item["name"] == "citizens-demo")
    status, group_details = request("GET", f"{base}/groups/{group['id']}", token=admin)
    require(status, 200, group_details)
    if group_details.get("attributes", {}).get("tenant_id") != ["demo"]:
        group_details.setdefault("attributes", {})["tenant_id"] = ["demo"]
        status, result = request("PUT", f"{base}/groups/{group['id']}", token=admin, data=group_details)
        require(status, 204, result)
    status, defaults = request("GET", f"{base}/default-groups", token=admin)
    require(status, 200, defaults)
    if not any(item["id"] == group["id"] for item in defaults):
        status, result = request("PUT", f"{base}/default-groups/{group['id']}", token=admin)
        require(status, 204, result)

    status, citizen = request("GET", f"{base}/roles/citizen", token=admin)
    require(status, 200, citizen)
    status, group_roles = request("GET", f"{base}/groups/{group['id']}/role-mappings/realm", token=admin)
    require(status, 200, group_roles)
    if not any(role["name"] == "citizen" for role in group_roles):
        status, result = request(
            "POST", f"{base}/groups/{group['id']}/role-mappings/realm", token=admin, data=[citizen]
        )
        require(status, 204, result)

    # Keep citizen scoped to the default group, including on realms configured
    # by an earlier local setup that added it to the realm-wide default role.
    status, default_role = request("GET", f"{base}/roles/default-roles-dxos", token=admin)
    require(status, 200, default_role)
    status, composites = request("GET", f"{base}/roles-by-id/{default_role['id']}/composites", token=admin)
    require(status, 200, composites)
    if any(role["name"] == "citizen" and not role.get("clientRole") for role in composites):
        status, result = request(
            "DELETE", f"{base}/roles-by-id/{default_role['id']}/composites", token=admin, data=[citizen]
        )
        require(status, 204, result)

    # Keep profile verification enabled. A Keycloak 26.4 bug loops if the
    # admin-only tenant uses user-profile defaultValue; the group avoids it.
    status, actions = request("GET", f"{base}/authentication/required-actions", token=admin)
    require(status, 200, actions)
    verify_profile = next(action for action in actions if action["alias"] == "VERIFY_PROFILE")
    if not verify_profile["enabled"]:
        verify_profile["enabled"] = True
        status, result = request(
            "PUT", f"{base}/authentication/required-actions/VERIFY_PROFILE",
            token=admin, data=verify_profile,
        )
        require(status, 204, result)

    status, realm = request("GET", base, token=admin)
    require(status, 200, realm)
    if not realm.get("registrationAllowed"):
        realm["registrationAllowed"] = True
        status, result = request("PUT", base, token=admin, data=realm)
        require(status, 204, result)

    print("Citizen registration enabled; new accounts receive role citizen and tenant demo.")


if __name__ == "__main__":
    main()
