"use strict";

const getFormElement = id => document.getElementById(id);

function connectPasswordToggle() {
  const password = getFormElement("authPassword");
  const authToggle = getFormElement("authToggle");
  const authName = getFormElement("authName");
  if (!password || !authToggle || !authName) return;

  const group = document.createElement("div");
  group.className = "input-group";
  password.before(group);
  group.append(password);

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "btn btn-outline-secondary";
  toggle.textContent = "Hiện";
  toggle.setAttribute("aria-controls", password.id);
  toggle.setAttribute("aria-label", "Hiện mật khẩu");
  group.append(toggle);

  const hint = document.createElement("div");
  hint.id = "authPasswordHint";
  hint.className = "form-text d-none";
  hint.textContent = "Mật khẩu đăng ký cần ít nhất 10 ký tự.";
  group.after(hint);
  password.setAttribute("aria-describedby", hint.id);

  function setVisible(visible) {
    password.type = visible ? "text" : "password";
    toggle.textContent = visible ? "Ẩn" : "Hiện";
    toggle.setAttribute("aria-label", visible ? "Ẩn mật khẩu" : "Hiện mật khẩu");
  }

  toggle.addEventListener("click", () => setVisible(password.type === "password"));
  authToggle.addEventListener("click", () => {
    setVisible(false);
    hint.classList.toggle("d-none", !authName.required);
  });
}

function connectCheckoutReview() {
  const form = getFormElement("checkoutForm");
  const submit = getFormElement("checkoutButton");
  const address = getFormElement("addressInput");
  const payment = getFormElement("paymentSelect");
  const cart = getFormElement("cartItems");
  const total = getFormElement("cartTotal");
  if (!form || !submit || !address || !payment || !cart || !total) return;

  const dialog = document.createElement("dialog");
  dialog.className = "border rounded-4 shadow p-0";
  dialog.style.width = "min(92vw, 520px)";
  dialog.style.maxHeight = "85vh";
  dialog.setAttribute("aria-labelledby", "checkoutReviewTitle");
  dialog.innerHTML = `
    <div class="p-4">
      <h2 id="checkoutReviewTitle" class="h5 fw-bold mb-3">Kiểm tra đơn hàng</h2>
      <p class="small text-muted" data-count></p>
      <div data-groups class="mb-3"></div>
      <dl class="mb-3">
        <dt class="small">Địa chỉ giao hàng</dt>
        <dd class="text-break" data-address></dd>
        <dt class="small">Phương thức thanh toán</dt>
        <dd data-payment></dd>
        <dt class="small">Tổng thanh toán</dt>
        <dd class="fs-5 fw-bold text-danger" data-total></dd>
      </dl>
      <div class="d-flex flex-wrap justify-content-end gap-2">
        <button type="button" class="btn btn-outline-secondary" data-back autofocus>
          Quay lại
        </button>
        <button type="button" class="btn btn-dark" data-confirm>
          Xác nhận đặt hàng
        </button>
      </div>
    </div>`;
  document.body.append(dialog);

  const groupsBox = dialog.querySelector("[data-groups]");
  let confirmed = false;

  function renderGroup(group) {
    const section = document.createElement("section");
    section.className = "border rounded p-3 mb-2";

    const title = document.createElement("h3");
    title.className = "h6 mb-2";
    title.textContent = group.querySelector("label strong")?.textContent.trim()
      || "Nhà hàng";

    const items = document.createElement("ul");
    items.className = "small ps-3 mb-2";
    for (const row of group.querySelectorAll(".fw-semibold")) {
      const item = document.createElement("li");
      const quantity = row.nextElementSibling?.textContent?.trim();
      item.textContent = [row.textContent.trim(), quantity].filter(Boolean).join(" · ");
      items.append(item);
    }

    const amounts = document.createElement("p");
    amounts.className = "small text-muted mb-0";
    amounts.textContent = group.querySelector("[data-group-totals]")?.textContent ?? "";
    section.append(title, items, amounts);
    return section;
  }

  form.addEventListener("submit", event => {
    if (confirmed) return;

    event.preventDefault();
    event.stopImmediatePropagation();
    if (submit.disabled || dialog.open) return;

    const deliveryAddress = address.value.trim();
    if (deliveryAddress.length < 5) {
      address.setCustomValidity("Vui lòng nhập địa chỉ giao hàng từ 5 ký tự.");
      address.reportValidity();
      return;
    }

    const selectedGroups = [...cart.querySelectorAll("[data-cart-group]")].filter(
      group => group.querySelector("[data-cart-select]")?.checked
    );
    if (!selectedGroups.length) return;

    groupsBox.replaceChildren(...selectedGroups.map(renderGroup));
    dialog.querySelector("[data-count]").textContent =
      `Bạn đang đặt ${selectedGroups.length} đơn từ ${selectedGroups.length} quán.`;
    dialog.querySelector("[data-address]").textContent = deliveryAddress;
    dialog.querySelector("[data-payment]").textContent =
      payment.selectedOptions[0]?.textContent ?? "";
    dialog.querySelector("[data-total]").textContent = total.textContent;
    dialog.showModal();
  }, true);

  address.addEventListener("input", () => address.setCustomValidity(""));
  dialog.querySelector("[data-back]").addEventListener("click", () => dialog.close());
  dialog.querySelector("[data-confirm]").addEventListener("click", () => {
    dialog.close();
    if (submit.disabled) return;

    confirmed = true;
    try {
      form.requestSubmit(submit);
    } finally {
      confirmed = false;
    }
  });
}

function connectFoodPricePreview() {
  const price = getFormElement("ownerFoodPrice");
  const form = getFormElement("ownerFoodForm");
  const menu = getFormElement("ownerMenuList");
  const cancel = getFormElement("ownerFoodCancel");
  if (!price || !form || !menu || !cancel) return;

  const formatter = new Intl.NumberFormat("vi-VN");
  const preview = document.createElement("div");
  preview.id = "ownerPricePreview";
  preview.className = "form-text";
  price.after(preview);
  price.setAttribute("aria-describedby", preview.id);

  function updatePreview() {
    const amount = price.valueAsNumber;
    preview.textContent = price.validity.valid && Number.isFinite(amount)
      ? `${formatter.format(amount)} VNĐ`
      : "";
  }

  price.addEventListener("input", updatePreview);
  menu.addEventListener("click", updatePreview);
  cancel.addEventListener("click", updatePreview);

  // Đọc lại ô giá khi form thêm hoặc sửa món được xóa sau khi lưu.
  const save = getFormElement("ownerFoodSave");
  if (save) {
    new MutationObserver(updatePreview).observe(save, {
      attributes: true,
      attributeFilter: ["disabled"],
      childList: true
    });
  }
}

connectPasswordToggle();
connectCheckoutReview();
connectFoodPricePreview();