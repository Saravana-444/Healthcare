from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import sqlite3, os, requests, smtplib, csv
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app  = Flask(__name__)
CORS(app)

GMAIL_USER     = os.environ.get('GMAIL_USER', '')
GMAIL_PASSWORD = os.environ.get('GMAIL_PASSWORD', '')
DB_PATH        = 'database/vynox.db'
CSV_FILE       = 'A_Z_medicines_dataset_of_India.csv'

# ══════════════════════════════════════════════════════
#  DATABASE SETUP
# ══════════════════════════════════════════════════════
def init_db():
    os.makedirs('database', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS scans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        medicine_name TEXT, barcode TEXT, use_for TEXT,
        dosage TEXT, side_effects TEXT, warning TEXT,
        confidence INTEGER, source TEXT, scanned_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guardian_name TEXT, guardian_email TEXT,
        medicine_name TEXT, sent_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_medicines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        barcode TEXT UNIQUE, medicine_name TEXT, brand TEXT,
        use_for TEXT, dosage TEXT, side_effects TEXT,
        warning TEXT, submitted_at TEXT)''')
    conn.commit()
    conn.close()

def save_scan(med, barcode='manual', source='local'):
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute('''INSERT INTO scans
            (medicine_name,barcode,use_for,dosage,side_effects,warning,confidence,source,scanned_at)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (med.get('name',''), barcode, med.get('use',''),
             med.get('dose',''), med.get('side',''), med.get('warning',''),
             med.get('confidence',0), source,
             datetime.now().strftime('%Y-%m-%d %H:%M')))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB error: {e}")

def get_history():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        'SELECT * FROM scans ORDER BY scanned_at DESC LIMIT 100').fetchall()
    conn.close()
    return [{'id':r[0],'name':r[1],'barcode':r[2],'use':r[3],
             'dose':r[4],'side':r[5],'warning':r[6],
             'confidence':r[7],'source':r[8],'time':r[9]} for r in rows]

# ══════════════════════════════════════════════════════
#  BUILT-IN DATABASE — each medicine is SEPARATE
#  NO shared data between medicines — this fixes the bug
# ══════════════════════════════════════════════════════
MEDICINES = {
    "MED001": {
        "id": "MED001",
        "name": "Metformin 500mg",
        "brand": "Glycomet / Glucophage",
        "generic": "Metformin Hydrochloride",
        "manufacturer": "Sun Pharma",
        "use": "Type 2 Diabetes — controls blood sugar levels",
        "class": "Biguanide / Antidiabetic",
        "dose": "1 tablet · Twice daily",
        "when": "After meals (breakfast and dinner)",
        "side": "Nausea, stomach upset, diarrhoea, metallic taste",
        "type": "Prescription (Rx)",
        "confidence": 94,
        "warning": "Avoid alcohol completely. Never take on empty stomach. Stop and call doctor if unusual tiredness or muscle pain (sign of lactic acidosis)."
    },
    "MED002": {
        "id": "MED002",
        "name": "Glimepiride 2mg",
        "brand": "Amaryl / Glimestar / Glimpid",
        "generic": "Glimepiride",
        "manufacturer": "Sanofi India",
        "use": "Type 2 Diabetes — stimulates insulin release",
        "class": "Sulfonylurea / Antidiabetic",
        "dose": "1 tablet · Once daily",
        "when": "Before breakfast",
        "side": "Low blood sugar (hypoglycaemia), dizziness, weight gain",
        "type": "Prescription (Rx)",
        "confidence": 91,
        "warning": "Can cause dangerously low blood sugar. Always carry glucose tablets or sugar. Do not skip meals."
    },
    "MED003": {
        "id": "MED003",
        "name": "Paracetamol 500mg",
        "brand": "Crocin / Calpol / Dolo 500 / Pyrigesic",
        "generic": "Acetaminophen / Paracetamol",
        "manufacturer": "GSK / Micro Labs",
        "use": "Fever and mild to moderate pain relief",
        "class": "Analgesic / Antipyretic",
        "dose": "1 to 2 tablets · Every 6 hours",
        "when": "With or without food, as needed",
        "side": "Very rare at normal doses. Liver damage if overdosed.",
        "type": "OTC (Over the Counter)",
        "confidence": 97,
        "warning": "Do NOT exceed 8 tablets (4g) in 24 hours. Do NOT combine with other medicines containing paracetamol. Dangerous with alcohol."
    },
    "MED004": {
        "id": "MED004",
        "name": "Dolo 650mg",
        "brand": "Dolo 650",
        "generic": "Paracetamol 650mg",
        "manufacturer": "Micro Labs",
        "use": "High fever, body pain, post-vaccination fever",
        "class": "Analgesic / Antipyretic",
        "dose": "1 tablet · Every 4 to 6 hours",
        "when": "With or without food, as needed",
        "side": "Very rare at normal doses",
        "type": "OTC (Over the Counter)",
        "confidence": 97,
        "warning": "Do NOT take more than 6 tablets in 24 hours. Do NOT combine with Crocin or other paracetamol medicines. See doctor if fever continues beyond 3 days."
    },
    "MED005": {
        "id": "MED005",
        "name": "Aspirin 75mg",
        "brand": "Ecosprin / Aspirin Cardio / Disprin",
        "generic": "Acetylsalicylic Acid",
        "manufacturer": "USV / Bayer",
        "use": "Prevention of heart attack and blood clots",
        "class": "Antiplatelet / NSAID",
        "dose": "1 tablet · Once daily",
        "when": "After evening meal",
        "side": "Stomach irritation, increased bleeding risk, nausea",
        "type": "Prescription (Rx)",
        "confidence": 96,
        "warning": "Increases bleeding risk — inform surgeon before any operation. Do NOT give to children under 16. Avoid if you have stomach ulcers."
    },
    "MED006": {
        "id": "MED006",
        "name": "Ibuprofen 400mg",
        "brand": "Brufen / Combiflam / Ibugesic",
        "generic": "Ibuprofen",
        "manufacturer": "Abbott India",
        "use": "Pain relief, fever, inflammation, menstrual cramps",
        "class": "NSAID / Anti-inflammatory",
        "dose": "1 tablet · Three times daily",
        "when": "After meals — never on empty stomach",
        "side": "Stomach irritation, nausea, headache, indigestion",
        "type": "OTC / Prescription",
        "confidence": 93,
        "warning": "ALWAYS take with food. Avoid if you have kidney problems or stomach ulcers. Do NOT use in last 3 months of pregnancy."
    },
    "MED007": {
        "id": "MED007",
        "name": "Diclofenac 50mg",
        "brand": "Voveran / Dicloran / Reactin",
        "generic": "Diclofenac Sodium",
        "manufacturer": "Novartis India",
        "use": "Joint pain, arthritis, back pain, dental pain",
        "class": "NSAID / Anti-inflammatory",
        "dose": "1 tablet · Twice or three times daily",
        "when": "After meals",
        "side": "Stomach pain, indigestion, dizziness, headache",
        "type": "Prescription (Rx)",
        "confidence": 92,
        "warning": "Always take with food. Do not use for more than 7 days without doctor advice. Risk of stomach bleeding with long-term use."
    },
    "MED008": {
        "id": "MED008",
        "name": "Amoxicillin 500mg",
        "brand": "Mox / Novamox / Amoxil / Amoxyclav",
        "generic": "Amoxicillin Trihydrate",
        "manufacturer": "Cipla / Ranbaxy",
        "use": "Bacterial infections — throat, ear, chest, urinary tract",
        "class": "Penicillin Antibiotic",
        "dose": "1 capsule · Three times daily (every 8 hours)",
        "when": "With or without food",
        "side": "Diarrhoea, skin rash, nausea, vomiting",
        "type": "Prescription (Rx)",
        "confidence": 95,
        "warning": "Complete the FULL course even if you feel better. Stopping early causes resistant bacteria. Tell doctor if allergic to penicillin."
    },
    "MED009": {
        "id": "MED009",
        "name": "Azithromycin 500mg",
        "brand": "Azithral / Zithromax / Azee",
        "generic": "Azithromycin Dihydrate",
        "manufacturer": "Alembic Pharma / Cipla",
        "use": "Chest infections, skin infections, typhoid, sinusitis",
        "class": "Macrolide Antibiotic",
        "dose": "1 tablet · Once daily for 3 to 5 days",
        "when": "1 hour before or 2 hours after food",
        "side": "Nausea, diarrhoea, stomach cramps, headache",
        "type": "Prescription (Rx)",
        "confidence": 94,
        "warning": "Complete the full course. Do NOT take with antacids — wait 2 hours. Rare but serious risk of abnormal heart rhythm."
    },
    "MED010": {
        "id": "MED010",
        "name": "Ciprofloxacin 500mg",
        "brand": "Ciplox / Cifran / Ciprobid",
        "generic": "Ciprofloxacin Hydrochloride",
        "manufacturer": "Cipla",
        "use": "UTI, typhoid, diarrhoea, bone and joint infections",
        "class": "Fluoroquinolone Antibiotic",
        "dose": "1 tablet · Twice daily (every 12 hours)",
        "when": "With or without food",
        "side": "Nausea, dizziness, tendon pain, sensitivity to sunlight",
        "type": "Prescription (Rx)",
        "confidence": 93,
        "warning": "Do NOT take antacids within 2 hours. Avoid excessive sunlight — use sunscreen. NOT safe for children or pregnant women."
    },
    "MED011": {
        "id": "MED011",
        "name": "Amlodipine 5mg",
        "brand": "Amlip / Amlong / Norvasc / Amlovas",
        "generic": "Amlodipine Besylate",
        "manufacturer": "Dr. Reddy's / Pfizer",
        "use": "High blood pressure, angina (chest pain)",
        "class": "Calcium Channel Blocker / Antihypertensive",
        "dose": "1 tablet · Once daily",
        "when": "Same time every day, with or without food",
        "side": "Ankle swelling, flushing, dizziness, palpitations",
        "type": "Prescription (Rx)",
        "confidence": 91,
        "warning": "Do NOT stop suddenly — can cause rebound hypertension. May cause dizziness — avoid driving initially. Avoid grapefruit juice."
    },
    "MED012": {
        "id": "MED012",
        "name": "Telmisartan 40mg",
        "brand": "Telma / Telmikind / Telsar",
        "generic": "Telmisartan",
        "manufacturer": "Glenmark / Lupin",
        "use": "High blood pressure, kidney protection in diabetics",
        "class": "ARB / Angiotensin Receptor Blocker",
        "dose": "1 tablet · Once daily",
        "when": "With or without food",
        "side": "Dizziness, back pain, sinusitis, diarrhoea",
        "type": "Prescription (Rx)",
        "confidence": 90,
        "warning": "Do NOT use during pregnancy — can harm baby. Monitor kidney function and potassium levels regularly."
    },
    "MED013": {
        "id": "MED013",
        "name": "Atorvastatin 10mg",
        "brand": "Lipitor / Atorva / Storvas / Aztor",
        "generic": "Atorvastatin Calcium",
        "manufacturer": "Pfizer / Ranbaxy",
        "use": "High cholesterol, heart disease prevention",
        "class": "Statin / Lipid-lowering agent",
        "dose": "1 tablet · Once daily",
        "when": "Evening meal or bedtime",
        "side": "Muscle pain, liver enzyme changes, headache, nausea",
        "type": "Prescription (Rx)",
        "confidence": 92,
        "warning": "Report any unexplained muscle pain or weakness to doctor immediately. Avoid grapefruit juice. Regular liver tests needed."
    },
    "MED014": {
        "id": "MED014",
        "name": "Omeprazole 20mg",
        "brand": "Omez / Ocid / Omesec / Prilosec",
        "generic": "Omeprazole",
        "manufacturer": "Abbott India / Dr. Reddy's",
        "use": "Acid reflux, GERD, stomach ulcers, heartburn",
        "class": "Proton Pump Inhibitor (PPI)",
        "dose": "1 capsule · Once daily",
        "when": "30 minutes before breakfast on empty stomach",
        "side": "Headache, diarrhoea, nausea, flatulence",
        "type": "Prescription (Rx)",
        "confidence": 93,
        "warning": "Must be taken 30 min BEFORE breakfast for best effect. Long-term use may cause low B12 and magnesium. Do NOT crush capsule."
    },
    "MED015": {
        "id": "MED015",
        "name": "Pantoprazole 40mg",
        "brand": "Pan 40 / Pantocid / Pantop / Nexpro",
        "generic": "Pantoprazole Sodium",
        "manufacturer": "Alkem Labs / Sun Pharma",
        "use": "Acidity, GERD, stomach and duodenal ulcers",
        "class": "Proton Pump Inhibitor (PPI)",
        "dose": "1 tablet · Once daily",
        "when": "30 to 60 minutes before first meal",
        "side": "Headache, diarrhoea, flatulence, dizziness",
        "type": "Prescription (Rx)",
        "confidence": 92,
        "warning": "Swallow tablet whole — do NOT crush or chew. Long-term use may affect bone density. Inform doctor if taking for more than 2 months."
    },
    "MED016": {
        "id": "MED016",
        "name": "Levothyroxine 50mcg",
        "brand": "Thyronorm / Eltroxin / Thyrox",
        "generic": "Levothyroxine Sodium",
        "manufacturer": "Abbott India / Glaxo",
        "use": "Hypothyroidism — underactive thyroid gland",
        "class": "Thyroid Hormone Replacement",
        "dose": "1 tablet · Once daily",
        "when": "Empty stomach, 30 to 60 minutes before breakfast",
        "side": "Palpitations, sweating, tremor (only if dose too high)",
        "type": "Prescription (Rx)",
        "confidence": 95,
        "warning": "Take on EMPTY STOMACH every morning. Do NOT take within 4 hours of calcium, iron, or antacids. Get blood test every 6 months."
    },
    "MED017": {
        "id": "MED017",
        "name": "Cetirizine 10mg",
        "brand": "Zyrtec / Cetzine / Alerid / Okacet",
        "generic": "Cetirizine Hydrochloride",
        "manufacturer": "UCB / Cipla",
        "use": "Allergies, hay fever, hives, runny nose, watery eyes",
        "class": "Antihistamine / Anti-allergy",
        "dose": "1 tablet · Once daily",
        "when": "At night (causes drowsiness)",
        "side": "Drowsiness, dry mouth, headache, fatigue",
        "type": "OTC (Over the Counter)",
        "confidence": 95,
        "warning": "Causes drowsiness — do NOT drive or operate machinery. Avoid alcohol. Safe for most adults and children above 6 years."
    },
    "MED018": {
        "id": "MED018",
        "name": "Montelukast 10mg",
        "brand": "Montair / Singulair / Montek",
        "generic": "Montelukast Sodium",
        "manufacturer": "Cipla / MSD",
        "use": "Asthma prevention, allergic rhinitis",
        "class": "Leukotriene Receptor Antagonist",
        "dose": "1 tablet · Once daily",
        "when": "At night",
        "side": "Headache, stomach pain, mood changes, sleep problems",
        "type": "Prescription (Rx)",
        "confidence": 91,
        "warning": "Report any mood changes, depression, or unusual behaviour to doctor immediately. This is NOT a rescue inhaler — do NOT use for sudden asthma attacks."
    },
    "MED019": {
        "id": "MED019",
        "name": "Clopidogrel 75mg",
        "brand": "Plavix / Clopilet / Deplatt / Clopicard",
        "generic": "Clopidogrel Bisulfate",
        "manufacturer": "Sanofi / Sun Pharma",
        "use": "Prevention of heart attack and stroke, after stent placement",
        "class": "Antiplatelet Agent",
        "dose": "1 tablet · Once daily",
        "when": "With or without food",
        "side": "Bleeding, bruising, stomach pain, headache",
        "type": "Prescription (Rx)",
        "confidence": 93,
        "warning": "Do NOT stop without doctor's advice — can trigger heart attack. Tell surgeon before any operation. Increases bleeding time significantly."
    },
    "MED020": {
        "id": "MED020",
        "name": "Vitamin D3 60000 IU",
        "brand": "Calcirol / D-Rise / Uprise D3",
        "generic": "Cholecalciferol",
        "manufacturer": "Cadila / Sun Pharma",
        "use": "Vitamin D deficiency, bone health, immunity",
        "class": "Vitamin / Nutritional Supplement",
        "dose": "1 sachet dissolved in water · Once a week",
        "when": "With a fatty meal for best absorption",
        "side": "Nausea or constipation if overdosed",
        "type": "OTC / Prescription",
        "confidence": 90,
        "warning": "Do NOT take daily — this is a weekly dose. Take with a fatty meal (like milk or ghee) for proper absorption. Overdose can cause kidney problems."
    },
}

# ══════════════════════════════════════════════════════
#  CSV DATASET LOADER — loads Kaggle Indian medicines CSV
# ══════════════════════════════════════════════════════
csv_db = {}

def load_csv():
    global csv_db
    if not os.path.exists(CSV_FILE):
        print(f"⚠️  CSV not found: {CSV_FILE}")
        print(f"    Place the file in the same folder as app.py")
        return

    try:
        count = 0
        with open(CSV_FILE, encoding='utf-8', errors='ignore') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Get name from whichever column exists
                name = (row.get('name') or row.get('Name') or
                        row.get('medicine_name') or '').strip()
                if not name or name.lower() in ('nan', 'none', ''):
                    continue

                # Skip if already in built-in db
                if name.lower() in [m['name'].lower() for m in MEDICINES.values()]:
                    continue

                # Collect uses
                uses = []
                for i in range(10):
                    v = row.get(f'use{i}','').strip()
                    if v and v.lower() not in ('nan','none',''):
                        uses.append(v)

                # Collect side effects
                sides = []
                for i in range(15):
                    v = row.get(f'sideEffect{i}','').strip()
                    if v and v.lower() not in ('nan','none',''):
                        sides.append(v)

                # Collect substitutes
                subs = []
                for i in range(5):
                    v = row.get(f'substitute{i}','').strip()
                    if v and v.lower() not in ('nan','none',''):
                        subs.append(v)

                therapeutic = row.get('Therapeutic Class','').strip()
                chemical    = row.get('Chemical Class','').strip()
                habit       = row.get('Habit Forming','').strip()

                warning = ''
                if habit and habit.lower() not in ('no','nan','none',''):
                    warning += f"Habit forming: {habit}. "
                if subs:
                    warning += f"Available substitutes: {', '.join(subs[:2])}. "
                warning += "Always consult your doctor before taking this medicine."

                csv_db[name.lower()] = {
                    "id":         f"CSV_{count}",
                    "name":       name,
                    "brand":      name,
                    "generic":    chemical or "See packaging",
                    "manufacturer": "See packaging",
                    "use":        ', '.join(uses[:3]) if uses else (therapeutic or "See packaging"),
                    "class":      therapeutic or chemical or "Medicine",
                    "dose":       "As directed by doctor",
                    "when":       "As directed by doctor",
                    "side":       ', '.join(sides[:4]) if sides else "Consult your doctor",
                    "type":       "See packaging",
                    "confidence": 82,
                    "warning":    warning,
                    "source":     "Kaggle Dataset"
                }
                count += 1

        print(f"✅ Loaded {count:,} medicines from Kaggle CSV")
    except Exception as e:
        print(f"❌ CSV load error: {e}")


# ══════════════════════════════════════════════════════
#  MEDICINE FINDER — the single function that finds
#  any medicine by ID, name, or brand — NO bugs
# ══════════════════════════════════════════════════════
def find_medicine(query):
    if not query:
        return None

    q = query.strip()

    # 1. Exact ID match (MED001 etc.)
    upper = q.upper()
    if upper in MEDICINES:
        return MEDICINES[upper]

    # 2. Exact name match in built-in
    lower = q.lower()
    for med in MEDICINES.values():
        if med['name'].lower() == lower:
            return med

    # 3. Exact brand match in built-in
    for med in MEDICINES.values():
        brands = [b.strip().lower() for b in med['brand'].split('/')]
        if lower in brands:
            return med

    # 4. Partial name match in built-in (medicine name contains query)
    for med in MEDICINES.values():
        if lower in med['name'].lower():
            return med

    # 5. Partial brand match in built-in
    for med in MEDICINES.values():
        if lower in med['brand'].lower():
            return med

    # 6. Exact name match in CSV
    if lower in csv_db:
        return csv_db[lower]

    # 7. Partial match in CSV
    for name_key, med in csv_db.items():
        if lower in name_key:
            return med

    return None


# ══════════════════════════════════════════════════════
#  ONLINE BARCODE LOOKUP
# ══════════════════════════════════════════════════════
def lookup_barcode_online(barcode):
    # Open Food Facts
    try:
        r = requests.get(
            f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json",
            timeout=6, headers={"User-Agent": "VYNOX/1.0"})
        d = r.json()
        if d.get('status') == 1 and d.get('product'):
            p    = d['product']
            name = (p.get('product_name') or p.get('generic_name') or '').strip()
            if name:
                # Try to find better data in our dataset
                better = find_medicine(name)
                if better:
                    return better
                return {
                    "id": "ONLINE",
                    "name":       name,
                    "brand":      p.get('brands', name),
                    "generic":    p.get('generic_name','See packaging'),
                    "manufacturer": p.get('brands','Unknown'),
                    "use":        p.get('categories','See packaging')[:80],
                    "class":      "Medicine",
                    "dose":       p.get('quantity','See packaging'),
                    "when":       "As directed by doctor",
                    "side":       "Consult your doctor",
                    "type":       "See packaging",
                    "confidence": 72,
                    "warning":    "Always read the label carefully. Consult your doctor.",
                    "source":     "Open Food Facts"
                }
    except Exception as e:
        print(f"OFF error: {e}")

    # Open FDA
    try:
        r = requests.get(
            f"https://api.fda.gov/drug/ndc.json?search=product_ndc:{barcode}&limit=1",
            timeout=6)
        d = r.json()
        if d.get('results'):
            res  = d['results'][0]
            name = res.get('brand_name') or res.get('generic_name','')
            if name:
                better = find_medicine(name)
                if better:
                    return better
                return {
                    "id": "ONLINE",
                    "name":       name,
                    "brand":      res.get('brand_name', name),
                    "generic":    res.get('generic_name',''),
                    "manufacturer": res.get('labeler_name','Unknown'),
                    "use":        ', '.join(res.get('route',['See packaging'])),
                    "class":      (res.get('pharm_class') or ['Medicine'])[0],
                    "dose":       res.get('dosage_form','See packaging'),
                    "when":       "As directed by doctor",
                    "side":       "Consult your doctor",
                    "type":       res.get('product_type','Prescription'),
                    "confidence": 78,
                    "warning":    "Always read the label carefully.",
                    "source":     "Open FDA"
                }
    except Exception as e:
        print(f"FDA error: {e}")

    return None


# ══════════════════════════════════════════════════════
#  EMAIL
# ══════════════════════════════════════════════════════
def send_email(to_email, guardian_name, med, relation):
    if not GMAIL_USER or not GMAIL_PASSWORD:
        return False, "Gmail not configured in .env"
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"VYNOX Medicine Alert — {med.get('name','')}"
        msg['From']    = GMAIL_USER
        msg['To']      = to_email
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">
          <div style="background:#04111f;padding:24px;text-align:center;border-radius:12px 12px 0 0;">
            <h1 style="color:#00c8b4;margin:0;letter-spacing:4px;font-size:28px;">VYNOX</h1>
            <p style="color:#88a0b4;font-size:11px;margin:4px 0 0;letter-spacing:2px;">AI MEDICATION SAFETY</p>
          </div>
          <div style="background:#ffffff;padding:28px;border-radius:0 0 12px 12px;border:1px solid #e5e7eb;">
            <p style="font-size:15px;color:#374151;">Hello <strong>{guardian_name}</strong> ({relation}),</p>
            <p style="color:#6b7280;">A medicine has been scanned and shared with you:</p>
            <div style="background:#f0fdf9;border-left:4px solid #00c8b4;padding:18px;margin:18px 0;border-radius:0 8px 8px 0;">
              <h2 style="color:#00c8b4;margin:0 0 12px;font-size:20px;">{med.get('name','')}</h2>
              <table style="width:100%;font-size:14px;color:#374151;">
                <tr><td style="padding:4px 0;"><b>Used For:</b></td><td>{med.get('use','')}</td></tr>
                <tr><td style="padding:4px 0;"><b>Dosage:</b></td><td>{med.get('dose','')}</td></tr>
                <tr><td style="padding:4px 0;"><b>When:</b></td><td>{med.get('when','')}</td></tr>
                <tr><td style="padding:4px 0;"><b>Side Effects:</b></td><td>{med.get('side','')}</td></tr>
              </table>
            </div>
            <div style="background:#fff7ed;border-left:4px solid #f97316;padding:18px;border-radius:0 8px 8px 0;">
              <p style="color:#f97316;font-weight:bold;margin:0 0 6px;">⚠️ Warning</p>
              <p style="color:#374151;margin:0;font-size:14px;">{med.get('warning','')}</p>
            </div>
            <p style="color:#9ca3af;font-size:11px;margin-top:24px;padding-top:16px;border-top:1px solid #f3f4f6;">
              Sent via VYNOX AI Medication Safety System. Always consult a licensed healthcare professional.
            </p>
          </div>
        </div>"""
        msg.attach(MIMEText(html, 'html'))
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls()
            s.login(GMAIL_USER, GMAIL_PASSWORD)
            s.sendmail(GMAIL_USER, to_email, msg.as_string())
        return True, "Sent!"
    except Exception as e:
        return False, str(e)


# ══════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════

@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/medicine/<path:med_id>')
def get_medicine(med_id):
    med = find_medicine(med_id)
    if med:
        return jsonify(med)
    return jsonify({"error": f"Medicine not found: {med_id}"}), 404


@app.route('/api/barcode/<barcode>')
def barcode_route(barcode):
    # 1. Check user-submitted barcodes
    try:
        conn = sqlite3.connect(DB_PATH)
        row  = conn.execute(
            'SELECT * FROM user_medicines WHERE barcode=?', (barcode,)).fetchone()
        conn.close()
        if row:
            med = {
                "id": f"USER{row[0]}", "name": row[2], "brand": row[3],
                "generic": "", "manufacturer": "Community",
                "use": row[4], "class": "Medicine",
                "dose": row[5], "when": "As directed",
                "side": row[6], "type": "See packaging",
                "confidence": 88, "warning": row[7], "source": "Community Database"
            }
            save_scan(med, barcode, 'Community DB')
            return jsonify(med)
    except Exception:
        pass

    # 2. Try online APIs
    result = lookup_barcode_online(barcode)
    if result:
        save_scan(result, barcode, result.get('source', 'Online'))
        return jsonify(result)

    return jsonify({"error": "Barcode not found in any database", "barcode": barcode}), 404


@app.route('/api/search')
def search():
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])

    lower    = q.lower()
    results  = []
    seen     = set()

    # Built-in DB first — highest quality
    for med_id, med in MEDICINES.items():
        if (lower in med['name'].lower() or
            lower in med['brand'].lower() or
            lower in med['use'].lower()):
            if med['name'] not in seen:
                results.append({**med})
                seen.add(med['name'])

    # CSV dataset
    for name_key, med in csv_db.items():
        if len(results) >= 15:
            break
        if med['name'] in seen:
            continue
        if (lower in name_key or
            lower in med.get('use','').lower() or
            lower in med.get('class','').lower()):
            results.append({**med})
            seen.add(med['name'])

    return jsonify(results[:15])


@app.route('/api/all-medicines')
def all_medicines():
    return jsonify(MEDICINES)


@app.route('/api/interaction', methods=['POST'])
def interaction():
    meds         = request.json.get('medicines', [])
    interactions = [
        {
            "drugs": ["Aspirin 75mg", "Warfarin"],
            "level": "danger",
            "message": "DANGER: Aspirin + Warfarin causes severe bleeding risk. Go to doctor immediately."
        },
        {
            "drugs": ["Metformin 500mg", "Alcohol"],
            "level": "danger",
            "message": "DANGER: Metformin + Alcohol can cause life-threatening lactic acidosis."
        },
        {
            "drugs": ["Aspirin 75mg", "Ibuprofen 400mg"],
            "level": "danger",
            "message": "DANGER: Both damage stomach and thin blood together. Risk of internal bleeding."
        },
        {
            "drugs": ["Aspirin 75mg", "Paracetamol 500mg"],
            "level": "warn",
            "message": "CAUTION: Increases stomach irritation. Take only if prescribed together."
        },
        {
            "drugs": ["Amlodipine 5mg", "Atorvastatin 10mg"],
            "level": "warn",
            "message": "CAUTION: May raise Atorvastatin blood levels. Watch for muscle pain."
        },
        {
            "drugs": ["Levothyroxine 50mcg", "Calcium"],
            "level": "warn",
            "message": "CAUTION: Calcium blocks Levothyroxine absorption. Take at least 4 hours apart."
        },
        {
            "drugs": ["Clopidogrel 75mg", "Omeprazole 20mg"],
            "level": "warn",
            "message": "CAUTION: Omeprazole reduces Clopidogrel effectiveness. Ask doctor about Pantoprazole."
        },
    ]
    for inter in interactions:
        if inter['level'] == 'danger' and all(d in meds for d in inter['drugs']):
            return jsonify(inter)
    for inter in interactions:
        if all(d in meds for d in inter['drugs']):
            return jsonify(inter)
    return jsonify({
        "level": "safe",
        "message": "No known dangerous interactions found. Always consult your doctor."
    })


@app.route('/api/history')
def history():
    return jsonify(get_history())


@app.route('/api/save-scan', methods=['POST'])
def save_scan_route():
    data = request.json
    save_scan(data, data.get('barcode', 'manual'), 'manual')
    return jsonify({"success": True})


@app.route('/api/submit-medicine', methods=['POST'])
def submit_medicine():
    data    = request.json
    barcode = data.get('barcode', '').strip()
    name    = data.get('name', '').strip()
    if not barcode or not name:
        return jsonify({"error": "Barcode and name are required"}), 400
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            '''INSERT OR REPLACE INTO user_medicines
               (barcode,medicine_name,brand,use_for,dosage,side_effects,warning,submitted_at)
               VALUES (?,?,?,?,?,?,?,?)''',
            (barcode, name, data.get('brand',''), data.get('use',''),
             data.get('dose',''), data.get('side',''), data.get('warning',''),
             datetime.now().strftime('%Y-%m-%d %H:%M')))
        conn.commit()
        conn.close()
        return jsonify({"success": True, "message": "Medicine added!"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/send-alert', methods=['POST'])
def send_alert():
    data     = request.json
    gname    = data.get('guardian_name', 'Guardian')
    gemail   = data.get('guardian_email', '')
    relation = data.get('relation', 'Family')
    med      = data.get('medicine', {})

    print(f"\n🚨 ALERT → {gname} ({gemail}) | {med.get('name','')}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        'INSERT INTO alerts (guardian_name,guardian_email,medicine_name,sent_at) VALUES (?,?,?,?)',
        (gname, gemail, med.get('name',''), datetime.now().strftime('%Y-%m-%d %H:%M')))
    conn.commit()
    conn.close()

    if GMAIL_USER and GMAIL_PASSWORD and gemail:
        ok, msg = send_email(gemail, gname, med, relation)
        return jsonify({
            "success": True,
            "message": f"✅ Email sent to {gemail}!" if ok else f"⚠️ Saved. Email error: {msg}",
            "email_sent": ok
        })
    return jsonify({
        "success": True,
        "message": f"✅ Alert saved for {gname}. Add Gmail in .env to enable emails.",
        "email_sent": False
    })


@app.route('/api/stats')
def stats():
    conn   = sqlite3.connect(DB_PATH)
    scans  = conn.execute('SELECT COUNT(*) FROM scans').fetchone()[0]
    alerts = conn.execute('SELECT COUNT(*) FROM alerts').fetchone()[0]
    userm  = conn.execute('SELECT COUNT(*) FROM user_medicines').fetchone()[0]
    conn.close()
    return jsonify({
        "total_scans":    scans,
        "total_alerts":   alerts,
        "user_medicines": userm,
        "csv_medicines":  len(csv_db),
        "builtin":        len(MEDICINES),
        "total":          len(MEDICINES) + len(csv_db)
    })


if __name__ == '__main__':
    init_db()
    load_csv()
    total = len(MEDICINES) + len(csv_db)
    print(f"\n{'='*55}")
    print(f"  🏥  VYNOX — AI Medication Safety")
    print(f"  💊  Built-in: {len(MEDICINES)}  |  CSV: {len(csv_db):,}  |  Total: {total:,}")
    print(f"  🌐  http://localhost:5000")
    print(f"{'='*55}\n")
    app.run(debug=True, port=5000)
