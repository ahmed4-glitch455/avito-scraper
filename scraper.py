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
    digits = "".join([c for c in price_str if c.isdigit()])
    if len(digits) > 7: digits = digits[:6]
    try:
        return f"{int(digits):,}".replace(",", " ")
    except:
        return digits

def send_telegram_page(data, page_number):
    if not data: return
    date_str = datetime.datetime.now().strftime("%H:%M")
    msg = f"✨ *SÉLECTION AVITO - PAGE {page_number}/{MAX_PAGES}* ✨\n"
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
            url = BASE_URL if i == 1 else f"{BASE_URL}?o={i}"
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i}...")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(6) # Un peu plus de temps pour charger les icônes

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                annonces = soup.find_all('a', href=True)

                for ad in annonces:
                    href = ad.get('href', '')
                    if "/vi/" in href or ".htm" in href:
                        full_url = href if href.startswith("http") else "https://www.avito.ma" + href
                        
                        # Extraction Nom et Prix
                        title_tag = ad.find(['h3', 'p', 'span'], class_='iHApav') or ad.find('h3')
                        price_tag = ad.find(['p', 'span'], class_=['dJAfqm', 'hsBiLW'])
                        
                        if title_tag and price_tag:
                            name = title_tag.get_text(strip=True)[:30]
                            price = format_price(price_tag.get_text(strip=True))
                            
                            # --- NOUVELLE LOGIQUE DE DÉTAILS ---
                            # On récupère tous les petits textes
                            badges = ad.find_all(['span', 'p'], class_='dGUnYf')
                            text_list = [b.get_text(strip=True) for b in badges if b.get_text(strip=True)]
                            
                            ville = "Non spécifiée"
                            annee = "N/C"
                            autres = []

                            for text in text_list:
                                # Si c'est 4 chiffres, c'est l'année
                                if re.match(r"^(19|20)\d{2}$", text):
                                    annee = text
                                # Si contient 'km', 'Diesel', 'Essence', 'Manuel', 'Auto'
                                elif any(x in text.lower() for x in ['km', 'diesel', 'essence', 'manuel', 'auto']):
                                    if text not in autres: autres.append(text)
                                # Sinon, par élimination, c'est la ville (si ce n'est pas le prix)
                                elif "DH" not in text and "/" not in text and len(text) > 2:
                                    ville = text

                            if any(char.isdigit() for char in price):
                                page_data.append({
                                    "name": name,
                                    "price": price,
                                    "ville": ville,
                                    "annee": annee,
                                    "details": " | ".join(autres),
                                    "url": full_url
                                })

                if page_data:
                    unique = list({v['url']:v for v in page_data}.values())
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
