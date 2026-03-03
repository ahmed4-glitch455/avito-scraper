import asyncio
import os
import datetime
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
TELEGRAM_API = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre?price=-60000"
MAX_PAGES = 30 

def send_telegram_page(data, page_number):
    """Formate et envoie les données d'une seule page sur Telegram."""
    if not data:
        return
    
    date_str = datetime.datetime.now().strftime("%H:%M")
    header = f"📄 *Avito Page {page_number}/30* ({date_str})\n"
    header += "```\n"
    header += f"{'Modèle':<18} | {'Prix':<10}\n"
    header += "-" * 31 + "\n"
    
    body = ""
    for car in data:
        body += f"{car['name']:<18} | {car['price']:<10}\n"
    
    footer = "```"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": header + body + footer,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code != 200:
            print(f"Erreur Telegram Page {page_number}: {response.text}")
    except Exception as e:
        print(f"Erreur envoi Telegram: {e}")

async def scrape_and_send():
    async with async_playwright() as p:
        # Lancement du navigateur avec des options de discrétion
        browser = await p.chromium.launch(headless=True)
        
        # On définit un User-Agent fixe pour tout le navigateur
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        for i in range(1, MAX_PAGES + 1):
            page_data = []
            url = f"{BASE_URL}&o={i}"
            
            tab = await context.new_page()
            print(f"Analyse de la page {i}...")

            try:
                # On attend que la page soit chargée
                await tab.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Attente visuelle des annonces
                await tab.wait_for_selector('div[data-testid="ad-card"]', timeout=15000)
                
                content = await tab.content()
                soup = BeautifulSoup(content, 'html.parser')
                annonces = soup.find_all('div', {'data-testid': 'ad-card'})

                for ad in annonces:
                    try:
                        name = ad.find('p', class_=lambda x: x and 'heading' in x.lower()).get_text(strip=True)
                        price = ad.find('p', class_=lambda x: x and 'price' in x.lower()).get_text(strip=True)
                        
                        price_clean = price.replace(" DH", "").replace(" ", "")
                        page_data.append({"name": name[:18], "price": price_clean})
                    except:
                        continue

                # ENVOI IMMÉDIAT de la page
                if page_data:
                    send_telegram_page(page_data, i)
                    print(f"Page {i} envoyée avec succès.")
                else:
                    print(f"Page {i} vide ou bloquée.")

            except Exception as e:
                print(f"Erreur sur la page {i}: {e}")
            
            finally:
                await tab.close() # Ferme l'onglet pour libérer la RAM

            # Pause entre les pages pour éviter d'être banni
            await asyncio.sleep(2)

        await browser.close()

if __name__ == "__main__":
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("ERREUR: Token ou Chat ID manquant dans les secrets GitHub !")
    else:
        asyncio.run(scrape_and_send())


