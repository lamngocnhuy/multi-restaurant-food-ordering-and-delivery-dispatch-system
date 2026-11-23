"use strict";

(() => {
  const view = document.getElementById("view-ADMIN");
  const orders = document.getElementById("adminOrders");
  if (!view || !orders || document.getElementById("adminUsersPanel")) return;

  const panel = document.createElement("section");
  panel.id = "adminUsersPanel";
  panel.className = "card shadow-sm border-0 mt-4";
  panel.setAttribute("aria-labelledby", "adminUsersHeading");
  panel.innerHTML = `
    <div class="card-body">
      <h2 id="adminUsersHeading" class="h5 fw-bold mb-3">Quản lý tài khoản</h2>
      <div class="row g-2 align-items-end mb-3">
        <div class="col-md-6">
          <label for="accountSearch" class="form-label">Tên hoặc email</label>
          <input id="accountSearch" type="search" class="form-control">
        </div>
        <div class="col-md-4">
          <label for="accountRole" class="form-label">Vai trò</label>
          <select id="accountRole" class="form-select">
            <option value="">Tất cả vai trò</option>
            <option value="CUSTOMER">Khách hàng</option>
            <option value="RESTAURANT">Chủ quán</option>
            <option value="DRIVER">Tài xế</option>
            <option value="ADMIN">Admin</option>
          </select>
        </div>
        <div class="col-md-2">
          <button type="button" class="btn btn-outline-dark w-100" data-reload>
            Tải lại
          </button>
        </div>
      </div>
      <p class="small mb-2" role="status"></p>
      <div class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr>
              <th scope="col">Họ tên</th>
              <th scope="col">Email</th>
              <th scope="col">Vai trò</th>
              <th scope="col">Trạng thái</th>
              <th scope="col">Thao tác</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>`;
  orders.after(panel);

  const search = panel.querySelector("#accountSearch");
  const roleFilter = panel.querySelector("#accountRole");
  const reload = panel.querySelector("[data-reload]");
  const message = panel.querySelector('[role="status"]');
  const rows = panel.querySelector("tbody");
  const endpoint = "/api/v1/admin/users";

  const roles = new Map([
    ["CUSTOMER", "Khách hàng"],
    ["RESTAURANT", "Chủ quán"],
    ["DRIVER", "Tài xế"],
    ["ADMIN", "Admin"]
  ]);
  const statuses = new Map([
    ["ACTIVE", "Đang hoạt động"],
    ["LOCKED", "Đã khóa"],
    ["PENDING", "Chờ kích hoạt"]
  ]);
  const editableRoles = new Set(["CUSTOMER", "RESTAURANT", "DRIVER"]);

  let users = [];
  let loaded = false;
  let busy = false;

  function notice(text, isError = false) {
    message.textContent = text;
    message.className = isError ? "small text-danger mb-2" : "small text-muted mb-2";
  }

  function render() {
    const keyword = search.value.trim().toLocaleLowerCase("vi-VN");
    const visible = users.filter(user => {
      const nameAndEmail = `${user.name ?? ""} ${user.email ?? ""}`;
      return nameAndEmail.toLocaleLowerCase("vi-VN").includes(keyword)
        && (!roleFilter.value || user.role === roleFilter.value);
    });

    rows.replaceChildren();
    if (loaded && !visible.length) {
      const cell = rows.insertRow().insertCell();
      cell.colSpan = 5;
      cell.textContent = "Không có tài khoản khớp bộ lọc.";
      return;
    }

    for (const user of visible) {
      const row = rows.insertRow();
      row.insertCell().textContent = user.name ?? "—";
      row.insertCell().textContent = user.email ?? "—";
      row.insertCell().textContent = roles.get(user.role) ?? user.role;
      row.insertCell().textContent = statuses.get(user.status) ?? "Chưa xác định";

      const actions = row.insertCell();
      if (!editableRoles.has(user.role) || !["ACTIVE", "LOCKED"].includes(user.status)) {
        actions.textContent = "—";
        continue;
      }

      const lock = user.status === "ACTIVE";
      const button = document.createElement("button");
      button.type = "button";
      button.className = lock ? "btn btn-sm btn-outline-danger" : "btn btn-sm btn-outline-success";
      button.textContent = lock ? "Khóa" : "Mở khóa";
      button.disabled = busy;
      button.addEventListener("click", () => changeStatus(user, lock));
      actions.append(button);
    }
  }

  function setBusy(value) {
    busy = value;
    reload.disabled = value;
    for (const button of rows.querySelectorAll("button")) button.disabled = value;
  }

  async function loadUsers() {
    if (busy) return;
    setBusy(true);
    notice("Đang tải tài khoản…");

    try {
      const result = await api(endpoint);
      if (!Array.isArray(result)) throw new Error("Danh sách tài khoản không hợp lệ.");
      users = result;
      loaded = true;
      notice("");
    } catch (error) {
      notice(`Chưa tải được tài khoản. ${error.message}`, true);
    } finally {
      setBusy(false);
      render();
    }
  }

  async function changeStatus(user, lock) {
    if (busy) return;
    if (lock && !window.confirm(`Khóa tài khoản ${user.email}?`)) return;

    setBusy(true);
    notice("");

    try {
      const updated = await api(`${endpoint}/${encodeURIComponent(user.id)}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: lock ? "LOCKED" : "ACTIVE" })
      });
      users = users.map(item => item.id === updated.id ? updated : item);
      notice(lock ? "Đã khóa tài khoản." : "Đã mở khóa tài khoản.");
    } catch (error) {
      notice(`Chưa cập nhật được trạng thái. ${error.message}`, true);
    } finally {
      setBusy(false);
      render();
    }
  }

  search.addEventListener("input", render);
  roleFilter.addEventListener("change", render);
  reload.addEventListener("click", loadUsers);

  function loadWhenVisible() {
    if (view.classList.contains("d-none")) return;
    observer.disconnect();
    void loadUsers();
  }

  const observer = new MutationObserver(loadWhenVisible);
  observer.observe(view, { attributes: true, attributeFilter: ["class"] });
  loadWhenVisible();
})();
