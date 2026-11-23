"use strict";

(() => {
  const orders = document.getElementById("customerOrders");
  if (!orders) return;

  orders.addEventListener("click", event => {
    const button = event.target.closest("[data-review-order]");
    if (button) void openReview(button.dataset.reviewOrder);
  });

  async function openReview(orderId) {
    if (document.getElementById("orderReviewDialog")) return;

    const endpoint = `/api/v1/orders/${encodeURIComponent(orderId)}/review`;
    const dialog = document.createElement("dialog");
    dialog.id = "orderReviewDialog";
    dialog.className = "border rounded-4 shadow p-0";
    dialog.style.width = "min(92vw, 460px)";
    dialog.setAttribute("aria-labelledby", "orderReviewTitle");
    dialog.innerHTML = `
      <form class="p-4">
        <h2 id="orderReviewTitle" class="h5 mb-3">Đánh giá đơn hàng</h2>
        <div class="mb-3">
          <label for="reviewRestaurantStars" class="form-label">Nhà hàng</label>
          <select id="reviewRestaurantStars" class="form-select" required></select>
        </div>
        <div class="mb-3" data-driver-field hidden>
          <label for="reviewDriverStars" class="form-label">Tài xế</label>
          <select id="reviewDriverStars" class="form-select"></select>
        </div>
        <div class="mb-3">
          <label for="reviewComment" class="form-label">Nhận xét</label>
          <textarea id="reviewComment" class="form-control" rows="3" maxlength="500"></textarea>
        </div>
        <div data-restaurant-replies class="mb-3"></div>
        <p class="small" role="status"></p>
        <div class="d-flex justify-content-end gap-2">
          <button type="button" class="btn btn-outline-secondary" data-close>Đóng</button>
          <button type="submit" class="btn btn-dark" disabled>Lưu đánh giá</button>
        </div>
      </form>`;

    const form = dialog.querySelector("form");
    const restaurant = dialog.querySelector("#reviewRestaurantStars");
    const driver = dialog.querySelector("#reviewDriverStars");
    const driverField = dialog.querySelector("[data-driver-field]");
    const comment = dialog.querySelector("#reviewComment");
    const message = dialog.querySelector('[role="status"]');
    const save = dialog.querySelector('[type="submit"]');

    function fillStars(select, placeholder) {
      select.append(new Option(placeholder, ""));
      for (let stars = 5; stars >= 1; stars--) {
        select.append(new Option(`${stars} sao`, String(stars)));
      }
    }

    fillStars(restaurant, "Chọn số sao");
    fillStars(driver, "Bỏ qua");
    dialog.querySelector("[data-close]").addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => dialog.remove(), { once: true });

    form.addEventListener("submit", async event => {
      event.preventDefault();
      if (save.disabled) return;
      save.disabled = true;
      message.textContent = "";

      try {
        await api(endpoint, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            restaurant_stars: Number(restaurant.value),
            driver_stars: !driverField.hidden && driver.value ? Number(driver.value) : null,
            comment: comment.value.trim()
          })
        });
        message.className = "small text-success";
        message.textContent = "Đã lưu đánh giá.";
      } catch (error) {
        message.className = "small text-danger";
        message.textContent = error.message;
      } finally {
        save.disabled = false;
      }
    });

    document.body.append(dialog);
    message.textContent = "Đang tải đánh giá…";
    dialog.showModal();

    try {
      const data = await api(endpoint);
      driverField.hidden = !data.can_rate_driver;
      restaurant.value = data.review ? String(data.review.restaurant_stars) : "";
      driver.value = data.review?.driver_stars ? String(data.review.driver_stars) : "";
      comment.value = data.review?.comment ?? "";
      const replies = dialog.querySelector("[data-restaurant-replies]");
      for (const reply of data.restaurant_replies ?? []) {
        const title = document.createElement("strong");
        title.className = "small";
        title.textContent = `Phản hồi từ ${reply.restaurant_name}`;
        const text = document.createElement("p");
        text.className = "small text-break mb-2";
        text.textContent = reply.message;
        replies.append(title, text);
      }
      message.textContent = "";
      save.disabled = false;
    } catch (error) {
      message.className = "small text-danger";
      message.textContent = error.message;
    }
  }
})();
