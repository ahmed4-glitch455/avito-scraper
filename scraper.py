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
    digits = "".join([c for c in price_str if c.isdigit()])
    # Si le nombre est trop long (prix + mensualité), on coupe au prix de vente
    if len(digits) > 7:
        digits = digits[:6]
    try:
        return f"{int(digits):,}".replace(",", " ")
    except:
        return digits

def send_telegram_page(data, page_number):
    """Présentation avec détails enrichis."""
    if not data: return
    
    date_str = datetime.datetime.now().strftime("%H:%M")
    msg = f"🚗 *AVITO - PAGE {page_number}/{MAX_PAGES}* ({date_str})\n"
    msg += "─" * 20 + "\n\n"
    
    for car in data[:12]:
        msg += f"🔹 *{car['name']}*\n"
        msg += f"💰 *{car['price']} DH*\n"
        # On ajoute un emoji pour les détails
        msg += f"ℹ️ _{car['details']}_\n"
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
                print(f"Analyse Page {i}...")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # Scroll profond pour activer le chargement des badges
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(5)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # On cherche les conteneurs d'annonces
                annonces = soup.find_all('a', href=True)

                for ad in annonces:
                    # 1. Extraction Titre
                    title_tag = ad.find(['h3', 'p', 'span'], class_='iHApav') or ad.find('h3')
                    
                    # 2. Extraction Prix
                    price_tag = ad.find(['p', 'span'], class_=['dJAfqm', 'hsBiLW'])
                    
                    # 3. EXTRACTION DÉTAILS (Correction ici)
                    # On cherche TOUS les éléments qui ont la classe des badges 'dGUnYf'
                    # ou simplement les petits textes grisés en bas de l'annonce
                    details_list = []
                    
                    # On cherche dans les paragraphes et spans secondaires
                    tags_secondaires = ad.find_all(['p', 'span'], class_=lambda x: x and ('dGUnYf' in x or 'hsBiLW' in x))
                    
                    for t in tags_secondaires:
                        txt = t.get_text(strip=True)
                        # On ignore le prix et les textes trop longs ou trop courts
                        if txt and "DH" not in txt and len(txt) < 30:
                            details_list.append(txt)
                    
                    # Si on ne trouve rien par classe, on cherche les éléments textuels isolés
                    if not details_list:
                        details_list = [span.get_text(strip=True) for span in ad.find_all('span') if 2 < len(span.get_text()) < 20]

                    # On nettoie pour enlever le titre des détails
                    name = title_tag.get_text(strip=True) if title_tag else "Inconnu"
                    details_final = [d for d in details_list if d not in name]
                    details_text = " | ".join(details_final) if details_final else "Infos non dispo"

                    if title_tag and price_tag:
                        raw_price = price_tag.get_text(strip=True)
                        clean_p = format_price(raw_price)
                        
                        if any(char.isdigit() for char in clean_p):
                            page_data.append({
                                "name": name[:25], 
                                "price": clean_p,
                                "details": details_text
                            })

                if page_data:
                    # Supprimer les doublons
                    final_data = []
                    seen = set()
                    for car in page_data:
                        if car['name'] not in seen:
                            final_data.append(car)
                            seen.add(car['name'])
                    
                    send_telegram_page(final_data, i)
                    print(f"✅ Page {i} : {len(final_data)} voitures envoyées.")

            except Exception as e:
                print(f"Erreur Page {i}: {e}")
            finally:
                await page.close()
            
            await asyncio.sleep(2)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
