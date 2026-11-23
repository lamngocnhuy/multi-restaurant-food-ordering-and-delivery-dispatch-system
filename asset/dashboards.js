"use strict";

(() => {
  const byId = id => document.getElementById(id);

  function attachDriverFilters() {
    const list = byId("driverOrders");
    if (!list) return;

    const filters = document.createElement("div");
    filters.className = "mb-3";
    filters.innerHTML = `
      <div class="btn-group" role="group" aria-label="Lọc chuyến giao hàng">
        <button type="button" class="btn btn-sm btn-outline-dark active"
                data-trip-filter="current" aria-pressed="true">
          Chuyến hiện tại
        </button>
        <button type="button" class="btn btn-sm btn-outline-dark"
                data-trip-filter="history" aria-pressed="false">
          Lịch sử giao hàng
        </button>
      </div>
      <p class="small text-muted mt-2 mb-0" role="status"></p>
    `;
    list.before(filters);

    const status = filters.querySelector('[role="status"]');
    let selected = "current";

    function applyFilter() {
      const cards = [...list.children].filter(
        element => element.querySelector("article.card")
      );

      if (!cards.length) {
        status.textContent = "";
        return;
      }

      let visible = 0;
      for (const card of cards) {
        const isCurrent = Boolean(card.querySelector(
          '[data-action="driver-accept"], [data-action="driver-reject"], [data-action="pickup"], [data-action="complete"]'
        ));
        const show = selected === "current" ? isCurrent : !isCurrent;

        card.classList.toggle("d-none", !show);
        if (show) visible++;
      }

      status.textContent = visible
        ? ""
        : selected === "current"
          ? "Hiện chưa có đề nghị hoặc chuyến đang giao."
          : "Chưa có chuyến nào trong lịch sử.";
    }

    filters.addEventListener("click", event => {
      const button = event.target.closest("[data-trip-filter]");
      if (!button) return;

      selected = button.dataset.tripFilter;
      for (const option of filters.querySelectorAll("[data-trip-filter]")) {
        const active = option === button;
        option.classList.toggle("active", active);
        option.setAttribute("aria-pressed", String(active));
      }
      applyFilter();
    });

    new MutationObserver(applyFilter).observe(list, { childList: true });
    applyFilter();
  }

  function attachAdminFilters() {
    const list = byId("adminOrders");
    if (!list) return;

    const filters = document.createElement("div");
    filters.className = "row g-2 align-items-end mb-3";
    filters.innerHTML = `
      <div class="col-sm-6 col-lg-4">
        <label for="adminOrderSearch" class="form-label">Mã đơn</label>
        <input id="adminOrderSearch" type="search" class="form-control"
               placeholder="Nhập mã hiển thị trong bảng">
      </div>
      <div class="col-sm-6 col-lg-4">
        <label for="adminPaymentFilter" class="form-label">Thanh toán</label>
        <select id="adminPaymentFilter" class="form-select">
          <option value="">Tất cả trạng thái</option>
          <option value="Chờ thanh toán">Chờ thanh toán</option>
          <option value="Đã thanh toán">Đã thanh toán</option>
          <option value="Đã hủy thanh toán">Đã hủy thanh toán</option>
          <option value="Đang xử lý hoàn tiền">Đang xử lý hoàn tiền</option>
          <option value="Đã hoàn tiền">Đã hoàn tiền</option>
        </select>
      </div>
      <p class="col-12 small text-muted mb-0" role="status"></p>
    `;
    list.before(filters);

    const search = filters.querySelector("#adminOrderSearch");
    const payment = filters.querySelector("#adminPaymentFilter");
    const status = filters.querySelector('[role="status"]');
    const normalizeCode = value => value.trim().replace(/^#\s*/, "").toLowerCase();

    function applyFilter() {
      const rows = [...list.querySelectorAll("tbody tr")];
      const keyword = normalizeCode(search.value);
      let visible = 0;

      for (const row of rows) {
        const orderCode = normalizeCode(row.cells[0]?.textContent ?? "");
        const paymentCell = row.cells[3];
        // Ô thanh toán có thể chứa thêm nút xác nhận hoàn tiền.
        const paymentLabel = paymentCell?.firstChild?.textContent.trim() ?? "";

        const show = orderCode.includes(keyword)
          && (!payment.value || paymentLabel === payment.value);

        row.classList.toggle("d-none", !show);
        if (show) visible++;
      }

      status.textContent = rows.length && !visible
        ? "Không có đơn khớp với bộ lọc."
        : "";
    }

    search.addEventListener("input", applyFilter);
    payment.addEventListener("change", applyFilter);
    new MutationObserver(applyFilter).observe(list, { childList: true });
    applyFilter();
  }

  attachDriverFilters();
  attachAdminFilters();
})();