"use strict";

(() => {
  const view = document.getElementById("view-ADMIN");
  const orderTable = document.getElementById("adminOrders");
  if (!view || !orderTable) return;

  const panel = document.createElement("section");
  panel.className = "card shadow-sm border-0 mb-3";
  panel.setAttribute("aria-labelledby", "adminReportTitle");
  panel.innerHTML = `
    <div class="card-body">
      <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <h2 id="adminReportTitle" class="h5 fw-bold mb-0">Báo cáo đơn hàng</h2>
        <div class="d-flex gap-2">
          <button type="button" class="btn btn-sm btn-outline-dark" data-refresh>
            Tải báo cáo
          </button>
          <button type="button" class="btn btn-sm btn-dark" data-export disabled>
            Xuất CSV
          </button>
        </div>
      </div>
      <dl class="row g-3 mb-0">
        <div class="col-sm-6 col-lg-3">
          <dt class="small text-muted">Tổng số đơn</dt>
          <dd class="fs-5 fw-bold mb-0" data-count>—</dd>
        </div>
        <div class="col-sm-6 col-lg-3">
          <dt class="small text-muted">Đơn đã giao</dt>
          <dd class="fs-5 fw-bold mb-0" data-completed>—</dd>
        </div>
        <div class="col-sm-6 col-lg-3">
          <dt class="small text-muted">Tiền đơn đã giao và đã thu</dt>
          <dd class="fs-5 fw-bold mb-0" data-collected>—</dd>
        </div>
        <div class="col-sm-6 col-lg-3">
          <dt class="small text-muted">Tiền đang chờ hoàn</dt>
          <dd class="fs-5 fw-bold mb-0" data-refunds>—</dd>
        </div>
      </dl>
      <p class="small mt-3 mb-0" role="status"></p>
    </div>
  `;
  orderTable.before(panel);

  const refresh = panel.querySelector("[data-refresh]");
  const exportButton = panel.querySelector("[data-export]");
  const message = panel.querySelector('[role="status"]');
  const currency = new Intl.NumberFormat("vi-VN", {
    style: "currency",
    currency: "VND"
  });

  let orders = [];
  let busy = false;

  const completedStatuses = new Set(["COMPLETED", "DELIVERED"]);
  const paidStatuses = new Set(["SUCCESS", "PAID"]);

  function amount(order) {
    const value = Number(order.grand_total);
    return Number.isFinite(value) ? value : 0;
  }

  function render() {
    const completed = orders.filter(order => completedStatuses.has(order.status));
    const collected = completed
      .filter(order => paidStatuses.has(order.payment_status))
      .reduce((sum, order) => sum + amount(order), 0);
    const pendingRefunds = orders
      .filter(order => order.payment_status === "REFUND_PROCESSING")
      .reduce((sum, order) => sum + amount(order), 0);

    panel.querySelector("[data-count]").textContent = orders.length;
    panel.querySelector("[data-completed]").textContent = completed.length;
    panel.querySelector("[data-collected]").textContent = currency.format(collected);
    panel.querySelector("[data-refunds]").textContent = currency.format(pendingRefunds);
  }

  async function loadReport() {
    if (busy) return;

    busy = true;
    refresh.disabled = true;
    exportButton.disabled = true;
    message.className = "small text-muted mt-3 mb-0";
    message.textContent = "Đang tải báo cáo…";

    try {
      const data = await api("/api/v1/orders");
      if (!Array.isArray(data)) throw new Error("Danh sách đơn trả về không hợp lệ.");

      orders = data;
      render();
      exportButton.disabled = orders.length === 0;
      const updatedAt = new Date().toLocaleTimeString("vi-VN");
      message.textContent = `Cập nhật lúc ${updatedAt}. Báo cáo tính trên toàn bộ đơn hàng.`;
    } catch (error) {
      message.className = "small text-danger mt-3 mb-0";
      message.textContent = "Chưa tải được báo cáo. " + error.message;
    } finally {
      busy = false;
      refresh.disabled = false;
    }
  }

  function csvCell(value) {
    let text = String(value ?? "");
    // Giữ mã và trạng thái dưới dạng văn bản khi mở trong Excel.
    if (typeof value !== "number" && /^\s*[=+\-@]/.test(text)) {
      text = "'" + text;
    }
    return `"${text.replace(/"/g, '""')}"`;
  }

  exportButton.addEventListener("click", () => {
    if (busy || orders.length === 0) return;

    const rows = [
      ["Mã đơn", "Trạng thái đơn", "Phương thức", "Trạng thái thanh toán", "Tổng tiền (VNĐ)"],
      ...orders.map(order => [
        order.order_id,
        order.status,
        order.payment_method,
        order.payment_status,
        amount(order)
      ])
    ];
    const csv = rows.map(row => row.map(csvCell).join(",")).join("\r\n");
    const file = new Blob(["\uFEFF", csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(file);
    const link = document.createElement("a");
    link.href = url;
    link.download = "bao-cao-don-hang.csv";
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  });

  refresh.addEventListener("click", loadReport);

  const observer = new MutationObserver(loadWhenVisible);
  function loadWhenVisible() {
    if (view.classList.contains("d-none")) return;
    observer.disconnect();
    void loadReport();
  }

  observer.observe(view, { attributes: true, attributeFilter: ["class"] });
  loadWhenVisible();
})();