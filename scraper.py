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
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre?price=-60000"
MAX_PAGES = 30 

def format_price(price_str):
    # On coupe tout après 'DH' pour éviter la mensualité
    clean_str = price_str.split('DH')[0]
    digits = "".join([c for c in clean_str if c.isdigit()])
    if len(digits) > 5 and digits.endswith(('1', '2', '3', '4', '5', '6', '7', '8', '9')):
        if digits[:-1].endswith('00'): digits = digits[:-1]
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
    msg = f"📍 *AVITO : VILLE EXACTE - PAGE {page_number}* 📍\n"
    msg += f"🕒 {date_str} | Budget < 60k\n"
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
            url = BASE_URL if i == 1 else BASE_URL.replace("?", f"?o={i}&")
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Ville Page {i}...")
                await page.goto(url, wait_until="load", timeout=60000)
                
                # Scroll pour charger les icônes et textes de ville
                for _ in range(5):
                    await page.mouse.wheel(0, 1000)
                    await asyncio.sleep(1)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                annonces = soup.find_all('a', href=True)

                for ad in annonces:
                    href = ad.get('href', '')
                    if "/vi/" in href or ".htm" in href:
                        full_url = href if href.startswith("http") else "https://www.avito.ma" + href
                        
                        price_tag = ad.find(['p', 'span'], class_=['dJAfqm', 'hsBiLW'])
                        title_tag = ad.find(['h3', 'p', 'span'], class_='iHApav') or ad.find('h3')
                        
                        if title_tag and price_tag:
                            name = title_tag.get_text(strip=True)
                            price = format_price(price_tag.get_text(strip=True))
                            
                            # --- NOUVELLE STRATÉGIE VILLE ---
                            # On cherche spécifiquement le badge qui contient le nom de la ville
                            # Souvent c'est le dernier badge de type span
                            badges = ad.find_all('span', class_='dGUnYf')
                            
                            ville = "Maroc"
                            infos_tech = []
                            
                            for b in badges:
                                # On nettoie le texte de l'icône directement
                                # separator=' ' évite de coller 'Casablanca' à 'Icon'
                                raw_text = b.get_text(separator=' ', strip=True)
                                
                                # Si le texte contient des chiffres, c'est l'année ou les KM, pas la ville
                                if any(char.isdigit() for char in raw_text):
                                    continue
                                
                                # On supprime les noms d'icônes connus
                                clean_text = re.sub(r'(Downward|Upward|Arrow|Icon|Location|Pin|MapPin|Map)', '', raw_text).strip()
                                
                                # Si après nettoyage il reste un mot propre, c'est notre ville
                                if len(clean_text) > 2 and clean_text.lower() not in ["neuf", "plus d'infos"]:
                                    ville = clean_text

                            # Extraction de l'année (Modèle)
                            annee = extract_year_from_text(name)
                            if not annee:
                                # Si pas dans le titre, on cherche dans les badges
                                for b in badges:
                                    txt = b.get_text(strip=True)
                                    if re.match(r"^(19|20)\d{2}$", txt):
                                        annee = txt
                                        break
                            
                            # Détails techniques
                            for b in badges:
                                txt = b.get_text(strip=True).lower()
                                if any(x in txt for x in ['km', 'diesel', 'essence', 'manuel', 'auto']):
                                    infos_tech.append(b.get_text(strip=True))

                            if any(char.isdigit() for char in price):
                                page_data.append({
                                    "name": name[:30],
                                    "price": price,
                                    "ville": ville,
                                    "annee": annee or "N/C",
                                    "details": " | ".join(infos_tech),
                                    "url": full_url
                                })

                if page_data:
                    # Supprime les doublons
                    unique = list({v['url']:v for v in page_data}.values())
                    send_telegram_page(unique, i)
                    print(f"✅ Page {i} traitée.")

            except Exception as e:
                print(f"Erreur Page {i}: {e}")
            finally:
                await page.close()
            await asyncio.sleep(2)
        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
