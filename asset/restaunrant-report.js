"use strict";

(() => {
  const view = document.getElementById("view-RESTAURANT");
  const orders = document.getElementById("restaurantOrders");
  if (!view || !orders) return;

  const panel = document.createElement("section");
  panel.className = "card shadow-sm border-0 mt-4";
  panel.setAttribute("aria-labelledby", "restaurantReportHeading");
  panel.innerHTML = `
    <div class="card-body">
      <div class="d-flex flex-wrap justify-content-between align-items-center gap-2 mb-3">
        <h2 id="restaurantReportHeading" class="h5 fw-bold mb-0">Đối soát tiền món</h2>
        <button type="button" class="btn btn-sm btn-outline-dark" data-refresh>
          Tải lại
        </button>
      </div>
      <dl class="row g-3 mb-0">
        <div class="col-sm-6">
          <dt class="small text-muted">Đơn đã giao và đã thanh toán</dt>
          <dd class="fs-5 fw-bold mb-0" data-order-count>—</dd>
        </div>
        <div class="col-sm-6">
          <dt class="small text-muted">Tổng tiền món, chưa gồm phí giao</dt>
          <dd class="fs-5 fw-bold mb-0" data-food-total>—</dd>
        </div>
      </dl>
      <p class="small mt-3 mb-0" role="status"></p>
    </div>`;
  orders.after(panel);

  const refresh = panel.querySelector("[data-refresh]");
  const count = panel.querySelector("[data-order-count]");
  const total = panel.querySelector("[data-food-total]");
  const message = panel.querySelector('[role="status"]');
  const completed = new Set(["COMPLETED", "DELIVERED"]);
  const paid = new Set(["SUCCESS", "PAID"]);

  async function loadReport() {
    if (refresh.disabled) return;
    refresh.disabled = true;
    message.className = "small text-muted mt-3 mb-0";
    message.textContent = "Đang tải số liệu…";

    try {
      const data = await api("/api/v1/orders");
      if (!Array.isArray(data)) {
        throw new Error("Danh sách đơn trả về không hợp lệ.");
      }

      const eligible = data.filter(order =>
        completed.has(order.status) && paid.has(order.payment_status)
      );

      let foodTotal = 0;
      let missingDetails = 0;

      for (const order of eligible) {
        if (!Array.isArray(order.items) || order.items.length === 0) {
          missingDetails++;
          continue;
        }

        const amounts = order.items.map(item =>
          item.line_total == null ? NaN : Number(item.line_total)
        );
        if (!amounts.every(amount => Number.isFinite(amount) && amount >= 0)) {
          missingDetails++;
          continue;
        }

        foodTotal += amounts.reduce((sum, amount) => sum + amount, 0);
      }

      count.textContent = String(eligible.length);
      total.textContent = formatMoney(foodTotal);
      message.textContent = missingDetails
        ? `Tạm tính. Có ${missingDetails} đơn thiếu chi tiết tiền món.`
        : "";
    } catch (error) {
      count.textContent = "—";
      total.textContent = "—";
      message.className = "small text-danger mt-3 mb-0";
      message.textContent = `Chưa tải được số liệu. ${error.message}`;
    } finally {
      refresh.disabled = false;
    }
  }

  refresh.addEventListener("click", loadReport);

  function loadWhenVisible() {
    if (view.classList.contains("d-none")) return;
    observer.disconnect();
    void loadReport();
  }

  const observer = new MutationObserver(loadWhenVisible);
  observer.observe(view, { attributes: true, attributeFilter: ["class"] });
  loadWhenVisible();
})();