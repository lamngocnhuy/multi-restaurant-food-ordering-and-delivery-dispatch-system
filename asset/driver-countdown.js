"use strict";

(() => {
  const list = document.getElementById("driverOrders");
  if (!list) return;

  function updateCountdowns() {
    const now = Date.now();

    for (const element of list.querySelectorAll("[data-offer-expires]")) {
      const expiresAt = Date.parse(element.dataset.offerExpires);
      if (!Number.isFinite(expiresAt)) {
        element.textContent = "Không đọc được thời hạn đề nghị.";
        continue;
      }

      const seconds = Math.max(0, Math.ceil((expiresAt - now) / 1000));
      element.textContent = seconds > 0
        ? `Còn ${seconds} giây để phản hồi`
        : "Đề nghị đã hết hạn.";

      element.classList.toggle("text-danger", seconds <= 5);
    }
  }

  new MutationObserver(updateCountdowns).observe(list, { childList: true });
  setInterval(updateCountdowns, 1000);
  updateCountdowns();
})();
