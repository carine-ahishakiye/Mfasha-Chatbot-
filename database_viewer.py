import sqlite3
import tkinter as tk
from tkinter import ttk

conn = sqlite3.connect("mfasha.db")
cursor = conn.cursor()

root = tk.Tk()
root.title("MFASHA - Database Explorer")
root.geometry("1100x650")

tk.Label(
    root,
    text="MFASHA DATABASE EXPLORER",
    font=("Arial", 18, "bold")
).pack(pady=10)

frame = tk.Frame(root)
frame.pack(fill="both", expand=True, padx=15, pady=10)

tables = ["questions", "answers", "feedback", "officers", "expert_reviews"]

selected = tk.StringVar(value=tables[0])

dropdown = ttk.Combobox(
    root, textvariable=selected,
    values=tables, state="readonly", width=30
)
dropdown.pack(pady=5)

tree = ttk.Treeview(frame, show="headings")
tree.pack(side="left", fill="both", expand=True)

scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
scroll.pack(side="right", fill="y")
tree.configure(yscrollcommand=scroll.set)

def show_table(event=None):
    table = selected.get()

    cursor.execute(f'PRAGMA table_info("{table}")')
    columns = [row[1] for row in cursor.fetchall()]

    cursor.execute(f'SELECT * FROM "{table}" LIMIT 100')
    records = cursor.fetchall()

    tree.delete(*tree.get_children())
    tree["columns"] = columns

    for column in columns:
        tree.heading(column, text=column)
        tree.column(column, width=160, anchor="w")

    for record in records:
        tree.insert("", "end", values=record)

dropdown.bind("<<ComboboxSelected>>", show_table)
show_table()

root.mainloop()
conn.close()
