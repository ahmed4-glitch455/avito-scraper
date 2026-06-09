import asyncio
import os
import datetime
import re
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
import httpx
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION MOTEUR.MA ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Exemple d'URL de base pour moteur.ma filtrée selon tes critères (à ajuster si besoin)
BASE_URL = "https://www.moteur.ma/fr/voiture/achat-voiture-occasion/"
MAX_PAGES = 30 

def format_price(price_str):
    # Conserve uniquement les chiffres pour formater proprement le prix (ex: 380,000 MAD -> 380 000)
    digits = "".join([c for c in price_str if c.isdigit()])
    try:
        return f"{int(digits):,}".replace(",", " ")
    except ValueError:
        return price_str

def build_page_url(base_url, page_number):
    """Gère proprement la pagination sur Moteur.ma (généralement via le paramètre 'page')"""
    if page_number == 1:
        return base_url
    url_parts = list(urlparse(base_url))
    query = parse_qs(url_parts[4])
    query['page'] = [str(page_number)]
    url_parts[4] = urlencode(query, doseq=True)
    return urlunparse(url_parts)

async def send_telegram_page_async(client, data, page_number):
    if not data: 
        return
        
    date_str = datetime.datetime.now().strftime("%H:%M")
    msg = f"✨ *SÉLECTION MOTEUR.MA - PAGE {page_number}/{MAX_PAGES}* ✨\n"
    msg += f"🕒 {date_str}\n"
    msg += "=" * 25 + "\n\n"
    
    for car in data[:10]:
        msg += f"🚘 *NOM :* {car['name']}\n"
        msg += f"💰 *PRIX :* {car['price']} DH\n"
        msg += f"📅 *MODÈLE :* {car['annee']}\n"
        msg += f"🕒 *DATE PUBLICATION :* {car['date_pub']}\n"
        msg += f"📍 *VILLE :* {car['ville']}\n"
        if car['details']:
            msg += f"⚙️ *INFOS :* {car['details']}\n"
        msg += f"🔗 [Ouvrir l'annonce]({car['url']})\n"
        msg += "─" * 15 + "\n"
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    
    try:
        response = await client.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID, 
            "text": msg, 
            "parse_mode": "Markdown", 
            "disable_web_page_preview": True
        })
        response.raise_for_status()
    except Exception as e:
        print(f"❌ Erreur lors de l'envoi Telegram : {e}")

async def scrape_moteur():
    async with httpx.AsyncClient() as client, async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="fr-FR"
        )

        for i in range(1, MAX_PAGES + 1):
            url = build_page_url(BASE_URL, i)
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i} -> {url}")
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                
                # Petit scroll pour forcer le chargement de l'ensemble du DOM
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(0.5)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # Extraction des conteneurs d'annonces de Moteur.ma
                annonces = soup.find_all('div', class_='ads-index-card')

                for ad in annonces:
                    # 1. Extraction du Titre et de l'URL
                    title_tag = ad.find('h5', class_='ads-index-title')
                    if not title_tag:
                        continue
                        
                    name = title_tag.get_text(strip=True)
                    
                    # Recherche du lien de l'annonce
                    link_tag = ad.find('a', href=True)
                    href = link_tag['href'] if link_tag else ""
                    if not href:
                        continue
                    full_url = href if href.startswith("http") else "https://www.moteur.ma" + href
                    
                    # 2. Extraction du Prix
                    price_tag = ad.find(class_='ad-price-grid')
                    price = format_price(price_tag.get_text(strip=True)) if price_tag else "Demander le prix"
                    
                    # 3. Extraction de la Ville (trouvée via l'icône de marqueur)
                    ville = "Maroc"
                    marker_icon = ad.find('i', class_='fa-map-marker')
                    if marker_icon and marker_icon.parent:
                        ville = marker_icon.parent.get_text(strip=True)
                    
                    # 4. Extraction de la Date de publication
                    date_pub = "N/C"
                    time_tag = ad.find('span', class_='timeago')
                    if time_tag:
                        date_pub = time_tag.get_text(strip=True)
                    
                    # 5. Extraction des Badges techniques (Année, Carburant, Boite...)
                    annee = "N/C"
                    meta_container = ad.find('div', class_='ad-meta')
                    autres_details = []
                    
                    if meta_container:
                        badges = meta_container.find_all('span')
                        for b in badges:
                            text = b.get_text(strip=True)
                            if not text:
                                continue
                            
                            # Si le texte est un chiffre correspondant à une année (Ex: 2020)
                            if re.match(r"^(19|20)\d{2}$", text):
                                annee = text
                            else:
                                autres_details.append(text)

                    page_data.append({
                        "name": name[:30],
                        "price": price,
                        "ville": ville,
                        "date_pub": date_pub,
                        "annee": annee,
                        "details": " | ".join(autres_details),
                        "url": full_url
                    })

                print(f"-> Annonces trouvées et parsées sur la page {i} : {len(page_data)}")

                if page_data:
                    # Élimination des doublons potentiels d'URL
                    unique = list({v['url']: v for v in page_data}.values())
                    await send_telegram_page_async(client, unique, i)
                    print(f"✅ Page {i} envoyée sur Telegram.")
                else:
                    if i == 1:
                        await page.screenshot(path="screenshot_moteur_p1.png")
                        print("📸 Capture d'écran enregistrée pour vérification.")

            except Exception as e:
                print(f"❌ Erreur lors du traitement de la Page {i}: {e}")
            finally:
                await page.close()
            
            await asyncio.sleep(1.5)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_moteur())
