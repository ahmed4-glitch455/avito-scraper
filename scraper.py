import asyncio
import os
import datetime
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Chargement des variables (Local ou GitHub Actions)
load_dotenv()

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# URL de base avec votre filtre de prix
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre?price=-60000"
MAX_PAGES = 30  # Limitation à 30 pages

async def scrape_page(browser, page_number):
    """Scrape une seule page spécifique."""
    url = f"{BASE_URL}&o={page_number}"
    context = await browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    )
    page = await context.new_page()
    
    data = []
    try:
        print(f"Scraping Page {page_number}...")
        await page.goto(url, wait_until="networkidle", timeout=60000)
        
        # Attendre le chargement des annonces
        await page.wait_for_selector('div[data-testid="ad-card"]', timeout=10000)
        content = await page.content()
        soup = BeautifulSoup(content, 'html.parser')
        annonces = soup.find_all('div', {'data-testid': 'ad-card'})

        for ad in annonces:
            try:
                name = ad.find('p', class_=lambda x: x and 'heading' in x.lower()).get_text(strip=True)
                price = ad.find('p', class_=lambda x: x and 'price' in x.lower()).get_text(strip=True)
                # Nettoyage rapide du prix
                price_clean = price.replace(" DH", "").replace(" ", "")
                data.append({"name": name[:20], "price": price_clean})
            except:
                continue
    except Exception as e:
        print(f"Erreur sur la page {page_number}: {e}")
    finally:
        await context.close()
    
    return data

def send_telegram_chunk(text):
    """Envoie des morceaux de texte (Telegram limite à 4096 caractères)."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    requests.post(url, data=payload)

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        toutes_les_voitures = []

        # Boucle sur les 30 pages
        for i in range(1, MAX_PAGES + 1):
            voitures_page = await scrape_page(browser, i)
            toutes_les_voitures.extend(voitures_page)
            # Petit délai pour être "gentil" avec le serveur
            await asyncio.sleep(1) 

        await browser.close()

        # Préparation du message (Tableau)
        if toutes_les_voitures:
            header = f"🚗 *Top Voitures < 60.000 DH ({len(toutes_les_voitures)} trouvées)*\n\n"
            header += "```\n"
            header += f"{'Modèle':<20} | {'Prix':<10}\n"
            header += "-" * 32 + "\n"
            
            # Telegram limite la taille des messages. 
            # On envoie par blocs de 20 voitures pour ne pas dépasser.
            current_msg = header
            for idx, car in enumerate(toutes_les_voitures):
                current_msg += f"{car['name']:<20} | {car['price']:<10}\n"
                
                if (idx + 1) % 20 == 0: # Toutes les 20 lignes
                    current_msg += "```"
                    send_telegram_chunk(current_msg)
                    current_msg = "```\n" # Nouveau bloc
            
            if current_msg != "```\n":
                current_msg += "```"
                send_telegram_chunk(current_msg)
                
            print(f"Terminé ! {len(toutes_les_voitures)} voitures traitées.")
        else:
            print("Aucune voiture trouvée.")

if __name__ == "__main__":
    asyncio.run(main())

