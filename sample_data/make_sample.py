"""Generates the synthetic messy customer CSV (no real people). Run: python sample_data/make_sample.py"""
import csv, random
from pathlib import Path

random.seed(7)
first = ["Ayesha", "Bilal", "Sara", "Usman", "Hina", "Zain", "Maryam", "Ali", "Noor", "Hamza"]
last = ["Khan", "Ahmed", "Shah", "Malik", "Iqbal", "Raza"]
cities = ["Peshawar", "Lahore", "Karachi", "Islamabad", "Quetta"]
rows = []
for i in range(1, 31):
    name = f"{random.choice(first)} {random.choice(last)}"
    if i % 4 == 0: name = f"  {name} "                      # extra spaces
    reg = f"{random.randint(1,12):02d}/{random.randint(1,12):02d}/2026" if i % 5 else "03/04/2026"
    spend = random.choice(["1200.50", "$980.00", "2,450.75", "300", "NA", "N/A"])
    email = f"user{i}@example.com" if i % 6 else random.choice(["", "-", "null"])
    rows.append([f"{i:05d}", name, email, random.choice(cities) + (" " if i % 7 == 0 else ""), reg, spend])
rows[9][4] = "not provided yet"       # invalid date
rows.append(rows[2][:])              # exact duplicate
rows.append(rows[5][:])              # exact duplicate
out = Path(__file__).parent / "messy_customers.csv"
with out.open("w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["customer_id", "customer_name", "email", "city", "registration_date", "total_spend"])
    w.writerows(rows)
print("wrote", out, len(rows), "rows")
