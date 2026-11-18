"use strict";

(() => {
  const view = document.getElementById("view-DRIVER");
  if (!view) return;

  const panel = document.createElement("section");
  panel.className = "card shadow-sm border-0 mb-3";
  panel.setAttribute("aria-labelledby", "driverAvailabilityHeading");
  panel.innerHTML = `
    <div class="card-body">
      <div class="d-flex flex-wrap align-items-center justify-content-between gap-2">
        <div>
          <h2 id="driverAvailabilityHeading" class="h6 fw-bold mb-1">
            Trạng thái nhận chuyến
          </h2>
          <span class="badge text-bg-secondary" data-status>Đang tải</span>
        </div>
        <button type="button" class="btn btn-outline-dark" disabled>
          Đang tải…
        </button>
      </div>
      <p class="small mt-2 mb-0 d-none" role="status"></p>
    </div>
  `;
  view.querySelector("h1").after(panel);

  const status = panel.querySelector("[data-status]");
  const button = panel.querySelector("button");
  const message = panel.querySelector('[role="status"]');
  const endpoint = "/api/v1/driver/availability";

  let isOnline = null;
  let busy = false;

  function render() {
    status.textContent = isOnline === null
      ? busy ? "Đang tải" : "Chưa xác định"
      : isOnline ? "Đang nhận chuyến" : "Đang tạm ngừng";

    status.className = isOnline ? "badge text-bg-success" : "badge text-bg-secondary";
    button.disabled = busy;
    button.textContent = busy
      ? "Đang xử lý…"
      : isOnline === null
        ? "Tải lại trạng thái"
        : isOnline ? "Tạm ngừng nhận chuyến" : "Bật nhận chuyến";
  }

  async function requestAvailability(nextStatus) {
    if (busy) return;

    busy = true;
    message.classList.add("d-none");
    render();

    try {
      const data = nextStatus === undefined
        ? await api(endpoint)
        : await api(endpoint, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ is_online: nextStatus })
          });

      if (typeof data?.is_online !== "boolean") {
        throw new Error("Không đọc được trạng thái nhận chuyến.");
      }

      isOnline = data.is_online;
    } catch (error) {
      message.textContent = error.message;
      message.className = "small text-danger mt-2 mb-0";
    } finally {
      busy = false;
      render();
    }
  }

  button.addEventListener("click", () => {
    if (isOnline === null) {
      void requestAvailability();
    } else {
      void requestAvailability(!isOnline);
    }
  });

  function loadWhenVisible() {
    if (view.classList.contains("d-none")) return;
    observer.disconnect();
    void requestAvailability();
  }

  const observer = new MutationObserver(loadWhenVisible);
  observer.observe(view, { attributes: true, attributeFilter: ["class"] });
  loadWhenVisible();
})();