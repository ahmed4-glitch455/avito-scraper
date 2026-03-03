import asyncio
import os
import datetime
import requests
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_API")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE_URL = "https://www.avito.ma/fr/maroc/voitures_d_occasion-%C3%A0_vendre?price=-60000"
MAX_PAGES = 30 

def send_telegram_page(data, page_number):
    if not data: return
    date_str = datetime.datetime.now().strftime("%H:%M")
    header = f"🚗 *Avito Page {page_number}/30* ({date_str})\n"
    header += "```\n"
    header += f"{'Modèle':<18} | {'Prix':<10}\n"
    header += "-" * 31 + "\n"
    # On limite à 15 voitures par message pour éviter de bloquer Telegram
    body = "".join([f"{car['name']:<18} | {car['price']:<10}\n" for car in data[:15]])
    msg = header + body + "```"
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg, "parse_mode": "Markdown"})

async def scrape_avito():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

        for i in range(1, MAX_PAGES + 1):
            url = f"{BASE_URL}&o={i}"
            page = await context.new_page()
            page_data = []

            try:
                print(f"Analyse Page {i}...")
                await page.goto(url, wait_until="networkidle", timeout=60000)
                
                # On scrolle un peu pour charger le contenu
                await page.mouse.wheel(0, 2000)
                await asyncio.sleep(5)

                content = await page.content()
                soup = BeautifulSoup(content, 'html.parser')
                
                # --- NOUVELLE STRATÉGIE ---
                # On cherche TOUS les éléments <p> ou <span> qui contiennent "DH"
                elements_prix = soup.find_all(lambda tag: tag.name in ['p', 'span', 'h3'] and 'DH' in tag.text)
                
                for el in elements_prix:
                    prix_text = el.get_text(strip=True)
                    # On vérifie que c'est bien un prix (chiffres + DH)
                    if any(char.isdigit() for char in prix_text) and len(prix_text) < 20:
                        
                        # Pour chaque prix trouvé, on cherche le titre le plus proche (souvent juste au-dessus)
                        # On remonte un peu dans le code HTML pour trouver un texte de titre
                        parent = el.find_parent('div')
                        if parent:
                            # On cherche le premier texte qui n'est pas le prix
                            titre_tag = parent.find(['h2', 'h3', 'p'])
                            if titre_tag:
                                titre = titre_tag.get_text(strip=True)[:18]
                                if titre and "DH" not in titre:
                                    price_clean = prix_text.replace("DH", "").replace(" ", "").strip()
                                    page_data.append({"name": titre, "price": price_clean})

                # Nettoyage des doublons
                seen = set()
                final_data = []
                for d in page_data:
                    if d['name'] not in seen:
                        final_data.append(d)
                        seen.add(d['name'])

                if final_data:
                    send_telegram_page(final_data, i)
                    print(f"✅ Page {i} : {len(final_data)} voitures envoyées.")
                else:
                    # Si toujours vide, on affiche le texte de la page pour comprendre (dans les logs)
                    print(f"❌ Page {i} toujours vide. Nombre d'éléments DH trouvés: {len(elements_prix)}")

            except Exception as e:
                print(f"Erreur Page {i}: {e}")
            finally:
                await page.close()
            await asyncio.sleep(2)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(scrape_avito())
