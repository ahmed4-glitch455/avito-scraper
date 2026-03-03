import asyncio
import os
import datetime
import requests
import re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre"
MAX_PAGES = 30 

def format_price(price_str):
    """Garde uniquement le prix principal."""
    digits = "".join([c for c in price_str if c.isdigit()])
    if len(digits) > 7: digits = digits[:6] # Coupe la mensualité si collée
    try:
        return f"{int(digits):,}".replace(",", " ")
    except:
        return digits

def clean_details(details_list):
    """Supprime les doublons, les icônes et les infos inutiles."""
    cleaned = []
    # Mots à bannir totalement des détails
    banned = ["icon", "camera", "mois", "dh", "/", "1/", "2/", "3/"]
    
    for item in details_list:
        val = item.lower().strip()
        # On ne garde que si l'élément n'est pas déjà présent et n'est pas banni
        if val not in [c.lower() for c in cleaned]:
            if not any(b in val for b in banned) and len(val) > 1:
                cleaned.append(item.strip())
    
    return " | ".join(cleaned)

def send_telegram_page(data, page_number):
    if not data: return
    date_str = datetime.datetime.now().strftime("%H:%M")
    msg = f"🚗 *AVITO - PAGE {page_number}/{MAX_PAGES}* ({date_str})\n"
    msg += "─" * 20 + "\n\n"
    
    for car in data[:12]:
        msg += f"🚘 *{car['name']}*\n"
        msg += f"💰 *{car['price']} DH*\n"
        msg += f"📍 _{car['details']}_\n"
        msg += "─" * 15 + "\n"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

async def scrape_avito():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

        for i in range(1, MAX_PAGES + 1):
            url = BASE_URL if i == 1 else f"{BASE_URL}?o={i}"
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i}...")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(5)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                annonces = soup.find_all('a', href=True)

                for ad in annonces:
                    title_tag = ad.find(['h3', 'p', 'span'], class_='iHApav') or ad.find('h3')
                    price_tag = ad.find(['p', 'span'], class_=['dJAfqm', 'hsBiLW'])
                    
                    if title_tag and price_tag:
                        name = title_tag.get_text(strip=True)[:25]
                        
                        # Extraction et nettoyage des détails
                        detail_tags = ad.find_all(['span', 'p'], class_='dGUnYf')
                        raw_details = [t.get_text(strip=True) for t in detail_tags]
                        # Si vide, on tente de prendre tous les petits textes
                        if not raw_details:
                            raw_details = [s.get_text(strip=True) for s in ad.find_all('span') if 2 < len(s.get_text()) < 20]
                        
                        price = format_price(price_tag.get_text(strip=True))
                        details = clean_details(raw_details)

                        if any(char.isdigit() for char in price):
                            page_data.append({"name": name, "price": price, "details": details})

                if page_data:
                    # Déduplication finale par nom de voiture
                    unique = list({v['name']:v for v in page_data}.values())
                    send_telegram_page(unique, i)
                    print(f"✅ Page {i} envoyée.")

            except Exception as e:
                print(f"Erreur Page {i}: {e}")
            finally:
                await page.close()
            await asyncio.sleep(2)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
