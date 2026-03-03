import asyncio
import os
import datetime
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
# Nouvelle URL de base sans filtre de prix
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre"
MAX_PAGES = 30 

def send_telegram_page(data, page_number):
    """Envoie les résultats d'une page sur Telegram."""
    if not data:
        return
    
    date_str = datetime.datetime.now().strftime("%H:%M")
    header = f"🚗 *Avito Page {page_number}/{MAX_PAGES}* ({date_str})\n"
    header += "```\n"
    header += f"{'Modèle':<18} | {'Prix':<10}\n"
    header += "-" * 31 + "\n"
    
    body = ""
    for car in data[:20]: # Limite à 20 pour la clarté du message
        body += f"{car['name']:<18} | {car['price']:<10}\n"
    
    msg = header + body + "```"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"}, timeout=10)
    except Exception as e:
        print(f"Erreur envoi Telegram : {e}")

async def scrape_avito():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        for i in range(1, MAX_PAGES + 1):
            # Rectification de la logique d'URL
            if i == 1:
                url = BASE_URL
            else:
                url = f"{BASE_URL}?o={i}"
            
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i} : {url}")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Scroll pour déclencher le chargement des données
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(5)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Stratégie de recherche par texte "DH" pour contourner les blocages de balises
                elements_prix = soup.find_all(lambda tag: tag.name in ['p', 'span', 'h3'] and 'DH' in tag.text)
                
                print(f"Éléments 'DH' trouvés sur la page {i} : {len(elements_prix)}")

                for el in elements_prix:
                    prix_text = el.get_text(strip=True)
                    # Validation du format prix
                    if any(char.isdigit() for char in prix_text) and len(prix_text) < 25:
                        
                        # Recherche du titre le plus proche
                        parent = el.find_parent('div')
                        if parent:
                            # On cherche un titre dans le même bloc
                            titre_tag = parent.find(['h2', 'h3', 'p', 'span'], class_=lambda x: x and ('title' in x.lower() or 'heading' in x.lower()))
                            if not titre_tag:
                                titre_tag = parent.find(['h2', 'h3']) # Backup sur les titres standards
                            
                            if titre_tag:
                                titre = titre_tag.get_text(strip=True)[:18]
                                # On évite de prendre le prix comme titre
                                if titre and "DH" not in titre:
                                    price_clean = prix_text.replace("DH", "").replace(" ", "").strip()
                                    page_data.append({"name": titre, "price": price_clean})

                # Suppression des doublons
                final_data = []
                seen_names = set()
                for car in page_data:
                    if car['name'] not in seen_names:
                        final_data.append(car)
                        seen_names.add(car['name'])

                if final_data:
                    send_telegram_page(final_data, i)
                    print(f"✅ Page {i} envoyée ({len(final_data)} annonces).")
                else:
                    print(f"❌ Page {i} : Aucune annonce extraite.")

            except Exception as e:
                print(f"Erreur sur la page {i}: {e}")
            finally:
                await page.close()
            
            # Pause de sécurité pour ne pas être banni
            await asyncio.sleep(3)

        await browser.close()

if __name__ == "__main__":
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        asyncio.run(scrape_avito())
    else:
        print("Erreur : Les secrets TELEGRAM_API ou TELEGRAM_CHAT_ID ne sont pas configurés.")
