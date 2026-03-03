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

def parse_car_details(details_list):
    """Sépare intelligemment la ville, l'année et le reste."""
    res = {"ville": "Maroc", "annee": "N/C", "autres": []}
    banned = ["icon", "camera", "mois", "dh", "/", "1/", "2/"]
    
    for item in details_list:
        val = item.strip()
        val_lower = val.lower()
        
        if any(b in val_lower for b in banned) or len(val) < 2:
            continue
            
        # Détection de l'année (4 chiffres consécutifs commençant par 19 ou 20)
        if re.match(r"^(19|20)\d{2}$", val):
            res["annee"] = val
        # Détection de la ville (souvent les derniers éléments, ou via une liste si besoin)
        # Ici on prend le dernier élément non-numérique comme ville probable
        elif not any(char.isdigit() for char in val):
            res["ville"] = val
        else:
            if val not in res["autres"]:
                res["autres"].append(val)
                
    res["autres_str"] = " | ".join(res["autres"])
    return res

def send_telegram_page(data, page_number):
    if not data: return
    date_str = datetime.datetime.now().strftime("%H:%M")
    
    msg = f"✨ *AVITO - SÉLECTION PAGE {page_number}* ✨\n"
    msg += "📅 " + date_str + "\n"
    msg += "=" * 25 + "\n\n"
    
    for car in data[:8]:
        msg += f"🚘 *NOM :* {car['name']}\n"
        msg += f"💰 *PRIX :* {car['price']} DH\n"
        msg += f"📍 *VILLE :* {car['info']['ville']}\n"
        msg += f"📅 *MODÈLE :* {car['info']['annee']}\n"
        if car['info']['autres_str']:
            msg += f"⚙️ *INFOS :* {car['info']['autres_str']}\n"
        msg += f"🔗 [Ouvrir l'annonce sur Avito]({car['url']})\n"
        msg += "─" * 15 + "\n"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": msg, 
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    })

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
                    href = ad.get('href', '')
                    if "/vi/" in href or ".htm" in href:
                        full_url = href if href.startswith("http") else "https://www.avito.ma" + href
                        
                        title_tag = ad.find(['h3', 'p', 'span'], class_='iHApav') or ad.find('h3')
                        price_tag = ad.find(['p', 'span'], class_=['dJAfqm', 'hsBiLW'])
                        
                        if title_tag and price_tag:
                            name = title_tag.get_text(strip=True)[:30]
                            price = format_price(price_tag.get_text(strip=True))
                            
                            # Extraction des badges de détails
                            detail_tags = ad.find_all(['span', 'p'], class_='dGUnYf')
                            raw_details = [t.get_text(strip=True) for t in detail_tags]
                            
                            # Traitement intelligent des infos
                            info_traitee = parse_car_details(raw_details)

                            if any(char.isdigit() for char in price):
                                page_data.append({
                                    "name": name, 
                                    "price": price, 
                                    "info": info_traitee,
                                    "url": full_url
                                })

                if page_data:
                    # Unicité par URL pour éviter les doublons
                    unique = list({v['url']:v for v in page_data}.values())
                    send_telegram_page(unique, i)
                    print(f"✅ Page {i} envoyée proprement.")

            except Exception as e:
                print(f"Erreur Page {i}: {e}")
            finally:
                await page.close()
            await asyncio.sleep(2)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
