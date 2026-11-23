"use strict";

(() => {
  const view = document.getElementById("view-RESTAURANT");
  const orders = document.getElementById("restaurantOrders");
  if (!view || !orders) return;

  const panel = document.createElement("section");
  panel.className = "card border-0 shadow-sm mt-4";
  panel.setAttribute("aria-labelledby", "restaurantReviewsTitle");
  panel.innerHTML = `
    <div class="card-body">
      <div class="d-flex justify-content-between align-items-center gap-2">
        <h2 id="restaurantReviewsTitle" class="h5 fw-bold mb-0">Đánh giá của khách</h2>
        <button type="button" class="btn btn-sm btn-outline-dark" data-reload>Tải lại</button>
      </div>
      <p class="small mt-2 mb-0" role="status"></p>
      <div data-reviews></div>
    </div>`;
  orders.after(panel);

  const list = panel.querySelector("[data-reviews]");
  const reload = panel.querySelector("[data-reload]");
  const notice = panel.querySelector('[role="status"]');
  const endpoint = "/api/v1/orders/restaurant/reviews";

  function createReview(item) {
    const card = document.createElement("article");
    card.className = "border rounded p-3 mt-3";
    card.innerHTML = `
      <h3 class="h6"></h3>
      <p class="small text-break" data-comment></p>
      <form>
        <label class="form-label small fw-bold">
          Phản hồi của quán
          <textarea class="form-control" rows="2" maxlength="500" required></textarea>
        </label>
        <div>
          <button type="submit" class="btn btn-sm btn-dark">Lưu phản hồi</button>
        </div>
        <p class="small mb-0 mt-1" role="status"></p>
      </form>`;
    card.querySelector("h3").textContent =
      `${item.restaurant_name} · ${item.stars}/5 sao · Đơn #${item.order_id.slice(0, 8)}`;
    card.querySelector("[data-comment]").textContent = item.comment || "Khách không viết nhận xét.";

    const form = card.querySelector("form");
    const field = form.querySelector("textarea");
    const button = form.querySelector("button");
    const message = form.querySelector('[role="status"]');
    field.value = item.reply ?? "";

    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (button.disabled) return;
      const reply = field.value.trim();
      if (!reply) {
        message.className = "small text-danger mb-0 mt-1";
        message.textContent = "Vui lòng nhập phản hồi.";
        return;
      }

      button.disabled = true;
      field.disabled = true;
      message.textContent = "Đang lưu…";
      const id = encodeURIComponent(item.order_id);
      const restaurantId = encodeURIComponent(item.restaurant_id);

      try {
        const saved = await api(`${endpoint}/${id}/${restaurantId}/reply`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: reply })
        });
        field.value = saved.reply;
        message.className = "small text-success mb-0 mt-1";
        message.textContent = "Đã lưu phản hồi.";
      } catch (error) {
        message.className = "small text-danger mb-0 mt-1";
        message.textContent = error.message;
      } finally {
        button.disabled = false;
        field.disabled = false;
      }
    });

    return card;
  }

  async function loadReviews() {
    if (reload.disabled || list.querySelector("textarea:disabled")) return;
    reload.disabled = true;
    notice.className = "small text-muted mt-2 mb-0";
    notice.textContent = "Đang tải đánh giá…";

    try {
      const reviews = await api(endpoint);
      if (!Array.isArray(reviews)) throw new Error("Danh sách đánh giá không hợp lệ.");
      list.replaceChildren(...reviews.map(createReview));
      notice.textContent = reviews.length ? "" : "Quán chưa có đánh giá.";
    } catch (error) {
      notice.className = "small text-danger mt-2 mb-0";
      notice.textContent = error.message;
    } finally {
      reload.disabled = false;
    }
  }

  reload.addEventListener("click", loadReviews);
  const observer = new MutationObserver(onVisible);

  function onVisible() {
    if (view.classList.contains("d-none")) return;
    observer.disconnect();
    void loadReviews();
  }

  observer.observe(view, { attributes: true, attributeFilter: ["class"] });
  onVisible();
})();
