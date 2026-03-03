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

def extract_year_from_text(text):
    match = re.search(r"(19|20)\d{2}", text)
    return match.group(0) if match else None

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
                await page.goto(url, wait_until="load", timeout=60000)
                
                # Scroll plus lent et plus long pour forcer l'affichage de la ville
                for _ in range(6):
                    await page.mouse.wheel(0, 800)
                    await asyncio.sleep(1)

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
                            name = title_tag.get_text(strip=True)
                            price = format_price(price_tag.get_text(strip=True))
                            
                            # On récupère TOUS les textes dans l'annonce
                            badges = ad.find_all(['span', 'p'])
                            all_texts = [b.get_text(strip=True) for b in badges if b.get_text(strip=True)]
                            
                            ville = "Maroc" # Valeur par défaut plus propre que "Non spécifiée"
                            annee = extract_year_from_text(name) or "N/C"
                            autres = []
                            candidates_ville = []

                            for text in all_texts:
                                lower_text = text.lower()
                                
                                # Ignorer les prix et crédits
                                if "dh" in lower_text or "/mois" in lower_text:
                                    continue
                                
                                # Détecter l'année
                                if re.match(r"^(19|20)\d{2}$", text):
                                    annee = text
                                # Détecter les infos techniques
                                elif any(x in lower_text for x in ['km', 'diesel', 'essence', 'manuel', 'auto', 'cv']):
                                    if text not in autres: 
                                        autres.append(text)
                                # Collecter les candidats pour la ville (Texte pur sans chiffres)
                                elif len(text) > 2 and not any(char.isdigit() for char in text):
                                    if lower_text not in ["plus d'infos", "voir l'annonce", "neuf"]:
                                        candidates_ville.append(text)

                            # La ville est très souvent le DERNIER élément de texte pur dans l'annonce
                            if candidates_ville:
                                ville = candidates_ville[-1]

                            if any(char.isdigit() for char in price):
                                page_data.append({
                                    "name": name[:30],
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
