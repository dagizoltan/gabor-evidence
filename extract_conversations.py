import os
import pytesseract
from PIL import Image
import pandas as pd
import exifread
import re

def get_exif_date(filepath):
    try:
        with open(filepath, 'rb') as f:
            tags = exifread.process_file(f, stop_tag='DateTimeOriginal')
            if 'EXIF DateTimeOriginal' in tags:
                return str(tags['EXIF DateTimeOriginal'])
    except:
        pass
    return None

def parse_viber_filename(filename):
    try:
        parts = filename.split('_')
        if len(parts) >= 3:
            date_part = parts[2]
            time_part = parts[3].replace('-', ':')
            time_part = ':'.join(time_part.split(':')[0:3])
            return f"{date_part} {time_part}"
    except:
        pass
    return None

def is_junk_text(text):
    # Filter out common UI noise and keyboard artifacts
    text_clean = text.lower().strip()
    if not text_clean:
        return True

    # Keyboard rows and common artifacts
    junk_patterns = [
        r'^[qwertyuiop]+$',
        r'^[asdfghjkl]+$',
        r'^[zxcvbnm]+$',
        r'^[1234567890]+$',
        r'^[\W_]+$',
        r'^.*[zxvbnm]{4,}.*$', # Sequences of bottom row keys
        r'^[a-z]$', # Single letters usually noise unless 'a' or 'i'
    ]

    test_str = text_clean.replace(" ", "").replace("@", "").replace("&", "").replace("|", "")
    for p in junk_patterns:
        if re.match(p, test_str):
            return True

    # Too many symbols
    if len(text_clean) > 0:
        symbol_count = len(re.findall(r'[\W_]', text_clean))
        if symbol_count / len(text_clean) > 0.5 and len(text_clean) > 3:
            return True

    return False

def process_image(filepath, platform):
    img = Image.open(filepath)
    width, height = img.size

    # Get OCR data
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DATAFRAME)
    df = data[data.text.notna() & (data.text.str.strip() != "")].copy()

    if df.empty:
        return []

    # Filter out top (status bar) and bottom (keyboard/UI)
    # Increased bottom crop to 20% to avoid keyboard and Viber action bar
    df = df[(df.top > height * 0.08) & (df.top < height * 0.80)]

    if df.empty:
        return []

    # Robust Line Grouping
    df = df.sort_values(by='top')
    lines = []
    current_line = []
    if not df.empty:
        current_y_center = df.iloc[0].top + df.iloc[0].height / 2
        for _, row in df.iterrows():
            row_y_center = row.top + row.height / 2
            if abs(row_y_center - current_y_center) < row.height * 0.8:
                current_line.append(row)
            else:
                current_line.sort(key=lambda r: r['left'])
                lines.append(current_line)
                current_line = [row]
                current_y_center = row_y_center
        if current_line:
            current_line.sort(key=lambda r: r['left'])
            lines.append(current_line)

    processed_messages = []
    for line in lines:
        text = " ".join([str(r['text']) for r in line])
        if is_junk_text(text):
            continue

        min_left = min([r['left'] for r in line])
        avg_top = sum([r['top'] for r in line]) / len(line)

        # Sender attribution
        sender = "System"
        if platform == "iMessage":
            if min_left > width * 0.40:
                sender = "You"
            elif min_left < width * 0.3:
                # Name headers usually at the very top (already mostly filtered)
                if "Elena" in text or "Siankevich" in text:
                    sender = "System"
                else:
                    sender = "Elena Siankevich"
            else:
                sender = "System"
        else: # Viber
            if min_left > width * 0.45:
                sender = "You"
            elif min_left < width * 0.3:
                sender = "Elena Siankevich"
            else:
                sender = "System"

        # Platform specific cleanup
        if any(x in text for x in ["Voice call", "Missed", "No answer", "Video call"]):
            sender = "System"
        if "deleted this message" in text.lower():
            sender = "System"

        processed_messages.append({
            'text': text,
            'sender': sender,
            'top': avg_top
        })

    # Message Consolidation
    final_messages = []
    if processed_messages:
        curr = processed_messages[0]
        for next_msg in processed_messages[1:]:
            if next_msg['sender'] == curr['sender'] and (next_msg['top'] - curr['top'] < 70) and curr['sender'] != "System":
                curr['text'] += " " + next_msg['text']
                curr['top'] = next_msg['top']
            else:
                final_messages.append(curr)
                curr = next_msg
        final_messages.append(curr)

    return final_messages

def main():
    files = sorted(os.listdir('.'))
    image_files = [f for f in files if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower()
                for text in re.split('([0-9]+)', s)]

    image_files.sort(key=natural_sort_key)

    results = []
    current_date_header = "Unknown Date"

    for f in image_files:
        platform = "iMessage" if f.startswith('IMG_') else "Viber"
        exif_date = get_exif_date(f)
        filename_date = parse_viber_filename(f) if platform == "Viber" else None

        print(f"Processing {f}...")
        msgs = process_image(f, platform)

        for m in msgs:
            if m['sender'] == "System":
                if re.search(r'(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Today|Yesterday|January|February|March|April|May|June|July|August|September|October|November|December)', m['text']):
                    current_date_header = m['text']

        display_date = exif_date or filename_date or current_date_header

        results.append({
            'file': f,
            'platform': platform,
            'date': display_date,
            'messages': msgs
        })

    with open('court_evidence.md', 'w') as out:
        out.write("# Conversation Data - Court Evidence\n\n")
        out.write("Structured chronological transcripts extracted for court review.\n\n")

        for res in results:
            out.write(f"## Source File: {res['file']}\n")
            out.write(f"- **Platform**: {res['platform']}\n")
            out.write(f"- **Estimated Date**: {res['date']}\n\n")

            if not res['messages']:
                out.write("*[No conversation text detected in this image area]*\n")

            for m in res['messages']:
                text = m['text'].strip()
                if not text: continue

                if m['sender'] == "System":
                    out.write(f"> *[{text}]*\n")
                else:
                    out.write(f"* **{m['sender']}**: {text}\n")
            out.write("\n---\n\n")

    print(f"Extraction complete. Results saved to court_evidence.md")

if __name__ == "__main__":
    main()
