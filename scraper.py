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
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre"
MAX_PAGES = 30 

def format_price(price_str):
    """Nettoie le prix pour enlever les mensualités de crédit collées."""
    # On ne garde que les chiffres
    digits = "".join([c for c in price_str if c.isdigit()])
    # Si le nombre est trop long (ex: 1450003007), on prend les 6 premiers chiffres (le prix de vente)
    if len(digits) > 7:
        digits = digits[:6]
    # Ajoute un espace pour les milliers (ex: 145 000)
    try:
        return f"{int(digits):,}".replace(",", " ")
    except:
        return digits

def send_telegram_page(data, page_number):
    """Présentation améliorée des informations sur Telegram."""
    if not data: return
    
    date_str = datetime.datetime.now().strftime("%H:%M")
    msg = f"🚗 *AVITO - PAGE {page_number}/{MAX_PAGES}* ({date_str})\n"
    msg += "─" * 20 + "\n\n"
    
    # On envoie par blocs de 10 voitures pour une meilleure lisibilité
    for car in data[:12]:
        msg += f"🔹 *{car['name']}*\n"
        msg += f"💰 *{car['price']} DH*\n"
        msg += f"📍 {car['details']}\n"
        msg += "─" * 15 + "\n"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

async def scrape_avito():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        for i in range(1, MAX_PAGES + 1):
            url = BASE_URL if i == 1 else f"{BASE_URL}?o={i}"
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i} : {url}")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Scroll pour charger les données Lazy Load
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(5)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # On cherche les conteneurs d'annonces (balises <a>)
                annonces = soup.find_all('a', href=True)

                for ad in annonces:
                    # 1. Extraction Titre
                    title_tag = ad.find(['h3', 'p', 'span'], class_='iHApav') or ad.find('h3')
                    
                    # 2. Extraction Prix
                    price_tag = ad.find(['p', 'span'], class_=['dJAfqm', 'hsBiLW']) or \
                                ad.find(lambda t: t.name == 'p' and 'DH' in t.text)
                    
                    # 3. NOUVEAU : Extraction des Détails (Carburant, Année, KM)
                    # Ces infos utilisent souvent la classe 'dGUnYf' dans votre HTML
                    detail_spans = ad.find_all('span', class_='dGUnYf')
                    details_list = [d.get_text(strip=True) for d in detail_spans if d.get_text(strip=True)]
                    details_text = " | ".join(details_list) if details_list else "Détails non dispo"

                    if title_tag and price_tag:
                        name = title_tag.get_text(strip=True)[:25]
                        raw_price = price_tag.get_text(strip=True)
                        
                        # Nettoyage et formatage
                        clean_p = format_price(raw_price)
                        
                        if any(char.isdigit() for char in clean_p):
                            page_data.append({
                                "name": name, 
                                "price": clean_p,
                                "details": details_text
                            })

                # Nettoyage des doublons sur cette page
                final_data = []
                seen = set()
                for car in page_data:
                    if car['name'] not in seen:
                        final_data.append(car)
                        seen.add(car['name'])

                if final_data:
                    send_telegram_page(final_data, i)
                    print(f"✅ Page {i} : {len(final_data)} voitures envoyées.")
                else:
                    print(f"⚠️ Page {i} : Aucune donnée extraite.")

            except Exception as e:
                print(f"Erreur Page {i}: {e}")
            finally:
                await page.close()
            
            await asyncio.sleep(2)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
