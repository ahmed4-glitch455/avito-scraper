import asyncio
import os
import datetime
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION (Utilise vos noms de secrets) ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre?price=-60000"
MAX_PAGES = 30 

def send_telegram_page(data, page_number):
    """Envoie les résultats d'une page sous forme de tableau propre."""
    if not data:
        return
    
    date_str = datetime.datetime.now().strftime("%H:%M")
    header = f"🚗 *Avito Page {page_number}/30* ({date_str})\n"
    header += "```\n"
    header += f"{'Modèle':<18} | {'Prix':<10}\n"
    header += "-" * 31 + "\n"
    
    body = ""
    for car in data:
        body += f"{car['name']:<18} | {car['price']:<10}\n"
    
    msg = header + body + "```"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

async def scrape_avito():
    async with async_playwright() as p:
        # Lancement avec options anti-détection
        browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        print(f"Début du scraping global : {MAX_PAGES} pages.")

        for i in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}&o={i}"
            tab = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i}...")
                await tab.goto(url, wait_until="load", timeout=60000)
                
                # Petite pause pour laisser les prix s'afficher
                await asyncio.sleep(4)
                
                content = await tab.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # On cherche les cartes d'annonces
                annonces = soup.find_all('div', {'data-testid': 'ad-card'})
                if not annonces:
                    annonces = soup.select('div[class*="o-card"]') # Alternative

                for ad in annonces:
                    try:
                        # Extraction du titre et du prix par mots-clés
                        name_tag = ad.find('p', class_=lambda x: x and 'heading' in x.lower())
                        price_tag = ad.find('p', class_=lambda x: x and 'price' in x.lower())
                        
                        if name_tag and price_tag:
                            name = name_tag.get_text(strip=True)[:18]
                            price = price_tag.get_text(strip=True).replace(" DH", "").replace(" ", "")
                            page_data.append({"name": name, "price": price})
                    except:
                        continue

                if page_data:
                    send_telegram_page(page_data, i)
                    print(f"✅ Page {i} envoyée.")
                else:
                    print(f"⚠️ Page {i} semble vide.")

            except Exception as e:
                print(f"❌ Erreur Page {i}: {e}")
            
            finally:
                await tab.close()

            # Pause entre les pages pour la discrétion
            await asyncio.sleep(2)

        await browser.close()

if __name__ == "__main__":
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        asyncio.run(scrape_avito())
    else:
        print("Erreur : Configuration Telegram incomplète.")
