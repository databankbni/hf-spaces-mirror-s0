import express from "express";
import cors from "cors";
import sqlite3 from "sqlite3";

const app = express();
const db = new sqlite3.Database("messages.db");

// ✅ Middleware
app.use(cors());
app.use(express.json());

// ✅ Create table
db.run(`
  CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    email TEXT,
    message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  )
`);
// ✅ 👉 ADD YOUR API HERE
app.post("/contact", (req, res) => {
  console.log("Incoming data:", req.body); // 👈 DEBUG

  const { name, email, message } = req.body;

  db.run(
    "INSERT INTO messages (name, email, message) VALUES (?, ?, ?)",
    [name, email, message],
    function (err) {
      if (err) {
        console.log("DB ERROR:", err);
        return res.status(500).json({ error: err.message });
      }

      console.log("Inserted ID:", this.lastID); // 👈 DEBUG
      res.json({ message: "Message saved successfully" });
    }
  );
});
// GET all messages
app.get("/messages", (req, res) => {
  db.all("SELECT * FROM messages ORDER BY id DESC", [], (err, rows) => {
    if (err) return res.status(500).json({ error: err.message });
    res.json(rows);
  });
});

// DELETE message
app.delete("/messages/:id", (req, res) => {
  const id = req.params.id;

  db.run("DELETE FROM messages WHERE id = ?", [id], function (err) {
    if (err) return res.status(500).json({ error: err.message });
    res.json({ message: "Deleted successfully" });
  });
});

// ✅ Start server (ALWAYS LAST)
app.listen(5001, () => {
  console.log("Server running on http://localhost:5001");
});