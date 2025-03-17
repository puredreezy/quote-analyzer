import PyPDF2
import re
import os
from textblob import TextBlob
from datetime import datetime, timedelta

# Set PROJECT_FOLDER to the directory where the script is located
PROJECT_FOLDER = os.path.dirname(os.path.abspath(__file__))

def extract_text_from_pdf(pdf_path):
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                text += page.extract_text()
            return text
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
        return ""

def clean_numeric_string(value):
    """
    Clean a string to extract a numeric value (e.g., '$10,000 USD' -> '10000').
    Handles commas, currency symbols, and unexpected text.
    """
    value = re.sub(r'(?i)(Total|Grand Total|Total Price|Price|Subtotal|Discount|Shipping Cost|VAT)[:\s]*', '', value)
    value = re.sub(r'[^\d.]', '', value)  # Keep only digits and decimal points
    try:
        return float(value)
    except ValueError:
        return None

def analyze_quote(text):
    quote_info = {}

    # Extract Supplier Name
    supplier_pattern = r'Supplier Quote\s*-\s*(.+?)(?:\n|$|Supplier Details)'
    supplier_match = re.search(supplier_pattern, text, re.IGNORECASE)
    quote_info["supplier"] = supplier_match.group(1).strip() if supplier_match else "Unknown"

    # Extract Total Price (prioritize Grand Total over other totals)
    total_price_pattern = r'(Grand Total)[:\s]*\$?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*(USD)?'
    total_price_match = re.search(total_price_pattern, text, re.IGNORECASE)
    if total_price_match:
        price_str = total_price_match.group(0)
        quote_info["total_price"] = clean_numeric_string(price_str)
    else:
        total_price_pattern = r'(Subtotal)[:\s]*\$?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*(USD)?'
        total_price_match = re.search(total_price_pattern, text, re.IGNORECASE)
        if total_price_match:
            price_str = total_price_match.group(0)
            quote_info["total_price"] = clean_numeric_string(price_str)
        else:
            quote_info["total_price"] = None

    # Extract Discount (handle absolute values like -$500)
    discount_pattern = r'Discount[:\s]*-?\$?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*(USD)?'
    discount_match = re.search(discount_pattern, text, re.IGNORECASE)
    if discount_match:
        discount_str = discount_match.group(0)
        quote_info["discount"] = clean_numeric_string(discount_str) or 0.0
    else:
        quote_info["discount"] = 0.0

    # Extract Delivery Lead Time
    delivery_pattern = r'(?:Delivery|Lead Time)\s*\(?Days\)?[:\s]*(?:in|within)?\s*(\d+)\s*(days)?'
    delivery_match = re.search(delivery_pattern, text, re.IGNORECASE)
    quote_info["delivery_days"] = int(delivery_match.group(1)) if delivery_match else None

    # Extract Shipping Cost
    shipping_cost_pattern = r'Shipping(?: Cost)?[:\s]*\$?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s*(USD)?'
    shipping_cost_match = re.search(shipping_cost_pattern, text, re.IGNORECASE)
    if shipping_cost_match:
        cost_str = shipping_cost_match.group(0)
        quote_info["shipping_cost"] = clean_numeric_string(cost_str) or 0.0
    else:
        quote_info["shipping_cost"] = 0.0

    # Extract Payment Terms
    payment_terms_pattern = r'Payment Terms[:\s]*(.*?)(?:\n|$|Lead Time|Shipping)'
    payment_terms_match = re.search(payment_terms_pattern, text, re.IGNORECASE)
    quote_info["payment_terms"] = payment_terms_match.group(1).strip() if payment_terms_match else "Unknown"

    # Extract Warranty Period
    warranty_pattern = r'Warranty[:\s]*(\d+)-?\s*(year|month)s?(?:\s*manufacturers\s*warranty)?'
    warranty_match = re.search(warranty_pattern, text, re.IGNORECASE)
    quote_info["warranty_period"] = warranty_match.group(1) + " " + warranty_match.group(2) if warranty_match else "None"

    # Extract Validity Period
    validity_pattern = r'Valid(?:ity Period| until)[:\s]*(\d{4}-\d{2}-\d{2})'
    validity_match = re.search(validity_pattern, text, re.IGNORECASE)
    quote_info["validity_date"] = validity_match.group(1) if validity_match else None

    # Analyze sentiment
    blob = TextBlob(text)
    quote_info["sentiment"] = blob.sentiment.polarity

    return quote_info

def score_quote(quote):
    score = 0
    red_flags = []

    # Price: Lower price = better score
    if quote["total_price"]:
        score += (20000 - quote["total_price"]) / 1000
    else:
        red_flags.append("Missing total price (critical information)")

    # Delivery: Faster delivery = better score
    if quote["delivery_days"]:
        score += (30 - quote["delivery_days"]) / 5
    else:
        red_flags.append("Missing delivery time (uncertain fulfillment)")

    # Payment Terms: More flexible terms = better score
    if "payment_terms" in quote and quote["payment_terms"] != "Unknown":
        if "60%" in quote["payment_terms"]:
            score += 2
        elif "50%" in quote["payment_terms"]:
            score += 1
        elif "100%" in quote["payment_terms"] or "upfront" in quote["payment_terms"].lower():
            red_flags.append("Upfront payment required (less flexible)")
    else:
        red_flags.append("Missing payment terms (uncertain financial terms)")

    # Warranty: Longer warranty = better score
    if quote["warranty_period"] != "None":
        match = re.match(r'(\d+)\s*(year|month)s?', quote["warranty_period"], re.IGNORECASE)
        if match:
            period = int(match.group(1))
            unit = match.group(2).lower()
            if unit == "year":
                score += period * 2
            elif unit == "month":
                score += period / 6
    else:
        red_flags.append("Missing warranty (potential risk if defective)")

    # Shipping Cost: Lower cost = better score
    if quote["shipping_cost"]:
        if quote["shipping_cost"] > 400:
            red_flags.append(f"High shipping cost (${quote['shipping_cost']})")
        score += (1000 - quote["shipping_cost"]) / 200

    # Validity Period: Check if quote is still valid
    if quote["validity_date"]:
        try:
            validity_date = datetime.strptime(quote["validity_date"], "%Y-%m-%d")
            current_date = datetime.now()
            if validity_date < current_date:
                red_flags.append("Quote expired")
            elif (validity_date - current_date).days < 7:
                red_flags.append("Quote expires soon (within 7 days)")
        except ValueError:
            red_flags.append("Invalid validity date format")

    return score, red_flags

def compare_quotes(quote1, quote2):
    print("\nComparison Results:")
    print(f"Quote 1 ({quote1['supplier']}):")
    print(f"  Total Price: ${quote1['total_price'] if quote1['total_price'] else 'Not specified'}")
    print(f"  Discount: ${quote1['discount']}")
    print(f"  Delivery: {quote1['delivery_days'] if quote1['delivery_days'] else 'Not specified'} days")
    print(f"  Shipping Cost: ${quote1['shipping_cost']}")
    print(f"  Payment Terms: {quote1['payment_terms']}")
    print(f"  Warranty: {quote1['warranty_period']}")
    print(f"  Validity: {quote1['validity_date'] if quote1['validity_date'] else 'Not specified'}")
    print(f"  Sentiment: {quote1['sentiment']}")

    print(f"\nQuote 2 ({quote2['supplier']}):")
    print(f"  Total Price: ${quote2['total_price'] if quote2['total_price'] else 'Not specified'}")
    print(f"  Discount: ${quote2['discount']}")
    print(f"  Delivery: {quote2['delivery_days'] if quote2['delivery_days'] else 'Not specified'} days")
    print(f"  Shipping Cost: ${quote2['shipping_cost']}")
    print(f"  Payment Terms: {quote2['payment_terms']}")
    print(f"  Warranty: {quote2['warranty_period']}")
    print(f"  Validity: {quote2['validity_date'] if quote2['validity_date'] else 'Not specified'}")
    print(f"  Sentiment: {quote2['sentiment']}")

    # Score and flag red flags for each quote
    score1, red_flags1 = score_quote(quote1)
    score2, red_flags2 = score_quote(quote2)

    print("\nRed Flags:")
    print(f"Quote 1 ({quote1['supplier']}):")
    if red_flags1:
        for flag in red_flags1:
            print(f"  - {flag}")
    else:
        print("  No red flags identified.")

    print(f"Quote 2 ({quote2['supplier']}):")
    if red_flags2:
        for flag in red_flags2:
            print(f"  - {flag}")
    else:
        print("  No red flags identified.")

    print("\nRecommendation:")
    print(f"Score for Quote 1 ({quote1['supplier']}): {score1:.2f}")
    print(f"Score for Quote 2 ({quote2['supplier']}): {score2:.2f}")
    if score1 > score2:
        print(f"{quote1['supplier']} is recommended (higher score: {score1:.2f} vs {score2:.2f}).")
    elif score2 > score1:
        print(f"{quote2['supplier']} is recommended (higher score: {score2:.2f} vs {score1:.2f}).")
    else:
        print("Scores are equal. Review red flags and other factors to decide.")

if __name__ == "__main__":
    # Prompt to confirm or change PDF files
    print("Current PDFs in folder:", os.listdir(PROJECT_FOLDER))
    use_default = input("Use default files (quote1.pdf and quote2.pdf)? (yes/no): ").lower()
    if use_default == "no":
        pdf1_name = input("Enter the filename for the first PDF (e.g., quote1.pdf): ")
        pdf2_name = input("Enter the filename for the second PDF (e.g., quote2.pdf): ")
        PDF1_PATH = os.path.join(PROJECT_FOLDER, pdf1_name)
        PDF2_PATH = os.path.join(PROJECT_FOLDER, pdf2_name)
    else:
        PDF1_PATH = os.path.join(PROJECT_FOLDER, "quote1.pdf")
        PDF2_PATH = os.path.join(PROJECT_FOLDER, "quote2.pdf")

    # Check if the PDFs exist
    if not os.path.exists(PDF1_PATH) or not os.path.exists(PDF2_PATH):
        print(f"One or both PDFs not found: {PDF1_PATH} and {PDF2_PATH}")
        print("Please ensure the specified PDFs are in the Project folder.")
    else:
        text1 = extract_text_from_pdf(PDF1_PATH)
        text2 = extract_text_from_pdf(PDF2_PATH)

        if text1 and text2:
            quote1 = analyze_quote(text1)
            quote2 = analyze_quote(text2)
            compare_quotes(quote1, quote2)
        else:
            print("Failed to extract text from one or both PDFs.")

    input("Press Enter to exit...")