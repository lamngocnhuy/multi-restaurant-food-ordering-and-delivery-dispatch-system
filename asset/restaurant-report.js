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
        <button type="button" class="btn btn-sm btn-outline-dark" data-refresh>Tải lại</button>
      </div>
      <div class="row g-2 mb-3">
        <div class="col-sm-6">
          <label for="ownerReportFrom" class="form-label small">Từ ngày</label>
          <input id="ownerReportFrom" data-report-from type="date" class="form-control">
        </div>
        <div class="col-sm-6">
          <label for="ownerReportTo" class="form-label small">Đến ngày</label>
          <input id="ownerReportTo" data-report-to type="date" class="form-control">
        </div>
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
        <div class="col-sm-6">
          <dt class="small text-muted">Phí nền tảng</dt>
          <dd class="fs-5 fw-bold mb-0" data-platform-total>—</dd>
        </div>
        <div class="col-sm-6">
          <dt class="small text-muted">Thực nhận</dt>
          <dd class="fs-5 fw-bold mb-0" data-net-total>—</dd>
        </div>
      </dl>
      <p class="small mt-3 mb-0" role="status"></p>
    </div>`;
  orders.after(panel);

  const refresh = panel.querySelector("[data-refresh]");
  const count = panel.querySelector("[data-order-count]");
  const total = panel.querySelector("[data-food-total]");
  const platform = panel.querySelector("[data-platform-total]");
  const net = panel.querySelector("[data-net-total]");
  const message = panel.querySelector('[role="status"]');
  const completed = new Set(["COMPLETED", "DELIVERED"]);
  const paid = new Set(["SUCCESS", "PAID"]);

  async function loadReport() {
    if (refresh.disabled) return;
    refresh.disabled = true;
    message.className = "small text-muted mt-3 mb-0";
    message.textContent = "Đang tải số liệu…";

    try {
      const from = panel.querySelector("[data-report-from]").value;
      const to = panel.querySelector("[data-report-to]").value;

      if (from && to && from > to) {
        throw new Error("Từ ngày phải nhỏ hơn hoặc bằng Đến ngày.");
      }

      const params = new URLSearchParams();
      if (from) params.set("date_from", from);
      if (to) params.set("date_to", to);
      const query = params.toString();
      const data = await api("/api/v1/orders" + (query ? "?" + query : ""));
      if (!Array.isArray(data)) {
        throw new Error("Danh sách đơn trả về không hợp lệ.");
      }

      const eligible = data.filter(order =>
        completed.has(order.status) && paid.has(order.payment_status)
      );

      let foodTotal = 0;
      let platformTotal = 0;
      let missingDetails = 0;
      let missingFees = 0;
      let invalidFees = 0;

      for (const order of eligible) {
        const amounts = (Array.isArray(order.items) ? order.items : []).map(
          item => item.line_total == null ? NaN : Number(item.line_total)
        );

        if (!amounts.length || !amounts.every(amount => Number.isFinite(amount) && amount >= 0)) {
          missingDetails++;
          continue;
        }

        const subtotal = amounts.reduce((sum, amount) => sum + amount, 0);
        foodTotal += subtotal;

        if (order.platform_fee == null) {
          missingFees++;
          continue;
        }

        const fee = order.platform_fee;
        if (!Number.isFinite(fee) || fee < 0 || fee > subtotal) {
          invalidFees++;
          continue;
        }

        platformTotal += fee;
      }

      count.textContent = String(eligible.length);
      total.textContent = formatMoney(foodTotal);
      platform.textContent = invalidFees ? "—" : formatMoney(platformTotal);
      net.textContent = invalidFees ? "—" : formatMoney(foodTotal - platformTotal);

      const notes = [];
      if (missingDetails) {
        notes.push(`Số liệu tạm tính vì ${missingDetails} đơn thiếu chi tiết tiền món.`);
      }
      if (missingFees) {
        notes.push(`${missingFees} đơn chưa có phí nền tảng được lưu. Tiền món của các đơn này được giữ nguyên trong phần thực nhận.`);
      }
      if (invalidFees) {
        notes.push(`Có ${invalidFees} đơn có dữ liệu phí không hợp lệ.`);
      }
      message.textContent = notes.join(" ");
    } catch (error) {
      for (const field of [count, total, platform, net]) {
        field.textContent = "—";
      }
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
