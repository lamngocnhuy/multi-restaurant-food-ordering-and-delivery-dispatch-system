"use strict";

(() => {
  const view = document.getElementById("view-RESTAURANT");
  const heading = document.getElementById("restaurantHeading");
  if (!view || !heading) return;

  const panel = document.createElement("section");
  panel.className = "card border-0 shadow-sm mb-4";
  panel.setAttribute("aria-labelledby", "ownerMenuHeading");
  panel.innerHTML = `
    <div class="card-body">
      <h2 id="ownerMenuHeading" class="h5 fw-bold">Quản lý thực đơn</h2>
      <p id="ownerMenuMessage" class="small" role="status"></p>
      <div class="d-flex flex-wrap align-items-center gap-2 mb-3">
        <span class="small fw-semibold" data-restaurant-status></span>
        <button type="button" class="btn btn-sm btn-outline-dark"
                data-change-restaurant-status disabled>
          Thay đổi trạng thái quán
        </button>
      </div>

      <form id="ownerFoodForm" class="row g-3 mb-3">
        <div class="col-md-3">
          <label for="ownerRestaurant" class="form-label">Nhà hàng</label>
          <select id="ownerRestaurant" class="form-select" required></select>
        </div>
        <div class="col-md-4">
          <label for="ownerFoodName" class="form-label">Tên món</label>
          <input id="ownerFoodName" class="form-control" maxlength="120" required>
        </div>
        <div class="col-md-2">
          <label for="ownerFoodPrice" class="form-label">Giá (VNĐ)</label>
          <input id="ownerFoodPrice" class="form-control" type="number"
                 min="1" max="100000000" step="1" required>
        </div>
        <div class="col-md-3">
          <label for="ownerFoodCategory" class="form-label">Loại món</label>
          <select id="ownerFoodCategory" class="form-select" required>
            <option value="FOOD">Món ăn</option>
            <option value="DRINK">Đồ uống</option>
          </select>
        </div>
        <div class="col-12">
          <label for="ownerFoodImage" class="form-label">Đường dẫn ảnh</label>
          <input id="ownerFoodImage" class="form-control" maxlength="1000"
                 placeholder="/static/trasua.jpg hoặc https://…">
        </div>
        <div class="col-md-3">
          <label for="ownerFoodStock" class="form-label">Tình trạng món</label>
          <select id="ownerFoodStock" class="form-select" required>
            <option value="IN_STOCK">Còn món</option>
            <option value="OUT_OF_STOCK">Hết món</option>
          </select>
        </div>
        <div class="col-12">
          <button id="ownerFoodSave" class="btn btn-dark" type="submit" disabled>
            Thêm món
          </button>
          <button id="ownerFoodCancel" class="btn btn-outline-secondary d-none"
                  type="button">Hủy sửa</button>
          <button id="ownerMenuReload" class="btn btn-outline-dark"
                  type="button">Tải lại</button>
        </div>
      </form>

      <div id="ownerMenuList" class="table-responsive">
        <table class="table table-sm align-middle mb-0">
          <thead>
            <tr><th>Tên món</th><th>Giá</th><th>Loại món</th><th>Tình trạng</th><th>Thao tác</th></tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  `;
  heading.after(panel);

  const find = id => panel.querySelector(`#${id}`);
  const form = find("ownerFoodForm");
  const restaurant = find("ownerRestaurant");
  const name = find("ownerFoodName");
  const price = find("ownerFoodPrice");
  const image = find("ownerFoodImage");
  const category = find("ownerFoodCategory");
  const stock = find("ownerFoodStock");
  const save = find("ownerFoodSave");
  const cancel = find("ownerFoodCancel");
  const reload = find("ownerMenuReload");
  const message = find("ownerMenuMessage");
  const rows = panel.querySelector("tbody");
  const endpoint = "/api/v1/restaurant/menu";

  const statusLabel = panel.querySelector("[data-restaurant-status]");
  const statusButton = panel.querySelector("[data-change-restaurant-status]");
  let restaurants = [];
  let foods = [];
  let editingId = null;
  let busy = false;

  function status(text, error = false) {
    message.textContent = text;
    message.className = error ? "small text-danger" : "small text-muted";
  }

  function renderRestaurantStatus() {
    const selected = restaurants.find(item => item.id === restaurant.value);
    const closed = selected?.status === "CLOSED";
    statusLabel.textContent = selected
      ? (closed ? "Quán đang tạm ngừng nhận đơn" : "Quán đang nhận đơn")
      : "";
    statusButton.textContent = closed ? "Mở nhận đơn" : "Tạm ngừng nhận đơn";
    statusButton.disabled = busy || !selected;
  }

  function setBusy(value) {
    busy = value;
    restaurant.disabled = value;
    save.disabled = value || !restaurant.value;
    cancel.disabled = value;
    reload.disabled = value;
    renderRestaurantStatus();
  }

  function clearEdit() {
    editingId = null;
    name.value = "";
    price.value = "";
    image.value = "";
    category.value = "FOOD";
    stock.value = "IN_STOCK";
    save.textContent = "Thêm món";
    cancel.classList.add("d-none");
  }

  function render() {
    rows.replaceChildren();
    const visible = foods.filter(food => food.restaurant_id === restaurant.value);

    if (!visible.length) {
      const cell = rows.insertRow().insertCell();
      cell.colSpan = 5;
      cell.textContent = restaurant.value ? "Quán chưa có món." : "Chưa có nhà hàng.";
      return;
    }

    for (const food of visible) {
      const row = rows.insertRow();
      row.insertCell().textContent = food.name;
      row.insertCell().textContent = formatMoney(food.price);
      row.insertCell().textContent = food.category === "DRINK" ? "Đồ uống" : "Món ăn";
      row.insertCell().textContent = food.status === "OUT_OF_STOCK" ? "Hết món" : "Còn món";

      const edit = document.createElement("button");
      edit.type = "button";
      edit.className = "btn btn-sm btn-outline-dark";
      edit.textContent = "Sửa";
      edit.setAttribute("aria-label", `Sửa món ${food.name}`);
      edit.addEventListener("click", () => {
        if (busy) return;
        editingId = food.id;
        name.value = food.name;
        price.value = food.price;
        image.value = food.image_url ?? "";
        category.value = food.category === "DRINK" ? "DRINK" : "FOOD";
        stock.value = food.status === "OUT_OF_STOCK" ? "OUT_OF_STOCK" : "IN_STOCK";
        save.textContent = "Lưu thay đổi";
        cancel.classList.remove("d-none");
        name.focus();
      });
      row.insertCell().append(edit);
    }
  }

  async function loadMenu() {
    if (busy) return;
    setBusy(true);
    status("Đang tải thực đơn…");

    try {
      const selected = restaurant.value;
      const data = await api(endpoint);
      foods = data.foods;
      restaurants = data.restaurants;
      restaurant.replaceChildren(...data.restaurants.map(
        item => new Option(item.name, item.id)
      ));
      if (data.restaurants.some(item => item.id === selected)) {
        restaurant.value = selected;
      }
      clearEdit();
      render();
      status(restaurant.value ? "" : "Tài khoản chưa được gắn với nhà hàng.");
    } catch (error) {
      status("Không tải được thực đơn. " + error.message, true);
    } finally {
      setBusy(false);
    }
  }

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (busy || !restaurant.value) return;

    const foodName = name.value.trim();
    if (!foodName) {
      status("Vui lòng nhập tên món.", true);
      name.focus();
      return;
    }

    const base = `${endpoint}/${encodeURIComponent(restaurant.value)}/foods`;
    const path = editingId ? `${base}/${encodeURIComponent(editingId)}` : base;
    const method = editingId ? "PUT" : "POST";

    setBusy(true);
    status("");

    try {
      const saved = await api(path, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: foodName,
          price: price.valueAsNumber,
          image_url: image.value.trim(),
          category: category.value,
          status: stock.value
        })
      });
      foods = [...foods.filter(item => item.id !== saved.id), saved];
      foods.sort((a, b) => a.name.localeCompare(b.name, "vi"));

      clearEdit();
      render();
      status("Đã lưu món vào thực đơn.");
    } catch (error) {
      status(error.message, true);
    } finally {
      setBusy(false);
    }
  });

  restaurant.addEventListener("change", () => {
    clearEdit();
    render();
    renderRestaurantStatus();
  });

  statusButton.addEventListener("click", async () => {
    const selected = restaurants.find(item => item.id === restaurant.value);
    if (busy || !selected) return;

    const nextStatus = selected.status === "CLOSED" ? "OPEN" : "CLOSED";
    setBusy(true);
    status("");

    try {
      const result = await api(`${endpoint}/${encodeURIComponent(selected.id)}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus })
      });
      selected.status = result.status;
      status(result.status === "CLOSED"
        ? "Quán đã tạm ngừng nhận đơn mới."
        : "Quán đã mở nhận đơn mới.");
    } catch (error) {
      status(error.message, true);
    } finally {
      setBusy(false);
    }
  });
  cancel.addEventListener("click", clearEdit);
  reload.addEventListener("click", loadMenu);

  const observer = new MutationObserver(loadWhenVisible);

  function loadWhenVisible() {
    if (view.classList.contains("d-none")) return;
    observer.disconnect();
    void loadMenu();
  }

  observer.observe(view, { attributes: true, attributeFilter: ["class"] });
  loadWhenVisible();
})();