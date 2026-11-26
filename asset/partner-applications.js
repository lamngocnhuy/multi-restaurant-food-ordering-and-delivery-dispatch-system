"use strict";

(() => {
  const endpoint = "/api/v1/partners/applications";
  const auth = document.getElementById("authPanel");
  const admin = document.getElementById("view-ADMIN");

  if (auth) addRegistration(auth);
  if (admin) addAdminQueue(admin);

  function addRegistration(view) {
    const open = document.createElement("button");
    open.type = "button";
    open.className = "btn btn-outline-dark mt-3";
    open.textContent = "Đăng ký nhà hàng";
    (view.querySelector(".card-body") ?? view).append(open);

    const dialog = document.createElement("dialog");
    dialog.className = "border rounded-4 shadow p-0";
    dialog.style.width = "min(92vw, 460px)";
    dialog.setAttribute("aria-labelledby", "partnerRegistrationTitle");
    dialog.innerHTML = `
      <form class="p-4">
        <h2 id="partnerRegistrationTitle" class="h5 mb-3">Đăng ký nhà hàng</h2>
        <label class="form-label d-block">
          Tên người liên hệ
          <input name="full_name" class="form-control" maxlength="120" autocomplete="name" required>
        </label>
        <label class="form-label d-block">
          Email
          <input name="email" class="form-control" type="email" maxlength="254" autocomplete="email" required>
        </label>
        <label class="form-label d-block">
          Mật khẩu
          <input name="password" class="form-control" type="password"
                 minlength="10" maxlength="128" autocomplete="new-password" required>
        </label>
        <label class="form-label d-block">
          Tên nhà hàng
          <input name="restaurant_name" class="form-control" maxlength="150" required>
        </label>
        <label class="form-label d-block">
          Địa chỉ nhà hàng
          <textarea name="address" class="form-control" minlength="5"
                    maxlength="500" rows="2" required></textarea>
        </label>
        <p class="small" role="status"></p>
        <div class="d-flex flex-wrap justify-content-end gap-2">
          <button type="button" class="btn btn-outline-secondary" data-close>Đóng</button>
          <button type="submit" class="btn btn-dark">Gửi hồ sơ</button>
        </div>
      </form>`;
    document.body.append(dialog);

    const form = dialog.querySelector("form");
    const save = form.querySelector('[type="submit"]');
    const message = form.querySelector('[role="status"]');

    open.addEventListener("click", () => {
      if (!dialog.open) dialog.showModal();
    });
    dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => {
      form.elements.namedItem("password").value = "";
    });

    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (save.disabled) return;

      save.disabled = true;
      message.textContent = "Đang gửi hồ sơ…";

      try {
        const result = await api(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(Object.fromEntries(new FormData(form)))
        });
        form.reset();
        message.className = "small text-success";
        message.textContent = result.message;
      } catch (error) {
        message.className = "small text-danger";
        message.textContent = error.message;
      } finally {
        save.disabled = false;
      }
    });
  }

  function addAdminQueue(view) {
    const panel = document.createElement("section");
    panel.className = "card border-0 shadow-sm mt-4";
    panel.setAttribute("aria-labelledby", "partnerQueueTitle");
    panel.innerHTML = `
      <div class="card-body">
        <div class="d-flex flex-wrap justify-content-between align-items-center gap-2">
          <h2 id="partnerQueueTitle" class="h5 mb-0">Hồ sơ nhà hàng đối tác</h2>
          <button type="button" class="btn btn-sm btn-outline-dark" data-reload>Tải lại</button>
        </div>
        <p class="small mt-2 mb-0" role="status"></p>
        <div data-applications></div>
      </div>`;
    view.append(panel);

    const list = panel.querySelector("[data-applications]");
    const message = panel.querySelector('[role="status"]');
    const reload = panel.querySelector("[data-reload]");
    const labels = {
      PENDING: "Chờ duyệt",
      APPROVED: "Đã duyệt",
      REJECTED: "Đã từ chối"
    };
    let applications = [];
    let busy = false;

    function render() {
      list.replaceChildren();
      for (const item of applications) {
        const card = document.createElement("article");
        card.className = "border rounded p-3 mt-3";

        const title = document.createElement("h3");
        title.className = "h6";
        title.textContent = item.restaurant_name;

        const contact = document.createElement("p");
        contact.className = "small text-break mb-1";
        contact.textContent = `${item.full_name} · ${item.email}`;

        const address = document.createElement("p");
        address.className = "small text-break mb-1";
        address.textContent = item.address;

        const state = document.createElement("p");
        state.className = "small fw-semibold mb-2";
        state.textContent = labels[item.status] ?? item.status;

        card.append(title, contact, address, state);

        if (item.status === "PENDING") {
          const actions = document.createElement("div");
          actions.className = "d-flex flex-wrap gap-2";
          for (const [decision, text, style] of [
            ["APPROVED", "Phê duyệt", "btn-success"],
            ["REJECTED", "Từ chối", "btn-outline-danger"]
          ]) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = `btn btn-sm ${style}`;
            button.textContent = text;
            button.addEventListener("click", () => decide(item, decision, text));
            actions.append(button);
          }
          card.append(actions);
        }

        list.append(card);
      }
    }

    function setBusy(value) {
      busy = value;
      reload.disabled = value;
      for (const button of list.querySelectorAll("button")) button.disabled = value;
    }

    async function load() {
      if (busy) return;
      setBusy(true);
      message.textContent = "Đang tải hồ sơ…";
      try {
        const data = await api(endpoint);
        if (!Array.isArray(data)) throw new Error("Danh sách hồ sơ không hợp lệ.");
        applications = data;
        render();
        message.textContent = applications.length ? "" : "Chưa có hồ sơ nhà hàng.";
      } catch (error) {
        message.textContent = error.message;
      } finally {
        setBusy(false);
      }
    }

    async function decide(item, decision, text) {
      if (busy || !window.confirm(`${text} hồ sơ của ${item.restaurant_name}?`)) return;
      setBusy(true);

      try {
        const result = await api(`${endpoint}/${encodeURIComponent(item.owner_id)}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision })
        });
        item.status = result.status;
        render();
        message.textContent = decision === "APPROVED"
          ? "Đã duyệt hồ sơ và tạo nhà hàng."
          : "Đã từ chối hồ sơ.";
      } catch (error) {
        message.textContent = error.message;
      } finally {
        setBusy(false);
      }
    }

    reload.addEventListener("click", load);

    function loadWhenVisible() {
      if (view.classList.contains("d-none")) return;
      observer.disconnect();
      void load();
    }

    const observer = new MutationObserver(loadWhenVisible);
    observer.observe(view, { attributes: true, attributeFilter: ["class"] });
    loadWhenVisible();
  }
})();
