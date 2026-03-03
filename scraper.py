import asyncio
import os
import datetime
import requests
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

def clean_details(details_list):
    cleaned = []
    banned = ["icon", "camera", "mois", "dh", "/", "1/", "2/", "3/"]
    for item in details_list:
        val = item.lower().strip()
        if val not in [c.lower() for c in cleaned]:
            if not any(b in val for b in banned) and len(val) > 1:
                cleaned.append(item.strip())
    return " | ".join(cleaned)

def send_telegram_page(data, page_number):
    if not data: return
    date_str = datetime.datetime.now().strftime("%H:%M")
    msg = f"🚗 *AVITO - PAGE {page_number}/{MAX_PAGES}*\n"
    msg += "─" * 20 + "\n\n"
    
    for car in data[:8]: # On réduit à 8 pour ne pas faire de trop longs messages
        msg += f"🚘 *{car['name']}*\n"
        msg += f"💰 *{car['price']} DH*\n"
        msg += f"📍 _{car['details']}_\n"
        msg += f"🔗 [Voir l'annonce]({car['url']})\n" # LIEN DE VÉRIFICATION
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
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(5)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                # Chaque 'ad' est une boîte isolée (un lien <a>)
                annonces = soup.find_all('a', href=True)

                for ad in annonces:
                    href = ad.get('href', '')
                    # On vérifie que c'est bien un lien d'annonce voiture
                    if "/vi/" in href or ".htm" in href:
                        full_url = href if href.startswith("http") else "https://www.avito.ma" + href
                        
                        title_tag = ad.find(['h3', 'p', 'span'], class_='iHApav') or ad.find('h3')
                        price_tag = ad.find(['p', 'span'], class_=['dJAfqm', 'hsBiLW'])
                        
                        if title_tag and price_tag:
                            name = title_tag.get_text(strip=True)[:25]
                            price = format_price(price_tag.get_text(strip=True))
                            
                            detail_tags = ad.find_all(['span', 'p'], class_='dGUnYf')
                            raw_details = [t.get_text(strip=True) for t in detail_tags]
                            details = clean_details(raw_details)

                            if any(char.isdigit() for char in price):
                                page_data.append({
                                    "name": name, 
                                    "price": price, 
                                    "details": details,
                                    "url": full_url
                                })

                if page_data:
                    unique = list({v['url']:v for v in page_data}.values()) # Unicité par URL
                    send_telegram_page(unique, i)
                    print(f"✅ Page {i} envoyée avec liens.")

            except Exception as e:
                print(f"Erreur Page {i}: {e}")
            finally:
                await page.close()
            await asyncio.sleep(2)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
