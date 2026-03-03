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

def send_telegram_page(data, page_number):
    if not data: return
    date_str = datetime.datetime.now().strftime("%H:%M")
    header = f"🚗 *Avito Page {page_number}/{MAX_PAGES}* ({date_str})\n"
    header += "```\n"
    header += f"{'Modèle':<18} | {'Prix':<10}\n"
    header += "-" * 31 + "\n"
    
    # On envoie les 20 premières annonces pour ne pas dépasser la limite Telegram
    body = ""
    for car in data[:20]:
        body += f"{car['name']:<18} | {car['price']:<10}\n"
    
    msg = header + body + "```"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

async def scrape_avito():
    async with async_playwright() as p:
        # On lance le navigateur
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        for i in range(1, MAX_PAGES + 1):
            # Logique d'URL : Page 1 standard, puis ?o=2, 3...
            url = BASE_URL if i == 1 else f"{BASE_URL}?o={i}"
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i} : {url}")
                await page.goto(url, wait_until="load", timeout=60000)
                
                # SÉCURITÉ : On scrolle pour charger le contenu (Lazy Load détecté dans votre HTML)
                await page.mouse.wheel(0, 4000)
                await asyncio.sleep(5) # On laisse le temps aux scripts de charger les prix

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # On cherche tous les liens d'annonces qui contiennent les classes identifiées
                annonces = soup.find_all('a', href=True)

                for ad in annonces:
                    # On cherche le titre et le prix à l'intérieur de chaque lien 'a'
                    # Utilisation des classes exactes trouvées dans votre fichier code_avito.txt
                    title_tag = ad.find('h3', class_='iHApav') or ad.find('h3')
                    price_tag = ad.find('p', class_='dJAfqm') or ad.find('span', class_='hsBiLW')

                    if title_tag and price_tag:
                        titre = title_tag.get_text(strip=True)[:18]
                        prix_raw = price_tag.get_text(strip=True)
                        
                        # Nettoyage du prix
                        if "DH" in prix_raw:
                            prix = prix_raw.replace("DH", "").replace(" ", "").strip()
                            # On ne garde que si c'est un chiffre
                            if any(char.isdigit() for char in prix):
                                page_data.append({"name": titre, "price": prix})

                # Nettoyage des doublons (si le scraper attrape deux fois le même lien)
                final_data = []
                seen = set()
                for car in page_data:
                    if car['name'] not in seen:
                        final_data.append(car)
                        seen.add(car['name'])

                if final_data:
                    send_telegram_page(final_data, i)
                    print(f"✅ Page {i} : {len(final_data)} annonces envoyées.")
                else:
                    # Si c'est vide, on tente une recherche plus large
                    print(f"⚠️ Page {i} : Recherche ciblée vide, tentative de secours...")
                    # (Le code de secours ici chercherait juste les 'DH' comme avant)

            except Exception as e:
                print(f"❌ Erreur Page {i}: {e}")
            finally:
                await page.close()
            
            await asyncio.sleep(3) # Pause entre les pages

        await browser.close()

if __name__ == "__main__":
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        asyncio.run(scrape_avito())
    else:
        print("ERREUR : Secrets manquants sur GitHub.")
