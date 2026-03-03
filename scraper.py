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

def clean_price(price_str):
    """Sépare le prix de vente de la mensualité de crédit."""
    # On ne garde que les chiffres avant le premier 'DH' ou avant la répétition suspecte
    # Le prix Avito est souvent formaté : '145 0003 007/mois' -> on veut '145 000'
    price_str = price_str.replace(" ", "").replace("DH", "")
    # Si le prix est très long (mensualité collée), on prend les 5 ou 6 premiers chiffres
    if len(price_str) > 7:
        return price_str[:6].strip() # Estimation du prix de vente principal
    return price_str

def send_telegram_page(data, page_number):
    if not data: return
    
    msg = f"🚗 *AVITO - PAGE {page_number}*\n"
    msg += "─" * 20 + "\n"
    
    for car in data[:10]: # 10 par 10 pour la lisibilité
        msg += f"🔹 *{car['name']}*\n"
        msg += f"💰 {car['price']} DH\n"
        msg += f"📑 {car['details']}\n"
        msg += f"─" * 15 + "\n"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

async def scrape_avito():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        
        for i in range(1, 6): # Test sur 5 pages pour commencer
            url = BASE_URL if i == 1 else f"{BASE_URL}?o={i}"
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i}...")
                await page.goto(url, wait_until="load", timeout=60000)
                await page.mouse.wheel(0, 3000)
                await asyncio.sleep(4)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # On cible les conteneurs d'annonces
                annonces = soup.find_all('a', href=True)

                for ad in annonces:
                    # 1. Extraction Titre
                    title_tag = ad.find('h3', class_='iHApav')
                    # 2. Extraction Prix
                    price_tag = ad.find('p', class_='dJAfqm')
                    # 3. Extraction Détails (Année, Carburant, KM)
                    # Dans votre HTML, ce sont des span avec la classe 'dGUnYf' ou 'hsBiLW'
                    details_tags = ad.find_all('span', class_='dGUnYf')
                    infos = [t.get_text(strip=True) for t in details_tags if t.get_text(strip=True)]
                    
                    if title_tag and price_tag:
                        name = title_tag.get_text(strip=True)
                        price = clean_price(price_tag.get_text(strip=True))
                        # On joint les infos trouvées (ex: "Diesel • 2022 • 100k km")
                        details_str = " | ".join(infos) if infos else "Détails non dispo"
                        
                        page_data.append({
                            "name": name,
                            "price": f"{int(price):,}".replace(",", " ") if price.isdigit() else price,
                            "details": details_str
                        })

                if page_data:
                    # Supprimer les doublons
                    unique = list({v['name']:v for v in page_data}.values())
                    send_telegram_page(unique, i)
                    print(f"✅ Page {i} envoyée.")
                
            except Exception as e:
                print(f"Erreur Page {i}: {e}")
            finally:
                await page.close()
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
