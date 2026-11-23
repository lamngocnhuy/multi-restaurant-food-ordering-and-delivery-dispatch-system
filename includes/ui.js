"use strict";

const byId = id => document.getElementById(id);
const money = new Intl.NumberFormat("vi-VN");
const formatMoney = amount => money.format(amount) + " VNĐ";
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, character => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[character]);
}
function label(labels, code) {
  return Object.hasOwn(labels, code) ? labels[code] : (code || "—");
}
