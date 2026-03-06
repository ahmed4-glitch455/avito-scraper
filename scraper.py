import asyncio
import os
import datetime
import requests
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre?price=-40000"
MAX_PAGES = 30 

def format_price(price_str):
    # 1. On garde uniquement les chiffres
    digits = "".join([c for c in price_str if c.isdigit()])
    
    # 2. LOGIQUE DE CORRECTION :
    # Si le prix semble avoir un chiffre de trop (ex: 580001 pour 58000)
    # On sait que les prix ronds finissent souvent par 000 au Maroc.
    # Si le prix dépasse 5 chiffres et finit par un chiffre parasite du crédit
    if len(digits) > 5 and digits.endswith(('1', '2', '3', '4', '5', '6', '7', '8', '9')):
        # On vérifie si enlever le dernier chiffre rend le prix plus "normal" (multiple de 100 ou 1000)
        if digits[:-1].endswith('00'):
            digits = digits[:-1]
            
    try:
        return f"{int(digits):,}".replace(",", " ")
    except:
        return digits

def extract_year_from_text(text):
    match = re.search(r"(19|20)\d{2}", text)
    return match.group(0) if match else None

def send_telegram_page(data, page_number):
    if not data: return
    date_str = datetime.datetime.now().strftime("%H:%M")
    msg = f"✨ *SÉLECTION AVITO (<40k) - PAGE {page_number}/{MAX_PAGES}* ✨\n"
    msg += f"🕒 {date_str}\n"
    msg += "=" * 25 + "\n\n"
    
    for car in data[:10]:
        msg += f"🚘 *NOM :* {car['name']}\n"
        msg += f"💰 *PRIX :* {car['price']} DH\n"
        msg += f"📍 *VILLE :* {car['ville']}\n"
        msg += f"📅 *MODÈLE :* {car['annee']}\n"
        if car['details']:
            msg += f"⚙️ *INFOS :* {car['details']}\n"
        msg += f"🔗 [Ouvrir l'annonce]({car['url']})\n"
        msg += "─" * 15 + "\n"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown", "disable_web_page_preview": True})

async def scrape_avito():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        for i in range(1, MAX_PAGES + 1):
            if i == 1:
                url = BASE_URL
            else:
                url = BASE_URL.replace("?", f"?o={i}&")
            
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i}...")
                await page.goto(url, wait_until="load", timeout=60000)
                
                for _ in range(6):
                    await page.mouse.wheel(0, 800)
                    await asyncio.sleep(1)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                annonces = soup.find_all('a', href=True)

                for ad in annonces:
                    href = ad.get('href', '')
                    if "/vi/" in href or ".htm" in href:
                        full_url = href if href.startswith("http") else "https://www.avito.ma" + href
                        
                        # Ici on cible plus précisément pour éviter de déborder sur la mensualité
                        price_tag = ad.find(['p', 'span'], class_=['dJAfqm', 'hsBiLW'])
                        title_tag = ad.find(['h3', 'p', 'span'], class_='iHApav') or ad.find('h3')
                        
                        if title_tag and price_tag:
                            name = title_tag.get_text(strip=True)
                            # On nettoie le prix avant de l'envoyer à la fonction format_price
                            raw_price = price_tag.get_text(strip=True).split('DH')[0] + " DH"
                            price = format_price(raw_price)
                            
                            badges = ad.find_all(['span', 'p'])
                            all_texts = [b.get_text(strip=True) for b in badges if b.get_text(strip=True)]
                            
                            ville = "Maroc"
                            annee = extract_year_from_text(name) or "N/C"
                            autres = []
                            candidates_ville = []

                            for text in all_texts:
                                lower_text = text.lower()
                                if "dh" in lower_text or "/mois" in lower_text:
                                    continue
                                
                                if re.match(r"^(19|20)\d{2}$", text):
                                    annee = text
                                elif any(x in lower_text for x in ['km', 'diesel', 'essence', 'manuel', 'auto', 'cv']):
                                    if text not in autres: autres.append(text)
                                elif len(text) > 2 and not any(char.isdigit() for char in text):
                                    if lower_text not in ["plus d'infos", "voir l'annonce", "neuf"]:
                                        candidates_ville.append(text)

                            if candidates_ville:
                                ville = candidates_ville[-1]

                            if any(char.isdigit() for char in price):
                                page_data.append({
                                    "name": name[:30],
                                    "price": price,
                                    "ville": ville,
                                    "annee": annee,
                                    "details": " | ".join(autres),
                                    "url": full_url
                                })

                if page_data:
                    unique = list({v['url']:v for v in page_data}.values())
                    send_telegram_page(unique, i)
                    print(f"✅ Page {i} corrigée envoyée.")

            except Exception as e:
                print(f"Erreur Page {i}: {e}")
            finally:
                await page.close()
            await asyncio.sleep(2)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
