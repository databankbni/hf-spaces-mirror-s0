/* Điểm khởi động: nạp dữ liệu ban đầu + auto refresh thiết bị */

loadTools();
loadMedia();
loadDevices();
setInterval(loadDevices, 30000);
