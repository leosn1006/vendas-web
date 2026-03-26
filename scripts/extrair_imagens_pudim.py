import re, base64, os, hashlib

html_path = "app/templates/pudim.html"
output_dir = "static/images"
os.makedirs(output_dir, exist_ok=True)

with open(html_path, "r", encoding="utf-8") as f:
    html = f.read()

pattern = re.compile(r'src="data:image/jpeg;base64,([A-Za-z0-9+/=]+)"')
counter = 0
hash_to_filename = {}

def replace_match(m):
    global counter
    b64 = m.group(1)
    h = hashlib.md5(b64.encode()).hexdigest()
    if h in hash_to_filename:
        filename = hash_to_filename[h]
        print(f"Reutilizado: {filename}")
    else:
        counter += 1
        img_data = base64.b64decode(b64)
        filename = f"pudim-{counter:02d}.jpg"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "wb") as f:
            f.write(img_data)
        hash_to_filename[h] = filename
        print(f"Salvo: {filepath} ({len(img_data):,} bytes)")
    return f'src="/static/images/{filename}"'

new_html = pattern.sub(replace_match, html)

with open(html_path, "w", encoding="utf-8") as f:
    f.write(new_html)

print(f"\nConcluído! {counter} imagens únicas salvas.")
